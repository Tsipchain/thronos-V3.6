"""Internal Studio AI routes for ThronosLabs production services.

Mounted by server_ext.py on the same Flask app/process that imports server.py.
This is NOT a second AI core. It is a service-to-service interface over the
existing Thronos AI/provider layer.

Endpoints:
  GET  /api/studio/health
  POST /api/studio/chat
  POST /api/studio/image

Authentication:
  X-Internal-Key: <THRONOS_STUDIO_KEY or APP_AI_KEY>
  Authorization: Bearer <same key>

Creative scopes are explicit and isolated:
  thronoslabs-kids
  cryptohunters-children
  cryptohunters-game
"""
from __future__ import annotations

import base64
import io
import math
import os
from typing import Any

from flask import Blueprint, jsonify, request
from PIL import Image

studio_ai_bp = Blueprint("studio_ai", __name__)

_ALLOWED_APPS = {
    "thronoslabs-kids",
    "cryptohunters-children",
    "cryptohunters-game",
}

_APP_PROMPTS = {
    "thronoslabs-kids": (
        "You are the ThronosLabs Kids production AI. Work only from owner-approved "
        "canon supplied by the requesting service. Follow target age and audience. "
        "Preserve approved character names, visual traits, relationships and style. "
        "Never silently invent canon. Treat all creative memory and characters as "
        "private tenant-scoped IP and never reuse them across tenants."
    ),
    "cryptohunters-children": (
        "You are the Crypto Hunters children's-adaptation production AI. Use only "
        "owner-approved children's canon and aliases. Keep output age-appropriate. "
        "Do not import mature cybercrime, political, violent or dark-market framing "
        "directly from game canon. Never invent missing child aliases; flag them. "
        "Treat all characters and unreleased story material as private tenant-scoped IP."
    ),
    "cryptohunters-game": (
        "You are the Crypto Hunters game-production AI. Work from approved game canon "
        "for characters, equipment, story, UI and gameplay assets. Keep children's "
        "adaptation aliases separate from game canon. Treat unreleased character and "
        "story material as private tenant-scoped IP."
    ),
}

_MAX_IMAGE_BYTES = 50 * 1024 * 1024
_MAX_EDGE = 3840
_MAX_PIXELS = 8_294_400
_MIN_PIXELS = 655_360


def _studio_key() -> str:
    return (
        os.getenv("THRONOS_STUDIO_KEY", "").strip()
        or os.getenv("APP_AI_KEY", "").strip()
    )


def _authorized() -> bool:
    expected = _studio_key()
    if not expected:
        return False
    auth = request.headers.get("Authorization", "")
    bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    provided = (
        request.headers.get("X-Internal-Key")
        or request.headers.get("X-API-Key")
        or bearer
        or ""
    ).strip()
    return bool(provided and provided == expected)


def _require_auth():
    if not _studio_key():
        return jsonify(ok=False, error="studio_service_key_not_configured"), 503
    if not _authorized():
        return jsonify(ok=False, error="unauthorized"), 401
    return None


def _app_id() -> str:
    return (request.headers.get("X-Thronos-App") or "").strip().lower()


def _validate_app(app_id: str):
    if app_id not in _ALLOWED_APPS:
        return jsonify(ok=False, error="unsupported_app_scope"), 400
    return None


def _normalize_image_size(width: int, height: int) -> tuple[int, int]:
    """Normalize to current GPT Image custom-resolution constraints.

    - dimensions are multiples of 16
    - max edge 3840
    - aspect ratio <= 3:1
    - total pixels within supported bounds
    """
    width = max(256, int(width))
    height = max(256, int(height))

    scale = min(1.0, _MAX_EDGE / width, _MAX_EDGE / height)
    width = max(256, int(width * scale))
    height = max(256, int(height * scale))

    ratio = max(width, height) / min(width, height)
    if ratio > 3:
        raise ValueError("aspect_ratio_exceeds_3_to_1")

    pixels = width * height
    if pixels > _MAX_PIXELS:
        scale = math.sqrt(_MAX_PIXELS / pixels)
        width = max(256, int(width * scale))
        height = max(256, int(height * scale))

    width = max(256, (width // 16) * 16)
    height = max(256, (height // 16) * 16)

    if width * height < _MIN_PIXELS:
        # Preserve aspect ratio while raising pixel count to the supported floor.
        scale = math.sqrt(_MIN_PIXELS / (width * height))
        width = min(_MAX_EDGE, max(256, int(width * scale)))
        height = min(_MAX_EDGE, max(256, int(height * scale)))
        width = max(256, (width // 16) * 16)
        height = max(256, (height // 16) * 16)

    if width * height > _MAX_PIXELS:
        raise ValueError("pixel_count_exceeds_provider_limit")
    return width, height


def _scoped_system_prompt(app_id: str, supplied: str = "") -> str:
    base = _APP_PROMPTS[app_id]
    supplied = (supplied or "").strip()
    return f"{base}\n\n{suppplied}" if supplied else base


def _call_existing_llm(
    *,
    app_id: str,
    messages: list[dict[str, str]],
    model: str,
    system_prompt: str,
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    from ai_agent_service import call_llm

    return call_llm(
        model=model or "auto",
        messages=messages,
        system_prompt=_scoped_system_prompt(app_id, system_prompt),
        temperature=temperature,
        max_tokens=max_tokens,
        session_id=None,
        wallet=None,
        chain_context={"origin": "studio_service", "app_id": app_id},
    )


def _generate_openai_image(
    *,
    prompt: str,
    model: str,
    width: int,
    height: int,
    quality: str,
) -> tuple[bytes, str]:
    api_key = (os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("openai_image_provider_not_configured")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    result = client.images.generate(
        model=model,
        prompt=prompt,
        size=f"{width}x{height}",
        quality=quality,
        output_format="png",
    )
    encoded = result.data[0].b64_json if result.data else None
    if not encoded:
        raise RuntimeError("image_provider_returned_no_data")

    raw = base64.b64decode(encoded, validate=True)
    if not raw or len(raw) > _MAX_IMAGE_BYTES:
        raise RuntimeError("image_provider_returned_invalid_size")

    img = Image.open(io.BytesIO(raw))
    img.verify()
    return raw, encoded


@studio_ai_bp.get("/health")
def studio_health():
    denied = _require_auth()
    if denied:
        return denied

    return jsonify(
        ok=True,
        service="thronos-studio-ai",
        runtime="server_ext:app/server.py",
        apps=sorted(_ALLOWED_APPS),
        text_provider=True,
        image_provider=bool(
            (os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY") or "").strip()
        ),
        image_model=os.getenv("AI_IMAGE_MODEL", "gpt-image-2"),
    ), 200


@studio_ai_bp.post("/chat")
def studio_chat():
    denied = _require_auth()
    if denied:
        return denied

    app_id = _app_id()
    invalid = _validate_app(app_id)
    if invalid:
        return invalid

    data = request.get_json(silent=True) or {}
    messages = data.get("messages") or []
    if not isinstance(messages, list) or not messages:
        return jsonify(ok=False, error="messages_array_required"), 400

    cleaned: list[dict[str, str]] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user").strip().lower()
        content = str(item.get("content") or "").strip()
        if role not in {"system", "user", "assistant"} or not content:
            continue
        cleaned.append({"role": role, "content": content})

    if not cleaned:
        return jsonify(ok=False, error="no_valid_messages"), 400

    model = str(data.get("model") or "auto").strip()
    supplied_system = str(data.get("system_prompt") or "").strip()
    temperature = float(data.get("temperature", 0.3))
    max_tokens = max(64, min(int(data.get("max_tokens", 2048)), 8192))

    try:
        result = _call_existing_llm(
            app_id=app_id,
            messages=cleaned,
            model=model,
            system_prompt=supplied_system,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        return jsonify(ok=False, error="provider_error", reason=str(exc)), 503

    response_text = (
        result.get("response")
        if isinstance(result, dict)
        else str(result or "")
    )
    if not response_text:
        return jsonify(ok=False, error="empty_provider_response"), 503

    return jsonify(
        ok=True,
        content=response_text,
        app_id=app_id,
        provider=result.get("provider") if isinstance(result, dict) else None,
        model=result.get("model") if isinstance(result, dict) else model,
        status=result.get("status") if isinstance(result, dict) else "ok",
    ), 200


@studio_ai_bp.post("/image")
def studio_image():
    denied = _require_auth()
    if denied:
        return denied

    app_id = _app_id()
    invalid = _validate_app(app_id)
    if invalid:
        return invalid

    data = request.get_json(silent=True) or {}
    prompt = str(data.get("prompt") or "").strip()
    if not prompt:
        return jsonify(ok=False, error="prompt_required"), 400

    negative = str(data.get("negative_prompt") or "").strip()
    model = str(data.get("model") or os.getenv("AI_IMAGE_MODEL", "gpt-image-2")).strip()
    quality = str(data.get("quality") or os.getenv("AI_IMAGE_QUALITY", "medium")).strip().lower()
    if quality not in {"auto", "low", "medium", "high"}:
        return jsonify(ok=False, error="invalid_quality"), 400

    try:
        width, height = _normalize_image_size(
            int(data.get("width", 2048)),
            int(data.get("height", 2656)),
        )
    except (TypeError, ValueError) as exc:
        return jsonify(ok=False, error="invalid_image_size", reason=str(exc)), 400

    scoped_prompt = f"{_APP_PROMPTS[app_id]}\n\nIMAGE TASK:\n{prompt}"
    if negative:
        scoped_prompt += f"\n\nAVOID:\n{negative}"

    try:
        raw, encoded = _generate_openai_image(
            prompt=scoped_prompt,
            model=model,
            width=width,
            height=height,
            quality=quality,
        )
    except Exception as exc:
        return jsonify(ok=False, error="image_provider_error", reason=str(exc)), 503

    return jsonify(
        ok=True,
        image_base64=encoded,
        format="png",
        width=width,
        height=height,
        byte_size=len(raw),
        model=model,
        quality=quality,
        app_id=app_id,
    ), 200
