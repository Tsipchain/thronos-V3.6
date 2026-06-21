# USB ASIC Mining — Thronos Network

## Supported hardware

- GekkoScience Compac F / 2Pac / NewPac
- Antminer U1 / U2 / U3 (USB)
- Block Erupter (original)
- Any USB SHA-256 ASIC recognised by CGMiner or BFGMiner

## Required software (NOT bundled)

Download and place the binary in `usb-asic\bin\`:

| Software | URL | Note |
|----------|-----|------|
| cgminer | https://github.com/ckolivas/cgminer | Windows: cgminer.exe |
| bfgminer | https://bfgminer.org | Windows: bfgminer.exe |

After downloading, your folder should look like:
```
usb-asic\
  bin\
    cgminer.exe     ← place here
    bfgminer.exe    ← optional alternative
  cgminer.conf
  bfgminer.conf
  run_cgminer_usb.bat
  run_bfgminer_usb.bat
  drivers\
    README_DRIVERS.md
```

## Quick start (Windows)

1. Install USB drivers (see `drivers\README_DRIVERS.md`)
2. Start the stratum proxy in another window:
   ```
   python ..\proxy\stratum_proxy.py
   ```
3. Edit `cgminer.conf` — set your THR address in the `"user"` field
4. Double-click `run_cgminer_usb.bat`

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
Host     : 127.0.0.1   (via local proxy)
Port     : 3334
Username : YOUR_THR_ADDRESS
Password : x
```
