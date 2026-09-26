"""Self-hosted LLM provider via Ollama.

No API key required — runs locally on the node's GPU.
Supports any model Ollama can serve (Qwen2.5-Coder, DeepSeek, CodeLlama, etc.).
Uses the OpenAI-compatible API that Ollama exposes at /v1/.
"""

import os
import json
import logging
from typing import Any, Dict, List, Optional
from urllib import request as urllib_request
from urllib.error import URLError

logger = logging.getLogger(__name__)

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def _api_url(path: str) -> str:
    return f"{OLLAMA_BASE.rstrip('/')}{path}"


def default_model() -> str:
    return os.getenv("OLLAMA_DEFAULT_MODEL", "qwen2.5-coder:32b")


def _post_json(url: str, payload: dict, timeout: float = 120.0) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url: str, timeout: float = 10.0) -> dict:
    req = urllib_request.Request(url, method="GET")
    with urllib_request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def health_check() -> dict:
    """Check if Ollama is running and which models are loaded."""
    try:
        tags = _get_json(_api_url("/api/tags"))
        models = [m.get("name", "") for m in tags.get("models", [])]
        return {"healthy": True, "models": models}
    except Exception as exc:
        return {"healthy": False, "error": str(exc), "models": []}


def list_models() -> List[dict]:
    """Return available models from the local Ollama instance."""
    try:
        tags = _get_json(_api_url("/api/tags"))
        return [
            {
                "id": m.get("name", ""),
                "label": m.get("name", ""),
                "size": m.get("size", 0),
                "modified_at": m.get("modified_at", ""),
            }
            for m in tags.get("models", [])
        ]
    except Exception:
        return []


def pull_model(model_name: str) -> dict:
    """Pull a model from the Ollama registry."""
    try:
        result = _post_json(
            _api_url("/api/pull"),
            {"name": model_name, "stream": False},
            timeout=600.0,
        )
        return {"success": True, "result": result}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def generate(
    prompt: str,
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tools: Optional[List[dict]] = None,
    temperature: float = 0.1,
) -> Dict[str, Any]:
    """Generate a response using the local Ollama model.

    Uses the /api/chat endpoint for conversation-style interaction
    with optional tool calling support.
    """
    m = model or default_model()

    messages: List[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload: dict = {
        "model": m,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_ctx": 32768,
        },
    }

    if tools:
        payload["tools"] = tools

    try:
        resp = _post_json(_api_url("/api/chat"), payload, timeout=300.0)
    except URLError as exc:
        logger.error("Ollama unreachable at %s: %s", OLLAMA_BASE, exc)
        return {
            "provider": "ollama",
            "model": m,
            "content": f"[Ollama offline] Could not reach {OLLAMA_BASE}",
            "error": str(exc),
            "raw": {},
        }

    message = resp.get("message", {})
    content = message.get("content", "")
    tool_calls = message.get("tool_calls", [])

    return {
        "provider": "ollama",
        "model": m,
        "content": content,
        "tool_calls": tool_calls,
        "raw": resp,
    }


def generate_with_tools(
    messages: List[dict],
    tools: List[dict],
    model: Optional[str] = None,
    temperature: float = 0.1,
    max_rounds: int = 10,
    tool_executor: Optional[callable] = None,
) -> Dict[str, Any]:
    """Run a multi-turn tool-calling loop until the model stops calling tools.

    This is the MCP-style agentic loop: model calls tools, we execute them,
    feed results back, repeat until the model gives a final text answer.
    """
    m = model or default_model()
    conversation = list(messages)
    all_tool_calls = []

    for _ in range(max_rounds):
        payload = {
            "model": m,
            "messages": conversation,
            "tools": tools,
            "stream": False,
            "options": {"temperature": temperature, "num_ctx": 32768},
        }

        try:
            resp = _post_json(_api_url("/api/chat"), payload, timeout=300.0)
        except URLError as exc:
            return {
                "provider": "ollama",
                "model": m,
                "content": f"[Ollama offline] {exc}",
                "tool_calls": all_tool_calls,
                "raw": {},
            }

        message = resp.get("message", {})
        tool_calls = message.get("tool_calls", [])

        if not tool_calls:
            return {
                "provider": "ollama",
                "model": m,
                "content": message.get("content", ""),
                "tool_calls": all_tool_calls,
                "raw": resp,
            }

        conversation.append({"role": "assistant", "content": "", "tool_calls": tool_calls})
        all_tool_calls.extend(tool_calls)

        if tool_executor:
            for tc in tool_calls:
                fn_name = tc.get("function", {}).get("name", "")
                fn_args = tc.get("function", {}).get("arguments", {})
                result = tool_executor(fn_name, fn_args)
                conversation.append({
                    "role": "tool",
                    "content": json.dumps(result) if not isinstance(result, str) else result,
                })

    return {
        "provider": "ollama",
        "model": m,
        "content": message.get("content", ""),
        "tool_calls": all_tool_calls,
        "raw": resp,
    }
