@echo off
title Thronos Dual Miner Launcher

echo ===================================================
echo    Thronos Chain - Dual Mining Starter
echo ===================================================
echo.
echo 1. Starting Thronos Stratum Proxy (bridges to HTTP API)...
echo    (Make sure you have configured stratum_proxy.py with your server URL)
echo.

start "Thronos Proxy" cmd /k "python stratum_proxy.py"

echo Waiting 5 seconds for proxy to initialize...
timeout /t 5 /nobreak >nul

echo.
echo 2. Starting CGMiner (Dual Mining Mode)...
echo    Primary: Thronos (via Local Proxy)
echo    Secondary: NiceHash (SHA256)
echo.

:: Assuming cgminer.exe is in the same folder or in PATH
:: You can download cgminer 4.10+ for SHA256 support
if exist cgminer.exe (
    cgminer.exe --config cgminer.conf
) else (
    echo ERROR: cgminer.exe not found in this directory!
    echo Please download cgminer and place it here.
    pause
)

pause