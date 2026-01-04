from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional


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
        ModelInfo(id="claude-3.5-sonnet", display_name="Claude 3.7 Sonnet", provider="anthropic", tier="premium", default=True),
        ModelInfo(id="claude-3.5-haiku", display_name="Claude 3.5 Haiku", provider="anthropic", tier="fast"),
    ],
    "gemini": [
        ModelInfo(id="gemini-2.0-flash", display_name="Gemini 2.0 Flash", provider="gemini", tier="fast", default=True),
        ModelInfo(id="gemini-2.5-pro", display_name="Gemini 2.5 Pro", provider="gemini", tier="premium"),
        ModelInfo(id="gemini-2.5-flash", display_name="Gemini 2.5 Flash", provider="gemini", tier="fast"),
    ],
    "local": [
        ModelInfo(id="offline_corpus", display_name="Offline corpus (local)", provider="local", tier="local", default=False, enabled=True),
    ],
    "thronos": [
        ModelInfo(id="thrai", display_name="Thronos / Thrai (custom)", provider="thronos", tier="custom", default=False, enabled=True),
    ],
}


def _apply_env_flags() -> None:
    # FIX 7: Support env var aliases and check availability for local/thronos
    import logging
    logger = logging.getLogger(__name__)

    # Check OpenAI: OPENAI_API_KEY or OPENAI_KEY
    openai_key = (os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY") or "").strip()
    has_openai = bool(openai_key)
    logger.debug(f"OpenAI provider check: OPENAI_API_KEY={bool(os.getenv('OPENAI_API_KEY'))}, OPENAI_KEY={bool(os.getenv('OPENAI_KEY'))} → enabled={has_openai}")

    # Check Anthropic: ANTHROPIC_API_KEY
    anthropic_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    has_anthropic = bool(anthropic_key)
    logger.debug(f"Anthropic provider check: ANTHROPIC_API_KEY={bool(os.getenv('ANTHROPIC_API_KEY'))} → enabled={has_anthropic}")

    # Check Gemini: GEMINI_API_KEY or GOOGLE_API_KEY
    gemini_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    has_gemini = bool(gemini_key)
    logger.debug(f"Gemini provider check: GEMINI_API_KEY={bool(os.getenv('GEMINI_API_KEY'))}, GOOGLE_API_KEY={bool(os.getenv('GOOGLE_API_KEY'))} → enabled={has_gemini}")

    # Check local: offline corpus file exists
    data_dir = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
    corpus_file = os.path.join(data_dir, "ai_offline_corpus.json")
    has_local = os.path.exists(corpus_file)
    logger.debug(f"Local provider check: corpus_file={corpus_file} exists={has_local} → enabled={has_local}")

    # Check thronos: CUSTOM_MODEL_URL configured
    custom_url = (os.getenv("CUSTOM_MODEL_URL") or "").strip()
    has_thronos = bool(custom_url)
    # Also check THRONOS_AI_MODE allows custom (if mode is restrictive)
    ai_mode = (os.getenv("THRONOS_AI_MODE") or "all").lower()
    if ai_mode not in ("all", "router", "auto", "custom", ""):
        has_thronos = False  # Restricted mode doesn't allow custom
    logger.debug(f"Thronos provider check: CUSTOM_MODEL_URL={bool(custom_url)}, THRONOS_AI_MODE={ai_mode} → enabled={has_thronos}")

    for provider_name, models in AI_MODEL_REGISTRY.items():
        if provider_name == "openai":
            enabled = has_openai
        elif provider_name == "anthropic":
            enabled = has_anthropic
        elif provider_name == "gemini":
            enabled = has_gemini
        elif provider_name == "local":
            enabled = has_local
        elif provider_name == "thronos":
            enabled = has_thronos
        else:
            enabled = True

        for m in models:
            m.enabled = enabled


_apply_env_flags()


def get_provider_status() -> dict:
    """
    FIX 7: Return provider status with env var names checked.
    Returns dict with provider → {configured: bool, checked_env: [str], missing_env: [str], source: str}
    """
    status = {}

    # OpenAI
    openai_vars = ["OPENAI_API_KEY", "OPENAI_KEY"]
    openai_configured = any(os.getenv(v) for v in openai_vars)
    openai_missing = [v for v in openai_vars if not os.getenv(v)]
    status["openai"] = {
        "configured": openai_configured,
        "checked_env": openai_vars,
        "missing_env": openai_missing if not openai_configured else [],
        "source": "registry"
    }

    # Anthropic
    anthropic_vars = ["ANTHROPIC_API_KEY"]
    anthropic_configured = any(os.getenv(v) for v in anthropic_vars)
    anthropic_missing = [v for v in anthropic_vars if not os.getenv(v)]
    status["anthropic"] = {
        "configured": anthropic_configured,
        "checked_env": anthropic_vars,
        "missing_env": anthropic_missing if not anthropic_configured else [],
        "source": "registry"
    }

    # Gemini
    gemini_vars = ["GEMINI_API_KEY", "GOOGLE_API_KEY"]
    gemini_configured = any(os.getenv(v) for v in gemini_vars)
    gemini_missing = [v for v in gemini_vars if not os.getenv(v)]
    status["gemini"] = {
        "configured": gemini_configured,
        "checked_env": gemini_vars,
        "missing_env": gemini_missing if not gemini_configured else [],
        "source": "registry"
    }

    # Local (offline corpus)
    data_dir = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
    corpus_file = os.path.join(data_dir, "ai_offline_corpus.json")
    local_configured = os.path.exists(corpus_file)
    status["local"] = {
        "configured": local_configured,
        "checked_env": ["DATA_DIR"],
        "missing_env": [] if local_configured else ["ai_offline_corpus.json"],
        "corpus_file": corpus_file,
        "source": "registry"
    }

    # Thronos (custom model)
    thronos_vars = ["CUSTOM_MODEL_URL", "THRONOS_AI_MODE"]
    custom_url = (os.getenv("CUSTOM_MODEL_URL") or "").strip()
    ai_mode = (os.getenv("THRONOS_AI_MODE") or "all").lower()
    thronos_configured = bool(custom_url) and ai_mode in ("all", "router", "auto", "custom", "")
    thronos_missing = []
    if not custom_url:
        thronos_missing.append("CUSTOM_MODEL_URL")
    if ai_mode not in ("all", "router", "auto", "custom", ""):
        thronos_missing.append(f"THRONOS_AI_MODE={ai_mode} (restrictive)")
    status["thronos"] = {
        "configured": thronos_configured,
        "checked_env": thronos_vars,
        "missing_env": thronos_missing,
        "source": "registry"
    }

    return status


def find_model(model_id: str) -> Optional[ModelInfo]:
    for provider_models in AI_MODEL_REGISTRY.values():
        for m in provider_models:
            if m.id == model_id:
                return m
    return None


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

