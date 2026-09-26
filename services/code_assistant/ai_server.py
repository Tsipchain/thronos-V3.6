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
        "version": "1.1.0",
        "endpoints": {
            "health": "/health",
            "chat": "/api/ai/chat",
            "complete": "/api/ai/complete",
            "translate": "/api/ai/translate",
            "languages": "/api/ai/languages",
            "models": "/api/ai/models",
            "code_assistant": "/api/code-assistant",
        },
        "capabilities": [
            "chat", "code_completion", "code_translation",
            "multi_language", "agentic_coding", "mcp_tools",
        ],
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


@app.route("/api/ai/translate", methods=["POST"])
def translate_code():
    """Translate code between any programming languages.

    Input:  { "code": "...", "source_language": "python", "target_language": "cpp" }
    Output: { "translated_code": "...", "source_language": "...", "target_language": "..." }

    Supports all languages: Python, C/C++, Rust, Go, Java, JavaScript/TypeScript,
    Solidity, Ruby, Swift, Kotlin, Haskell, Scala, Lua, PHP, C#, and more.
    """
    data = request.get_json(force=True)
    code = data.get("code")
    if not code:
        return jsonify({"error": "code is required"}), 400

    source_lang = data.get("source_language", "auto-detect")
    target_lang = data.get("target_language")
    if not target_lang:
        return jsonify({"error": "target_language is required"}), 400

    preserve_comments = data.get("preserve_comments", True)
    explain = data.get("explain", False)

    system_prompt = (
        "You are an expert polyglot programmer fluent in every programming language. "
        "You translate code accurately between languages, preserving logic, structure, "
        "and idioms. Use the target language's conventions and best practices. "
        "Handle language-specific features (memory management, type systems, concurrency) appropriately."
    )

    prompt_parts = [f"Translate the following {source_lang} code to {target_lang}.\n"]
    if preserve_comments:
        prompt_parts.append("Preserve comments (translated to English if needed).\n")
    if explain:
        prompt_parts.append("After the code, add a brief section explaining key translation decisions.\n")
    prompt_parts.append(f"\n```{source_lang}\n{code}\n```")

    result = ollama_helper.generate(
        prompt="\n".join(prompt_parts),
        model=data.get("model"),
        system_prompt=system_prompt,
    )

    return jsonify({
        "provider": result.get("provider"),
        "model": result.get("model"),
        "source_language": source_lang,
        "target_language": target_lang,
        "translated_code": result.get("content"),
        "error": result.get("error"),
    })


@app.route("/api/ai/languages", methods=["GET"])
def supported_languages():
    """List all programming languages the AI can work with."""
    return jsonify({
        "languages": [
            {"id": "python", "name": "Python", "extensions": [".py"]},
            {"id": "javascript", "name": "JavaScript", "extensions": [".js", ".mjs"]},
            {"id": "typescript", "name": "TypeScript", "extensions": [".ts", ".tsx"]},
            {"id": "cpp", "name": "C++", "extensions": [".cpp", ".hpp", ".cc", ".h"]},
            {"id": "c", "name": "C", "extensions": [".c", ".h"]},
            {"id": "rust", "name": "Rust", "extensions": [".rs"]},
            {"id": "go", "name": "Go", "extensions": [".go"]},
            {"id": "java", "name": "Java", "extensions": [".java"]},
            {"id": "kotlin", "name": "Kotlin", "extensions": [".kt"]},
            {"id": "swift", "name": "Swift", "extensions": [".swift"]},
            {"id": "csharp", "name": "C#", "extensions": [".cs"]},
            {"id": "ruby", "name": "Ruby", "extensions": [".rb"]},
            {"id": "php", "name": "PHP", "extensions": [".php"]},
            {"id": "solidity", "name": "Solidity", "extensions": [".sol"]},
            {"id": "haskell", "name": "Haskell", "extensions": [".hs"]},
            {"id": "scala", "name": "Scala", "extensions": [".scala"]},
            {"id": "lua", "name": "Lua", "extensions": [".lua"]},
            {"id": "r", "name": "R", "extensions": [".r", ".R"]},
            {"id": "dart", "name": "Dart", "extensions": [".dart"]},
            {"id": "elixir", "name": "Elixir", "extensions": [".ex", ".exs"]},
            {"id": "shell", "name": "Shell/Bash", "extensions": [".sh", ".bash"]},
            {"id": "sql", "name": "SQL", "extensions": [".sql"]},
            {"id": "html", "name": "HTML", "extensions": [".html"]},
            {"id": "css", "name": "CSS", "extensions": [".css"]},
            {"id": "yaml", "name": "YAML", "extensions": [".yml", ".yaml"]},
            {"id": "toml", "name": "TOML", "extensions": [".toml"]},
            {"id": "zig", "name": "Zig", "extensions": [".zig"]},
            {"id": "nim", "name": "Nim", "extensions": [".nim"]},
            {"id": "assembly", "name": "Assembly", "extensions": [".asm", ".s"]},
        ],
        "translation_supported": True,
        "completion_supported": True,
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    logger.info("Starting Thronos AI server on port %d", port)
    app.run(host="0.0.0.0", port=port, debug=debug)
