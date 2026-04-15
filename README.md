# Zoom Co-Pilot

> Real-time AI assistant for Zoom, Teams, and Google Meet.

![License](https://img.shields.io/badge/license-GPL%20v3-blue)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![Release](https://img.shields.io/github/v/release/Sombra-1/zoom-copilot)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey)

Listens to your meeting audio, transcribes it, and gives you AI-generated replies — all in a floating overlay that's **invisible to screen share**.

> **Copyright (C) 2026 Sombra-1** — Licensed under [GPL v3](LICENSE).
> You may use, modify, and share this project freely, but you must keep the copyright notice and release any modifications under the same license.

---

## Features

- **Real-time transcription** — Groq Whisper (cloud, fast) or Local Whisper (fully offline, no internet needed)
- **Multiple AI backends** — Ollama (free/local), Groq (free cloud), Claude (Anthropic), Demo
- **Smart AI trigger** — only responds when something worth noting is said (questions, prices, keywords) — saves ~70% of API tokens
- **Interview mode** — STAR-format suggested answers using your resume and role context
- **Screen watch** — periodic AI vision analysis of a selected screen region
- **Screen-share invisible** — overlay is hidden from screen capture by default; toggle with the lock button
- **Opacity slider** — adjust window transparency for overlay use
- **Manual input** — type questions to the AI mid-call
- **Timestamps** on every message
- **One-click setup** — `setup.bat` or `setup.py` installs everything automatically

---

## Quick Start (Windows)

**Step 1** — Double-click `setup.bat`
- Click YES on the admin prompt
- Wait 1-2 minutes (installs Python packages + VB-Cable audio driver)

**Step 2** — Open Zoom (or Teams / Google Meet)
- Go to Settings → Audio → Speaker
- Change it to **CABLE Input**

**Step 3** — Double-click **Zoom Co-Pilot** on your Desktop (shortcut created by setup.bat)

**Step 4** — Paste your Groq API key in Section 03, then click **LAUNCH**

### Cross-platform (Windows / Linux)

```bash
python setup.py
```

Checks all dependencies, installs missing ones, and launches the app.

---

## Getting a Groq API Key (free)

1. Go to [console.groq.com](https://console.groq.com)
2. Sign up (no credit card needed)
3. API Keys → Create API Key
4. Copy the `gsk_...` value and paste it in Section 03 of the app

---

## AI Backends

| Backend | Cost | Requires |
|---------|------|----------|
| Built-in (Ollama) | Free, local | Auto-installs on first use |
| Demo | Free | Nothing — fake replies for UI testing |
| Groq | Free (14k req/day) | Groq API key |
| Claude | Paid | Anthropic API key |
| Ollama (custom) | Free, local | Ollama installed + model name |

---

## Transcription Options

| Mode | Speed | Requires |
|------|-------|----------|
| Groq Whisper | Fast (cloud) | Groq API key + internet |
| Local Whisper | Offline | One-click install inside the app |

Local Whisper works anywhere — no internet, no VPN, no API key.
Model sizes: `tiny` (40 MB) · `base` (150 MB) · `small` (500 MB) · `medium` (1.5 GB)

To install: open the app → Settings → Section 03 → click **Install faster-whisper**.

---

## Interview Mode

Enable in Settings → toggle **Interview Mode**.

- Fill in your resume/background and the job title you're interviewing for
- Every transcript automatically triggers a STAR-format suggested answer
- Responses include context from your experience and the role

---

## Requirements

- Windows 10/11 (Linux partially supported)
- Python 3.8+
- `sounddevice`, `numpy`, `requests` (auto-installed by setup)
- VB-Cable virtual audio driver (auto-installed by `setup.bat` on Windows)

---

## Troubleshooting

- **Groq 403 error** — Your region may be blocked. Switch to **Local Whisper** in Section 03 (fully offline, no API needed).
- **No audio captured** — Make sure Zoom's speaker is set to **CABLE Input**.
- **Python not found** — Install Python 3.8+ from [python.org](https://www.python.org/downloads/) and check "Add to PATH".
- **Setup errors** — Check `setup_log.txt` in the project folder.

---

## License

Copyright (C) 2026 Sombra-1

This project is licensed under the **GNU General Public License v3.0**.
See [LICENSE](LICENSE) for full details.

You are free to use, study, modify, and distribute this software.
Any distributed version — modified or not — must remain open source under GPL v3 and must retain this copyright notice.
