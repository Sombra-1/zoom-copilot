"""Console-free entry point with local-venv selection and visible startup failures."""
import os
from pathlib import Path
import runpy
import subprocess
import sys
import threading

from .diagnostics import record_failure
from .processes import quiet_process_options


def preferred_python(root, current):
    root, current = Path(root), Path(current)
    for name in ("venv", ".venv"):
        executable = root / name / ("Scripts/pythonw.exe" if os.name == "nt" else "bin/python")
        if executable.is_file():
            return executable.absolute()
    if os.name == "nt" and current.with_name("pythonw.exe").is_file():
        return current.with_name("pythonw.exe").absolute()
    return current.absolute()


def startup_error(log):
    message = "Zoom Copilot could not start. Python 3.11 or newer is required. Run setup.bat to check the installation."
    if log:
        message += f"\n\nLocal diagnostics: {log}"
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, "Zoom Copilot", 0x10 | 0x10000 | 0x40000)
    else:
        from tkinter import messagebox
        messagebox.showerror("Zoom Copilot", message)


def main(root=None):
    root = Path(root) if root else Path(__file__).resolve().parents[1]
    try:
        if sys.version_info < (3, 11):
            raise RuntimeError("Python 3.11 or newer is required")
        executable = preferred_python(root, sys.executable)
        if executable != Path(sys.executable).absolute():
            subprocess.Popen([str(executable), "-B", str(root / "launch.pyw")], cwd=str(root),
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, **quiet_process_options())
            return 0
        for name, mode in (("stdin", "r"), ("stdout", "w"), ("stderr", "w")):
            if getattr(sys, name) is None:
                setattr(sys, name, open(os.devnull, mode, encoding="utf-8"))
        threading.excepthook = lambda args: record_failure((args.exc_type, args.exc_value, args.exc_traceback), "worker")
        runpy.run_path(str(root / "zoom_copilot.py"), run_name="__main__")
        return 0
    except Exception:
        startup_error(record_failure(sys.exc_info(), "startup"))
        return 1
