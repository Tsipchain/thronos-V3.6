#!/bin/bash
set -e

# Ensure DATA_DIR exists (defaults to ./data if not set env var)
DATA_DIR=${DATA_DIR:-./data}
mkdir -p "$DATA_DIR/contracts"

echo "=== Starting Stratum engine on TCP port 3333 ==="
python stratum_engine.py &
STRATUM_PID=$!

echo "=== Starting MicroMiner demonstration ==="
python micro_miner.py &
MINER_PID=$!

echo "=== Starting Flask app on HTTP port ${PORT:-8000} ==="
# server.py is configured to read PORT env var
python server.py

echo "=== Shutting down background services ==="
kill $STRATUM_PID $MINER_PID || true