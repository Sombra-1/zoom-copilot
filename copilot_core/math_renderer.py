"""Offline KaTeX rasterization in an isolated, hidden browser helper."""
import base64
import json
import subprocess
import sys
import threading
from collections import OrderedDict
from pathlib import Path

from .processes import OwnedProcess


class MathRenderer:
    def __init__(self):
        self._cache = OrderedDict()
        self._lock = threading.Lock()
        self._owners = set()
        self.closed = False

    def render(self, equations, font_size=18, width=440):
        key = (tuple(equations[:60]), font_size, width)
        with self._lock:
            if self.closed:
                return []
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            owner = OwnedProcess([sys.executable, "-m", "copilot_core.math_worker"],
                                 cwd=str(Path(__file__).resolve().parents[1]),
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
            self._owners.add(owner)
        try:
            output, _ = owner.process.communicate(json.dumps({"equations": list(key[0]),
                                                             "font": font_size, "width": width}), timeout=25)
            if owner.process.returncode:
                return []
            values = json.loads(output)
            images = [base64.b64decode(x) if isinstance(x, str) else None for x in values]
            with self._lock:
                self._cache[key] = images
                while len(self._cache) > 32:
                    self._cache.popitem(last=False)
                while sum(len(image) for value in self._cache.values() for image in value if image) > 16_000_000:
                    self._cache.popitem(last=False)
            return images
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return []
        finally:
            with self._lock:
                self._owners.discard(owner)
            owner.close()

    def close(self):
        with self._lock:
            self.closed = True
            owners = list(self._owners)
        for owner in owners:
            owner.close()
