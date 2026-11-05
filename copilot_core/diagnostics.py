"""Bounded local failure metadata; never record exception messages or user content."""
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import threading
import traceback

_lock = threading.Lock()


def record_failure(info, stage="runtime", directory=None):
    folder = Path(directory) if directory else Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "state") / "ZoomCopilot" / "logs"
    path = folder / "runtime.log"
    try:
        with _lock:
            folder.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(path, maxBytes=65536, backupCount=2, encoding="utf-8")
            try:
                handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
                frames = traceback.extract_tb(info[2])
                locations = " > ".join(f"{Path(f.filename).name}:{f.lineno}:{f.name}" for f in frames[-12:])
                record = logging.LogRecord("zoom_copilot", logging.ERROR, "", 0, "%s %s %s",
                                           (stage, info[0].__name__, locations), None)
                handler.emit(record)
            finally:
                handler.close()
        return path
    except OSError:
        return None
