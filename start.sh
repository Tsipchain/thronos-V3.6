#!/bin/bash
set -e

# Ensure DATA_DIR exists (defaults to ./data if not set env var)
DATA_DIR=${DATA_DIR:-./data}
mkdir -p "$DATA_DIR/contracts"

# Reserve the public web port for the Flask app and keep Stratum separate
PORT=${PORT:-8000}
STRATUM_PORT=${STRATUM_PORT:-3333}
export PORT STRATUM_PORT

# Only start Stratum on master node (replicas are read-only)
NODE_ROLE=${NODE_ROLE:-master}
if [[ "$NODE_ROLE" == "master" ]]; then
  echo "=== Starting Stratum engine on TCP port ${STRATUM_PORT} ==="
  python3 stratum_engine.py &
  STRATUM_PID=$!
else
  echo "=== Skipping Stratum engine on $NODE_ROLE node (read-only) ==="
  STRATUM_PID=""
fi

MINER_PID=""
if [[ "${ENABLE_MICRO_MINER:-false}" == "true" ]]; then
  echo "=== Starting MicroMiner demonstration ==="
  python3 micro_miner.py &
  MINER_PID=$!
else
  echo "=== Skipping MicroMiner demonstration (set ENABLE_MICRO_MINER=true to enable) ==="
fi

echo "=== Starting Flask app on HTTP port ${PORT} ==="
# Use Gunicorn with proper lifecycle hooks for graceful scheduler shutdown
# NOTE: Using config file which sets workers=1 to avoid APScheduler job duplication
gunicorn -c gunicorn_config.py server:app

echo "=== Shutting down background services ==="
if [[ -n "$STRATUM_PID" && -n "$MINER_PID" ]]; then
  kill $STRATUM_PID $MINER_PID || true
elif [[ -n "$STRATUM_PID" ]]; then
  kill $STRATUM_PID || true
elif [[ -n "$MINER_PID" ]]; then
  kill $MINER_PID || true
fi
