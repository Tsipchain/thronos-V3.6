from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class ModelInfo:
    id: str
    label: str
    provider: str  # "openai" | "anthropic" | "gemini"
    tier: str = "standard"
    default: bool = False
    enabled: bool = True


AI_MODEL_REGISTRY: Dict[str, List[ModelInfo]] = {
    "openai": [
        ModelInfo(id="gpt-4.1", label="GPT-4.1", provider="openai", tier="premium", default=True),
        ModelInfo(id="gpt-4.1-mini", label="GPT-4.1 mini", provider="openai", tier="fast"),
        ModelInfo(id="o3-mini", label="o3-mini (reasoning)", provider="openai", tier="reasoning"),
    ],
    "anthropic": [
        ModelInfo(id="claude-3.5-sonnet", label="Claude 3.5 Sonnet", provider="anthropic", tier="premium", default=True),
    ],
    "gemini": [
        ModelInfo(id="gemini-1.5-pro", label="Gemini 1.5 Pro", provider="gemini", tier="premium", default=True),
        ModelInfo(id="gemini-1.5-flash", label="Gemini 1.5 Flash", provider="gemini", tier="fast"),
    ],
}


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
