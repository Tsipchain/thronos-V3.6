@echo off
title Thronos Miner Kit
cd /d "%~dp0"

if not exist logs mkdir logs

:: ── Python detection: prefer py launcher, fall back to python ───────────────
set PYTHON=
py -3 --version >nul 2>&1 && set PYTHON=py -3
if "%PYTHON%"=="" python --version >nul 2>&1 && set PYTHON=python
if "%PYTHON%"=="" (
    echo.
    echo  ERROR: Python 3 is not installed or not on PATH.
    echo.
    echo  Install Python 3 from: https://www.python.org/downloads/
    echo  During installation, check "Add Python to PATH".
    echo.
    echo  Then re-run start_here.bat.
    echo.
    pause
    exit /b 1
)

:: ── Install requests silently if missing ────────────────────────────────────
%PYTHON% -c "import requests" >nul 2>&1
if errorlevel 1 (
    echo Installing required library (requests)...
    %PYTHON% -m pip install requests --quiet --disable-pip-version-check
    if errorlevel 1 (
        echo  WARNING: could not auto-install requests.
        echo  Run manually:  pip install requests
        echo.
    )
)

:: ── THR address: use personalised value or prompt ───────────────────────────
set THR_ADDRESS=YOUR_THR_ADDRESS
if "%THR_ADDRESS%"=="YOUR_THR_ADDRESS" (
    if not "%~1"=="" (
        set THR_ADDRESS=%~1
    ) else (
        set /p THR_ADDRESS="Enter your THR wallet address (THR...): "
    )
)
if "%THR_ADDRESS%"=="" (
    echo ERROR: THR address is required.
    pause
    exit /b 1
)

set THRONOS_API_URL=https://api.thronoschain.org

:MENU
cls
echo ============================================================
echo  Thronos Miner Kit
echo  Address : %THR_ADDRESS%
echo  Server  : %THRONOS_API_URL%
echo  Logs    : %~dp0logs\
echo ============================================================
echo.
echo   1. CPU Miner      ^(any PC, no extra hardware^)
echo   2. Stratum Proxy  ^(for USB ASIC / GPU miners^)
echo   3. USB ASIC setup instructions
echo   4. Exit
echo.
set CHOICE=
set /p CHOICE="Choice (1-4): "

if "%CHOICE%"=="1" goto CPU_MINER
if "%CHOICE%"=="2" goto STRATUM_PROXY
if "%CHOICE%"=="3" goto USB_ASIC_INFO
if "%CHOICE%"=="4" exit /b 0
echo.
echo  Invalid choice — press any key and try again.
pause >nul
goto MENU

:: ── CPU Miner ───────────────────────────────────────────────────────────────
:CPU_MINER
echo.
echo  Starting CPU Miner...
echo  Logs: logs\cpu.log
echo  Press Ctrl+C to stop.
echo.
set PYTHONUNBUFFERED=1
%PYTHON% -u cpu\pow_miner_cpu.py --address %THR_ADDRESS% --api %THRONOS_API_URL% 2>&1 | powershell -NoProfile -NonInteractive -Command "$input | Tee-Object -FilePath 'logs\cpu.log'"
if errorlevel 1 (
    echo.
    echo  CPU miner exited. See logs\cpu.log for details.
    echo  Common fix:  %PYTHON% -m pip install requests
)
pause
goto MENU

:: ── Stratum Proxy ────────────────────────────────────────────────────────────
:STRATUM_PROXY
echo.
echo  Starting Stratum Proxy on port 3334...
echo  Point your miner at: stratum+tcp://127.0.0.1:3334
echo  Logs: logs\proxy.log
echo  Press Ctrl+C to stop.
echo.
set PYTHONUNBUFFERED=1
set STRATUM_PROXY_ADDRESS=%THR_ADDRESS%
set THRONOS_SERVER=%THRONOS_API_URL%
%PYTHON% -u proxy\stratum_proxy.py 2>&1 | powershell -NoProfile -NonInteractive -Command "$input | Tee-Object -FilePath 'logs\proxy.log'"
if errorlevel 1 (
    echo.
    echo  Stratum proxy exited. See logs\proxy.log for details.
)
pause
goto MENU

:: ── USB ASIC Info ────────────────────────────────────────────────────────────
:USB_ASIC_INFO
cls
echo ============================================================
echo  USB ASIC Setup
echo ============================================================
echo.
echo  Step 1. Install driver
echo          Open: usb-asic\drivers\README_DRIVERS.md
echo          Use Zadig to install CP210x or WinUSB driver.
echo.
echo  Step 2. Add miner binary
echo          Place cgminer.exe in usb-asic\bin\cgminer.exe
echo          (binary NOT included — download from the cgminer project)
echo.
echo  Step 3. Start the Stratum Proxy first (option 2 on main menu).
echo.
echo  Step 4. Run: usb-asic\run_cgminer_usb.bat
echo.
echo  NOTE: HTTP 202 responses from the server are SUCCESS.
echo        This means your block is queued for processing.
echo.
pause
goto MENU
