"""Provider-aware LLM router for Thronos Quantum.

This module exposes a single entry point `call_llm` which:
  * Reads provider configuration from environment variables.
  * Normalizes the (provider, model) selection.
  * Dispatches the request to OpenAI, Anthropic or Gemini helpers.
  * Returns a unified response object so the rest of the app stays simple.
"""

import os
from typing import Dict, Any, Optional

from .providers import openai_helper, anthropic_helper, gemini_helper

THRONOS_AI_MODE = os.getenv("THRONOS_AI_MODE", "openai").lower()

def call_llm(
    prompt: str,
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Route a prompt to the correct provider based on THRONOS_AI_MODE and model.

    Returns a dict with:
      - provider: str
      - model: str
      - content: str
      - raw: original provider response (if needed)
    """
    mode = THRONOS_AI_MODE

    if model and ":" in model:
        # allow explicit "provider:model" override from UI
        explicit_provider, explicit_model = model.split(":", 1)
        mode = explicit_provider.lower()
        model = explicit_model

    if mode == "anthropic":
        return anthropic_helper.generate(prompt, model=model, system_prompt=system_prompt, metadata=metadata)
    elif mode == "gemini":
        return gemini_helper.generate(prompt, model=model, system_prompt=system_prompt, metadata=metadata)
    else:
        # default: OpenAI
        return openai_helper.generate(prompt, model=model, system_prompt=system_prompt, metadata=metadata)
