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
    echo Installing required library ^(requests^)...
    %PYTHON% -m pip install requests --quiet --disable-pip-version-check
    if errorlevel 1 (
        echo.
        echo  WARNING: auto-install failed. Run this manually then restart:
        echo    pip install requests
        echo.
        pause
        exit /b 1
    )
    echo  Done.
    echo.
)

:: ── THR address: use personalised value or prompt ───────────────────────────
:: YOUR_THR_ADDRESS is replaced at zip build time with the real address.
:: The /I prefix check avoids the comparison being corrupted when both sides
:: get substituted with the real address by the zip builder.
set THR_ADDRESS=YOUR_THR_ADDRESS
if not "%~1"=="" set THR_ADDRESS=%~1
if /I "%THR_ADDRESS:~0,3%"=="THR" goto ADDR_VALID
set /p THR_ADDRESS="Enter your THR wallet address (THR...): "
:ADDR_VALID
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
cls
echo ============================================================
echo  CPU Miner — running
echo  Address : %THR_ADDRESS%
echo  Press Ctrl+C to stop.
echo ============================================================
echo.
set PYTHONUNBUFFERED=1
%PYTHON% -u cpu\pow_miner_cpu.py --address %THR_ADDRESS% --api %THRONOS_API_URL%
set CPU_EXIT=%ERRORLEVEL%
echo.
echo ============================================================
echo  Miner stopped ^(exit code %CPU_EXIT%^).
if %CPU_EXIT% NEQ 0 (
    echo.
    echo  If you see "ModuleNotFoundError: No module named 'requests'":
    echo    Run:  %PYTHON% -m pip install requests
    echo    Then re-run start_here.bat.
    echo.
)
echo  Press any key to return to the menu.
echo ============================================================
pause >nul
goto MENU

:: ── Stratum Proxy ────────────────────────────────────────────────────────────
:STRATUM_PROXY
cls
echo ============================================================
echo  Stratum Proxy — port 3334
echo  Address : %THR_ADDRESS%
echo  Point your miner at:  stratum+tcp://127.0.0.1:3334
echo  Worker:  %THR_ADDRESS%.worker1    Password: x
echo  Press Ctrl+C to stop.
echo ============================================================
echo.
set PYTHONUNBUFFERED=1
set STRATUM_PROXY_ADDRESS=%THR_ADDRESS%
set THRONOS_SERVER=%THRONOS_API_URL%
%PYTHON% -u proxy\stratum_proxy.py
set PROXY_EXIT=%ERRORLEVEL%
echo.
echo ============================================================
echo  Proxy stopped ^(exit code %PROXY_EXIT%^).
echo  Press any key to return to the menu.
echo ============================================================
pause >nul
goto MENU

:: ── USB ASIC Info ────────────────────────────────────────────────────────────
:USB_ASIC_INFO
cls
echo ============================================================
echo  USB ASIC Setup Guide
echo ============================================================
echo.
echo  STEP 1 — Install USB driver
echo    Open: usb-asic\drivers\README_DRIVERS.md
echo    Use Zadig to install CP210x or WinUSB for your device.
echo.
echo  STEP 2 — Download cgminer or bfgminer (NOT included)
echo    cgminer: https://github.com/ckolivas/cgminer/releases
echo    bfgminer: https://bfgminer.org/
echo.
echo    Place the .exe here:
echo      %~dp0usb-asic\bin\cgminer.exe
echo      %~dp0usb-asic\bin\bfgminer.exe
echo.
echo  STEP 3 — Start the Stratum Proxy (menu option 2)
echo    Keep that window open.
echo.
echo  STEP 4 — Run the ASIC bat
echo    Double-click:  usb-asic\run_cgminer_usb.bat
echo                   usb-asic\run_bfgminer_usb.bat
echo.
echo  Connection details:
echo    Pool URL : stratum+tcp://127.0.0.1:3334
echo    Worker   : %THR_ADDRESS%.worker1
echo    Password : x
echo.
echo  NOTE: HTTP 202 from the server = SUCCESS (block queued).
echo.
pause
goto MENU
