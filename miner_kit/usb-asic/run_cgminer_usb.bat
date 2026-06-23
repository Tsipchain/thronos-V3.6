@echo off
title Thronos USB ASIC — CGMiner
cd /d "%~dp0"

set CGMINER=bin\cgminer.exe
set CGMINER_CONF=cgminer.conf

:: ── Pre-flight: binary ───────────────────────────────────────────────────────
if not exist "%CGMINER%" (
    echo.
    echo ============================================================
    echo  ERROR: cgminer.exe not found.
    echo.
    echo  Place a complete Windows build here:
    echo    %~dp0bin\cgminer.exe
    echo.
    echo  The bin\ folder must also contain any .dll files that
    echo  came with your cgminer download.
    echo.
    echo  Download: https://github.com/ckolivas/cgminer/releases
    echo.
    echo  IMPORTANT: Start the Stratum Proxy first:
    echo    Go back to start_here.bat and choose option 2.
    echo ============================================================
    echo.
    echo  Press any key to close.
    pause >nul
    exit /b 1
)

:: ── Pre-flight: config ───────────────────────────────────────────────────────
if not exist "%CGMINER_CONF%" (
    echo.
    echo ============================================================
    echo  ERROR: cgminer.conf not found.
    echo.
    echo  Expected: %~dp0cgminer.conf
    echo  Make sure you extracted the full miner kit zip.
    echo ============================================================
    echo.
    echo  Press any key to close.
    pause >nul
    exit /b 1
)

:: ── DLL / runtime check via --version ────────────────────────────────────────
echo   Checking cgminer runtime...
"%CGMINER%" --version >nul 2>&1
set VER_EXIT=%ERRORLEVEL%

if %VER_EXIT% EQU -1073741515 goto DLL_ERROR
if %VER_EXIT% EQU  3221225781 goto DLL_ERROR
if %VER_EXIT% EQU -1073741701 goto ARCH_ERROR

:: ── Launch ───────────────────────────────────────────────────────────────────
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

%CGMINER% -c cgminer.conf
set CGMINER_EXIT=%ERRORLEVEL%

echo.
echo ============================================================
if %CGMINER_EXIT% EQU -1073741515 goto DLL_ERROR_STOP
if %CGMINER_EXIT% EQU  3221225781 goto DLL_ERROR_STOP
if %CGMINER_EXIT% EQU -1073741701 goto ARCH_ERROR_STOP
echo  CGMiner stopped ^(exit code %CGMINER_EXIT%^).
echo  Press any key to close.
echo ============================================================
pause >nul
exit /b %CGMINER_EXIT%

:DLL_ERROR_STOP
echo  CGMiner stopped: missing DLL / Visual C++ runtime.
goto DLL_FIX

:DLL_ERROR
echo.
echo ============================================================
echo  ERROR: cgminer.exe failed to start.

:DLL_FIX
echo.
echo  Missing DLL / Visual C++ runtime dependency.
echo.
echo  Fix 1 — Install Visual C++ Redistributable 2015-2022 x64:
echo    https://aka.ms/vs/17/release/vc_redist.x64.exe
echo.
echo  Fix 2 — Use a cgminer build that bundles its own DLLs:
echo    Place cgminer.exe AND all .dll files from the archive
echo    into: %~dp0bin\
echo ============================================================
echo.
echo  Press any key to close.
pause >nul
exit /b 1

:ARCH_ERROR_STOP
echo  CGMiner stopped: architecture mismatch.
goto ARCH_FIX

:ARCH_ERROR
echo.
echo ============================================================
echo  ERROR: cgminer.exe cannot run.

:ARCH_FIX
echo.
echo  Architecture mismatch — 32-bit binary on 64-bit Windows,
echo  or vice versa.
echo  Download the x64 Windows build of cgminer.
echo ============================================================
echo.
echo  Press any key to close.
pause >nul
exit /b 1
