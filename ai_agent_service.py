import os
import secrets
import time
import json
from typing import Dict, Any, List

# Προαιρετικοί clients – αν δεν υπάρχουν τα πακέτα, απλά γυρνάμε σε local mode
try:
    import google.generativeai as genai
except ImportError:
    genai = None  # type: ignore[assignment]

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore[assignment]


class ThronosAI:
    def __init__(self) -> None:
        """
        Mode:
          - "gemini"  -> μόνο Gemini
          - "openai"  -> μόνο OpenAI
          - "auto"    -> πρώτα Gemini, μετά OpenAI, μετά local
          - "local"   -> καθόλου external, μόνο blockchain/local
        """
        self.mode = os.getenv("THRONOS_AI_MODE", "auto").lower()

        # 👉 Κλειδιά: διαβάζουμε ΚΑΙ GEMINI_API_KEY ΚΑΙ GOOGLE_API_KEY (fallback)
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

        self.gemini_model = None        # type: ignore[assignment]
        self.openai_client = None       # type: ignore[assignment]

        # αρχικοποίηση providers
        self._init_gemini()
        self._init_openai()

    # ─── INIT PROVIDERS ─────────────────────────────

    def _init_gemini(self) -> None:
        """Ενεργοποίηση Gemini client (αν υπάρχει κλειδί + βιβλιοθήκη)."""
        if not self.gemini_api_key or not genai:
            return
        try:
            genai.configure(api_key=self.gemini_api_key)
            self.gemini_model = genai.GenerativeModel(self.gemini_model_name)
            print(f"[ThronosAI] Gemini online ({self.gemini_model_name})")
        except Exception as e:
            print("[ThronosAI] Gemini init error:", e)
            self.gemini_model = None

    def _init_openai(self) -> None:
        """Ενεργοποίηση OpenAI client (αν υπάρχει κλειδί + πακέτο)."""
        if not self.openai_api_key or not OpenAI:
            return
        try:
            self.openai_client = OpenAI(api_key=self.openai_api_key)
            print(f"[ThronosAI] OpenAI online ({self.openai_model_name})")
        except Exception as e:
            print("[ThronosAI] OpenAI init error:", e)
            self.openai_client = None

    # ─── UTILS ──────────────────────────────────────

    def generate_quantum_key(self) -> str:
        return secrets.token_hex(16)

    def _base_payload(self, text: str, status: str = "online") -> Dict[str, Any]:
        return {
            "response": text,
            "status": status,
            "quantum_key": self.generate_quantum_key(),
        }

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
        Condensed log στο ai_block_log.json.
        Από εκεί το σηκώνει Whisper / Survival node για κανονικά blocks.
        """
        try:
            try:
                with open(self.ai_block_log_file, "r", encoding="utf-8") as f:
                    items = json.load(f)
            except Exception:
                items = []
            items.append(entry)
            with open(self.ai_block_log_file, "w", encoding="utf-8") as f:
                json.dump(items, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print("[ThronosAI] Failed to append block-log:", e)

    def _store_history(self, prompt: str, answer: Dict[str, Any], wallet: str | None) -> None:
        """Γράφει full history + condensed block log."""
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

        block_rec = {
            "ts": rec["ts"],
            "wallet": rec["wallet"],
            "prompt_hash": self._hash_short(rec["prompt"]),
            "response_hash": self._hash_short(rec["response"]),
            "status": rec["status"],
        }
        self._append_block_log(block_rec)

    def _hash_short(self, text: str) -> str:
        import hashlib
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return h[:24]

    # ─── PROVIDERS ──────────────────────────────────

    def _call_gemini(self, prompt: str) -> Dict[str, Any]:
        if not self.gemini_model:
            raise RuntimeError("Gemini model not initialized")
        try:
            resp = self.gemini_model.generate_content(prompt)
            txt = (getattr(resp, "text", "") or "").strip()
            if not txt:
                txt = "Quantum Core: empty response from Gemini."
            return self._base_payload(txt, status="gemini")
        except Exception as e:
            msg = str(e)
            if "quota" in msg.lower() or "exceeded" in msg.lower() or "429" in msg:
                return self._base_payload(
                    "Quantum Core Notice: Το εξωτερικό AI (Gemini) δεν έχει πλέον διαθέσιμα credits "
                    "ή έχει ξεπεραστεί το όριο χρήσης. Χρήση τοπικής blockchain γνώσης.",
                    status="quota_exceeded",
                )
            return self._base_payload(
                f"Quantum Core Error (Gemini): {msg}",
                status="error",
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
            txt = completion.choices[0].message.content
            txt = (txt or "").strip()
            if not txt:
                txt = "Quantum Core: empty response from OpenAI."
            return self._base_payload(txt, status="openai")
        except Exception as e:
            msg = str(e)
            if "rate limit" in msg.lower() or "quota" in msg.lower() or "429" in msg:
                return self._base_payload(
                    "Quantum Core Notice: Το εξωτερικό AI (OpenAI) είναι σε rate limit / quota. "
                    "Χρήση τοπικής blockchain γνώσης.",
                    status="quota_exceeded",
                )
            return self._base_payload(
                f"Quantum Core Error (OpenAI): {msg}",
                status="error",
            )

    # ─── LOCAL / BLOCKCHAIN KNOWLEDGE ───────────────

    def _local_answer(self, prompt: str) -> Dict[str, Any]:
        """
        Όταν δεν έχουμε provider ή quota, ψάχνουμε στο τοπικό history.
        Απλό keyword matching, αλλά είναι ΠΡΑΓΜΑΤΙΚΑ δεδομένα του χρήστη.
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
            score = 0
            for w in words:
                if w in hay:
                    score += 1
            # μικρό μπόνους στα πιο πρόσφατα
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

    # ─── PUBLIC API ─────────────────────────────────

    def generate_response(self, prompt: str, wallet: str | None = None) -> Dict[str, Any]:
        """
        Κεντρική μέθοδος:
        - Δοκιμάζει external providers (ανάλογα με το mode)
        - Αν έχουν quota / error, πέφτει σε τοπική blockchain γνώση
        - Ό,τι απάντηση βγει, γράφεται σε history + ai_block_log.json
        """
        prompt = (prompt or "").strip()
        if not prompt:
            return self._base_payload("Empty prompt.", status="error")

        mode = self.mode

        # 1) Μόνο local
        if mode == "local":
            answer = self._local_answer(prompt)
            self._store_history(prompt, answer, wallet)
            return answer

        # 2) Μόνο Gemini
        if mode == "gemini":
            if not self.gemini_model:
                answer = self._local_answer(prompt)
            else:
                answer = self._call_gemini(prompt)
                if answer.get("status") in ("quota_exceeded", "error"):
                    local = self._local_answer(prompt)
                    local["response"] += (
                        "\n\n---\n[Σημείωση provider]: " + answer.get("response", "")
                    )
                    answer = local
            self._store_history(prompt, answer, wallet)
            return answer

        # 3) Μόνο OpenAI
        if mode == "openai":
            if not self.openai_client:
                answer = self._local_answer(prompt)
            else:
                answer = self._call_openai(prompt)
                if answer.get("status") in ("quota_exceeded", "error"):
                    local = self._local_answer(prompt)
                    local["response"] += (
                        "\n\n---\n[Σημείωση provider]: " + answer.get("response", "")
                    )
                    answer = local
            self._store_history(prompt, answer, wallet)
            return answer

        # 4) auto – πρώτα Gemini, μετά OpenAI, μετά local
        answer: Dict[str, Any] | None = None
        last_err: Dict[str, Any] | None = None

        if self.gemini_model:
            ans_g = self._call_gemini(prompt)
            if ans_g.get("status") not in ("quota_exceeded", "error"):
                answer = ans_g
            else:
                last_err = ans_g

        if answer is None and self.openai_client:
            ans_o = self._call_openai(prompt)
            if ans_o.get("status") not in ("quota_exceeded", "error"):
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
