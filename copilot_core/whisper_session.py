"""Keep native Local Whisper work in an owned, cancellable process."""
import base64
from contextlib import contextmanager
import errno
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

from .codex_client import Cancelled
from .processes import OwnedProcess

MAX_AUDIO_BYTES = 45 * 16000 * 4
MAX_REQUEST = MAX_AUDIO_BYTES * 4 // 3 + 2048
MAX_REPLY = 65536
_cache_lock = threading.Lock()


class WhisperBusy(RuntimeError):
    def __init__(self):
        super().__init__("Local Whisper's model cache is in use. Wait for cleanup or model work to finish, "
                         "or stop Local Whisper in another window, then retry.")


def cache_busy():
    return _cache_lock.locked()


def _hub_cache_directory():
    hub = os.environ.get("HF_HUB_CACHE") or os.environ.get("HUGGINGFACE_HUB_CACHE")
    if hub:
        return Path(hub).expanduser().resolve()
    cache_home = os.environ.get("XDG_CACHE_HOME") or "~/.cache"
    hf_home = os.environ.get("HF_HOME") or os.path.join(cache_home, "huggingface")
    return (Path(hf_home).expanduser() / "hub").resolve()


def whisper_cache_directory():
    """Keep models apart from older apps that can delete the original cache."""
    cache = _hub_cache_directory() / "zoom-copilot-v2.1"
    if cache.resolve() != cache:
        raise RuntimeError("The Zoom Copilot model cache must not point outside its own folder.")
    return str(cache)


@contextmanager
def cache_lease():
    """Hold an OS lock until this operation or process closes its file handle."""
    cache = Path(whisper_cache_directory()).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    # Keep the lock file in place so concurrent users always lock the same file.
    with (cache / ".zoom-copilot.lock").open("a+b") as lease:
        lease.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lease.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise WhisperBusy() from None
            raise
        yield


@contextmanager
def model_maintenance():
    if not _cache_lock.acquire(blocking=False):
        raise WhisperBusy()
    try:
        with cache_lease():
            yield
    finally:
        _cache_lock.release()


class WhisperSession:
    """One serialized decoder per listening session. Audio stays in pipes."""

    def __init__(self):
        self._lock = threading.Lock()
        self._closed = threading.Event()
        self._owner = None

    @staticmethod
    def _reap(owner):
        try:
            owner.close()
        finally:
            if owner.process.poll() is not None:
                _cache_lock.release()

    def _start(self):
        if self._closed.is_set():
            raise Cancelled("Local transcription canceled")
        if not _cache_lock.acquire(blocking=False):
            raise WhisperBusy()
        try:
            env = dict(os.environ, HF_HUB_CACHE=str(_hub_cache_directory()))
            owner = OwnedProcess([sys.executable, "-m", "copilot_core.whisper_worker"],
                                 cwd=str(Path(__file__).resolve().parents[1]), stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
        except Exception:
            _cache_lock.release()
            raise
        with self._lock:
            if not self._closed.is_set():
                self._owner = owner
                return owner
        self._reap(owner)
        raise Cancelled("Local transcription canceled")

    def transcribe(self, audio, model, language, overlap_samples=0):
        import numpy as np

        samples = np.asarray(audio, dtype="<f4").reshape(-1)
        if samples.nbytes > MAX_AUDIO_BYTES:
            raise ValueError("Local transcription input is too large")
        with self._lock:
            owner = self._owner
        if owner is None:
            owner = self._start()
        payload = {"audio": base64.b64encode(samples.tobytes()).decode("ascii"),
                   "model": model, "language": language, "overlap_samples": overlap_samples}
        try:
            owner.process.stdin.write(json.dumps(payload).encode("utf-8") + b"\n")
            owner.process.stdin.flush()
            reply = owner.process.stdout.readline(MAX_REPLY + 1)
            if not reply.endswith(b"\n") or len(reply) > MAX_REPLY:
                raise ValueError("Local Whisper response was incomplete")
            result = json.loads(reply)
            if not isinstance(result, dict) or not isinstance(result.get("text", result.get("error")), str):
                raise ValueError("Invalid Local Whisper response")
        except (OSError, ValueError) as exc:
            with self._lock:
                owns_process = self._owner is owner
                if owns_process:
                    self._owner = None
            if owns_process:
                self._reap(owner)
            if self._closed.is_set():
                raise Cancelled("Local transcription canceled") from None
            raise RuntimeError("Local Whisper worker stopped unexpectedly") from exc
        if self._closed.is_set():
            raise Cancelled("Local transcription canceled")
        if result.get("busy") is True:
            raise WhisperBusy()
        if "error" in result:
            raise RuntimeError(result["error"])
        return result["text"]

    def close(self):
        with self._lock:
            self._closed.set()
            owner, self._owner = self._owner, None
        if owner is not None:
            threading.Thread(target=self._reap, args=(owner,), name="whisper-cleanup", daemon=True).start()
