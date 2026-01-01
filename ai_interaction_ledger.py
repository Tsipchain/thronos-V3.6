"""AI Interaction Ledger utilities for the Quantum backend.

The module implements a lightweight, append-only ledger that mirrors the
schema described in the "AI Interaction Ledger" brief:

- ``ai_providers``   : metadata for each upstream provider
- ``ai_sessions``    : session lifecycle entries
- ``ai_interactions``: prompt/response level records (hashed payloads)
- ``ai_scores``      : ML/human scoring signals

Data is stored under ``DATA_DIR`` in newline-delimited JSON files so we can
stream entries into a blockchain chain file later without blocking the main
request path.  Hashes are always SHA256 and prompts/responses are never stored
in plaintext here.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from typing import Any, Dict, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))

LEDGER_FILE = os.path.join(DATA_DIR, "ai_interactions.log")
BLOCKCHAIN_FILE = os.path.join(DATA_DIR, "thronos_blockchain.json")
CHAIN_FILE = os.path.join(DATA_DIR, "ai_interaction_chain.jsonl")
PROVIDERS_FILE = os.path.join(DATA_DIR, "ai_providers.json")
SESSIONS_FILE = os.path.join(DATA_DIR, "ai_sessions.json")
INTERACTIONS_FILE = os.path.join(DATA_DIR, "ai_interactions_v4.jsonl")
SCORES_FILE = os.path.join(DATA_DIR, "ai_scores.jsonl")

for path in [LEDGER_FILE, BLOCKCHAIN_FILE, CHAIN_FILE, PROVIDERS_FILE, SESSIONS_FILE, INTERACTIONS_FILE, SCORES_FILE]:
    os.makedirs(os.path.dirname(path), exist_ok=True)


def _hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _append_jsonl(path: str, payload: Dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _chain_append(kind: str, data: Dict[str, Any]) -> None:
    entry = {"id": str(uuid.uuid4()), "type": kind, "timestamp": int(time.time() * 1000), "data": data}
    try:
        _append_jsonl(CHAIN_FILE, entry)
    except Exception:
        pass


def register_provider(provider: Dict[str, Any]) -> Dict[str, Any]:
    """Register or update AI provider metadata.

    ``provider`` is expected to contain keys like ``id``, ``name``, ``type``,
    ``api`` and ``cost_per_token`` but we store the full object for flexibility.
    """

    providers = _load_json(PROVIDERS_FILE, {})
    pid = provider.get("id") or provider.get("name") or f"provider-{len(providers)+1}"
    provider["id"] = pid
    providers[pid] = provider
    try:
        _save_json(PROVIDERS_FILE, providers)
        _chain_append("ai_provider", provider)
    except Exception:
        pass
    return provider


def register_session(session: Dict[str, Any]) -> Dict[str, Any]:
    sessions = _load_json(SESSIONS_FILE, {})
    sid = session.get("session_id") or session.get("id") or str(uuid.uuid4())
    session_id = str(sid)
    session["session_id"] = session_id
    session.setdefault("created_at", int(time.time() * 1000))
    sessions[session_id] = session
    try:
        _save_json(SESSIONS_FILE, sessions)
        _chain_append("ai_session", session)
    except Exception:
        pass
    return session


def log_interaction(
    session_id: Optional[str],
    provider_id: str,
    prompt_text: str,
    response_text: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    latency_ms: int,
    cost_est: float,
    user_wallet: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = {
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "provider_id": provider_id,
        "model": model,
        "prompt_hash": _hash_text(prompt_text),
        "response_hash": _hash_text(response_text),
        "tokens_in": int(tokens_in or 0),
        "tokens_out": int(tokens_out or 0),
        "latency_ms": int(latency_ms or 0),
        "cost_est": float(cost_est or 0.0),
        "created_at": int(time.time() * 1000),
        "user_wallet": user_wallet,
        "metadata": metadata or {},
    }

    try:
        _append_jsonl(INTERACTIONS_FILE, payload)
        _append_jsonl(LEDGER_FILE, payload)  # keep backward compatibility
        _chain_append("ai_interaction", payload)
    except Exception:
        pass
    return payload


def log_score(
    interaction_id: str,
    quality_score: float,
    safety_score: float,
    domain_label: Optional[str] = None,
    model_decision: Optional[str] = None,
    human_feedback: Optional[str] = None,
) -> Dict[str, Any]:
    payload = {
        "id": str(uuid.uuid4()),
        "interaction_id": interaction_id,
        "quality_score": quality_score,
        "safety_score": safety_score,
        "domain_label": domain_label,
        "model_decision": model_decision,
        "human_feedback": human_feedback,
        "created_at": int(time.time() * 1000),
    }

    try:
        _append_jsonl(SCORES_FILE, payload)
        _chain_append("ai_score", payload)
    except Exception:
        pass
    return payload


def record_ai_interaction(
    provider: str,
    model: str,
    prompt_text: str,
    output_text: str,
    duration: float,
    session_id: Optional[str] = None,
    wallet: Optional[str] = None,
    difficulty: Optional[str] = None,
    block_hash: Optional[str] = None,
    error: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Backward compatible logger used by legacy callers.

    Internally it now writes into the v4 interaction ledger so the new REST
    endpoints and routing helper can reuse the same data set.
    """

    entry = {
        "timestamp": time.time(),
        "provider": provider,
        "model": model,
        "prompt_hash": _hash_text(prompt_text),
        "output_hash": _hash_text(output_text),
        "duration": duration,
        "session_id": session_id,
        "wallet": wallet,
        "difficulty": difficulty,
        "block_hash": block_hash,
        "error": error,
        "metadata": metadata or {},
    }

    try:
        with open(LEDGER_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass

    try:
        log_interaction(
            session_id=session_id,
            provider_id=provider,
            prompt_text=prompt_text,
            response_text=output_text,
            model=model,
            tokens_in=len(prompt_text.split()),
            tokens_out=len(output_text.split()),
            latency_ms=int(duration * 1000),
            cost_est=0.0,
            user_wallet=wallet,
            metadata=metadata,
        )
    except Exception:
        pass

    # Optional append to blockchain file as a special AI block type
    try:
        if os.path.exists(BLOCKCHAIN_FILE):
            with open(BLOCKCHAIN_FILE, "r", encoding="utf-8") as f:
                chain = json.load(f)
        else:
            chain = []
        chain.append({"type": "ai_interaction", "data": entry})
        with open(BLOCKCHAIN_FILE, "w", encoding="utf-8") as f:
            json.dump(chain, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
