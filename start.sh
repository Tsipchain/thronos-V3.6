#!/bin/bash
set -e

# Activate the Nixpacks virtual-env so gunicorn & all pip packages are on PATH.
if [[ -f /opt/venv/bin/activate ]]; then
  source /opt/venv/bin/activate
fi

# Ensure DATA_DIR exists (defaults to ./data if not set env var)
DATA_DIR=${DATA_DIR:-./data}
mkdir -p "$DATA_DIR/contracts"

# Reserve the public web port for the Flask app and keep Stratum separate
PORT=${PORT:-8000}
STRATUM_PORT=${STRATUM_PORT:-3334}
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

PYTHEIA_PID=""
if [[ "${PYTHEIA_STANDALONE:-false}" == "true" ]]; then
  echo "=== Starting PYTHEIA Worker (standalone health monitor) ==="
  mkdir -p logs data
  python3 pytheia_worker.py &
  PYTHEIA_PID=$!
else
  echo "=== PYTHEIA Worker will run via APScheduler on master node ==="
fi

echo "=== Starting Flask app on HTTP port ${PORT} (server_ext:app) ==="
# server_ext:app wraps server:app and registers additional blueprints (L2E EDU etc.)
gunicorn -c gunicorn_config.py server_ext:app

echo "=== Shutting down background services ==="
for pid in $STRATUM_PID $MINER_PID $PYTHEIA_PID; do
  if [[ -n "$pid" ]]; then
    kill "$pid" 2>/dev/null || true
  fi
done
