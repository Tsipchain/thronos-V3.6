# ai_agent_service.py
# ThronosAI – Unified AI core (Gemini / OpenAI / Local Blockchain Log)
#
# Fixes:
# - Removed duplicate ThronosAI class definitions
# - Fixed invalid import/except syntax
# - Added robust model routing via model_key (gemini-* / gpt-*)
# - Preserves existing history + block-log behavior
#
# NOTE: This file does NOT implement Claude. If UI sends "claude-*" it will be ignored.

import os
import time
import json
import secrets
import hashlib
from typing import Dict, Any, List, Optional

import requests

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

# Optional Anthropic provider
try:
    import anthropic
except Exception:
    anthropic = None


class ThronosAI:
    """
    Ενιαίο AI layer για το Thronos.

    Modes (env THRONOS_AI_MODE):
        "gemini" -> μόνο Gemini
        "openai" -> μόνο OpenAI
        "local"  -> μόνο τοπικό ιστορικό / blockchain log
        "auto"   -> Gemini -> OpenAI -> local

    Routing by model_key (request parameter):
        - if model_key starts with "gemini-" -> try Gemini with that model
        - if model_key starts with "gpt-" or "o" -> try OpenAI with that model
        - anything else (e.g. "claude-*") is ignored and we use env defaults per mode
    """

    def __init__(self) -> None:
        self.mode = os.getenv("THRONOS_AI_MODE", "auto").lower()

        # Keys
        self.gemini_api_key = (os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")).strip()
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        self.custom_model_url = os.getenv("CUSTOM_MODEL_URL", "").strip()

        # Default models
        self.gemini_model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
        self.openai_model_name = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        self.anthropic_model_name = os.getenv("ANTHROPIC_MODEL", "claude-3-sonnet")
        self.custom_model_name = os.getenv("CUSTOM_MODEL", "custom-default")

        # Data dir
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = os.getenv("DATA_DIR", os.path.join(base_dir, "data"))
        os.makedirs(self.data_dir, exist_ok=True)

        self.ai_history_file = os.path.join(self.data_dir, "ai_history.json")
        self.ai_block_log_file = os.path.join(self.data_dir, "ai_block_log.json")

        # Provider availability
        self.gemini_enabled = bool(self.gemini_api_key and genai)
        self.openai_enabled = bool(self.openai_api_key and OpenAI)
        self.anthropic_enabled = bool(self.anthropic_api_key)
        self.custom_enabled = bool(self.custom_model_url)

        self.gemini_model = None
        self.openai_client = None
        self.anthropic_client = None

        self._init_gemini()
        self._init_openai()
        self._init_anthropic()

    # ─── Provider init ──────────────────────────────────────────────────────

    def _init_gemini(self) -> None:
        if not self.gemini_enabled:
            return
        try:
            genai.configure(api_key=self.gemini_api_key)
            self.gemini_model = genai.GenerativeModel(self.gemini_model_name)
        except Exception:
            self.gemini_model = None

    def _init_openai(self) -> None:
        if not self.openai_enabled:
            return
        try:
            self.openai_client = OpenAI(api_key=self.openai_api_key)
        except Exception:
            self.openai_client = None

    def _init_anthropic(self) -> None:
        if not self.anthropic_enabled:
            return
        try:
            if anthropic:
                self.anthropic_client = anthropic.Anthropic(api_key=self.anthropic_api_key)
        except Exception:
            self.anthropic_client = None

    # ─── Utils ──────────────────────────────────────────────────────────────

    def generate_quantum_key(self) -> str:
        return secrets.token_hex(16)

    def _base_payload(self, text: str, status: str, provider: str, model: str) -> Dict[str, Any]:
        return {
            "response": text,
            "status": status,
            "provider": provider,
            "model": model,
            "quantum_key": self.generate_quantum_key(),
        }

    def _language_directive(self, lang: Optional[str]) -> str:
        lang = (lang or "").lower()
        mapping = {
            "el": "Απάντησε στα ελληνικά.",
            "en": "Respond in English.",
            "es": "Responde en español.",
            "ja": "日本語で回答してください。",
        }
        return mapping.get(lang, "Respond in the user's language.")

    def _system_prompt(self, lang: Optional[str]) -> str:
        directive = self._language_directive(lang)
        return f"""You are Thronos Autonomous AI. Answer concisely and in production-ready code when needed. {directive}

**FILE GENERATION CAPABILITY:**
When users ask you to create, edit, or generate files, use this format:

[[FILE:filename.ext]]
file content here
[[/FILE]]

Examples:
- Python script: [[FILE:miner.py]] code here [[/FILE]]
- Edited document: [[FILE:edited.txt]] content [[/FILE]]
- Configuration: [[FILE:config.json]] {...} [[/FILE]]

Multiple files can be created in one response. Always describe what you're creating before the file block."""

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

    def _call_gemini(self, prompt: str, model_name: str, lang: Optional[str]) -> Dict[str, Any]:
        if not self.gemini_enabled:
            raise RuntimeError("Gemini not available (missing key or library)")
        try:
            system_instruction = self._system_prompt(lang)

            model = genai.GenerativeModel(
                model_name,
                system_instruction=system_instruction
            )
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

    def _call_openai(self, prompt: str, model_name: str, lang: Optional[str]) -> Dict[str, Any]:
        if not self.openai_client:
            raise RuntimeError("OpenAI client not initialized")
        try:
            system_prompt = self._system_prompt(lang)

            completion = self.openai_client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
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

    def _call_anthropic(self, prompt: str, model_name: str, lang: Optional[str]) -> Dict[str, Any]:
        if not self.anthropic_enabled:
            raise RuntimeError("Anthropic not available (missing key or library)")

        started = time.time()
        model = model_name or self.anthropic_model_name
        try:
            system_prompt = self._system_prompt(lang)
            if self.anthropic_client:
                resp = self.anthropic_client.messages.create(
                    model=model,
                    max_tokens=4096,
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}],
                    timeout=30,
                )
                text = "".join([p.text for p in getattr(resp, "content", []) if hasattr(p, "text")])
            else:
                headers = {
                    "x-api-key": self.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                }
                payload = {
                    "model": model,
                    "max_tokens": 4096,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": prompt}],
                }
                r = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload,
                    timeout=30,
                )
                if r.status_code >= 400:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text}")
                data = r.json()
                text = "".join(
                    [
                        item.get("text", "")
                        for item in data.get("content", [])
                        if isinstance(item, dict)
                    ]
                )

            latency_ms = int((time.time() - started) * 1000)
            txt = (text or "").strip() or "Quantum Core: empty response from Anthropic."
            ans = self._base_payload(txt, "anthropic", "anthropic", model)
            ans["latency_ms"] = latency_ms
            return ans
        except Exception as e:
            latency_ms = int((time.time() - started) * 1000)
            ans = self._base_payload(
                f"Quantum Core Error (Anthropic): {e}", "anthropic_error", "anthropic", model
            )
            ans["latency_ms"] = latency_ms
            return ans

    def _call_custom(self, prompt: str, model_name: str, session_id: Optional[str], lang: Optional[str]) -> Dict[str, Any]:
        if not self.custom_enabled:
            raise RuntimeError("Custom model URL not configured")

        model = model_name or self.custom_model_name
        payload = {
            "prompt": prompt,
            "session_id": session_id,
            "lang": lang,
            "model": model,
        }
        last_error = None
        for _ in range(2):
            started = time.time()
            try:
                resp = requests.post(self.custom_model_url, json=payload, timeout=20)
                latency_ms = int((time.time() - started) * 1000)
                if resp.status_code >= 400:
                    last_error = f"HTTP {resp.status_code}: {resp.text}"
                    continue
                try:
                    data = resp.json()
                except Exception:
                    data = {"response": resp.text}
                text = (data.get("response") or data.get("text") or "").strip()
                if not text:
                    text = "Quantum Core: empty response from custom agent."
                ans = self._base_payload(text, "custom", "custom", model)
                ans["latency_ms"] = latency_ms
                return ans
            except Exception as e:
                last_error = str(e)

        err_payload = self._base_payload(
            f"Quantum Core Error (Custom): {last_error or 'Unknown error'}",
            "custom_error",
            "custom",
            model,
        )
        return err_payload

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
            return self._base_payload("Empty prompt.", "error", "local", "offline")

        mk = (model_key or "").strip().lower()
        lang = (kwargs.get("lang") or kwargs.get("language") or "").strip().lower() or None

        route_key = mk or self.mode or "auto"

        def store_and_return(ans: Dict[str, Any]) -> Dict[str, Any]:
            self._store_history(prompt, ans, wallet)
            return ans

        def append_error(local_ans: Dict[str, Any], err: Dict[str, Any]) -> Dict[str, Any]:
            local_ans["response"] += "\n\n---\n[Σημείωση provider]: " + err.get("response", "")
            return local_ans

        def is_success(ans: Dict[str, Any]) -> bool:
            return ans.get("status") not in {
                "gemini_error",
                "gemini_quota",
                "openai_error",
                "openai_quota",
                "anthropic_error",
                "custom_error",
            }

        # Explicit routing
        if route_key.startswith("gemini-"):
            try:
                ans = self._call_gemini(prompt, route_key, lang)
                if not is_success(ans):
                    return store_and_return(append_error(self._local_answer(prompt), ans))
                return store_and_return(ans)
            except Exception as e:
                local = self._local_answer(prompt)
                local["response"] += f"\n\n---\n[Σημείωση provider]: Gemini unavailable: {e}"
                return store_and_return(local)

        if route_key.startswith("gpt-") or route_key.startswith("o"):
            try:
                ans = self._call_openai(prompt, route_key, lang)
                if not is_success(ans):
                    return store_and_return(append_error(self._local_answer(prompt), ans))
                return store_and_return(ans)
            except Exception as e:
                local = self._local_answer(prompt)
                local["response"] += f"\n\n---\n[Σημείωση provider]: OpenAI unavailable: {e}"
                return store_and_return(local)

        if route_key.startswith("claude-"):
            try:
                ans = self._call_anthropic(prompt, route_key, lang)
                if not is_success(ans):
                    return store_and_return(append_error(self._local_answer(prompt), ans))
                return store_and_return(ans)
            except Exception as e:
                local = self._local_answer(prompt)
                local["response"] += f"\n\n---\n[Σημείωση provider]: Anthropic unavailable: {e}"
                return store_and_return(local)

        if route_key.startswith("custom-"):
            try:
                ans = self._call_custom(prompt, route_key, session_id, lang)
                if not is_success(ans):
                    return store_and_return(append_error(self._local_answer(prompt), ans))
                return store_and_return(ans)
            except Exception as e:
                local = self._local_answer(prompt)
                local["response"] += f"\n\n---\n[Σημείωση provider]: Custom agent unavailable: {e}"
                return store_and_return(local)

        if route_key == "local":
            return store_and_return(self._local_answer(prompt))

        # AUTO pipeline: gemini -> openai -> anthropic -> local
        last_err = None

        if self.gemini_enabled:
            try:
                a = self._call_gemini(prompt, self.gemini_model_name, lang)
                if is_success(a):
                    return store_and_return(a)
                last_err = a
            except Exception as e:
                last_err = self._base_payload(f"Gemini unavailable: {e}", "gemini_error", "gemini", self.gemini_model_name)

        if self.openai_client:
            try:
                a = self._call_openai(prompt, self.openai_model_name, lang)
                if is_success(a):
                    return store_and_return(a)
                last_err = a
            except Exception as e:
                last_err = self._base_payload(f"OpenAI unavailable: {e}", "openai_error", "openai", self.openai_model_name)

        if self.anthropic_enabled:
            try:
                a = self._call_anthropic(prompt, self.anthropic_model_name, lang)
                if is_success(a):
                    return store_and_return(a)
                last_err = a
            except Exception as e:
                last_err = self._base_payload(f"Anthropic unavailable: {e}", "anthropic_error", "anthropic", self.anthropic_model_name)

        local = self._local_answer(prompt)
        if last_err:
            local = append_error(local, last_err)
        return store_and_return(local)
