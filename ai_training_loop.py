# ai_training_loop.py
"""
AI Training Loop for Thronos Quantum.

Διαβάζει το data/ai_offline_corpus.json και χτίζει δύο σύνολα:

- data/ai_training_pairs.jsonl
    user -> assistant ζεύγη, κατάλληλα για fine-tune.

- data/ai_knowledge_blocks.jsonl
    high-quality assistant blocks, ιδανικά για retrieval / RAG.

Το script είναι ανθεκτικό σε μεταβολές σχήματος (flat log ή blocks).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).parent
CORPUS_PATH = ROOT / "data" / "ai_offline_corpus.json"
TRAIN_PAIRS_PATH = ROOT / "data" / "ai_training_pairs.jsonl"
KNOWLEDGE_BLOCKS_PATH = ROOT / "data" / "ai_knowledge_blocks.jsonl"


def load_corpus(path: Path = CORPUS_PATH) -> List[Dict[str, Any]]:
  if not path.exists():
    raise SystemExit(f"Offline corpus not found at {path}")

  with path.open("r", encoding="utf-8") as f:
    data = json.load(f)

  # Normalise σε λίστα
  if isinstance(data, dict):
    for key in ("items", "logs", "corpus", "data"):
      if key in data and isinstance(data[key], list):
        return data[key]
    return [data]

  if not isinstance(data, list):
    raise SystemExit(f"Unexpected corpus type: {type(data)!r}")

  return data


def iter_message_pairs(
  corpus: List[Dict[str, Any]]
) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
  """
  Επιστρέφει (user_msg, assistant_msg) pairs.

  Υποστηρίζει δύο σχήματα:
  1. Block log: item["messages"] = [...]
  2. Flat log: κάθε item έχει role/content/session_id.
  """
  pairs: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []

  if corpus and isinstance(corpus[0], dict) and "messages" in corpus[0]:
    # Block-shaped
    for block in corpus:
      msgs = block.get("messages") or []
      last_user = None
      for msg in msgs:
        role = msg.get("role")
        if role == "user":
          last_user = msg
        elif role in ("assistant", "system") and last_user is not None:
          pairs.append((last_user, msg))
          last_user = None
  else:
    # Flat log – group by session_id
    by_session: Dict[str, List[Dict[str, Any]]] = {}
    for item in corpus:
      sid = str(item.get("session_id") or item.get("session") or "global")
      by_session.setdefault(sid, []).append(item)

    for sid, msgs in by_session.items():
      # Αν υπάρχει created_at το χρησιμοποιούμε για ordering
      msgs.sort(key=lambda m: m.get("created_at", 0))
      last_user = None
      for msg in msgs:
        role = msg.get("role")
        if role == "user":
          last_user = msg
        elif role in ("assistant", "system") and last_user is not None:
          pairs.append((last_user, msg))
          last_user = None

  return pairs


def quality_score(msg: Dict[str, Any]) -> float:
  """
  Heuristic scoring για assistant μήνυμα.

  +1.0 αν meta.thumbs_up / meta.liked
  +rating αν meta.rating >= 1
  +0.3 αν το μήνυμα έχει “φυσιολογικό” μήκος
  -0.5 αν μοιάζει με error/traceback
  """
  meta = msg.get("meta") or msg.get("metadata") or {}
  score = 0.0

  if meta.get("thumbs_up") or meta.get("liked"):
    score += 1.0

  rating = meta.get("rating")
  if isinstance(rating, (int, float)) and rating >= 1:
    score += float(rating)

  content = (msg.get("content") or "").strip()
  n = len(content)

  if 80 <= n <= 4000:
    score += 0.3

  if "Traceback (most recent call last):" in content or "Error:" in content:
    score -= 0.5

  return score


def build_datasets(threshold: float = 0.5) -> None:
  corpus = load_corpus()
  pairs = iter_message_pairs(corpus)

  TRAIN_PAIRS_PATH.parent.mkdir(parents=True, exist_ok=True)

  n_pairs = 0
  n_blocks = 0

  with TRAIN_PAIRS_PATH.open("w", encoding="utf-8") as f_pairs, \
       KNOWLEDGE_BLOCKS_PATH.open("w", encoding="utf-8") as f_blocks:

    for user_msg, assistant_msg in pairs:
      pair = {
        "input": user_msg.get("content", ""),
        "output": assistant_msg.get("content", ""),
        "session_id": user_msg.get("session_id") or assistant_msg.get("session_id"),
      }
      f_pairs.write(json.dumps(pair, ensure_ascii=False) + "\n")
      n_pairs += 1

      score = quality_score(assistant_msg)
      if score >= threshold:
        block = {
          "content": assistant_msg.get("content", ""),
          "session_id": assistant_msg.get("session_id") or user_msg.get("session_id"),
          "score": score,
          "meta": assistant_msg.get("meta") or assistant_msg.get("metadata") or {},
        }
        f_blocks.write(json.dumps(block, ensure_ascii=False) + "\n")
        n_blocks += 1

  print(f"Built {n_pairs} training pairs → {TRAIN_PAIRS_PATH}")
  print(
    f"Selected {n_blocks} high-quality blocks (score ≥ {threshold}) "
    f"→ {KNOWLEDGE_BLOCKS_PATH}"
  )


if __name__ == "__main__":
  build_datasets()
