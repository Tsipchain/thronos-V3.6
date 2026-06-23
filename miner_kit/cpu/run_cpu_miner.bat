@echo off
title Thronos CPU Miner
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
set THR_ADDRESS=%~1
if "%THR_ADDRESS%"=="" set THR_ADDRESS=YOUR_THR_ADDRESS
if /I "%THR_ADDRESS:~0,3%"=="THR" goto CPU_ADDR_VALID
set /p THR_ADDRESS="Enter THR wallet address: "
:CPU_ADDR_VALID
if "%THR_ADDRESS%"=="" (
    echo ERROR: THR address required.
    pause
    exit /b 1
)

set THRONOS_API_URL=https://api.thronoschain.org

echo.
echo ============================================================
echo  Thronos CPU Miner
echo  Address : %THR_ADDRESS%
echo  Server  : %THRONOS_API_URL%
echo  Press Ctrl+C to stop.
echo ============================================================
echo.

set PYTHONUNBUFFERED=1
%PYTHON% -u pow_miner_cpu.py --address %THR_ADDRESS% --api %THRONOS_API_URL%
set MINER_EXIT=%ERRORLEVEL%

echo.
echo ============================================================
echo  Miner stopped ^(exit code %MINER_EXIT%^).
if %MINER_EXIT% NEQ 0 (
    echo.
    echo  If you see "No module named 'requests'":
    echo    Run:  %PYTHON% -m pip install requests
    echo    Then re-run this file.
    echo.
)
echo  Press any key to close.
echo ============================================================
pause >nul
