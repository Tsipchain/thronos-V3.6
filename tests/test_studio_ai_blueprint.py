import base64
import io

from flask import Flask
from PIL import Image

import studio_ai_blueprint as studio


def _app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(studio.studio_ai_bp, url_prefix="/api/studio")
    return app


def _png_bytes(width=64, height=96):
    img = Image.new("RGB", (width, height), "white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_studio_routes_require_service_key(monkeypatch):
    monkeypatch.setenv("THRONOS_STUDIO_KEY", "secret")
    client = _app().test_client()

    response = client.get("/api/studio/health")
    assert response.status_code == 401


def test_studio_health_reports_same_monolith_runtime(monkeypatch):
    monkeypatch.setenv("THRONOS_STUDIO_KEY", "secret")
    monkeypatch.setenv("OPENAI_API_KEY", "configured-for-test")
    client = _app().test_client()

    response = client.get(
        "/api/studio/health",
        headers={"X-Internal-Key": "secret"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["runtime"] == "server_ext:app/server.py"
    assert payload["image_provider"] is True
    assert "thronoslabs-kids" in payload["apps"]
    assert "cryptohunters-children" in payload["apps"]
    assert "cryptohunters-game" in payload["apps"]


def test_children_and_game_scopes_are_separate():
    assert studio._APP_PROMPTS["cryptohunters-children"] != studio._APP_PROMPTS["cryptohunters-game"]
    assert "age-appropriate" in studio._APP_PROMPTS["cryptohunters-children"]
    assert "game canon" in studio._APP_PROMPTS["cryptohunters-game"]


def test_studio_chat_uses_existing_ai_layer(monkeypatch):
    monkeypatch.setenv("THRONOS_STUDIO_KEY", "secret")
    seen = {}

    def fake_call(**kwargs):
        seen.update(kwargs)
        return {
            "response": "scoped answer",
            "provider": "openai",
            "model": "test-model",
            "status": "openai",
        }

    monkeypatch.setattr(studio, "_call_existing_llm", fake_call)
    client = _app().test_client()

    response = client.post(
        "/api/studio/chat",
        headers={
            "X-Internal-Key": "secret",
            "X-Thronos-App": "thronoslabs-kids",
        },
        json={
            "messages": [{"role": "user", "content": "Create chapter outline"}],
            "model": "auto",
            "system_prompt": "Use approved Axolotl canon only.",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["content"] == "scoped answer"
    assert seen["app_id"] == "thronoslabs-kids"
    assert seen["model"] == "auto"


def test_studio_chat_rejects_unknown_scope(monkeypatch):
    monkeypatch.setenv("THRONOS_STUDIO_KEY", "secret")
    client = _app().test_client()

    response = client.post(
        "/api/studio/chat",
        headers={
            "X-Internal-Key": "secret",
            "X-Thronos-App": "unknown-app",
        },
        json={"messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "unsupported_app_scope"


def test_studio_image_uses_scoped_prompt_and_normalizes_book_size(monkeypatch):
    monkeypatch.setenv("THRONOS_STUDIO_KEY", "secret")
    seen = {}
    raw = _png_bytes()

    def fake_generate(**kwargs):
        seen.update(kwargs)
        return raw, base64.b64encode(raw).decode("ascii")

    monkeypatch.setattr(studio, "_generate_openai_image", fake_generate)
    client = _app().test_client()

    response = client.post(
        "/api/studio/image",
        headers={
            "X-Internal-Key": "secret",
            "X-Thronos-App": "thronoslabs-kids",
        },
        json={
            "prompt": "Fluffy crosses the crystal bridge.",
            "negative_prompt": "watermark",
            "width": 2550,
            "height": 3300,
            "quality": "medium",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["app_id"] == "thronoslabs-kids"
    assert payload["width"] % 16 == 0
    assert payload["height"] % 16 == 0
    assert payload["width"] * payload["height"] <= studio._MAX_PIXELS
    assert "ThronosLabs Kids" in seen["prompt"]
    assert "Fluffy crosses the crystal bridge." in seen["prompt"]
    assert "watermark" in seen["prompt"]


def test_normalize_image_size_rejects_extreme_ratio():
    try:
        studio._normalize_image_size(3840, 256)
    except ValueError as exc:
        assert "3_to_1" in str(exc)
    else:
        raise AssertionError("expected extreme aspect ratio to be rejected")
