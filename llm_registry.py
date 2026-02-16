from __future__ import annotations

import os
import importlib.util
import logging
from dataclasses import dataclass
import json
import time
from urllib import request as urllib_request
from urllib.parse import urlsplit
from typing import Dict, List, Optional

MODEL_DISABLE_REASONS: Dict[str, str] = {}


def _ensure_diag(entry: dict) -> dict:
    """Ensure diagnostic keys exist on a provider entry."""
    if not isinstance(entry, dict):
        entry = {}
    entry.setdefault("checked_sources", [])
    entry.setdefault("reasons", [])
    entry.setdefault("last_error", None)
    return entry


def _module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False


def _env_truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _url_health_ok(url: str, timeout: float = 2.5) -> tuple[bool, Optional[str]]:
    target = (url or "").strip()
    if not target:
        return False, "empty_url"

    candidates = [target]
    try:
        parsed = urlsplit(target)
        if parsed.scheme and parsed.netloc:
            base = f"{parsed.scheme}://{parsed.netloc}"
            candidates.append(f"{base}/api/ai/health")
            candidates.append(f"{base}/health")
    except Exception:
        pass

    for candidate in candidates:
        try:
            req = urllib_request.Request(candidate, method="GET")
            with urllib_request.urlopen(req, timeout=timeout) as resp:
                status = int(getattr(resp, "status", 200) or 200)
                if status < 500:
                    return True, None
        except Exception as exc:
            last = str(exc)
            continue
    return False, last if 'last' in locals() else "health_check_failed"


def _offline_corpus_health(path: str) -> tuple[bool, Optional[str]]:
    try:
        if not path or not os.path.exists(path):
            return False, f"missing_path:{path}"
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, list):
            return False, "invalid_corpus_format"
        return True, None
    except Exception as exc:
        return False, str(exc)


def _thrai_router_health(url: str, timeout: float = 2.5) -> tuple[bool, Optional[str]]:
    ok, err = _url_health_ok(url, timeout=timeout)
    if ok:
        return True, None
    target = (url or "").strip()
    if not target:
        return False, "missing_router_url"
    try:
        req = urllib_request.Request(
            target,
            data=b'{"ping":"thrai"}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib_request.urlopen(req, timeout=timeout) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            if status < 500:
                return True, None
    except Exception as post_exc:
        return False, str(post_exc)
    return False, err

try:
    import google.genai as genai
except Exception:
    genai = None


@dataclass
class ModelInfo:
    id: str
    provider: str
    display_name: str
    tier: str = "standard"
    default: bool = False
    enabled: bool = True


PROVIDER_METADATA: Dict[str, Dict[str, str]] = {
    "openai": {
        "id": "openai",
        "name": "OpenAI (GPT)",
        "description": "OpenAI GPT-4.1 family",
    },
    "anthropic": {
        "id": "anthropic",
        "name": "Anthropic (Claude)",
        "description": "Claude 3.7 models",
    },
    "gemini": {
        "id": "gemini",
        "name": "Google Gemini",
        "description": "Gemini 2.0 / 3.0 models",
    },
    "local": {
        "id": "local",
        "name": "Thronos Offline Corpus",
        "description": "Local knowledge base / blockchain log",
    },
    "thronos": {
        "id": "thronos",
        "name": "Thronos / Thrai",
        "description": "Custom Thronos model",
    },
}


AI_MODEL_REGISTRY: Dict[str, List[ModelInfo]] = {
    "openai": [
        ModelInfo(id="gpt-4.1-mini", display_name="GPT-4.1 mini", provider="openai", tier="fast", default=True),
        ModelInfo(id="gpt-4.1", display_name="GPT-4.1", provider="openai", tier="premium"),
        ModelInfo(id="gpt-4.1-preview", display_name="GPT-4.1 Preview", provider="openai", tier="preview"),
        ModelInfo(id="o3-mini", display_name="o3-mini (reasoning)", provider="openai", tier="reasoning"),
    ],
    "anthropic": [
        ModelInfo(id="claude-3-sonnet-20240229", display_name="Claude 3 Sonnet", provider="anthropic", tier="premium", default=True),
        ModelInfo(id="claude-3-haiku-20240307", display_name="Claude 3 Haiku", provider="anthropic", tier="fast"),
        ModelInfo(id="claude-3-opus-20240229", display_name="Claude 3 Opus", provider="anthropic", tier="premium"),
    ],
    "gemini": [
        ModelInfo(id="gemini-2.0-flash", display_name="Gemini 2.0 Flash", provider="gemini", tier="fast", default=True),
        ModelInfo(id="gemini-2.5-pro", display_name="Gemini 2.5 Pro", provider="gemini", tier="premium"),
        ModelInfo(id="gemini-2.5-flash", display_name="Gemini 2.5 Flash", provider="gemini", tier="fast"),
    ],
    "local": [
        ModelInfo(id="offline_corpus", display_name="Offline corpus (local)", provider="local", tier="local", default=False, enabled=False),
    ],
    "thronos": [
        ModelInfo(id="thrai", display_name="Thronos / Thrai (custom)", provider="thronos", tier="custom", default=False, enabled=False),
    ],
}


MODEL_ID_ALIASES: Dict[str, str] = {
    # Anthropic legacy/non-canonical ids -> stable canonical ids
    "claude-3.5-sonnet": "claude-3-sonnet-20240229",
    "claude-3.5-haiku": "claude-3-haiku-20240307",
    "claude-3-5-sonnet": "claude-3-sonnet-20240229",
    "claude-3-5-haiku": "claude-3-haiku-20240307",
    "claude-3-5-sonnet-latest": "claude-3-sonnet-20240229",
    "claude-3-5-haiku-latest": "claude-3-haiku-20240307",
    "claude-3-5-sonnet-20240620": "claude-3-sonnet-20240229",
    "claude-3-5-haiku-20241022": "claude-3-haiku-20240307",
}


def _http_json_get(url: str, headers: Optional[dict] = None, timeout: float = 7.5) -> dict:
    req = urllib_request.Request(url, headers=headers or {}, method="GET")
    with urllib_request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return json.loads(data.decode("utf-8")) if data else {}


def _fallback_provider_models(provider: str) -> list[dict]:
    items = []
    for m in AI_MODEL_REGISTRY.get(provider, []):
        items.append({
            "id": m.id,
            "type": "chat",
            "enabled": bool(m.enabled),
            "degraded": not bool(m.enabled),
            "health_reason": None if m.enabled else "fallback_disabled",
            "preview": ("preview" in m.id or "preview" in (m.tier or "")),
            "voice_friendly": any(t in m.id for t in ("mini", "haiku", "flash")),
        })
    return items


def discover_openai_models(api_key: str) -> list[dict]:
    if not (api_key or "").strip():
        return [{**m, "enabled": False, "degraded": True, "health_reason": "missing_api_key"} for m in _fallback_provider_models("openai")]
    try:
        payload = _http_json_get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key.strip()}"},
        )
        out = []
        for item in payload.get("data", []) if isinstance(payload, dict) else []:
            mid = str((item or {}).get("id") or "").strip()
            if not mid or not (mid.startswith("gpt-") or mid.startswith("o3")):
                continue
            preview = any(token in mid for token in ("preview", "beta"))
            unsupported = mid in {"o3", "gpt-o3", "o3-pro", "gpt-o3-preview"}
            out.append({
                "id": mid,
                "type": "chat",
                "enabled": not (preview or unsupported),
                "degraded": bool(preview or unsupported),
                "health_reason": "preview_only" if (preview or unsupported) else None,
                "preview": bool(preview or unsupported),
                "voice_friendly": any(t in mid for t in ("mini", "nano")),
            })
        return sorted(out, key=lambda x: x.get("id") or "") or _fallback_provider_models("openai")
    except Exception:
        return _fallback_provider_models("openai")


def discover_anthropic_models(api_key: str) -> list[dict]:
    if not (api_key or "").strip():
        return [{**m, "enabled": False, "degraded": True, "health_reason": "missing_api_key"} for m in _fallback_provider_models("anthropic")]
    try:
        payload = _http_json_get(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": api_key.strip(), "anthropic-version": "2023-06-01"},
        )
        out = []
        models = payload.get("data") if isinstance(payload, dict) else []
        for item in models or []:
            mid = str((item or {}).get("id") or (item or {}).get("name") or "").strip()
            if not mid or not mid.startswith("claude"):
                continue
            out.append({
                "id": mid,
                "type": "chat",
                "enabled": True,
                "degraded": False,
                "health_reason": None,
                "preview": "preview" in mid,
                "voice_friendly": any(t in mid for t in ("haiku", "sonnet")),
            })
        return sorted(out, key=lambda x: x.get("id") or "") or _fallback_provider_models("anthropic")
    except Exception:
        return _fallback_provider_models("anthropic")


def discover_gemini_models(api_key: str) -> list[dict]:
    if not (api_key or "").strip():
        return [{**m, "enabled": False, "degraded": True, "health_reason": "missing_api_key"} for m in _fallback_provider_models("gemini")]
    try:
        payload = _http_json_get(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key.strip()}",
        )
        out = []
        for item in payload.get("models", []) if isinstance(payload, dict) else []:
            name = str((item or {}).get("name") or "")
            mid = name.split("/")[-1].strip()
            if not mid.startswith("gemini"):
                continue
            out.append({
                "id": mid,
                "type": "chat",
                "enabled": True,
                "degraded": False,
                "health_reason": None,
                "preview": "preview" in mid,
                "voice_friendly": any(t in mid for t in ("flash", "lite")),
            })
        return sorted(out, key=lambda x: x.get("id") or "") or _fallback_provider_models("gemini")
    except Exception:
        return _fallback_provider_models("gemini")




def refresh_registry_from_provider_discovery(openai_key: str = "", anthropic_key: str = "", gemini_key: str = "") -> dict:
    """Refresh in-memory AI_MODEL_REGISTRY from live provider discovery results.

    Only updates remote providers (openai/anthropic/gemini) and keeps local/thronos
    entries untouched. Returns metadata for telemetry/logging.
    """
    now = int(time.time())
    snapshot = {
        "ok": True,
        "updated_at": now,
        "providers": {},
    }

    provider_payloads = {
        "openai": discover_openai_models((openai_key or "").strip()),
        "anthropic": discover_anthropic_models((anthropic_key or "").strip()),
        "gemini": discover_gemini_models((gemini_key or "").strip()),
    }

    for provider_name, models in provider_payloads.items():
        discovered = [m for m in models if isinstance(m, dict) and (m.get("id") or "").strip()]
        new_models: list[ModelInfo] = []

        for idx, model in enumerate(discovered):
            mid = str(model.get("id") or "").strip()
            if not mid:
                continue
            display = str(model.get("display_name") or model.get("label") or mid).strip() or mid
            tier = "preview" if bool(model.get("preview")) else ("fast" if bool(model.get("voice_friendly")) else "standard")
            enabled = bool(model.get("enabled", True))
            new_models.append(
                ModelInfo(
                    id=mid,
                    display_name=display,
                    provider=provider_name,
                    tier=tier,
                    default=(idx == 0),
                    enabled=enabled,
                )
            )

        if new_models:
            AI_MODEL_REGISTRY[provider_name] = new_models

        snapshot["providers"][provider_name] = {
            "models_count": len(new_models),
            "enabled_count": sum(1 for m in new_models if m.enabled),
            "updated": bool(new_models),
        }

    return snapshot

def find_model(model_id: str) -> Optional[ModelInfo]:
    lookup = str(model_id or "").strip()
    if not lookup:
        return None
    lookup = MODEL_ID_ALIASES.get(lookup, lookup)
    for provider_models in AI_MODEL_REGISTRY.values():
        for m in provider_models:
            if m.id == lookup:
                return m
    return None


def mark_model_disabled(model_id: str, reason: str) -> None:
    model = find_model(model_id)
    if not model:
        return
    model.enabled = False
    MODEL_DISABLE_REASONS[model_id] = reason


def _apply_env_flags(provider_status: Optional[dict] = None) -> None:
    provider_status = provider_status or get_provider_status()

    for provider_name, models in AI_MODEL_REGISTRY.items():
        info = provider_status.get(provider_name, {}) if isinstance(provider_status, dict) else {}
        enabled = bool(info.get("configured", False))
        degraded = enabled and not info.get("library_loaded", True)

        for m in models:
            m.enabled = enabled
            if degraded:
                m.degraded = True
            reason = MODEL_DISABLE_REASONS.get(m.id)
            if reason:
                m.enabled = False


def _provider_status_entry(
    configured: bool,
    key_sources: list[str],
    library_loaded: Optional[bool] = True,
    last_error: Optional[str] = None,
    extra: Optional[dict] = None,
) -> dict:
    checked_sources = [{"source": "env", "key": k, "present": bool((os.getenv(k) or "").strip())} for k in key_sources]
    entry = {
        "configured": configured,
        "has_key": configured,
        "library_loaded": library_loaded if library_loaded is not None else True,
        "checked_env": key_sources,
        "key_sources_checked": key_sources,
        "checked_sources": checked_sources,
        "missing_env": [] if configured else key_sources,
        "last_sync_ok": True,
        "last_error": last_error,
        "source": "registry",
    }
    if extra:
        entry.update(extra)
    return entry


def get_provider_status() -> dict:
    """
    Return provider status with explicit key source tracing and library flags.
    Never exposes secrets; only reports which env names were checked.
    """
    status = {}

    invalid_by_provider: Dict[str, List[dict]] = {}
    for mid, reason in MODEL_DISABLE_REASONS.items():
        m = find_model(mid)
        if not m:
            continue
        invalid_by_provider.setdefault(m.provider, []).append({"id": mid, "reason": reason})

    openai_vars = ["OPENAI_API_KEY", "OPENAI_KEY"]
    openai_primary = (os.getenv("OPENAI_API_KEY") or "").strip()
    openai_legacy = (os.getenv("OPENAI_KEY") or "").strip()
    openai_configured = bool(openai_primary or openai_legacy)
    openai_lib = _module_available("openai")
    openai_entry = _ensure_diag(
        _provider_status_entry(
            openai_configured,
            openai_vars,
            library_loaded=openai_lib,
            extra={"configured_by": "OPENAI_API_KEY" if openai_primary else ("OPENAI_KEY" if openai_legacy else None)},
        )
    )
    openai_entry["checked_sources"].append({"source": "import", "module": "openai", "present": openai_lib})
    openai_entry["invalid_models"] = invalid_by_provider.get("openai", [])
    if openai_entry["invalid_models"] and not openai_entry.get("last_error"):
        openai_entry["last_error"] = openai_entry["invalid_models"][0].get("reason")
    status["openai"] = openai_entry

    anthropic_vars = ["ANTHROPIC_API_KEY"]
    anthropic_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    anthropic_configured = bool(anthropic_key)
    anthropic_lib = _module_available("anthropic")
    anthropic_entry = _ensure_diag(
        _provider_status_entry(anthropic_configured, anthropic_vars, library_loaded=anthropic_lib)
    )
    anthropic_entry["checked_sources"].append({"source": "import", "module": "anthropic", "present": anthropic_lib})
    anthropic_entry["invalid_models"] = invalid_by_provider.get("anthropic", [])
    if anthropic_entry["invalid_models"] and not anthropic_entry.get("last_error"):
        anthropic_entry["last_error"] = anthropic_entry["invalid_models"][0].get("reason")
    status["anthropic"] = anthropic_entry

    gemini_vars = ["GEMINI_API_KEY", "GOOGLE_API_KEY"]
    gemini_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    gemini_configured = bool(gemini_key)
    gemini_lib = bool(genai)
    gemini_entry = _ensure_diag(
        _provider_status_entry(gemini_configured, gemini_vars, library_loaded=gemini_lib)
    )
    gemini_entry["checked_sources"].append({"source": "import", "module": "google.generativeai", "present": gemini_lib})
    gemini_entry["invalid_models"] = invalid_by_provider.get("gemini", [])
    if gemini_entry["invalid_models"] and not gemini_entry.get("last_error"):
        gemini_entry["last_error"] = gemini_entry["invalid_models"][0].get("reason")
    status["gemini"] = gemini_entry

    data_dir = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
    offline_path = (os.getenv("THR_OFFLINE_CORPUS_PATH") or "").strip()
    if not offline_path:
        offline_path = os.path.join(data_dir, "ai_offline_corpus.json")
    offline_flag = _env_truthy("THR_OFFLINE_CORPUS_ENABLED", default=False)
    offline_exists = os.path.exists(offline_path)
    offline_ok, offline_err = _offline_corpus_health(offline_path)
    local_configured = bool(offline_flag and offline_ok)
    local_missing = []
    if not offline_flag:
        local_missing.append("THR_OFFLINE_CORPUS_ENABLED")
    if not offline_exists:
        local_missing.append(f"THR_OFFLINE_CORPUS_PATH={offline_path}")
    local_entry = _ensure_diag(
        _provider_status_entry(
            local_configured,
            ["THR_OFFLINE_CORPUS_ENABLED", "THR_OFFLINE_CORPUS_PATH", "DATA_DIR"],
            library_loaded=True,
            last_error=None if offline_ok else offline_err,
            extra={"corpus_file": offline_path, "missing_env": local_missing, "health_ok": offline_ok},
        )
    )
    local_entry["checked_sources"].append({"source": "file", "path": offline_path, "present": offline_exists, "health_ok": offline_ok})
    local_entry["invalid_models"] = invalid_by_provider.get("local", [])
    if local_entry["invalid_models"] and not local_entry.get("last_error"):
        local_entry["last_error"] = local_entry["invalid_models"][0].get("reason")
    status["local"] = local_entry

    thronos_vars = ["THR_THAI_ENABLED", "DIKO_MAS_MODEL_URL", "CUSTOM_MODEL_URL", "CUSTOM_MODEL_URI"]
    diko_url = (
        os.getenv("DIKO_MAS_MODEL_URL")
        or os.getenv("CUSTOM_MODEL_URL")
        or os.getenv("CUSTOM_MODEL_URI")
        or ""
    ).strip()
    thai_flag = _env_truthy("THR_THAI_ENABLED", default=bool(diko_url))
    thai_health_ok, thai_health_err = _thrai_router_health(diko_url) if diko_url else (False, "missing_router_url")
    thronos_configured = bool(diko_url and thai_flag and thai_health_ok)
    thronos_missing = []
    if not thai_flag:
        thronos_missing.append("THR_THAI_ENABLED")
    if not diko_url:
        thronos_missing.append("DIKO_MAS_MODEL_URL")
    if diko_url and not thai_health_ok:
        thronos_missing.append("DIKO_MAS_MODEL_URL health_check")
    thronos_entry = _ensure_diag(
        _provider_status_entry(
            thronos_configured,
            thronos_vars,
            library_loaded=True,
            last_error=None if thai_health_ok else thai_health_err,
            extra={
                "missing_env": thronos_missing,
                "custom_url": bool(diko_url),
                "router_url": diko_url,
                "health_ok": thai_health_ok,
            },
        )
    )
    thronos_entry["checked_sources"].append({"source": "health", "url": diko_url, "ok": thai_health_ok})
    thronos_entry["invalid_models"] = invalid_by_provider.get("thronos", [])
    if thronos_entry["invalid_models"] and not thronos_entry.get("last_error"):
        thronos_entry["last_error"] = thronos_entry["invalid_models"][0].get("reason")
    status["thronos"] = thronos_entry

    return status


try:
    _apply_env_flags(get_provider_status())
except Exception as exc:
    logging.warning("llm_registry: provider status initialization failed: %s", exc)


def list_enabled_model_ids(mode: Optional[str] = None) -> List[str]:
    """Return a list of enabled model ids, respecting THRONOS_AI_MODE if provided."""

    _apply_env_flags(get_provider_status())

    normalized_mode = (mode or os.getenv("THRONOS_AI_MODE", "all")).strip().lower()
    if normalized_mode in ("", "router", "auto", "hybrid"):
        normalized_mode = "all"
    if normalized_mode == "openai_only":
        normalized_mode = "openai"

    enabled_ids: List[str] = []
    for provider_name, models in AI_MODEL_REGISTRY.items():
        if normalized_mode != "all" and provider_name != normalized_mode:
            continue
        for m in models:
            if m.enabled:
                enabled_ids.append(m.id)
    return enabled_ids


def get_default_model(provider: Optional[str] = None) -> Optional[ModelInfo]:
    if provider:
        models = AI_MODEL_REGISTRY.get(provider, [])
        for m in models:
            if m.default and m.enabled:
                return m
        return next((m for m in models if m.enabled), None)

    for models in AI_MODEL_REGISTRY.values():
        for m in models:
            if m.default and m.enabled:
                return m
    for models in AI_MODEL_REGISTRY.values():
        default_candidate = next((m for m in models if m.enabled), None)
        if default_candidate:
            return default_candidate
    return None
# ---------------------------------------------------------------------------
# Default model helper (backwards-compatible)
# ---------------------------------------------------------------------------


def get_default_model_for_mode(mode: Optional[str] = None) -> str:
    """
    Επιστρέφει το κατάλληλο model_id με βάση το mode.

    Λογική:
    1. Αν υπάρχει ειδικό env για το mode, το τιμάμε.
       - THRONOS_DEFAULT_CHAT_MODEL
       - THRONOS_DEFAULT_CODE_MODEL
       - THRONOS_DEFAULT_VISION_MODEL
    2. Αλλιώς κοιτάμε ένα γενικό:
       - THRONOS_DEFAULT_MODEL
    3. Τελευταίο fallback: ένα ασφαλές μοντέλο (π.χ. gpt-4.1-mini).
    """
    mode = (mode or "").strip().lower()

    # 1) mode-specific env, π.χ. THRONOS_DEFAULT_CHAT_MODEL
    env_key = f"THRONOS_DEFAULT_{mode.upper()}_MODEL"
    env_value = os.getenv(env_key)
    if env_value:
        return env_value.strip()

    # 2) global default
    global_default = os.getenv("THRONOS_DEFAULT_MODEL")
    if global_default:
        return global_default.strip()

    # 3) hardcoded ασφαλές fallback
    return "gpt-4.1-mini"


# -------------------------------------------------------------
# ΝΕΑ λογική για επιλογή μοντέλου ανά provider + mode
# -------------------------------------------------------------


def _normalize_provider_name(provider: Optional[str]) -> Optional[str]:
    """
    Ενοποίηση ονομάτων provider από UI/παλιά versions σε canonical keys
    που υπάρχουν στο AI_MODEL_REGISTRY.
    """
    if not provider:
        return None

    p = provider.strip().lower()

    alias_map = {
        # OpenAI
        "gpt": "openai",
        "openai": "openai",
        "oai": "openai",

        # Anthropic
        "claude": "anthropic",
        "anthropic": "anthropic",

        # Google / Gemini
        "google": "gemini",
        "gemini": "gemini",

        # Local
        "local": "local",
        "ollama": "local",

        # Thronos custom
        "thronos": "thronos",
    }

    return alias_map.get(p, p)


def get_model_for_provider(
    provider: Optional[str] = None,
    mode: Optional[str] = None,
) -> Optional[str]:
    """
    Επιστρέφει το κατάλληλο model_id (string) για τον δοθέντα provider & mode.

    - provider: π.χ. "openai", "gpt", "claude", "gemini", "local", "thronos"
    - mode: π.χ. "chat", "tools", "vision", "audio", "embed"

    Αν δεν βρεθεί κάτι ειδικό, επιστρέφει fallback από get_default_model_for_mode().
    """

    # Αν δεν δόθηκε provider, άσε το mode-default να αποφασίσει
    if not provider:
        return get_default_model_for_mode(mode or "chat")

    provider_key = _normalize_provider_name(provider)
    if not provider_key:
        return get_default_model_for_mode(mode or "chat")

    models = AI_MODEL_REGISTRY.get(provider_key, [])
    if not models:
        # Άγνωστος provider -> fallback στο global default για το συγκεκριμένο mode
        return get_default_model_for_mode(mode or "chat")

    # 1) Πρώτα ψάξε για default μοντέλο που είναι enabled
    for m in models:
        if m.default and m.enabled:
            return m.id

    # 2) Αλλιώς, πάρε οποιοδήποτε enabled μοντέλο
    for m in models:
        if m.enabled:
            return m.id

    # 3) Αν δεν βρεθεί enabled, πάρε το default (ακόμα κι αν είναι disabled)
    for m in models:
        if m.default:
            return m.id

    # 4) Τελευταία λύση: οποιοδήποτε μοντέλο του provider
    if models:
        return models[0].id

    # 5) Αν φτάσαμε εδώ, γύρνα στο global default per mode
    return get_default_model_for_mode(mode or "chat")
