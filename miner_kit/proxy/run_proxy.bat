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
    echo  ERROR: Python 3 is not installed or not on PATH.
    echo  Download: https://www.python.org/downloads/
    echo  During install, check "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

:: ── THR address ─────────────────────────────────────────────────────────────
set STRATUM_PROXY_ADDRESS=YOUR_THR_ADDRESS
if not "%~1"=="" set STRATUM_PROXY_ADDRESS=%~1
if /I "%STRATUM_PROXY_ADDRESS:~0,3%"=="THR" goto PROXY_ADDR_VALID
set /p STRATUM_PROXY_ADDRESS="Enter THR wallet address: "
:PROXY_ADDR_VALID
if "%STRATUM_PROXY_ADDRESS%"=="" (
    echo ERROR: THR address required.
    pause
    exit /b 1
)

set THRONOS_SERVER=https://api.thronoschain.org
set STRATUM_PORT=3334

echo.
echo ============================================================
echo  Thronos Stratum Proxy
echo  Address : %STRATUM_PROXY_ADDRESS%
echo  Server  : %THRONOS_SERVER%
echo  Port    : %STRATUM_PORT%
echo.
echo  Point your miner at: stratum+tcp://127.0.0.1:%STRATUM_PORT%
echo  Worker : %STRATUM_PROXY_ADDRESS%.worker1
echo  Password: x
echo.
echo  NOTE: HTTP 202 = block accepted/queued. This is success.
echo  Press Ctrl+C to stop.
echo ============================================================
echo.

set PYTHONUNBUFFERED=1
%PYTHON% -u stratum_proxy.py
set PROXY_EXIT=%ERRORLEVEL%

echo.
echo ============================================================
echo  Proxy stopped ^(exit code %PROXY_EXIT%^).
echo  Press any key to close.
echo ============================================================
pause >nul
