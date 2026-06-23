@echo off
title Thronos USB ASIC — BFGMiner
cd /d "%~dp0"

set BFGMINER=bin\bfgminer.exe

if not exist "%BFGMINER%" (
    echo.
    echo ============================================================
    echo  ERROR: bfgminer.exe not found.
    echo.
    echo  Download BFGMiner and place the .exe here:
    echo    %~dp0bin\bfgminer.exe
    echo.
    echo  Download: https://bfgminer.org/
    echo.
    echo  Also make sure the Stratum Proxy is running first:
    echo    Go back to start_here.bat and choose option 2.
    echo ============================================================
    echo.
    echo  Press any key to close.
    pause >nul
    exit /b 1
)

echo.
echo ============================================================
echo  Thronos USB ASIC Miner — BFGMiner
echo  Config : %~dp0bfgminer.conf
echo.
echo  IMPORTANT: Stratum Proxy must be running in another window.
echo    Use start_here.bat option 2, or run:
echo      python ..\proxy\stratum_proxy.py
echo.
echo  Press Ctrl+C to stop.
echo ============================================================
echo.

%BFGMINER% --sha256d -c bfgminer.conf
set BFGMINER_EXIT=%ERRORLEVEL%

echo.
echo ============================================================
echo  BFGMiner stopped ^(exit code %BFGMINER_EXIT%^).
echo  Press any key to close.
echo ============================================================
pause >nul
