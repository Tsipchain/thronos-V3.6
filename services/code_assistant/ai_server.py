"""Thronos AI Server — standalone service for ai.thronoschain.org

This is the dedicated AI endpoint, separate from the blockchain core
(api.thronoschain.org). It serves:
  - Code Assistant API (MCP tools, sessions, agentic coding)
  - AI chat/completion endpoints (routed to Ollama on Railway GPU)
  - Model management (list, pull, health)

Deploy on Render as thr-ai-core, pointing OLLAMA_BASE_URL to the
Railway GPU service where Ollama runs.

Usage:
    gunicorn services.code_assistant.ai_server:app --bind 0.0.0.0:$PORT
    # or
    python3 -m services.code_assistant.ai_server
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from flask import Flask, jsonify, request
from flask_cors import CORS

# Ensure project root is on path so imports work
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from services.code_assistant.api_routes import code_assistant_bp
from ai.providers import ollama_helper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("thronos-ai")

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Register Code Assistant blueprint
app.register_blueprint(code_assistant_bp, url_prefix="/api/code-assistant")


# ── Core AI endpoints ────────────────────────────────────────────────────────

@app.route("/")
def index():
    return jsonify({
        "service": "Thronos AI",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "chat": "/api/ai/chat",
            "models": "/api/ai/models",
            "code_assistant": "/api/code-assistant",
        },
        "powered_by": "Ollama (self-hosted, no API key)",
        "node": "ai.thronoschain.org",
    })


@app.route("/health")
def health():
    ollama_status = ollama_helper.health_check()
    status = "healthy" if ollama_status.get("healthy") else "degraded"
    return jsonify({
        "status": status,
        "service": "thronos-ai",
        "ollama": ollama_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }), 200 if status == "healthy" else 503


@app.route("/api/ai/models", methods=["GET"])
def list_models():
    models = ollama_helper.list_models()
    return jsonify({
        "provider": "ollama",
        "models": models,
        "default": os.getenv("OLLAMA_DEFAULT_MODEL", "qwen2.5-coder:32b"),
    })


@app.route("/api/ai/models/pull", methods=["POST"])
def pull_model():
    data = request.get_json(force=True)
    model_name = data.get("model")
    if not model_name:
        return jsonify({"error": "model is required"}), 400
    result = ollama_helper.pull_model(model_name)
    return jsonify(result)


@app.route("/api/ai/chat", methods=["POST"])
def chat():
    """Direct chat endpoint — send a prompt, get a response from the local model."""
    data = request.get_json(force=True)
    prompt = data.get("message") or data.get("prompt")
    if not prompt:
        return jsonify({"error": "message or prompt is required"}), 400

    model = data.get("model")
    system_prompt = data.get("system_prompt")
    temperature = data.get("temperature", 0.1)

    result = ollama_helper.generate(
        prompt=prompt,
        model=model,
        system_prompt=system_prompt,
        metadata={"temperature": temperature},
    )

    return jsonify({
        "provider": result.get("provider"),
        "model": result.get("model"),
        "content": result.get("content"),
        "error": result.get("error"),
    })


@app.route("/api/ai/complete", methods=["POST"])
def complete():
    """Code completion endpoint — optimized for coding tasks."""
    data = request.get_json(force=True)
    code = data.get("code") or data.get("prompt")
    if not code:
        return jsonify({"error": "code or prompt is required"}), 400

    language = data.get("language", "")
    task = data.get("task", "complete")

    system_prompt = (
        f"You are an expert {language} programmer. "
        f"Task: {task}. "
        "Return only code, no explanations unless asked."
    )

    result = ollama_helper.generate(
        prompt=code,
        model=data.get("model"),
        system_prompt=system_prompt,
    )

    return jsonify({
        "provider": result.get("provider"),
        "model": result.get("model"),
        "completion": result.get("content"),
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    logger.info("Starting Thronos AI server on port %d", port)
    app.run(host="0.0.0.0", port=port, debug=debug)
