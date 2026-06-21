@echo off
title Thronos USB ASIC — CGMiner

set CGMINER=bin\cgminer.exe

if not exist "%CGMINER%" (
    echo ============================================================
    echo  ERROR: cgminer.exe not found.
    echo.
    echo  Please download CGMiner and place it at:
    echo    %~dp0bin\cgminer.exe
    echo.
    echo  Download from: https://github.com/ckolivas/cgminer
    echo ============================================================
    pause
    exit /b 1
)

echo ============================================================
echo  Thronos USB ASIC Miner (CGMiner)
echo  Config: cgminer.conf
echo  Make sure stratum_proxy.py is running first!
echo    Start with: python ..\proxy\stratum_proxy.py
echo ============================================================
echo.

%CGMINER% --sha256d -c cgminer.conf
pause
