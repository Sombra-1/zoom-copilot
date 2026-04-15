@echo off
cd /d "%~dp0"

:: Try venv pythonw first (no console window)
if exist "%~dp0venv\Scripts\pythonw.exe" (
    start "" "%~dp0venv\Scripts\pythonw.exe" "%~dp0zoom_copilot.py"
    exit /b 0
)

:: Try venv python (shows a brief console)
if exist "%~dp0venv\Scripts\python.exe" (
    start "" "%~dp0venv\Scripts\python.exe" "%~dp0zoom_copilot.py"
    exit /b 0
)

:: Fall back to system python
python --version >nul 2>&1
if not errorlevel 1 (
    start "" python "%~dp0zoom_copilot.py"
    exit /b 0
)

:: Nothing worked
echo.
echo  [!] Could not find Python or the virtual environment.
echo      Please run setup.bat first.
echo.
pause
