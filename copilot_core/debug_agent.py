"""Opt-in development operations with a fixed repository boundary and commands."""
import ast
import difflib
import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from .processes import OwnedProcess


def redact(text, limit=24000):
    text = re.sub(r"(?i)(bearer\s+)[^\s]+", r"\1[REDACTED]", str(text))
    text = re.sub(r"\b(?:sk-|gsk_)[A-Za-z0-9_-]{8,}", "[REDACTED]", text)
    text = re.sub(r'(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)'
                  r'\s*[=:]\s*)[^\s,;]+', r'\1[REDACTED]', text)
    text = re.sub(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+", "[IMAGE REDACTED]", text)
    return text[-limit:] if limit else text


@dataclass(frozen=True)
class ProposedEdit:
    path: str
    original_hash: str
    replacement: str
    diff: str
    reason: str


class DebugAgent:
    def __init__(self, repository, enabled=False):
        if not enabled:
            raise PermissionError("Developer mode is disabled")
        self.root = Path(repository).resolve(strict=True)
        self._lock = threading.Lock()
        self._edit_lock = threading.Lock()
        self._owners = set()
        self._closed = False

    def source_path(self, relative):
        path = (self.root / relative).resolve(strict=True)
        if self.root not in path.parents or path.suffix != ".py":
            raise PermissionError("Only project Python sources may be inspected or edited")
        rel = path.relative_to(self.root)
        if rel.parts[0] not in ("zoom_copilot.py", "setup.py", "copilot_core", "tests"):
            raise PermissionError("Path is outside the development source allowlist")
        if path.stat().st_size > 300000:
            raise ValueError("Source too large")
        return path

    def files(self):
        rows = ["zoom_copilot.py", "setup.py"]
        for directory in ("copilot_core", "tests"):
            for path in (self.root / directory).rglob("*.py"):
                try:
                    rel = str(path.relative_to(self.root))
                    self.source_path(rel)
                    rows.append(rel)
                except (OSError, PermissionError):
                    pass
        return rows

    def inspect(self, relative):
        return redact(self.source_path(relative).read_text(encoding="utf-8"), limit=None)

    def check(self, name):
        return self._check(name, self.root)

    def _check(self, name, directory):
        commands = {
            "tests": [sys.executable, "-m", "unittest", "discover", "-v"],
            "lint": [sys.executable, "-m", "pyflakes", "zoom_copilot.py", "setup.py", "copilot_core", "tests"],
            "security": [sys.executable, "-m", "bandit", "-q", "-lll", "-r", "zoom_copilot.py", "setup.py", "copilot_core"],
        }
        if name not in commands:
            raise PermissionError("Unsupported development command")
        with self._lock:
            if self._closed:
                raise RuntimeError("Developer tools closed")
            owner = OwnedProcess(commands[name], cwd=str(directory), stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            self._owners.add(owner)
        try:
            output, _ = owner.process.communicate(timeout=90)
            return owner.process.returncode, redact(output)
        finally:
            with self._lock:
                self._owners.discard(owner)
            owner.close()

    def close(self):
        with self._lock:
            self._closed = True
            owners = list(self._owners)
        for owner in owners:
            owner.close()

    def propose(self, relative, replacement, reason=""):
        path = self.source_path(relative)
        original = path.read_bytes()
        if not isinstance(replacement, str) or len(replacement) > 300000:
            raise ValueError("Invalid replacement")
        ast.parse(replacement, filename=str(path))
        diff = "".join(difflib.unified_diff(original.decode("utf-8").splitlines(keepends=True),
                                            replacement.splitlines(keepends=True),
                                            fromfile=str(relative), tofile=str(relative)))
        return ProposedEdit(str(relative), hashlib.sha256(original).hexdigest(), replacement, diff, reason)

    def propose_change(self, relative, before, after, reason, original_hash):
        path = self.source_path(relative)
        original = path.read_bytes()
        if hashlib.sha256(original).hexdigest() != original_hash:
            raise RuntimeError("Source changed while Codex was investigating")
        text = original.decode("utf-8").replace("\r\n", "\n")
        if not isinstance(before, str) or not before or text.count(before) != 1:
            raise ValueError("Proposed edit must match exactly one source fragment")
        if not isinstance(after, str):
            raise ValueError("Invalid replacement fragment")
        replacement = text.replace(before.replace("\r\n", "\n"), after.replace("\r\n", "\n"), 1)
        if b"\r\n" in original:
            replacement = replacement.replace("\n", "\r\n")
        return self.propose(relative, replacement, reason)

    def approve(self, proposal, approved=False):
        if not approved:
            raise PermissionError("Explicit approval is required to apply a proposed edit")
        with self._edit_lock:
            path = self.source_path(proposal.path)
            self._verify_original(path, proposal)
            ast.parse(proposal.replacement, filename=str(path))
            with tempfile.TemporaryDirectory(prefix="copilot-check-") as folder:
                candidate = Path(folder)
                # Copy project inputs only. User settings, logs and environments
                # are outside this temporary test workspace.
                for name in ("zoom_copilot.py", "setup.py", "launch.pyw", "Zoom Copilot.exe",
                             "support.json", "copilot_core", "tests", "assets"):
                    source = self.root / name
                    if not source.exists() or self._is_link(source):
                        continue
                    if source.is_dir():
                        shutil.copytree(source, candidate / name, ignore=self._ignore_snapshot_files)
                    elif source.is_file():
                        shutil.copy2(source, candidate / name)
                (candidate / path.relative_to(self.root)).write_bytes(proposal.replacement.encode("utf-8"))
                result = self._check("tests", candidate)
            if result[0] != 0:
                return result
            with self._lock:
                if self._closed:
                    raise RuntimeError("Developer tools closed before applying the edit")
                if self.source_path(proposal.path) != path:
                    raise RuntimeError("File path changed since review")
                self._verify_original(path, proposal)
                self._replace_source(path, proposal.replacement)
            return result

    @staticmethod
    def _is_link(path):
        info = path.lstat()
        return stat.S_ISLNK(info.st_mode) or bool(
            getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        )

    @staticmethod
    def _ignore_snapshot_files(folder, names):
        ignored = []
        for name in names:
            path = Path(folder) / name
            if (name.startswith(".") or name in ("__pycache__", "venv", "work")
                    or DebugAgent._is_link(path)):
                ignored.append(name)
        return ignored

    @staticmethod
    def _verify_original(path, proposal):
        if hashlib.sha256(path.read_bytes()).hexdigest() != proposal.original_hash:
            raise RuntimeError("File changed since review. Generate and review a new proposal.")

    @staticmethod
    def _replace_source(path, replacement):
        descriptor, temporary = tempfile.mkstemp(prefix=".copilot-patch-", dir=str(path.parent))
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                stream.write(replacement)
            shutil.copymode(path, temporary)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
