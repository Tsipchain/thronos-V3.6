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
"""
import os
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from flask import Flask

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.earn_account import (
    EarnAccountStore,
    EarnError,
    build_cpx_offerwall_url,
    register_earn_account_routes,
    verify_cpx_postback_signature,
)

_TEST_KEY = "test-earn-identity-key-e2e"

_CPX_ENV = {
    "CPX_APP_ID": "test-app",
    "CPX_APP_SECURE_HASH": "test-secret",
    "CPX_POSTBACK_SIGNATURE_MODE": "md5_trans_id_dash_secret_v1",
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
        assert body["expires_in"] == 900

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
        assert balance["pending"] == 500.0
        assert balance["available"] == 0.0

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
        assert store.thc_balance(user_a["earn_user_id"])["pending"] == 300.0

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
        assert store.thc_balance(user_a["earn_user_id"])["pending"] == 1000.0

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
        assert store.thc_balance(user_a["earn_user_id"])["pending"] == 400.0

        r2, changed = store.record_cpx_receipt(
            trans_id="tx-rev", cpx_ext_user_id=u["cpx_ext_user_id"],
            status=2, amount_local="400", payload={"status": "2"},
        )
        assert changed is True
        assert r2["status"] == 2

        balance = store.thc_balance(user_a["earn_user_id"])
        assert balance["pending"] == 0.0
        assert balance["available"] == 0.0

    def test_reversal_of_confirmed_entry(self, store, user_a):
        _, t = store.login("alice@example.com", "password123")
        u = store.user_for_session(t)
        r, _ = store.record_cpx_receipt(
            trans_id="tx-rev2", cpx_ext_user_id=u["cpx_ext_user_id"],
            status=1, amount_local="200", payload={},
        )
        store.transition_thc(r["thc_entry_id"], "confirmed")
        assert store.thc_balance(user_a["earn_user_id"])["available"] == 200.0

        store.record_cpx_receipt(
            trans_id="tx-rev2", cpx_ext_user_id=u["cpx_ext_user_id"],
            status=2, amount_local="200", payload={},
        )
        assert store.thc_balance(user_a["earn_user_id"])["available"] == 0.0


# ══════════════════════════════════════════════════════════════════════════
# 7. NO THC CREDIT UNTIL VERIFIED CALLBACK
# ══════════════════════════════════════════════════════════════════════════


class TestNoPreemptiveCredit:
    def test_new_account_has_zero_balance(self, store, user_a):
        balance = store.thc_balance(user_a["earn_user_id"])
        assert balance["available"] == 0.0
        assert balance["pending"] == 0.0
        assert balance["total_earned"] == 0.0

    def test_pending_not_in_available_balance(self, store, user_a):
        _, t = store.login("alice@example.com", "password123")
        u = store.user_for_session(t)
        store.record_cpx_receipt(
            trans_id="tx-pend", cpx_ext_user_id=u["cpx_ext_user_id"],
            status=1, amount_local="1000", payload={},
        )
        balance = store.thc_balance(user_a["earn_user_id"])
        assert balance["pending"] == 1000.0
        assert balance["available"] == 0.0

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
        assert alice_history[0]["amount"] == 100.0
        assert bob_history[0]["amount"] == 200.0

    def test_api_history_is_scoped(self, client, user_a, user_b, store):
        store.record_thc_credit(user_a["earn_user_id"], "cpx", "a-2", "50")
        store.record_thc_credit(user_b["earn_user_id"], "cpx", "b-2", "75")

        token_a = _login(client, "alice@example.com", "password123")
        resp = client.get("/api/earn/history", headers=_auth(token_a))
        entries = resp.get_json()["entries"]
        assert len(entries) == 1
        assert entries[0]["amount"] == 50.0

    def test_api_balance_is_scoped(self, client, user_a, user_b, store):
        e, _ = store.record_thc_credit(user_a["earn_user_id"], "cpx", "a-3", "300")
        store.transition_thc(e["entry_id"], "confirmed")
        store.record_thc_credit(user_b["earn_user_id"], "cpx", "b-3", "500")

        token_a = _login(client, "alice@example.com", "password123")
        resp = client.get("/api/earn/balance", headers=_auth(token_a))
        assert resp.get_json()["available"] == 300.0


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
        assert balance.get_json()["available"] == 0.0

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
            import hashlib as hl
            expected = hl.md5(b"tx-99-test-secret").hexdigest()
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
