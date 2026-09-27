"""Thronos Quantum Learning Engine.

Bridges user feedback (thumbs up/down) into the offline corpus and provides
RAG-lite knowledge retrieval so the chatbot improves over time.

Three responsibilities:
1. apply_feedback()  — stamps thumbs_up on the matching corpus entry
2. rebuild_knowledge_base() — runs the training loop to regenerate knowledge blocks
3. retrieve_knowledge()  — finds relevant high-rated past responses for context injection
"""

import json
import os
import re
import logging
import time
from pathlib import Path
from collections import Counter
from typing import Any, Dict, List, Optional

logger = logging.getLogger("thronos-learning")

DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
CORPUS_FILE = os.path.join(DATA_DIR, "ai_offline_corpus.json")
FEEDBACK_FILE = os.path.join(DATA_DIR, "ai_feedback.json")
KNOWLEDGE_FILE = os.path.join(DATA_DIR, "ai_knowledge_blocks.jsonl")
TRAINING_PAIRS_FILE = os.path.join(DATA_DIR, "ai_training_pairs.jsonl")

_REBUILD_INTERVAL = 300  # seconds between auto-rebuilds
_last_rebuild_ts = 0.0
_feedback_since_rebuild = 0

_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "above", "below", "between", "out", "off", "over",
    "under", "again", "further", "then", "once", "here", "there", "when",
    "where", "why", "how", "all", "each", "every", "both", "few", "more",
    "most", "other", "some", "such", "no", "not", "only", "own", "same",
    "so", "than", "too", "very", "just", "because", "but", "and", "or",
    "if", "while", "about", "up", "this", "that", "these", "those",
    "what", "which", "who", "whom", "it", "its", "i", "me", "my", "we",
    "our", "you", "your", "he", "she", "they", "them", "his", "her",
})


def _tokenize(text: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9_]+", text.lower()) if w not in _STOP_WORDS and len(w) > 2]


def _load_json(path: str, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else []


def _save_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def _get_corpus_entries() -> list:
    raw = _load_json(CORPUS_FILE, {"conversations": []})
    if isinstance(raw, dict):
        conv = raw.get("conversations")
        return conv if isinstance(conv, list) else []
    return raw if isinstance(raw, list) else []


def _save_corpus_entries(entries: list):
    raw = _load_json(CORPUS_FILE, {})
    if isinstance(raw, dict):
        raw["conversations"] = entries
        _save_json(CORPUS_FILE, raw)
    else:
        _save_json(CORPUS_FILE, entries)


def apply_feedback(session_id: str, message_text: str, thumbs_up: bool) -> bool:
    """Stamp feedback on the matching corpus entry so the training loop picks it up."""
    entries = _get_corpus_entries()
    msg_snippet = (message_text or "").strip()[:200].lower()
    if not msg_snippet:
        return False

    matched = False
    for entry in reversed(entries):
        eid = entry.get("session_id") or "default"
        if session_id and eid != session_id:
            continue
        resp = (entry.get("response") or "").strip()[:200].lower()
        if not resp:
            continue
        if resp == msg_snippet or msg_snippet in resp or resp in msg_snippet:
            if "meta" not in entry:
                entry["meta"] = {}
            entry["meta"]["thumbs_up"] = thumbs_up
            entry["meta"]["feedback_ts"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
            matched = True
            break

    if matched:
        _save_corpus_entries(entries)
        global _feedback_since_rebuild
        _feedback_since_rebuild += 1

    return matched


def rebuild_knowledge_base(force: bool = False) -> Dict[str, Any]:
    """Rebuild knowledge blocks and training pairs from the corpus.

    Auto-skips if called too frequently unless force=True.
    """
    global _last_rebuild_ts, _feedback_since_rebuild

    now = time.time()
    if not force and (now - _last_rebuild_ts) < _REBUILD_INTERVAL:
        return {"skipped": True, "reason": "too_recent", "next_in": int(_REBUILD_INTERVAL - (now - _last_rebuild_ts))}

    entries = _get_corpus_entries()
    if not entries:
        return {"skipped": True, "reason": "empty_corpus"}

    os.makedirs(DATA_DIR, exist_ok=True)
    n_pairs = 0
    n_blocks = 0

    with open(TRAINING_PAIRS_FILE, "w", encoding="utf-8") as f_pairs, \
         open(KNOWLEDGE_FILE, "w", encoding="utf-8") as f_blocks:

        for entry in entries:
            prompt = (entry.get("prompt") or "").strip()
            response = (entry.get("response") or "").strip()
            if not prompt or not response:
                continue

            sid = entry.get("session_id") or "default"
            meta = entry.get("meta") or {}

            pair = {"input": prompt, "output": response, "session_id": sid}
            f_pairs.write(json.dumps(pair, ensure_ascii=False) + "\n")
            n_pairs += 1

            score = _quality_score(response, meta)
            if score >= 0.3:
                block = {
                    "prompt": prompt,
                    "content": response,
                    "session_id": sid,
                    "score": round(score, 2),
                    "meta": meta,
                    "tokens": _tokenize(prompt + " " + response),
                }
                f_blocks.write(json.dumps(block, ensure_ascii=False) + "\n")
                n_blocks += 1

    _last_rebuild_ts = now
    _feedback_since_rebuild = 0

    logger.info("[Learning] Rebuilt: %d pairs, %d knowledge blocks", n_pairs, n_blocks)
    return {"pairs": n_pairs, "blocks": n_blocks, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())}


def _quality_score(response: str, meta: dict) -> float:
    score = 0.0
    if meta.get("thumbs_up"):
        score += 1.5
    elif meta.get("thumbs_up") is False:
        score -= 1.0
    rating = meta.get("rating")
    if isinstance(rating, (int, float)) and rating >= 1:
        score += float(rating)
    n = len(response)
    if 80 <= n <= 6000:
        score += 0.3
    if "Traceback (most recent call last):" in response or "Error:" in response:
        score -= 0.5
    if "AI unavailable" in response or "[Ollama offline]" in response:
        score -= 2.0
    return score


def retrieve_knowledge(prompt: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """Find the most relevant high-rated past responses for context injection."""
    if not os.path.exists(KNOWLEDGE_FILE):
        maybe_rebuild()
        if not os.path.exists(KNOWLEDGE_FILE):
            return []

    query_tokens = set(_tokenize(prompt))
    if not query_tokens:
        return []

    candidates = []
    try:
        with open(KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    block = json.loads(line)
                except json.JSONDecodeError:
                    continue
                block_tokens = set(block.get("tokens") or _tokenize(block.get("content", "")))
                if not block_tokens:
                    continue
                overlap = query_tokens & block_tokens
                if len(overlap) < 2:
                    continue
                relevance = len(overlap) / (len(query_tokens | block_tokens) or 1)
                quality = block.get("score", 0.0)
                rank = relevance * 0.6 + min(quality / 3.0, 1.0) * 0.4
                candidates.append((rank, block))
    except FileNotFoundError:
        return []

    candidates.sort(key=lambda x: x[0], reverse=True)
    results = []
    seen = set()
    for rank, block in candidates[:top_k * 2]:
        content = block.get("content", "")
        sig = content[:100]
        if sig in seen:
            continue
        seen.add(sig)
        results.append({
            "prompt": block.get("prompt", ""),
            "response": content,
            "score": block.get("score", 0),
            "relevance": round(rank, 3),
        })
        if len(results) >= top_k:
            break

    return results


def build_knowledge_context(prompt: str, max_chars: int = 2000) -> str:
    """Build a context string from relevant knowledge blocks to inject into the chat prompt."""
    blocks = retrieve_knowledge(prompt, top_k=3)
    if not blocks:
        return ""

    parts = ["[Relevant past knowledge — use as reference, not verbatim:]"]
    total = 0
    for b in blocks:
        snippet = b["response"]
        if len(snippet) > 600:
            snippet = snippet[:600] + "..."
        entry = f"Q: {b['prompt'][:150]}\nA: {snippet}"
        if total + len(entry) > max_chars:
            break
        parts.append(entry)
        total += len(entry)

    if len(parts) == 1:
        return ""
    return "\n\n".join(parts) + "\n\n"


def maybe_rebuild():
    """Trigger a rebuild if enough feedback has accumulated."""
    global _feedback_since_rebuild
    if _feedback_since_rebuild >= 5 or not os.path.exists(KNOWLEDGE_FILE):
        rebuild_knowledge_base(force=True)


def get_learning_stats() -> Dict[str, Any]:
    """Return stats about the learning system."""
    entries = _get_corpus_entries()
    total = len(entries)
    with_feedback = sum(1 for e in entries if (e.get("meta") or {}).get("thumbs_up") is not None)
    thumbs_up = sum(1 for e in entries if (e.get("meta") or {}).get("thumbs_up") is True)
    thumbs_down = sum(1 for e in entries if (e.get("meta") or {}).get("thumbs_up") is False)

    kb_count = 0
    if os.path.exists(KNOWLEDGE_FILE):
        with open(KNOWLEDGE_FILE, "r") as f:
            kb_count = sum(1 for line in f if line.strip())

    return {
        "corpus_entries": total,
        "with_feedback": with_feedback,
        "thumbs_up": thumbs_up,
        "thumbs_down": thumbs_down,
        "knowledge_blocks": kb_count,
        "feedback_pending_rebuild": _feedback_since_rebuild,
        "last_rebuild": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(_last_rebuild_ts)) if _last_rebuild_ts else None,
    }
