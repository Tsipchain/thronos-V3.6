"""Thronos AI Core — serv3r.py

Lightweight Flask service powering ai.thronoschain.org.

Endpoints:
  GET  /                       Landing page
  GET  /health                 Quick JSON health (Render / uptime checks)
  GET  /api/v1/health          Full health via blueprint
  POST /api/chat               VerifyID Agent Dashboard chat (X-Internal-Key)
  POST /api/v1/fraud/document  KYC document fraud analysis   (X-API-Key)
  POST /api/v1/assistant/ask   AI assistant for agents       (X-API-Key)
  POST /api/ai/chat            App-aware chat (X-Thronos-App header)
  GET  /api/ai/chat            Service info / endpoint map
  POST /tx/submit              AI tx types: AI_SERVICE_REGISTER, AI_ATTESTATION
  GET  /tx/registry            List registered AI services (requires X-API-Key)

Auth:
  Internal endpoints require the header X-Internal-Key (or X-API-Key)
  to match the APP_AI_KEY environment variable.
  If APP_AI_KEY is not set the checks are skipped (dev / local mode).

LLM Backend (env-driven):
  THRONOS_AI_MODE = anthropic (default) | openai
  ANTHROPIC_API_KEY           required when mode=anthropic
  AI_CORE_MODEL               override model name
  OPENAI_API_KEY              required when mode=openai
  APP_AI_BASE_URL             optional OpenAI-compatible base URL
"""

from __future__ import annotations

import json
import logging
import os

from flask import Flask, Response, jsonify, request

from health_check_v3 import health_bp, health_check

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

INTERNAL_KEY: str = os.getenv("APP_AI_KEY", "")
THRONOS_AI_MODE: str = os.getenv("THRONOS_AI_MODE", "anthropic").lower()

# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


def _check_key(req) -> bool:
    """Return True if the request carries a valid internal key.

    If APP_AI_KEY is not configured all requests pass (development / local mode).
    """
    if not INTERNAL_KEY:
        return True
    provided = req.headers.get("X-Internal-Key") or req.headers.get("X-API-Key") or ""
    return provided == INTERNAL_KEY


# ---------------------------------------------------------------------------
# LLM helper — thin wrapper around Anthropic / OpenAI
# ---------------------------------------------------------------------------


def _call_ai(
    messages: list,
    *,
    system: str = "",
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> dict:
    """Call the configured LLM provider.

    Args:
        messages:    list of {role, content} dicts.
        system:      system prompt string.
        max_tokens:  maximum completion tokens.
        temperature: sampling temperature.

    Returns:
        dict with keys: content (str), model (str), tokens_used (int).
    """
    mode = THRONOS_AI_MODE

    if mode == "anthropic":
        try:
            import anthropic as _ant  # type: ignore[import]
        except ImportError:
            raise RuntimeError("anthropic package not installed — run: pip install anthropic")

        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")

        model = os.getenv("AI_CORE_MODEL", "claude-3-5-sonnet-20241022")
        client = _ant.Anthropic(api_key=api_key)

        # Anthropic takes system separately; filter it out of messages
        user_msgs = [m for m in messages if m.get("role") != "system"]
        effective_system = system or next(
            (m["content"] for m in messages if m.get("role") == "system"),
            "You are a helpful AI assistant for the Thronos ecosystem.",
        )

        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=effective_system,
            messages=user_msgs,
        )

        text = "".join(
            block.text
            for block in resp.content
            if getattr(block, "type", None) == "text"
        )
        tokens_used = resp.usage.input_tokens + resp.usage.output_tokens
        return {"content": text, "model": model, "tokens_used": tokens_used}

    else:
        # OpenAI / OpenAI-compatible provider
        try:
            from openai import OpenAI  # type: ignore[import]
        except ImportError:
            raise RuntimeError("openai package not installed — run: pip install openai")

        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("APP_AI_KEY", "")
        base_url = os.getenv("APP_AI_BASE_URL") or None
        model = os.getenv("AI_CORE_MODEL", "gpt-4o-mini")

        client = OpenAI(api_key=api_key, base_url=base_url)

        effective_system = system or next(
            (m["content"] for m in messages if m.get("role") == "system"), ""
        )
        full_messages: list = []
        if effective_system:
            full_messages.append({"role": "system", "content": effective_system})
        full_messages.extend(m for m in messages if m.get("role") != "system")

        resp = client.chat.completions.create(
            model=model,
            messages=full_messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text = resp.choices[0].message.content or ""
        tokens_used = resp.usage.total_tokens if resp.usage else 0
        return {"content": text, "model": model, "tokens_used": tokens_used}


# ---------------------------------------------------------------------------
# App-specific system prompts
# ---------------------------------------------------------------------------

_PROMPT_THRONOS = (
    "You are Thronos Autonomous AI. "
    "You are an expert in the Thronos V3.6 blockchain architecture, governance system, "
    "billing, chain economics, smart contracts, and on-chain telemetry. "
    "You help core developers and power users with architecture questions, code, "
    "and protocol-level topics. Be concise and technically precise."
)

_PROMPT_VERIFYID = (
    "You are the VerifyID AI Assistant for the Thronos ecosystem. "
    "Your job is to help KYC agents and managers with identity verification, "
    "document authentication, risk scoring, fraud detection, compliance, "
    "device verification (ASIC, GPS, Vehicle nodes), verification rewards, "
    "and Delphi-3 agent training. "
    "Be professional, clear, and focused on identity and KYC topics."
)

_PROMPT_FRAUD_ANALYST = (
    "You are a document fraud detection AI for KYC verification. "
    "Analyze the provided document metadata and return a JSON object with exactly these fields:\n"
    '  "fraud_score": integer 0-100 (higher = more suspicious),\n'
    '  "risk_level": one of "low", "medium", "high", "critical",\n'
    '  "explanation": brief plain-text explanation of findings,\n'
    '  "flags": array of specific fraud indicators (empty array if none).\n'
    "Respond ONLY with valid JSON. No markdown, no code fences, no extra text."
)


def _app_prompt(app_id: str) -> str:
    return _PROMPT_VERIFYID if app_id == "verifyid" else _PROMPT_THRONOS


# ---------------------------------------------------------------------------
# Landing page HTML
# ---------------------------------------------------------------------------

AI_CORE_LANDING_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Thronos AI Core</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      *, *::before, *::after { box-sizing: border-box; }
      body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; padding: 0; background: #050816; color: #f9fafb; }
      .hero { min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 2rem; }
      h1 { font-size: clamp(2rem, 4vw, 3rem); margin-bottom: 0.75rem; background: linear-gradient(135deg, #22c55e, #38bdf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
      p { max-width: 640px; margin: 0.25rem auto; line-height: 1.6; color: #d1d5db; }
      .tag { display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.3rem 0.75rem; border-radius: 999px; border: 1px solid #374151; font-size: 0.8rem; margin-bottom: 1.25rem; color: #9ca3af; }
      .tag-dot { width: 8px; height: 8px; border-radius: 50%; background: #22c55e; box-shadow: 0 0 10px #22c55e; animation: pulse 2s infinite; }
      @keyframes pulse { 0%,100%{ opacity:1; } 50%{ opacity:0.4; } }
      .links { display: flex; flex-wrap: wrap; gap: 0.75rem; justify-content: center; margin-top: 1.75rem; }
      .btn { padding: 0.65rem 1.4rem; border-radius: 999px; border: 1px solid #374151; color: #e5e7eb; text-decoration: none; font-size: 0.9rem; transition: all 0.15s ease; }
      .btn.primary { background: linear-gradient(135deg, #22c55e, #38bdf8); border-color: transparent; color: #020617; font-weight: 600; }
      .btn:hover { border-color: #6b7280; transform: translateY(-1px); }
      .btn.primary:hover { filter: brightness(1.08); }
      .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; margin-top: 2.5rem; max-width: 900px; width: 100%; }
      .card { padding: 1.1rem 1.2rem; border-radius: 0.9rem; border: 1px solid #1f2937; background: radial-gradient(circle at top left, rgba(56,189,248,0.12), transparent 55%), #080f1e; text-align: left; }
      .card h3 { margin: 0 0 0.4rem; font-size: 0.95rem; color: #e5e7eb; }
      .card p { font-size: 0.82rem; margin: 0; color: #9ca3af; }
      code { font-family: monospace; background: #0f172a; padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.78rem; color: #38bdf8; }
      .footnote { margin-top: 2.5rem; font-size: 0.72rem; color: #4b5563; }
    </style>
  </head>
  <body>
    <main class="hero">
      <div class="tag">
        <span class="tag-dot"></span>
        <span>Thronos AI Core &middot; Live</span>
      </div>
      <h1>Autonomous AI Core</h1>
      <p>
        This node powers all internal AI workloads for the Thronos ecosystem &mdash;
        VerifyID KYC agents, document fraud analysis, AI assistant services,
        and on-chain AI copilots.
      </p>
      <p style="margin-top:0.6rem;">
        This is an <strong>internal service node</strong>, not a public chat interface.
        Access is restricted to approved Thronos backends via API key.
      </p>
      <div class="links">
        <a class="btn primary" href="/health">Live health status</a>
        <a class="btn" href="https://thronoschain.org" target="_blank" rel="noreferrer">thronoschain.org</a>
        <a class="btn" href="https://verifyid.thronoschain.org" target="_blank" rel="noreferrer">VerifyID</a>
      </div>
      <section class="grid">
        <article class="card">
          <h3>Agent Chat</h3>
          <p><code>POST /api/chat</code> &mdash; VerifyID agent dashboard assistant with KYC context.</p>
        </article>
        <article class="card">
          <h3>Fraud Analysis</h3>
          <p><code>POST /api/v1/fraud/document</code> &mdash; AI-powered KYC document fraud detection and scoring.</p>
        </article>
        <article class="card">
          <h3>AI Assistant</h3>
          <p><code>POST /api/v1/assistant/ask</code> &mdash; Context-aware assistant for agents and managers.</p>
        </article>
        <article class="card">
          <h3>App-aware Chat</h3>
          <p><code>POST /api/ai/chat</code> &mdash; Multi-app routing via <code>X-Thronos-App</code> header.</p>
        </article>
      </section>
      <p class="footnote">
        Node: ai.thronoschain.org &mdash; Thronos V3.6 AI Core
      </p>
    </main>
  </body>
</html>
"""


# ---------------------------------------------------------------------------
# Flask application factory
# ---------------------------------------------------------------------------


def create_app() -> Flask:  # noqa: C901
    app = Flask(__name__)

    # ── Landing page ─────────────────────────────────────────────────────────

    @app.route("/", methods=["GET"])
    def landing() -> Response:
        return Response(AI_CORE_LANDING_HTML, mimetype="text/html")

    # ── Health ───────────────────────────────────────────────────────────────

    app.register_blueprint(health_bp)  # provides /api/v1/health

    @app.route("/health", methods=["GET"])
    def simple_health():  # type: ignore[return]
        """Quick health check — reuses the full /api/v1/health handler."""
        return health_check()

    # ── /api/chat ────────────────────────────────────────────────────────────
    # Used by VerifyID's Agent Dashboard modal (backend/ai_chat.py)

    @app.route("/api/chat", methods=["POST"])
    def api_chat():
        """VerifyID Agent Dashboard AI chat.

        Body:    { "message": "...", "context": "...", "system_prompt": "..." }
        Headers: X-Internal-Key: <APP_AI_KEY>
        Returns: { "response": "...", "model": "...", "tokens_used": 0 }
        """
        if not _check_key(request):
            return jsonify({"error": "unauthorized"}), 401

        data = request.get_json(silent=True) or {}
        message = (data.get("message") or "").strip()
        context = (data.get("context") or "").strip()
        system_prompt = (data.get("system_prompt") or _PROMPT_VERIFYID).strip()

        if not message:
            return jsonify({"error": "message is required"}), 400

        user_content = f"Context: {context}\n\n{message}" if context else message

        try:
            result = _call_ai(
                [{"role": "user", "content": user_content}],
                system=system_prompt,
            )
            return jsonify(
                {
                    "response": result["content"],
                    "model": result["model"],
                    "tokens_used": result["tokens_used"],
                }
            )
        except Exception as exc:
            logger.exception("[AI Core] /api/chat error")
            return jsonify({"error": str(exc)}), 500

    # ── /api/v1/fraud/document ───────────────────────────────────────────────
    # Called by verifyid backend/services/aihub_client.py → analyze_document()

    @app.route("/api/v1/fraud/document", methods=["POST"])
    def api_fraud_document():
        """KYC document fraud analysis.

        Body:    document metadata / feature dict (any structure)
        Headers: X-API-Key: <APP_AI_KEY>
        Returns: { "fraud_score": 0-100, "risk_level": "low|medium|high|critical",
                   "explanation": "...", "flags": [...] }
        """
        if not _check_key(request):
            return jsonify({"error": "unauthorized"}), 401

        data = request.get_json(silent=True) or {}
        payload_str = json.dumps(data, ensure_ascii=False, indent=2)
        user_msg = f"Analyze this KYC document payload for fraud indicators:\n\n{payload_str}"

        try:
            result = _call_ai(
                [{"role": "user", "content": user_msg}],
                system=_PROMPT_FRAUD_ANALYST,
                max_tokens=512,
                temperature=0.1,
            )
            content = result["content"].strip()

            # Strip markdown code fences if the model wrapped the JSON
            if content.startswith("```"):
                parts = content.split("```")
                content = parts[1].lstrip("json").strip() if len(parts) > 1 else content

            try:
                parsed: dict = json.loads(content)
                parsed.setdefault("fraud_score", 50)
                parsed.setdefault("risk_level", "medium")
                parsed.setdefault("explanation", "")
                parsed.setdefault("flags", [])
                return jsonify(parsed)
            except json.JSONDecodeError:
                logger.warning(
                    "[AI Core] /api/v1/fraud/document — model did not return JSON: %.200s",
                    content,
                )
                return jsonify(
                    {
                        "fraud_score": 50,
                        "risk_level": "medium",
                        "explanation": content[:500] or "Analysis unavailable",
                        "flags": [],
                    }
                )

        except Exception as exc:
            logger.exception("[AI Core] /api/v1/fraud/document error")
            return (
                jsonify(
                    {
                        "fraud_score": 50,
                        "risk_level": "medium",
                        "explanation": "AI analysis temporarily unavailable",
                        "flags": [],
                    }
                ),
                500,
            )

    # ── /api/v1/assistant/ask ────────────────────────────────────────────────
    # Called by verifyid backend/services/aihub_client.py → ask_assistant()

    @app.route("/api/v1/assistant/ask", methods=["POST"])
    def api_assistant_ask():
        """AI Assistant for VerifyID agents and managers.

        Body:    { "prompt": "...", "context": "...",
                   "role": "agent|manager|admin", "service": "verifyid" }
        Headers: X-API-Key: <APP_AI_KEY>
        Returns: { "answer": "...", "confidence": 0.9, "sources": [] }
        """
        if not _check_key(request):
            return jsonify({"error": "unauthorized"}), 401

        data = request.get_json(silent=True) or {}
        prompt = (data.get("prompt") or "").strip()
        context = (data.get("context") or "").strip()
        role = (data.get("role") or "agent").strip()
        service = (data.get("service") or "verifyid").strip()

        if not prompt:
            return jsonify({"error": "prompt is required"}), 400

        system = _PROMPT_VERIFYID + f"\n\nUser role: {role}. Service: {service}."
        user_content = f"Context: {context}\n\nQuestion: {prompt}" if context else prompt

        try:
            result = _call_ai(
                [{"role": "user", "content": user_content}],
                system=system,
                max_tokens=1024,
            )
            return jsonify(
                {
                    "answer": result["content"],
                    "confidence": 0.9,
                    "sources": [],
                }
            )
        except Exception as exc:
            logger.exception("[AI Core] /api/v1/assistant/ask error")
            return jsonify({"error": str(exc)}), 503

    # ── /api/ai/chat ─────────────────────────────────────────────────────────
    # Multi-app chat with X-Thronos-App header routing

    @app.route("/api/ai/chat", methods=["GET"])
    def api_ai_chat_info():
        """Service info and endpoint map (no auth required)."""
        return jsonify(
            {
                "ok": True,
                "service": "thronos-ai-core",
                "version": "1.1.0",
                "node": "ai.thronoschain.org",
                "endpoints": {
                    "landing":   "GET  /",
                    "health":    "GET  /health",
                    "chat":      "POST /api/chat              (X-Internal-Key)",
                    "fraud":     "POST /api/v1/fraud/document (X-API-Key)",
                    "assistant": "POST /api/v1/assistant/ask  (X-API-Key)",
                    "ai_chat":   "POST /api/ai/chat           (X-Thronos-App)",
                },
                "apps": ["thronos", "verifyid"],
            }
        )

    @app.route("/api/ai/chat", methods=["POST"])
    def api_ai_chat():
        """App-aware AI chat endpoint.

        Headers: X-Thronos-App: verifyid | thronos  (default: thronos)
        Body:    { "messages": [...], "temperature": 0.3, "max_tokens": 1024 }
        Returns: { "ok": true, "content": "...", "model": "...",
                   "app_id": "...", "usage": {"total_tokens": 0} }
        """
        app_id = request.headers.get("X-Thronos-App", "thronos").lower().strip()
        data = request.get_json(silent=True) or {}
        messages: list = data.get("messages") or []
        temperature = float(data.get("temperature", 0.3))
        max_tokens = int(data.get("max_tokens", 1024))

        if not messages:
            return jsonify({"ok": False, "error": "messages array is required"}), 400

        system = _app_prompt(app_id)

        try:
            result = _call_ai(
                messages,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return jsonify(
                {
                    "ok": True,
                    "content": result["content"],
                    "model": result["model"],
                    "app_id": app_id,
                    "usage": {"total_tokens": result["tokens_used"]},
                }
            )
        except Exception as exc:
            logger.exception("[AI Core] /api/ai/chat error (app=%s)", app_id)
            return jsonify({"ok": False, "error": str(exc)}), 500

    # ── CareerForge AI tx types ──────────────────────────────────────────────
    # Endpoint: POST /tx/submit
    # Handles AI_SERVICE_REGISTER and AI_ATTESTATION tx types for CareerForge
    # L2 microservice integration. Only hashes + metadata are stored (no PII).

    import hashlib as _hashlib
    import time as _time
    import secrets as _secrets

    # In-memory AI service registry (persisted to file for restarts)
    _REGISTRY_FILE = os.getenv("AI_REGISTRY_FILE", "ai_registry.json")
    _ai_registry: dict = {}  # pubkey_hex -> {service_name, scopes, registered_at}

    def _load_registry():
        nonlocal _ai_registry
        try:
            with open(_REGISTRY_FILE, "r") as f:
                _ai_registry = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            _ai_registry = {}

    def _save_registry():
        with open(_REGISTRY_FILE, "w") as f:
            json.dump(_ai_registry, f, indent=2)

    def _canonical_bytes(payload: dict) -> bytes:
        return json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    def _verify_compact_sig(pubkey_hex: str, msg: bytes, sig_hex: str) -> bool:
        """Verify secp256k1 compact 64-byte signature using ecdsa library."""
        try:
            from ecdsa import VerifyingKey, SECP256k1
            from ecdsa.util import sigdecode_string

            pub_bytes = bytes.fromhex(pubkey_hex)
            digest = _hashlib.sha256(msg).digest()

            if len(pub_bytes) == 33:
                # Compressed pubkey → decompress
                prefix = pub_bytes[0]
                x = int.from_bytes(pub_bytes[1:], "big")
                p = SECP256k1.curve.p()
                y_sq = (pow(x, 3, p) + 7) % p
                y = pow(y_sq, (p + 1) // 4, p)
                if (y % 2) != (prefix - 2):
                    y = p - y
                uncompressed = b"\x04" + x.to_bytes(32, "big") + y.to_bytes(32, "big")
                vk = VerifyingKey.from_string(uncompressed[1:], curve=SECP256k1)
            else:
                vk = VerifyingKey.from_string(pub_bytes[1:] if pub_bytes[0] == 4 else pub_bytes, curve=SECP256k1)

            sig_bytes = bytes.fromhex(sig_hex)
            return vk.verify_digest(sig_bytes, digest, sigdecode=sigdecode_string)
        except Exception as e:
            logger.warning("[tx/submit] sig verify failed: %s", e)
            return False

    _load_registry()

    @app.route("/tx/submit", methods=["POST"])
    def tx_submit():
        """
        Accept AI_SERVICE_REGISTER and AI_ATTESTATION transactions from
        CareerForge (and other L2 services). Validates:
          1. tx_type is known
          2. canonical txid matches sha256(prefix + payload_bytes)
          3. signature is valid secp256k1 compact 64-byte
          4. for AI_ATTESTATION: pubkey must be in registry with ai:attest scope
        """
        body = request.get_json(force=True) or {}
        tx_type = (body.get("payload") or {}).get("tx_type") or body.get("tx_type", "")

        if tx_type == "AI_SERVICE_REGISTER":
            payload = body.get("payload", {})
            pubkey = payload.get("pubkey", "").lower()
            service_name = payload.get("service_name", "")
            scopes = payload.get("scopes", [])
            sig_hex = body.get("registrant_signature", "")
            txid = body.get("txid", "")

            if not pubkey or not service_name or not sig_hex:
                return jsonify({"accepted": False, "error": "MISSING_FIELDS"}), 400

            prefix = os.getenv("SERVICE_PREFIX_REGISTER", "THRONOS|AI_SERVICE_REGISTER|V1|").encode("utf-8")
            payload_bytes = _canonical_bytes(payload)
            signing_bytes = prefix + payload_bytes
            expected_txid = _hashlib.sha256(signing_bytes).hexdigest()

            if txid and txid != expected_txid:
                return jsonify({"accepted": False, "error": "TXID_MISMATCH"}), 400

            # Allowlist mode: if REGISTRY_OPEN_REGISTRATION=false, reject unknown pubkeys
            if os.getenv("REGISTRY_OPEN_REGISTRATION", "true").lower() == "false":
                if pubkey not in _ai_registry:
                    return jsonify({"accepted": False, "error": "PUBKEY_NOT_ALLOWLISTED"}), 403

            if not _verify_compact_sig(pubkey, signing_bytes, sig_hex):
                return jsonify({"accepted": False, "error": "BAD_SIGNATURE"}), 400

            _ai_registry[pubkey] = {
                "service_name": service_name,
                "scopes": scopes,
                "registered_at": int(_time.time()),
                "txid": expected_txid,
            }
            _save_registry()
            logger.info("[tx/submit] AI_SERVICE_REGISTER: service=%s pubkey=%s...", service_name, pubkey[:12])
            return jsonify({"accepted": True, "mempool_txid": expected_txid, "tx_type": "AI_SERVICE_REGISTER"})

        elif tx_type == "AI_ATTESTATION":
            payload = body.get("payload", {})
            pubkey = body.get("attestor_pubkey", "").lower()
            sig_hex = body.get("attestor_signature", "")
            txid = body.get("txid", "")
            service = payload.get("service", "")

            if not pubkey or not sig_hex:
                return jsonify({"accepted": False, "error": "MISSING_FIELDS"}), 400

            # 1. Registry enforcement
            reg = _ai_registry.get(pubkey)
            if not reg:
                return jsonify({"accepted": False, "error": "UNREGISTERED_SERVICE"}), 403
            if "ai:attest" not in reg.get("scopes", []):
                return jsonify({"accepted": False, "error": "MISSING_SCOPE"}), 403

            # 2. Canonical bytes + txid check
            prefix_str = os.getenv("SERVICE_PREFIX", f"THRONOS|AI_ATTESTATION|V1|{service}|")
            prefix = prefix_str.encode("utf-8")
            payload_bytes = _canonical_bytes(payload)
            signing_bytes = prefix + payload_bytes
            expected_txid = _hashlib.sha256(signing_bytes).hexdigest()

            if txid and txid != expected_txid:
                return jsonify({"accepted": False, "error": "TXID_MISMATCH"}), 400

            # 3. Payload size limit
            if len(payload_bytes) > 2048:
                return jsonify({"accepted": False, "error": "PAYLOAD_TOO_LARGE"}), 400

            # 4. Time drift check (±10 min)
            created_at = payload.get("created_at", 0)
            now = int(_time.time())
            if abs(now - created_at) > 600:
                return jsonify({"accepted": False, "error": "TIME_DRIFT"}), 400

            # 5. Signature verify
            if not _verify_compact_sig(pubkey, signing_bytes, sig_hex):
                return jsonify({"accepted": False, "error": "BAD_SIGNATURE"}), 400

            logger.info(
                "[tx/submit] AI_ATTESTATION: service=%s type=%s tenant=%s txid=%s...",
                service,
                payload.get("artifact_type"),
                payload.get("tenant_id"),
                expected_txid[:12],
            )
            return jsonify({"accepted": True, "mempool_txid": expected_txid, "tx_type": "AI_ATTESTATION"})

        else:
            return jsonify({"accepted": False, "error": f"UNKNOWN_TX_TYPE: {tx_type}"}), 400

    @app.route("/tx/registry", methods=["GET"])
    def tx_registry():
        """List registered AI services (pubkeys + scopes). Admin view."""
        if not _check_key(request):
            return jsonify({"error": "unauthorized"}), 401
        return jsonify({"registry": _ai_registry, "count": len(_ai_registry)})

    return app


# ---------------------------------------------------------------------------
# WSGI entry point
# ---------------------------------------------------------------------------

app = create_app()

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8001"))
    app.run(host=host, port=port, debug=False)
