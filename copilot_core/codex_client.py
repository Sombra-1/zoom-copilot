"""Official Codex app-server newline JSON-RPC. Never reads credential files."""
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from pathlib import Path

from .processes import OwnedProcess
from .version import APP_VERSION


class CodexError(RuntimeError):
    pass


class Cancelled(CodexError):
    pass


def _windows_codex_candidates():
    """Known CLI locations, including desktop-managed CLI bins, never its GUI."""
    local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    managed = local / "OpenAI" / "Codex" / "bin"
    try:
        # Updates use a new directory; do not pin a versioned path in settings.
        versions = sorted(managed.glob("*/codex.exe"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        versions = []
    yield from versions
    yield managed / "codex.exe"
    yield Path.home() / ".local" / "bin" / "codex.exe"


def find_codex(configured=""):
    if configured:
        path = Path(os.path.expandvars(configured.strip().strip('"'))).expanduser()
        if path.is_file() and path.suffix.lower() not in (".cmd", ".bat", ".ps1"):
            return str(path.resolve())
        return None
    # Deliberately select the CLI, never a Codex desktop executable or URI.
    found = shutil.which("codex.exe" if os.name == "nt" else "codex")
    if found:
        return found
    if os.name == "nt":
        for path in _windows_codex_candidates():
            if path.is_file():
                return str(path.resolve())
        shim = shutil.which("codex")
        node = shutil.which("node.exe")
        # Explorer may also lack npm's per-user bin in its inherited PATH.
        if not shim:
            npm = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "npm"
            shim = str(npm / "codex.cmd") if (npm / "codex.cmd").is_file() else None
        if shim and node:
            # Official npm launcher, invoked as argv through Node, never cmd.exe.
            script = Path(shim).parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
            if script.is_file():
                return (node, str(script))
    return None


class CodexClient:
    def __init__(self, executable, cwd, timeout=120, active=None):
        self.timeout = timeout
        self.active = active or (lambda: True)
        self.deadline = time.monotonic() + timeout
        self._closed = threading.Event()
        self._write_lock = threading.Lock()
        self._events = queue.Queue(maxsize=2048)
        self._serial = 0
        self._deferred = deque(maxlen=2048)
        command = list(executable) if isinstance(executable, tuple) else [executable]
        command += ["app-server", "--listen", "stdio://"]
        for setting in (
            'features.shell_tool=false', 'features.apply_patch_freeform=false',
            'features.apps=false', 'features.skills=false', 'features.multi_agent=false',
            'tools.view_image=false',
            'web_search="disabled"', 'mcp_servers={}', 'plugins={}',
            'history.persistence="none"', 'analytics.enabled=false',
            'feedback.enabled=false',
        ):
            command += ["-c", setting]
        self.owner = OwnedProcess(command, cwd=cwd, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  text=True, encoding="utf-8", bufsize=1)
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self):
        try:
            for line in self.owner.process.stdout:
                if self._closed.is_set():
                    break
                if len(line) > 4_000_000:
                    raise ValueError("Oversized protocol message")
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    raise ValueError("Invalid protocol message")
                self._events.put_nowait(obj)
        except (ValueError, OSError, queue.Full):
            pass
        finally:
            self._closed.set()

    def send(self, message):
        try:
            with self._write_lock:
                self.owner.process.stdin.write(json.dumps(message) + "\n")
                self.owner.process.stdin.flush()
        except (OSError, ValueError):
            raise CodexError("Codex process disconnected") from None

    def receive(self, include_deferred=True):
        while True:
            if not self.active():
                raise Cancelled("Codex request cancelled")
            if time.monotonic() >= self.deadline:
                raise CodexError("Codex request timed out")
            if include_deferred and self._deferred:
                return self._deferred.popleft()
            try:
                obj = self._events.get(timeout=0.05)
            except queue.Empty:
                if self._closed.is_set():
                    raise CodexError("Codex process stopped; check installation and connection") from None
                continue
            if "method" in obj and "id" in obj:
                # No approval, command, connector, credential refresh, or dynamic tool
                # request may be executed implicitly by meeting inference.
                self.send({"id": obj["id"], "error": {
                    "code": -32601, "message": "Tools are disabled in meeting mode"}})
                continue
            return obj

    def rpc(self, method, params):
        self._serial += 1
        request_id = self._serial
        self.send({"id": request_id, "method": method, "params": params})
        while True:
            msg = self.receive(include_deferred=False)
            if msg.get("id") == request_id:
                if "error" in msg:
                    # Server error strings may contain context or sensitive paths.
                    raise CodexError(f"Codex rejected {method}; check CLI version, model and account")
                return msg.get("result", {})
            self._deferred.append(msg)

    def initialize(self):
        self.rpc("initialize", {"clientInfo": {"name": "zoom_copilot",
                  "title": "Zoom Copilot", "version": APP_VERSION}})
        self.send({"method": "initialized", "params": {}})

    def safe_thread_config(self):
        resolved = self.rpc("config/read", {"includeLayers": False}).get("config", {})
        # CLI table overrides can merge with existing tables: explicitly disable
        # every inherited MCP server, plugin and app before starting any thread.
        config = {"features.shell_tool": False, "features.apply_patch_freeform": False,
                  "features.apps": False, "features.skills": False,
                  "features.multi_agent": False, "tools.view_image": False,
                  "web_search": "disabled"}
        for section in ("mcp_servers", "plugins", "apps"):
            for name in (resolved.get(section) or {}):
                segment = name if re.fullmatch(r"[A-Za-z0-9_-]+", name) else json.dumps(name)
                config[f'{section}.{segment}.enabled'] = False
        return config

    def interrupt(self, thread_id, turn_id):
        try:
            self.send({"id": 999999, "method": "turn/interrupt",
                       "params": {"threadId": thread_id, "turnId": turn_id}})
        except CodexError:
            pass

    def close(self):
        self._closed.set()
        self.owner.close()
        self._reader.join(timeout=1)
