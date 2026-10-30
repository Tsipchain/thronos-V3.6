"""
Integration tests for the account-first Earn beta.

Covers:
  1. Registration / login / session security
  2. Server-side CPX identity (never browser-supplied)
  3. Postback idempotency and concurrent delivery
  4. Reversal handling (CPX status=2 reverses THC entry)
  5. No wallet required
  6. No THC credit until verified callback
  7. History isolation between two Earn Accounts
  8. Rate limiting on login
  9. Balance excludes pending entries
 10. CPX MD5 signature compatibility with known fixtures
 11. Decimal precision (no float)
"""
import hashlib
import os
import sys
import threading
import time
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from flask import Flask

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.earn_account import (
    _SESSION_COOKIE,
    _SESSION_TTL,
    EarnAccountStore,
    EarnError,
    build_cpx_offerwall_url,
    cpx_postback_hash,
    register_earn_account_routes,
    verify_cpx_postback_signature,
)

_TEST_KEY = "test-earn-identity-key-e2e"

_CPX_ENV = {
    "CPX_APP_ID": "test-app",
    "CPX_APP_SECURE_HASH": "test-secret",
    "CPX_POSTBACK_LIVE": "1",
    "CPX_SURVEYS_BETA_ENABLED": "1",
}


@pytest.fixture()
def store(tmp_path):
    return EarnAccountStore(str(tmp_path / "earn.db"), _TEST_KEY)


@pytest.fixture()
def user_a(store):
    return store.register("alice@example.com", "password123")


@pytest.fixture()
def user_b(store):
    return store.register("bob@example.com", "password456")


@pytest.fixture()
def app(store):
    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    register_earn_account_routes(flask_app, store)
    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


def _login(client, email="alice@example.com", password="password123"):
    resp = client.post("/api/earn/login", json={"email": email, "password": password})
    return resp.get_json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ══════════════════════════════════════════════════════════════════════════
# 1. REGISTRATION
# ══════════════════════════════════════════════════════════════════════════


class TestRegistration:
    def test_register_success(self, client):
        resp = client.post("/api/earn/register", json={
            "email": "new@example.com", "password": "secure123",
        })
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["ok"] is True
        assert body["earn_user_id"].startswith("earn_")
        assert body["email"] == "new@example.com"
        assert body["email_verified"] is False

    def test_duplicate_email_rejected(self, client, user_a):
        resp = client.post("/api/earn/register", json={
            "email": "alice@example.com", "password": "another123",
        })
        assert resp.status_code == 400
        assert "already_registered" in resp.get_json()["error"]

    def test_case_insensitive_email(self, client, user_a):
        resp = client.post("/api/earn/register", json={
            "email": "ALICE@EXAMPLE.COM", "password": "another123",
        })
        assert resp.status_code == 400

    def test_invalid_email_rejected(self, client):
        resp = client.post("/api/earn/register", json={
            "email": "not-an-email", "password": "secure123",
        })
        assert resp.status_code == 400
        assert "invalid_email" in resp.get_json()["error"]

    def test_short_password_rejected(self, client):
        resp = client.post("/api/earn/register", json={
            "email": "x@example.com", "password": "short",
        })
        assert resp.status_code == 400
        assert "password_too_short" in resp.get_json()["error"]

    def test_no_wallet_required(self, client):
        resp = client.post("/api/earn/register", json={
            "email": "walletless@example.com", "password": "password123",
        })
        assert resp.status_code == 201
        body = resp.get_json()
        assert "wallet" not in body
        assert "wallet_address" not in body


# ══════════════════════════════════════════════════════════════════════════
# 2. LOGIN + SESSION SECURITY
# ══════════════════════════════════════════════════════════════════════════


class TestLoginSession:
    def test_login_returns_token(self, client, user_a):
        resp = client.post("/api/earn/login", json={
            "email": "alice@example.com", "password": "password123",
        })
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        assert "access_token" in body
        assert body["expires_in"] == _SESSION_TTL
        assert _SESSION_TTL == 30 * 24 * 60 * 60
        cookie = resp.headers.get("Set-Cookie", "")
        assert f"{_SESSION_COOKIE}=" in cookie
        assert "HttpOnly" in cookie
        assert "Secure" in cookie
        assert "SameSite=Lax" in cookie

    def test_cookie_session_authenticates_without_bearer_header(self, client, user_a):
        login = client.post("/api/earn/login", json={
            "email": "alice@example.com", "password": "password123",
        }, base_url="https://api.thronoschain.org")
        assert login.status_code == 200
        # Flask's test client retains the secure same-origin cookie.
        me = client.get("/api/earn/me", base_url="https://api.thronoschain.org")
        assert me.status_code == 200
        assert me.get_json()["earn_user_id"] == user_a["earn_user_id"]

    def test_wrong_password_rejected(self, client, user_a):
        resp = client.post("/api/earn/login", json={
            "email": "alice@example.com", "password": "wrong",
        })
        assert resp.status_code == 401
        assert "invalid_credentials" in resp.get_json()["error"]

    def test_generic_error_for_unknown_email(self, client):
        resp = client.post("/api/earn/login", json={
            "email": "nobody@example.com", "password": "anything123",
        })
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "invalid_credentials"

    def test_me_endpoint_requires_auth(self, client):
        resp = client.get("/api/earn/me")
        assert resp.status_code == 401

    def test_me_returns_user_info(self, client, user_a):
        token = _login(client)
        resp = client.get("/api/earn/me", headers=_auth(token))
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["earn_user_id"] == user_a["earn_user_id"]
        assert body["email"] == "alice@example.com"
        assert "password" not in str(body)


class TestEarnCoursesSafetyContract:
    def test_courses_use_stable_earn_identity_and_do_not_forge_card_payment(self):
        root = Path(__file__).parent.parent
        courses = (root / "templates" / "courses.html").read_text()
        server = (root / "server.py").read_text()
        assert "activeLearnerId()" in courses
        assert "restoreEarnAccount()" in courses
        assert "pi_demo_" not in courses
        assert "course_stripe_checkout_not_enabled" in server

    def test_logout_invalidates_session(self, client, user_a):
        token = _login(client)
        client.post("/api/earn/logout", headers=_auth(token))
        resp = client.get("/api/earn/me", headers=_auth(token))
        assert resp.status_code == 401

    def test_session_rotation(self, client, user_a):
        old_token = _login(client)
        resp = client.post("/api/earn/session/rotate", headers=_auth(old_token))
        assert resp.status_code == 200
        new_token = resp.get_json()["access_token"]
        assert new_token != old_token
        assert client.get("/api/earn/me", headers=_auth(old_token)).status_code == 401
        assert client.get("/api/earn/me", headers=_auth(new_token)).status_code == 200


# ══════════════════════════════════════════════════════════════════════════
# 3. RATE LIMITING
# ══════════════════════════════════════════════════════════════════════════


class TestRateLimiting:
    def test_lockout_after_max_failures(self, client, user_a):
        for _ in range(5):
            client.post("/api/earn/login", json={
                "email": "alice@example.com", "password": "wrong",
            })
        resp = client.post("/api/earn/login", json={
            "email": "alice@example.com", "password": "password123",
        })
        assert resp.status_code == 429
        assert "locked" in resp.get_json()["error"]

    def test_successful_login_clears_attempts(self, client, user_a):
        for _ in range(3):
            client.post("/api/earn/login", json={
                "email": "alice@example.com", "password": "wrong",
            })
        resp = client.post("/api/earn/login", json={
            "email": "alice@example.com", "password": "password123",
        })
        assert resp.status_code == 200
        resp2 = client.post("/api/earn/login", json={
            "email": "alice@example.com", "password": "wrong",
        })
        assert resp2.status_code == 401


# ══════════════════════════════════════════════════════════════════════════
# 4. SERVER-SIDE CPX IDENTITY
# ══════════════════════════════════════════════════════════════════════════


class TestCPXIdentity:
    def test_cpx_id_is_server_generated(self, store, user_a):
        user, _ = store.login("alice@example.com", "password123")
        session_user = store.user_for_session(_)
        assert session_user["cpx_ext_user_id"].startswith("thr_")
        assert session_user["cpx_ext_user_id"] != user_a["earn_user_id"]

    def test_cpx_id_is_deterministic(self, store, user_a):
        _, t1 = store.login("alice@example.com", "password123")
        _, t2 = store.login("alice@example.com", "password123")
        u1 = store.user_for_session(t1)
        u2 = store.user_for_session(t2)
        assert u1["cpx_ext_user_id"] == u2["cpx_ext_user_id"]

    def test_different_users_get_different_cpx_ids(self, store, user_a, user_b):
        _, ta = store.login("alice@example.com", "password123")
        _, tb = store.login("bob@example.com", "password456")
        ua = store.user_for_session(ta)
        ub = store.user_for_session(tb)
        assert ua["cpx_ext_user_id"] != ub["cpx_ext_user_id"]

    def test_offerwall_requires_auth(self, client):
        resp = client.get("/api/earn/cpx/offerwall")
        assert resp.status_code == 401

    @patch.dict(os.environ, _CPX_ENV, clear=False)
    def test_offerwall_url_uses_server_cpx_id(self, client, user_a):
        token = _login(client)
        resp = client.get("/api/earn/cpx/offerwall", headers=_auth(token))
        assert resp.status_code == 200
        url = resp.get_json()["url"]
        assert "ext_user_id=thr_" in url
        assert "test-secret" not in url

    def test_no_browser_supplied_ext_user_id_in_source(self):
        """The route code must not read ext_user_id from the request."""
        source = (Path(__file__).parent.parent / "services" / "earn_account.py").read_text()
        for line in source.split("\n"):
            if "ext_user_id" in line and "request" in line:
                pytest.fail(f"Browser-supplied ext_user_id found: {line.strip()}")


class TestProviderAvailability:
    # --- Test 1: GET /api/earn/providers requires authenticated Earn session ---

    def test_provider_listing_requires_an_authenticated_earn_account(self, client):
        assert client.get("/api/earn/providers").status_code == 401

    def test_provider_listing_rejects_invalid_bearer_token(self, client, user_a):
        resp = client.get("/api/earn/providers", headers=_auth("bad-token-xxx"))
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "earn_auth_required"

    # --- Test 2: Response exposes only provider availability, never keys/secrets/URLs ---

    @patch.dict(os.environ, {"CPX_SURVEYS_BETA_ENABLED": "1", "BITCOTASKS_ENABLED": "0"}, clear=False)
    def test_provider_listing_exposes_feature_state_not_credentials(self, client, user_a):
        token = _login(client)
        response = client.get("/api/earn/providers", headers=_auth(token))
        assert response.status_code == 200
        body = response.get_json()
        assert body["ok"] is True
        providers = {item["id"]: item for item in body["providers"]}
        assert providers["cpx"]["enabled"] is True
        assert providers["bitcotasks"]["enabled"] is False
        assert "api_key" not in str(body).lower()
        assert "secret" not in str(body).lower()

    @patch.dict(os.environ, {
        "CPX_SURVEYS_BETA_ENABLED": "1", "BITCOTASKS_ENABLED": "1",
        "CPX_APP_SECURE_HASH": "super-secret-cpx", "BITCOTASKS_SECRET": "super-secret-bt",
    }, clear=False)
    def test_provider_response_never_leaks_env_secrets(self, client, user_a):
        token = _login(client)
        resp = client.get("/api/earn/providers", headers=_auth(token))
        raw = resp.get_data(as_text=True).lower()
        for forbidden in ["super-secret-cpx", "super-secret-bt", "api_key", "secret_key",
                          "private_key", "password", "token", "hash"]:
            assert forbidden not in raw, f"Forbidden value '{forbidden}' leaked in provider response"
        body = resp.get_json()
        for p in body["providers"]:
            allowed_keys = {"id", "label", "kind", "enabled"}
            assert set(p.keys()) == allowed_keys, f"Provider {p['id']} exposes extra keys: {set(p.keys()) - allowed_keys}"

    # --- Test 3: CPX enabled/disabled state is correct ---

    @patch.dict(os.environ, {"CPX_SURVEYS_BETA_ENABLED": "0"}, clear=False)
    def test_cpx_disabled_when_env_is_zero(self, client, user_a):
        token = _login(client)
        resp = client.get("/api/earn/providers", headers=_auth(token))
        providers = {p["id"]: p for p in resp.get_json()["providers"]}
        assert providers["cpx"]["enabled"] is False

    @patch.dict(os.environ, {"CPX_SURVEYS_BETA_ENABLED": "1"}, clear=False)
    def test_cpx_enabled_when_env_is_one(self, client, user_a):
        token = _login(client)
        resp = client.get("/api/earn/providers", headers=_auth(token))
        providers = {p["id"]: p for p in resp.get_json()["providers"]}
        assert providers["cpx"]["enabled"] is True

    # --- Test 4: BitcoTasks remains disabled unless BITCOTASKS_ENABLED=1 ---

    @patch.dict(os.environ, {"BITCOTASKS_ENABLED": "0"}, clear=False)
    def test_bitcotasks_disabled_by_default(self, client, user_a):
        token = _login(client)
        resp = client.get("/api/earn/providers", headers=_auth(token))
        providers = {p["id"]: p for p in resp.get_json()["providers"]}
        assert providers["bitcotasks"]["enabled"] is False

    @patch.dict(os.environ, {"BITCOTASKS_ENABLED": "1"}, clear=False)
    def test_bitcotasks_enabled_only_when_flag_is_one(self, client, user_a):
        token = _login(client)
        resp = client.get("/api/earn/providers", headers=_auth(token))
        providers = {p["id"]: p for p in resp.get_json()["providers"]}
        assert providers["bitcotasks"]["enabled"] is True

    def test_bitcotasks_disabled_when_env_unset(self, client, user_a):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BITCOTASKS_ENABLED", None)
            token = _login(client)
            resp = client.get("/api/earn/providers", headers=_auth(token))
            providers = {p["id"]: p for p in resp.get_json()["providers"]}
            assert providers["bitcotasks"]["enabled"] is False


# ══════════════════════════════════════════════════════════════════════════
# 4b. EARN ROUTE COLLISION AND INTEGRATED ACCOUNT FLOW
# ══════════════════════════════════════════════════════════════════════════


class TestEarnRouteCollision:
    """Test 5: No route collision with existing Earn routes."""

    def test_all_earn_routes_are_unique(self, app):
        earn_rules = [
            rule for rule in app.url_map.iter_rules()
            if rule.rule.startswith("/api/earn")
        ]
        seen = {}
        for rule in earn_rules:
            for method in rule.methods - {"HEAD", "OPTIONS"}:
                key = (method, rule.rule)
                assert key not in seen, (
                    f"Route collision: {method} {rule.rule} registered twice "
                    f"(endpoints: {seen[key]} and {rule.endpoint})"
                )
                seen[key] = rule.endpoint

    def test_providers_route_does_not_shadow_cpx_or_bitcotasks(self, app):
        rules = {r.rule for r in app.url_map.iter_rules()}
        assert "/api/earn/providers" in rules
        assert "/api/earn/cpx/offerwall" in rules
        assert "/api/earn/bitcotasks/offerwall" in rules


class TestIntegratedAccountFlow:
    """Test 6: /api/earn/me, balance, history and provider list work together."""

    @patch.dict(os.environ, _CPX_ENV, clear=False)
    def test_full_authenticated_account_flow(self, client, store, user_a):
        token = _login(client)
        headers = _auth(token)

        me_resp = client.get("/api/earn/me", headers=headers)
        assert me_resp.status_code == 200
        me = me_resp.get_json()
        assert me["ok"] is True
        assert me["email"] == "alice@example.com"
        assert me["earn_user_id"].startswith("earn_")

        bal_resp = client.get("/api/earn/balance", headers=headers)
        assert bal_resp.status_code == 200
        bal = bal_resp.get_json()
        assert bal["ok"] is True
        assert "available" in bal
        assert "pending" in bal
        assert bal["currency"] == "THC"

        hist_resp = client.get("/api/earn/history", headers=headers)
        assert hist_resp.status_code == 200
        hist = hist_resp.get_json()
        assert hist["ok"] is True
        assert isinstance(hist["entries"], list)

        prov_resp = client.get("/api/earn/providers", headers=headers)
        assert prov_resp.status_code == 200
        prov = prov_resp.get_json()
        assert prov["ok"] is True
        assert len(prov["providers"]) >= 2
        provider_ids = {p["id"] for p in prov["providers"]}
        assert "cpx" in provider_ids
        assert "bitcotasks" in provider_ids

    @patch.dict(os.environ, _CPX_ENV, clear=False)
    def test_all_endpoints_reject_without_auth(self, client):
        for endpoint in ["/api/earn/me", "/api/earn/balance",
                         "/api/earn/history", "/api/earn/providers"]:
            resp = client.get(endpoint)
            assert resp.status_code == 401, f"{endpoint} did not require auth"


class TestActivityOutputSafety:
    """Test 7: Activity/history output is safe for wallet-linked and email-only accounts."""

    @patch.dict(os.environ, _CPX_ENV, clear=False)
    def test_history_safe_for_email_only_account(self, client, store, user_a):
        token = _login(client)
        headers = _auth(token)

        me = client.get("/api/earn/me", headers=headers).get_json()
        assert me["wallet_address"] is None

        u = store.user_for_session(token)
        store.record_cpx_receipt(
            trans_id="tx-safe-1", cpx_ext_user_id=u["cpx_ext_user_id"],
            status=1, amount_local="100", payload={"status": "1"},
        )

        hist = client.get("/api/earn/history", headers=headers).get_json()
        assert hist["ok"] is True
        assert len(hist["entries"]) >= 1
        raw = str(hist).lower()
        for forbidden in ["private_key", "secret", "password", "api_key", "mnemonic"]:
            assert forbidden not in raw, f"Forbidden '{forbidden}' in history output"

        entry = hist["entries"][0]
        assert "amount" in entry
        assert "state" in entry
        assert "source" in entry

    @patch.dict(os.environ, _CPX_ENV, clear=False)
    def test_history_safe_for_wallet_linked_account(self, client, store, user_a):
        token = _login(client)
        headers = _auth(token)

        with store._tx() as con:
            con.execute(
                "INSERT OR REPLACE INTO earn_wallet_links (wallet_address, earn_user_id, public_key, linked_at) VALUES (?,?,?,?)",
                ("THR_TEST_WALLET_ADDR", user_a["earn_user_id"], "pubkey_placeholder", int(time.time())),
            )

        me = client.get("/api/earn/me", headers=headers).get_json()
        assert me["wallet_address"] == "THR_TEST_WALLET_ADDR"

        u = store.user_for_session(token)
        store.record_cpx_receipt(
            trans_id="tx-safe-2", cpx_ext_user_id=u["cpx_ext_user_id"],
            status=1, amount_local="200", payload={"status": "1"},
        )

        hist = client.get("/api/earn/history", headers=headers).get_json()
        assert hist["ok"] is True
        assert len(hist["entries"]) >= 1
        raw = str(hist).lower()
        for forbidden in ["private_key", "secret", "password", "api_key"]:
            assert forbidden not in raw

        bal = client.get("/api/earn/balance", headers=headers).get_json()
        assert bal["ok"] is True
        assert Decimal(bal["pending"]) >= Decimal("200")

    @patch.dict(os.environ, _CPX_ENV, clear=False)
    def test_two_accounts_history_isolated(self, client, store, user_a, user_b):
        token_a = _login(client, "alice@example.com", "password123")
        token_b = _login(client, "bob@example.com", "password456")

        u_a = store.user_for_session(token_a)
        store.record_cpx_receipt(
            trans_id="tx-iso-alice", cpx_ext_user_id=u_a["cpx_ext_user_id"],
            status=1, amount_local="500", payload={"status": "1"},
        )

        hist_b = client.get("/api/earn/history", headers=_auth(token_b)).get_json()
        assert hist_b["ok"] is True
        assert len(hist_b["entries"]) == 0


# ══════════════════════════════════════════════════════════════════════════
# 5. THC LEDGER — POSTBACK IDEMPOTENCY
# ══════════════════════════════════════════════════════════════════════════


class TestPostbackIdempotency:
    def test_receipt_creates_pending_thc_entry(self, store, user_a):
        _, t = store.login("alice@example.com", "password123")
        u = store.user_for_session(t)
        receipt, created = store.record_cpx_receipt(
            trans_id="tx-100", cpx_ext_user_id=u["cpx_ext_user_id"],
            status=1, amount_local="500", payload={"status": "1"},
        )
        assert created is True
        assert receipt["thc_entry_id"] is not None

        balance = store.thc_balance(user_a["earn_user_id"])
        assert Decimal(balance["pending"]) == Decimal("500")
        assert Decimal(balance["available"]) == Decimal("0")

    def test_duplicate_receipt_is_idempotent(self, store, user_a):
        _, t = store.login("alice@example.com", "password123")
        u = store.user_for_session(t)
        r1, c1 = store.record_cpx_receipt(
            trans_id="tx-dup", cpx_ext_user_id=u["cpx_ext_user_id"],
            status=1, amount_local="300", payload={},
        )
        r2, c2 = store.record_cpx_receipt(
            trans_id="tx-dup", cpx_ext_user_id=u["cpx_ext_user_id"],
            status=1, amount_local="300", payload={},
        )
        assert c1 is True
        assert c2 is False
        assert r1["trans_id"] == r2["trans_id"]
        assert Decimal(store.thc_balance(user_a["earn_user_id"])["pending"]) == Decimal("300")

    def test_concurrent_postbacks_no_duplicate_credits(self, store, user_a):
        _, t = store.login("alice@example.com", "password123")
        u = store.user_for_session(t)
        errors = []

        def post(i):
            try:
                store.record_cpx_receipt(
                    trans_id=f"concurrent-{i}",
                    cpx_ext_user_id=u["cpx_ext_user_id"],
                    status=1, amount_local="100", payload={},
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=post, args=(i,)) for i in range(10)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert errors == []
        entries = store.thc_history(user_a["earn_user_id"], limit=200)
        assert len(entries) == 10
        assert Decimal(store.thc_balance(user_a["earn_user_id"])["pending"]) == Decimal("1000")

    def test_conflicting_user_for_same_trans_id_rejected(self, store, user_a, user_b):
        _, ta = store.login("alice@example.com", "password123")
        _, tb = store.login("bob@example.com", "password456")
        ua = store.user_for_session(ta)
        ub = store.user_for_session(tb)
        store.record_cpx_receipt(
            trans_id="tx-conflict", cpx_ext_user_id=ua["cpx_ext_user_id"],
            status=1, amount_local="100", payload={},
        )
        with pytest.raises(EarnError, match="cpx_receipt_conflict"):
            store.record_cpx_receipt(
                trans_id="tx-conflict", cpx_ext_user_id=ub["cpx_ext_user_id"],
                status=1, amount_local="100", payload={},
            )


# ══════════════════════════════════════════════════════════════════════════
# 6. REVERSAL HANDLING
# ══════════════════════════════════════════════════════════════════════════


class TestReversalHandling:
    def test_reversal_sets_thc_entry_to_reversed(self, store, user_a):
        _, t = store.login("alice@example.com", "password123")
        u = store.user_for_session(t)
        r1, _ = store.record_cpx_receipt(
            trans_id="tx-rev", cpx_ext_user_id=u["cpx_ext_user_id"],
            status=1, amount_local="400", payload={},
        )
        assert Decimal(store.thc_balance(user_a["earn_user_id"])["pending"]) == Decimal("400")

        r2, changed = store.record_cpx_receipt(
            trans_id="tx-rev", cpx_ext_user_id=u["cpx_ext_user_id"],
            status=2, amount_local="400", payload={"status": "2"},
        )
        assert changed is True
        assert r2["status"] == 2

        balance = store.thc_balance(user_a["earn_user_id"])
        assert Decimal(balance["pending"]) == Decimal("0")
        assert Decimal(balance["available"]) == Decimal("0")

    def test_reversal_of_confirmed_entry(self, store, user_a):
        _, t = store.login("alice@example.com", "password123")
        u = store.user_for_session(t)
        r, _ = store.record_cpx_receipt(
            trans_id="tx-rev2", cpx_ext_user_id=u["cpx_ext_user_id"],
            status=1, amount_local="200", payload={},
        )
        store.transition_thc(r["thc_entry_id"], "confirmed")
        assert Decimal(store.thc_balance(user_a["earn_user_id"])["available"]) == Decimal("200")

        store.record_cpx_receipt(
            trans_id="tx-rev2", cpx_ext_user_id=u["cpx_ext_user_id"],
            status=2, amount_local="200", payload={},
        )
        assert Decimal(store.thc_balance(user_a["earn_user_id"])["available"]) == Decimal("0")


# ══════════════════════════════════════════════════════════════════════════
# 7. NO THC CREDIT UNTIL VERIFIED CALLBACK
# ══════════════════════════════════════════════════════════════════════════


class TestNoPreemptiveCredit:
    def test_new_account_has_zero_balance(self, store, user_a):
        balance = store.thc_balance(user_a["earn_user_id"])
        assert Decimal(balance["available"]) == Decimal("0")
        assert Decimal(balance["pending"]) == Decimal("0")
        assert Decimal(balance["total_earned"]) == Decimal("0")

    def test_pending_not_in_available_balance(self, store, user_a):
        _, t = store.login("alice@example.com", "password123")
        u = store.user_for_session(t)
        store.record_cpx_receipt(
            trans_id="tx-pend", cpx_ext_user_id=u["cpx_ext_user_id"],
            status=1, amount_local="1000", payload={},
        )
        balance = store.thc_balance(user_a["earn_user_id"])
        assert Decimal(balance["pending"]) == Decimal("1000")
        assert Decimal(balance["available"]) == Decimal("0")

    def test_paid_requires_real_settlement_ref(self, store, user_a):
        entry, _ = store.record_thc_credit(
            user_a["earn_user_id"], "test", "ref-1", "50",
        )
        store.transition_thc(entry["entry_id"], "confirmed")
        store.transition_thc(entry["entry_id"], "payable")
        with pytest.raises(EarnError, match="settlement_ref_required"):
            store.transition_thc(entry["entry_id"], "paid")
        result = store.transition_thc(
            entry["entry_id"], "paid", settlement_ref="BTC-real-txid",
        )
        assert result["state"] == "paid"
        assert result["settlement_ref"] == "BTC-real-txid"


# ══════════════════════════════════════════════════════════════════════════
# 8. HISTORY ISOLATION BETWEEN ACCOUNTS
# ══════════════════════════════════════════════════════════════════════════


class TestHistoryIsolation:
    def test_alice_cannot_see_bob_entries(self, store, user_a, user_b):
        store.record_thc_credit(user_a["earn_user_id"], "cpx", "a-1", "100")
        store.record_thc_credit(user_b["earn_user_id"], "cpx", "b-1", "200")

        alice_history = store.thc_history(user_a["earn_user_id"])
        bob_history = store.thc_history(user_b["earn_user_id"])
        assert len(alice_history) == 1
        assert len(bob_history) == 1
        assert Decimal(alice_history[0]["amount"]) == Decimal("100")
        assert Decimal(bob_history[0]["amount"]) == Decimal("200")

    def test_api_history_is_scoped(self, client, user_a, user_b, store):
        store.record_thc_credit(user_a["earn_user_id"], "cpx", "a-2", "50")
        store.record_thc_credit(user_b["earn_user_id"], "cpx", "b-2", "75")

        token_a = _login(client, "alice@example.com", "password123")
        resp = client.get("/api/earn/history", headers=_auth(token_a))
        entries = resp.get_json()["entries"]
        assert len(entries) == 1
        assert Decimal(str(entries[0]["amount"])) == Decimal("50")

    def test_api_balance_is_scoped(self, client, user_a, user_b, store):
        e, _ = store.record_thc_credit(user_a["earn_user_id"], "cpx", "a-3", "300")
        store.transition_thc(e["entry_id"], "confirmed")
        store.record_thc_credit(user_b["earn_user_id"], "cpx", "b-3", "500")

        token_a = _login(client, "alice@example.com", "password123")
        resp = client.get("/api/earn/balance", headers=_auth(token_a))
        assert Decimal(str(resp.get_json()["available"])) == Decimal("300")


# ══════════════════════════════════════════════════════════════════════════
# 9. NO WALLET REQUIRED
# ══════════════════════════════════════════════════════════════════════════


class TestNoWalletRequired:
    def test_full_flow_without_wallet(self, client, store):
        reg = client.post("/api/earn/register", json={
            "email": "nochain@example.com", "password": "password123",
        })
        assert reg.status_code == 201
        uid = reg.get_json()["earn_user_id"]

        login = client.post("/api/earn/login", json={
            "email": "nochain@example.com", "password": "password123",
        })
        assert login.status_code == 200
        token = login.get_json()["access_token"]

        me = client.get("/api/earn/me", headers=_auth(token))
        body = me.get_json()
        assert "wallet" not in body
        assert body["earn_user_id"] == uid

        balance = client.get("/api/earn/balance", headers=_auth(token))
        assert balance.status_code == 200
        assert Decimal(str(balance.get_json()["available"])) == Decimal("0")

    def test_source_has_no_wallet_requirement(self):
        source = (Path(__file__).parent.parent / "services" / "earn_account.py").read_text()
        assert "wallet_address" not in source
        assert "wallet NOT NULL" not in source


# ══════════════════════════════════════════════════════════════════════════
# 10. CPX POSTBACK API (HTTP layer)
# ══════════════════════════════════════════════════════════════════════════


class TestCPXPostbackAPI:
    @patch.dict(os.environ, _CPX_ENV, clear=False)
    def test_postback_rejects_bad_signature(self, client, user_a):
        resp = client.post("/api/earn/cpx/postback", data={
            "trans_id": "tx-api-1", "user_id": "thr_fake",
            "secure_hash": "bad", "status": "1", "amount_local": "100",
        })
        assert resp.status_code == 403

    @patch.dict(os.environ, {**_CPX_ENV, "CPX_POSTBACK_LIVE": "0"}, clear=False)
    def test_postback_disabled_returns_503(self, client):
        resp = client.post("/api/earn/cpx/postback", data={"trans_id": "x"})
        assert resp.status_code == 503

    def test_postback_signature_verification(self):
        with patch.dict(os.environ, _CPX_ENV, clear=False):
            expected = hashlib.md5(b"tx-99-test-secret").hexdigest()
            assert verify_cpx_postback_signature("tx-99", expected) is True
            assert verify_cpx_postback_signature("tx-99", "wrong") is False

    def test_offerwall_url_never_exposes_secret(self):
        with patch.dict(os.environ, _CPX_ENV, clear=False):
            url = build_cpx_offerwall_url("thr_abc123")
            assert "test-secret" not in url
            assert "app_id=test-app" in url


# ══════════════════════════════════════════════════════════════════════════
# 11. THC STATE MACHINE
# ══════════════════════════════════════════════════════════════════════════


class TestTHCStateMachine:
    def test_valid_transition_chain(self, store, user_a):
        e, _ = store.record_thc_credit(user_a["earn_user_id"], "t", "r1", "10")
        assert e["state"] == "pending"
        e = store.transition_thc(e["entry_id"], "confirmed")
        assert e["state"] == "confirmed"
        e = store.transition_thc(e["entry_id"], "payable")
        assert e["state"] == "payable"
        e = store.transition_thc(e["entry_id"], "paid", settlement_ref="TX123")
        assert e["state"] == "paid"

    def test_invalid_transition_rejected(self, store, user_a):
        e, _ = store.record_thc_credit(user_a["earn_user_id"], "t", "r2", "10")
        with pytest.raises(EarnError, match="invalid_thc_transition"):
            store.transition_thc(e["entry_id"], "payable")

    def test_reversal_from_any_non_terminal_state(self, store, user_a):
        for i, via in enumerate(["pending", "confirmed", "payable", "paid"]):
            e, _ = store.record_thc_credit(
                user_a["earn_user_id"], "t", f"rev-{i}", "10",
            )
            if via != "pending":
                e = store.transition_thc(e["entry_id"], "confirmed")
            if via in ("payable", "paid"):
                e = store.transition_thc(e["entry_id"], "payable")
            if via == "paid":
                e = store.transition_thc(
                    e["entry_id"], "paid", settlement_ref=f"TX-{i}",
                )
            result = store.transition_thc(e["entry_id"], "reversed")
            assert result["state"] == "reversed"

    def test_reversed_is_terminal(self, store, user_a):
        e, _ = store.record_thc_credit(user_a["earn_user_id"], "t", "r3", "10")
        store.transition_thc(e["entry_id"], "reversed")
        with pytest.raises(EarnError, match="invalid_thc_transition"):
            store.transition_thc(e["entry_id"], "confirmed")

    def test_idempotent_same_state_transition(self, store, user_a):
        e, _ = store.record_thc_credit(user_a["earn_user_id"], "t", "r4", "10")
        e2 = store.transition_thc(e["entry_id"], "pending")
        assert e2["state"] == "pending"


# ══════════════════════════════════════════════════════════════════════════
# 12. IDENTITY KEY SAFETY
# ══════════════════════════════════════════════════════════════════════════


class TestIdentityKeySafety:
    def test_missing_identity_key_raises(self, tmp_path):
        with pytest.raises(EarnError, match="earn_identity_key_not_configured"):
            EarnAccountStore(str(tmp_path / "bad.db"), "")

    def test_change_me_identity_key_raises(self, tmp_path):
        with pytest.raises(EarnError, match="earn_identity_key_not_configured"):
            EarnAccountStore(str(tmp_path / "bad.db"), "CHANGE_ME")

    def test_no_secrets_in_source(self):
        source = (Path(__file__).parent.parent / "services" / "earn_account.py").read_text()
        assert "APP_AI_KEY" not in source
        assert "admin_key" not in source
        assert "CHANGE_ME" not in source.replace('"CHANGE_ME"', "").replace("'CHANGE_ME'", "")


# ══════════════════════════════════════════════════════════════════════════
# 13. CPX MD5 SIGNATURE COMPATIBILITY (known fixtures)
# ══════════════════════════════════════════════════════════════════════════


class TestCPXSignatureCompatibility:
    """Verified CPX production callback formula: md5(trans_id + "-" + CPX_APP_SECURE_HASH).

    These fixtures use known trans_id and secret values to verify the exact
    documented formula. If any of these fail, the signature code has deviated
    from the CPX specification.
    """

    def test_documented_formula_fixture_1(self):
        result = cpx_postback_hash("12345", "mysecret")
        expected = hashlib.md5(b"12345-mysecret").hexdigest()
        assert result == expected

    def test_documented_formula_fixture_2(self):
        result = cpx_postback_hash("tx-abc-999", "prod-secure-hash-value")
        expected = hashlib.md5(b"tx-abc-999-prod-secure-hash-value").hexdigest()
        assert result == expected

    def test_documented_formula_fixture_3(self):
        result = cpx_postback_hash("0", "x")
        expected = hashlib.md5(b"0-x").hexdigest()
        assert result == expected

    def test_verify_accepts_correct_hash(self):
        secret = "production-secret-abc"
        trans_id = "tx-9999"
        correct = hashlib.md5(f"{trans_id}-{secret}".encode()).hexdigest()
        with patch.dict(os.environ, {"CPX_APP_SECURE_HASH": secret}):
            assert verify_cpx_postback_signature(trans_id, correct) is True

    def test_verify_rejects_wrong_hash(self):
        with patch.dict(os.environ, {"CPX_APP_SECURE_HASH": "secret123"}):
            assert verify_cpx_postback_signature("tx-1", "deadbeef") is False

    def test_verify_rejects_empty_secret(self):
        with patch.dict(os.environ, {"CPX_APP_SECURE_HASH": ""}):
            assert verify_cpx_postback_signature("tx-1", "anything") is False

    def test_verify_rejects_empty_trans_id(self):
        with patch.dict(os.environ, {"CPX_APP_SECURE_HASH": "secret"}):
            assert verify_cpx_postback_signature("", "anything") is False

    def test_verify_case_insensitive_on_received_hash(self):
        secret = "test-secret"
        tid = "tx-case"
        correct = hashlib.md5(f"{tid}-{secret}".encode()).hexdigest()
        with patch.dict(os.environ, {"CPX_APP_SECURE_HASH": secret}):
            assert verify_cpx_postback_signature(tid, correct.upper()) is True

    def test_no_cpx_survey_secret_in_source(self):
        """Must only use CPX_APP_SECURE_HASH, never CPX_SURVEY_SECRET."""
        source = (Path(__file__).parent.parent / "services" / "earn_account.py").read_text()
        assert "CPX_SURVEY_SECRET" not in source

    def test_no_custom_hmac_sha256_for_signature(self):
        """CPX callback uses MD5, not HMAC-SHA256."""
        source = (Path(__file__).parent.parent / "services" / "earn_account.py").read_text()
        in_verify = False
        for line in source.split("\n"):
            if "def verify_cpx_postback_signature" in line or "def cpx_postback_hash" in line:
                in_verify = True
            elif in_verify and line and not line.startswith(" ") and not line.startswith("\t"):
                in_verify = False
            if in_verify and "sha256" in line.lower() and "hmac" in line.lower():
                pytest.fail(f"HMAC-SHA256 found in CPX signature code: {line.strip()}")

    def test_no_signature_mode_gate(self):
        """The documented formula must not be gated behind an env var mode switch."""
        source = (Path(__file__).parent.parent / "services" / "earn_account.py").read_text()
        assert "CPX_POSTBACK_SIGNATURE_MODE" not in source


# ══════════════════════════════════════════════════════════════════════════
# 14. DECIMAL PRECISION — NO FLOAT
# ══════════════════════════════════════════════════════════════════════════


class TestDecimalPrecision:
    """THC amounts must never pass through float().

    Repeated small credits that would accumulate floating-point error
    under float arithmetic must produce an exact total under Decimal.
    """

    def test_no_float_in_service_source(self):
        source = (Path(__file__).parent.parent / "services" / "earn_account.py").read_text()
        for i, line in enumerate(source.split("\n"), 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"') or stripped.startswith("'"):
                continue
            if "float(" in line:
                pytest.fail(f"float() found at line {i}: {stripped}")
            if "AS REAL" in line.upper():
                pytest.fail(f"CAST AS REAL found at line {i}: {stripped}")

    def test_repeated_small_credits_exact_total(self, store, user_a):
        uid = user_a["earn_user_id"]
        for i in range(100):
            store.record_thc_credit(uid, "precision", f"p-{i}", "0.01")
        balance = store.thc_balance(uid)
        assert Decimal(balance["pending"]) == Decimal("1.000000")

    def test_fractional_credits_sum_exactly(self, store, user_a):
        uid = user_a["earn_user_id"]
        store.record_thc_credit(uid, "precision", "f-1", "0.1")
        store.record_thc_credit(uid, "precision", "f-2", "0.2")
        store.record_thc_credit(uid, "precision", "f-3", "0.3")
        balance = store.thc_balance(uid)
        assert Decimal(balance["pending"]) == Decimal("0.600000")

    def test_large_credit_exact(self, store, user_a):
        uid = user_a["earn_user_id"]
        store.record_thc_credit(uid, "precision", "big-1", "999999.999999")
        balance = store.thc_balance(uid)
        assert Decimal(balance["pending"]) == Decimal("999999.999999")

    def test_amount_stored_as_quantized_string(self, store, user_a):
        uid = user_a["earn_user_id"]
        e, _ = store.record_thc_credit(uid, "precision", "q-1", "5")
        assert e["amount"] == "5.000000"
        e2, _ = store.record_thc_credit(uid, "precision", "q-2", "3.1")
        assert e2["amount"] == "3.100000"

    def test_balance_returns_strings_not_floats(self, store, user_a):
        uid = user_a["earn_user_id"]
        balance = store.thc_balance(uid)
        for key in ("available", "pending", "total_earned", "paid_out"):
            assert isinstance(balance[key], str), f"{key} is not a string"

    def test_cpx_receipt_amount_quantized(self, store, user_a):
        _, t = store.login("alice@example.com", "password123")
        u = store.user_for_session(t)
        r, _ = store.record_cpx_receipt(
            trans_id="tx-dec-1", cpx_ext_user_id=u["cpx_ext_user_id"],
            status=1, amount_local="12.345678999", payload={},
        )
        thc = store.thc_history(user_a["earn_user_id"], limit=1)
        assert Decimal(thc[0]["amount"]) == Decimal("12.345678")


# ══════════════════════════════════════════════════════════════════════════
# 15. FULL-SERVER ROUTE INTEGRATION (production registration paths)
# ══════════════════════════════════════════════════════════════════════════


class TestFullServerRouteIntegration:
    """Exercise the ACTUAL production registration factories from both
    earn_center.py and earn_account.py on the same Flask app to verify:

      - When both EARN_CENTER_ENABLED=1 and EARN_ACCOUNT_ENABLED=1 are set,
        server.py's production guard prevents legacy routes from loading.
      - /api/earn/cpx/postback resolves to one unambiguous POST handler.
      - A signed CPX callback writes only to the Account-first THC ledger.
      - The legacy wallet-bound cpx_receipts table stays empty.
    """

    @pytest.fixture()
    def dual_setup(self, tmp_path):
        """Register BOTH production route sets on one Flask app,
        reproducing the production registration order from server.py:
          1. Account-first at line ~1130 (registered first)
          2. Legacy Earn Center at line ~48438 (registered second)
        Legacy is loaded here to prove cross-ledger isolation; in
        production, server.py prevents this double-registration.
        """
        import sqlite3 as _sqlite3
        from services.earn_center import (
            EarnStore as LegacyEarnStore,
            register_earn_routes as register_legacy_routes,
        )

        env = {
            "EARN_ACCOUNT_ENABLED": "1",
            "EARN_CENTER_ENABLED": "1",
            "EARN_IDENTITY_KEY": _TEST_KEY,
            "CPX_APP_ID": "test-app",
            "CPX_APP_SECURE_HASH": "test-secret",
            "CPX_POSTBACK_LIVE": "1",
            "CPX_SURVEYS_BETA_ENABLED": "1",
        }

        acct_db = str(tmp_path / "earn_accounts.db")
        legacy_db = str(tmp_path / "earn_center.db")

        with patch.dict(os.environ, env, clear=False):
            flask_app = Flask(__name__)
            flask_app.config["TESTING"] = True

            acct_store = EarnAccountStore(acct_db, _TEST_KEY)
            legacy_store = LegacyEarnStore(legacy_db, _TEST_KEY)

        def _stub_wallet_proof(proof):
            return False, "", "stubbed_out"

        # These two production factories deliberately cannot coexist: both
        # expose the same Flask endpoint name and callback URL.  Production
        # must therefore install only Account-first routes when it is active.
        register_earn_account_routes(flask_app, acct_store)
        with pytest.raises(AssertionError):
            register_legacy_routes(flask_app, legacy_store, _stub_wallet_proof)

        return flask_app, acct_store, legacy_store, acct_db, legacy_db, _stub_wallet_proof

    @pytest.fixture()
    def acct_only_app(self, tmp_path):
        """Account-first routes ONLY — the production path when
        EARN_ACCOUNT_ENABLED supersedes legacy."""
        env = {
            "EARN_ACCOUNT_ENABLED": "1",
            "EARN_IDENTITY_KEY": _TEST_KEY,
            "CPX_APP_ID": "test-app",
            "CPX_APP_SECURE_HASH": "test-secret",
            "CPX_POSTBACK_LIVE": "1",
            "CPX_SURVEYS_BETA_ENABLED": "1",
        }
        acct_db = str(tmp_path / "earn_accounts.db")
        with patch.dict(os.environ, env, clear=False):
            flask_app = Flask(__name__)
            flask_app.config["TESTING"] = True
            acct_store = EarnAccountStore(acct_db, _TEST_KEY)
            register_earn_account_routes(flask_app, acct_store)
        return flask_app, acct_store, acct_db

    # ── Route map tests ─────────────────────────────────────────────────

    def test_account_only_has_one_postback_route(self, acct_only_app):
        app, _, _ = acct_only_app
        postback_rules = [
            r for r in app.url_map.iter_rules()
            if r.rule == "/api/earn/cpx/postback"
        ]
        assert len(postback_rules) == 1

    def test_account_only_has_all_expected_routes(self, acct_only_app):
        app, _, _ = acct_only_app
        rules = {r.rule for r in app.url_map.iter_rules()}
        expected = {
            "/api/earn/register",
            "/api/earn/login",
            "/api/earn/logout",
            "/api/earn/me",
            "/api/earn/balance",
            "/api/earn/history",
            "/api/earn/cpx/offerwall",
            "/api/earn/cpx/postback",
            "/api/earn/session/rotate",
        }
        missing = expected - rules
        assert not missing, f"Missing routes: {missing}"

    def test_no_legacy_wallet_routes(self, acct_only_app):
        app, _, _ = acct_only_app
        rules = {r.rule for r in app.url_map.iter_rules()}
        assert "/api/earn/authenticate" not in rules

    # ── CPX callback writes ONLY to Account-first ledger ────────────────

    def test_postback_writes_to_account_first_ledger(self, acct_only_app):
        import sqlite3 as _sqlite3
        app, store, acct_db = acct_only_app
        with patch.dict(os.environ, {
            "CPX_POSTBACK_LIVE": "1",
            "CPX_APP_SECURE_HASH": "test-secret",
        }, clear=False):
            store.register("acctuser@example.com", "password123")
            _, token = store.login("acctuser@example.com", "password123")
            u = store.user_for_session(token)
            tid = "tx-cross-ledger-1"
            sig = hashlib.md5(f"{tid}-test-secret".encode()).hexdigest()
            with app.test_client() as client:
                resp = client.post("/api/earn/cpx/postback", data={
                    "trans_id": tid,
                    "user_id": u["cpx_ext_user_id"],
                    "secure_hash": sig,
                    "status": "1",
                    "amount_local": "750",
                })
                assert resp.status_code == 200
                assert resp.data == b"1"

        balance = store.thc_balance(
            store.user_for_session(token)["earn_user_id"],
        )
        assert Decimal(balance["pending"]) == Decimal("750")

        con = _sqlite3.connect(acct_db)
        try:
            row = con.execute(
                "SELECT * FROM cpx_receipts WHERE trans_id = ?", (tid,),
            ).fetchone()
            assert row is not None, "Receipt missing from Account-first DB"
            thc_row = con.execute(
                "SELECT * FROM thc_ledger WHERE source_ref = ?", (tid,),
            ).fetchone()
            assert thc_row is not None, "THC entry missing from Account-first DB"
        finally:
            con.close()

    def test_legacy_factory_cannot_shadow_account_postback(self, dual_setup):
        import sqlite3 as _sqlite3
        app, acct_store, legacy_store, acct_db, legacy_db, _ = dual_setup
        with patch.dict(os.environ, {
            "CPX_POSTBACK_LIVE": "1",
            "CPX_APP_SECURE_HASH": "test-secret",
        }, clear=False):
            acct_store.register("cross@example.com", "password123")
            _, token = acct_store.login("cross@example.com", "password123")
            u = acct_store.user_for_session(token)
            tid = "tx-cross-ledger-2"
            sig = hashlib.md5(f"{tid}-test-secret".encode()).hexdigest()
            with app.test_client() as client:
                resp = client.post("/api/earn/cpx/postback", data={
                    "trans_id": tid,
                    "user_id": u["cpx_ext_user_id"],
                    "secure_hash": sig,
                    "status": "1",
                    "amount_local": "500",
                })
                assert resp.status_code == 200

        # The failed legacy registration cannot receive the callback.  Its
        # database exists solely because its store was constructed, and must
        # remain empty after the Account-first request.
        con = _sqlite3.connect(legacy_db)
        try:
            count = con.execute("SELECT COUNT(*) FROM cpx_receipts").fetchone()[0]
            assert count == 0, f"Legacy cpx_receipts has {count} rows — leak!"
        finally:
            con.close()

    def test_bad_signature_rejected(self, acct_only_app):
        app, store, _ = acct_only_app
        with patch.dict(os.environ, {
            "CPX_POSTBACK_LIVE": "1",
            "CPX_APP_SECURE_HASH": "test-secret",
        }, clear=False):
            store.register("reject@example.com", "password123")
            _, token = store.login("reject@example.com", "password123")
            u = store.user_for_session(token)
            with app.test_client() as client:
                resp = client.post("/api/earn/cpx/postback", data={
                    "trans_id": "tx-bad",
                    "user_id": u["cpx_ext_user_id"],
                    "secure_hash": "forged_hash",
                    "status": "1",
                    "amount_local": "100",
                })
                assert resp.status_code == 403

    # ── Production server.py guards ─────────────────────────────────────

    def test_is_master_gate_in_server_source(self):
        """server.py must gate earn_account registration behind is_master()."""
        source = (Path(__file__).parent.parent / "server.py").read_text()
        found = False
        for line in source.split("\n"):
            if "EARN_ACCOUNT_ENABLED" in line and "is_master()" in line:
                found = True
                break
        assert found, "EARN_ACCOUNT_ENABLED registration must be gated by is_master()"

    def test_server_supersedes_legacy_when_account_enabled(self):
        """When EARN_ACCOUNT_ENABLED is set, server.py must skip legacy
        Earn Center route registration to prevent route shadowing."""
        source = (Path(__file__).parent.parent / "server.py").read_text()
        found_guard = False
        for line in source.split("\n"):
            if "EARN_ACCOUNT_ENABLED" in line and "supersede" in line.lower():
                found_guard = True
                break
            if "_earn_acct_active" in line and "EARN_ACCOUNT_ENABLED" in line:
                found_guard = True
                break
        assert found_guard, (
            "server.py must skip legacy Earn Center routes when "
            "EARN_ACCOUNT_ENABLED supersedes them"
        )

    def test_server_only_supersedes_legacy_on_master(self):
        """A shared feature flag must not suppress the legacy service on a
        non-Master replica, where Account-first routes are not registered."""
        source = (Path(__file__).parent.parent / "server.py").read_text()
        assert "and is_master()" in source[source.index("_earn_acct_active"):source.index("if _earn_acct_active")]

    def test_legacy_block_checks_earn_acct_active(self):
        """The legacy Earn Center registration block must check that
        Account-first is not already active before calling
        register_earn_routes.  In server.py the guard sets
        _earn_acct_active *before* the elif that loads legacy routes."""
        source = (Path(__file__).parent.parent / "server.py").read_text()
        lines = source.split("\n")
        acct_active_line = None
        register_legacy_line = None
        for i, line in enumerate(lines):
            if line.strip().startswith("_earn_acct_active ="):
                acct_active_line = i
            if "register_earn_routes(" in line and acct_active_line is not None:
                register_legacy_line = i
                break
        assert acct_active_line is not None, (
            "_earn_acct_active guard not found in server.py"
        )
        assert register_legacy_line is not None, (
            "register_earn_routes call not found after _earn_acct_active"
        )
        assert acct_active_line < register_legacy_line, (
            "_earn_acct_active must be checked before register_earn_routes"
        )


class TestEarnTemplateCookieSession:
    """A restored HttpOnly session must not be shadowed by Bearer null."""

    def test_restored_cookie_session_omits_empty_bearer_header(self):
        template = (Path(__file__).parent.parent / "templates" / "earn_beta.html").read_text()
        assert "function earnAuthHeaders()" in template
        assert "return token ? {'Authorization': 'Bearer ' + token} : {};" in template
        assert "headers: earnAuthHeaders()" in template
        assert "'Authorization':'Bearer '+token" not in template
        assert "if (!token) return;" not in template

    def test_dashboard_always_exposes_available_and_pending_balances(self):
        template = (Path(__file__).parent.parent / "templates" / "earn_beta.html").read_text()
        assert "AVAILABLE THC" in template
        assert "PENDING THC" in template
        # Decimal strings are deliberately formatted without Number()/float conversion.
        assert "formatThc(bData.available)" in template
        assert "formatThc(bData.pending)" in template
        assert "Number(bData.available" not in template
        assert "Number(bData.pending" not in template
        assert "No verified Earn receipts yet." in template

    def test_mobile_provider_tab_preserves_earn_dashboard(self):
        template = (Path(__file__).parent.parent / "templates" / "earn_beta.html").read_text()
        assert "window.open('', '_blank')" in template
        assert "providerTab.location.replace(data.url)" in template
        assert "window.addEventListener('focus'" in template
        assert "visibilitychange" in template

    def test_provider_cards_and_compact_activity_dialog_are_present(self):
        template = (Path(__file__).parent.parent / "templates" / "earn_beta.html").read_text()
        assert "/api/earn/providers" in template
        assert "Open BitcoTasks" in template
        assert "earn-activity-dialog" in template
        assert "activityDialog.showModal()" in template
        assert "source.textContent" in template

    def test_activity_view_explains_link_and_unavailable_settlement(self):
        template = (Path(__file__).parent.parent / "templates" / "earn_beta.html").read_text()
        assert "earn-wallet-status" in template
        assert "Cash-out" in template
        assert "Not enabled yet." in template
        assert "get('view') === 'activity'" in template