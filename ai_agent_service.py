# -*- coding: utf-8 -*-
"""
Thronos AI Agent Service

- Ενιαίο interface για OpenAI / Gemini / Offline.
- Καταγραφή όλων των κλήσεων σε ai_block_log.json.
- Συμβατό με server.py (generate_response + generate_quantum_key).
"""

import os
import json
import time
import hashlib
import random
import string
import logging
from typing import Optional, Dict, Any

import requests

# Προσπαθούμε να φορτώσουμε OpenAI client (νέο SDK)
try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except Exception:
    _OPENAI_AVAILABLE = False

# Αν θέλεις να χρησιμοποιήσεις το επίσημο google-genai SDK, μπορείς,
# αλλά εδώ πάμε με καθαρό requests γιατί έτσι κι αλλιώς το error 429
# ήρθε από HTTP κλήση.
# from google import genai   # προαιρετικό


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
os.makedirs(DATA_DIR, exist_ok=True)

AI_BLOCK_LOG_FILE = os.path.join(DATA_DIR, "ai_block_log.json")

logger = logging.getLogger("thronos_ai")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


class ThronosAI:
    def __init__(self) -> None:
        # Mode:
        #   "gemini"  -> μόνο Gemini
        #   "openai"  -> μόνο OpenAI
        #   "auto"    -> προσπαθεί Gemini, μετά OpenAI, μετά local
        #   "local"   -> καθόλου external, μόνο blockchain/local
        self.mode = os.getenv("THRONOS_AI_MODE", "auto").lower()

        # 👉 Διάβασε ΚΑΙ τα δύο ονόματα env, με προτεραιότητα στο GEMINI_API_KEY
        self.gemini_api_key = (
            os.getenv("GEMINI_API_KEY", "").strip()
            or os.getenv("GOOGLE_API_KEY", "").strip()
        )
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()

        self.gemini_model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
        self.openai_model_name = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = os.getenv("DATA_DIR", os.path.join(base_dir, "data"))
        os.makedirs(self.data_dir, exist_ok=True)

        self.ai_history_file = os.path.join(self.data_dir, "ai_history.json")
        self.ai_block_log_file = os.path.join(self.data_dir, "ai_block_log.json")

        self.gemini_model = None
        self.openai_client = None

        self._init_gemini()
        self._init_openai()

    # ------------------------------------------------------------------ #
    #  Βοηθητικά
    # ------------------------------------------------------------------ #
    def generate_quantum_key(self, length: int = 32) -> str:
        """Μικρό, όμορφο pseudo-κβαντικό κλειδί για το UI."""
        alphabet = string.hexdigits.lower()
        return "".join(random.choice(alphabet) for _ in range(length))

    def _load_log(self):
        try:
            with open(AI_BLOCK_LOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save_log(self, data):
        try:
            with open(AI_BLOCK_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Failed to write ai_block_log.json: %s", e)

    def _append_log_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Γράφει μία εγγραφή στο ai_block_log.json.
        Βάζουμε id, timestamp κτλ ώστε ο watcher να μπορεί να την δει.
        """
        log = self._load_log()
        # default fields
        entry.setdefault("id", f"{int(time.time()*1000)}-{len(log)}")
        entry.setdefault(
            "timestamp",
            time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        )
        log.append(entry)
        # Κρατάμε τα τελευταία 2000 για να μην ξεφύγει
        log = log[-2000:]
        self._save_log(log)
        return entry

    # ------------------------------------------------------------------ #
    #  Providers
    # ------------------------------------------------------------------ #
    def _call_gemini(self, prompt: str) -> str:
        """
        Κλήση σε Gemini REST API.
        Αν βαρέσει 429 / quota / άλλο error, πετάει Exception.
        """
        if not self.gemini_key:
            raise RuntimeError("GEMINI_API_KEY not configured")

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.gemini_model}:generateContent?key={self.gemini_key}"
        )

        payload = {
            "contents": [
                {"parts": [{"text": prompt}]}
            ]
        }

        r = requests.post(url, json=payload, timeout=60)
        if r.status_code != 200:
            # αφήνω το μήνυμα όπως στο error που είδες, για να είναι οικείο
            raise RuntimeError(
                f"Gemini HTTP {r.status_code}: {r.text[:512]}"
            )

        data = r.json()
        try:
            # κλασική δομή: candidates[0].content.parts[0].text
            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError("No candidates in Gemini response")
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if not parts:
                raise RuntimeError("No parts in Gemini response")
            text = parts[0].get("text", "")
            return text
        except Exception as e:
            raise RuntimeError(f"Gemini parse error: {e}")

    def _call_openai(self, prompt: str) -> str:
        """
        Κλήση σε OpenAI Chat.
        Χρησιμοποιεί το νέο openai SDK αν είναι διαθέσιμο.
        """
        if not self.openai_key:
            raise RuntimeError("OPENAI_API_KEY not configured")

        if not self._openai_client:
            raise RuntimeError("OpenAI client not available")

        try:
            resp = self._openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are Thronos Autonomous AI, speaking in Greek / English "
                            "with a technical but clear tone. When user asks for code, "
                            "return FULL code snippets and, when appropriate, embed "
                            "FILE blocks of the form:\n"
                            "[[FILE:filename.ext]]\n<content>\n[[/FILE]]\n"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=2048,
            )
            text = resp.choices[0].message.content
            return text
        except Exception as e:
            raise RuntimeError(f"OpenAI error: {e}")

    def _offline_reply(self, prompt: str) -> str:
        """
        Fallback όταν δεν έχουμε καθόλου API ή όλα βαράνε error.
        Δεν είναι μοντέλο, είναι απλά άνθρωπος-γραμματέας με χιούμορ.
        """
        base = (
            "[OFFLINE CORE]\n"
            "Το κεντρικό AI backend δεν είναι διαθέσιμο αυτή τη στιγμή "
            "(quota, δίκτυο ή ρυθμίσεις). "
            "Θα σου απαντήσω με ένα απλό, στατικό μήνυμα:\n\n"
        )
        tail = (
            "• Μπορείς να ξαναδοκιμάσεις σε λίγο.\n"
            "• Ή να ρυθμίσεις σωστά τα API keys (Gemini / OpenAI) "
            "στον server.\n"
        )
        return base + tail

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #
    def generate_response(self, prompt: str, wallet: Optional[str] = None) -> Dict[str, Any]:
        """
        Ενιαίο entrypoint που χρησιμοποιεί τον καλύτερο διαθέσιμο provider,
        logάρει στο ai_block_log.json, και γυρνά dict για το /api/chat.
        """
        provider = None
        model = None
        text = ""
        status = "secure"
        error_msg = None

        # 1. Προσπαθούμε με σειρά προτεραιότητας
        try:
            if self.gemini_key:
                provider = "gemini"
                model = self.gemini_model
                text = self._call_gemini(prompt)
            elif self.openai_key and self._openai_client:
                provider = "openai"
                model = self.openai_model
                text = self._call_openai(prompt)
            else:
                provider = "offline"
                model = "thronos-offline"
                text = self._offline_reply(prompt)
        except Exception as e:
            # αν έσκασε το πρώτο, δοκίμασε δεύτερο provider
            error_msg = str(e)
            logger.error("Primary AI provider error: %s", e)

            if provider == "gemini" and self.openai_key and self._openai_client:
                try:
                    provider = "openai"
                    model = self.openai_model
                    text = self._call_openai(prompt)
                    error_msg = None  # δεύτερη προσπάθεια πέτυχε
                except Exception as e2:
                    logger.error("Fallback OpenAI error: %s", e2)
                    error_msg = f"{error_msg} | Fallback: {e2}"
                    provider = "offline"
                    model = "thronos-offline"
                    text = self._offline_reply(prompt)
            elif provider == "openai" and self.gemini_key:
                try:
                    provider = "gemini"
                    model = self.gemini_model
                    text = self._call_gemini(prompt)
                    error_msg = None
                except Exception as e2:
                    logger.error("Fallback Gemini error: %s", e2)
                    error_msg = f"{error_msg} | Fallback: {e2}"
                    provider = "offline"
                    model = "thronos-offline"
                    text = self._offline_reply(prompt)
            else:
                # δεν είχαμε κανένα provider διαθέσιμο εξαρχής
                provider = provider or "offline"
                model = model or "thronos-offline"
                text = self._offline_reply(prompt)

        if error_msg:
            status = "error"

        # 2. Καταγραφή στο ai_block_log.json
        entry = {
            "wallet": wallet or "",
            "prompt": prompt,
            "response": text,
            "provider": provider,
            "model": model,
            "status": status,
            "error": error_msg,
        }
        entry = self._append_log_entry(entry)

        # 3. Επιστροφή για το /api/chat
        resp = {
            "response": text,
            "quantum_key": self.generate_quantum_key(),
            "status": status,
            "wallet": wallet or "",
            "provider": provider,
            "model": model,
            "id": entry.get("id"),
        }
        if error_msg:
            resp["error"] = error_msg
        return resp
