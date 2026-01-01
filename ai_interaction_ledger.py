import json
import os
import time
import hashlib
import uuid
from typing import Any, Dict, List, Optional


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
os.makedirs(DATA_DIR, exist_ok=True)

LEDGER_FILE = os.path.join(DATA_DIR, "ai_interactions.log")
BLOCKCHAIN_FILE = os.path.join(DATA_DIR, "thronos_blockchain.json")
CHAIN_FILE = os.path.join(DATA_DIR, "ai_interaction_chain.json")
PROVIDERS_FILE = os.path.join(DATA_DIR, "ai_providers.json")
SESSIONS_FILE = os.path.join(DATA_DIR, "ai_sessions.json")
INTERACTIONS_FILE = os.path.join(DATA_DIR, "ai_interactions_v4.json")
SCORES_FILE = os.path.join(DATA_DIR, "ai_scores.json")


def _hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


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

    try:
        with open(LEDGER_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
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
