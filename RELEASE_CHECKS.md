# Release validation

## v2.1.0

All 154 local Windows tests passed with native test-window capture and offline
math rendering enabled. The Settings regression test switches views during
listening and verifies that the last audio fragment, transcript, pinned answer,
notes, and draft are available when the workspace reopens. The Groq regression
test verifies that automatic language detection omits the optional language field.

The packaged Windows launcher also transcribed quiet synthetic speech offline
with the real Whisper tiny model. The mixed-version check ran Local Whisper from
v2.0.3 and v2.1 with the same configured Hugging Face cache root. Each version
continued decoding after the other deleted its own model copy, and a second
v2.1 process was blocked from deleting an active model.

The audio checks used synthetic inputs and clips. Live Zoom, Teams, and Meet
sessions still need field validation.

## v2.0.3 Quality Update

Local Windows validation passed 140 tests across the main suite with native
capture and a separate offline math-rendering run. The audio recovery tests
held the final partial chunk's decoder open while exercising manual cancellation
and the inactivity timeout. Both paths restored export, retained decoded speech
and recorded the gap. A later session rejected the abandoned decoder's result.

The tests used synthetic audio. An abandoned native Local Whisper call may stay
busy until it returns or the app restarts. Live meeting validation remains open.

## v2.0.2 audio hotfix

The Windows suite passed all 138 tests with native capture and math rendering
enabled. The listening UI passed 30 synthetic start/stop cycles and finished a
partial utterance after Stop. An accelerated replay fed 900 eight-second chunks
to a deliberately stalled decoder. The queue peaked at eight chunks, and the
transcript placed the recorded loss between the surviving speech and final tail.
Live meeting validation remains open.

## v2.0.1 reliability release

See the [v2.0.1 validation record](docs/release-checks-v2.0.1.md) for that release's
local tests, CI and asset verification.

## v2.0.0 baseline — 2026-11-05

Validated on Windows with Python 3.11.9. The supported baseline is Python 3.11+.

### Launch

Open **Zoom Co-Pilot** from the Desktop, **Zoom Copilot.exe**, or `launch.pyw`.
The branded launcher starts the project's windowless Python environment.
The native launch test reported a zero console handle, usable standard streams,
constructed settings widgets, and a clean process exit.

`run.bat` remains a compatibility launcher. Windows can briefly show CMD when
opening a batch file; the desktop shortcut and `.pyw` entry point avoid it.

### Corrections completed

- Added windowless startup with project-environment selection and a startup error dialog.
- Hid background Python, PowerShell, package-install and Ollama console helpers.
- Added bounded local exception metadata logs, excluding messages, source lines,
  credentials, images and conversation content.
- Made shutdown idempotent and ensured audio close is attempted even if stop fails.
- Restored the window if system-tray startup fails; stopped the tray during shutdown.
- Routed installer worker updates through the UI dispatcher and ignored late callbacks.
- Rejected an empty audio-device name instead of matching the first microphone.
- Reused an existing Ollama installation when its server is stopped.
- Updated Pillow to 13.x, its supported resize API, installer checks, Python baseline
  and CI configuration. Pillow 13 includes the security fixes documented in the
  [official release notes](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html)
  and requires Python 3.11+ according to its
  [supported Python versions](https://pillow.readthedocs.io/en/stable/installation/python-support.html).

### Verification

| Check | Result |
| --- | --- |
| Full suite, including opt-in native capture and math integration tests | 129 passed, no skips |
| Compilation, indentation and Pyflakes | Passed |
| Bandit high-severity check | Passed |
| Python dependency audit of the installed snapshot, including packaging tools | 49 packages; zero known advisory entries |
| Installed dependency compatibility (`pip check`) | Passed |
| Actual windowless bootstrap | No attached console; clean exit |
| Real Codex vision through a typed screen question under `pythonw.exe` | Read an application-owned synthetic channel name and number |
| Offline equation rendering under `pythonw.exe` | Passed |
| Three settings/workspace round trips | Passed; opacity restored and vision starts Off |
| Windows capture exclusion, fallback hiding and direct window capture | Passed using synthetic windows |
| Local Whisper in the dedicated app environment | Installed and import verified |
| Support reminder and release notices | Persistence, offline behavior, lifecycle and real UI tests passed |
| Both notices at minimum workspace size | Answer, composer and listening controls remain accessible |
| Logo without optional Pillow at standard Windows scaling | Native PNG fallback preserves the header size and answer area |
| Public screenshots and demo video | Actual app, synthetic Demo-mode content only |

The installed environment was created from the project requirements, with local
Whisper and developer-check dependencies included. `requirements-validated.txt`
records the exact Windows/Python 3.11 package snapshot used for these checks.
The dependency audit describes known Python-package advisories at validation time.

The live-image test uploaded only pixels from an application-owned demonstration
window. Full meeting audio with Zoom/Teams and live Groq/Claude/Ollama account
requests were not exercised; their dispatch, error and session behavior is covered
by the regression suite. GitHub Actions checks Python 3.11, 3.12 and 3.13, rebuilds
the native launcher, and runs high-severity Bandit checks. Current CI results are
visible on the [Actions page](https://github.com/Sombra-1/zoom-copilot/actions/workflows/ci.yml).

The release ZIP contains source and a small Windows launcher, not a bundled
Python runtime. `setup.bat` refreshes packaging tools and dependencies. Public
packages exclude settings, credentials, caches, logs, models and environments.
SHA-256 checksums accompany the downloadable release assets.

Update notices begin with v2.0. Older installations need one manual update to
gain the checker; future stable GitHub Releases can notify automatically.

Local failure metadata is stored in `%LOCALAPPDATA%\ZoomCopilot\logs\runtime.log`,
with rotation limited to three files of approximately 64 KiB each.
