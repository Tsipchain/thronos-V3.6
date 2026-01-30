## CPU Mining (HTTP)

Thronos provides a simple HTTP mining contract for CPU (and optional GPU) miners:

- `GET /api/miner/work` → returns `job_id`, `last_hash`, `target`, `height`, etc.
- `POST /api/miner/submit` → submit `nonce`, `pow_hash`, `address` (and optional `job_id`).

### Python miner

Use the built-in miner:

```bash
export THRONOS_SERVER="https://thrchain.up.railway.app"
python3 miner_kit/pow_miner_cpu.py THR_YOUR_ADDRESS
```

The script will request work, mine locally, and submit over HTTP.
