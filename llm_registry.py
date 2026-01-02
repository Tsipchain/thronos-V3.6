
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Iterable, Optional


@dataclass
class ModelInfo:
    """
    Canonical registry entry for an AI model that can be used by Thronos.

    The fields here are intentionally generic so they can work across providers.
    Only `id` is required by the low‑level client – everything else is metadata
    for routing / UI / analytics.
    """

    # Identifier that will be passed to the underlying SDK (e.g. "gpt-4o")
    id: str

    # Logical provider name: "openai", "anthropic", "google", "local"
    provider: str

    # Human friendly label shown in the UI
    label: str

    # Short alias we can also accept when resolving (e.g. "gpt4o")
    alias: str

    # Pricing / capability tier – purely descriptive
    tier: str  # e.g. "flagship", "fast", "cheap"

    # Family for grouping (e.g. "gpt-4", "claude-3.5", "gemini-2.0")
    family: str

    # Whether this is a safety tuned / instruction tuned variant
    safety_tuned: bool = True

    # Modality flags
    supports_vision: bool = False
    supports_audio: bool = False
    supports_tools: bool = False

    # Whether this model is available by default in the UI
    enabled_by_default: bool = True

    # Whether Architect is allowed to use this model explicitly
    architect_enabled: bool = True

    # Whether the Quantum chat console can select this model explicitly
    chat_enabled: bool = True


# Base registry – per provider we keep a list of ModelInfo entries.
# NOTE: The `id` values below must match the IDs that the ai_agent_service
#      knows how to call for each provider.
AI_MODEL_REGISTRY: Dict[str, List[ModelInfo]] = {
    "openai": [
        ModelInfo(
            id="gpt-4o",
            provider="openai",
            label="GPT‑4o (general)",
            alias="gpt4o",
            tier="flagship",
            family="gpt-4",
            safety_tuned=True,
            supports_vision=True,
            supports_audio=False,
            supports_tools=True,
            enabled_by_default=True,
            architect_enabled=True,
            chat_enabled=True,
        ),
        ModelInfo(
            id="gpt-4o-mini",
            provider="openai",
            label="GPT‑4o mini (cheap + fast)",
            alias="gpt4o-mini",
            tier="fast",
            family="gpt-4-mini",
            safety_tuned=True,
            supports_vision=True,
            supports_audio=False,
            supports_tools=True,
            enabled_by_default=True,
            architect_enabled=True,
            chat_enabled=True,
        ),
    ],
    "anthropic": [
        ModelInfo(
            id="claude-3.5-sonnet",
            provider="anthropic",
            label="Claude 3.5 Sonnet",
            alias="claude-sonnet-35",
            tier="flagship",
            family="claude-3.5",
            safety_tuned=True,
            supports_vision=True,
            supports_audio=False,
            supports_tools=True,
            enabled_by_default=True,
            architect_enabled=True,
            chat_enabled=True,
        ),
        ModelInfo(
            id="claude-3.5-haiku",
            provider="anthropic",
            label="Claude 3.5 Haiku",
            alias="claude-haiku-35",
            tier="fast",
            family="claude-3.5",
            safety_tuned=True,
            supports_vision=True,
            supports_audio=False,
            supports_tools=True,
            enabled_by_default=True,
            architect_enabled=True,
            chat_enabled=True,
        ),
    ],
    "google": [
        ModelInfo(
            id="gemini-2.0-flash",
            provider="google",
            label="Gemini 2.0 Flash",
            alias="gemini-2.0-flash",
            tier="fast",
            family="gemini-2.0",
            safety_tuned=True,
            supports_vision=True,
            supports_audio=True,
            supports_tools=True,
            enabled_by_default=True,
            architect_enabled=True,
            chat_enabled=True,
        ),
        ModelInfo(
            id="gemini-2.0-pro",
            provider="google",
            label="Gemini 2.0 Pro",
            alias="gemini-2.0-pro",
            tier="flagship",
            family="gemini-2.0",
            safety_tuned=True,
            supports_vision=True,
            supports_audio=True,
            supports_tools=True,
            enabled_by_default=True,
            architect_enabled=True,
            chat_enabled=True,
        ),
    ],
    "local": [
        # Placeholder example – you can wire this to whatever local / Ollama
        # model you want, or leave it disabled in production.
        ModelInfo(
            id="local-llama-3.1",
            provider="local",
            label="Local Llama 3.1 (Ollama)",
            alias="llama-3.1-local",
            tier="experimental",
            family="llama-3.1",
            safety_tuned=False,
            supports_vision=False,
            supports_audio=False,
            supports_tools=False,
            enabled_by_default=False,
            architect_enabled=False,
            chat_enabled=False,
        )
    ],
}


def iter_all_models() -> Iterable[ModelInfo]:
    for models in AI_MODEL_REGISTRY.values():
        for mi in models:
            yield mi


def find_model(key: str) -> Optional[ModelInfo]:
    """
    Resolve a model either by id or alias.
    """
    key = (key or "").strip()
    if not key:
        return None

    for mi in iter_all_models():
        if mi.id == key or mi.alias == key:
            return mi
    return None


def get_default_model_for_mode(mode: str) -> str:
    """
    Fallback defaults when the caller passes model="auto".
    These IDs must also exist in AI_MODEL_REGISTRY above.
    """
    mode = (mode or "").lower()
    if mode in {"architect", "blueprint"}:
        return "gemini-2.0-flash"
    if mode in {"chat", "console", "quantum"}:
        return "gpt-4o"
    # generic fallback
    return "gpt-4o"
