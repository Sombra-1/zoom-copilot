"""Local support links and a cumulative three-hour reminder. No telemetry."""
import json
import math
import os
from pathlib import Path
import tempfile
import time
import tkinter as tk
from tkinter import messagebox
from urllib.parse import urlsplit
import webbrowser

PROJECT_URL = "https://github.com/Sombra-1/zoom-copilot"
REMINDER_SECONDS = 3 * 60 * 60
POLL_MS = 10000


def valid_link(value, github=False):
    if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 for c in value):
        return False
    try:
        url = urlsplit(value)
        return bool(url.scheme == "https" and url.hostname and not url.username and not url.password
                    and (not github or url.hostname == "github.com"))
    except ValueError:
        return False


def load_links(root=None):
    root = Path(root) if root else Path(__file__).resolve().parents[1]
    result = {"repository_url": PROJECT_URL, "donation_url": ""}
    try:
        path = root / "support.json"
        if path.stat().st_size > 16384:
            return result
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in result:
            if valid_link(data.get(key), github=key == "repository_url"):
                result[key] = data[key]
    except (OSError, ValueError, AttributeError):
        pass
    return result


class UsageTracker:
    def __init__(self, path, clock=time.monotonic):
        self.path, self.clock = Path(path), clock
        self.seconds, self.dismissed, self.shown = 0.0, False, False
        try:
            if self.path.stat().st_size <= 16384:
                state = json.loads(self.path.read_text(encoding="utf-8"))
                value = state.get("usage_seconds", 0)
                if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                    self.seconds = max(0.0, min(REMINDER_SECONDS, float(value)))
                self.dismissed = state.get("reminder_dismissed") is True
                self.shown = state.get("reminder_shown") is True
        except (OSError, ValueError, AttributeError):
            pass
        self.last, self.active = clock(), False
        self.saved = self.seconds
        self.dirty = False

    @property
    def due(self):
        return self.seconds >= REMINDER_SECONDS and not self.dismissed and not self.shown

    def mark_shown(self):
        self.shown, self.dirty = True, True
        self.flush()

    def tick(self, active):
        now = self.clock()
        elapsed = now - self.last
        # Long event-loop pauses (including sleep) are not usage.
        if self.active and not self.dismissed and 0 < elapsed <= 30:
            value = min(REMINDER_SECONDS, self.seconds + elapsed)
            self.dirty = self.dirty or value != self.seconds
            self.seconds = value
        self.last, self.active = now, bool(active)
        if self.seconds - self.saved >= 60:
            self.flush()

    def dismiss(self):
        self.dismissed, self.dirty = True, True
        self.flush()

    def flush(self):
        if not self.dirty:
            return
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix=".support-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump({"usage_seconds": self.seconds, "reminder_dismissed": self.dismissed,
                           "reminder_shown": self.shown}, stream)
            os.replace(temporary, self.path)
            self.saved, self.dirty = self.seconds, False
        except OSError:
            pass
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def close(self):
        self.tick(False)
        self.flush()


def open_link(root, action, links):
    url = links["repository_url"] if action == "star" else links["donation_url"]
    if not url:
        messagebox.showinfo("Support Zoom Copilot",
                            "Donations are coming soon. You can already support the project by starring it on GitHub.",
                            parent=root)
        return False
    try:
        opened = webbrowser.open(url, new=2)
    except (OSError, webbrowser.Error):
        opened = False
    if not opened:
        messagebox.showinfo("Open support page", "Open this link in your browser:\n\n" + url, parent=root)
    return opened


def support_action(root, action):
    service = getattr(root, "_community", None)
    return service.open(action) if service else open_link(root, action, load_links())


class CommunitySupport:
    def __init__(self, root, active, view, state_file=None):
        folder = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "state")
        self.usage = UsageTracker(state_file or folder / "ZoomCopilot" / "community-support.json")
        self.root, self.active, self.view = root, active, view
        self.links = load_links()
        self.closed = False
        self.prompt_view = None
        self.timer = root.after(POLL_MS, self.poll)

    def sync(self):
        self.usage.tick(self.active())
        view = self.view()
        if view is not None and hasattr(view, "_support_strip"):
            from .support_ui import show_reminder
            # Consume the invitation only when it can actually be seen.
            if self.usage.due and self.root.state() == "normal":
                self.prompt_view = view
                self.usage.mark_shown()
            show_reminder(view, view is self.prompt_view and not self.usage.dismissed)

    def pause(self):
        self.usage.tick(False)

    def poll(self):
        if self.closed:
            return
        self.sync()
        self.timer = self.root.after(POLL_MS, self.poll)

    def dismiss(self):
        self.usage.dismiss()
        self.sync()

    def open(self, action):
        opened = open_link(self.root, action, self.links)
        if opened:
            # This records acting on the invitation, not a verified star/payment.
            self.dismiss()
        return opened

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.root.after_cancel(self.timer)
        except tk.TclError:
            pass
        self.usage.close()
