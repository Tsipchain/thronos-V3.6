import os
from typing import Dict, Any, Optional

from openai import OpenAI

def _client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY")
    return OpenAI(api_key=api_key)

def default_model() -> str:
    return os.getenv("OPENAI_DEFAULT_MODEL", "gpt-4.1-mini")

def generate(prompt: str, model: Optional[str] = None, system_prompt: Optional[str] = None,
             metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    client = _client()
    m = model or default_model()

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    resp = client.chat.completions.create(
        model=m,
        messages=messages,
    )

    content = resp.choices[0].message.content
    return {
        "provider": "openai",
        "model": m,
        "content": content,
        "raw": resp.model_dump(),
    }
