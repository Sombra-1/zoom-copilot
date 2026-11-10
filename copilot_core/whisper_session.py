"""Keep native Local Whisper work in an owned, cancellable process."""
import base64
from contextlib import contextmanager
import json
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
        super().__init__("Local Whisper is finishing cleanup or managing a model. Try again shortly.")


def cache_busy():
    return _cache_lock.locked()


@contextmanager
def model_maintenance():
    if not _cache_lock.acquire(blocking=False):
        raise WhisperBusy()
    try:
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
            owner = OwnedProcess([sys.executable, "-m", "copilot_core.whisper_worker"],
                                 cwd=str(Path(__file__).resolve().parents[1]), stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except Exception:
            _cache_lock.release()
            raise
        with self._lock:
            if not self._closed.is_set():
                self._owner = owner
                return owner
        self._reap(owner)
        raise Cancelled("Local transcription canceled")

    def transcribe(self, audio, model, language):
        import numpy as np

        samples = np.asarray(audio, dtype="<f4").reshape(-1)
        if samples.nbytes > MAX_AUDIO_BYTES:
            raise ValueError("Local transcription input is too large")
        with self._lock:
            owner = self._owner
        if owner is None:
            owner = self._start()
        payload = {"audio": base64.b64encode(samples.tobytes()).decode("ascii"),
                   "model": model, "language": language}
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
        if "error" in result:
            raise RuntimeError(result["error"])
        return result["text"]

    def close(self):
        with self._lock:
            self._closed.set()
            owner, self._owner = self._owner, None
        if owner is not None:
            threading.Thread(target=self._reap, args=(owner,), name="whisper-cleanup", daemon=True).start()
