#!/bin/bash
set -e

# Ensure DATA_DIR exists (defaults to ./data if not set env var)
DATA_DIR=${DATA_DIR:-./data}
mkdir -p "$DATA_DIR/contracts"

# Reserve the public web port for the Flask app and keep Stratum separate
PORT=${PORT:-8000}
STRATUM_PORT=${STRATUM_PORT:-3333}
export PORT STRATUM_PORT

echo "=== Starting Stratum engine on TCP port ${STRATUM_PORT} ==="
python3 stratum_engine.py &
STRATUM_PID=$!

echo "=== Starting MicroMiner demonstration ==="
python3 micro_miner.py &
MINER_PID=$!

echo "=== Starting Flask app on HTTP port ${PORT} ==="
# server.py is configured to read PORT env var
python3 server.py

echo "=== Shutting down background services ==="
kill $STRATUM_PID $MINER_PID || true
