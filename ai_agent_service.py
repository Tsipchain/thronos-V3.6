# ai_agent_service.py
# ThronosAI – Unified AI core (Gemini / OpenAI / Local Blockchain Log)
#
# Fixes:
# - Removed duplicate ThronosAI class definitions
# - Fixed invalid import/except syntax
# - Added robust model routing via model_key (gemini-* / gpt-*)
# - Preserves existing history + block-log behavior
#
# NOTE: Supports Gemini, OpenAI, Anthropic (Claude), and custom Thrai agent routing.

import os
import time
import json
import secrets
import hashlib
import logging
from typing import Dict, Any, List, Optional

import requests

logger = logging.getLogger("thronos")

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

try:
    from ai_router import ThronosAIScorer  # type: ignore
except Exception:
    ThronosAIScorer = None  # type: ignore

from ai_interaction_ledger import record_ai_interaction
from llm_registry import (
    find_model,
    get_default_model,
    list_enabled_model_ids,
    AI_MODEL_REGISTRY,
    get_provider_status,
    mark_model_disabled,
)


def _resolve_model(
    model: Optional[str],
    normalized_mode: Optional[str] = None,
    provider_status: Optional[dict] = None,
    wallet: Optional[str] = None,
):
    raw_mode = normalized_mode or (os.getenv("THRONOS_AI_MODE", "all").strip().lower() or "all")
    if raw_mode in ("router", "auto", "all", "hybrid", "proxy", "core"):
        normalized_mode = "all"
    elif raw_mode == "openai_only":
        normalized_mode = "openai"
    else:
        normalized_mode = raw_mode

    provider_status = provider_status or get_provider_status()

    logger.info("[AI_MODEL] resolve model_id=%s raw_mode=%s normalized=%s wallet=%s", model, raw_mode, normalized_mode, wallet)

    def _provider_configured(provider: str) -> bool:
        info = provider_status.get(provider) if isinstance(provider_status, dict) else None

        def _has_env_key(p: str) -> bool:
            if p == "openai":
                return bool((os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY") or "").strip())
            if p == "anthropic":
                return bool((os.getenv("ANTHROPIC_API_KEY") or "").strip())
            if p == "gemini":
                return bool((os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip())
            return False

        if info and info.get("enabled") is False and not _has_env_key(provider):
            return False

        if provider == "local":
            return True

        if provider in ("thronos", "custom", "diko_mas"):
            custom_url = (
                os.getenv("CUSTOM_MODEL_URL", "").strip()
                or os.getenv("CUSTOM_MODEL_URI", "").strip()
                or os.getenv("DIKO_MAS_MODEL_URL", "").strip()
            )
            return bool(custom_url)

        if info:
            if not info.get("configured"):
                return False
            if info.get("library_loaded") is False:
                return False
            return True

        # Fallback directly to env detection if status payload is missing/empty
        return _has_env_key(provider)

    def _match_alias(candidate: str):
        cand_norm = (candidate or "").strip().lower().replace(" ", "").replace("-", "")
        for provider_models in AI_MODEL_REGISTRY.values():
            for m in provider_models:
                display_norm = m.display_name.lower().replace(" ", "").replace("-", "")
                if cand_norm == display_norm:
                    return m
        return None

    if not model or model == "auto":
        env_default_id = (os.getenv("THRONOS_DEFAULT_MODEL_ID") or "gpt-4.1-mini").strip()
        if env_default_id:
            env_default = find_model(env_default_id) or _match_alias(env_default_id)
            if env_default and (normalized_mode in ("all", env_default.provider)) and _provider_configured(env_default.provider):
                return env_default

        fallback = get_default_model(None if normalized_mode == "all" else normalized_mode)
        if fallback and _provider_configured(fallback.provider):
            return fallback

        for provider_name, model_list in AI_MODEL_REGISTRY.items():
            if normalized_mode != "all" and provider_name != normalized_mode:
                continue
            if not _provider_configured(provider_name):
                continue
            if model_list:
                return model_list[0]
        return None

    info = find_model(model) or _match_alias(model)
    if not info:
        return None

    if normalized_mode != "all" and info.provider != normalized_mode:
        return None
    if not _provider_configured(info.provider):
        return None
    return info


def call_openai(model: str, messages: List[Dict[str, str]], system_prompt: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 4096) -> Dict[str, Any]:
    api_key = (os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY") or "").strip()
    if not api_key:
        logging.warning("missing OPENAI_API_KEY")
        raise RuntimeError("OpenAI API key missing")

    if system_prompt:
        messages = ([{"role": "system", "content": system_prompt}] + messages)

    client = OpenAI(api_key=api_key) if OpenAI else None
    if not client:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text}")
        data = r.json()
        return (data.get("choices", [{}])[0].get("message", {}) or {}).get("content", "")

    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return (completion.choices[0].message.content or "").strip()


def call_anthropic(model: str, messages: List[Dict[str, str]], system_prompt: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 4096) -> str:
    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        logging.warning("missing ANTHROPIC_API_KEY")
        raise RuntimeError("Anthropic API key missing")

    if system_prompt:
        sys_prompt = system_prompt
    else:
        sys_prompt = None

    if anthropic:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=sys_prompt,
            messages=messages,
            temperature=temperature,
        )
        return "".join([p.text for p in getattr(resp, "content", []) if hasattr(p, "text")]).strip()

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": sys_prompt,
        "messages": messages,
        "temperature": temperature,
    }
    r = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text}")
    data = r.json()
    return "".join([item.get("text", "") for item in data.get("content", []) if isinstance(item, dict)]).strip()


def call_gemini(model: str, messages: List[Dict[str, str]], system_prompt: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 4096) -> str:
    api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if not api_key:
        logging.warning("missing GEMINI_API_KEY/GOOGLE_API_KEY")
        raise RuntimeError("Gemini API key missing")
    if not genai:
        raise RuntimeError("Gemini SDK not installed")

    genai.configure(api_key=api_key)
    system_instruction = system_prompt or None
    model_client = genai.GenerativeModel(model, system_instruction=system_instruction)
    user_content = "\n\n".join([m.get("content", "") for m in messages if m.get("role") != "system"])
    resp = model_client.generate_content(user_content, generation_config={"temperature": temperature, "max_output_tokens": max_tokens})
    return (getattr(resp, "text", "") or "").strip()


def _read_offline_corpus(corpus_file: str, messages: List[Dict[str, str]]) -> str:
    prompt = "\n\n".join([m.get("content", "") for m in messages if m.get("role") == "user"]).strip()
    try:
        with open(corpus_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and data:
            latest = data[-1]
            if isinstance(latest, dict):
                return latest.get("response") or latest.get("text") or "Offline corpus entry found but empty."
            if isinstance(latest, str):
                return latest
        return "No offline corpus entries found."
    except Exception:
        return f"Offline corpus available ({corpus_file}) but unreadable for prompt: {prompt[:80]}"


def call_llm(
    model: str,
    messages: List[Dict[str, str]],
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    session_id: Optional[str] = None,
    wallet: Optional[str] = None,
    difficulty: Optional[str] = None,
    block_hash: Optional[str] = None,
    chain_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    requested_model = model
    enabled_model_ids = list_enabled_model_ids()
    resolved = _resolve_model(model, wallet=wallet)
    if not resolved:
        # QUEST: Better error messaging for disabled models
        from llm_registry import find_model
        model_info = find_model(model)
        if model_info:
            if not model_info.enabled:
                error_msg = f"Model '{model}' ({model_info.provider}) is disabled. Please configure the {model_info.provider.upper()}_API_KEY environment variable."
            else:
                error_msg = f"Model '{model}' found but not available in current mode."
        else:
            error_msg = f"Unknown model id '{model}'. Please select a model from /api/ai_models."

        return {
            "response": error_msg,
            "status": "model_not_found",
            "provider": None,
            "model": model,
            "error": error_msg,
        }

    provider = resolved.provider
    resolved_model = resolved.id
    tier = resolved.tier

    mode = (os.getenv("THRONOS_AI_MODE", "all").strip().lower() or "all")
    if mode in ("router", "auto", "all", "hybrid", "proxy"):
        normalized_mode = "all"
    elif mode == "openai_only":
        normalized_mode = "openai"
    else:
        normalized_mode = mode
    if normalized_mode != "all" and provider != normalized_mode:
        return {
            "response": "Provider blocked by THRONOS_AI_MODE",
            "status": "forbidden",
            "provider": provider,
            "model": model,
            "error": "Provider not allowed",
        }

    model = resolved_model
    prompt_text = "\n\n".join([m.get("content", "") for m in messages])
    routing_meta: Dict[str, Any] = {}
    call_attempted = False

    is_auto = not requested_model or requested_model == "auto"

    if ThronosAIScorer is not None and mode == "router" and not is_auto:
        try:
            router = ThronosAIScorer()
            decision = router.route_provider(prompt_text)
            routing_meta = {
                "provider": decision.provider,
                "confidence": decision.confidence,
                "label": decision.label,
            }
            if decision.provider:
                provider = decision.provider
        except Exception:
            routing_meta = {"provider": provider, "label": "router_error"}

    started = time.time()
    text = ""
    error = None

    try:
        if provider == "openai":
            call_attempted = True
            text = call_openai(model, messages, system_prompt=system_prompt, temperature=temperature, max_tokens=max_tokens)
        elif provider == "anthropic":
            call_attempted = True
            text = call_anthropic(model, messages, system_prompt=system_prompt, temperature=temperature, max_tokens=max_tokens)
        elif provider == "gemini":
            call_attempted = True
            text = call_gemini(model, messages, system_prompt=system_prompt, temperature=temperature, max_tokens=max_tokens)
        elif provider == "local":
            corpus_file = (os.getenv("THR_OFFLINE_CORPUS_PATH") or "").strip()
            if not corpus_file:
                data_dir = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
                corpus_file = os.path.join(data_dir, "ai_offline_corpus.json")
            if not os.path.exists(corpus_file):
                routing_meta["call_attempted"] = False
                return {
                    "response": "Offline corpus not configured.",
                    "status": "provider_error",
                    "provider": provider,
                    "model": model,
                    "call_attempted": False,
                }
            call_attempted = True
            text = _read_offline_corpus(corpus_file, messages)
        elif provider in ("thronos", "custom"):
            custom_url = (
                os.getenv("DIKO_MAS_MODEL_URL")
                or os.getenv("CUSTOM_MODEL_URL")
                or os.getenv("CUSTOM_MODEL_URI")
                or ""
            ).strip()
            if not custom_url:
                routing_meta["call_attempted"] = False
                return {
                    "response": "Custom model endpoint not configured.",
                    "status": "provider_error",
                    "provider": provider,
                    "model": model,
                    "call_attempted": False,
                }
            call_attempted = True
            payload = {
                "messages": messages,
                "system_prompt": system_prompt or "",
                "temperature": temperature,
                "max_tokens": max_tokens,
                "session_id": session_id,
                "wallet": wallet,
                "chain_context": chain_context or {},
            }
            res = requests.post(custom_url, json=payload, timeout=60)
            try:
                data = res.json()
                text = data.get("response") or data.get("text") or ""
                if not text:
                    text = res.text
            except Exception:
                text = res.text
        else:
            routing_meta["call_attempted"] = False
            return {
                "response": f"Unsupported provider for model {model}",
                "status": "provider_error",
                "provider": provider,
                "model": model,
                "call_attempted": False,
            }
    except Exception as exc:
        logging.exception("LLM provider error", extra={"provider": provider, "model": model})
        error = str(exc)
        if provider == "anthropic" and ("not found" in error.lower() or "404" in error):
            mark_model_disabled(model, f"anthropic_not_found:{error}")

    duration = time.time() - started
    try:
        record_ai_interaction(
            provider=provider,
            model=model,
            tier=tier,
            prompt_text=prompt_text,
            output_text=text,
            duration=duration,
            latency_ms=int(duration * 1000),
            session_id=session_id,
            wallet=wallet,
            difficulty=difficulty,
            block_hash=block_hash,
            error=error,
            success=error is None,
            metadata={**routing_meta, "call_attempted": call_attempted},
        )
    except Exception:
        logging.exception("Failed to record AI interaction", extra={"provider": provider, "model": model})

    if error:
        return {
            "response": f"Quantum Core Error ({provider}): {error}",
            "status": "provider_error",
            "provider": provider,
            "model": model,
            "error": error,
            "call_attempted": call_attempted,
        }

    return {
        "response": text or "Quantum Core: empty response.",
        "status": provider,
        "provider": provider,
        "model": model,
        "call_attempted": call_attempted,
    }


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
        self.mode = (os.getenv("THRONOS_AI_MODE", "all").strip().lower() or "all")

        # Keys
        self.gemini_api_key = (os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")).strip()
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        custom_url = (
            os.getenv("CUSTOM_MODEL_URL")
            or os.getenv("CUSTOM_MODEL_URI")
            or os.getenv("DIKO_MAS_MODEL_URL")
            or ""
        ).strip()
        self.custom_model_url = custom_url
        self.diko_mas_model_url = custom_url or "http://127.0.0.1:8080/api/thrai/ask"

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
        self.ai_interactions_file = os.path.join(self.data_dir, "ai_interactions.jsonl")

        # Provider availability
        self.gemini_enabled = bool(self.gemini_api_key and genai)
        # OpenAI should work even if the SDK isn't installed; we'll fall back
        # to a direct HTTPS call when the client is missing.
        self.openai_enabled = bool(self.openai_api_key)
        self.anthropic_enabled = bool(self.anthropic_api_key)
        self.custom_enabled = bool(self.custom_model_url)

        self.gemini_model = None
        self.openai_client = None
        self.anthropic_client = None

        self._init_gemini()
        self._init_openai()
        self._init_anthropic()
        self._governance_context = self._load_governance_context()

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
            if OpenAI:
                self.openai_client = OpenAI(api_key=self.openai_api_key)
            else:
                self.openai_client = None
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

    def _build_base_payload(self, text: str, status: str, provider: str, model: str) -> Dict[str, Any]:
        return {
            "response": text,
            "status": status,
            "provider": provider,
            "model": model,
            "quantum_key": self.generate_quantum_key(),
        }

    def _base_payload(self, text: str, status: str, provider: str, model: str) -> Dict[str, Any]:
        return self._build_base_payload(text, status, provider, model)

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
        governance_context = self._governance_context or ""
        base_prompt = f"""You are Thronos Autonomous AI. Answer concisely and in production-ready code when needed. {directive}

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
        if governance_context:
            return base_prompt + f"\n\n**Governance context (authoritative):**\n{governance_context}"
        return base_prompt

    def _load_governance_context(self) -> str:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        governance_dir = os.path.join(base_dir, "governance")
        if not os.path.isdir(governance_dir):
            return ""
        docs = []
        total_chars = 0
        max_total_chars = 12000
        max_file_chars = 2000
        for name in sorted(os.listdir(governance_dir)):
            if not name.endswith(".md"):
                continue
            path = os.path.join(governance_dir, name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                continue
            snippet = content.strip()
            if len(snippet) > max_file_chars:
                snippet = snippet[:max_file_chars] + "\n...[truncated]..."
            entry = f"[governance/{name}]\n{snippet}"
            docs.append(entry)
            total_chars += len(entry)
            if total_chars >= max_total_chars:
                break
        return "\n\n".join(docs)

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

    # ─── Interaction ledger (shared dataset for routing + metrics) ──────────

    def _load_interaction_ledger(self, limit: int = 4000) -> List[Dict[str, Any]]:
        """Load past AI interactions from the shared ledger (JSONL).

        The ledger is persisted in ``ai_interactions.jsonl`` and is also used by
        the backend API.  We keep a cap to avoid loading unbounded history in
        memory.
        """

        entries: List[Dict[str, Any]] = []
        if not os.path.exists(self.ai_interactions_file):
            return entries

        try:
            with open(self.ai_interactions_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        continue
        except Exception:
            return []

        if len(entries) > limit:
            entries = entries[-limit:]
        return entries

    def _status_is_success(self, status: str) -> bool:
        status_l = (status or "").lower()
        if not status_l:
            return False
        error_tokens = ["error", "quota", "blocked", "no_credits", "provider_error"]
        return not any(tok in status_l for tok in error_tokens)

    def _infer_task_type(self, prompt: str) -> str:
        """Lightweight heuristic to bucket prompts into task types.

        The routing policy uses this to scope historical success rates.
        """

        prompt_l = (prompt or "").lower()
        if any(k in prompt_l for k in ["code", "function", "class", "python", "bug", "compile"]):
            return "coding"
        if any(k in prompt_l for k in ["design", "idea", "creative", "story", "lyrics"]):
            return "creative"
        if any(k in prompt_l for k in ["translate", "language", "english", "greek", "spanish"]):
            return "translation"
        if any(k in prompt_l for k in ["analyze", "summary", "explain", "reason"]):
            return "analysis"
        return "general"

    def _score_providers(self, task_type: str) -> Dict[str, float]:
        """Return a simple Laplace-smoothed success rate per provider."""

        entries = self._load_interaction_ledger()
        stats: Dict[str, Dict[str, float]] = {}

        for entry in entries:
            provider = entry.get("provider") or "unknown"
            if provider not in ("openai", "anthropic", "gemini", "local"):
                continue
            entry_task = entry.get("task_type") or entry.get("metadata", {}).get("task_type")
            if entry_task and entry_task != task_type:
                continue

            bucket = stats.setdefault(provider, {"success": 1.0, "total": 2.0})
            bucket["total"] += 1.0

            success = bool(entry.get("success")) or self._status_is_success(
                entry.get("metadata", {}).get("status") or entry.get("status") or ""
            )
            if success:
                bucket["success"] += 1.0

        scores: Dict[str, float] = {}
        for provider, bucket in stats.items():
            success = bucket.get("success", 1.0)
            total = max(bucket.get("total", 2.0), 1.0)
            scores[provider] = success / total

        return scores

    def _rank_providers(self, task_type: str) -> List[Dict[str, Any]]:
        """Return available providers ranked by historical success."""

        scores = self._score_providers(task_type)
        availability: List[Dict[str, Any]] = []

        if self.openai_enabled:
            availability.append({"provider": "openai", "model": self.openai_model_name})
        if self.anthropic_enabled:
            availability.append({"provider": "anthropic", "model": self.anthropic_model_name})
        if self.gemini_enabled:
            availability.append({"provider": "gemini", "model": self.gemini_model_name})

        # Local fallback is always available
        availability.append({"provider": "local", "model": "offline_corpus"})

        for item in availability:
            item["score"] = scores.get(item["provider"], 0.5)

        # Stable sort: highest score first, then a deterministic preference order
        preference = {"openai": 3, "anthropic": 2, "gemini": 1, "local": 0}
        availability.sort(key=lambda x: (x["score"], preference.get(x["provider"], -1)), reverse=True)
        return availability

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

    def _call_gemini(self, prompt: str, model_name: str, lang: Optional[str] = None, wallet: Optional[str] = None, session_id: Optional[str] = None) -> Dict[str, Any]:
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

    def _call_openai(self, prompt: str, model_name: str, lang: Optional[str] = None, wallet: Optional[str] = None, session_id: Optional[str] = None) -> Dict[str, Any]:
        if not self.openai_enabled:
            raise RuntimeError("OpenAI not available (missing key)")

        system_prompt = self._system_prompt(lang)
        try:
            if self.openai_client:
                completion = self.openai_client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                )
                txt = (completion.choices[0].message.content or "").strip()
            else:
                headers = {
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                }
                r = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=30,
                )
                if r.status_code >= 400:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text}")
                data = r.json()
                txt = ""
                try:
                    txt = (data.get("choices", [{}])[0].get("message", {}) or {}).get("content", "")
                except Exception:
                    txt = data.get("response", "")

            if not txt:
                txt = "Quantum Core: empty response from OpenAI."
            return self._base_payload(txt, "openai", "openai", model_name)
        except Exception as e:
            msg = str(e)
            if "rate limit" in msg.lower() or "quota" in msg.lower() or "429" in msg:
                return self._base_payload("Quantum Core Notice: OpenAI quota/rate limit.", "openai_quota", "openai", model_name)
            return self._base_payload(f"Quantum Core Error (OpenAI): {msg}", "openai_error", "openai", model_name)

    def _call_anthropic(self, prompt: str, model_name: str, lang: Optional[str] = None, wallet: Optional[str] = None, session_id: Optional[str] = None) -> Dict[str, Any]:
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

    def _call_diko_mas_model(self, prompt: str, wallet: str = "", session_id: Optional[str] = None) -> Dict[str, Any]:
        if not self.diko_mas_model_url:
            return self._build_base_payload(
                "Custom model URL is not configured. Set CUSTOM_MODEL_URL in Railway.",
                status="config_error",
                provider="diko_mas",
                model="thrai",
            )

        payload = {
            "prompt": prompt,
            "session_id": session_id,
            "wallet": wallet or None,
        }

        try:
            res = requests.post(
                self.diko_mas_model_url,
                json=payload,
                timeout=60,
            )

            try:
                data = res.json()
            except Exception:
                data = {"response": res.text}

            if all(k in data for k in ("response", "status", "provider", "model", "quantum_key")):
                return data

            txt = data.get("response") or data.get("text") or ""
            status = data.get("status") or "ok"

            base = self._build_base_payload(
                txt or "Empty response from custom model.",
                status=status,
                provider=data.get("provider") or "diko_mas",
                model=data.get("model") or "thrai",
            )
            if data.get("quantum_key"):
                base["quantum_key"] = data["quantum_key"]

            return base
        except Exception as e:
            return self._build_base_payload(
                f"Quantum Core Error (Custom): {e}",
                status="provider_error",
                provider="diko_mas",
                model="thrai",
            )

    def _call_claude(self, prompt: str, model_name: str, lang: Optional[str] = None, wallet: Optional[str] = None, session_id: Optional[str] = None) -> Dict[str, Any]:
        return self._call_anthropic(prompt, model_name, lang)

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

    def generate_response(
        self,
        prompt: str,
        wallet: Optional[str] = None,
        model_key: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        prompt = (prompt or "").strip()
        if not prompt:
            return self._build_base_payload("Empty prompt.", "error", "local", "offline")

        mk = (model_key or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")).strip()
        lang = (kwargs.get("lang") or kwargs.get("language") or "").strip().lower() or None
        task_type = self._infer_task_type(prompt)

        def ensure_quantum_key(ans: Dict[str, Any]) -> Dict[str, Any]:
            if ans is None:
                return self._build_base_payload(
                    "Empty response.",
                    status="provider_error",
                    provider="thronos_ai",
                    model=mk or "auto",
                )
            if not ans.get("quantum_key"):
                ans["quantum_key"] = self.generate_quantum_key()
            return ans

        messages = [{"role": "user", "content": prompt}]
        system_prompt = self._system_prompt(lang)

        try:
            resp = call_llm(
                mk,
                messages,
                system_prompt=system_prompt,
                temperature=float(kwargs.get("temperature", 0.7)),
                max_tokens=int(kwargs.get("max_tokens", 4096)),
                session_id=session_id,
                wallet=wallet,
                difficulty=kwargs.get("difficulty"),
                block_hash=kwargs.get("block_hash"),
                chain_context=kwargs.get("chain_context"),
            )
            resp["task_type"] = task_type
            resp = ensure_quantum_key(resp)
            self._store_history(prompt, resp, wallet)
            return resp
        except Exception as e:
            resp = self._build_base_payload(
                f"Quantum Core Error: {e}",
                status="provider_error",
                provider="thronos_ai",
                model=mk or "auto",
            )
            resp["task_type"] = task_type
            resp = ensure_quantum_key(resp)
            self._store_history(prompt, resp, wallet)
            return resp
