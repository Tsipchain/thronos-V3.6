"""Delphi (D3lfoi) Admin Blueprint — AI Layer Management Console.

Provides admin-only endpoints for:
- AI layer health monitoring (providers, models, corpus, credits)
- AI credits management (check, grant, revoke)
- Provider configuration and toggles
- AI usage statistics and diagnostics
- Direct admin chat (bypasses credits billing)

All endpoints require ADMIN_SECRET authentication.
Works on ALL node roles (master, ai_core, worker).
"""

import json
import logging
import os
import secrets
import time
from typing import Any, Dict

from flask import Blueprint, jsonify, request

logger = logging.getLogger("thronos-delphi")

delphi_bp = Blueprint("delphi", __name__)


def _admin_ok() -> bool:
    """Check admin authentication from request headers/params."""
    expected = (os.getenv("ADMIN_SECRET") or "").strip()
    if not expected:
        return False
    provided = (
        request.headers.get("X-Admin-Secret")
        or request.headers.get("X-API-Key")
        or request.headers.get("Authorization", "").replace("Bearer ", "", 1)
        or request.args.get("adminSecret")
        or request.args.get("secret")
        or (request.get_json(silent=True) or {}).get("adminSecret")
        or (request.get_json(silent=True) or {}).get("secret")
        or ""
    ).strip()
    return bool(provided and provided == expected)


def _require_admin():
    if not _admin_ok():
        return jsonify(ok=False, error="unauthorized"), 401
    return None


# ── Health & Diagnostics ────────────────────────────────────────────────────

@delphi_bp.route("/health", methods=["GET"])
def delphi_health():
    """Full AI layer health check — providers, models, credits pool, corpus."""
    denied = _require_admin()
    if denied:
        return denied

    from server import (
        _build_ai_model_catalog,
        get_provider_status,
        _allowed_providers,
        _normalized_ai_mode,
        NODE_ROLE,
        AI_FREE_MESSAGES_LIMIT,
    )

    catalog = _build_ai_model_catalog()
    providers = get_provider_status()
    allowed = sorted(list(_allowed_providers()))

    openai_key = bool((os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY") or "").strip())
    anthropic_key = bool((os.getenv("ANTHROPIC_API_KEY") or "").strip())
    gemini_key = bool((os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip())

    enabled_models = [m for m in catalog if isinstance(m, dict) and m.get("enabled")]
    disabled_models = [m for m in catalog if isinstance(m, dict) and not m.get("enabled")]

    config_issues = []
    if openai_key and "openai" not in allowed:
        config_issues.append("OPENAI_API_KEY is set but 'openai' not in THR_ALLOWED_PROVIDERS")
    if anthropic_key and "anthropic" not in allowed:
        config_issues.append("ANTHROPIC_API_KEY is set but 'anthropic' not in THR_ALLOWED_PROVIDERS")
    if gemini_key and "gemini" not in allowed:
        config_issues.append("GEMINI/GOOGLE_API_KEY is set but 'gemini' not in THR_ALLOWED_PROVIDERS")
    if not openai_key and not anthropic_key and not gemini_key:
        config_issues.append("No LLM API keys configured (OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY)")

    ollama_url = (os.getenv("OLLAMA_BASE_URL") or "").strip()
    vapid_key = bool((os.getenv("VAPID_PRIVATE_KEY") or "").strip())

    return jsonify({
        "ok": True,
        "engine": "d3lfoi",
        "node_role": NODE_ROLE,
        "ai_mode": _normalized_ai_mode(),
        "raw_ai_mode": os.getenv("THRONOS_AI_MODE", ""),
        "providers": {
            "status": providers,
            "allowed": allowed,
            "raw_env": os.getenv("THR_ALLOWED_PROVIDERS", "(not set — using defaults)"),
            "keys_configured": {
                "openai": openai_key,
                "anthropic": anthropic_key,
                "gemini": gemini_key,
            },
        },
        "models": {
            "total": len(catalog),
            "enabled": len(enabled_models),
            "disabled": len(disabled_models),
            "catalog": catalog,
        },
        "services": {
            "ollama_url": ollama_url or "(not set)",
            "vapid_configured": vapid_key,
            "free_messages_limit": AI_FREE_MESSAGES_LIMIT,
        },
        "config_issues": config_issues,
    }), 200


# ── Credits Management ──────────────────────────────────────────────────────

@delphi_bp.route("/credits/check", methods=["GET"])
def delphi_credits_check():
    """Check AI credits balance for a wallet."""
    denied = _require_admin()
    if denied:
        return denied

    from server import get_ai_credits, get_available_ai_credits, is_ai_core

    wallet = (request.args.get("wallet") or "").strip()
    if not wallet:
        return jsonify(ok=False, error="wallet parameter required"), 400

    balance = get_available_ai_credits(wallet) if not is_ai_core() else get_ai_credits(wallet)
    return jsonify(ok=True, wallet=wallet, credits=balance), 200


@delphi_bp.route("/credits/grant", methods=["POST"])
def delphi_credits_grant():
    """Grant AI credits to a wallet."""
    denied = _require_admin()
    if denied:
        return denied

    from server import add_ai_credits, get_ai_credits, get_available_ai_credits, is_ai_core

    data = request.get_json(silent=True) or {}
    wallet = (data.get("wallet") or "").strip()
    amount = data.get("amount")
    reason = (data.get("reason") or "admin_grant").strip()

    if not wallet:
        return jsonify(ok=False, error="wallet required"), 400
    if amount is None or not isinstance(amount, (int, float)) or int(amount) < 1:
        return jsonify(ok=False, error="amount must be a positive integer"), 400

    amount = int(amount)
    before = get_available_ai_credits(wallet) if not is_ai_core() else get_ai_credits(wallet)
    after = add_ai_credits(wallet, amount, reason=reason, metadata={"origin": "delphi_admin", "admin": True})
    logger.info("[DELPHI] Granted %d credits to %s (before=%d after=%d reason=%s)", amount, wallet, before, after, reason)

    return jsonify(ok=True, wallet=wallet, granted=amount, before=before, after=after), 200


@delphi_bp.route("/credits/revoke", methods=["POST"])
def delphi_credits_revoke():
    """Remove AI credits from a wallet."""
    denied = _require_admin()
    if denied:
        return denied

    from server import add_ai_credits, get_ai_credits, get_available_ai_credits, is_ai_core

    data = request.get_json(silent=True) or {}
    wallet = (data.get("wallet") or "").strip()
    amount = data.get("amount")

    if not wallet:
        return jsonify(ok=False, error="wallet required"), 400
    if amount is None or not isinstance(amount, (int, float)) or int(amount) < 1:
        return jsonify(ok=False, error="amount must be a positive integer"), 400

    amount = int(amount)
    before = get_available_ai_credits(wallet) if not is_ai_core() else get_ai_credits(wallet)
    after = add_ai_credits(wallet, -amount, reason="admin_revoke", metadata={"origin": "delphi_admin"})

    return jsonify(ok=True, wallet=wallet, revoked=amount, before=before, after=after), 200


@delphi_bp.route("/credits/bulk-grant", methods=["POST"])
def delphi_credits_bulk_grant():
    """Grant AI credits to multiple wallets at once."""
    denied = _require_admin()
    if denied:
        return denied

    from server import add_ai_credits

    data = request.get_json(silent=True) or {}
    wallets = data.get("wallets") or []
    amount = data.get("amount")
    reason = (data.get("reason") or "admin_bulk_grant").strip()

    if not wallets or not isinstance(wallets, list):
        return jsonify(ok=False, error="wallets array required"), 400
    if amount is None or not isinstance(amount, (int, float)) or int(amount) < 1:
        return jsonify(ok=False, error="amount must be a positive integer"), 400

    amount = int(amount)
    results = []
    for w in wallets:
        w = (str(w) or "").strip()
        if not w:
            continue
        after = add_ai_credits(w, amount, reason=reason, metadata={"origin": "delphi_admin", "bulk": True})
        results.append({"wallet": w, "after": after})

    return jsonify(ok=True, granted=amount, count=len(results), results=results), 200


@delphi_bp.route("/credits/ledger", methods=["GET"])
def delphi_credits_ledger():
    """View recent AI credits ledger entries."""
    denied = _require_admin()
    if denied:
        return denied

    from server import load_ai_credits_ledger

    wallet = (request.args.get("wallet") or "").strip()
    limit = min(int(request.args.get("limit", 50)), 200)

    ledger = load_ai_credits_ledger()
    if not isinstance(ledger, list):
        ledger = []

    if wallet:
        ledger = [e for e in ledger if isinstance(e, dict) and e.get("wallet") == wallet]

    entries = ledger[-limit:]
    entries.reverse()

    return jsonify(ok=True, count=len(entries), entries=entries), 200


# ── Provider Management ─────────────────────────────────────────────────────

@delphi_bp.route("/providers", methods=["GET"])
def delphi_providers():
    """List all AI providers and their configuration status."""
    denied = _require_admin()
    if denied:
        return denied

    from server import get_provider_status, _allowed_providers

    status = get_provider_status()
    allowed = _allowed_providers()

    providers_detail = []
    provider_list = [
        ("openai", "OpenAI", "OPENAI_API_KEY"),
        ("anthropic", "Anthropic", "ANTHROPIC_API_KEY"),
        ("gemini", "Google Gemini", "GEMINI_API_KEY,GOOGLE_API_KEY"),
    ]
    for pid, name, env_keys in provider_list:
        has_key = any(bool((os.getenv(k) or "").strip()) for k in env_keys.split(","))
        providers_detail.append({
            "id": pid,
            "name": name,
            "api_key_configured": has_key,
            "allowed": pid in allowed,
            "available": status.get(pid, False),
            "issue": None if (has_key and pid in allowed) else
                     "API key missing" if not has_key else
                     f"Not in THR_ALLOWED_PROVIDERS (add '{pid}' to env var)",
        })

    providers_detail.append({
        "id": "offline",
        "name": "Offline Corpus",
        "api_key_configured": True,
        "allowed": "offline" in allowed,
        "available": True,
        "issue": None,
    })

    ollama_url = (os.getenv("OLLAMA_BASE_URL") or "").strip()
    providers_detail.append({
        "id": "ollama",
        "name": "Ollama (Self-hosted)",
        "api_key_configured": bool(ollama_url),
        "allowed": True,
        "available": bool(ollama_url),
        "issue": None if ollama_url else "OLLAMA_BASE_URL not set",
    })

    return jsonify(ok=True, providers=providers_detail, allowed_raw=os.getenv("THR_ALLOWED_PROVIDERS", "(not set)")), 200


# ── AI Statistics ────────────────────────────────────────────────────────────

@delphi_bp.route("/stats", methods=["GET"])
def delphi_stats():
    """AI usage statistics — interactions, credits spent, sessions."""
    denied = _require_admin()
    if denied:
        return denied

    from server import load_ai_credits, load_ai_credits_ledger, load_ai_interactions

    credits_map = load_ai_credits()
    total_wallets = len(credits_map)
    total_credits = sum(int(v or 0) for v in credits_map.values() if isinstance(v, (int, float, str)))
    wallets_with_credits = sum(1 for v in credits_map.values() if int(v or 0) > 0)

    ledger = load_ai_credits_ledger()
    total_granted = sum(e.get("delta", 0) for e in ledger if isinstance(e, dict) and e.get("delta", 0) > 0)
    total_spent = sum(abs(e.get("delta", 0)) for e in ledger if isinstance(e, dict) and e.get("delta", 0) < 0)

    interactions = load_ai_interactions()
    total_interactions = len(interactions) if isinstance(interactions, list) else 0

    return jsonify({
        "ok": True,
        "credits": {
            "total_wallets": total_wallets,
            "wallets_with_credits": wallets_with_credits,
            "total_credits_balance": total_credits,
            "total_granted": total_granted,
            "total_spent": total_spent,
        },
        "interactions": {
            "total": total_interactions,
        },
    }), 200


# ── Admin Direct Chat (No billing) ──────────────────────────────────────────

@delphi_bp.route("/chat", methods=["POST"])
def delphi_chat():
    """Admin AI chat — bypasses credits billing. D3lfoi operator console."""
    denied = _require_admin()
    if denied:
        return denied

    from server import (
        ai_agent,
        _select_callable_model,
        _build_chain_context_for_router,
        _build_ai_model_catalog,
        ensure_session_exists,
    )

    if not ai_agent:
        return jsonify(ok=False, error="ai_agent_not_loaded"), 503

    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify(ok=False, error="message required"), 400

    model_id = (data.get("model_id") or "auto").strip()
    session_id = (data.get("session_id") or f"delphi_{secrets.token_hex(6)}").strip()
    lang = (data.get("lang") or "el").strip().lower()

    selected_model, fallback_notice, error_resp = _select_callable_model(model_id, session_type="admin")
    if error_resp:
        payload = error_resp[0].get_json() if isinstance(error_resp, tuple) and hasattr(error_resp[0], "get_json") else {"error": "no_available_model"}
        payload["origin"] = "delphi_admin"
        payload["models"] = _build_ai_model_catalog()
        return jsonify(payload), 200

    resolved_model = selected_model or model_id or "auto"
    ensure_session_exists(session_id, "", "admin")

    prompt = f"[LANG={lang}]\n{message}"
    chain_context = _build_chain_context_for_router()

    try:
        raw = ai_agent.generate_response(prompt, wallet="", model_key=resolved_model, session_id=session_id, chain_context=chain_context)
    except Exception as exc:
        logger.exception("delphi_chat_failed")
        return jsonify(ok=False, error="provider_error", reason=str(exc), model_id=resolved_model), 200

    response_text = str(raw.get("response") if isinstance(raw, dict) else raw or "")

    return jsonify({
        "ok": True,
        "session_id": session_id,
        "model_id": resolved_model,
        "model_notice": fallback_notice,
        "response": response_text,
        "origin": "delphi_admin",
        "billing": "free",
    }), 200


# ── Configuration Overview ───────────────────────────────────────────────────

@delphi_bp.route("/config", methods=["GET"])
def delphi_config():
    """View current AI layer configuration."""
    denied = _require_admin()
    if denied:
        return denied

    from server import NODE_ROLE, AI_FREE_MESSAGES_LIMIT, _normalized_ai_mode, _allowed_providers

    env_snapshot = {
        "NODE_ROLE": NODE_ROLE,
        "THRONOS_AI_MODE": os.getenv("THRONOS_AI_MODE", "(not set)"),
        "THR_ALLOWED_PROVIDERS": os.getenv("THR_ALLOWED_PROVIDERS", "(not set)"),
        "AI_FREE_MESSAGES_LIMIT": AI_FREE_MESSAGES_LIMIT,
        "OLLAMA_BASE_URL": os.getenv("OLLAMA_BASE_URL", "(not set)"),
        "OLLAMA_PROXY_ENABLED": os.getenv("OLLAMA_PROXY_ENABLED", "(not set)"),
        "OPENAI_API_KEY": "***configured***" if (os.getenv("OPENAI_API_KEY") or "").strip() else "(not set)",
        "ANTHROPIC_API_KEY": "***configured***" if (os.getenv("ANTHROPIC_API_KEY") or "").strip() else "(not set)",
        "GEMINI_API_KEY": "***configured***" if (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip() else "(not set)",
        "VAPID_PRIVATE_KEY": "***configured***" if (os.getenv("VAPID_PRIVATE_KEY") or "").strip() else "(not set)",
    }

    return jsonify({
        "ok": True,
        "resolved_mode": _normalized_ai_mode(),
        "allowed_providers": sorted(list(_allowed_providers())),
        "env": env_snapshot,
        "recommendations": _build_recommendations(env_snapshot),
    }), 200


def _build_recommendations(env: dict) -> list:
    recs = []
    if env.get("THR_ALLOWED_PROVIDERS") == "(not set)":
        configured = []
        if env.get("OPENAI_API_KEY") != "(not set)":
            configured.append("openai")
        if env.get("ANTHROPIC_API_KEY") != "(not set)":
            configured.append("anthropic")
        if env.get("GEMINI_API_KEY") != "(not set)":
            configured.append("gemini")
        configured.extend(["offline", "thrai"])
        recs.append({
            "severity": "critical",
            "issue": "THR_ALLOWED_PROVIDERS not set — defaults to {openai, offline} only",
            "fix": f"Set THR_ALLOWED_PROVIDERS={','.join(configured)}",
        })
    if env.get("OPENAI_API_KEY") == "(not set)" and env.get("ANTHROPIC_API_KEY") == "(not set)" and env.get("GEMINI_API_KEY") == "(not set)":
        recs.append({
            "severity": "critical",
            "issue": "No LLM API keys configured — AI chat/architect cannot call any provider",
            "fix": "Set at least one of: OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY",
        })
    return recs
