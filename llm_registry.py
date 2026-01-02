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
        ModelInfo(id="offline_corpus", display_name="Offline corpus", provider="local", tier="local", default=False, enabled=True),
    ],
    "thronos": [
        ModelInfo(id="thrai", display_name="Thronos Thrai", provider="thronos", tier="custom", default=False, enabled=True),
    ],
}


def _apply_env_flags() -> None:
    has_openai = bool((os.getenv("OPENAI_API_KEY") or "").strip())
    has_anthropic = bool((os.getenv("ANTHROPIC_API_KEY") or "").strip())
    has_gemini = bool((os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip())

    for provider_name, models in AI_MODEL_REGISTRY.items():
        if provider_name == "openai":
            enabled = has_openai
        elif provider_name == "anthropic":
            enabled = has_anthropic
        elif provider_name == "gemini":
            enabled = has_gemini
        else:
            enabled = True

        for m in models:
            m.enabled = enabled


_apply_env_flags()


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

import os


def get_default_model_for_mode(mode: str) -> str:
    """
    Επιστρέφει το default μοντέλο για το δοσμένο mode.
    Χρησιμοποιείται από το server.py για να επιλέγει fallback μοντέλο.

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
