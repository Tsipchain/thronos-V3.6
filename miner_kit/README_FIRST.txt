Thronos Miner Kit — README FIRST
=================================

STEP 1: Extract the ZIP
-----------------------
Extract all files to a folder you can easily find, e.g.:
  C:\Users\YourName\Downloads\thronos_miner\

Do NOT run files directly from inside the ZIP.

STEP 2: Run start_here.bat
---------------------------
Double-click start_here.bat (or run it from a Command Prompt).
It will show a menu where you can choose your mining method.

REQUIREMENTS
------------
  Python 3.8+  — https://www.python.org/downloads/
                 During install: check "Add Python to PATH"
  requests     — installed automatically by start_here.bat
                 or manually: pip install requests

WHAT IS IN THIS KIT
-------------------
  start_here.bat          Main launcher (start here on Windows)
  README_FIRST.txt        This file
  QUICKSTART_WINDOWS.md   Detailed Windows guide
  QUICKSTART_LINUX.md     Linux/macOS guide

  cpu/                    CPU miner
    pow_miner_cpu.py      Python CPU miner script
    run_cpu_miner.bat     Direct Windows launcher for CPU miner

  proxy/                  Stratum bridge proxy (for ASIC/GPU miners)
    stratum_proxy.py      Python Stratum-to-HTTP bridge
    run_proxy.bat         Direct Windows launcher for proxy

  usb-asic/               USB ASIC (GekkoScience, Antminer USB, etc.)
    README_USB_ASIC.md    Setup instructions
    cgminer.conf          Pre-filled config (requires cgminer.exe)
    bfgminer.conf         Pre-filled config (requires bfgminer.exe)
    drivers/              Driver installation guide

  external-asic/          External ASIC (Antminer S19, Whatsminer, etc.)
    Pool configs and setup examples

  gpu/                    GPU mining (experimental)
    Config templates for lolMiner, BzMiner, SRBMiner

  logs/                   Log files created when miners run

MINING METHODS
--------------
  CPU     — Run start_here.bat, choose option 1.
            No extra hardware needed.

  USB ASIC — Requires cgminer.exe or bfgminer.exe (NOT included).
              Run the Stratum Proxy first, then connect your ASIC.

  External ASIC — Set pool URL in your ASIC web UI:
                  stratum+tcp://api.thronoschain.org:3334
                  Worker: YOUR_THR_ADDRESS.worker1   Password: x

  GPU     — Experimental. See gpu/README_GPU.md.

ABOUT HTTP 202 RESPONSES
------------------------
When you submit a mined block, the server may return HTTP 202.
This is NOT an error. It means your block was accepted and is
queued for processing. The miner scripts handle this correctly.

SECURITY
--------
This kit does NOT require your private key, seed phrase, or
mnemonic. Mining only uses your public THR wallet address.
Never enter your seed phrase or private key anywhere in this kit.

SUPPORT
-------
API:    https://api.thronoschain.org
Docs:   https://api.thronoschain.org/docs
Wallet: https://api.thronoschain.org/
