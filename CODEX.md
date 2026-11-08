# Codex / ChatGPT and the answer HUD

## Getting started

1. Install the official **Codex CLI**, then sign in once with `codex login` or
   `codex login --device-auth`. The Codex desktop application is not required.
2. Install the app's optional dependencies:
   `python -m pip install -r requirements-optional.txt`. `setup.bat` and
   `setup.py` also install them. Existing text/audio modes remain usable if
   optional installation fails.
3. Choose **Codex / ChatGPT** in Settings and click **Refresh Codex status**.
   Leave Model empty to use the model marked default by `model/list`. A specific
   model must appear in that catalog. Catalog availability does not prove an
   account's inference entitlement; a completed request does.
4. Launch and type a question, or start meeting transcription. Transcription is
   still the existing Groq Whisper / Local Whisper selection; Codex does not
   replace Whisper and does not supply a Groq transcription key.

Discovery uses the CLI on PATH, including the official npm Node launcher on
Windows. CLI path can instead point to a native CLI executable. Do not select
the desktop GUI executable or a shell script. Existing Codex-managed credentials
are used by app-server itself; this app never opens, copies or parses auth files.
If a desktop-only installation has no usable CLI on PATH, install the CLI using
the official instructions and sign in through Codex. No account information is
hardcoded, and requests never launch a `codex://` URL or the desktop application.

Official documentation checked on 2026-10-31:

- [App-server protocol, accounts, models, images and structured output](https://learn.chatgpt.com/docs/app-server)
- [Codex authentication](https://learn.chatgpt.com/docs/auth)
- [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)

App-server is an evolving interface. This implementation was exercised with
`codex-cli 0.166.0-alpha.5.1`. Incompatible CLI versions, unavailable models,
expired accounts, timeouts and failed turns produce recoverable UI errors.
Status checks do not submit a billable inference request; Test Connection does.

## CLI detection on Windows

On Windows, automatic CLI detection checks PATH, the desktop-managed
`%LOCALAPPDATA%\OpenAI\Codex\bin` CLI directories (newest first), and
`%USERPROFILE%\.local\bin`. It also recognizes the official npm launcher
without executing its shell shim. This works when launching from Explorer,
whose PATH can differ from a Codex terminal. Keep the optional CLI path empty
for automatic detection across desktop updates. An explicit invalid path
reports a settings error rather than silently selecting another executable.

## Vision and privacy

The workspace has a **Watch screen** switch. Turning it on selects **All
displays** and starts an immediate analysis, then checks at the configured
interval. No window or region picker is needed. **Ctrl+Shift+S** toggles it
while Copilot is focused. Watching continues when you switch applications.
Turning it off disables vision and cancels pending screen answers. Each newly
opened workspace starts with vision Off, including after returning from Settings.

While vision is enabled, typed questions and triggered spoken questions attach
a fresh image of the selected target. Asking again always takes a fresh image,
even if an automatic check previously saw the same screen. Explicit questions
take priority over an older periodic analysis. With vision Off, questions use
the text-only backend. The scope/provider badge and last submitted capture time
remain visible; watch controls are separate from Windows screen-share exclusion.

This reads the visible desktop, including application switches. It does not
inspect minimized/covered windows or files. Codex receives sampled image inputs,
not a continuous video stream. The capture is compressed in memory rather than
saved to a screenshot file.

Vision defaults to **Off** when migrating older settings. Mode and target are
separate controls:

| Control | Behavior |
| --- | --- |
| Off | No model image requests; questions use text only |
| Manual | Capture now submits one selected target |
| Periodic | Watch starts the existing interval loop; identical JPEGs are skipped |
| Region | Use Region to drag an area; an unselected/cancelled region never means full screen |
| Window | Select window lists visible external Windows applications and uses direct PrintWindow capture |
| Screen | Explicitly captures the primary monitor; does not combine all monitors |
| All displays | Explicitly captures the visible desktop across all monitors |

Capture now includes any question currently in the input box and the last eight
transcript entries. Present requests short talking points and a suggested next
sentence. Changing the vision mode/target or selecting another region/window
stops the old periodic run. Watch must be started again explicitly.

The persistent label says **Codex Vision — Cloud** or **Ollama Vision — Local**
when enabled. Image requests use the same existing capture/compression functions
as screen watch. Codex receives an image and text together, through documented
app-server inputs. Screenshot bytes stay in memory for Codex requests, are never
written to application logs, and are never sent with vision Off. The direct
window helper uses an application-owned temporary PNG, deletes it on completion,
and never falls back to a desktop capture. Conversation text and answers remain
in the existing in-memory meeting history and explicit exports.

Loopback Ollama hosts are labeled Local; configuring Ollama Host to a remote
server changes the vision label to Remote and sends data there. Use a trusted host. Provider data handling and retention also
depend on the selected account/provider; app-server threads are requested as
ephemeral and this app does not persist their IDs.

## Overlay exclusion: measured behavior and limits

The Windows sharing control retains `WDA_EXCLUDEFROMCAPTURE` and checks the API's
readback. **Share: hidden** means Windows accepted and reported that affinity.
It is not a guarantee about an external recorder. Private app toplevel windows
also request affinity when mapped while hiding is enabled.

At overlay startup, a small synthetic green/pink test checks the actual selected
MSS/Pillow path for underlying green content after excluding the pink window.
This local test is never uploaded. The UI reports whether that capturer passed.
For real captures, each visible private app surface must also have exclusion
enabled. Otherwise the app withdraws its private windows, waits a compositor
frame, captures, and restores them in `finally`. This fallback can cause a brief
visible disappearance (about 65 ms plus capture time). It is used automatically
on Linux and unverified Windows capture paths. It never paints the overlay black
over the underlying content as a substitute for excluding it.

Selected-window capture uses a hidden, time-bounded helper with `PrintWindow`.
Some GPU-rendered, protected, minimized or hung windows return blank/unsupported
images. These produce an error; choose a region instead. Direct window capture
is currently Windows-only. Region/primary-screen capture remain available on
supported Linux desktops. Wayland and compositor permissions may restrict them.

**External acceptance still required:** test the exact Zoom/Teams/Meet sharing
mode and a recording with another account/device before relying on privacy.
Capture cards, cameras, virtual machines, remote-desktop and driver-level capture
may bypass affinity. No local pixel test can guarantee their behavior.

## Answers and math

The HUD handles answer, math, code, debugging, definition, comparison,
presentation and meeting-note cards. Model JSON is validated into an immutable
`Answer`; malformed, unknown or oversized output falls back to bounded text.
The original meeting log/filter/export controls remain available underneath.

- **Compact** shows the summary/final equation or speaking bullets.
- **Normal** adds the main content, cause/fix and code.
- **Detailed / Solution** adds worked steps and explanation, without another request.
- Previous/next, Pin, Copy, Clear and font −/+ operate locally. Pin keeps the
  selected card while later responses accumulate (up to 50 cards).
- The opacity slider is temporary for the current overlay session.

LaTeX is rendered with bundled **KaTeX 0.19.1**, including fractions, powers,
roots, integrals, derivatives, limits, sums, matrices, vectors, Greek letters,
cases, aligned equations and boxed answers. Its MIT license and npm integrity
metadata are in `copilot_core/vendor/katex/`. Rendering uses an isolated hidden
Playwright browser and embedded fonts, with page network requests blocked,
`trust:false`, bounded expansion/size and the browser sandbox enabled.
No model HTML or JavaScript is executed. The helper and its process tree are
owned and stopped on shutdown. A small bounded memory cache avoids repeat work.

On Windows, math preview uses the installed Microsoft Edge browser. On Linux,
install Playwright's Chromium with `python -m playwright install chromium`
(and its documented OS dependencies). Enterprise browser policy can prevent
headless rendering. Missing dependencies or unsupported/malformed LaTeX display
a safe LaTeX source fallback and an availability message. Code uses Consolas and
optional Pygments language detection/highlighting, with a plain code fallback.

## Optional project development tools

Enable Developer tools in Settings. This grants a fixed set of UI actions:
inspect allowlisted project Python files, view recent in-memory application
errors/tracebacks, run the fixed tests/lint/security commands, and ask Codex to
propose a source change from the selected file and entered issue. Only the
explicit Propose action sends that source/issue to Codex Cloud.

The model has no unrestricted Windows desktop, shell, connector, filesystem or
MCP tools. Normal inference disables shell/patch/image-file tools, skills,
connectors/plugins, web search and delegation; inherited MCP/plugin/app entries
are explicitly disabled for the thread. Unexpected server tool/approval requests
are refused. General diagnosis can still use the supplied screen/transcript.

Developer proposals must identify one exact, unique before/after source
fragment. The app builds a unified diff without changing code. Approve displayed
diff is an explicit user action. It checks the original SHA-256, validates Python
syntax, and runs the existing unit suite with the proposed edit in a temporary
copy. The copy excludes local settings and logs. A failed check discards the
candidate and shows the test result. On success, the app rechecks the original
hash and replaces the file atomically. Test processes run with your Python
process's permissions. Review the proposal before approving it.
Credentials, settings, paths outside the repository and symlink escapes are not
available to these tools. Closing the panel/app stops owned checks and requests.

## Validation

Commands (also used by CI, including the new modules):

```text
python -m compileall -q zoom_copilot.py setup.py copilot_core tests
python -m tabnanny zoom_copilot.py setup.py copilot_core tests
python -m pyflakes zoom_copilot.py setup.py copilot_core tests
python -m unittest discover -v
python -m bandit -q -lll -r zoom_copilot.py setup.py copilot_core
```

The default suite has 63 tests, with five platform/dependency integration tests
opt-in. To run all on an interactive Windows desktop in PowerShell:

```powershell
$env:COPILOT_CAPTURE_TESTS='1'
$env:COPILOT_RENDER_TESTS='1'
python -m unittest discover -v
```

Verified locally: all 63 tests pass with both switches enabled; compilation,
tabnanny, pyflakes and high-severity Bandit checks pass; setup/overlay/developer
widgets construct; real synthetic pixel tests cover accepted exclusion, the
hide/restore fallback and occluded selected-window capture; real offline KaTeX
tests cover the mathematical notation above. The real installed Codex account
completed text and synthetic image requests, returning `x = 6` and integral `12`.
No real meeting desktop image was uploaded during these checks. Existing cloud
backend regressions use mocked payloads; live Groq/Claude/Whisper meetings and
external Zoom recording were not exercised.

Tests cover availability, backend selection/regressions, malformed schema,
disclosure/code/math, privacy defaults, capture errors, cancellation, process
exit/timeout/shutdown, settings migration, patch approval and stale-file rejection.
Windows subprocesses use kill-on-close jobs; POSIX helpers use owned process
groups. Clear, Stop, settings transitions and shutdown invalidate old work.

Final review follow-ups were applied and tested: remote Ollama host labeling,
late-cancellation checks before legacy vision dispatch, a capture-probe positive
control compatible with the automatic Map exclusion hook, and typed note cards.
The immutable Codex Security scan preceding these small follow-ups reviewed 18
changed runtime files and reported no validated vulnerabilities; third-party
Codex/browser/OS/KaTeX internals and external meeting recorders were excluded.
The final follow-ups were checked with the full 63-test suite and the same
compilation/lint/high-severity security commands.
