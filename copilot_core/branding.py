"""Application identity and icons, resolved relative to the source distribution."""
import ctypes
from pathlib import Path
import sys
import tkinter as tk

ASSETS = Path(__file__).resolve().parents[1] / "assets"
APP_ID = "Sombra1.ZoomCopilot.Community"


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
        return tk.Label(parent, text="◈", font=("Segoe UI", size), bg=background, fg="#9baeff")


def tray_icon():
    try:
        from PIL import Image
        with Image.open(ASSETS / "logo.png") as source:
            return source.convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
    except (ImportError, OSError):
        return None
