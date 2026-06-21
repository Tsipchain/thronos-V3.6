# GPU Mining — Thronos Network

## Status: Experimental (proxy/local mode)

GPU mining on Thronos requires:
1. A GPU miner binary that supports Stratum (not included — download separately)
2. The `proxy/stratum_proxy.py` running locally to bridge Stratum → Thronos HTTP API

No GPU binaries are bundled in this kit.

## Supported GPU miners

| Miner | Algorithm | Download |
|-------|-----------|----------|
| lolMiner | SHA-256 | https://github.com/Lolliedieb/lolMiner-releases |
| BzMiner | SHA-256 | https://www.bzminer.com |
| SRBMiner-MULTI | SHA-256 | https://github.com/doktor83/SRBMiner-Multi |

## How to connect your GPU miner

1. Start the stratum proxy:
   ```
   python3 ../proxy/stratum_proxy.py
   ```
   The proxy listens on `127.0.0.1:3334` by default.

2. Point your GPU miner at the local proxy:
   ```
   POOL_HOST=127.0.0.1
   POOL_PORT=3334
   WALLET=YOUR_THR_ADDRESS
   PASSWORD=x
   ```

## Config templates in this folder

| File | Miner |
|------|-------|
| `example_lolminer_config.txt` | lolMiner command line |
| `example_bzminer_config.txt` | BzMiner config |
| `example_srbminer_config.txt` | SRBMiner config |
| `run_gpu_example.bat` | Windows launcher (edit binary path first) |

## Note on public stratum endpoint

If a public stratum port is available for direct ASIC/GPU connections without the local proxy, it will be listed at:
  `https://api.thronoschain.org/api/miner-kit`

Until a public stratum server is announced, use the local `stratum_proxy.py` to bridge your GPU miner.
