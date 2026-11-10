"""Application identity and icons, resolved relative to the source distribution."""
import ctypes
import math
from pathlib import Path
import sys
import tkinter as tk

ASSETS = Path(__file__).resolve().parents[1] / "assets"
APP_ID = "Sombra1.ZoomCopilot.Preview"


def set_process_identity():
    if sys.platform == "win32":
        try:
            shell = ctypes.WinDLL("shell32", use_last_error=True)
            shell.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
            shell.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
            return shell.SetCurrentProcessExplicitAppUserModelID(APP_ID) == 0
        except OSError:
            return False
    return False


def apply_window_icon(root):
    try:
        if sys.platform == "win32" and (ASSETS / "app.ico").is_file():
            root.iconbitmap(default=str(ASSETS / "app.ico"))
            root.iconbitmap(str(ASSETS / "app.ico"))
        elif (ASSETS / "logo.png").is_file():
            root._brand_icon = tk.PhotoImage(master=root, file=str(ASSETS / "logo.png"))
            root.iconphoto(True, root._brand_icon)
    except (OSError, tk.TclError):
        pass


def logo_label(parent, size=26):
    try:
        import customtkinter as ctk
        from PIL import Image
        with Image.open(ASSETS / "logo.png") as source:
            logo = source.convert("RGBA")
        picture = ctk.CTkImage(light_image=logo, dark_image=logo, size=(size, size))
        return ctk.CTkLabel(parent, text="", image=picture, width=size, height=size)
    except (ImportError, OSError):
        try:
            background = parent.cget("bg")
        except (ValueError, tk.TclError):
            background = "#101114"
        getter = "_get_window_scaling" if isinstance(parent, (tk.Tk, tk.Toplevel)) else "_get_widget_scaling"
        scale = getattr(parent, getter, lambda: 1.0)()
        pixels = max(1, round(size * scale))
        try:
            # Tk supports PNG itself. Keep the logo and its pixel budget when
            # optional Pillow is missing; point-sized fallback text grew at 96 DPI.
            source = tk.PhotoImage(master=parent, file=str(ASSETS / "logo.png"))
            picture = source.subsample(max(1, math.ceil(source.width() / pixels)))
            label = tk.Label(parent, image=picture, bg=background, bd=0, padx=0, pady=0,
                             width=pixels, height=pixels)
            label._brand_image = picture
            return label
        except (OSError, tk.TclError):
            return tk.Label(parent, text="◈", font=("Segoe UI", -max(1, round(pixels * .7))),
                            bg=background, fg="#9baeff", bd=0, padx=0, pady=0)


def tray_icon():
    try:
        from PIL import Image
        with Image.open(ASSETS / "logo.png") as source:
            return source.convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
    except (ImportError, OSError):
        return None


def signal_label(parent):
    """A static 3D illustration with a native PNG fallback."""
    path = ASSETS / "signal-depth.png"
    try:
        import customtkinter as ctk
        from PIL import Image
        with Image.open(path) as source:
            art = source.convert("RGBA")
        picture = ctk.CTkImage(light_image=art, dark_image=art, size=(210, 108))
        return ctk.CTkLabel(parent, text="", image=picture, width=210, height=108)
    except (ImportError, OSError):
        try:
            picture = tk.PhotoImage(master=parent, file=str(path)).subsample(2, 2)
            label = tk.Label(parent, image=picture, bg=parent.cget("fg_color"), bd=0, highlightthickness=0)
            label._signal_image = picture
            return label
        except (OSError, tk.TclError):
            return None
