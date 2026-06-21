@echo off
title Thronos CPU Miner

:: Set your THR address here or pass as argument
set THR_ADDRESS=%1
if "%THR_ADDRESS%"=="" (
    set /p THR_ADDRESS="Enter your THR wallet address: "
)

if "%THR_ADDRESS%"=="" (
    echo ERROR: THR address is required.
    pause
    exit /b 1
)

set THRONOS_API_URL=https://api.thronoschain.org

echo ===========================================
echo  Thronos CPU Miner
echo  Address: %THR_ADDRESS%
echo  Server : %THRONOS_API_URL%
echo ===========================================
echo.

python pow_miner_cpu.py --address %THR_ADDRESS% --api %THRONOS_API_URL%
if errorlevel 1 (
    echo.
    echo ERROR: Make sure Python and requests are installed.
    echo   pip install requests
)
pause
