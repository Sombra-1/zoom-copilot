@echo off
if not exist venv (
    echo Run setup.bat first!
    pause
    exit /b 1
)
start "" venv\Scripts\pythonw.exe zoom_copilot.py
