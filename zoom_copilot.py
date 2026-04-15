#!/usr/bin/env python3
"""
Zoom Co-Pilot — Real-time AI assistant for Zoom, Teams, and Google Meet
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
Single-file edition. No config editing needed — just run and fill in the GUI.

Usage:
    python zoom_copilot.py

Requirements:
    pip install sounddevice numpy requests
    A free Groq API key from console.groq.com
"""

import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog
import threading
import queue
import json
import os
import sys
import time
import webbrowser
try:
    import requests
except ImportError:
    requests = None
try:
    import pystray
    from PIL import Image as _PILImage
    _TRAY_AVAILABLE = True
except ImportError:
    _TRAY_AVAILABLE = False

# PIL is needed for screen capture resizing (separate from pystray)
try:
    from PIL import Image as _PIL_Image_SC, ImageGrab as _PIL_ImageGrab
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

try:
    import mss as _mss
    _MSS_AVAILABLE = True
except ImportError:
    _MSS_AVAILABLE = False

# ── Paths ─────────────────────────────────────────────────────────────────────
SETTINGS_FILE = os.path.join(os.path.dirname(__file__), ".copilot_settings.json")

# ── State ─────────────────────────────────────────────────────────────────────
audio_queue          = queue.Queue()
conversation_history = []
_history_lock        = threading.Lock()    # guards conversation_history
_listen_event        = threading.Event()   # replaces bool flag — thread-safe
stream               = None

# ── Session stats (thread-safe via atomic int ops on GIL + _stats_lock) ──────
_stats_lock = threading.Lock()
session_stats = {"transcriptions": 0, "ai_calls": 0, "errors": 0, "start_time": None}

def _stats_inc(key):
    with _stats_lock:
        session_stats[key] = session_stats.get(key, 0) + 1

def _stats_reset():
    with _stats_lock:
        session_stats.update({"transcriptions": 0, "ai_calls": 0, "errors": 0, "start_time": time.time()})

# ── Screen watch state ────────────────────────────────────────────────────────
_screen_watch_event = threading.Event()
_screen_region      = {"coords": None}  # {"coords": (left,top,right,bottom)} or None

# ── Colors / Fonts ────────────────────────────────────────────────────────────
C = {
    "bg":        "#0b0b0f",   # deep near-black with subtle blue tint
    "panel":     "#111118",   # slightly lighter panel
    "panel2":    "#16161f",   # card/input background
    "border":    "#1e1e30",   # visible but subtle border
    "border2":   "#2a2a40",   # slightly brighter border for hover
    "accent":    "#00d4ff",   # vibrant cyan
    "accent2":   "#0088bb",   # deeper cyan for buttons
    "accent3":   "#7c3aed",   # purple for variety (AI messages)
    "them":      "#94a3b8",   # cool slate-blue for THEM speech
    "ai":        "#00d4ff",   # cyan for AI replies
    "error":     "#ff4466",   # vivid red-pink
    "success":   "#00e87a",   # vibrant green
    "warn":      "#ffb300",   # amber
    "fg":        "#e2e8f0",   # warm-white primary text
    "fg2":       "#475569",   # muted secondary text
    "btn_hover": "#0d2d3d",
    "input_bg":  "#0d0d16",
    "input_fg":  "#cbd5e1",
}

_f = "Segoe UI" if sys.platform == "win32" else "JetBrains Mono"
MONO  = (_f, 12)
MONO9 = (_f, 11)
MONO8 = (_f, 10)
MONO7 = (_f, 9)
BIG   = (_f, 17, "bold")
TITLE = (_f, 13, "bold")

PLACEHOLDER = "Ask the AI or type a message…"

SYSTEM_PROMPT = (
    "You are a real-time AI co-pilot listening to a live call (Zoom/Teams/Meet). "
    "Transcribed speech from the call arrives labelled [TRANSCRIPT]. "
    "The user's own typed questions arrive labelled [USER]. "
    "YOUR JOB: help the user understand or respond to what was actually said in the call. "
    "STRICT RULES — no exceptions: "
    "1. ONLY use information from [TRANSCRIPT] messages. Never invent, assume, or add anything not said. "
    "2. If no [TRANSCRIPT] has arrived yet, reply only: 'I don\'t hear anything yet.' "
    "3. When a [TRANSCRIPT] arrives, give a SHORT useful summary or insight (1-3 sentences max). "
    "   Focus on: what was said, any key claim or opinion, and if helpful — a suggested reply for the user. "
    "4. When [USER] asks a question, answer it strictly based on the transcripts already received. "
    "5. Never roleplay, never speak as a call participant, never speculate beyond the transcript."
)

INTERVIEW_SYSTEM_PROMPT = """\
You are a real-time interview co-pilot. The interviewer's speech arrives as [TRANSCRIPT].
The candidate's own typed notes arrive as [USER].

CANDIDATE BACKGROUND:
{background}

ROLE / COMPANY:
{role}

YOUR JOB — for every [TRANSCRIPT]:
1. Decide what type of question/statement it is.
2. Suggest exactly what the candidate should say — concise, confident, tailored to their background.
3. Use this format every time:

💡 SAY: <2-4 sentence suggested answer, written in first person as if the candidate is speaking>

• <key point or fact from their background to emphasise>
• <second key point>
• <optional: follow-up question the candidate could ask back>

QUESTION TYPE RULES:
- Behavioral ("Tell me about a time…"): structure as Situation → Action → Result (STAR).
  Keep each part to one sentence.
- Technical: give the correct short answer, then relate it to a project from their background.
- Motivation ("Why this role?"): tie their background directly to this specific role/company.
- Salary/comp: suggest they ask what the band is before giving a number.
- "Any questions for us?": suggest 1-2 smart questions based on the role.
- Small talk / opener: keep it warm and brief — 1-2 sentences.
- If the transcript is not a question (small statement, filler), reply: "—  waiting for next question."

STRICT RULES:
- Never mention you are an AI.
- Keep the total reply under 100 words so it fits on screen quickly.
- Always use the candidate's actual skills/projects above — never invent experience.
- If background is empty, give generic but strong interview answers.
"""

def build_system_prompt(s):
    """Return the right system prompt based on current mode."""
    if s.get("interview_mode"):
        bg   = s.get("interview_background", "").strip() or "Not provided."
        role = s.get("interview_role", "").strip()       or "Not provided."
        return INTERVIEW_SYSTEM_PROMPT.format(background=bg, role=role)
    return SYSTEM_PROMPT


SCREEN_PROMPT = (
    "You are a real-time AI screen watcher during a live meeting. "
    "You receive periodic screenshots of the user's screen. "
    "YOUR JOB: extract and summarize anything useful that appears on screen — slides, documents, "
    "whiteboards, code, charts, agendas, action items, names, URLs, or key numbers. "
    "RULES: "
    "1. Be concise — 1-4 bullet points max. "
    "2. Flag anything actionable or time-sensitive (deadlines, open questions, decisions). "
    "3. If nothing new or significant is visible, reply: 'Screen unchanged — no new content.' "
    "4. Never describe UI chrome (taskbar, browser tabs) unless the content itself is notable. "
    "5. If the screen shows code, quote the key function/line. "
    "6. If the screen shows a URL, quote it exactly."
)


def _hover_btn(btn, hover_bg, hover_fg=None):
    """Add hover effect to a button."""
    orig_bg = btn.cget("bg")
    orig_fg = btn.cget("fg")
    btn.bind("<Enter>", lambda e: btn.config(bg=hover_bg, fg=hover_fg or orig_fg))
    btn.bind("<Leave>", lambda e: btn.config(bg=orig_bg, fg=orig_fg))

# ── Settings persistence ───────────────────────────────────────────────────────

def load_settings():
    defaults = {
        "backend":       "builtin",
        "ollama_host":   "http://localhost:11434",
        "ollama_model":  "llama3.1:8b",
        "anthropic_key": "",
        "claude_model":  "claude-sonnet-4-6",
        "groq_key":      "",
        "groq_model":    "llama-3.1-8b-instant",
        "whisper_model":       "whisper-large-v3-turbo",
        "transcription":       "groq",   # "groq" or "local"
        "local_whisper_model": "base",   # tiny/base/small/medium/large-v2
        "language":            "en",
        "device_name":         "CABLE Output" if sys.platform == "win32" else "zoom_capture.monitor",
        "chunk_seconds":       8,
        "opacity":             0.94,
        "custom_keywords":       "",     # comma-separated user-defined trigger words
        "screen_interval":       10,    # seconds between screen captures when watching
        "interview_mode":        False, # when True: answer-suggestion mode instead of summary mode
        "interview_background":  "",    # candidate resume / skills / experience
        "interview_role":        "",    # role title + company + job description snippet
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE) as f:
                saved = json.load(f)
            defaults.update(saved)
        except Exception:
            pass
    return defaults


def save_settings(s):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(s, f, indent=2)
    # Restrict file permissions so other users can't read API keys (no-op on Windows)
    if sys.platform != "win32":
        os.chmod(SETTINGS_FILE, 0o600)


# ── Ollama auto-install helpers ───────────────────────────────────────────────

OLLAMA_BUILTIN_HOST  = "http://localhost:11434"
OLLAMA_BUILTIN_MODEL = "llama3.2:1b"

def ollama_is_running():
    try:
        import urllib.request
        urllib.request.urlopen(OLLAMA_BUILTIN_HOST, timeout=2)
        return True
    except Exception:
        return False

def ollama_model_exists(model):
    try:
        import urllib.request, json as _json
        req = urllib.request.urlopen(f"{OLLAMA_BUILTIN_HOST}/api/tags", timeout=5)
        data = _json.loads(req.read())
        return any(m["name"].startswith(model.split(":")[0]) for m in data.get("models", []))
    except Exception:
        return False

def _ollama_exe():
    """Return the ollama executable path, checking the Windows install location if not in PATH."""
    import shutil
    if shutil.which("ollama"):
        return "ollama"
    if sys.platform == "win32":
        candidate = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")
        if os.path.exists(candidate):
            return candidate
    return "ollama"  # will raise FileNotFoundError with a clear message


def ollama_install_and_start(progress_cb):
    """Install Ollama if needed and start the server. progress_cb(msg) for UI updates."""
    import subprocess, urllib.request, tempfile

    if not ollama_is_running():
        progress_cb("Checking Ollama install...")
        if sys.platform == "win32":
            # Download and run the Windows installer
            installer = os.path.join(tempfile.gettempdir(), "OllamaSetup.exe")
            progress_cb("Downloading Ollama installer...")
            urllib.request.urlretrieve(
                "https://ollama.com/download/OllamaSetup.exe", installer)
            progress_cb("Running installer (approve the UAC prompt)...")
            subprocess.run([installer], check=True)
        else:
            progress_cb("Installing Ollama — enter your password in the terminal...")
            # Open a new terminal window so the user can type their sudo password
            term_cmd = None
            for term in [["gnome-terminal", "--", "bash", "-c"],
                         ["xterm", "-e", "bash -c"],
                         ["konsole", "-e", "bash", "-c"],
                         ["xfce4-terminal", "-e", "bash -c"]]:
                if subprocess.run(["which", term[0]], capture_output=True).returncode == 0:
                    term_cmd = term
                    break

            script = "curl -fsSL https://ollama.com/install.sh | sh; echo; echo 'Press Enter to close...'; read"
            if term_cmd:
                proc = subprocess.Popen(term_cmd + [script])
                proc.wait()
            else:
                # Fallback: try with pkexec (graphical sudo)
                subprocess.run(
                    ["pkexec", "bash", "-c", "curl -fsSL https://ollama.com/install.sh | sh"],
                    check=True)

        # Start the server
        progress_cb("Starting Ollama server...")
        subprocess.Popen([_ollama_exe(), "serve"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Wait up to 15 s for it to come up
        for _ in range(15):
            time.sleep(1)
            if ollama_is_running():
                break
        else:
            raise RuntimeError("Ollama server did not start in time.")

    if not ollama_model_exists(OLLAMA_BUILTIN_MODEL):
        progress_cb(f"Downloading model {OLLAMA_BUILTIN_MODEL} (~800 MB)...")
        subprocess.run([_ollama_exe(), "pull", OLLAMA_BUILTIN_MODEL], check=True)

    progress_cb("Ready.")


# ── Screen capture ────────────────────────────────────────────────────────────

def screen_capture_available():
    return _MSS_AVAILABLE or _PIL_AVAILABLE


def capture_screen(region=None):
    """Capture the screen (or a region) and return a PIL Image.
    region: (left, top, right, bottom) in screen pixels, or None for primary monitor.
    Prefers mss (faster, cross-platform); falls back to PIL ImageGrab."""
    if _MSS_AVAILABLE:
        import mss
        with mss.mss() as sct:
            if region:
                left, top, right, bottom = region
                mon = {"left": left, "top": top, "width": right - left, "height": bottom - top}
            else:
                mon = sct.monitors[1]  # primary monitor
            sct_img = sct.grab(mon)
            # mss returns BGRA; convert to RGB PIL Image
            from PIL import Image as _I
            return _I.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
    elif _PIL_AVAILABLE:
        bbox = region  # PIL ImageGrab accepts (left,top,right,bottom) or None
        return _PIL_ImageGrab.grab(bbox=bbox)
    else:
        raise RuntimeError(
            "Screen capture requires 'mss' or 'Pillow'.\n"
            "Install with:  pip install mss Pillow"
        )


def image_to_base64_jpeg(img, max_width=1280):
    """Resize if needed and return base64-encoded JPEG string."""
    import io, base64
    if img.width > max_width:
        ratio = max_width / img.width
        from PIL import Image as _I
        img = img.resize((max_width, int(img.height * ratio)), _I.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=72)
    return base64.b64encode(buf.getvalue()).decode()


_VISION_BACKENDS = {"claude", "ollama"}  # backends that support image input

def backend_supports_vision(s):
    return s.get("backend") in _VISION_BACKENDS


def ask_ai_vision(image_b64, extra_context, s):
    """Send a screenshot to a vision-capable AI backend and return the reply.
    image_b64: base64 JPEG string.
    extra_context: optional recent transcript snippet for grounding."""
    backend = s["backend"]

    if not backend_supports_vision(s):
        raise RuntimeError(
            f"Backend '{backend}' does not support vision.\n"
            "Switch to Claude or Ollama (with a vision model like llava) in settings."
        )

    user_content_text = SCREEN_PROMPT
    if extra_context:
        user_content_text += f"\n\nRecent transcript context: {extra_context}"

    if backend == "claude":
        if requests is None:
            raise RuntimeError("'requests' package not installed.")
        msg_content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": image_b64,
                },
            },
            {"type": "text", "text": "Analyze this meeting screen and give me the key insights."},
        ]
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": s["anthropic_key"],
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": s["claude_model"],
                "max_tokens": 400,
                "system": user_content_text,
                "messages": [{"role": "user", "content": msg_content}],
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip()

    elif backend == "ollama":
        if requests is None:
            raise RuntimeError("'requests' package not installed.")
        # Ollama vision API: images field on the user message
        r = requests.post(
            f"{s['ollama_host']}/api/chat",
            json={
                "model": s["ollama_model"],
                "messages": [
                    {"role": "system", "content": user_content_text},
                    {
                        "role": "user",
                        "content": "Analyze this meeting screen and give me the key insights.",
                        "images": [image_b64],
                    },
                ],
                "stream": False,
            },
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["message"]["content"].strip()

    raise RuntimeError(f"Vision not implemented for backend: {backend}")


def screen_watch_loop(s, gui):
    """Periodically capture the screen and send to vision AI."""
    interval = max(3, int(s.get("screen_interval", 10)))
    _prev_b64 = [None]

    while _screen_watch_event.is_set():
        # Wait the full interval, but check every second so we stop promptly
        for _ in range(interval):
            if not _screen_watch_event.is_set():
                return
            time.sleep(1)

        if not _screen_watch_event.is_set():
            return

        gui.set_status("Watching screen...", "#c084fc")
        try:
            coords = _screen_region["coords"]
            img = capture_screen(region=coords)
            b64 = image_to_base64_jpeg(img)

            # Skip if image is identical to previous capture (unchanged screen)
            if b64 == _prev_b64[0]:
                gui.set_status("Listening...", C["accent"])
                continue
            _prev_b64[0] = b64

            # Grab a short transcript snippet for grounding
            with _history_lock:
                recent = [
                    m["content"].replace("[TRANSCRIPT] ", "")
                    for m in conversation_history[-4:]
                    if m["role"] == "user" and "[TRANSCRIPT]" in m["content"]
                ]
            context = " | ".join(recent[-2:]) if recent else ""

            _stats_inc("ai_calls")
            reply = ask_ai_vision(b64, context, s)

            with _history_lock:
                conversation_history.append({
                    "role": "assistant",
                    "content": f"[SCREEN] {reply}",
                })
            gui.append_message("🖥  SCREEN", reply, "ai")

        except Exception as e:
            _stats_inc("errors")
            gui.append_message("ERROR", f"Screen watch: {e}", "error")

        gui.set_status("Listening...", C["accent"])
        gui.update_stats()


# ── AI backends ───────────────────────────────────────────────────────────────

def ask_ai(messages, s):
    backend = s["backend"]
    sys_prompt = build_system_prompt(s)
    # Interview mode needs slightly more tokens for the structured answer format
    max_tok = 400 if s.get("interview_mode") else 300

    if backend not in ("demo", "builtin", "ollama", "claude", "groq"):
        raise ValueError(f"Unknown backend: {backend}")

    if backend not in ("demo", "builtin") and requests is None:
        raise RuntimeError("'requests' package not installed. Run: pip install requests")

    if backend == "builtin":
        # Route through local Ollama using the built-in model
        import urllib.request, json as _json
        payload = _json.dumps({
            "model": OLLAMA_BUILTIN_MODEL,
            "messages": [{"role": "system", "content": sys_prompt}] + messages,
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            f"{OLLAMA_BUILTIN_HOST}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            return _json.loads(resp.read())["message"]["content"].strip()

    if backend == "ollama":
        r = requests.post(f"{s['ollama_host']}/api/chat", json={
            "model": s["ollama_model"],
            "messages": [{"role": "system", "content": sys_prompt}] + messages,
            "stream": False,
        }, timeout=60)
        r.raise_for_status()
        return r.json()["message"]["content"].strip()

    elif backend == "claude":
        r = requests.post("https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": s["anthropic_key"],
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": s["claude_model"],
                "max_tokens": max_tok,
                "system": sys_prompt,
                "messages": messages,
            }, timeout=20)
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip()

    elif backend == "groq":
        last_err = None
        for attempt in range(3):
            try:
                r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {s['groq_key']}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": s["groq_model"],
                        "messages": [{"role": "system", "content": sys_prompt}] + messages,
                        "max_tokens": max_tok,
                    }, timeout=20)
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"].strip()
            except Exception as e:
                last_err = e
                # Don't retry client errors (bad key, quota exceeded, etc.)
                resp = getattr(e, "response", None)
                if resp is not None and 400 <= resp.status_code < 500:
                    raise
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        raise last_err

    elif backend == "demo":
        import random, time
        time.sleep(0.6)  # fake thinking delay
        last = messages[-1]["content"] if messages else ""
        responses = [
            "This is Demo Mode — the UI is working perfectly. In a real call, I'd answer what they just said.",
            "Demo response: I can see the transcript came through. Everything is connected correctly.",
            "That's a great question. In live mode I'd give you a real answer using the AI backend you configure.",
            "Demo Mode active. Transcript received. When you switch to Ollama or Groq, real AI replies appear here.",
            f"Got your message: '{last[:60]}...' — In production I'd analyze this and give a proper response.",
        ]
        return random.choice(responses)



# ── Audio ─────────────────────────────────────────────────────────────────────

def list_linux_sources():
    """Return list of PulseAudio/PipeWire source names via pactl."""
    import subprocess
    try:
        result = subprocess.run(
            ["pactl", "list", "sources", "short"],
            capture_output=True, text=True, timeout=4
        )
        names = []
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                names.append(parts[1])
        return names
    except Exception:
        return []


def list_windows_devices():
    """Return list of (name, kind_label) for all input-capable devices on Windows.
    kind_label is one of: 'VB-Cable', 'Stereo Mix', 'Loopback', 'Microphone'."""
    try:
        import sounddevice as sd
        results = []
        for d in sd.query_devices():
            if d["max_input_channels"] < 1:
                continue
            name = d["name"]
            low  = name.lower()
            if "cable output" in low or "vb-cable" in low:
                label = "VB-Cable  ✓ best"
            elif "stereo mix" in low or "what u hear" in low or "wave out mix" in low:
                label = "Stereo Mix  (speaker loopback)"
            elif "loopback" in low:
                label = "Loopback"
            elif any(k in low for k in ("microphone", "mic", "input", "headset", "webcam")):
                label = "Microphone"
            else:
                label = "Input device"
            results.append((name, label))
        return results
    except Exception:
        return []


def find_best_capture_device():
    """Auto-detect the best available audio capture device.
    Priority: VB-Cable → Stereo Mix → any loopback → default system input → first input.
    Returns (device_name, method_label) or (None, None) if nothing found."""
    try:
        import sounddevice as sd
        devices = sd.query_devices()

        # 1. VB-Cable — cleanest: captures exactly what goes to the meeting speaker
        for d in devices:
            n = d["name"].lower()
            if ("cable output" in n or "vb-cable" in n) and d["max_input_channels"] > 0:
                return d["name"], "VB-Cable"

        # 2. Stereo Mix / What U Hear — Windows built-in speaker loopback
        #    (must be enabled in Windows Sound → Recording → Show disabled devices)
        for d in devices:
            n = d["name"].lower()
            if d["max_input_channels"] > 0 and any(
                k in n for k in ("stereo mix", "what u hear", "wave out mix", "sum")
            ):
                return d["name"], "Stereo Mix"

        # 3. Any device with "loopback" in its name
        for d in devices:
            if d["max_input_channels"] > 0 and "loopback" in d["name"].lower():
                return d["name"], "Loopback"

        # 4. Default system input (usually the microphone)
        try:
            default = sd.query_devices(kind="input")
            if default and default.get("max_input_channels", 0) > 0:
                return default["name"], "default microphone"
        except Exception:
            pass

        # 5. First available input device
        for d in devices:
            if d["max_input_channels"] > 0:
                return d["name"], "input device"

    except Exception:
        pass
    return None, None


def find_device(name):
    import sounddevice as sd
    # Direct match — works on Windows (WASAPI) and ALSA
    for i, d in enumerate(sd.query_devices()):
        if name.lower() in d["name"].lower() and d["max_input_channels"] > 0:
            return i
    # Linux/PipeWire fallback: PortAudio can't see PulseAudio sources by name,
    # so set the source as PulseAudio default and use the PipeWire bridge device.
    if sys.platform != "win32":
        import subprocess
        try:
            result = subprocess.run(
                ["pactl", "set-default-source", name],
                capture_output=True, timeout=3
            )
            if result.returncode == 0:
                for i, d in enumerate(sd.query_devices()):
                    if "pipewire" in d["name"].lower() and d["max_input_channels"] > 0:
                        return i
        except Exception:
            pass
    return None


def audio_callback(indata, frames, time_info, status):
    audio_queue.put(indata.copy())


def _numpy_to_wav_bytes(audio_np):
    """Convert float32 numpy array (16 kHz mono) to in-memory WAV bytes."""
    import io, wave
    import numpy as np
    buf = io.BytesIO()
    pcm = (np.clip(audio_np, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


WHISPER_MODELS = [
    "whisper-large-v3-turbo",      # fast, great quality — default
    "whisper-large-v3",            # highest accuracy, ~2× slower
    "distil-whisper-large-v3-en",  # English only, fastest
]

GROQ_AI_MODELS = [
    "llama-3.1-8b-instant",     # fastest — default
    "llama-3.3-70b-versatile",  # best quality
    "llama-3.1-70b-versatile",  # great quality
    "gemma2-9b-it",             # Google Gemma, fast
    "mixtral-8x7b-32768",       # long context
]


def transcribe_groq(audio_np, key, language="en", model="whisper-large-v3-turbo"):
    """Send audio to Groq's free Whisper API and return the transcript.
    Retries up to 2 times on transient network/server errors."""
    import urllib.request, urllib.error, json as _json
    wav = _numpy_to_wav_bytes(audio_np)
    boundary = "GCPBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
        f"Content-Type: audio/wav\r\n\r\n"
    ).encode() + wav + (
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="model"\r\n\r\n{model}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="language"\r\n\r\n{language}\r\n'
        f"--{boundary}--\r\n"
    ).encode()

    last_err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                data=body,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return _json.loads(resp.read())["text"].strip()
        except urllib.error.HTTPError as e:
            # 4xx = client errors (bad key, quota) — don't retry
            if 400 <= e.code < 500:
                raise
            last_err = e
        except Exception as e:
            last_err = e
        if attempt < 2:
            time.sleep(1.5 * (attempt + 1))
    raise last_err


LOCAL_WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v2"]
# Size guide: tiny=~40MB, base=~150MB, small=~500MB, medium=~1.5GB, large-v2=~3GB

_local_whisper_model_cache = {}   # model_name → loaded model instance

def transcribe_local(audio_np, model_name="base", language="en"):
    """Transcribe using faster-whisper running locally — no internet needed."""
    from faster_whisper import WhisperModel
    import numpy as np

    if model_name not in _local_whisper_model_cache:
        _local_whisper_model_cache[model_name] = WhisperModel(
            model_name, device="cpu", compute_type="int8"
        )
    model = _local_whisper_model_cache[model_name]
    audio_np = audio_np.astype(np.float32)
    lang = language if language and language != "auto" else None
    segments, _ = model.transcribe(audio_np, language=lang, beam_size=5)
    return " ".join(seg.text for seg in segments).strip()


def faster_whisper_installed():
    try:
        import faster_whisper  # noqa
        return True
    except ImportError:
        return False


def install_faster_whisper(progress_cb):
    """Install faster-whisper via pip."""
    import subprocess
    progress_cb("Installing faster-whisper...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "faster-whisper", "-q"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-300:] if result.stderr else "pip failed")
    progress_cb("Installed. First use will download the model.")


def _get_transcription_key(s):
    return s.get("groq_key", "").strip()


def transcribe_loop(s, gui):
    import numpy as np
    buffer = []
    chunk_samples = int(16000 * s["chunk_seconds"])

    while _listen_event.is_set():
        try:
            chunk = audio_queue.get(timeout=1)
            buffer.append(chunk)
            if sum(len(c) for c in buffer) >= chunk_samples:
                audio_np = np.concatenate(buffer).flatten().astype(np.float32)
                buffer = []
                threading.Thread(
                    target=process_audio,
                    args=(audio_np, s, gui),
                    daemon=True,
                ).start()
        except queue.Empty:
            continue


def _should_respond(text, history, custom_keywords="", interview_mode=False):
    """Return True if this transcript chunk warrants an AI response."""
    # Interview mode: respond to everything — every word from the interviewer matters
    if interview_mode:
        return True

    t = text.lower().strip()

    # Always respond to direct questions
    if "?" in text:
        return True

    # Always respond if the user hasn't heard anything yet (first transcript)
    if not any(m["role"] == "user" for m in history):
        return True

    # Respond to action/decision words — moments that matter in a meeting
    triggers = [
        "what do you think", "your opinion", "recommend", "suggestion",
        "should we", "can you", "could you", "would you", "do you",
        "explain", "how do", "what is", "what are", "why is", "why are",
        "problem", "issue", "error", "bug", "fail", "broke", "crash",
        "price", "cost", "budget", "expensive", "cheap", "worth",
        "deadline", "urgent", "asap", "immediately",
        "agree", "disagree", "wrong", "correct", "exactly",
    ]
    if any(kw in t for kw in triggers):
        return True

    # User-defined custom trigger keywords
    if custom_keywords:
        custom = [kw.strip().lower() for kw in custom_keywords.split(",") if kw.strip()]
        if any(kw in t for kw in custom):
            return True

    # Respond every 5th transcript even if nothing special — keeps context fresh
    transcript_count = sum(
        1 for m in history if m["role"] == "user" and "[TRANSCRIPT]" in m["content"]
    )
    if transcript_count > 0 and transcript_count % 5 == 0:
        return True

    return False


def _is_silence(audio_np, rms_threshold=0.008, min_duration_ms=200, samplerate=16000):
    """Return True if the audio is effectively silent.
    Uses RMS (root mean square) which is more accurate than simple mean.
    Also skips chunks that are too short to be meaningful speech."""
    import numpy as np
    min_samples = int(samplerate * min_duration_ms / 1000)
    if len(audio_np) < min_samples:
        return True
    rms = float(np.sqrt(np.mean(audio_np.astype(np.float32) ** 2)))
    return rms < rms_threshold


def process_audio(audio_np, s, gui):
    import numpy as np
    if _is_silence(audio_np):
        return

    use_local = s.get("transcription", "groq") == "local"

    if use_local:
        if not faster_whisper_installed():
            gui.append_message("ERROR",
                "faster-whisper is not installed.\n"
                "Go to Settings → section 03 → click 'Install faster-whisper'.", "error")
            gui.after(0, gui._stop)
            return
    else:
        key = _get_transcription_key(s)
        if not key:
            gui.append_message("ERROR",
                "No Groq API key set.\n"
                "Go to Settings → section 03 and add your Groq key, or switch to Local transcription.",
                "error")
            gui.after(0, gui._stop)
            return

    gui.set_status("Transcribing...", C["warn"])
    try:
        if use_local:
            text = transcribe_local(audio_np,
                                    s.get("local_whisper_model", "base"),
                                    s.get("language", "en"))
        else:
            text = transcribe_groq(audio_np, key,
                                   s.get("language", "en"),
                                   s.get("whisper_model", "whisper-large-v3-turbo"))
    except Exception as e:
        gui.append_message("ERROR", f"Transcription failed: {e}", "error")
        gui.set_status("Listening...", C["accent"])
        return

    if not text or len(text) < 4:
        gui.set_status("Listening...", C["accent"])
        return

    _stats_inc("transcriptions")
    gui.append_message("🎙  THEM", text, "them")

    # Only call AI when the transcript is worth responding to
    with _history_lock:
        should = _should_respond(
            text, conversation_history,
            s.get("custom_keywords", ""),
            interview_mode=bool(s.get("interview_mode")),
        )
        conversation_history.append({"role": "user", "content": f"[TRANSCRIPT] {text}"})
        history_snapshot = list(conversation_history[-20:])

    if should:
        gui.set_status("AI thinking...", "#aa88ff")
        _stats_inc("ai_calls")
        try:
            reply = ask_ai(history_snapshot, s)
            with _history_lock:
                conversation_history.append({"role": "assistant", "content": reply})
            gui.append_message("🤖  AI", reply, "ai")
        except Exception as e:
            _stats_inc("errors")
            gui.append_message("ERROR", str(e), "error")

    gui.set_status("Listening...", C["accent"])
    gui.update_stats()


# ================================================================================
#  REGION SELECTOR  (drag-to-select screen area for screen watch)
# ================================================================================

class RegionSelector(tk.Toplevel):
    """Fullscreen transparent overlay — click and drag to select a capture region."""

    def __init__(self, master, on_select):
        super().__init__(master)
        self.on_select = on_select  # callback(left, top, right, bottom) or None on cancel
        self._x0 = self._y0 = self._x1 = self._y1 = 0
        self._dragging = False
        self._rect_id = None

        # Cover all monitors by making the window very large
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        self.attributes("-fullscreen", True)
        self.attributes("-alpha", 0.30)
        self.attributes("-topmost", True)
        self.configure(bg="black")
        self.overrideredirect(True)

        self.canvas = tk.Canvas(self, bg="black", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)

        # Instruction label
        self.canvas.create_text(
            sw // 2, 36,
            text="Drag to select region   ·   Esc to cancel   ·   Release to confirm",
            fill="#00d4ff", font=("Arial", 16),
        )

        self.canvas.bind("<ButtonPress-1>",   self._press)
        self.canvas.bind("<B1-Motion>",       self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.bind("<Escape>", lambda _: self._cancel())
        self.focus_set()

    def _press(self, e):
        self._x0, self._y0 = e.x_root, e.y_root
        self._dragging = True
        if self._rect_id:
            self.canvas.delete(self._rect_id)

    def _drag(self, e):
        self._x1, self._y1 = e.x_root, e.y_root
        if self._rect_id:
            self.canvas.delete(self._rect_id)
        # Draw selection rectangle
        self._rect_id = self.canvas.create_rectangle(
            self._x0 - self.winfo_rootx(),
            self._y0 - self.winfo_rooty(),
            self._x1 - self.winfo_rootx(),
            self._y1 - self.winfo_rooty(),
            outline="#00d4ff", width=2, dash=(6, 4),
            fill="#00d4ff",
        )
        self.canvas.itemconfig(self._rect_id, stipple="gray25")

    def _release(self, e):
        self._x1, self._y1 = e.x_root, e.y_root
        left   = min(self._x0, self._x1)
        top    = min(self._y0, self._y1)
        right  = max(self._x0, self._x1)
        bottom = max(self._y0, self._y1)
        self.destroy()
        if right - left > 20 and bottom - top > 20:
            self.on_select(left, top, right, bottom)
        else:
            self.on_select(None, None, None, None)  # too small — treat as cancel

    def _cancel(self):
        self.destroy()
        self.on_select(None, None, None, None)


# ================================================================================
#  SETUP SCREEN
# ================================================================================

class SetupScreen(tk.Frame):

    BACKENDS = ["builtin", "demo", "ollama", "claude", "groq"]

    def __init__(self, master, settings, on_launch):
        super().__init__(master, bg=C["bg"])
        self.pack(fill="both", expand=True)
        self.s = settings
        self.on_launch = on_launch
        self._vars = {}
        self._build()

    def _build(self):
        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=C["bg"])
        hdr.pack(fill="x", padx=24, pady=(20, 0))

        tk.Label(hdr, text="◈", font=(_f, 26, "bold"),
                 bg=C["bg"], fg=C["accent"]).pack(side="left")
        tf = tk.Frame(hdr, bg=C["bg"])
        tf.pack(side="left", padx=12)
        tk.Label(tf, text="ZOOM CO-PILOT", font=BIG,
                 bg=C["bg"], fg=C["fg"]).pack(anchor="w")
        tk.Label(tf, text="real-time AI assistant for your calls",
                 font=MONO8, bg=C["bg"], fg=C["fg2"]).pack(anchor="w")

        # Double-line divider like the overlay
        tk.Frame(self, bg=C["accent"], height=1).pack(fill="x", pady=(14, 0))
        tk.Frame(self, bg=C["border"], height=1).pack(fill="x", pady=(0, 4))

        # Scrollable area
        canvas = tk.Canvas(self, bg=C["bg"], highlightthickness=0, bd=0)
        scroll = tk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True, padx=(24, 0))

        inner = tk.Frame(canvas, bg=C["bg"])
        cwin  = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(cwin, width=e.width))
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        # Mousewheel scrolling — Windows uses <MouseWheel> delta, Linux uses Button-4/5
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _on_scroll_up(event):
            canvas.yview_scroll(-1, "units")

        def _on_scroll_down(event):
            canvas.yview_scroll(1, "units")

        def _bind_wheel(event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
            canvas.bind_all("<Button-4>",   _on_scroll_up)
            canvas.bind_all("<Button-5>",   _on_scroll_down)

        def _unbind_wheel(event):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind("<Enter>", _bind_wheel)
        canvas.bind("<Leave>", _unbind_wheel)

        # Backend
        self._section(inner, "01  AI BACKEND")
        self._vars["backend"] = tk.StringVar(value=self.s["backend"])
        labels = {"builtin": "Built-in AI  (free, no account — installs automatically)",
                  "demo":    "Demo         (no AI — test the UI only)",
                  "ollama":  "Ollama       (free, local — bring your own model)",
                  "claude":  "Claude       (Anthropic API — paid)",
                  "groq":    "Groq         (free cloud, 14k req/day)"}
        bf = tk.Frame(inner, bg=C["bg"])
        bf.pack(fill="x", pady=(0, 16))
        for b in self.BACKENDS:
            tk.Radiobutton(
                bf, text=labels[b],
                variable=self._vars["backend"], value=b,
                font=MONO9, bg=C["bg"], fg=C["fg"],
                activebackground=C["bg"], activeforeground=C["accent"],
                selectcolor=C["panel"], cursor="hand2",
                command=self._refresh,
            ).pack(anchor="w", pady=2)

        # Container for backend-specific panels (keeps pack order stable)
        self._backend_container = tk.Frame(inner, bg=C["bg"])
        self._backend_container.pack(fill="x")

        # Built-in
        self._bif = tk.Frame(self._backend_container, bg=C["bg"])
        self._bif.pack(fill="x")
        self._section(self._bif, "02  BUILT-IN AI  (Ollama + llama3.2:1b)")
        tk.Label(self._bif,
            text="No account or API key needed.\nThe app installs a small local AI model automatically (~800 MB, one-time).",
            font=MONO8, bg=C["bg"], fg=C["fg2"], justify="left").pack(anchor="w", pady=(0, 6))

        bi_row = tk.Frame(self._bif, bg=C["bg"])
        bi_row.pack(fill="x", pady=(0, 4))

        self._bi_status = tk.Label(bi_row, text="", font=MONO8, bg=C["bg"], fg=C["fg2"])
        self._bi_status.pack(side="left")

        self._bi_btn = tk.Button(bi_row, text="⚙  Setup Built-in AI",
            font=MONO9, bg="#141414", fg=C["fg2"],
            activebackground="#1e1e1e", activeforeground=C["fg"],
            relief="flat", bd=0, cursor="hand2", padx=12, pady=6,
            command=self._setup_builtin)
        self._bi_btn.pack(side="right")
        _hover_btn(self._bi_btn, "#1e1e1e", C["fg"])

        self._bi_progress = tk.Label(self._bif, text="", font=MONO8, bg=C["bg"], fg=C["warn"], justify="left")
        self._bi_progress.pack(anchor="w")
        self._check_builtin_status()

        # Demo
        self._df = tk.Frame(self._backend_container, bg=C["bg"])
        self._df.pack(fill="x")
        self._section(self._df, "02  DEMO MODE")
        tk.Label(self._df,
            text="No setup needed. Type anything in the text box below\nand fake AI replies will appear in the overlay.",
            font=MONO8, bg=C["bg"], fg=C["fg2"], justify="left").pack(anchor="w", pady=(0, 4))
        self._note(self._df, "Use this to test the UI, layout, and overlay behaviour\nbefore connecting a real AI backend.")

        # Ollama
        self._of = tk.Frame(self._backend_container, bg=C["bg"])
        self._of.pack(fill="x")
        self._section(self._of, "02  OLLAMA SETTINGS")
        self._field(self._of, "Host",  "ollama_host",  "http://localhost:11434")
        self._field(self._of, "Model", "ollama_model", "llama3.1:8b")
        self._note(self._of, "curl -fsSL https://ollama.com/install.sh | sh\nollama pull llama3.1:8b\nollama serve")

        # Claude
        self._cf = tk.Frame(self._backend_container, bg=C["bg"])
        self._cf.pack(fill="x")
        self._section(self._cf, "02  ANTHROPIC API")
        self._field(self._cf, "API Key", "anthropic_key", "sk-ant-...", secret=True)
        self._field(self._cf, "Model",   "claude_model",  "claude-sonnet-4-6")
        self._note(self._cf, "Get key at: console.anthropic.com")

        # Groq
        self._gf = tk.Frame(self._backend_container, bg=C["bg"])
        self._gf.pack(fill="x")
        self._section(self._gf, "02  GROQ AI MODEL")
        gm_row = tk.Frame(self._gf, bg=C["bg"])
        gm_row.pack(fill="x", pady=4)
        tk.Label(gm_row, text=f"{'Model':<14}", font=MONO9, bg=C["bg"], fg=C["fg2"],
                 width=14, anchor="w").pack(side="left")
        self._vars["groq_model"] = tk.StringVar(value=self.s.get("groq_model", "llama-3.1-8b-instant"))
        gm_menu = tk.OptionMenu(gm_row, self._vars["groq_model"], *GROQ_AI_MODELS)
        gm_menu.config(font=MONO9, bg=C["input_bg"], fg=C["input_fg"],
                       activebackground=C["panel"], activeforeground=C["accent"],
                       relief="flat", bd=0, highlightthickness=1,
                       highlightbackground=C["border"], highlightcolor=C["accent2"],
                       cursor="hand2", padx=8, pady=4)
        gm_menu["menu"].config(font=MONO9, bg=C["panel"], fg=C["fg"],
                               activebackground=C["accent2"], activeforeground="#fff")
        gm_menu.pack(side="left", fill="x", expand=True)
        tk.Label(self._gf,
            text="  instant=fastest  |  70b=best quality  |  gemma/mixtral=alternatives",
            font=MONO8, bg=C["bg"], fg=C["fg2"]).pack(anchor="w", pady=(0, 4))
        self._note(self._gf, "API key is set in section 03 below.")

        tk.Frame(inner, bg=C["border"], height=1).pack(fill="x", pady=14)

        # Section 03 — Transcription
        self._section(inner, "03  TRANSCRIPTION  (how the app hears the call)")

        # Transcription backend radio buttons
        self._vars["transcription"] = tk.StringVar(value=self.s.get("transcription", "groq"))
        tr_options = [
            ("groq",  "Groq Whisper  (cloud, free — requires Groq key + internet)"),
            ("local", "Local Whisper  (offline, no key, no VPN — works anywhere)"),
        ]
        tr_frame = tk.Frame(inner, bg=C["bg"])
        tr_frame.pack(fill="x", pady=(0, 8))
        for val, label in tr_options:
            tk.Radiobutton(tr_frame, text=label,
                variable=self._vars["transcription"], value=val,
                font=MONO9, bg=C["bg"], fg=C["fg"],
                activebackground=C["bg"], activeforeground=C["accent"],
                selectcolor=C["panel"], cursor="hand2",
                command=self._refresh_transcription,
            ).pack(anchor="w", pady=2)

        # ── Groq transcription panel ──────────────────────────────────────────
        self._groq_tr_frame = tk.Frame(inner, bg=C["bg"])
        self._groq_tr_frame.pack(fill="x")

        tk.Label(self._groq_tr_frame,
            text="One Groq key handles transcription + Groq AI responses (same key).",
            font=MONO8, bg=C["bg"], fg=C["fg2"], justify="left").pack(anchor="w", pady=(0, 4))
        self._field(self._groq_tr_frame, "Groq API Key", "groq_key", "gsk_...", secret=True)

        # Clickable signup link
        signup_row = tk.Frame(self._groq_tr_frame, bg=C["bg"])
        signup_row.pack(fill="x", pady=(0, 6))
        tk.Label(signup_row, text="No account? →", font=MONO8, bg=C["bg"], fg=C["fg2"]).pack(side="left")
        link = tk.Label(signup_row,
            text="Create free Groq account (console.groq.com)",
            font=MONO8, bg=C["bg"], fg=C["accent"], cursor="hand2")
        link.pack(side="left", padx=4)
        link.bind("<Button-1>", lambda e: webbrowser.open("https://console.groq.com"))

        # Groq Whisper model dropdown
        wm_row = tk.Frame(self._groq_tr_frame, bg=C["bg"])
        wm_row.pack(fill="x", pady=4)
        tk.Label(wm_row, text=f"{'Whisper Model':<14}", font=MONO9, bg=C["bg"], fg=C["fg2"],
                 width=14, anchor="w").pack(side="left")
        self._vars["whisper_model"] = tk.StringVar(value=self.s.get("whisper_model", "whisper-large-v3-turbo"))
        wm_menu = tk.OptionMenu(wm_row, self._vars["whisper_model"], *WHISPER_MODELS)
        wm_menu.config(font=MONO9, bg=C["input_bg"], fg=C["input_fg"],
                       activebackground=C["panel"], activeforeground=C["accent"],
                       relief="flat", bd=0, highlightthickness=1,
                       highlightbackground=C["border"], highlightcolor=C["accent2"],
                       cursor="hand2", padx=8, pady=4)
        wm_menu["menu"].config(font=MONO9, bg=C["panel"], fg=C["fg"],
                               activebackground=C["accent2"], activeforeground="#fff")
        wm_menu.pack(side="left", fill="x", expand=True)
        tk.Label(self._groq_tr_frame,
            text="  turbo = fast + great quality  |  large-v3 = most accurate  |  distil = English only, fastest",
            font=MONO8, bg=C["bg"], fg=C["fg2"], justify="left").pack(anchor="w", pady=(0, 4))

        # ── Local transcription panel ─────────────────────────────────────────
        self._local_tr_frame = tk.Frame(inner, bg=C["bg"])
        self._local_tr_frame.pack(fill="x")

        tk.Label(self._local_tr_frame,
            text="Runs 100% offline — no API key, no internet, no VPN needed.\n"
                 "First use downloads the model once (~40 MB for 'base').",
            font=MONO8, bg=C["bg"], fg=C["fg2"], justify="left").pack(anchor="w", pady=(0, 6))

        # Local model size dropdown
        lm_row = tk.Frame(self._local_tr_frame, bg=C["bg"])
        lm_row.pack(fill="x", pady=4)
        tk.Label(lm_row, text=f"{'Model size':<14}", font=MONO9, bg=C["bg"], fg=C["fg2"],
                 width=14, anchor="w").pack(side="left")
        self._vars["local_whisper_model"] = tk.StringVar(value=self.s.get("local_whisper_model", "base"))
        lm_menu = tk.OptionMenu(lm_row, self._vars["local_whisper_model"], *LOCAL_WHISPER_MODELS)
        lm_menu.config(font=MONO9, bg=C["input_bg"], fg=C["input_fg"],
                       activebackground=C["panel"], activeforeground=C["accent"],
                       relief="flat", bd=0, highlightthickness=1,
                       highlightbackground=C["border"], highlightcolor=C["accent2"],
                       cursor="hand2", padx=8, pady=4)
        lm_menu["menu"].config(font=MONO9, bg=C["panel"], fg=C["fg"],
                               activebackground=C["accent2"], activeforeground="#fff")
        lm_menu.pack(side="left", fill="x", expand=True)
        tk.Label(self._local_tr_frame,
            text="  tiny=40MB  base=150MB  small=500MB  medium=1.5GB  large-v2=3GB",
            font=MONO8, bg=C["bg"], fg=C["fg2"], justify="left").pack(anchor="w", pady=(0, 6))

        # Install button row
        inst_row = tk.Frame(self._local_tr_frame, bg=C["bg"])
        inst_row.pack(fill="x", pady=(0, 4))
        self._fw_status = tk.Label(inst_row, text="", font=MONO8, bg=C["bg"], fg=C["fg2"])
        self._fw_status.pack(side="left")
        self._fw_btn = tk.Button(inst_row, text="⬇  Install faster-whisper",
            font=MONO9, bg="#141414", fg=C["fg2"],
            activebackground="#1e1e1e", activeforeground=C["fg"],
            relief="flat", bd=0, cursor="hand2", padx=12, pady=6,
            command=self._install_local_whisper)
        self._fw_btn.pack(side="right")
        _hover_btn(self._fw_btn, "#1e1e1e", C["fg"])
        self._check_local_whisper_status()

        # Language (shared by both)
        tk.Frame(inner, bg=C["border"], height=1).pack(fill="x", pady=(8, 4))
        self._field(inner, "Language", "language", "en")
        tk.Label(inner, text="  Language code: en, ar, fr, de, es, tr, zh ...",
            font=MONO8, bg=C["bg"], fg=C["fg2"]).pack(anchor="w", pady=(0, 4))

        # Custom trigger keywords
        tk.Frame(inner, bg=C["border"], height=1).pack(fill="x", pady=(8, 4))
        self._section(inner, "03b  CUSTOM TRIGGER KEYWORDS  (optional)")
        self._field(inner, "Keywords", "custom_keywords", "sprint, deploy, blockers")
        tk.Label(inner,
            text="  Comma-separated. AI responds whenever these words appear in the transcript.\n"
                 "  Add project names, team terms, or anything you want to always catch.",
            font=MONO8, bg=C["bg"], fg=C["fg2"], justify="left").pack(anchor="w", pady=(0, 4))

        self._refresh_transcription()

        tk.Frame(inner, bg=C["border"], height=1).pack(fill="x", pady=14)

        # Audio
        self._section(inner, "04  AUDIO DEVICE")
        if sys.platform == "win32":
            # Device name field + Windows-specific picker and auto-detect
            dev_row = tk.Frame(inner, bg=C["bg"])
            dev_row.pack(fill="x", pady=4)
            tk.Label(dev_row, text=f"{'Device name':<14}", font=MONO9, bg=C["bg"], fg=C["fg2"],
                     width=14, anchor="w").pack(side="left")
            self._vars["device_name"] = tk.StringVar(value=self.s.get("device_name", "CABLE Output"))
            dev_entry = tk.Entry(dev_row, textvariable=self._vars["device_name"], font=MONO9,
                         bg=C["input_bg"], fg=C["input_fg"],
                         insertbackground=C["accent"], relief="flat", bd=0,
                         highlightthickness=1, highlightcolor=C["accent2"],
                         highlightbackground=C["border"])
            dev_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 4))

            self._win_discover_btn = tk.Button(dev_row, text="⟳ Discover",
                font=MONO8, bg="#141414", fg=C["fg2"],
                activebackground="#1e1e1e", activeforeground=C["fg"],
                relief="flat", bd=0, cursor="hand2", padx=10, pady=5,
                command=self._discover_windows_devices)
            self._win_discover_btn.pack(side="left", padx=(0, 4))
            _hover_btn(self._win_discover_btn, "#1e1e1e", C["fg"])

            self._win_auto_btn = tk.Button(dev_row, text="⚡ Auto-detect",
                font=MONO8, bg="#0a1a0a", fg=C["success"],
                activebackground="#0f280f", activeforeground=C["success"],
                relief="flat", bd=0, cursor="hand2", padx=10, pady=5,
                command=self._autodetect_windows_device)
            self._win_auto_btn.pack(side="left")
            _hover_btn(self._win_auto_btn, "#0f280f", C["success"])

            self._win_dev_status = tk.Label(inner, text="", font=MONO8, bg=C["bg"], fg=C["fg2"])
            self._win_dev_status.pack(anchor="w", pady=(2, 0))

            self._note(inner,
                "Option A — VB-Cable (cleanest, captures exactly what Zoom plays):\n"
                "  1. Install from vb-audio.com/Cable  (free)\n"
                "  2. Zoom Settings → Audio → Speaker → CABLE Input\n"
                "  3. Device name: CABLE Output\n"
                "\n"
                "Option B — Stereo Mix (no extra install, built-in Windows loopback):\n"
                "  1. Right-click speaker icon → Sounds → Recording tab\n"
                "  2. Right-click blank area → Show Disabled Devices\n"
                "  3. Right-click 'Stereo Mix' → Enable\n"
                "  4. Click ⚡ Auto-detect above — it will find it automatically\n"
                "\n"
                "Option C — Microphone (captures room audio + speaker bleed):\n"
                "  1. Click ⟳ Discover above and pick your mic from the list\n"
                "  2. Works instantly, no setup needed — quality depends on your mic\n"
                "\n"
                "Click ⚡ Auto-detect to automatically pick the best available option."
            )
        else:
            # Device name field + live discovery button
            dev_row = tk.Frame(inner, bg=C["bg"])
            dev_row.pack(fill="x", pady=4)
            tk.Label(dev_row, text=f"{'Device name':<14}", font=MONO9, bg=C["bg"], fg=C["fg2"],
                     width=14, anchor="w").pack(side="left")
            self._vars["device_name"] = tk.StringVar(value=self.s.get("device_name", "zoom_capture.monitor"))
            dev_entry = tk.Entry(dev_row, textvariable=self._vars["device_name"], font=MONO9,
                         bg=C["input_bg"], fg=C["input_fg"],
                         insertbackground=C["accent"], relief="flat", bd=0,
                         highlightthickness=1, highlightcolor=C["accent2"],
                         highlightbackground=C["border"])
            dev_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 4))

            self._discover_btn = tk.Button(dev_row, text="⟳ Discover",
                font=MONO8, bg="#141414", fg=C["fg2"],
                activebackground="#1e1e1e", activeforeground=C["fg"],
                relief="flat", bd=0, cursor="hand2", padx=10, pady=5,
                command=self._discover_linux_sources)
            self._discover_btn.pack(side="left")
            _hover_btn(self._discover_btn, "#1e1e1e", C["fg"])

            self._note(inner,
                "Linux setup (run once in terminal):\n"
                "  pactl load-module module-null-sink sink_name=zoom_capture sink_properties=device.description=ZoomCapture\n"
                "  pactl load-module module-loopback source=zoom_capture.monitor\n"
                "Then in your meeting app:\n"
                "  Settings -> Audio -> Speaker -> ZoomCapture\n"
                "  Works with: Zoom, Teams, Google Meet, LinkedIn, Discord\n"
                "Click '⟳ Discover' to list all available PulseAudio/PipeWire sources."
            )

        # Mic test widget
        mic_frame = tk.Frame(inner, bg=C["bg"])
        mic_frame.pack(fill="x", pady=(4, 0))

        self._mic_btn = tk.Button(mic_frame, text="🎤 TEST MIC  (3 sec)",
            font=MONO9, bg="#141414", fg=C["fg2"],
            activebackground="#1e1e1e", activeforeground=C["fg"],
            relief="flat", bd=0, cursor="hand2", padx=12, pady=6,
            command=self._test_mic)
        self._mic_btn.pack(side="left")
        _hover_btn(self._mic_btn, "#1e1e1e", C["fg"])

        self._mic_status = tk.Label(mic_frame, text="", font=MONO8, bg=C["bg"], fg=C["fg2"])
        self._mic_status.pack(side="left", padx=10)

        # Canvas volume bar (hidden until test runs)
        self._vol_canvas = tk.Canvas(mic_frame, bg=C["panel2"], width=160, height=12,
                                     highlightthickness=0, bd=0)
        self._vol_bar = self._vol_canvas.create_rectangle(0, 0, 0, 12, fill=C["success"], width=0)

        tk.Frame(inner, bg=C["border"], height=1).pack(fill="x", pady=14)

        # Section 05 — Interview Mode
        self._section(inner, "05  INTERVIEW MODE")

        im_row = tk.Frame(inner, bg=C["bg"])
        im_row.pack(fill="x", pady=(0, 6))
        self._vars["interview_mode"] = tk.BooleanVar(value=bool(self.s.get("interview_mode", False)))
        im_chk = tk.Checkbutton(im_row,
            text="Enable Interview Mode  (AI suggests answers instead of summarising)",
            variable=self._vars["interview_mode"],
            font=MONO9, bg=C["bg"], fg=C["fg"],
            activebackground=C["bg"], activeforeground=C["accent"],
            selectcolor=C["panel"], cursor="hand2",
            command=self._refresh_interview_mode)
        im_chk.pack(anchor="w")

        self._im_frame = tk.Frame(inner, bg=C["bg"])
        self._im_frame.pack(fill="x")

        tk.Label(self._im_frame,
            text="Your background  (paste resume / skills / years of experience — the more detail, the better answers)",
            font=MONO8, bg=C["bg"], fg=C["fg2"], justify="left").pack(anchor="w", pady=(4, 2))
        self._im_bg_text = tk.Text(self._im_frame,
            font=MONO8, bg=C["input_bg"], fg=C["input_fg"],
            insertbackground=C["accent"], relief="flat", bd=0,
            highlightthickness=1, highlightcolor=C["accent2"],
            highlightbackground=C["border"],
            height=5, wrap="word")
        self._im_bg_text.pack(fill="x", pady=(0, 8))
        self._im_bg_text.insert("1.0", self.s.get("interview_background", ""))

        tk.Label(self._im_frame,
            text="Role & company  (job title + company name + 2-3 sentences from the job description)",
            font=MONO8, bg=C["bg"], fg=C["fg2"], justify="left").pack(anchor="w", pady=(0, 2))
        self._im_role_text = tk.Text(self._im_frame,
            font=MONO8, bg=C["input_bg"], fg=C["input_fg"],
            insertbackground=C["accent"], relief="flat", bd=0,
            highlightthickness=1, highlightcolor=C["accent2"],
            highlightbackground=C["border"],
            height=3, wrap="word")
        self._im_role_text.pack(fill="x", pady=(0, 4))
        self._im_role_text.insert("1.0", self.s.get("interview_role", ""))

        self._note(self._im_frame,
            "Audio tip: make sure you are capturing the INTERVIEWER's audio only.\n"
            "  Best: VB-Cable or Stereo Mix — captures speaker output, not your mic.\n"
            "  Do NOT use microphone mode — it would pick up your own answers too.\n"
            "AI will respond to EVERYTHING the interviewer says and suggest what to say.")

        self._refresh_interview_mode()

        tk.Frame(inner, bg=C["border"], height=1).pack(fill="x", pady=14)

        # Section 06 — Screen Watch
        self._section(inner, "06  SCREEN WATCH  (real-time vision AI)")
        cap_avail = screen_capture_available()
        cap_note = (
            "Captures your screen periodically and sends it to a vision AI.\n"
            "Requires: Claude or Ollama with a vision model (e.g. llava).\n"
            "Install capture library: pip install mss Pillow"
            if not cap_avail else
            "Captures your screen periodically and sends it to a vision AI.\n"
            "Requires: Claude or Ollama with a vision model (e.g. llava).\n"
            f"Capture library: {'mss ✓' if _MSS_AVAILABLE else 'Pillow ImageGrab ✓'}"
        )
        tk.Label(inner, text=cap_note, font=MONO8, bg=C["bg"],
                 fg=C["success"] if cap_avail else C["fg2"],
                 justify="left").pack(anchor="w", pady=(0, 6))

        si_row = tk.Frame(inner, bg=C["bg"])
        si_row.pack(fill="x", pady=4)
        tk.Label(si_row, text=f"{'Interval (sec)':<14}", font=MONO9, bg=C["bg"], fg=C["fg2"],
                 width=14, anchor="w").pack(side="left")
        self._vars["screen_interval"] = tk.StringVar(value=str(self.s.get("screen_interval", 10)))
        si_entry = tk.Entry(si_row, textvariable=self._vars["screen_interval"], font=MONO9,
                     bg=C["input_bg"], fg=C["input_fg"],
                     insertbackground=C["accent"], relief="flat", bd=0,
                     highlightthickness=1, highlightcolor=C["accent2"],
                     highlightbackground=C["border"], width=8)
        si_entry.pack(side="left", ipady=6)
        tk.Label(si_row, text="  seconds between captures (min 3)",
                 font=MONO8, bg=C["bg"], fg=C["fg2"]).pack(side="left", padx=6)

        tk.Frame(inner, bg=C["bg"], height=16).pack()

        # Bottom bar — double accent line + action row
        tk.Frame(self, bg=C["accent"], height=1).pack(fill="x")
        tk.Frame(self, bg=C["border"], height=1).pack(fill="x")
        bar = tk.Frame(self, bg=C["bg"], pady=12)
        bar.pack(fill="x", padx=24)

        self._test_btn = tk.Button(bar, text="⚡ TEST CONNECTION", command=self._test,
            font=MONO9, bg=C["panel2"], fg=C["fg2"],
            activebackground=C["border"], activeforeground=C["fg"],
            relief="flat", bd=0, cursor="hand2", padx=14, pady=8)
        self._test_btn.pack(side="left")
        _hover_btn(self._test_btn, C["border"], C["fg"])

        self._status = tk.Label(bar, text="", font=MONO8, bg=C["bg"], fg=C["fg2"])
        self._status.pack(side="left", padx=12)

        launch_btn = tk.Button(bar, text="▶  LAUNCH",
            command=self._launch,
            font=(_f, 12, "bold"),
            bg=C["accent2"], fg="#ffffff",
            activebackground=C["accent"], activeforeground="#000000",
            relief="flat", bd=0, cursor="hand2", padx=28, pady=9)
        launch_btn.pack(side="right")
        _hover_btn(launch_btn, C["accent"], "#000000")

        self._refresh()

    def _section(self, p, text):
        f = tk.Frame(p, bg=C["bg"])
        f.pack(fill="x", pady=(12, 6))
        tk.Label(f, text=text, font=MONO8, bg=C["bg"], fg=C["accent"]).pack(anchor="w")
        tk.Frame(f, bg=C["accent2"], height=1).pack(fill="x", pady=(3, 0))

    def _field(self, p, label, key, placeholder="", secret=False):
        row = tk.Frame(p, bg=C["bg"])
        row.pack(fill="x", pady=4)
        tk.Label(row, text=f"{label:<14}", font=MONO9, bg=C["bg"], fg=C["fg2"],
                 width=14, anchor="w").pack(side="left")
        var = tk.StringVar(value=self.s.get(key, placeholder))
        self._vars[key] = var
        e = tk.Entry(row, textvariable=var, font=MONO9,
                     bg=C["input_bg"], fg=C["input_fg"],
                     insertbackground=C["accent"], relief="flat", bd=0,
                     show="•" if secret else "",
                     highlightthickness=1,
                     highlightcolor=C["accent2"],
                     highlightbackground=C["border"])
        e.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 4))
        if secret:
            shown = [False]
            lbl = tk.Label(row, text=" 👁 ", font=MONO8, bg=C["bg"], fg=C["fg2"], cursor="hand2")
            lbl.pack(side="left")
            def toggle(_=None):
                shown[0] = not shown[0]
                e.config(show="" if shown[0] else "•")
            lbl.bind("<Button-1>", toggle)

    def _note(self, p, text):
        tk.Label(p, text=text, font=MONO8, bg=C["bg"], fg=C["fg2"],
                 justify="left", anchor="w").pack(anchor="w", pady=(0, 8))

    def _check_builtin_status(self):
        def check():
            if ollama_is_running() and ollama_model_exists(OLLAMA_BUILTIN_MODEL):
                self.after(0, lambda: self._bi_status.config(
                    text=f"✓ Ready — {OLLAMA_BUILTIN_MODEL} loaded", fg=C["success"]))
                self.after(0, lambda: self._bi_btn.config(text="✓ Ready", state="disabled", fg=C["success"]))
            elif ollama_is_running():
                self.after(0, lambda: self._bi_status.config(
                    text=f"Ollama running — model not pulled yet", fg=C["warn"]))
            else:
                self.after(0, lambda: self._bi_status.config(
                    text="Not installed", fg=C["fg2"]))
        threading.Thread(target=check, daemon=True).start()

    def _setup_builtin(self):
        self._bi_btn.config(state="disabled")
        self._bi_progress.config(text="Starting...")

        def progress(msg):
            self.after(0, lambda: self._bi_progress.config(text=msg))

        def run():
            try:
                ollama_install_and_start(progress)
                self.after(0, lambda: self._bi_status.config(
                    text=f"✓ Ready — {OLLAMA_BUILTIN_MODEL} loaded", fg=C["success"]))
                self.after(0, lambda: self._bi_btn.config(
                    text="✓ Ready", state="disabled", fg=C["success"]))
                self.after(0, lambda: self._bi_progress.config(text=""))
            except Exception as e:
                self.after(0, lambda: self._bi_progress.config(
                    text=f"✗ {e}", fg=C["error"]))
                self.after(0, lambda: self._bi_btn.config(state="normal"))

        threading.Thread(target=run, daemon=True).start()

    def _discover_windows_devices(self):
        """Popup listing all input-capable audio devices on Windows."""
        devices = list_windows_devices()
        if not devices:
            if hasattr(self, "_win_dev_status"):
                self._win_dev_status.config(
                    text="No input devices found — is sounddevice installed?", fg=C["warn"])
            return

        popup = tk.Toplevel(self, bg=C["bg"])
        popup.title("Select Audio Device")
        popup.geometry("540x360")
        popup.configure(bg=C["bg"])
        popup.grab_set()

        tk.Label(popup,
                 text="All input-capable audio devices on this system:",
                 font=MONO9, bg=C["bg"], fg=C["fg"]).pack(anchor="w", padx=16, pady=(12, 4))
        tk.Label(popup,
                 text="  ✓ best = VB-Cable   |   Stereo Mix = speaker loopback   |   Microphone = room audio",
                 font=MONO8, bg=C["bg"], fg=C["fg2"]).pack(anchor="w", padx=16, pady=(0, 6))

        lb_frame = tk.Frame(popup, bg=C["border"], padx=1, pady=1)
        lb_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        lb = tk.Listbox(lb_frame, font=MONO9, bg=C["panel"], fg=C["fg"],
                        selectbackground=C["accent2"], selectforeground="#fff",
                        relief="flat", bd=0, activestyle="none")
        lb.pack(fill="both", expand=True)

        # Group: preferred devices first, then everything else
        priority_order = ["VB-Cable", "Stereo Mix", "Loopback", "Microphone", "Input device"]
        sorted_devices = sorted(devices, key=lambda x: next(
            (i for i, p in enumerate(priority_order) if p in x[1]), len(priority_order)))

        for name, label in sorted_devices:
            fg = C["success"] if "best" in label else (C["warn"] if "Stereo" in label else C["fg"])
            lb.insert("end", f"  {name}  —  {label}")
            lb.itemconfig("end", fg=fg)

        def _pick():
            sel = lb.curselection()
            if sel:
                name = sorted_devices[sel[0]][0]
                self._vars["device_name"].set(name)
                if hasattr(self, "_win_dev_status"):
                    self._win_dev_status.config(text=f"✓ Set to: {name}", fg=C["success"])
            popup.destroy()

        tk.Button(popup, text="Use selected", command=_pick,
                  font=MONO9, bg=C["accent2"], fg="#fff",
                  activebackground=C["accent"], activeforeground="#000",
                  relief="flat", bd=0, cursor="hand2", padx=16, pady=7
                  ).pack(side="right", padx=16, pady=8)
        tk.Button(popup, text="Cancel", command=popup.destroy,
                  font=MONO9, bg=C["panel2"], fg=C["fg2"],
                  activebackground=C["border"], activeforeground=C["fg"],
                  relief="flat", bd=0, cursor="hand2", padx=14, pady=7
                  ).pack(side="right", padx=4, pady=8)

    def _autodetect_windows_device(self):
        """Auto-pick the best available capture device and populate the field."""
        if hasattr(self, "_win_dev_status"):
            self._win_dev_status.config(text="Scanning…", fg=C["warn"])
        self._win_auto_btn.config(state="disabled")

        def run():
            name, method = find_best_capture_device()
            def _apply():
                self._win_auto_btn.config(state="normal")
                if name:
                    self._vars["device_name"].set(name)
                    tips = {
                        "VB-Cable": "Perfect — captures exactly what Zoom/Teams plays.",
                        "Stereo Mix": "Good — captures all speaker output on this PC.",
                        "Loopback": "Good — loopback device detected.",
                        "default microphone": "Microphone mode — captures room audio. No VB-Cable found.",
                        "input device": "Fallback input — no loopback device found.",
                    }
                    tip = tips.get(method, "")
                    self._win_dev_status.config(
                        text=f"✓ Found: {name}  ({method})  {tip}",
                        fg=C["success"] if "VB-Cable" in method or "Stereo" in method or "Loopback" in method
                           else C["warn"])
                else:
                    self._win_dev_status.config(
                        text="✗ No input devices found — is sounddevice installed?",
                        fg=C["error"])
            self.after(0, _apply)

        threading.Thread(target=run, daemon=True).start()

    def _discover_linux_sources(self):
        """Populate a popup with discovered PulseAudio/PipeWire sources."""
        sources = list_linux_sources()
        if not sources:
            self._mic_status.config(
                text="No sources found — is pactl installed?", fg=C["warn"])
            return

        popup = tk.Toplevel(self, bg=C["bg"])
        popup.title("Select Audio Source")
        popup.geometry("460x300")
        popup.configure(bg=C["bg"])
        popup.grab_set()

        tk.Label(popup, text="Select an audio source:", font=MONO9,
                 bg=C["bg"], fg=C["fg"]).pack(anchor="w", padx=16, pady=(12, 4))

        lb_frame = tk.Frame(popup, bg=C["border"], padx=1, pady=1)
        lb_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        lb = tk.Listbox(lb_frame, font=MONO9, bg=C["panel"], fg=C["fg"],
                        selectbackground=C["accent2"], selectforeground="#fff",
                        relief="flat", bd=0, activestyle="none")
        lb.pack(fill="both", expand=True)
        for s in sources:
            lb.insert("end", s)

        def _pick():
            sel = lb.curselection()
            if sel:
                self._vars["device_name"].set(sources[sel[0]])
            popup.destroy()

        tk.Button(popup, text="Use selected", command=_pick,
                  font=MONO9, bg=C["accent2"], fg="#fff",
                  activebackground=C["accent"], activeforeground="#000",
                  relief="flat", bd=0, cursor="hand2", padx=16, pady=7
                  ).pack(side="right", padx=16, pady=8)
        tk.Button(popup, text="Cancel", command=popup.destroy,
                  font=MONO9, bg=C["panel2"], fg=C["fg2"],
                  activebackground=C["border"], activeforeground=C["fg"],
                  relief="flat", bd=0, cursor="hand2", padx=14, pady=7
                  ).pack(side="right", padx=4, pady=8)

    def _refresh_interview_mode(self):
        on = self._vars["interview_mode"].get()
        if on:
            self._im_frame.pack(fill="x")
        else:
            self._im_frame.pack_forget()

    def _refresh(self):
        b = self._vars["backend"].get()
        for f in (self._bif, self._df, self._of, self._cf, self._gf):
            f.pack_forget()
        {"builtin": self._bif, "demo": self._df, "ollama": self._of,
         "claude": self._cf, "groq": self._gf}[b].pack(in_=self._backend_container, fill="x")

    def _refresh_transcription(self):
        t = self._vars["transcription"].get()
        self._groq_tr_frame.pack_forget()
        self._local_tr_frame.pack_forget()
        if t == "groq":
            self._groq_tr_frame.pack(fill="x")
        else:
            self._local_tr_frame.pack(fill="x")

    def _check_local_whisper_status(self):
        if faster_whisper_installed():
            self._fw_status.config(text="✓ faster-whisper installed", fg=C["success"])
            self._fw_btn.config(text="✓ Installed", state="disabled", fg=C["success"])
        else:
            self._fw_status.config(text="Not installed", fg=C["fg2"])

    def _install_local_whisper(self):
        self._fw_btn.config(state="disabled")
        self._fw_status.config(text="Installing...", fg=C["warn"])

        def run():
            try:
                install_faster_whisper(
                    lambda msg: self.after(0, lambda: self._fw_status.config(text=msg, fg=C["warn"]))
                )
                self.after(0, lambda: self._fw_status.config(
                    text="✓ Installed — model downloads on first use", fg=C["success"]))
                self.after(0, lambda: self._fw_btn.config(
                    text="✓ Installed", state="disabled", fg=C["success"]))
            except Exception as e:
                self.after(0, lambda: self._fw_status.config(text=f"✗ {e}", fg=C["error"]))
                self.after(0, lambda: self._fw_btn.config(state="normal"))

        threading.Thread(target=run, daemon=True).start()

    def _collect(self):
        s = dict(self.s)
        for k, var in self._vars.items():
            val = var.get()
            # BooleanVar.get() returns bool; StringVar.get() returns str
            s[k] = val if isinstance(val, bool) else val.strip()
        try:
            s["chunk_seconds"] = int(s.get("chunk_seconds", 8))
        except (ValueError, TypeError):
            s["chunk_seconds"] = 8
        try:
            s["screen_interval"] = max(3, int(s.get("screen_interval", 10)))
        except (ValueError, TypeError):
            s["screen_interval"] = 10
        # Pull Text widget values (not in _vars)
        if hasattr(self, "_im_bg_text"):
            s["interview_background"] = self._im_bg_text.get("1.0", "end").strip()
        if hasattr(self, "_im_role_text"):
            s["interview_role"] = self._im_role_text.get("1.0", "end").strip()
        return s

    def _validate(self, s):
        b = s["backend"]
        using_local = s.get("transcription", "groq") == "local"
        # Groq key required only when using Groq transcription or Groq AI backend
        if not using_local and b != "demo" and not s.get("groq_key"):
            return "Groq API key is required (section 03). Free at console.groq.com"
        if using_local and b == "groq" and not s.get("groq_key"):
            return "Groq API key is required for the Groq AI backend (section 03)."
        if b == "claude" and not s.get("anthropic_key"):
            return "Anthropic API key is required."
        if using_local and not faster_whisper_installed():
            return "faster-whisper is not installed. Click 'Install faster-whisper' in section 03."
        return None

    def _test_mic(self):
        s = self._collect()
        device_name = s.get("device_name", "").strip()

        try:
            import sounddevice as sd
            import numpy as np
        except ImportError:
            self._mic_status.config(text="✗ sounddevice not installed  →  pip install sounddevice numpy", fg=C["error"])
            return

        dev_idx = find_device(device_name)
        if dev_idx is None:
            hint = "Install VB-Cable and set Zoom speaker to 'CABLE Input'" if sys.platform == "win32" else "Run the pactl setup commands first"
            self._mic_status.config(
                    text=f"✗ Device '{device_name}' not found. {hint}.", fg=C["error"])
            return

        self._mic_btn.config(state="disabled")
        self._mic_status.config(text="Listening...", fg=C["warn"])
        self._vol_canvas.pack(side="left")

        DURATION   = 3      # seconds
        SAMPLERATE = 16000
        CHUNK      = 1024
        peak_seen  = [0.0]

        def run():
            frames_total = int(SAMPLERATE * DURATION / CHUNK)
            try:
                with sd.InputStream(samplerate=SAMPLERATE, channels=1,
                                    device=dev_idx, blocksize=CHUNK) as st:
                    for _ in range(frames_total):
                        data, _ = st.read(CHUNK)
                        level = float(np.abs(data).mean())
                        peak_seen[0] = max(peak_seen[0], level)
                        # update bar on main thread
                        bar_w = min(int(level * 2000), 160)
                        color = C["success"] if level > 0.002 else C["error"]
                        self.after(0, lambda w=bar_w, c=color: (
                            self._vol_canvas.coords(self._vol_bar, 0, 0, w, 14),
                            self._vol_canvas.itemconfig(self._vol_bar, fill=c),
                        ))
            except Exception as e:
                self.after(0, lambda: self._mic_status.config(
                    text=f"✗ Error: {e}", fg=C["error"]))
                self.after(0, lambda: self._mic_btn.config(state="normal"))
                return

            # Final verdict
            if peak_seen[0] > 0.002:
                msg  = f"✓ Audio detected! Peak level: {peak_seen[0]:.4f}"
                col  = C["success"]
            else:
                msg  = "✗ No audio detected — check device or play something in Zoom"
                col  = C["error"]

            self.after(0, lambda: self._mic_status.config(text=msg, fg=col))
            self.after(0, lambda: self._vol_canvas.coords(self._vol_bar, 0, 0, 0, 14))
            self.after(0, lambda: self._mic_btn.config(state="normal"))

        threading.Thread(target=run, daemon=True).start()

    def _test(self):
        s = self._collect()
        if s["backend"] == "demo":
            self._status.config(text="✓ Demo mode — no connection needed, just launch!", fg=C["success"])
            return
        err = self._validate(s)
        if err:
            self._status.config(text=f"⚠ {err}", fg=C["error"])
            return
        self._status.config(text="Testing...", fg=C["warn"])
        self._test_btn.config(state="disabled")

        def run():
            try:
                b = s["backend"]
                if b == "builtin":
                    import urllib.request as _ur, json as _js
                    payload = _js.dumps({
                        "model": OLLAMA_BUILTIN_MODEL,
                        "messages": [{"role": "user", "content": "Reply: OK"}],
                        "stream": False,
                    }).encode()
                    req = _ur.Request(
                        f"{OLLAMA_BUILTIN_HOST}/api/chat",
                        data=payload,
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with _ur.urlopen(req, timeout=30) as resp:
                        reply = _js.loads(resp.read())["message"]["content"].strip()
                elif b == "ollama":
                    requests.get(s["ollama_host"], timeout=5).raise_for_status()
                    r = requests.post(f"{s['ollama_host']}/api/chat", json={
                        "model": s["ollama_model"],
                        "messages": [{"role": "user", "content": "Reply: OK"}],
                        "stream": False}, timeout=30)
                    r.raise_for_status()
                    reply = r.json()["message"]["content"].strip()
                elif b == "claude":
                    r = requests.post("https://api.anthropic.com/v1/messages",
                        headers={"x-api-key": s["anthropic_key"], "anthropic-version": "2023-06-01", "content-type": "application/json"},
                        json={"model": s["claude_model"], "max_tokens": 10, "messages": [{"role": "user", "content": "Reply: OK"}]},
                        timeout=15)
                    r.raise_for_status()
                    reply = r.json()["content"][0]["text"].strip()
                elif b == "groq":
                    r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {s['groq_key']}", "Content-Type": "application/json"},
                        json={"model": s["groq_model"], "messages": [{"role": "user", "content": "Reply: OK"}], "max_tokens": 10},
                        timeout=15)
                    r.raise_for_status()
                    reply = r.json()["choices"][0]["message"]["content"].strip()

                self.after(0, lambda: self._status.config(
                    text=f"✓ Connected! AI says: '{reply[:40]}'", fg=C["success"]))
            except Exception as e:
                self.after(0, lambda: self._status.config(
                    text=f"✗ {str(e)[:55]}", fg=C["error"]))
            finally:
                self.after(0, lambda: self._test_btn.config(state="normal"))

        threading.Thread(target=run, daemon=True).start()

    def _launch(self):
        s = self._collect()
        err = self._validate(s)
        if err:
            messagebox.showerror("Missing settings", err)
            return
        save_settings(s)
        self.on_launch(s)


# ================================================================================
#  OVERLAY SCREEN
# ================================================================================

class OverlayScreen(tk.Frame):

    def __init__(self, master, settings, on_settings, on_toggle_capture=None):
        super().__init__(master, bg=C["bg"])
        self.pack(fill="both", expand=True)
        self.s                 = settings
        self.on_settings       = on_settings
        self.on_toggle_capture = on_toggle_capture
        self._build()

    def _build(self):
        # ── Header bar ────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=C["bg"], pady=10)
        hdr.pack(fill="x", padx=16)

        # Logo + title
        logo_frame = tk.Frame(hdr, bg=C["bg"])
        logo_frame.pack(side="left")
        tk.Label(logo_frame, text="◈", font=(_f, 18, "bold"),
                 bg=C["bg"], fg=C["accent"]).pack(side="left", padx=(0, 6))
        tk.Label(logo_frame, text="ZOOM CO-PILOT", font=TITLE,
                 bg=C["bg"], fg=C["fg"]).pack(side="left")

        # Backend badge
        b = self.s["backend"]
        badge_colors = {
            "builtin": ("#002a00", "#00e87a"),
            "ollama":  ("#002a20", "#00d4aa"),
            "claude":  ("#0a001a", "#a78bfa"),
            "groq":    ("#1a0030", "#c084fc"),
            "demo":    ("#1a1a00", "#fbbf24"),
        }
        bb, bf = badge_colors.get(b, ("#111", "#aaa"))
        badge = tk.Label(hdr, text=f"  {b.upper()}  ", font=MONO7,
                         bg=bb, fg=bf, padx=2, pady=3)
        badge.pack(side="left", padx=8)

        # Interview Mode indicator badge
        if self.s.get("interview_mode"):
            tk.Label(hdr, text="  🎯 INTERVIEW  ", font=MONO7,
                     bg="#1a0a00", fg="#fb923c", padx=2, pady=3).pack(side="left", padx=2)

        # Right-side controls
        settings_btn = tk.Button(hdr, text="⚙", font=(_f, 13),
                  bg=C["bg"], fg=C["fg2"],
                  activebackground=C["panel2"], activeforeground=C["accent"],
                  relief="flat", bd=0, cursor="hand2", padx=6, pady=2)
        settings_btn.config(command=self.on_settings)
        settings_btn.pack(side="right", padx=2)
        _hover_btn(settings_btn, C["panel2"], C["accent"])

        if self.on_toggle_capture and sys.platform == "win32":
            self._capture_btn = tk.Button(
                hdr, text="🔒 Hidden",
                font=MONO8, bg=C["panel2"], fg=C["success"],
                activebackground=C["border"], activeforeground=C["warn"],
                relief="flat", bd=0, cursor="hand2", padx=8, pady=3)
            self._capture_btn.config(
                command=lambda: self.on_toggle_capture(self._capture_btn))
            self._capture_btn.pack(side="right", padx=6)
            _hover_btn(self._capture_btn, C["border"], C["warn"])

        # Animated status dot
        self.status_lbl = tk.Label(hdr, text="⬤  idle", font=MONO8,
                                   bg=C["bg"], fg=C["fg2"])
        self.status_lbl.pack(side="right", padx=10)

        # Accent divider line (gradient-effect via two lines)
        tk.Frame(self, bg=C["accent"], height=1).pack(fill="x")
        tk.Frame(self, bg=C["border"], height=1).pack(fill="x")

        # ── Chat area ─────────────────────────────────────────────────────────
        chat_outer = tk.Frame(self, bg=C["border"], padx=1, pady=1)
        chat_outer.pack(fill="both", expand=True, padx=14, pady=(10, 6))

        self.chat = scrolledtext.ScrolledText(
            chat_outer, bg=C["panel"], fg=C["fg"],
            font=MONO, relief="flat", bd=0,
            wrap="word", state="disabled", cursor="arrow",
            selectbackground="#1a3a50",
            padx=10, pady=8,
        )
        self.chat.pack(fill="both", expand=True)

        self.chat.tag_config("them",     foreground=C["them"])
        self.chat.tag_config("them_lbl", foreground="#334155", font=MONO7)
        self.chat.tag_config("ai",       foreground=C["ai"])
        self.chat.tag_config("ai_lbl",   foreground=C["accent2"], font=MONO7)
        self.chat.tag_config("error",    foreground=C["error"], font=(*MONO8[:1], MONO8[1], "bold"))
        self.chat.tag_config("sys",      foreground="#2a3a4a", font=MONO7)
        self.chat.tag_config("divider",  foreground="#13131e")
        self.chat.tag_config("ts",       foreground="#1e2d3d", font=MONO7)

        # #2 Right-click context menu for copying text
        self._ctx_menu = tk.Menu(self.chat, tearoff=0, bg=C["panel"], fg=C["fg"],
                                 activebackground=C["accent2"], activeforeground="#fff",
                                 font=MONO9)
        self._ctx_menu.add_command(label="Copy selection",
                                   command=lambda: self.master.clipboard_clear() or
                                       self.master.clipboard_append(
                                           self.chat.get("sel.first", "sel.last"))
                                   if self.chat.tag_ranges("sel") else None)
        self._ctx_menu.add_command(label="Copy last AI reply",
                                   command=self._copy_last_ai)
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="Save transcript…", command=self.save_transcript)
        self.chat.bind("<Button-3>", lambda e: self._ctx_menu.tk_popup(e.x_root, e.y_root))

        # ── Controls row ──────────────────────────────────────────────────────
        ctrl = tk.Frame(self, bg=C["bg"], pady=6)
        ctrl.pack(fill="x", padx=14)

        self.toggle_btn = tk.Button(ctrl, text="▶  START LISTENING  (Ctrl+L)",
            font=(_f, 11, "bold"),
            bg="#05282a", fg=C["accent"],
            activebackground="#0a3a3e", activeforeground=C["accent"],
            relief="flat", bd=0, cursor="hand2", padx=18, pady=8,
            command=self.toggle_listening)
        self.toggle_btn.pack(side="left")
        _hover_btn(self.toggle_btn, "#0a3a3e", C["accent"])

        clear_btn = tk.Button(ctrl, text="✕  CLEAR",
                  font=MONO9,
                  bg=C["panel2"], fg=C["fg2"],
                  activebackground=C["border"], activeforeground=C["fg"],
                  relief="flat", bd=0, cursor="hand2", padx=12, pady=8,
                  command=self.clear)
        clear_btn.pack(side="left", padx=8)
        _hover_btn(clear_btn, C["border"], C["fg"])

        # #1 Save button
        save_btn = tk.Button(ctrl, text="⬇ SAVE",
                  font=MONO9, bg=C["panel2"], fg=C["fg2"],
                  activebackground=C["border"], activeforeground=C["fg"],
                  relief="flat", bd=0, cursor="hand2", padx=12, pady=8,
                  command=self.save_transcript)
        save_btn.pack(side="left", padx=(0, 8))
        _hover_btn(save_btn, C["border"], C["fg"])

        # #3 Auto-scroll toggle
        self._autoscroll = [True]
        self._scroll_btn = tk.Button(ctrl, text="⬇ AUTO",
                  font=MONO9, bg=C["panel2"], fg=C["accent"],
                  activebackground=C["border"], activeforeground=C["accent"],
                  relief="flat", bd=0, cursor="hand2", padx=10, pady=8,
                  command=self._toggle_autoscroll)
        self._scroll_btn.pack(side="left")
        _hover_btn(self._scroll_btn, C["border"], C["accent"])

        # Screen watch button + region picker
        sw_frame = tk.Frame(ctrl, bg=C["bg"])
        sw_frame.pack(side="left", padx=(8, 0))

        self._screen_btn = tk.Button(sw_frame, text="👁 WATCH SCREEN",
                  font=MONO9, bg="#0a001a", fg="#c084fc",
                  activebackground="#160028", activeforeground="#c084fc",
                  relief="flat", bd=0, cursor="hand2", padx=12, pady=8,
                  command=self._toggle_screen_watch)
        self._screen_btn.pack(side="left")
        _hover_btn(self._screen_btn, "#160028", "#c084fc")

        self._region_btn = tk.Button(sw_frame, text="📐",
                  font=MONO9, bg=C["panel2"], fg=C["fg2"],
                  activebackground=C["border"], activeforeground=C["fg"],
                  relief="flat", bd=0, cursor="hand2", padx=8, pady=8,
                  command=self._pick_region)
        self._region_btn.pack(side="left", padx=(2, 0))
        _hover_btn(self._region_btn, C["border"], C["fg"])

        self._region_lbl = tk.Label(sw_frame, text="full screen",
                  font=MONO7, bg=C["bg"], fg=C["fg2"])
        self._region_lbl.pack(side="left", padx=4)

        # Opacity slider (right side)
        opacity_frame = tk.Frame(ctrl, bg=C["bg"])
        opacity_frame.pack(side="right")
        tk.Label(opacity_frame, text="OPACITY", font=MONO7,
                 bg=C["bg"], fg="#222233").pack(side="left", padx=(0, 4))
        self.opacity_var = tk.DoubleVar(value=self.s.get("opacity", 0.94))

        def _on_opacity(v):
            self.master.attributes("-alpha", float(v))
            self.s["opacity"] = float(v)
            save_settings(self.s)

        tk.Scale(opacity_frame, from_=0.3, to=1.0, resolution=0.02,
                 orient="horizontal", variable=self.opacity_var,
                 command=_on_opacity,
                 bg=C["bg"], fg=C["border2"], troughcolor=C["panel2"],
                 highlightthickness=0, bd=0, length=90, showvalue=False
                 ).pack(side="left")

        self.master.attributes("-alpha", self.s.get("opacity", 0.94))

        # ── Input row (multi-line — supports code paste) ──────────────────────
        inp_outer = tk.Frame(self, bg=C["border"], padx=1, pady=1)
        inp_outer.pack(fill="x", padx=14, pady=(0, 4))

        inp_frame = tk.Frame(inp_outer, bg=C["input_bg"])
        inp_frame.pack(fill="x")

        # Right-side button column
        btn_col = tk.Frame(inp_frame, bg=C["input_bg"])
        btn_col.pack(side="right", fill="y")

        send_btn = tk.Button(btn_col, text="SEND\n↵",
                  font=(_f, 9, "bold"),
                  bg=C["accent2"], fg="#ffffff",
                  activebackground=C["accent"], activeforeground="#000000",
                  relief="flat", bd=0, cursor="hand2", padx=14, pady=6)
        send_btn.pack(side="top", fill="x")
        _hover_btn(send_btn, C["accent"], "#000000")

        paste_btn = tk.Button(btn_col, text="📋",
                  font=MONO8,
                  bg=C["panel2"], fg=C["fg2"],
                  activebackground=C["border"], activeforeground=C["fg"],
                  relief="flat", bd=0, cursor="hand2", padx=14, pady=4)
        paste_btn.pack(side="top", fill="x")
        _hover_btn(paste_btn, C["border"], C["fg"])

        clr_btn = tk.Button(btn_col, text="✕",
                  font=MONO8,
                  bg=C["panel2"], fg=C["fg2"],
                  activebackground=C["border"], activeforeground=C["error"],
                  relief="flat", bd=0, cursor="hand2", padx=14, pady=4)
        clr_btn.pack(side="top", fill="x")
        _hover_btn(clr_btn, C["border"], C["error"])

        # Multi-line text widget — supports code paste
        self._manual_entry = tk.Text(
            inp_frame,
            font=MONO9, bg=C["input_bg"], fg=C["fg2"],
            insertbackground=C["accent"], relief="flat", bd=0,
            wrap="none",          # horizontal scroll for wide code
            height=3,             # starts at 3 lines, resizes
            undo=True,
        )
        self._manual_entry.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=4)
        self._manual_entry.insert("1.0", PLACEHOLDER)
        self._input_has_placeholder = True

        # Horizontal scrollbar for wide code lines
        inp_hscroll = tk.Scrollbar(inp_frame, orient="horizontal",
                                   command=self._manual_entry.xview,
                                   bg=C["panel2"], troughcolor=C["panel"])
        self._manual_entry.config(xscrollcommand=inp_hscroll.set)
        # Only show scrollbar when needed — pack after text widget
        inp_hscroll.pack(side="bottom", fill="x")

        def _clear_placeholder(e):
            if self._input_has_placeholder:
                self._manual_entry.delete("1.0", "end")
                self._manual_entry.config(fg=C["input_fg"])
                self._input_has_placeholder = False

        def _restore_placeholder(e):
            if not self._manual_entry.get("1.0", "end").strip():
                self._manual_entry.delete("1.0", "end")
                self._manual_entry.insert("1.0", PLACEHOLDER)
                self._manual_entry.config(fg=C["fg2"])
                self._input_has_placeholder = True

        def _on_paste(_=None):
            """Read clipboard and insert at cursor, clearing placeholder first."""
            _clear_placeholder(None)
            try:
                text = self.master.clipboard_get()
                self._manual_entry.insert(tk.INSERT, text)
            except Exception:
                pass
            # Auto-expand height for code (max 10 lines)
            lines = int(self._manual_entry.index("end-1c").split(".")[0])
            self._manual_entry.config(height=min(max(3, lines), 10))
            return "break"

        def _on_key_release(e):
            # Auto-expand height as user types (max 10 lines)
            lines = int(self._manual_entry.index("end-1c").split(".")[0])
            self._manual_entry.config(height=min(max(3, lines), 10))

        self._manual_entry.bind("<FocusIn>",    _clear_placeholder)
        self._manual_entry.bind("<FocusOut>",   _restore_placeholder)
        self._manual_entry.bind("<KeyRelease>", _on_key_release)
        # Enter = send, Shift+Enter = newline (natural for code)
        self._manual_entry.bind("<Return>",       lambda e: (self._send_manual(), "break")[1])
        self._manual_entry.bind("<Shift-Return>", lambda e: None)  # allow newline
        # Ctrl+V paste handler
        self._manual_entry.bind("<Control-v>", _on_paste)
        self._manual_entry.bind("<Control-V>", _on_paste)

        send_btn.config(command=self._send_manual)
        paste_btn.config(command=_on_paste)
        clr_btn.config(command=lambda: (
            self._manual_entry.delete("1.0", "end"),
            _restore_placeholder(None),
        ))

        # Keyboard hint
        tk.Label(self, text="Enter = send  ·  Shift+↵ = newline  ·  Ctrl+V = paste code",
                 font=MONO7, bg=C["bg"], fg="#1e2d3d", anchor="e"
                 ).pack(fill="x", padx=16, pady=(0, 2))

        # #10 Session stats footer
        stats_frame = tk.Frame(self, bg=C["bg"])
        stats_frame.pack(fill="x", padx=14, pady=(0, 8))
        self._stats_lbl = tk.Label(stats_frame, text="",
                                   font=MONO7, bg=C["bg"], fg=C["fg2"], anchor="w")
        self._stats_lbl.pack(side="left")

        # #4 Ctrl+L shortcut
        self.master.bind("<Control-l>", lambda e: self.toggle_listening())

    def append_message(self, label, text, kind="them"):
        def _w():
            ts = time.strftime("%H:%M:%S")
            self.chat.config(state="normal")
            if kind == "them":
                lbl_tag, txt_tag = "them_lbl", "them"
            elif kind == "ai":
                lbl_tag, txt_tag = "ai_lbl", "ai"
            else:
                lbl_tag, txt_tag = "sys", "error"
            self.chat.insert("end", "\n")
            self.chat.insert("end", f" {label}  ", lbl_tag)
            self.chat.insert("end", f"{ts}\n", "ts")
            self.chat.insert("end", f" {text}\n", txt_tag)
            self.chat.insert("end", "  " + "─" * 52 + "\n", "divider")
            self.chat.config(state="disabled")
            if self._autoscroll[0]:   # #3 only scroll if auto-scroll is on
                self.chat.see("end")
        self.after(0, _w)

    def _toggle_autoscroll(self):
        self._autoscroll[0] = not self._autoscroll[0]
        on = self._autoscroll[0]
        self._scroll_btn.config(
            text="⬇ AUTO" if on else "⏸ SCROLL",
            fg=C["accent"] if on else C["warn"],
        )
        if on:
            self.chat.see("end")

    def save_transcript(self):
        """#1 Export chat contents to a timestamped .txt file."""
        content = self.chat.get("1.0", "end").strip()
        if not content:
            messagebox.showinfo("Nothing to save", "The transcript is empty.")
            return
        default_name = f"transcript_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=default_name,
            title="Save transcript",
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

    def _copy_last_ai(self):
        """#2 Copy the last AI reply to the clipboard."""
        with _history_lock:
            history_copy = list(conversation_history)
        for msg in reversed(history_copy):
            if msg["role"] == "assistant":
                self.master.clipboard_clear()
                self.master.clipboard_append(msg["content"])
                self.set_status("Copied!", C["success"])
                self.after(1800, lambda: self.set_status(
                    "Listening..." if _listen_event.is_set() else "idle",
                    C["accent"] if _listen_event.is_set() else C["fg2"]))
                return
        self.set_status("No AI reply yet", C["warn"])
        self.after(1800, lambda: self.set_status(
            "Listening..." if _listen_event.is_set() else "idle",
            C["accent"] if _listen_event.is_set() else C["fg2"]))

    def update_stats(self):
        """#10 Refresh the stats footer label (called from background threads via after)."""
        def _apply():
            with _stats_lock:
                tr  = session_stats.get("transcriptions", 0)
                ai  = session_stats.get("ai_calls", 0)
                err = session_stats.get("errors", 0)
                t0  = session_stats.get("start_time")
            elapsed = ""
            if t0:
                secs = int(time.time() - t0)
                elapsed = f"  {secs//60}m {secs%60:02d}s"
            self._stats_lbl.config(
                text=f"transcriptions: {tr}   AI calls: {ai}   errors: {err}{elapsed}")
        self.after(0, _apply)

    def clear(self):
        self.chat.config(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.config(state="disabled")
        with _history_lock:
            conversation_history.clear()
        _stats_reset()
        self.update_stats()

    def set_status(self, text, color=None):
        icons = {
            "Listening...":  "⬤",
            "Transcribing...": "◎",
            "AI thinking...":  "◈",
            "idle":            "⬤",
            "Stopped":         "◼",
            "Loading...":      "◌",
        }
        # Fully dispatch to main thread — after_cancel is not thread-safe
        def _apply():
            self._stop_pulse()
            self.status_lbl.config(text=f"{icons.get(text,'⬤')}  {text}", fg=color or C["fg2"])
            if text == "Listening...":
                self.after(100, self._pulse)
        self.after(0, _apply)

    def _pulse(self):
        """Animate the status dot when listening."""
        if not _listen_event.is_set():
            return
        try:
            cur = self.status_lbl.cget("fg")
            next_col = C["accent"] if cur != C["accent"] else "#005566"
            self.status_lbl.config(fg=next_col)
            self._pulse_id = self.after(600, self._pulse)
        except Exception:
            pass

    def _stop_pulse(self):
        if hasattr(self, "_pulse_id"):
            try:
                self.after_cancel(self._pulse_id)
            except Exception:
                pass
            self._pulse_id = None

    def _send_manual(self, _=None):
        text = self._manual_entry.get("1.0", "end").strip()
        if not text or getattr(self, "_input_has_placeholder", False):
            return
        self._manual_entry.delete("1.0", "end")
        self._input_has_placeholder = True
        self._manual_entry.insert("1.0", PLACEHOLDER)
        self._manual_entry.config(fg=C["fg2"], height=3)
        self.append_message("🎙  YOU (typed)", text, "them")
        self.set_status("AI thinking...", "#aa88ff")

        def run():
            with _history_lock:
                conversation_history.append({"role": "user", "content": f"[USER] {text}"})
                history_snapshot = list(conversation_history[-20:])
            _stats_inc("ai_calls")
            try:
                reply = ask_ai(history_snapshot, self.s)
                with _history_lock:
                    conversation_history.append({"role": "assistant", "content": reply})
                self.append_message("🤖  AI", reply, "ai")
            except Exception as e:
                _stats_inc("errors")
                self.append_message("ERROR", str(e), "error")
            live = _listen_event.is_set()
            self.set_status("Listening..." if live else "idle", C["accent"] if live else C["fg2"])
            self.update_stats()

        threading.Thread(target=run, daemon=True).start()

    # ── Screen watch ──────────────────────────────────────────────────────────

    def _pick_region(self):
        """Open the drag-select overlay so the user can choose a capture area."""
        # Temporarily hide the app window so it doesn't appear in the selection
        self.master.withdraw()
        self.master.after(150, self._open_selector)  # small delay for withdraw to take effect

    def _open_selector(self):
        def _on_select(left, top, right, bottom):
            self.master.deiconify()
            if left is None:
                self._region_lbl.config(text="full screen")
                _screen_region["coords"] = None
            else:
                _screen_region["coords"] = (left, top, right, bottom)
                w, h = right - left, bottom - top
                self._region_lbl.config(
                    text=f"{w}×{h} @ ({left},{top})", fg=C["accent"])
        RegionSelector(self.master, _on_select)

    def _toggle_screen_watch(self):
        if _screen_watch_event.is_set():
            self._stop_screen_watch()
        else:
            self._start_screen_watch()

    def _start_screen_watch(self):
        if not screen_capture_available():
            self.append_message("ERROR",
                "Screen capture not available.\nRun: pip install mss Pillow", "error")
            return
        if not backend_supports_vision(self.s):
            self.append_message("ERROR",
                f"Backend '{self.s['backend']}' does not support vision.\n"
                "Switch to Claude or Ollama (with a vision model like llava) in settings.",
                "error")
            return

        _screen_watch_event.set()
        threading.Thread(target=screen_watch_loop, args=(self.s, self), daemon=True).start()

        self._screen_btn.config(
            text="■ STOP WATCHING",
            bg="#1a0030", fg="#ff44cc",
            activebackground="#250040", activeforeground="#ff44cc",
        )
        region = _screen_region["coords"]
        region_str = (
            f"{region[2]-region[0]}×{region[3]-region[1]} region"
            if region else "full screen"
        )
        self.append_message("SYSTEM",
            f"Screen watch started · {region_str} · every {self.s.get('screen_interval',10)}s", "ai")

    def _stop_screen_watch(self):
        _screen_watch_event.clear()
        self._screen_btn.config(
            text="👁 WATCH SCREEN",
            bg="#0a001a", fg="#c084fc",
            activebackground="#160028", activeforeground="#c084fc",
        )
        self.append_message("SYSTEM", "Screen watch stopped.", "ai")

    def toggle_listening(self):
        if not _listen_event.is_set():
            self._go_live()
        else:
            self._stop()

    def _go_live(self):
        global stream
        try:
            import sounddevice as sd
        except ImportError:
            self.append_message("ERROR",
                "sounddevice is not installed.\n"
                "Run:  pip install sounddevice numpy\n"
                "Then restart the app.", "error")
            return

        dev_idx = find_device(self.s["device_name"])
        if dev_idx is None:
            if sys.platform == "win32":
                hint = "Install VB-Cable from vb-audio.com/Cable, then set your meeting app speaker to 'CABLE Input'."
            else:
                hint = "Run the pactl setup commands first (shown in the Audio Device section of settings)."
            self.append_message("ERROR",
                    f"Device '{self.s['device_name']}' not found.\n{hint}", "error")
            self.toggle_btn.config(text="▶  START LISTENING", state="normal",
                                   bg="#05282a", fg=C["accent"],
                                   activebackground="#0a3a3e", activeforeground=C["accent"])
            return

        # Flush stale audio before starting fresh
        while True:
            try:
                audio_queue.get_nowait()
            except queue.Empty:
                break

        _stats_reset()
        _listen_event.set()
        stream = sd.InputStream(samplerate=16000, channels=1,
                                device=dev_idx, callback=audio_callback)
        stream.start()

        threading.Thread(target=transcribe_loop,
                         args=(self.s, self),
                         daemon=True).start()

        self.toggle_btn.config(text="■  STOP  (Ctrl+L)", state="normal",
                               bg="#2a0a0a", fg="#ff4444",
                               activebackground="#3d0d0d", activeforeground="#ff4444")
        self.set_status("Listening...", C["accent"])
        tr_type = "Local Whisper" if self.s.get("transcription") == "local" else "Groq Whisper"
        self.append_message("SYSTEM",
            f"Live · {self.s['backend'].upper()} · transcription: {tr_type} · Ctrl+L to stop", "ai")
        self.update_stats()

    def _stop(self):
        global stream
        _listen_event.clear()
        _screen_watch_event.clear()  # also stop screen watch if running
        if stream:
            stream.stop()
            stream.close()
            stream = None
        self.toggle_btn.config(text="▶  START LISTENING  (Ctrl+L)",
                               bg="#05282a", fg=C["accent"],
                               activebackground="#0a3a3e", activeforeground=C["accent"])
        self._screen_btn.config(text="👁 WATCH SCREEN", bg="#0a001a", fg="#c084fc")
        self.set_status("Stopped", C["fg2"])
        self.append_message("SYSTEM", "Stopped.", "ai")


# ================================================================================
#  APP
# ================================================================================

class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Zoom Co-Pilot")
        self.root.configure(bg=C["bg"])
        self.root.attributes("-topmost", True)
        self.root.resizable(True, True)
        self.current = None
        self._capture_hidden = [True]
        self._bind_drag()
        self._show_setup()

    def _bind_drag(self):
        self._dx = self._dy = 0

        def _start_drag(e):
            # Only drag when clicking directly on the root window (title bar area),
            # not on child widgets like buttons, entries, or sliders.
            if e.widget is self.root:
                self._dx, self._dy = e.x, e.y

        def _do_drag(e):
            if e.widget is self.root:
                self.root.geometry(
                    f"+{self.root.winfo_x()+e.x-self._dx}+{self.root.winfo_y()+e.y-self._dy}")

        self.root.bind("<Button-1>",  _start_drag)
        self.root.bind("<B1-Motion>", _do_drag)

    def _show_setup(self):
        # Stop any active audio + screen watch before switching screens
        _listen_event.clear()
        _screen_watch_event.clear()
        global stream
        if stream:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
            stream = None
        if self.current:
            self.current.destroy()
        self.root.geometry("560x720+100+60")
        self.root.minsize(500, 540)
        self.current = SetupScreen(self.root, load_settings(), on_launch=self._launch)

    def _launch(self, settings):
        if self.current:
            self.current.destroy()
        # Reset shared state so a re-launch starts clean
        _listen_event.clear()
        with _history_lock:
            conversation_history.clear()
        while True:
            try:
                audio_queue.get_nowait()
            except queue.Empty:
                break
        self.root.geometry("540x620+100+60")
        self.root.minsize(420, 340)
        self.current = OverlayScreen(
            self.root, settings,
            on_settings=self._show_setup,
            on_toggle_capture=self._toggle_capture,
        )
        # Re-apply capture hiding after overlay is built
        self.root.after(100, lambda: self._set_capture_hidden(self._capture_hidden[0]))

    def _toggle_capture(self, btn):
        """Toggle screen capture visibility and update the button label."""
        self._capture_hidden[0] = not self._capture_hidden[0]
        hidden = self._capture_hidden[0]
        ok = self._set_capture_hidden(hidden)
        if ok:
            btn.config(
                text="🔒 Hidden from capture" if hidden else "👁  Visible in capture",
                fg=C["success"] if hidden else C["warn"],
            )
        else:
            btn.config(text="⚠ Not supported on this Windows", fg=C["warn"])

    def _set_capture_hidden(self, hidden: bool):
        """Show or hide the window from screen capture (Windows 10 2004+ only)."""
        if sys.platform != "win32":
            return False
        try:
            import ctypes
            hwnd = self.root.winfo_id()
            # WDA_EXCLUDEFROMCAPTURE=0x11 → black in captures; WDA_NONE=0x0 → visible
            affinity = 0x00000011 if hidden else 0x00000000
            ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, affinity)
            return True
        except Exception:
            return False

    def _minimize_to_tray(self):
        """#7 Minimize to system tray (Windows, requires pystray + Pillow)."""
        if not _TRAY_AVAILABLE or sys.platform != "win32":
            self.root.iconify()
            return
        self.root.withdraw()

        def _make_icon():
            # Create a tiny 64×64 cyan icon programmatically — no image file needed
            img = _PILImage.new("RGB", (64, 64), color=(11, 11, 15))
            # Draw a simple "◈" shape by filling a center square
            for x in range(20, 44):
                for y in range(20, 44):
                    img.putpixel((x, y), (0, 212, 255))
            return img

        def _on_restore(icon, item):
            icon.stop()
            self._tray_icon = None
            self.root.after(0, self.root.deiconify)

        def _on_quit(icon, item):
            icon.stop()
            self._tray_icon = None
            self.root.after(0, self.root.destroy)

        menu = pystray.Menu(
            pystray.MenuItem("Restore", _on_restore, default=True),
            pystray.MenuItem("Quit", _on_quit),
        )
        self._tray_icon = pystray.Icon("zoom-copilot", _make_icon(), "Zoom Co-Pilot", menu)
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def run(self):
        self.root.after(200, lambda: self._set_capture_hidden(True))
        # Bind minimize button to tray when pystray is available
        if _TRAY_AVAILABLE and sys.platform == "win32":
            self.root.protocol("WM_DELETE_WINDOW", self._minimize_to_tray)
            # Override default minimize (WM_ICONIFY) — bind to tray instead
            self.root.bind("<Unmap>", lambda e: (
                self._minimize_to_tray() if e.widget is self.root and self.root.state() == "iconic" else None
            ))
        self.root.mainloop()


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor DPI awareness
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
    App().run()
