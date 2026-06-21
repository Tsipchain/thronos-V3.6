@echo off
title Thronos Stratum Proxy

set THRONOS_SERVER=https://api.thronoschain.org
set STRATUM_PORT=3334
set STRATUM_PROXY_ADDRESS=YOUR_THR_ADDRESS

echo ============================================================
echo  Thronos Stratum Proxy
echo  Server : %THRONOS_SERVER%
echo  Port   : %STRATUM_PORT%
echo  Address: %STRATUM_PROXY_ADDRESS%
echo.
echo  Point your miner at: stratum+tcp://127.0.0.1:%STRATUM_PORT%
echo ============================================================
echo.

python stratum_proxy.py
pause
