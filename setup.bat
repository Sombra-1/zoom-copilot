@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Zoom Co-Pilot — Setup

color 0B
cls
echo.
echo  ============================================================
echo   ZOOM CO-PILOT -- Automatic Setup
echo   This will install everything needed. Takes 1-2 minutes.
echo  ============================================================
echo.

set "SCRIPT_DIR=%~dp0"
set "VENV=%SCRIPT_DIR%venv"
set "LOG=%SCRIPT_DIR%setup_log.txt"
echo Setup started %date% %time% > "%LOG%"

:: ── Step 1: Python ─────────────────────────────────────────────────────────
echo  [1/4] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    :: Try common install locations before winget
    if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
        set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%PATH%"
        echo        Found Python in AppData.
        goto python_ok
    )
    if exist "C:\Python311\python.exe" (
        set "PATH=C:\Python311;%PATH%"
        echo        Found Python in C:\Python311.
        goto python_ok
    )

    echo        Not found -- installing Python 3.11 via winget...
    winget install --id Python.Python.3.11 -e --silent --accept-package-agreements --accept-source-agreements >> "%LOG%" 2>&1
    if errorlevel 1 (
        echo.
        echo  [!] winget could not install Python automatically.
        echo      Please install Python 3.11 from python.org/downloads
        echo      Check "Add python.exe to PATH" during install, then re-run this file.
        echo.
        start https://www.python.org/downloads/
        echo  Press any key to exit...
        pause >nul
        exit /b 1
    )
    :: Refresh PATH after winget install
    for /f "tokens=*" %%i in ('where python 2^>nul') do set "PYTHON_EXE=%%i"
    if "!PYTHON_EXE!"=="" (
        echo.
        echo  [!] Python was installed but not found on PATH.
        echo      Please close this window, restart your PC, and run setup.bat again.
        echo.
        pause
        exit /b 1
    )
    echo        Python installed.
) else (
    for /f "tokens=2" %%v in ('python --version 2^>&1') do echo        Found Python %%v
)
:python_ok
echo.

:: ── Step 2: Virtual environment ────────────────────────────────────────────
echo  [2/4] Setting up isolated environment...
if exist "%VENV%\Scripts\python.exe" (
    echo        Already exists -- skipping.
) else (
    python -m venv "%VENV%" >> "%LOG%" 2>&1
    if errorlevel 1 (
        echo.
        echo  [!] Could not create virtual environment.
        echo      See setup_log.txt for details.
        echo.
        pause
        exit /b 1
    )
    echo        Created.
)
echo.

:: ── Step 3: Python packages ────────────────────────────────────────────────
echo  [3/4] Installing Python packages...
echo        Core: sounddevice, numpy, requests
"%VENV%\Scripts\pip.exe" install -r "%SCRIPT_DIR%requirements.txt" -q >> "%LOG%" 2>&1
if errorlevel 1 (
    echo.
    echo  [!] Core package install failed. See setup_log.txt
    echo.
    pause
    exit /b 1
)
echo        Core packages done.

echo        Optional: mss, Pillow, pystray  (screen watch + system tray)
"%VENV%\Scripts\pip.exe" install -r "%SCRIPT_DIR%requirements-optional.txt" -q >> "%LOG%" 2>&1
if errorlevel 1 (
    echo        [WARN] Optional packages failed -- screen watch/tray won't work.
    echo               Core app will still work fine.
) else (
    echo        Optional packages done.
)
echo.

:: ── Step 4: VB-Cable virtual audio driver ──────────────────────────────────
echo  [4/4] Installing VB-Cable virtual audio driver...
echo        (This routes Zoom/Teams audio into the co-pilot)
echo.

set "CABLE_ZIP=%TEMP%\VBCable.zip"
set "CABLE_DIR=%TEMP%\VBCable"

powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack43.zip' -OutFile '%CABLE_ZIP%' -UseBasicParsing" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo        [WARN] Could not download VB-Cable automatically.
    echo               Download and install it manually from: vb-audio.com/Cable
    echo               Then in Zoom: Settings -^> Audio -^> Speaker -^> CABLE Input
) else (
    if exist "%CABLE_DIR%" rmdir /s /q "%CABLE_DIR%"
    powershell -NoProfile -Command "Expand-Archive -Path '%CABLE_ZIP%' -DestinationPath '%CABLE_DIR%' -Force" >> "%LOG%" 2>&1
    powershell -NoProfile -Command "$env:PSModulePath=$env:ProgramFiles+'\WindowsPowerShell\Modules;'+$env:WINDIR+'\System32\WindowsPowerShell\v1.0\Modules'; $s=Get-AuthenticodeSignature -LiteralPath '%CABLE_DIR%\VBCABLE_Setup_x64.exe'; if($s.Status -ne 'Valid'){ Write-Error ('Invalid installer signature: '+$s.Status); exit 1 }" >> "%LOG%" 2>&1
    if errorlevel 1 (
        echo        [WARN] VB-Cable installer signature is missing or invalid.
        echo               Install it manually from: vb-audio.com/Cable
    ) else (
        echo        Signature verified. Requesting admin rights for the driver only...
        powershell -NoProfile -Command "$p=Start-Process -FilePath '%CABLE_DIR%\VBCABLE_Setup_x64.exe' -ArgumentList '/S' -Verb RunAs -Wait -PassThru; exit $p.ExitCode" >> "%LOG%" 2>&1
        if errorlevel 1 (
            echo        [WARN] Silent driver install failed. Opening the verified installer...
            powershell -NoProfile -Command "Start-Process -FilePath '%CABLE_DIR%\VBCABLE_Setup_x64.exe' -Verb RunAs -Wait" >> "%LOG%" 2>&1
        )
        echo        VB-Cable installed.
    )
)
echo.

:: ── Create desktop shortcut ────────────────────────────────────────────────
echo  Creating desktop shortcut...
set "SHORTCUT=%USERPROFILE%\Desktop\Zoom Co-Pilot.lnk"
set "TARGET=%VENV%\Scripts\pythonw.exe"
set "ARGS=%SCRIPT_DIR%zoom_copilot.py"
powershell -NoProfile -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut('%SHORTCUT%'); $s.TargetPath='%TARGET%'; $s.Arguments='\"%ARGS%\"'; $s.WorkingDirectory='%SCRIPT_DIR%'; $s.Description='Zoom Co-Pilot'; $s.Save()" >> "%LOG%" 2>&1
echo        Shortcut created on Desktop.
echo.

:: ── Done ──────────────────────────────────────────────────────────────────
echo  ============================================================
echo   All done!
echo.
echo   Next steps:
echo     1. Open Zoom (or Teams/Meet)
echo     2. Go to Settings ^> Audio ^> Speaker
echo     3. Change it to "CABLE Input"
echo     4. Double-click "Zoom Co-Pilot" on your Desktop to launch
echo  ============================================================
echo.
pause
