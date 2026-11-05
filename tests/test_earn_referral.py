"""Tests for the Earn referral system."""
import os
import pytest
import tempfile

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
