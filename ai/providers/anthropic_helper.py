import os
from typing import Dict, Any, Optional

import anthropic

def _client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("Missing ANTHROPIC_API_KEY")
    return anthropic.Anthropic(api_key=api_key)

def default_model() -> str:
    return os.getenv("ANTHROPIC_DEFAULT_MODEL", "claude-3-5-sonnet-latest")

def generate(prompt: str, model: Optional[str] = None, system_prompt: Optional[str] = None,
             metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    client = _client()
    m = model or default_model()

    sys_prompt = system_prompt or os.getenv("THRONOS_SYSTEM_PROMPT", "")

    resp = client.messages.create(
        model=m,
        max_tokens=4096,
        system=sys_prompt,
        messages=[{"role": "user", "content": prompt}],
    )

    # Anthropic returns a list of content blocks; take the first text block
    text = ""
    if resp.content:
        for block in resp.content:
            if block.type == "text":
                text += block.text
    return {
        "provider": "anthropic",
        "model": m,
        "content": text,
        "raw": resp.model_dump(),
    }
