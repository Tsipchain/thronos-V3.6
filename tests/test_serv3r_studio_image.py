import serv3r


def test_studio_scopes_are_registered_in_live_serv3r_runtime():
    assert "ThronosLabs Kids" in serv3r._app_prompt("thronoslabs-kids")
    assert "children's-adaptation" in serv3r._app_prompt("cryptohunters-children")
    assert "game-production" in serv3r._app_prompt("cryptohunters-game")
    assert serv3r._app_prompt("cryptohunters-children") != serv3r._app_prompt("cryptohunters-game")


def test_image_size_normalization_matches_gpt_image_constraints():
    width, height = serv3r._normalize_image_size(2550, 3300)
    assert width == 2544
    assert height == 3296
    assert width % 16 == 0
    assert height % 16 == 0
    assert width <= 3840
    assert height <= 3840


def test_image_size_rejects_extreme_aspect_ratio():
    try:
        serv3r._normalize_image_size(3840, 256)
    except ValueError as exc:
        assert "3:1" in str(exc)
    else:
        raise AssertionError("expected aspect ratio validation failure")


def test_image_endpoint_requires_internal_key(monkeypatch):
    monkeypatch.setattr(serv3r, "INTERNAL_KEY", "test-internal-secret")
    client = serv3r.app.test_client()

    response = client.post(
        "/api/ai/image",
        headers={"X-Thronos-App": "thronoslabs-kids"},
        json={"prompt": "test"},
    )
    assert response.status_code == 401


def test_image_endpoint_rejects_unknown_app_before_provider_call(monkeypatch):
    monkeypatch.setattr(serv3r, "INTERNAL_KEY", "test-internal-secret")
    client = serv3r.app.test_client()

    response = client.post(
        "/api/ai/image",
        headers={
            "X-Internal-Key": "test-internal-secret",
            "X-Thronos-App": "unknown-private-app",
        },
        json={"prompt": "test"},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "unsupported app scope"
