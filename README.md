# Open Meeting Copilot

> Real-time AI assistant for Zoom, Teams, and Google Meet.

![License](https://img.shields.io/badge/license-GPL%20v3-blue)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![Release](https://img.shields.io/github/v/release/Sombra-1/zoom-copilot)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey)

Listens to your meeting audio, transcribes it, and turns the conversation into live context, summaries, decisions, action items, and Markdown notes from a floating overlay.

> **Copyright (C) 2026 Sombra-1** — Licensed under [GPL v3](LICENSE).
> You may use, modify, and share this project freely, but you must keep the copyright notice and release any modifications under the same license.

---

## Features

- **Real-time transcription** — Groq Whisper (cloud, fast) or Local Whisper (fully offline, no internet needed)
- **Multiple AI backends** — Ollama (free/local), Groq (free cloud), Claude (Anthropic), Demo
- **Structured meeting notes** — one-click Summary, Decisions, Action Items, and Open Questions
- **Markdown export** — save notes, backend/privacy mode, and raw transcript in an open format
- **Filterable overlay views** — switch between All, Transcript, AI, Notes, and Errors during a meeting
- **Privacy badges** — quickly see whether audio + AI are local-first, hybrid, or cloud-backed
- **Smart AI trigger** — only responds when something worth noting is said (questions, prices, keywords) — saves ~70% of API tokens
- **Practice Assist mode** — honest answer drafts for mock interviews, accessibility support, or explicitly permitted help
- **Screen watch** — periodic AI vision analysis of a selected screen region
- **Screen-share controls** — on supported Windows builds, the overlay requests OS-level capture exclusion and only reports hidden after Windows accepts it
- **Opacity slider** — adjust window transparency for overlay use
- **Manual input** — type questions to the AI mid-call
- **Timestamps** on every message
- **Hardened runtime settings** — settings are validated, clamped, and written atomically
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

**Step 4** — Choose local or cloud transcription/AI in Settings, then click **LAUNCH**

During a meeting:
- Click **START** to capture live audio.
- Click **Notes** to generate structured meeting notes from the captured transcript.
- Click **Export** to export notes and the raw transcript as Markdown.

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
4. Copy the `gsk_...` value and paste it in the **GROQ API KEY** box in Settings

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

## Windows Screen-share Hiding

On Windows 10 version 2004+ and Windows 11, the overlay uses the Windows `SetWindowDisplayAffinity` API with `WDA_EXCLUDEFROMCAPTURE`.

What this means:

- If the lock button says **Hidden from capture**, Windows accepted the capture-exclusion request.
- If Windows rejects the request, the app shows **Capture hide failed** instead of claiming it is hidden.
- Normal Zoom, Teams, and Meet screen sharing on Windows should respect this protection.
- Some capture paths can still see the overlay, including cameras pointed at the monitor, capture cards, VM-level capture, remote desktop/driver-level capture, or tools that bypass normal Windows capture APIs.

Always test your exact meeting app and sharing mode with a second device/account before relying on this behavior.

## Open-source direction

The project is designed to stay auditable and forkable:

- Local-first paths are available through Local Whisper and Ollama.
- Cloud providers are bring-your-own-key where possible.
- Meeting exports use plain Markdown instead of a proprietary format.
- Notes are generated only from captured transcript text; the prompts tell the model not to invent owners, dates, decisions, or tasks.
- API keys are stored only in the local `.copilot_settings.json`; on non-Windows systems the file is restricted to the current user.
- Audio-processing workers are capped so slow transcription or AI calls do not spawn unbounded background threads.

---

## Practice Assist Mode

Enable in Settings → toggle **Practice Assist**.

- Fill in your real resume/background and role context.
- Captured prompts trigger concise answer drafts grounded in that background.
- Use it for practice, mock interviews, accessibility support, or situations where assistance is allowed.

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
- **Overlay still appears in a share** — Confirm the button says **Hidden from capture**. If it says **Capture hide failed**, Windows rejected the capture-exclusion call. If it says hidden but still appears, test a different share mode; some capture tools bypass the Windows API.
- **Python not found** — Install Python 3.8+ from [python.org](https://www.python.org/downloads/) and check "Add to PATH".
- **Setup errors** — Check `setup_log.txt` in the project folder.

---

## License

Copyright (C) 2026 Sombra-1

This project is licensed under the **GNU General Public License v3.0**.
See [LICENSE](LICENSE) for full details.

You are free to use, study, modify, and distribute this software.
Any distributed version — modified or not — must remain open source under GPL v3 and must retain this copyright notice.
