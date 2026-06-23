# USB ASIC Mining — Thronos Network

## Supported hardware

- GekkoScience Compac F / 2Pac / NewPac
- Antminer U1 / U2 / U3 (USB)
- Block Erupter (original)
- Any USB SHA-256 ASIC recognised by CGMiner or BFGMiner

## Required software (NOT bundled)

Download and place the binary **and all DLLs from the archive** in `usb-asic\bin\`:

| Software | URL | Note |
|----------|-----|------|
| cgminer | https://github.com/ckolivas/cgminer/releases | Windows: cgminer.exe + DLLs |
| bfgminer | https://bfgminer.org | Windows: bfgminer.exe + DLLs |

> **Important:** Always use a complete Windows build that includes all required `.dll` files.
> If only `cgminer.exe` is copied without its DLLs, it will exit with error `-1073741515`
> (STATUS_DLL_NOT_FOUND). Copy the entire contents of the bin folder from the cgminer zip.

After downloading, your folder should look like:
```
usb-asic\
  bin\
    cgminer.exe       ← place here
    libcurl.dll       ← copy all .dll files from the cgminer zip
    jansson.dll
    ...               ← (names vary by build)
    bfgminer.exe      ← optional alternative
  cgminer.conf
  bfgminer.conf
  run_cgminer_usb.bat
  run_bfgminer_usb.bat
  drivers\
    README_DRIVERS.md
```

## Quick start (Windows)

### Step 1 — Install the USB driver

USB ASICs need a WinUSB-compatible driver. Use **Zadig** to install one:

1. Download Zadig from https://zadig.akeo.ie/
2. Plug in your USB ASIC
3. In Zadig: select your device → choose **WinUSB** → click "Install Driver"
4. See `drivers\README_DRIVERS.md` for device-specific notes

### Step 2 — Start the Stratum Proxy (keep this window open)

The Stratum Proxy translates the standard stratum protocol into Thronos API
calls. **It must be running before you start cgminer.**

Go back to `start_here.bat` and choose **option 2 — Stratum Proxy**.

Or run directly:
```
python ..\proxy\stratum_proxy.py
```

### Step 3 — Place cgminer in bin\ (with DLLs)

Copy `cgminer.exe` **and all .dll files** from your cgminer download into:
```
usb-asic\bin\
```

If cgminer exits immediately with a numeric error like `-1073741515`, install
the Visual C++ Redistributable or use a build that bundles its own DLLs:
- VC++ Redist 2015-2022 x64: https://aka.ms/vs/17/release/vc_redist.x64.exe

### Step 4 — Run the launcher

Double-click `run_cgminer_usb.bat`.

The launcher will:
- Verify `cgminer.exe` and `cgminer.conf` exist
- Run `cgminer.exe --version` to detect DLL/runtime problems before mining
- Print a clear error and fix instructions if anything is missing
- Start mining if all checks pass

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ERROR: cgminer.exe not found` | Binary not placed in bin\ | Copy cgminer.exe (and DLLs) to `usb-asic\bin\` |
| Exit code `-1073741515` | Missing DLL or VC++ runtime | Install VC++ Redist 2015-2022 x64, or use a build that bundles DLLs |
| Exit code `-1073741701` | Wrong architecture (32-bit on 64-bit) | Download the x64 build |
| cgminer says "No devices found" | USB driver not installed | Run Zadig → install WinUSB for your ASIC |
| cgminer connects but no shares | Stratum Proxy not running | Start `start_here.bat` option 2 first |
| HTTP 202 in proxy window | Normal — means block accepted | Keep mining |

## Quick start (Linux)

```bash
# Install cgminer
sudo apt-get install cgminer

# Start the stratum proxy
python3 ../proxy/stratum_proxy.py &

# Run cgminer
cgminer --sha256d -o stratum+tcp://127.0.0.1:3334 -u YOUR_THR_ADDRESS -p x
```

## Connection details

```
Protocol : stratum+tcp
Host     : 127.0.0.1   (via local Stratum Proxy)
Port     : 3334
Username : YOUR_THR_ADDRESS.worker1
Password : x
```

> **Note:** HTTP 202 responses in the proxy window mean the block was accepted
> and queued. This is success, not an error.
