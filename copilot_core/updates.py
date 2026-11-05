"""Bounded, anonymous GitHub release checks. Never download or execute updates."""
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
import time
import tkinter as tk
import webbrowser

import requests

from .version import APP_VERSION

RELEASES_URL = "https://github.com/Sombra-1/zoom-copilot/releases/latest"
API_URL = "https://api.github.com/repos/Sombra-1/zoom-copilot/releases/latest"
CHECK_INTERVAL = 24 * 60 * 60


def version_tuple(value):
    if isinstance(value, str) and re.fullmatch(r"v?\d{1,5}\.\d{1,5}\.\d{1,5}", value):
        return tuple(int(part) for part in value.removeprefix("v").split("."))
    return None


def fetch_latest():
    # No account token, meeting text, screenshots, settings, or machine ID.
    with requests.get(API_URL, headers={"Accept": "application/vnd.github+json",
                                       "User-Agent": "ZoomCopilot/" + APP_VERSION},
                      timeout=(4, 8), stream=True, allow_redirects=False,
                      auth=lambda prepared: prepared) as response:
        if response.status_code != 200:
            raise ValueError("Release unavailable")
        body = bytearray()
        for chunk in response.iter_content(8192):
            body.extend(chunk)
            if len(body) > 65536:
                raise ValueError("Release response too large")
        data = json.loads(body)
    if not isinstance(data, dict) or data.get("draft") is not False or data.get("prerelease") is not False:
        raise ValueError("Not a stable release")
    tag = data.get("tag_name")
    if version_tuple(tag) is None:
        raise ValueError("Invalid version")
    return tag.removeprefix("v")


class UpdateChecker:
    def __init__(self, root, view, state_file=None, enabled=True, clock=time.time):
        folder = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "state")
        self.path = Path(state_file) if state_file else folder / "ZoomCopilot" / "updates.json"
        self.root, self.view, self.clock = root, view, clock
        self.closed, self.busy = False, False
        self.latest, self.dismissed, self.checked = "", "", 0.0
        self.message = "Check for updates"
        try:
            if self.path.stat().st_size <= 16384:
                state = json.loads(self.path.read_text(encoding="utf-8"))
                self.latest = state.get("latest", "") if version_tuple(state.get("latest")) else ""
                self.dismissed = state.get("dismissed", "") if version_tuple(state.get("dismissed")) else ""
                checked = state.get("checked", 0)
                if isinstance(checked, (int, float)) and not isinstance(checked, bool) and math.isfinite(checked):
                    self.checked = checked
        except (OSError, ValueError, AttributeError):
            pass
        self.timer = root.after(8000, self.check) if enabled else None

    @property
    def available(self):
        return bool(version_tuple(self.latest) and version_tuple(self.latest) > version_tuple(APP_VERSION))

    def save(self):
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix=".update-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump({"latest": self.latest, "dismissed": self.dismissed, "checked": self.checked}, stream)
            os.replace(temporary, self.path)
        except OSError:
            pass
        finally:
            if temporary:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def sync(self):
        if not self.closed:
            from .update_ui import refresh
            refresh(self.view(), self)

    def check(self, manual=False):
        if self.closed or self.busy:
            return
        now = self.clock()
        if not manual and 0 <= now - self.checked < CHECK_INTERVAL:
            self.sync()
            self.schedule()
            return
        self.busy, self.message = True, "Checking…"
        self.sync()

        def worker():
            try:
                latest = fetch_latest()
            except (requests.RequestException, OSError, ValueError):
                latest = None
            self.root._dispatcher.post(lambda: self.complete(latest, manual))
        threading.Thread(target=worker, name="release-check", daemon=True).start()

    def complete(self, latest, manual):
        if self.closed:
            return
        self.busy = False
        self.checked = self.clock()
        if latest is None:
            self.message = "Offline · try again"
        else:
            self.latest = latest
            self.message = "Update available" if self.available else "You're up to date"
            if manual:
                self.dismissed = ""
        self.save()
        self.sync()
        self.schedule()

    def schedule(self):
        if self.closed:
            return
        if self.timer is not None:
            self.root.after_cancel(self.timer)
        remaining = max(1, min(CHECK_INTERVAL, CHECK_INTERVAL - (self.clock() - self.checked)))
        self.timer = self.root.after(int(remaining * 1000), self.check)

    def dismiss(self):
        self.dismissed = self.latest
        self.save()
        self.sync()

    def open_release(self):
        try:
            opened = webbrowser.open(RELEASES_URL, new=2)
        except (OSError, webbrowser.Error):
            opened = False
        if not opened:
            from tkinter import messagebox
            messagebox.showinfo("Latest Zoom Copilot release", "Open this link in your browser:\n\n" + RELEASES_URL,
                                parent=self.root)

    def close(self):
        self.closed = True
        if self.timer is not None:
            try:
                self.root.after_cancel(self.timer)
            except tk.TclError:
                pass
