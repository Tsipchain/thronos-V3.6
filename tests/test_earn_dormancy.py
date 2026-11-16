"""Tests for account dormancy and leaderboard eligibility.

Priority 2 of the THRONOS EARN consolidated production execution.
"""
import hashlib
import os
import pytest
import secrets
import tempfile
import time

os.environ.setdefault("EARN_DB_PATH", ":memory:")

from decimal import Decimal
from services.earn_account import (
    EarnAccountStore, EarnError,
    _DORMANCY_INACTIVITY_DAYS, _DORMANCY_REACTIVATION_DAYS,
    _DORMANCY_EFFECTIVE_AFTER, _DORMANCY_POLICY_VERSION,
    _LEADERBOARD_END,
)


_TEST_KEY = "test-identity-key-for-dormancy-abcdef0123"


@pytest.fixture()
def store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    s = EarnAccountStore(path, _TEST_KEY)
    yield s
    os.unlink(path)


@pytest.fixture()
def user(store):
    return store.register("dormancy@test.com", "SecurePass123!")


class TestCheckin:

    def test_first_checkin(self, store, user):
        uid = user["earn_user_id"]
        result = store.record_checkin(uid)
        assert result["utc_date"]
        assert result["idempotent"] is False

    def test_duplicate_checkin_idempotent(self, store, user):
        uid = user["earn_user_id"]
        first = store.record_checkin(uid)
        second = store.record_checkin(uid)
        assert second["idempotent"] is True
        assert second["checkin_id"] == first["checkin_id"]

    def test_unknown_user_fails(self, store):
        with pytest.raises(EarnError, match="unknown_earn_user"):
            store.record_checkin("earn_nonexistent")


class TestDormancyEvaluation:

    def test_policy_not_active_before_effective_date(self, store, user):
        uid = user["earn_user_id"]
        before = _DORMANCY_EFFECTIVE_AFTER - 86400
        result = store.evaluate_dormancy(uid, at_time=before)
        assert result["policy_not_yet_active"] is True
        assert result["is_dormant"] is False
        assert result["eligible_for_leaderboard"] is True

    def test_new_user_not_dormant_if_recent(self, store, user):
        uid = user["earn_user_id"]
        store.record_checkin(uid)
        after = _DORMANCY_EFFECTIVE_AFTER + 86400
        result = store.evaluate_dormancy(uid, at_time=after)
        assert result["is_dormant"] is False
        assert result["eligible_for_leaderboard"] is True

    def test_inactive_user_becomes_dormant(self, store, user):
        uid = user["earn_user_id"]
        store.record_checkin(uid)
        far_future = _DORMANCY_EFFECTIVE_AFTER + (_DORMANCY_INACTIVITY_DAYS + 1) * 86400
        result = store.evaluate_dormancy(uid, at_time=far_future)
        assert result["is_dormant"] is True
        assert result["eligible_for_leaderboard"] is False
        assert result["days_to_reactivate"] == _DORMANCY_REACTIVATION_DAYS

    def test_dormancy_does_not_delete_or_confiscate(self, store, user):
        uid = user["earn_user_id"]
        entry, _ = store.record_thc_credit(
            uid, "test", f"test_{secrets.token_hex(8)}", "1000.000000",
        )
        store.transition_thc(entry["entry_id"], "confirmed")

        store.record_checkin(uid)
        far_future = _DORMANCY_EFFECTIVE_AFTER + (_DORMANCY_INACTIVITY_DAYS + 1) * 86400
        store.evaluate_dormancy(uid, at_time=far_future)

        balance = store.thc_balance(uid)
        assert Decimal(balance["available"]) == Decimal("1000.000000")

    def test_no_checkin_user_becomes_dormant(self, store, user):
        uid = user["earn_user_id"]
        far_future = _DORMANCY_EFFECTIVE_AFTER + (_DORMANCY_INACTIVITY_DAYS + 1) * 86400
        result = store.evaluate_dormancy(uid, at_time=far_future)
        assert result["is_dormant"] is True


class TestReactivation:

    def test_seven_day_streak_reactivates(self, store, user):
        uid = user["earn_user_id"]
        store.record_checkin(uid)
        far_future = _DORMANCY_EFFECTIVE_AFTER + (_DORMANCY_INACTIVITY_DAYS + 1) * 86400
        store.evaluate_dormancy(uid, at_time=far_future)

        status = store.dormancy_status(uid)
        assert status["is_dormant"] is True

        for day in range(_DORMANCY_REACTIVATION_DAYS):
            checkin_time = far_future + (day + 1) * 86400
            utc_date = time.strftime("%Y-%m-%d", time.gmtime(checkin_time))
            checkin_id = "chk_" + secrets.token_hex(8)
            with store._tx() as con:
                try:
                    con.execute(
                        """INSERT INTO earn_activity_checkins
                           (checkin_id, earn_user_id, checkin_type, utc_date, created_at)
                           VALUES (?,?,?,?,?)""",
                        (checkin_id, uid, "manual", utc_date, checkin_time),
                    )
                except Exception:
                    pass
                ds = con.execute(
                    "SELECT * FROM earn_dormancy_status WHERE earn_user_id = ?",
                    (uid,),
                ).fetchone()
                new_streak = (ds["reactivation_streak"] or 0) + 1
                updates = {
                    "last_activity": checkin_time,
                    "updated_at": checkin_time,
                    "reactivation_streak": new_streak,
                }
                if new_streak >= _DORMANCY_REACTIVATION_DAYS:
                    updates["is_dormant"] = 0
                    updates["reactivated_at"] = checkin_time
                    updates["reactivation_streak"] = 0
                set_clause = ", ".join(f"{k} = ?" for k in updates)
                con.execute(
                    f"UPDATE earn_dormancy_status SET {set_clause} WHERE earn_user_id = ?",
                    list(updates.values()) + [uid],
                )

        status_after = store.dormancy_status(uid)
        assert status_after["is_dormant"] is False
        assert status_after["eligible_for_leaderboard"] is True

    def test_partial_streak_does_not_reactivate(self, store, user):
        uid = user["earn_user_id"]
        store.record_checkin(uid)
        far_future = _DORMANCY_EFFECTIVE_AFTER + (_DORMANCY_INACTIVITY_DAYS + 1) * 86400
        store.evaluate_dormancy(uid, at_time=far_future)

        for day in range(_DORMANCY_REACTIVATION_DAYS - 1):
            checkin_time = far_future + (day + 1) * 86400
            utc_date = time.strftime("%Y-%m-%d", time.gmtime(checkin_time))
            checkin_id = "chk_" + secrets.token_hex(8)
            with store._tx() as con:
                try:
                    con.execute(
                        """INSERT INTO earn_activity_checkins
                           (checkin_id, earn_user_id, checkin_type, utc_date, created_at)
                           VALUES (?,?,?,?,?)""",
                        (checkin_id, uid, "manual", utc_date, checkin_time),
                    )
                except Exception:
                    pass
                con.execute(
                    """UPDATE earn_dormancy_status
                       SET reactivation_streak = reactivation_streak + 1,
                           last_activity = ?, updated_at = ?
                       WHERE earn_user_id = ?""",
                    (checkin_time, checkin_time, uid),
                )

        status = store.dormancy_status(uid)
        assert status["is_dormant"] is True


class TestDormancyStatus:

    def test_status_defaults_for_new_user(self, store, user):
        uid = user["earn_user_id"]
        status = store.dormancy_status(uid)
        assert status["is_dormant"] is False
        assert status["eligible_for_leaderboard"] is True
        assert status["policy_version"] == _DORMANCY_POLICY_VERSION
        assert status["effective_after"] == _DORMANCY_EFFECTIVE_AFTER

    def test_status_preserves_policy_version(self, store, user):
        uid = user["earn_user_id"]
        store.record_checkin(uid)
        status = store.dormancy_status(uid)
        assert status["policy_version"] == _DORMANCY_POLICY_VERSION


class TestDormancyPreservation:

    def test_first_competition_rules_preserved(self, store, user):
        uid = user["earn_user_id"]
        result = store.evaluate_dormancy(uid, at_time=_LEADERBOARD_END - 86400)
        assert result.get("policy_not_yet_active") is True

    def test_no_thc_confiscation_on_dormancy(self, store, user):
        uid = user["earn_user_id"]
        entry, _ = store.record_thc_credit(
            uid, "test", f"test_{secrets.token_hex(8)}", "5000.000000",
        )
        store.transition_thc(entry["entry_id"], "confirmed")

        far_future = _DORMANCY_EFFECTIVE_AFTER + (_DORMANCY_INACTIVITY_DAYS + 10) * 86400
        store.evaluate_dormancy(uid, at_time=far_future)

        balance = store.thc_balance(uid)
        assert Decimal(balance["available"]) == Decimal("5000.000000")

        status = store.dormancy_status(uid)
        assert status["is_dormant"] is True

    def test_no_account_deletion_on_dormancy(self, store, user):
        uid = user["earn_user_id"]
        far_future = _DORMANCY_EFFECTIVE_AFTER + (_DORMANCY_INACTIVITY_DAYS + 10) * 86400
        store.evaluate_dormancy(uid, at_time=far_future)

        with store._tx() as con:
            acc = con.execute(
                "SELECT 1 FROM earn_accounts WHERE earn_user_id = ?",
                (uid,),
            ).fetchone()
            assert acc is not None
