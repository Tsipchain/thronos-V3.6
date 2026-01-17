"""AI Interaction Ledger for Thronos.

Lightweight module that:
  * hashes prompts and outputs,
  * stores minimal metadata to JSONL,
  * optionally appends a summarized block into the blockchain file.
"""

import hashlib
import json
import os
from datetime import datetime
from typing import Dict, Any

LEDGER_PATH = os.getenv("AI_LEDGER_PATH", "data/ai_ledger.jsonl")
LEDGER_CHAIN_PATH = os.getenv("AI_LEDGER_CHAIN_PATH", "data/ai_ledger_blocks.jsonl")

def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def record_interaction(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Append a single interaction to the JSONL ledger.

    Expected keys in entry:
      - provider, model
      - prompt, output
      - session_id, wallet, credits_used, score
    """
    os.makedirs(os.path.dirname(LEDGER_PATH), exist_ok=True)
    now = datetime.utcnow().isoformat() + "Z"

    doc = {
        "ts": now,
        "provider": entry.get("provider"),
        "model": entry.get("model"),
        "prompt_hash": _hash_text(entry.get("prompt", "")),
        "output_hash": _hash_text(entry.get("output", "")),
        "session_id": entry.get("session_id"),
        "wallet": entry.get("wallet"),
        "credits_used": entry.get("credits_used", 0),
        "score": entry.get("score"),
        "meta": entry.get("meta", {}),
    }

    with open(LEDGER_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(doc) + "\n")

    return doc
