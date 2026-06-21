@echo off
title Thronos USB ASIC — BFGMiner

set BFGMINER=bin\bfgminer.exe

if not exist "%BFGMINER%" (
    echo ============================================================
    echo  ERROR: bfgminer.exe not found.
    echo.
    echo  Please download BFGMiner and place it at:
    echo    %~dp0bin\bfgminer.exe
    echo.
    echo  Download from: https://bfgminer.org
    echo ============================================================
    pause
    exit /b 1
)

echo ============================================================
echo  Thronos USB ASIC Miner (BFGMiner)
echo  Config: bfgminer.conf
echo  Make sure stratum_proxy.py is running first!
echo    Start with: python ..\proxy\stratum_proxy.py
echo ============================================================
echo.

%BFGMINER% --sha256d -c bfgminer.conf
pause
