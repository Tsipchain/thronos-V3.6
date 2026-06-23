@echo off
title Thronos USB ASIC — CGMiner
cd /d "%~dp0"

set CGMINER=bin\cgminer.exe

if not exist "%CGMINER%" (
    echo.
    echo ============================================================
    echo  ERROR: cgminer.exe not found.
    echo.
    echo  Download CGMiner and place the .exe here:
    echo    %~dp0bin\cgminer.exe
    echo.
    echo  Download: https://github.com/ckolivas/cgminer/releases
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
echo  Thronos USB ASIC Miner — CGMiner
echo  Config : %~dp0cgminer.conf
echo.
echo  IMPORTANT: Stratum Proxy must be running in another window.
echo    Use start_here.bat option 2, or run:
echo      python ..\proxy\stratum_proxy.py
echo.
echo  Press Ctrl+C to stop.
echo ============================================================
echo.

%CGMINER% --sha256d -c cgminer.conf
set CGMINER_EXIT=%ERRORLEVEL%

echo.
echo ============================================================
echo  CGMiner stopped ^(exit code %CGMINER_EXIT%^).
echo  Press any key to close.
echo ============================================================
pause >nul
