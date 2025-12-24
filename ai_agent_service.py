# ai_agent_service.py
# ThronosAI – Unified AI core (Gemini / OpenAI / Local Blockchain Log)
#
# Fixes:
# - Single ThronosAI class (no duplicates)
# - Correct try/except imports
# - model_key routing: gemini-* / gpt-* / o* ; "auto" treated as no override
# - Always returns provider/model/status and includes debug block
# - Preserves ai_history.json + ai_block_log.json logging

import os
import time
import json
import secrets
import hashlib
from typing import Dict, Any, List, Optional

# Optional Gemini provider
try:
    import google.generativeai as genai
except Exception:
    genai = None

# Optional OpenAI provider
try:
    from openai import OpenAI
except Exception:
    OpenAI = None


class ThronosAI:
    def __init__(self) -> None:
        self.mode = os.getenv("THRONOS_AI_MODE", "auto").lower()

        # Keys
        self.gemini_api_key = (os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")).strip()
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()

        # Default models
        self.gemini_model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
        self.openai_model_name = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

        # Data dir
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = os.getenv("DATA_DIR", os.path.join(base_dir, "data"))
        os.makedirs(self.data_dir, exist_ok=True)

        self.ai_history_file = os.path.join(self.data_dir, "ai_history.json")
        self.ai_block_log_file = os.path.join(self.data_dir, "ai_block_log.json")

        # Provider availability
        self.gemini_enabled = bool(self.gemini_api_key and genai)
        self.openai_enabled = bool(self.openai_api_key and OpenAI)

        self.openai_client = None
        self._init_openai()

        # Configure Gemini once (models are created per-request to support overrides cleanly)
        if self.gemini_enabled:
            try:
                genai.configure(api_key=self.gemini_api_key)
            except Exception:
                self.gemini_enabled = False

    def _init_openai(self) -> None:
        if not self.openai_enabled:
            return
        try:
            self.openai_client = OpenAI(api_key=self.openai_api_key)
        except Exception:
            self.openai_client = None

    # ─── Utils ──────────────────────────────────────────────────────────────

    def generate_quantum_key(self) -> str:
        return secrets.token_hex(16)

    def _base_payload(self, text: str, status: str, provider: str, model: str) -> Dict[str, Any]:
        payload = {
            "response": text,
            "status": status,
            "provider": provider,
            "model": model,
            "quantum_key": self.generate_quantum_key(),
        }
        return payload

    def _attach_debug(self, ans: Dict[str, Any], requested_model: Optional[str]) -> Dict[str, Any]:
        try:
            ans["debug"] = {
                "requested_model": requested_model,
                "mode": self.mode,
                "used_provider": ans.get("provider"),
                "used_model": ans.get("model"),
            }
        except Exception:
            pass
        return ans

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
        except Exception:
            pass

    def _append_block_log(self, entry: Dict[str, Any]) -> None:
        try:
            try:
                with open(self.ai_block_log_file, "r", encoding="utf-8") as f:
                    items = json.load(f)
            except Exception:
                items = []

            items.append(entry)
            if len(items) > 2000:
                items = items[-2000:]

            with open(self.ai_block_log_file, "w", encoding="utf-8") as f:
                json.dump(items, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _hash_short(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]

    def _store_history(self, prompt: str, answer: Dict[str, Any], wallet: Optional[str]) -> None:
        items = self._load_history()
        items.append({
            "ts": int(time.time()),
            "wallet": wallet or None,
            "prompt": prompt,
            "response": answer.get("response", ""),
            "status": answer.get("status", ""),
            "provider": answer.get("provider", ""),
            "model": answer.get("model", ""),
        })
        if len(items) > 500:
            items = items[-500:]
        self._save_history(items)

        entry = {
            "id": f"{int(time.time()*1000)}-{secrets.token_hex(4)}",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "wallet": wallet or None,
            "prompt": prompt,
            "response": answer.get("response", ""),
            "status": answer.get("status", ""),
            "provider": answer.get("provider", ""),
            "model": answer.get("model", ""),
            "prompt_hash": self._hash_short(prompt),
            "response_hash": self._hash_short(answer.get("response", "")),
        }
        self._append_block_log(entry)

    # ─── Provider calls ─────────────────────────────────────────────────────

    def _call_gemini(self, prompt: str, model_name: str) -> Dict[str, Any]:
        if not self.gemini_enabled or not genai:
            raise RuntimeError("Gemini not available (missing key or library)")
        try:
            model = genai.GenerativeModel(model_name)
            resp = model.generate_content(prompt)
            txt = (getattr(resp, "text", "") or "").strip()
            if not txt:
                txt = "Quantum Core: empty response from Gemini."
            return self._base_payload(txt, "gemini", "gemini", model_name)
        except Exception as e:
            msg = str(e)
            if "quota" in msg.lower() or "exceeded" in msg.lower() or "429" in msg:
                return self._base_payload("Quantum Core Notice: Gemini quota/rate limit.", "gemini_quota", "gemini", model_name)
            return self._base_payload(f"Quantum Core Error (Gemini): {msg}", "gemini_error", "gemini", model_name)

    def _call_openai(self, prompt: str, model_name: str) -> Dict[str, Any]:
        if not self.openai_client:
            raise RuntimeError("OpenAI client not initialized")
        try:
            completion = self.openai_client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are Thronos Autonomous AI. Answer concisely and in production-ready code when needed."},
                    {"role": "user", "content": prompt},
                ],
            )
            txt = (completion.choices[0].message.content or "").strip()
            if not txt:
                txt = "Quantum Core: empty response from OpenAI."
            return self._base_payload(txt, "openai", "openai", model_name)
        except Exception as e:
            msg = str(e)
            if "rate limit" in msg.lower() or "quota" in msg.lower() or "429" in msg:
                return self._base_payload("Quantum Core Notice: OpenAI quota/rate limit.", "openai_quota", "openai", model_name)
            return self._base_payload(f"Quantum Core Error (OpenAI): {msg}", "openai_error", "openai", model_name)

    # ─── Local / blockchain knowledge ──────────────────────────────────────

    def _local_answer(self, prompt: str) -> Dict[str, Any]:
        prompt_l = prompt.lower()
        words = [w for w in prompt_l.split() if len(w) > 3]

        history = self._load_history()
        if not history:
            return self._base_payload(
                "Το Quantum Core δεν έχει ακόμη αρκετά αποθηκευμένα δεδομένα στο blockchain log.",
                "local_empty",
                "local",
                "offline_corpus",
            )

        best = None
        best_score = -1.0
        for rec in history:
            hay = (rec.get("prompt", "") + " " + rec.get("response", "")).lower()
            score = 0.0
            for w in words:
                if w in hay:
                    score += 1.0
            score += (rec.get("ts", 0) / 1_000_000_000.0)
            if score > best_score:
                best_score = score
                best = rec

        if not best or best_score <= 0:
            return self._base_payload(
                "Δεν βρήκα σχετικό block γνώσης στο τοπικό αρχείο.",
                "local_miss",
                "local",
                "offline_corpus",
            )

        text = "Απάντηση από το τοπικό blockchain log (offline γνώση):\n\n" + best.get("response", "")
        return self._base_payload(text, "local", "local", "offline_corpus")

    # ─── Public API ─────────────────────────────────────────────────────────

    def generate_response(self, prompt: str, wallet: Optional[str] = None, model_key: Optional[str] = None, session_id: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        prompt = (prompt or "").strip()
        if not prompt:
            return self._attach_debug(self._base_payload("Empty prompt.", "error", "local", "offline"), model_key)

        mk = (model_key or "").strip().lower()
        # UI may send "auto" as a dropdown value. Treat as "no override".
        if mk == "auto":
            mk = ""

        gemini_override = mk if mk.startswith("gemini-") else None
        openai_override = mk if (mk.startswith("gpt-") or mk.startswith("o")) else None

        # LOCAL
        if self.mode == "local":
            ans = self._local_answer(prompt)
            self._store_history(prompt, ans, wallet)
            return self._attach_debug(ans, model_key)

        # GEMINI ONLY
        if self.mode == "gemini":
            try:
                ans = self._call_gemini(prompt, gemini_override or self.gemini_model_name)
                if ans["status"] in ("gemini_quota", "gemini_error"):
                    local = self._local_answer(prompt)
                    local["response"] += "\n\n---\n[Σημείωση provider]: " + ans.get("response", "")
                    ans = local
            except Exception as e:
                ans = self._local_answer(prompt)
                ans["response"] += "\n\n---\n[Σημείωση provider]: Gemini unavailable: " + str(e)
            self._store_history(prompt, ans, wallet)
            return self._attach_debug(ans, model_key)

        # OPENAI ONLY
        if self.mode == "openai":
            try:
                ans = self._call_openai(prompt, openai_override or self.openai_model_name)
                if ans["status"] in ("openai_quota", "openai_error"):
                    local = self._local_answer(prompt)
                    local["response"] += "\n\n---\n[Σημείωση provider]: " + ans.get("response", "")
                    ans = local
            except Exception as e:
                ans = self._local_answer(prompt)
                ans["response"] += "\n\n---\n[Σημείωση provider]: OpenAI unavailable: " + str(e)
            self._store_history(prompt, ans, wallet)
            return self._attach_debug(ans, model_key)

        # AUTO: (model_key asks OpenAI) -> Gemini -> OpenAI -> Local
        last_err = None

        if openai_override and self.openai_client:
            a = self._call_openai(prompt, openai_override)
            if a["status"] not in ("openai_quota", "openai_error"):
                self._store_history(prompt, a, wallet)
                return self._attach_debug(a, model_key)
            last_err = a

        if self.gemini_enabled:
            a = self._call_gemini(prompt, gemini_override or self.gemini_model_name)
            if a["status"] not in ("gemini_quota", "gemini_error"):
                self._store_history(prompt, a, wallet)
                return self._attach_debug(a, model_key)
            last_err = a

        if self.openai_client:
            a = self._call_openai(prompt, openai_override or self.openai_model_name)
            if a["status"] not in ("openai_quota", "openai_error"):
                self._store_history(prompt, a, wallet)
                return self._attach_debug(a, model_key)
            last_err = a

        local = self._local_answer(prompt)
        if last_err:
            local["response"] += "\n\n---\n[Σημείωση provider]: " + last_err.get("response", "")
        self._store_history(prompt, local, wallet)
        return self._attach_debug(local, model_key)
