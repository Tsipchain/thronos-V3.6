#!/bin/bash
# start_serv3r.sh — Startup script for the Thronos AI Core lightweight node
# Deployed at: ai.thronoschain.org (separate Render service)
#
# Environment variables required:
#   THRONOS_AI_MODE      anthropic (default) | openai
#   ANTHROPIC_API_KEY    required when mode=anthropic
#   APP_AI_KEY           shared secret with verifyid (X-Internal-Key / X-API-Key)
#   PORT                 set by Render automatically
#
# Optional:
#   AI_CORE_MODEL        override model (default: claude-3-5-sonnet-20241022)
#   OPENAI_API_KEY       required when mode=openai
#   APP_AI_BASE_URL      optional OpenAI-compatible base URL

set -e

# Activate virtual-env if available (Nixpacks / Render)
if [[ -f /opt/venv/bin/activate ]]; then
  source /opt/venv/bin/activate
fi

PORT=${PORT:-8001}
export PORT

echo "=== Thronos AI Core (serv3r) starting on port ${PORT} ==="
echo "=== AI Mode: ${THRONOS_AI_MODE:-anthropic} ==="

# Lightweight app: 2 workers, 4 threads each is plenty for an AI proxy
gunicorn serv3r:app \
  --bind "0.0.0.0:${PORT}" \
  --workers 2 \
  --threads 4 \
  --worker-class gthread \
  --timeout 120 \
  --graceful-timeout 30 \
  --access-logfile - \
  --error-logfile - \
  --log-level info
