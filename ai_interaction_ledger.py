import json
import os
import time
import hashlib
from typing import Optional, Dict, Any

LEDGER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ai_interactions.log")
BLOCKCHAIN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "thronos_blockchain.json")

os.makedirs(os.path.dirname(LEDGER_FILE), exist_ok=True)


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
) -> None:
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
