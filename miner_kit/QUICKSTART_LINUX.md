# Thronos Miner — Linux / macOS Quick Start

## 1. CPU Mining

```bash
pip3 install requests
python3 cpu/pow_miner_cpu.py --address YOUR_THR_ADDRESS --api https://api.thronoschain.org
```

## 2. USB ASIC Mining (GekkoScience, Antminer USB, etc.)

```bash
# Install cgminer (example: Ubuntu/Debian)
sudo apt-get install cgminer

# Or build from source:
# https://github.com/ckolivas/cgminer

# Start the stratum proxy
python3 proxy/stratum_proxy.py &

# Run cgminer against local proxy
cgminer --sha256d -o stratum+tcp://127.0.0.1:3334 -u YOUR_THR_ADDRESS -p x
```

Or use the bundled config:
```bash
cgminer -c usb-asic/cgminer.conf
```

## 3. External ASIC (Antminer, Whatsminer, Avalon)

Configure pool settings in your miner's web UI:
- Pool URL: `stratum+tcp://api.thronoschain.org:3334`
- Worker: `YOUR_THR_ADDRESS.worker1`
- Password: `x`

## 4. GPU Mining (experimental)

```bash
# Start proxy
python3 proxy/stratum_proxy.py &

# Example: lolMiner (download from https://github.com/Lolliedieb/lolMiner-releases)
./lolMiner --algo SHA256 --pool stratum+tcp://127.0.0.1:3334 --user YOUR_THR_ADDRESS --pass x
```

See `gpu/README_GPU.md` for all supported GPU miners.

## Environment variables

```bash
export THR_ADDRESS=YOUR_THR_ADDRESS
export THRONOS_API_URL=https://api.thronoschain.org
export STRATUM_PORT=3334
python3 cpu/pow_miner_cpu.py
```

## Note on HTTP 202

The server returns **HTTP 202** when your block is queued for async processing. This is a **success** — do not retry.
