# ai_agent_service.py
# ThronosAI – Unified AI core (Gemini / OpenAI / Local Blockchain Log)

import os
import time
import json
import secrets
import hashlib
from typing import Dict, Any, List, Optional

# Optional providers
import google.generativeai as genai
except ImportError:
    genai = None

class ThronosAI:
    def __init__(self):
        self.gemini_api_key = (os.getenv("GEMINI_API_KEY","") or os.getenv("GOOGLE_API_KEY","")).strip()
        self.default_model = os.getenv("GEMINI_MODEL","gemini-2.5-pro")
        if self.gemini_api_key and genai:
            genai.configure(api_key=self.gemini_api_key)

    def generate_response(self, prompt, wallet=None, model_key=None, session_id=None, **kwargs):
        model = model_key if model_key and model_key.startswith("gemini-") else self.default_model
        try:
            if not genai or not self.gemini_api_key:
                raise RuntimeError("Gemini not available")
            m = genai.GenerativeModel(model)
            r = m.generate_content(prompt)
            return {
                "response": (getattr(r,"text","") or "").strip(),
                "provider": "gemini",
                "model": model,
                "status": "online",
                "quantum_key": secrets.token_hex(16)
            }
        except Exception:
            return {
                "response": "Απάντηση από το τοπικό blockchain log (offline γνώση).",
                "provider": "local",
                "model": "offline",
                "status": "offline",
                "quantum_key": secrets.token_hex(16)
            }


try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


class ThronosAI:
    """
    Ενιαίο AI layer για το Thronos:

    - mode:
        "gemini"  -> μόνο Gemini
        "openai"  -> μόνο OpenAI
        "local"   -> μόνο τοπικό ιστορικό / blockchain log
        "auto"    -> Gemini -> OpenAI -> local

    - Κάθε απάντηση:
        * γράφεται σε ai_history.json (full prompt/response)
        * γράφεται σε ai_block_log.json με πλήρη στοιχεία
          (ώστε το ai_knowledge_watcher στο server.py
           να τα μετατρέπει σε κανονικά TXs τύπου ai_knowledge)
    """

    def __init__(self) -> None:
        # ---- Modes & keys ---------------------------------------------------
        self.mode = os.getenv("THRONOS_AI_MODE", "auto").lower()

        # Παίρνουμε key είτε από GEMINI_API_KEY είτε από GOOGLE_API_KEY
        self.gemini_api_key = (
            os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
        ).strip()
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()

        # Default models – μπορείς να τα αλλάξεις από env
        self.gemini_model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
        self.openai_model_name = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

        # ---- Data dir -------------------------------------------------------
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = os.getenv("DATA_DIR", os.path.join(base_dir, "data"))
        os.makedirs(self.data_dir, exist_ok=True)

        self.ai_history_file = os.path.join(self.data_dir, "ai_history.json")
        self.ai_block_log_file = os.path.join(self.data_dir, "ai_block_log.json")

        # ---- Provider clients ----------------------------------------------
        self.gemini_model = None  # type: ignore[assignment]
        self.openai_client = None  # type: ignore[assignment]

        self._init_gemini()
        self._init_openai()

    # ─── Provider init ──────────────────────────────────────────────────────

    def _init_gemini(self) -> None:
        if not self.gemini_api_key or not genai:
            print("[ThronosAI] Gemini not configured (missing key or library).")
            return
        try:
            genai.configure(api_key=self.gemini_api_key)
            self.gemini_model = genai.GenerativeModel(self.gemini_model_name)
            print(f"[ThronosAI] Gemini online ({self.gemini_model_name})")
        except Exception as e:
            print("[ThronosAI] Gemini init error:", e)
            self.gemini_model = None

    def _init_openai(self) -> None:
        if not self.openai_api_key or not OpenAI:
            print("[ThronosAI] OpenAI not configured (missing key or library).")
            return
        try:
            self.openai_client = OpenAI(api_key=self.openai_api_key)
            print(f"[ThronosAI] OpenAI online ({self.openai_model_name})")
        except Exception as e:
            print("[ThronosAI] OpenAI init error:", e)
            self.openai_client = None

    # ─── Utils ──────────────────────────────────────────────────────────────

    def generate_quantum_key(self) -> str:
        return secrets.token_hex(16)

    def _base_payload(self, text: str, status: str = "online") -> Dict[str, Any]:
        return {
            "response": text,
            "status": status,
            "quantum_key": self.generate_quantum_key(),
        }

    # ─── History storage ────────────────────────────────────────────────────

    def _load_history(self) -> List[Dict[str, Any]]:
        try:
            with open(self.ai_history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_history(self, items: List[Dict[str, Any]]) -> None:
        try:
            with open(self.ai_history_file, "w", encoding="utf-8") as f:
                json.dump(items, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print("[ThronosAI] Failed to save history:", e)

    def _append_block_log(self, entry: Dict[str, Any]) -> None:
        """
        Γράφει πλήρες log στο ai_block_log.json.
        Μορφή που περιμένει το ai_knowledge_watcher στο server.py:
          {
            "id": "...",
            "timestamp": ...,
            "wallet": "...",
            "prompt": "...",
            "response": "...",
            "status": "gemini|openai|local|...",
            "provider": "gemini|openai|local",
            "model": "gemini-2.5-pro|gpt-4.1-mini|offline"
          }
        """
        try:
            try:
                with open(self.ai_block_log_file, "r", encoding="utf-8") as f:
                    items = json.load(f)
            except Exception:
                items = []

            items.append(entry)

            # προαιρετικό trimming
            if len(items) > 2000:
                items = items[-2000:]

            with open(self.ai_block_log_file, "w", encoding="utf-8") as f:
                json.dump(items, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print("[ThronosAI] Failed to append block-log:", e)

    def _hash_short(self, text: str) -> str:
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return h[:24]

    def _store_history(self, prompt: str, answer: Dict[str, Any], wallet: Optional[str]) -> None:
        # --- Full history (για local knowledge) -----------------------------
        items = self._load_history()

        rec = {
            "ts": int(time.time()),
            "wallet": wallet or None,
            "prompt": prompt,
            "response": answer.get("response", ""),
            "status": answer.get("status", ""),
        }
        items.append(rec)
        if len(items) > 500:
            items = items[-500:]
        self._save_history(items)

        # --- Block-log entry (για ai_knowledge TXs) -------------------------
        status = (answer.get("status") or "").lower()
        if status.startswith("gemini"):
            provider = "gemini"
            model = self.gemini_model_name
        elif status.startswith("openai"):
            provider = "openai"
            model = self.openai_model_name
        elif status.startswith("local"):
            provider = "local"
            model = "offline_corpus"
        else:
            provider = status or "unknown"
            model = "unknown"

        block_entry = {
            "id": f"{int(time.time()*1000)}-{secrets.token_hex(4)}",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "wallet": wallet or None,
            "prompt": prompt,
            "response": answer.get("response", ""),
            "status": answer.get("status", ""),
            "provider": provider,
            "model": model,
            "prompt_hash": self._hash_short(prompt),
            "response_hash": self._hash_short(answer.get("response", "")),
        }
        self._append_block_log(block_entry)

    # ─── Provider calls ─────────────────────────────────────────────────────

    def _call_gemini(self, prompt: str) -> Dict[str, Any]:
        if not self.gemini_model:
            raise RuntimeError("Gemini model not initialized")
        try:
            resp = self.gemini_model.generate_content(prompt)
            txt = (getattr(resp, "text", "") or "").strip()
            if not txt:
                txt = "Quantum Core: empty response from Gemini."
            payload = self._base_payload(txt, status="gemini")
            return payload
        except Exception as e:
            msg = str(e)
            if "quota" in msg.lower() or "exceeded" in msg.lower() or "429" in msg:
                return self._base_payload(
                    "Quantum Core Notice: Το εξωτερικό AI (Gemini) δεν έχει διαθέσιμα credits "
                    "ή έχει ξεπεραστεί το όριο χρήσης. Χρήση τοπικής blockchain γνώσης.",
                    status="gemini_quota",
                )
            return self._base_payload(
                f"Quantum Core Error (Gemini): {msg}",
                status="gemini_error",
            )

    def _call_openai(self, prompt: str) -> Dict[str, Any]:
        if not self.openai_client:
            raise RuntimeError("OpenAI client not initialized")
        try:
            completion = self.openai_client.chat.completions.create(
                model=self.openai_model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are the Thronos Autonomous AI, integrated in a blockchain environment. "
                            "Answer concisely and in production-ready code when needed."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            txt = completion.choices[0].message.content or ""
            txt = txt.strip()
            if not txt:
                txt = "Quantum Core: empty response from OpenAI."
            return self._base_payload(txt, status="openai")
        except Exception as e:
            msg = str(e)
            if "rate limit" in msg.lower() or "quota" in msg.lower() or "429" in msg:
                return self._base_payload(
                    "Quantum Core Notice: Το εξωτερικό AI (OpenAI) είναι σε rate limit / quota. "
                    "Χρήση τοπικής blockchain γνώσης.",
                    status="openai_quota",
                )
            return self._base_payload(
                f"Quantum Core Error (OpenAI): {msg}",
                status="openai_error",
            )

    # ─── Local / blockchain knowledge ──────────────────────────────────────

    def _local_answer(self, prompt: str) -> Dict[str, Any]:
        """
        Πολύ απλό keyword-based retrieval από το ai_history.json.
        Δεν είναι embeddings, αλλά είναι *πραγματικά* δεδομένα από το δίκτυο.
        """
        prompt_l = prompt.lower()
        words = [w for w in prompt_l.split() if len(w) > 3]

        history = self._load_history()
        if not history:
            text = (
                "Το Quantum Core δεν έχει ακόμη αρκετά αποθηκευμένα δεδομένα στο blockchain log.\n"
                "Συνέχισε να του δίνεις εντολές και κώδικα· κάθε καλή απάντηση αποθηκεύεται ως block γνώσης."
            )
            return self._base_payload(text, status="local_empty")

        best = None
        best_score = -1.0

        for rec in history:
            hay = (rec.get("prompt", "") + " " + rec.get("response", "")).lower()
            score = 0.0
            for w in words:
                if w in hay:
                    score += 1.0
            # μικρό weight για πιο πρόσφατα
            score += (rec.get("ts", 0) / 1_000_000_000.0)
            if score > best_score:
                best_score = score
                best = rec

        if not best or best_score <= 0:
            text = (
                "Δεν βρήκα σχετικό block γνώσης στο τοπικό αρχείο.\n"
                "Θα χρειαστούν περισσότερα παραδείγματα για να μάθει αυτόν τον τύπο ερωτήσεων."
            )
            return self._base_payload(text, status="local_miss")

        text = (
            "Απάντηση από το τοπικό blockchain log (offline γνώση):\n\n"
            + best.get("response", "")
        )
        return self._base_payload(text, status="local")

    # ─── Public API ─────────────────────────────────────────────────────────

    def generate_response(self, prompt: str, wallet: Optional[str] = None, model_key: Optional[str] = None, session_id: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Κεντρική μέθοδος:
        - Προσπαθεί provider(s) ανάλογα με mode
        - Αν πέσουν σε quota/error -> πέφτει σε local
        - Σε κάθε περίπτωση, γράφει ιστορικό + block_log
        """
        prompt = (prompt or "").strip()
        if not prompt:
            return self._base_payload("Empty prompt.", status="error")

        mode = self.mode
        answer: Dict[str, Any]

        # 1) Καθαρά local
        if mode == "local":
            answer = self._local_answer(prompt)
            self._store_history(prompt, answer, wallet)
            return answer

        # 2) Gemini only
        if mode == "gemini":
            if not self.gemini_model:
                answer = self._local_answer(prompt)
            else:
                answer = self._call_gemini(prompt)
                if answer.get("status") in ("gemini_quota", "gemini_error"):
                    local = self._local_answer(prompt)
                    local["response"] += (
                        "\n\n---\n[Σημείωση provider]: " + answer.get("response", "")
                    )
                    answer = local
            self._store_history(prompt, answer, wallet)
            return answer

        # 3) OpenAI only
        if mode == "openai":
            if not self.openai_client:
                answer = self._local_answer(prompt)
            else:
                answer = self._call_openai(prompt)
                if answer.get("status") in ("openai_quota", "openai_error"):
                    local = self._local_answer(prompt)
                    local["response"] += (
                        "\n\n---\n[Σημείωση provider]: " + answer.get("response", "")
                    )
                    answer = local
            self._store_history(prompt, answer, wallet)
            return answer

        # 4) auto mode – Gemini -> OpenAI -> Local
        answer = None  # type: ignore[assignment]
        last_err = None

        if self.gemini_model:
            ans_g = self._call_gemini(prompt)
            if ans_g.get("status") not in ("gemini_quota", "gemini_error"):
                answer = ans_g
            else:
                last_err = ans_g

        if answer is None and self.openai_client:
            ans_o = self._call_openai(prompt)
            if ans_o.get("status") not in ("openai_quota", "openai_error"):
                answer = ans_o
            else:
                last_err = ans_o

        if answer is None:
            answer = self._local_answer(prompt)
            if last_err is not None:
                answer["response"] += (
                    "\n\n---\n[Σημείωση provider]: " + last_err.get("response", "")
                )

        self._store_history(prompt, answer, wallet)
        return answer
