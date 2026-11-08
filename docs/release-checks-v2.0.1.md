# Zoom Copilot v2.0.1 validation

Released November 8, 2026 from commit `17e1c736f6c1e291c799e8388d198756d8bf769f`. [GitHub release](https://github.com/Sombra-1/zoom-copilot/releases/tag/v2.0.1)

| Check | Result |
| --- | --- |
| Local Windows suite with native capture and math rendering enabled | 137 passed |
| Listening UI with synthetic audio and a stalled answer | Transcription continued in order |
| Synthetic listening start/stop | 30 cycles with no stale replies or leftover audio workers |
| GitHub Windows CI | Python 3.11, 3.12 and 3.13 passed |
| GitHub security job | Passed |
| Release assets | ZIP and SHA-256 file verified against GitHub asset digests |

The Windows jobs compiled the launcher and ran the core suite. The local run
covered the optional native capture and math cases. [CI results](https://github.com/Sombra-1/zoom-copilot/actions/runs/42454845964)

Live Zoom, Teams and Meet audio, mixed-DPI meeting capture and a two-hour live
session remain open validation cases. The listening checks used synthetic input.
