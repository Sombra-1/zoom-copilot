@echo off
cd /d "%~dp0"
:: For zero console flash, use launch.pyw or the installed desktop shortcut.
if exist "%~dp0venv\Scripts\pythonw.exe" (
    start "" "%~dp0venv\Scripts\pythonw.exe" "%~dp0launch.pyw"
    exit /b 0
)
if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0launch.pyw"
    exit /b 0
)
where pythonw.exe >nul 2>&1
if not errorlevel 1 (
    start "" pythonw.exe "%~dp0launch.pyw"
    exit /b 0
)
where pyw.exe >nul 2>&1
if not errorlevel 1 (
    start "" pyw.exe "%~dp0launch.pyw"
    exit /b 0
)
echo A windowless Python interpreter was not found. Run setup.bat first.
pause
