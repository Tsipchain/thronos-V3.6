@echo off
title Thronos GPU Miner (Example)

:: ── EDIT THESE ────────────────────────────────────────────────────────
set THR_ADDRESS=YOUR_THR_ADDRESS
set POOL_HOST=127.0.0.1
set POOL_PORT=3334

:: Path to your GPU miner binary — download separately, NOT included
set LOLMINER=lolMiner.exe
:: ─────────────────────────────────────────────────────────────────────

echo ===========================================
echo  Thronos GPU Miner (via local proxy)
echo  Address : %THR_ADDRESS%
echo  Pool    : %POOL_HOST%:%POOL_PORT%
echo ===========================================
echo.
echo NOTE: This script requires the stratum proxy to be running.
echo       Start it first: python ..\proxy\stratum_proxy.py
echo.

if not exist "%LOLMINER%" (
    echo ERROR: %LOLMINER% not found.
    echo Please download lolMiner from: https://github.com/Lolliedieb/lolMiner-releases
    echo Place lolMiner.exe in the gpu\ folder, then re-run this script.
    pause
    exit /b 1
)

%LOLMINER% --algo SHA256 --pool stratum+tcp://%POOL_HOST%:%POOL_PORT% --user %THR_ADDRESS% --pass x
pause
