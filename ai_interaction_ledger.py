"""AI Interaction Ledger utilities for the Quantum backend."""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
os.makedirs(DATA_DIR, exist_ok=True)

LEDGER_FILE = os.path.join(DATA_DIR, "ai_interactions.log")
BLOCKCHAIN_FILE = os.path.join(DATA_DIR, "thronos_blockchain.json")
CHAIN_FILE = os.path.join(DATA_DIR, "ai_interaction_chain.jsonl")
PROVIDERS_FILE = os.path.join(DATA_DIR, "ai_providers.json")
SESSIONS_FILE = os.path.join(DATA_DIR, "ai_sessions.json")
INTERACTIONS_FILE = os.path.join(DATA_DIR, "ai_interactions_v4.jsonl")
SCORES_FILE = os.path.join(DATA_DIR, "ai_scores.jsonl")
VIEWER_CHAIN_FILE = os.getenv(
    "THRONOS_CHAIN_FILE", os.path.join(DATA_DIR, "phantom_tx_chain.json")
)
AI_AGENT_WALLET = os.getenv("THR_AI_AGENT_WALLET", "THR_AI_AGENT_WALLET_V1")
AI_TRANSFER_AMOUNT = float(os.getenv("AI_TRANSFER_AMOUNT", "0.001"))


def _hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _append_jsonl(path: str, data: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _load_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path: str, data: Any) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def _safe_load_chain(path: str) -> List[Dict[str, Any]]:
    data = _load_json(path, [])
    return data if isinstance(data, list) else []


def _chain_append(data: Dict[str, Any]) -> None:
    entry = {"timestamp": time.time(), "id": str(uuid.uuid4()), **data}
    _append_jsonl(CHAIN_FILE, entry)


def register_provider(provider_info: Dict[str, Any]) -> None:
    providers: List[Dict[str, Any]] = _load_json(PROVIDERS_FILE, [])
    providers.append(provider_info)
    _save_json(PROVIDERS_FILE, providers)


def register_session(session_info: Dict[str, Any]) -> None:
    sessions: List[Dict[str, Any]] = _load_json(SESSIONS_FILE, [])
    sessions.append(session_info)
    _save_json(SESSIONS_FILE, sessions)


def log_interaction(interaction: Dict[str, Any]) -> None:
    _append_jsonl(INTERACTIONS_FILE, interaction)


def log_score(score: Dict[str, Any]) -> None:
    _append_jsonl(SCORES_FILE, score)


def create_ai_transfer_from_ledger_entry(entry: Dict[str, Any]) -> None:
    """Create a sanitized AI transfer visible in the viewer.

    The transfer is written into the main ``phantom_tx_chain.json`` file so it
    appears in the Transfers tab without leaking raw prompts or responses.
    """

    try:
        from_address = entry.get("wallet") or entry.get("user_wallet") or "AI_SYSTEM"
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

        prompt_hash = entry.get("prompt_hash") or entry.get("input_hash") or ""
        response_hash = entry.get("output_hash") or entry.get("output_sha") or ""
        short_hash = (prompt_hash or response_hash or uuid.uuid4().hex)[:8]
        tx_id = f"AI-{int(time.time())}-{short_hash}"

        details: Dict[str, Any] = {
            "kind": "ai_interaction",
            "provider": entry.get("provider", "unknown"),
            "model": entry.get("model_id") or entry.get("model") or "unknown",
            "task_type": (entry.get("metadata") or {}).get("task_type")
            or entry.get("difficulty")
            or "unknown",
            "prompt_hash": prompt_hash,
            "response_hash": response_hash,
            "session_id": entry.get("session_id"),
            "wallet": entry.get("wallet") or entry.get("user_wallet"),
            "success": bool(entry.get("success", True)),
        }

        preview = entry.get("preview") or entry.get("output_preview")
        if isinstance(preview, str) and preview:
            details["preview"] = preview[:80]

        tx = {
            "tx_id": tx_id,
            "type": "transfer",
            "from": from_address,
            "to": AI_AGENT_WALLET,
            "asset": "THR",
            "token_symbol": "THR",
            "amount": AI_TRANSFER_AMOUNT,
            "fee": 0.0,
            "fee_burned": 0.0,
            "details": details,
            "timestamp": timestamp,
        }

        chain = _safe_load_chain(VIEWER_CHAIN_FILE)
        chain.append(tx)
        _save_json(VIEWER_CHAIN_FILE, chain)
    except Exception:
        # Transfers must not block the main AI interaction logging flow.
        try:
            print("[AI-LEDGER] Failed to create AI transfer", flush=True)
        except Exception:
            pass


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
    tier: Optional[str] = None,
    latency_ms: Optional[int] = None,
    success: Optional[bool] = None,
) -> None:
    """Backward compatible logger used by legacy callers.

    Internally it now writes into the v4 interaction ledger so the new REST
    endpoints and routing helper can reuse the same data set.
    """

    entry = {
        "timestamp": time.time(),
        "provider": provider,
        "model": model,
        "model_id": model,
        "tier": tier,
        "prompt_hash": _hash_text(prompt_text),
        "output_hash": _hash_text(output_text),
        "duration": duration,
        "latency_ms": latency_ms if latency_ms is not None else int(duration * 1000),
        "session_id": session_id,
        "wallet": wallet,
        "difficulty": difficulty,
        "block_hash": block_hash,
        "error": error,
        "success": success if success is not None else not bool(error),
        "metadata": metadata or {},
    }

    preview = (output_text or "")[:80]
    if preview:
        entry["preview"] = preview

    _append_jsonl(LEDGER_FILE, entry)
    _chain_append({"type": "ai_interaction", "data": entry})

    try:
        if os.path.exists(BLOCKCHAIN_FILE):
            with open(BLOCKCHAIN_FILE, "r", encoding="utf-8") as f:
                chain = json.load(f)
        else:
            chain = []
        chain.append({"type": "ai_interaction", "data": entry})
        _save_json(BLOCKCHAIN_FILE, chain)
    except Exception:
        pass

    try:
        create_ai_transfer_from_ledger_entry(entry)
    except Exception:
        # Avoid breaking the main recording flow due to transfer persistence issues
        pass


def compute_model_stats() -> Dict[str, Dict[str, Any]]:
    stats: Dict[str, Dict[str, Any]] = {}
    if not os.path.exists(LEDGER_FILE):
        return stats

    try:
        with open(LEDGER_FILE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                except Exception:
                    continue

                model_id = entry.get("model_id") or entry.get("model")
                if not model_id:
                    continue

                model_stats = stats.setdefault(
                    model_id,
                    {
                        "total_calls": 0,
                        "errors": 0,
                        "latency_sum_ms": 0.0,
                        "ratings": [],
                    },
                )

                model_stats["total_calls"] += 1
                if not entry.get("success", entry.get("error") is None):
                    model_stats["errors"] += 1

                latency_ms = entry.get("latency_ms")
                if latency_ms is None:
                    try:
                        latency_ms = float(entry.get("duration", 0)) * 1000
                    except Exception:
                        latency_ms = 0
                try:
                    model_stats["latency_sum_ms"] += float(latency_ms or 0)
                except Exception:
                    pass

                rating = None
                metadata = entry.get("metadata") or {}
                if isinstance(metadata, dict):
                    rating = metadata.get("rating") or metadata.get("user_rating")
                if rating is None:
                    rating = entry.get("user_rating")
                if rating is not None:
                    try:
                        model_stats["ratings"].append(float(rating))
                    except Exception:
                        pass
    except Exception:
        return stats

    aggregated: Dict[str, Dict[str, Any]] = {}
    for model_id, data in stats.items():
        total = max(1, data.get("total_calls", 0))
        avg_latency = (data.get("latency_sum_ms", 0.0) / total) if total else 0.0
        ratings = data.get("ratings", []) or []
        avg_rating = sum(ratings) / len(ratings) if ratings else None
        aggregated[model_id] = {
            "total_calls": data.get("total_calls", 0),
            "error_rate": (data.get("errors", 0) / total) if total else 0.0,
            "avg_latency_ms": avg_latency,
            "avg_user_rating": avg_rating,
        }

    return aggregated


def load_interactions() -> List[Dict[str, Any]]:
    if not os.path.exists(LEDGER_FILE):
        return []

    interactions: List[Dict[str, Any]] = []
    try:
        with open(LEDGER_FILE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    interactions.append(entry)
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return []
    except Exception:
        return []

    return interactions



def list_interactions(limit: int = 200) -> List[Dict[str, Any]]:
    """Return recent AI interactions from the ledger, newest first.

    This is a thin convenience wrapper used by the Flask API; the core
    logic remains in ``load_interactions`` above.
    """
    interactions = load_interactions()
    interactions.sort(
        key=lambda e: e.get("timestamp") or e.get("created_at", ""),
        reverse=True,
    )
    if limit and limit > 0:
        return interactions[:limit]
    return interactions


def get_ai_stats() -> Dict[str, Any]:
    """Public helper used by the Flask API to get aggregated stats.

    Under the hood we reuse ``compute_model_stats`` which reads the
    persisted model stats JSON produced by the background aggregator.
    """
    return compute_model_stats()


def interaction_to_block(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Transform a ledger entry into a minimal block payload for the chain.

    Kept intentionally small so that it can be safely embedded as a
    Thronos block without leaking full prompt / response contents.
    """
    return {
        "type": "ai_interaction",
        "timestamp": entry.get("timestamp"),
        "session_id": entry.get("session_id"),
        "provider": entry.get("provider"),
        "model": entry.get("model"),
        "wallet": entry.get("wallet"),
        "success": entry.get("success"),
        "hash": entry.get("hash"),
    }


def log_ai_error(
    provider: str,
    model: str,
    message: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Record an error-only entry in the AI ledger.

    This keeps error information in the same stream as successful
    calls, so the aggregator can compute error rates per model.
    """
    entry: Dict[str, Any] = {
        "timestamp": _utc_now(),
        "provider": provider,
        "model": model,
        "error": message,
        "success": False,
        "metadata": metadata or {},
    }
    _append_jsonl(LEDGER_FILE, entry)
