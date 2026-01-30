## ASIC Mining (Stratum)

Thronos supports classic Stratum flows for ASIC miners:

- **subscribe**
- **notify**
- **submit**

This repo includes a Stratum proxy in `miner_kit/stratum_proxy.py` that bridges
ASIC miners to the Thronos node.

### Quick start

1. Set the server and optional proxy address:

```bash
export THRONOS_SERVER="https://thrchain.up.railway.app"
export STRATUM_PROXY_ADDRESS="THR_YOUR_ADDRESS"
```

2. Run the proxy:

```bash
python3 miner_kit/stratum_proxy.py
```

3. Point your ASIC to the proxy host/port (default `3334`).

### Sample config

See `cgminer.conf.example` for a minimal configuration template.
