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
    echo  ERROR: Python 3 is not installed.
    echo  Download: https://www.python.org/downloads/
    echo  Enable "Add Python to PATH" during setup.
    echo.
    pause
    exit /b 1
)

:: ── THR address ─────────────────────────────────────────────────────────────
set THR_ADDRESS=%~1
if "%THR_ADDRESS%"=="" set THR_ADDRESS=YOUR_THR_ADDRESS
if "%THR_ADDRESS%"=="YOUR_THR_ADDRESS" (
    set /p THR_ADDRESS="Enter THR wallet address: "
)
if "%THR_ADDRESS%"=="" (
    echo ERROR: THR address required.
    pause
    exit /b 1
)

set THRONOS_API_URL=https://api.thronoschain.org

echo.
echo  Thronos CPU Miner
echo  Address : %THR_ADDRESS%
echo  Server  : %THRONOS_API_URL%
echo  Log     : ..\logs\cpu.log
echo  Press Ctrl+C to stop.
echo.

set PYTHONUNBUFFERED=1
%PYTHON% -u pow_miner_cpu.py --address %THR_ADDRESS% --api %THRONOS_API_URL% 2>&1 | powershell -NoProfile -NonInteractive -Command "$input | Tee-Object -FilePath '..\logs\cpu.log'"
if errorlevel 1 (
    echo.
    echo  Miner exited. Check ..\logs\cpu.log for details.
    echo  If Python packages are missing:
    echo    %PYTHON% -m pip install requests
    echo.
)
pause
