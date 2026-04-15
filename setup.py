#!/usr/bin/env python3
"""
Zoom Co-Pilot — Setup Checker
Copyright (C) 2026 Sombra-1 (https://github.com/Sombra-1)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

---
Run this first. It checks everything and fixes what's missing automatically.
"""

import sys
import os
import subprocess
import threading
import tkinter as tk
from tkinter import scrolledtext

# ── Theme (matches main app) ──────────────────────────────────────────────────
C = {
    "bg":      "#0a0a0a",
    "panel":   "#111111",
    "border":  "#1e1e1e",
    "accent":  "#00e5ff",
    "success": "#00ff88",
    "error":   "#ff4444",
    "warn":    "#ffaa00",
    "fg":      "#dddddd",
    "fg2":     "#555555",
}
MONO  = ("Consolas", 10)
MONO9 = ("Consolas", 9)
MONO8 = ("Consolas", 8)
BIG   = ("Consolas", 13, "bold")

# ── Helpers ───────────────────────────────────────────────────────────────────

def pip_install(package):
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", package],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

def check_package(name):
    try:
        __import__(name)
        return True
    except ImportError:
        return False

def check_vbcable():
    """Return True if VB-Cable (CABLE Output) is detected as an audio device."""
    try:
        import sounddevice as sd
        for d in sd.query_devices():
            name = d["name"].lower()
            # Match "cable output" specifically — avoids false positives from
            # other devices that happen to have "cable" in their name
            if ("cable output" in name or "vb-cable" in name) and d["max_input_channels"] > 0:
                return True
    except Exception:
        pass
    return False

def check_internet():
    """Return True if internet is reachable. Any HTTP response counts — even 403/404."""
    import urllib.request, urllib.error
    for url in ("https://www.google.com", "https://api.groq.com"):
        try:
            urllib.request.urlopen(url, timeout=5)
            return True
        except urllib.error.HTTPError:
            # Got an HTTP response — server is reachable, internet is working
            return True
        except Exception:
            continue
    return False

def python_ok():
    return sys.version_info >= (3, 8)

def find_main_app():
    """Find zoom_copilot.py next to this script."""
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ["zoom_copilot.py", "copilot_1.py"]:
        p = os.path.join(here, name)
        if os.path.exists(p):
            return p
    return None

# ── GUI ───────────────────────────────────────────────────────────────────────

class SetupApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Zoom Co-Pilot — Setup")
        self.root.configure(bg=C["bg"])
        self.root.geometry("480x700+120+80")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)

        self._rows = {}   # name → (icon_lbl, status_lbl, fix_btn)
        self._build()
        self.root.after(300, self._run_checks)

    def _build(self):
        # Header
        hdr = tk.Frame(self.root, bg=C["bg"])
        hdr.pack(fill="x", padx=24, pady=(20, 0))
        tk.Label(hdr, text="◈", font=("Consolas", 28), bg=C["bg"], fg=C["accent"]).pack(side="left")
        tf = tk.Frame(hdr, bg=C["bg"])
        tf.pack(side="left", padx=10)
        tk.Label(tf, text="ZOOM CO-PILOT SETUP", font=BIG, bg=C["bg"], fg=C["fg"]).pack(anchor="w")
        tk.Label(tf, text="Checking your system…", font=MONO8, bg=C["bg"], fg=C["fg2"]).pack(anchor="w")

        tk.Frame(self.root, bg=C["border"], height=1).pack(fill="x", padx=24, pady=14)

        # Checklist
        checks_frame = tk.Frame(self.root, bg=C["bg"])
        checks_frame.pack(fill="x", padx=24)

        checks = [
            ("python",      "Python 3.8+"),
            ("internet",    "Internet connection"),
            ("sounddevice", "sounddevice  (audio capture)"),
            ("numpy",       "numpy  (audio processing)"),
            ("requests",    "requests  (AI backends)"),
            ("mss",         "mss  (screen watch — optional)"),
            ("PIL",         "Pillow  (screen watch + tray — optional)"),
            ("pystray",     "pystray  (system tray — optional)"),
        ]
        if sys.platform == "win32":
            checks.append(("vbcable", "VB-Cable  (captures Zoom audio)"))

        for key, label in checks:
            row = tk.Frame(checks_frame, bg=C["bg"], pady=6)
            row.pack(fill="x")

            icon = tk.Label(row, text="◌", font=MONO9, bg=C["bg"], fg=C["fg2"], width=2)
            icon.pack(side="left")

            tk.Label(row, text=label, font=MONO9, bg=C["bg"], fg=C["fg"], anchor="w",
                     width=34).pack(side="left")

            status = tk.Label(row, text="checking…", font=MONO8, bg=C["bg"], fg=C["fg2"])
            status.pack(side="left")

            fix_btn = tk.Button(row, text="Fix", font=MONO8,
                bg="#1a1a1a", fg=C["warn"],
                activebackground="#2a2a2a", activeforeground=C["warn"],
                relief="flat", bd=0, cursor="hand2", padx=8, pady=3,
                state="disabled")
            fix_btn.pack(side="right")
            fix_btn.pack_forget()  # hidden until needed

            self._rows[key] = (icon, status, fix_btn)

        tk.Frame(self.root, bg=C["border"], height=1).pack(fill="x", padx=24, pady=14)

        # Log
        tk.Label(self.root, text="LOG", font=MONO8, bg=C["bg"], fg=C["fg2"]).pack(anchor="w", padx=24)
        self.log = scrolledtext.ScrolledText(
            self.root, bg=C["panel"], fg=C["fg2"], font=MONO8,
            relief="flat", bd=0, height=6, state="disabled",
            wrap="word",
        )
        self.log.pack(fill="x", padx=24, pady=(4, 0))

        # Bottom
        tk.Frame(self.root, bg=C["border"], height=1).pack(fill="x", padx=24, pady=12)
        bar = tk.Frame(self.root, bg=C["bg"])
        bar.pack(fill="x", padx=24, pady=(0, 16))

        self._bottom_status = tk.Label(bar, text="", font=MONO8, bg=C["bg"], fg=C["fg2"])
        self._bottom_status.pack(side="left")

        self._launch_btn = tk.Button(bar, text="▶  LAUNCH APP",
            font=MONO9, bg=C["accent"], fg=C["bg"],
            activebackground="#00b8cc", activeforeground=C["bg"],
            relief="flat", bd=0, cursor="hand2", padx=20, pady=8,
            state="disabled", command=self._launch)
        self._launch_btn.pack(side="right")

        self._retry_btn = tk.Button(bar, text="↺  RETRY",
            font=MONO9, bg="#1a1a1a", fg=C["fg2"],
            activebackground="#2a2a2a", activeforeground=C["fg"],
            relief="flat", bd=0, cursor="hand2", padx=12, pady=8,
            state="disabled", command=self._recheck)
        self._retry_btn.pack(side="right", padx=(0, 8))

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log(self, msg):
        def _w():
            self.log.config(state="normal")
            self.log.insert("end", msg + "\n")
            self.log.config(state="disabled")
            self.log.see("end")
        self.root.after(0, _w)

    # ── Row updates ───────────────────────────────────────────────────────────

    def _set_row(self, key, state, msg="", show_fix=False, fix_cmd=None):
        """state: 'ok' | 'fail' | 'warn' | 'working'"""
        icon_lbl, status_lbl, fix_btn = self._rows[key]
        icons   = {"ok": "✓", "fail": "✗", "warn": "⚠", "working": "◌"}
        colors  = {"ok": C["success"], "fail": C["error"], "warn": C["warn"], "working": C["fg2"]}
        def _w():
            icon_lbl.config(text=icons[state], fg=colors[state])
            status_lbl.config(text=msg, fg=colors[state])
            if show_fix and fix_cmd:
                fix_btn.config(state="normal", command=fix_cmd)
                fix_btn.pack(side="right")
            else:
                fix_btn.pack_forget()
        self.root.after(0, _w)

    # ── Checks ────────────────────────────────────────────────────────────────

    def _run_checks(self):
        threading.Thread(target=self._check_all, daemon=True).start()

    def _recheck(self):
        for key in self._rows:
            icon_lbl, status_lbl, fix_btn = self._rows[key]
            self.root.after(0, lambda i=icon_lbl, s=status_lbl, f=fix_btn: (
                i.config(text="◌", fg=C["fg2"]),
                s.config(text="checking…", fg=C["fg2"]),
                f.pack_forget(),
            ))
        self.root.after(0, lambda: self._retry_btn.config(state="disabled"))
        self.root.after(0, lambda: self._launch_btn.config(state="disabled"))
        self.root.after(0, lambda: self._bottom_status.config(text=""))
        threading.Thread(target=self._check_all, daemon=True).start()

    def _check_all(self):
        results = {}

        # Python version
        if python_ok():
            v = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            self._set_row("python", "ok", f"v{v}")
            self._log(f"✓ Python {v}")
            results["python"] = True
        else:
            v = f"{sys.version_info.major}.{sys.version_info.minor}"
            self._set_row("python", "fail", f"v{v} — need 3.8+", show_fix=True,
                          fix_cmd=lambda: self._open_url("https://www.python.org/downloads/"))
            self._log(f"✗ Python {v} is too old. Download 3.8+ from python.org")
            results["python"] = False

        # Internet
        self._set_row("internet", "working", "checking…")
        if check_internet():
            self._set_row("internet", "ok", "connected")
            self._log("✓ Internet — Groq API reachable")
            results["internet"] = True
        else:
            self._set_row("internet", "fail", "no connection")
            self._log("✗ Cannot reach api.groq.com — check your internet connection")
            results["internet"] = False

        # sounddevice
        self._set_row("sounddevice", "working", "checking…")
        if check_package("sounddevice"):
            self._set_row("sounddevice", "ok", "installed")
            self._log("✓ sounddevice")
            results["sounddevice"] = True
        else:
            self._set_row("sounddevice", "working", "installing…")
            self._log("→ Installing sounddevice…")
            try:
                pip_install("sounddevice")
                self._set_row("sounddevice", "ok", "installed")
                self._log("✓ sounddevice installed")
                results["sounddevice"] = True
            except Exception as e:
                self._set_row("sounddevice", "fail", "install failed")
                self._log(f"✗ sounddevice install failed: {e}")
                results["sounddevice"] = False

        # numpy
        self._set_row("numpy", "working", "checking…")
        if check_package("numpy"):
            self._set_row("numpy", "ok", "installed")
            self._log("✓ numpy")
            results["numpy"] = True
        else:
            self._set_row("numpy", "working", "installing…")
            self._log("→ Installing numpy…")
            try:
                pip_install("numpy")
                self._set_row("numpy", "ok", "installed")
                self._log("✓ numpy installed")
                results["numpy"] = True
            except Exception as e:
                self._set_row("numpy", "fail", "install failed")
                self._log(f"✗ numpy install failed: {e}")
                results["numpy"] = False

        # requests
        self._set_row("requests", "working", "checking…")
        if check_package("requests"):
            self._set_row("requests", "ok", "installed")
            self._log("✓ requests")
            results["requests"] = True
        else:
            self._set_row("requests", "working", "installing…")
            self._log("→ Installing requests…")
            try:
                pip_install("requests")
                self._set_row("requests", "ok", "installed")
                self._log("✓ requests installed")
                results["requests"] = True
            except Exception as e:
                self._set_row("requests", "fail", "install failed")
                self._log(f"✗ requests install failed: {e}")
                results["requests"] = False

        # mss (optional — screen watch)
        self._set_row("mss", "working", "checking…")
        if check_package("mss"):
            self._set_row("mss", "ok", "installed")
            self._log("✓ mss")
            results["mss"] = True
        else:
            self._set_row("mss", "working", "installing…")
            self._log("→ Installing mss (optional)…")
            try:
                pip_install("mss")
                self._set_row("mss", "ok", "installed")
                self._log("✓ mss installed")
                results["mss"] = True
            except Exception as e:
                self._set_row("mss", "warn", "optional — not installed")
                self._log(f"⚠ mss not installed (screen watch unavailable): {e}")
                results["mss"] = None  # None = optional miss, not a blocker

        # Pillow (optional — screen watch + tray)
        self._set_row("PIL", "working", "checking…")
        if check_package("PIL"):
            self._set_row("PIL", "ok", "installed")
            self._log("✓ Pillow")
            results["PIL"] = True
        else:
            self._set_row("PIL", "working", "installing…")
            self._log("→ Installing Pillow (optional)…")
            try:
                pip_install("Pillow")
                self._set_row("PIL", "ok", "installed")
                self._log("✓ Pillow installed")
                results["PIL"] = True
            except Exception as e:
                self._set_row("PIL", "warn", "optional — not installed")
                self._log(f"⚠ Pillow not installed (screen watch/tray unavailable): {e}")
                results["PIL"] = None

        # pystray (optional — system tray)
        self._set_row("pystray", "working", "checking…")
        if check_package("pystray"):
            self._set_row("pystray", "ok", "installed")
            self._log("✓ pystray")
            results["pystray"] = True
        else:
            self._set_row("pystray", "working", "installing…")
            self._log("→ Installing pystray (optional)…")
            try:
                pip_install("pystray")
                self._set_row("pystray", "ok", "installed")
                self._log("✓ pystray installed")
                results["pystray"] = True
            except Exception as e:
                self._set_row("pystray", "warn", "optional — not installed")
                self._log(f"⚠ pystray not installed (system tray unavailable): {e}")
                results["pystray"] = None

        # VB-Cable (Windows only)
        if sys.platform == "win32":
            self._set_row("vbcable", "working", "checking…")
            if check_vbcable():
                self._set_row("vbcable", "ok", "detected")
                self._log("✓ VB-Cable detected")
                results["vbcable"] = True
            else:
                self._set_row("vbcable", "fail",
                    "not found — download and install",
                    show_fix=True,
                    fix_cmd=lambda: self._open_url("https://vb-audio.com/Cable/"))
                self._log("✗ VB-Cable not found. Click Fix to download it (free).")
                self._log("  After install: set Zoom speaker → CABLE Input")
                results["vbcable"] = False

        self._finish(results)

    def _finish(self, results):
        # Optional packages (mss, PIL, pystray) use None to signal "optional miss"
        # VB-Cable failure is also a warning, not a hard blocker
        optional_keys = {"vbcable", "mss", "PIL", "pystray"}
        blockers = {k: v for k, v in results.items() if k not in optional_keys and not v}
        vbcable_missing = sys.platform == "win32" and not results.get("vbcable", True)

        if not blockers:
            if vbcable_missing:
                msg = "⚠ Almost ready — install VB-Cable to capture Zoom audio"
                col = C["warn"]
            else:
                msg = "✓ All checks passed — ready to launch!"
                col = C["success"]
            self.root.after(0, lambda: self._bottom_status.config(text=msg, fg=col))
            self.root.after(0, lambda: self._launch_btn.config(state="normal"))
            self._log(msg)
        else:
            msg = f"✗ {len(blockers)} issue(s) need fixing before launch"
            self.root.after(0, lambda: self._bottom_status.config(text=msg, fg=C["error"]))
            self._log(msg)

        self.root.after(0, lambda: self._retry_btn.config(state="normal"))

    # ── Actions ───────────────────────────────────────────────────────────────

    def _open_url(self, url):
        import webbrowser
        webbrowser.open(url)

    def _launch(self):
        app = find_main_app()
        if not app:
            self._log("✗ Could not find zoom_copilot.py next to this script.")
            self.root.after(0, lambda: self._bottom_status.config(
                text="✗ zoom_copilot.py not found", fg=C["error"]))
            return
        self._log(f"→ Launching {os.path.basename(app)}…")
        subprocess.Popen([sys.executable, app])
        self.root.after(800, self.root.destroy)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    SetupApp().run()
