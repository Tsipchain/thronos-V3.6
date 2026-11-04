"""TimeWall provider-card and placement-boundary tests.

The provider's postback formula is intentionally not implemented here: the
account manager still needs to supply the official signed callback contract.
"""
import os
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from flask import Flask

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.earn_account import (  # noqa: E402
    EarnAccountStore,
    EarnError,
    build_timewall_offerwall_url,
    register_earn_account_routes,
)


_KEY = "test-timewall-identity-key"


@pytest.fixture()
def store(tmp_path):
    return EarnAccountStore(str(tmp_path / "earn.db"), _KEY)


@pytest.fixture()
def client(store):
    app = Flask(__name__)
    app.config["TESTING"] = True
    register_earn_account_routes(app, store)
    return app.test_client()


def _login(client):
    client.post("/api/earn/register", json={
        "email": "timewall@example.com", "password": "password123",
    })
    response = client.post("/api/earn/login", json={
        "email": "timewall@example.com", "password": "password123",
    })
    return response.get_json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestTimeWallConfiguration:
    def test_builder_requires_server_configured_template(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TIMEWALL_PLACEMENT_URL", None)
            with pytest.raises(EarnError, match="timewall_not_configured"):
                build_timewall_offerwall_url("tw_test")

    def test_builder_requires_placeholder_and_https(self):
        with patch.dict(os.environ, {"TIMEWALL_PLACEMENT_URL": "http://evil.test"}):
            with pytest.raises(EarnError, match="invalid_timewall_placement"):
                build_timewall_offerwall_url("tw_test")

    def test_builder_replaces_only_server_side_user_id(self):
        with patch.dict(os.environ, {
            "TIMEWALL_PLACEMENT_URL":
            "https://wall.timewall.io/placement/abc?user={user_id}",
        }):
            url = build_timewall_offerwall_url("tw_opaque123")
        assert url == "https://wall.timewall.io/placement/abc?user=tw_opaque123"


class TestTimeWallRoutes:
    def test_provider_listing_contains_disabled_timewall_without_leaks(self, client):
        token = _login(client)
        response = client.get("/api/earn/providers", headers=_auth(token))
        assert response.status_code == 200
        providers = {p["id"]: p for p in response.get_json()["providers"]}
        assert providers["timewall"] == {
            "id": "timewall", "label": "TimeWall", "kind": "tasks", "enabled": False,
        }
        assert "secret" not in response.get_data(as_text=True).lower()

    def test_timewall_offerwall_requires_auth(self, client):
        assert client.get("/api/earn/timewall/offerwall").status_code == 401

    def test_timewall_requires_both_flag_and_placement(self, client):
        token = _login(client)
        with patch.dict(os.environ, {"TIMEWALL_ENABLED": "1"}, clear=False):
            os.environ.pop("TIMEWALL_PLACEMENT_URL", None)
            response = client.get("/api/earn/timewall/offerwall", headers=_auth(token))
        assert response.status_code == 503
        assert response.get_json()["error"] == "timewall_not_configured"

    def test_timewall_offerwall_returns_opaque_server_identity(self, client, store):
        token = _login(client)
        with patch.dict(os.environ, {
            "TIMEWALL_ENABLED": "1",
            "TIMEWALL_PLACEMENT_URL": "https://wall.timewall.io/p/abc?user={user_id}",
            "TIMEWALL_SECRET_KEY": "must-never-be-returned",
        }):
            response = client.get("/api/earn/timewall/offerwall", headers=_auth(token))
        assert response.status_code == 200
        body = response.get_json()
        assert body["provider"] == "timewall"
        assert "tw_" in body["url"]
        assert "timewall@example.com" not in body["url"]
        assert "must-never-be-returned" not in response.get_data(as_text=True)
        with sqlite3.connect(store.db_path) as con:
            con.row_factory = sqlite3.Row
            identities = con.execute(
                "SELECT provider, provider_user_id FROM earn_provider_identities"
            ).fetchall()
        assert [(r["provider"], r["provider_user_id"]) for r in identities] == [
            ("timewall", body["url"].split("user=", 1)[1])
        ]

    def test_timewall_identity_is_stable_and_route_is_present(self, client):
        token = _login(client)
        with patch.dict(os.environ, {
            "TIMEWALL_ENABLED": "1",
            "TIMEWALL_PLACEMENT_URL": "https://wall.timewall.io/p/abc?user={user_id}",
        }):
            first = client.get("/api/earn/timewall/offerwall", headers=_auth(token))
            second = client.get("/api/earn/timewall/offerwall", headers=_auth(token))
        assert first.get_json()["url"] == second.get_json()["url"]
        assert "/api/earn/timewall/offerwall" in {
            r.rule for r in client.application.url_map.iter_rules()
        }


class TestTimeWallTemplate:
    def test_frontend_has_three_named_provider_choices_and_no_secret(self):
        html = (Path(__file__).parent.parent / "templates" / "earn_beta.html").read_text()
        for marker in ("provider-cpx", "provider-pure", "provider-timewall",
                       "earn-timewall", "/api/earn/timewall/offerwall"):
            assert marker in html
        assert "TIMEWALL_SECRET_KEY" not in html
