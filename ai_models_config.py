"""AI model catalog configuration.

This module keeps a small curated list of provider/model metadata and is used by
the backend to expose `/api/ai/models` without hard-coding options in the
frontend. OpenAI and Google/Gemini can optionally be refreshed dynamically,
while Anthropic stays curated because their API does not expose a public model
listing endpoint.
"""

from __future__ import annotations

from typing import Dict, List


# Curated defaults that remain valid even if dynamic discovery fails
CURATED_MODELS: Dict[str, dict] = {
    "openai": {
        "models": [
            {"id": "gpt-4.1", "label": "gpt-4.1 (OpenAI)", "default": True},
            {"id": "gpt-4.1-mini", "label": "gpt-4.1-mini"},
            {"id": "o3-mini", "label": "o3-mini (reasoning)"},
        ],
    },
    "anthropic": {
        "models": [
            {"id": "claude-3.5-sonnet-latest", "label": "Claude 3.5 Sonnet", "default": True},
            {"id": "claude-3.5-haiku-latest", "label": "Claude 3.5 Haiku"},
        ],
    },
    "google": {
        "models": [
            {"id": "gemini-2.5-flash-latest", "label": "Gemini 2.5 Flash", "default": True},
            {"id": "gemini-2.5-pro-latest", "label": "Gemini 2.5 Pro"},
        ],
    },
}


# IDs we care about when dynamically fetching from OpenAI
OPENAI_MODEL_FILTER: List[str] = [
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4o",
    "gpt-4o-mini",
    "o3-mini",
]


def base_model_config() -> Dict[str, dict]:
    """Return a deep-ish copy of the curated config so callers can mutate safely."""

    def clone_models(items: List[dict]) -> List[dict]:
        return [dict(item) for item in items]

    return {
        provider: {"models": clone_models(data.get("models", []))}
        for provider, data in CURATED_MODELS.items()
    }

