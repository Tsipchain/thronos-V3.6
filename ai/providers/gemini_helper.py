import os
from typing import Dict, Any, Optional

import google.generativeai as genai

def _client():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GOOGLE_API_KEY")
    genai.configure(api_key=api_key)

def default_model() -> str:
    return os.getenv("GEMINI_DEFAULT_MODEL", "gemini-2.0-flash-exp")

def generate(prompt: str, model: Optional[str] = None, system_prompt: Optional[str] = None,
             metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    _client()
    m = model or default_model()
    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
    model_obj = genai.GenerativeModel(m)
    resp = model_obj.generate_content(full_prompt)
    text = resp.text or ""

    return {
        "provider": "gemini",
        "model": m,
        "content": text,
        "raw": resp.to_dict(),
    }
