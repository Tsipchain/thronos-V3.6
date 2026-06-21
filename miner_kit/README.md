# Thronos Miner Kit

Complete mining kit for the Thronos Network (SHA-256 PoW).

## What is included

| Folder | Contents | Status |
|--------|----------|--------|
| `cpu/` | Python HTTP miner — runs on any CPU | Ready |
| `gpu/` | Config templates for lolMiner, BzMiner, SRBMiner | Experimental (requires your own binary) |
| `usb-asic/` | CGMiner / BFGMiner configs for USB SHA-256 sticks | Ready (requires cgminer/bfgminer binary) |
| `external-asic/` | Pool config examples for Antminer, Whatsminer, Avalon | Ready |
| `proxy/` | Stratum proxy — bridges external miners to the Thronos HTTP API | Ready |
| `examples/` | Sample env file and pool config | Reference |

## Quick start

**CPU mining (fastest start):**
```
pip install requests
python cpu/pow_miner_cpu.py --address YOUR_THR_ADDRESS --api https://api.thronoschain.org
```

**USB ASIC / external ASIC:**
```
# 1. Start the stratum proxy
python proxy/stratum_proxy.py

# 2. Point your miner at 127.0.0.1:3334
# See usb-asic/ or external-asic/ for device-specific instructions
```

## Important notes

- No private keys are stored in this kit. Mining uses your public THR address only.
- `cgminer.exe` and `bfgminer.exe` are NOT bundled. See `usb-asic/README_USB_ASIC.md` for download links.
- GPU miner binaries (lolMiner, BzMiner, SRBMiner) are NOT bundled. See `gpu/README_GPU.md`.
- External ASIC firmware is NOT modified. Pool URL + worker config only.

## Network endpoints

| Endpoint | Purpose |
|----------|---------|
| `https://api.thronoschain.org/api/miner/work` | Fetch mining job |
| `https://api.thronoschain.org/api/miner/submit` | Submit mined block |
| Stratum proxy local: `stratum+tcp://127.0.0.1:3334` | For ASIC / GPU miners |

## Server response codes

| Code | Meaning |
|------|---------|
| 200 | Block accepted immediately |
| 202 | Block queued for processing (success — do not retry) |
| 409 | Stale work — fetch new job and retry |
| 503 | Node busy — retry after a moment |
