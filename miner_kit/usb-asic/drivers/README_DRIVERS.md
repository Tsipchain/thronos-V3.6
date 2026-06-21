# USB ASIC Drivers — Windows Setup

## Why you need this

Windows does not include drivers for USB Bitcoin mining hardware by default.
You need to install a WinUSB-compatible driver so CGMiner / BFGMiner can
detect your device.

## Recommended tool: Zadig

1. Download Zadig from: https://zadig.akeo.ie
2. Plug in your USB ASIC miner
3. Open Zadig
4. Options → List All Devices
5. Select your miner from the dropdown (e.g. "CP2102 USB to UART Bridge")
6. Select driver: **WinUSB** (or libusb-win32)
7. Click "Replace Driver"

## Common USB ASIC chip drivers

| Chip | Miner hardware | Driver |
|------|---------------|--------|
| CP210x | GekkoScience Compac, most clones | WinUSB via Zadig |
| CH340 | Some Chinese miners | CH340 driver (from manufacturer) |
| FTDI | Older Block Erupters | FTDI VCP driver |

## Linux

On Linux no extra drivers are needed. Connect the device and it appears
as `/dev/ttyUSB0` or `/dev/ttyACM0`. Add your user to the `dialout` group:

```bash
sudo usermod -aG dialout $USER
# Log out and back in, then:
cgminer --sha256d -o stratum+tcp://127.0.0.1:3334 -u YOUR_THR_ADDRESS -p x
```

## macOS

Install the CP210x driver from Silicon Labs:
https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers

Then use cgminer built from source (Homebrew):
```bash
brew install cgminer
cgminer --sha256d -o stratum+tcp://127.0.0.1:3334 -u YOUR_THR_ADDRESS -p x
```
