@echo off
title Thronos Stratum Proxy
cd /d "%~dp0"

if not exist "..\logs" mkdir "..\logs"

:: ── Python detection ────────────────────────────────────────────────────────
set PYTHON=
py -3 --version >nul 2>&1 && set PYTHON=py -3
if "%PYTHON%"=="" python --version >nul 2>&1 && set PYTHON=python
if "%PYTHON%"=="" (
    echo.
    echo  ERROR: Python 3 is not installed.
    echo  Download: https://www.python.org/downloads/
    echo  Enable "Add Python to PATH" during setup.
    echo.
    pause
    exit /b 1
)

:: ── THR address ─────────────────────────────────────────────────────────────
set STRATUM_PROXY_ADDRESS=YOUR_THR_ADDRESS
if "%STRATUM_PROXY_ADDRESS%"=="YOUR_THR_ADDRESS" (
    if not "%~1"=="" (
        set STRATUM_PROXY_ADDRESS=%~1
    ) else (
        set /p STRATUM_PROXY_ADDRESS="Enter THR wallet address: "
    )
)
if "%STRATUM_PROXY_ADDRESS%"=="" (
    echo ERROR: THR address required.
    pause
    exit /b 1
)

set THRONOS_SERVER=https://api.thronoschain.org
set STRATUM_PORT=3334

echo.
echo  Thronos Stratum Proxy
echo  Address : %STRATUM_PROXY_ADDRESS%
echo  Server  : %THRONOS_SERVER%
echo  Port    : %STRATUM_PORT%
echo  Log     : ..\logs\proxy.log
echo.
echo  Point your miner at: stratum+tcp://127.0.0.1:%STRATUM_PORT%
echo  Worker name: %STRATUM_PROXY_ADDRESS%.worker1
echo  Password:    x
echo.
echo  NOTE: HTTP 202 = accepted/queued. This is success, not an error.
echo  Press Ctrl+C to stop.
echo.

set PYTHONUNBUFFERED=1
%PYTHON% -u stratum_proxy.py 2>&1 | powershell -NoProfile -NonInteractive -Command "$input | Tee-Object -FilePath '..\logs\proxy.log'"
if errorlevel 1 (
    echo.
    echo  Proxy exited. Check ..\logs\proxy.log for details.
    echo.
)
pause
