"""Private captures coordinated on Tk's UI thread. No implicit desktop fallback."""
import ctypes
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from .codex_client import Cancelled
from .processes import OwnedProcess


def windows_api():
    from ctypes import wintypes as w
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.GetAncestor.argtypes, user.GetAncestor.restype = [w.HWND, w.UINT], w.HWND
    user.SetWindowDisplayAffinity.argtypes = [w.HWND, w.DWORD]
    user.SetWindowDisplayAffinity.restype = w.BOOL
    user.GetWindowDisplayAffinity.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    user.GetWindowDisplayAffinity.restype = w.BOOL
    return user


def root_handle(widget):
    handle = widget.winfo_id()
    return windows_api().GetAncestor(handle, 2) or handle


def set_affinity(widget, hidden=True):
    if sys.platform != "win32":
        return False
    try:
        from ctypes import wintypes as w
        widget.update_idletasks()
        user = windows_api()
        handle = root_handle(widget)
        wanted = 0x11 if hidden else 0
        value = w.DWORD()
        return bool(user.SetWindowDisplayAffinity(handle, wanted) and
                    user.GetWindowDisplayAffinity(handle, ctypes.byref(value)) and value.value == wanted)
    except (OSError, AttributeError):
        return False


def is_excluded(widget):
    if sys.platform != "win32":
        return False
    try:
        from ctypes import wintypes as w
        value = w.DWORD()
        return bool(windows_api().GetWindowDisplayAffinity(root_handle(widget), ctypes.byref(value)) and value.value == 0x11)
    except (OSError, AttributeError):
        return False


def private_surfaces(root):
    import tkinter as tk
    result = [root]
    def visit(widget):
        for child in widget.winfo_children():
            if isinstance(child, tk.Menu):
                child.unpost()
            if isinstance(child, tk.Toplevel):
                result.append(child)
            visit(child)
    visit(root)
    return result


def flush_compositor():
    if sys.platform == "win32":
        try:
            ctypes.WinDLL("dwmapi").DwmFlush()
        except OSError:
            pass


def list_windows():
    if sys.platform != "win32":
        return []
    from ctypes import wintypes as w
    user = windows_api()
    user.IsWindowVisible.argtypes, user.IsWindowVisible.restype = [w.HWND], w.BOOL
    user.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    rows = []
    callback_type = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    def visit(handle, _):
        pid = w.DWORD()
        user.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        title = ctypes.create_unicode_buffer(512)
        user.GetWindowTextW(handle, title, len(title))
        if user.IsWindowVisible(handle) and title.value and pid.value != os.getpid():
            rows.append((int(handle), title.value))
        return True
    callback = callback_type(visit)
    user.EnumWindows.argtypes = [callback_type, w.LPARAM]
    user.EnumWindows(callback, 0)
    return rows


def capture_window(handle, active=None):
    """PrintWindow in an owned helper: hung/GPU/blank windows fail without desktop fallback."""
    if sys.platform != "win32" or not handle:
        raise RuntimeError("Select a Windows application window first")
    from PIL import Image, ImageStat
    with tempfile.TemporaryDirectory(prefix="zoom-copilot-window-") as folder:
        output = Path(folder) / "window.png"
        owner = OwnedProcess([sys.executable, "-m", "copilot_core.window_capture", str(int(handle)), str(output)],
                             cwd=str(Path(__file__).resolve().parents[1]),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 4
            while owner.process.poll() is None:
                if active and not active():
                    raise Cancelled("Capture cancelled")
                if time.monotonic() > deadline:
                    raise RuntimeError("Selected window did not respond to capture")
                time.sleep(0.03)
            if owner.process.returncode or not output.exists():
                raise RuntimeError("Window capture failed; select a region instead")
            with Image.open(output) as source:
                image = source.convert("RGB")
            if max(ImageStat.Stat(image).stddev) < 1:
                raise RuntimeError("Window returned a blank capture; select a region instead")
            return image
        finally:
            owner.close()


class CaptureController:
    def __init__(self, root, dispatcher, capture):
        self.root, self.dispatcher, self.capture = root, dispatcher, capture
        self.verified = False
        self.closed = False
        self._busy = False
        self._restore = []

    def probe(self):
        """Synthetic pixel test of THIS capturer; never transmit probe pixels."""
        import tkinter as tk
        if sys.platform != "win32":
            return False
        back = tk.Toplevel(self.root)
        front = None
        try:
            back.overrideredirect(True)
            back.geometry("96x96+40+40")
            back.configure(bg="#16b35b")
            back.attributes("-topmost", True)
            back.update()
            front = tk.Toplevel(back)
            front.overrideredirect(True)
            front.geometry("64x64+56+56")
            front.configure(bg="#fa16cf")
            front.attributes("-topmost", True)
            front.attributes("-alpha", 0.94)
            front.update()
            # App's Map hook excludes new private toplevels. The synthetic
            # positive control must be visible before testing its exclusion.
            if not set_affinity(back, False) or not set_affinity(front, False):
                self.verified = False
                return False
            flush_compositor()
            # Establish a visible positive control first.
            before = self.capture((72, 72, 88, 88)).convert("RGB").getpixel((8, 8))
            accepted = set_affinity(front, True)
            flush_compositor()
            after = self.capture((72, 72, 88, 88)).convert("RGB").getpixel((8, 8))
            self.verified = bool(accepted and before[0] > 180 and before[2] > 150 and
                                 abs(after[0] - 22) < 15 and abs(after[1] - 179) < 15 and
                                 abs(after[2] - 91) < 15)
            return self.verified
        except Exception:
            self.verified = False
            return False
        finally:
            if front is not None:
                front.destroy()
            back.destroy()

    def take(self, settings, region=None, window=None, active=None):
        if settings.get("vision_mode", "off") == "off":
            raise RuntimeError("Vision is off")
        current = active or (lambda: True)
        if self.closed or not current():
            raise Cancelled("Capture cancelled")
        target = settings.get("vision_target", "region")
        if target == "window":
            return capture_window(window, current)
        if target == "region":
            if region is None or len(region) != 4 or region[2] <= region[0] or region[3] <= region[1]:
                raise RuntimeError("Select a screen region first")
        elif target in ("screen", "desktop"):
            region = None  # explicit primary/all-display selection only
        else:
            raise RuntimeError("Unknown capture target")
        done, result = threading.Event(), {}
        def restore():
            for surface, state in self._restore:
                try:
                    if surface.winfo_exists():
                        surface.deiconify() if state == "normal" else surface.iconify()
                except Exception:
                    pass
            self._restore = []
            self._busy = False
        def finish():
            try:
                if self.closed or not current() or done.is_set():
                    raise Cancelled("Capture cancelled")
                flush_compositor()
                result["image"] = self.capture(region, all_screens=True) if target == "desktop" else self.capture(region)
            except Exception as exc:
                result["error"] = exc
            finally:
                restore()
                done.set()
        def begin():
            if self._busy:
                result["error"] = RuntimeError("Another capture is in progress")
                done.set()
                return
            if self.closed or not current() or done.is_set():
                result["error"] = Cancelled("Capture cancelled")
                done.set()
                return
            self._busy = True
            surfaces = private_surfaces(self.root)
            trusted = self.verified and all(is_excluded(w) for w in surfaces if w.state() == "normal")
            if trusted:
                finish()
            else:
                self._restore = [(w, w.state()) for w in surfaces if w.state() != "withdrawn"]
                # Withdraw children first; restore parents first.
                for surface, _ in reversed(self._restore):
                    surface.withdraw()
                self.root.after(65, finish)
        if not self.dispatcher.post(begin):
            raise Cancelled("Capture dispatcher closed or busy")
        deadline = time.monotonic() + 6
        while not done.wait(0.05):
            if self.closed or not current() or time.monotonic() > deadline:
                done.set()  # queued UI callbacks now cannot capture
                raise Cancelled("Capture cancelled or timed out")
        if "error" in result:
            raise result["error"]
        if "image" not in result:
            raise Cancelled("Capture cancelled")
        return result["image"]

    def close(self):
        self.closed = True
        for surface, _ in self._restore:
            try:
                surface.deiconify()
            except Exception:
                pass
        self._restore = []
