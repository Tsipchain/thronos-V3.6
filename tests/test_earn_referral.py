"""Tests for the Earn referral system."""
import os
import pytest
import tempfile
from decimal import Decimal
from unittest.mock import patch

os.environ.setdefault("EARN_DB_PATH", ":memory:")

from services.earn_account import EarnAccountStore


_TEST_KEY = "test-identity-key-for-referrals-abcdef"


@pytest.fixture()
def store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    s = EarnAccountStore(path, _TEST_KEY)
    yield s
    os.unlink(path)


class TestEarnReferral:

    @staticmethod
    def _release(store, earned_user_id, monkeypatch):
        deadline = store.thc_history(earned_user_id)[0]["earn_hold_until"]
        monkeypatch.setattr("services.earn_account.time.time", lambda: deadline)
        with patch.dict(os.environ, {
            "NODE_ROLE": "master", "READ_ONLY": "0", "SCHEDULER_ENABLED": "1",
        }):
            assert store.release_mature_earn_holds() == 1

    @staticmethod
    def _cpx_reward(store, earned_user, trans_id, amount):
        store.record_cpx_receipt(
            trans_id=trans_id,
            cpx_ext_user_id=earned_user["cpx_ext_user_id"],
            status=1,
            amount_local=amount,
            payload={"status": "1"},
        )

    def test_register_with_referral_code(self, store):
        referrer = store.register("referrer@test.com", "SecurePass123!")
        referred = store.register(
            "friend@test.com", "SecurePass456!",
            ref_code=referrer["earn_user_id"],
        )
        stats = store.referral_stats(referrer["earn_user_id"])
        assert stats["referral_count"] == 1

    def test_referral_stats_empty_by_default(self, store):
        user = store.register("solo@test.com", "SecurePass123!")
        stats = store.referral_stats(user["earn_user_id"])
        assert stats["referral_count"] == 0

    def test_referral_list_returns_masked_emails(self, store):
        referrer = store.register("boss@test.com", "SecurePass123!")
        store.register(
            "friend1@test.com", "SecurePass456!",
            ref_code=referrer["earn_user_id"],
        )
        store.register(
            "friend2@test.com", "SecurePass789!",
            ref_code=referrer["earn_user_id"],
        )
        refs = store.referral_list(referrer["earn_user_id"])
        assert len(refs) == 2
        for ref in refs:
            assert "***" in ref["email_hint"]
            assert ref["created_at"] > 0

    def test_invalid_referral_code_ignored(self, store):
        user = store.register(
            "newbie@test.com", "SecurePass123!",
            ref_code="nonexistent_user_id",
        )
        assert user["earn_user_id"]

    def test_referral_code_is_user_id(self, store):
        user = store.register("me@test.com", "SecurePass123!")
        code = store.referral_code(user["earn_user_id"])
        assert code == user["earn_user_id"]

    def test_multiple_referrals(self, store):
        referrer = store.register("top@test.com", "SecurePass123!")
        for i in range(5):
            store.register(
                f"friend{i}@test.com", "SecurePass123!",
                ref_code=referrer["earn_user_id"],
            )
        stats = store.referral_stats(referrer["earn_user_id"])
        assert stats["referral_count"] == 5

    def test_referral_api_endpoints(self, store):
        from flask import Flask
        app = Flask(__name__)
        app.config["TESTING"] = True

        from services.earn_account import register_earn_account_routes
        register_earn_account_routes(app, store)

        with app.test_client() as c:
            r = c.post(
                "/api/earn/register",
                json={"email": "referrer@api.com", "password": "SecurePass123!"},
            )
            assert r.status_code == 201
            uid = r.get_json()["earn_user_id"]

            r = c.post(
                "/api/earn/login",
                json={"email": "referrer@api.com", "password": "SecurePass123!"},
            )
            token = r.get_json()["access_token"]

            r = c.get(
                "/api/earn/referral/code",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 200
            data = r.get_json()
            assert data["ok"]
            assert data["ref_code"] == uid

            c.post(
                "/api/earn/register",
                json={
                    "email": "friend@api.com",
                    "password": "SecurePass456!",
                    "ref": uid,
                },
            )

            r = c.get(
                "/api/earn/referral/stats",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 200
            data = r.get_json()
            assert data["ok"]
            assert data["referral_count"] == 1
            assert len(data["referrals"]) == 1

    def test_non_wallet_l1_reward_is_two_percent_only_after_clearance(self, store, monkeypatch):
        inviter = store.register("l1@example.com", "SecurePass123!")
        player = store.register("player@example.com", "SecurePass123!", inviter["earn_user_id"])
        self._cpx_reward(store, player, "ref-l1-200", "200")
        assert Decimal(store.referral_stats(inviter["earn_user_id"])["cleared_rewards"]) == 0

        self._release(store, player["earn_user_id"], monkeypatch)
        stats = store.referral_stats(inviter["earn_user_id"])
        assert Decimal(stats["cleared_rewards"]) == Decimal("4.000000")
        assert Decimal(store.thc_balance(inviter["earn_user_id"])["available"]) == Decimal("4.000000")
        with store._tx() as con:
            row = con.execute(
                """SELECT rate_bps, loyalty_eligible, state FROM earn_referral_reward_allocations
                   WHERE referrer_id=?""", (inviter["earn_user_id"],),
            ).fetchone()
        assert dict(row) == {"rate_bps": 200, "loyalty_eligible": 0, "state": "confirmed"}

    def test_linked_wallet_l1_and_l2_rewards_snapshot_loyalty_rates(self, store, monkeypatch):
        root = store.register("root@example.com", "SecurePass123!")
        parent = store.register("parent@example.com", "SecurePass123!", root["earn_user_id"])
        player = store.register("child@example.com", "SecurePass123!", parent["earn_user_id"])
        # The wallet link is inserted here only to isolate policy evaluation;
        # real links are cryptographically proved by the wallet-link flow.
        with store._tx() as con:
            now = 1
            con.execute(
                "INSERT INTO earn_wallet_links VALUES (?,?,?,?)",
                ("THR" + "a" * 40, parent["earn_user_id"], "02" + "b" * 64, now),
            )
            con.execute(
                "INSERT INTO earn_wallet_links VALUES (?,?,?,?)",
                ("THR" + "c" * 40, root["earn_user_id"], "02" + "d" * 64, now),
            )
        self._cpx_reward(store, player, "ref-l2-100", "100")
        self._release(store, player["earn_user_id"], monkeypatch)

        assert Decimal(store.referral_stats(parent["earn_user_id"])["cleared_rewards"]) == Decimal("3.000000")
        assert Decimal(store.referral_stats(root["earn_user_id"])["cleared_rewards"]) == Decimal("2.000000")
        with store._tx() as con:
            rows = con.execute(
                """SELECT referrer_id, level, rate_bps, loyalty_eligible
                   FROM earn_referral_reward_allocations ORDER BY level""",
            ).fetchall()
        assert [tuple(row) for row in rows] == [
            (parent["earn_user_id"], 1, 300, 1),
            (root["earn_user_id"], 2, 200, 1),
        ]

    def test_provider_reversal_reverses_referral_credit_once(self, store, monkeypatch):
        inviter = store.register("reverse-inviter@example.com", "SecurePass123!")
        player = store.register("reverse-player@example.com", "SecurePass123!", inviter["earn_user_id"])
        self._cpx_reward(store, player, "ref-reverse-500", "500")
        self._release(store, player["earn_user_id"], monkeypatch)
        assert Decimal(store.thc_balance(inviter["earn_user_id"])["available"]) == Decimal("10.000000")

        store.record_cpx_receipt(
            trans_id="ref-reverse-500", cpx_ext_user_id=player["cpx_ext_user_id"],
            status=2, amount_local="500", payload={"status": "2"},
        )
        assert Decimal(store.thc_balance(inviter["earn_user_id"])["available"]) == Decimal("0")
        # Same provider reversal must be idempotent and cannot reverse twice.
        receipt, changed = store.record_cpx_receipt(
            trans_id="ref-reverse-500", cpx_ext_user_id=player["cpx_ext_user_id"],
            status=2, amount_local="500", payload={"status": "2"},
        )
        assert changed is False
        assert receipt["status"] == 2
        with store._tx() as con:
            row = con.execute(
                "SELECT state FROM earn_referral_reward_allocations WHERE referrer_id=?",
                (inviter["earn_user_id"],),
            ).fetchone()
        assert row["state"] == "reversed"
