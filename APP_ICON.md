# Zoom Copilot logo and launcher

Open **Zoom Copilot.exe** to launch the app with its own file icon. Keep it beside
`launch.pyw`, `assets`, `copilot_core` and the other app files. This small Windows
launcher starts the existing Python app without a console; install the app's
dependencies with `setup.bat` when setting up a fresh copy.

The logo is used in the title bar/taskbar, settings and workspace headers, system
tray, and desktop shortcut. The editable source is `assets/logo.svg`; PNG and
multi-size Windows ICO exports are included.

Rebuild assets:

```powershell
python tools/build_icons.py
powershell -NoProfile -ExecutionPolicy Bypass -File tools/build-launcher.ps1
```

Recreate a desktop shortcut:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File create-shortcut.ps1
```

The launcher source is `tools/WindowsLauncher.cs` and is distributed under the
project's GPL-3.0 license. It resolves a local virtual environment first, then
registered Python 3.11+ installations. It also accepts an explicit
`--python "C:\path\to\pythonw.exe"` argument for an already configured environment.
It does not bundle Python or change Windows file associations.
