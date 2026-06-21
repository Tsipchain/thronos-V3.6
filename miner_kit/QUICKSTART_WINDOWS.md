# Thronos Miner — Windows Quick Start

## 1. CPU Mining (no extra software needed)

```
pip install requests
python cpu\pow_miner_cpu.py --address YOUR_THR_ADDRESS
```

## 2. USB ASIC Mining (GekkoScience, Antminer U3, etc.)

1. Install CP210x / WinUSB driver via Zadig (see `usb-asic\drivers\README_DRIVERS.md`)
2. Place `cgminer.exe` in `usb-asic\bin\cgminer.exe`
3. Start the proxy:
   ```
   python proxy\stratum_proxy.py
   ```
4. In a new window:
   ```
   usb-asic\run_cgminer_usb.bat
   ```

## 3. External ASIC (Antminer, Whatsminer, Avalon)

Edit your miner's web UI pool settings:
- Pool URL: `stratum+tcp://api.thronoschain.org:3334`
- Worker: `YOUR_THR_ADDRESS.worker1`
- Password: `x`

See `external-asic\` for model-specific examples.

## 4. GPU Mining (experimental)

1. Install a supported GPU miner binary (lolMiner, BzMiner, or SRBMiner — see `gpu\README_GPU.md`)
2. Start the proxy:
   ```
   python proxy\stratum_proxy.py
   ```
3. Run the example:
   ```
   gpu\run_gpu_example.bat
   ```

## Troubleshooting

- **cgminer.exe not found**: Place the binary in `usb-asic\bin\`
- **Connection refused**: Make sure `stratum_proxy.py` is running first
- **Submission failed**: Verify your THR address starts with `THR`
- **HTTP 202 responses are SUCCESS** — block is queued for processing
