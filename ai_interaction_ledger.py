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
