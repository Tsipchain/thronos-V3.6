"""Ollama Proxy Blueprint — exposes local Ollama to external services.

Railway runs Ollama on localhost:11434. Render (ai.thronoschain.org) needs
to reach it over the network. This blueprint proxies selected Ollama API
endpoints through the Railway Flask server with optional bearer-token auth.

Usage on Railway:
    Set OLLAMA_PROXY_ENABLED=1 and optionally OLLAMA_PROXY_TOKEN=<secret>

Usage on Render:
    Set OLLAMA_BASE_URL=https://api.thronoschain.org/ollama-bridge
    (and OLLAMA_PROXY_TOKEN if auth is enabled)
"""

import os
import json
import logging
from urllib import request as urllib_request
from urllib.error import URLError, HTTPError
from flask import Blueprint, request, jsonify, Response

logger = logging.getLogger(__name__)

ollama_proxy_bp = Blueprint("ollama_proxy", __name__)

OLLAMA_LOCAL = os.getenv("OLLAMA_LOCAL_URL", "http://localhost:11434")
PROXY_TOKEN = os.getenv("OLLAMA_PROXY_TOKEN", "")

ALLOWED_PATHS = {
    "api/tags", "api/chat", "api/generate", "api/pull",
    "api/show", "api/embeddings",
}


def _check_auth():
    if not PROXY_TOKEN:
        return None
    auth = request.headers.get("Authorization", "")
    if auth == f"Bearer {PROXY_TOKEN}":
        return None
    token_param = request.args.get("token", "")
    if token_param == PROXY_TOKEN:
        return None
    return jsonify({"error": "unauthorized", "detail": "Invalid or missing OLLAMA_PROXY_TOKEN"}), 401


@ollama_proxy_bp.route("/<path:subpath>", methods=["GET", "POST"])
def proxy(subpath):
    auth_err = _check_auth()
    if auth_err:
        return auth_err

    if subpath not in ALLOWED_PATHS:
        return jsonify({"error": "path_not_allowed", "allowed": sorted(ALLOWED_PATHS)}), 403

    target_url = f"{OLLAMA_LOCAL.rstrip('/')}/{subpath}"

    try:
        if request.method == "POST":
            body = request.get_data()
            req = urllib_request.Request(
                target_url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            timeout = 600.0 if subpath == "api/pull" else 300.0
        else:
            req = urllib_request.Request(target_url, method="GET")
            timeout = 15.0

        with urllib_request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            return Response(
                data,
                status=resp.status,
                content_type=resp.headers.get("Content-Type", "application/json"),
            )

    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return Response(body, status=exc.code, content_type="application/json")

    except URLError as exc:
        logger.error("[OllamaProxy] Cannot reach Ollama at %s: %s", OLLAMA_LOCAL, exc)
        return jsonify({
            "error": "ollama_unreachable",
            "detail": f"Ollama not running at {OLLAMA_LOCAL}",
        }), 502

    except Exception as exc:
        logger.error("[OllamaProxy] Unexpected error: %s", exc)
        return jsonify({"error": "proxy_error", "detail": str(exc)}), 500
