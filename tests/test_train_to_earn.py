"""Tests for Train-to-Earn service."""
import os
import tempfile
import time
import pytest
from services.train_to_earn import TrainToEarnStore, T2EError


@pytest.fixture()
def store(tmp_path):
    db_path = tmp_path / "t2e_test.db"
    return TrainToEarnStore(db_path=str(db_path))


@pytest.fixture()
def gym_with_key(store):
    gym, api_key = store.register_gym(
        name="Test Gym Athens",
        address="123 Syntagma",
        city="Athens",
        country="GR",
        checkin_method="qr",
    )
    return gym, api_key


class TestGymRegistration:
    def test_register_gym_returns_id_and_key(self, store):
        gym, api_key = store.register_gym(name="Fitness Club")
        assert gym["gym_id"].startswith("gym_")
        assert api_key.startswith("t2e_")
        assert gym["is_active"] == 1

    def test_register_gym_invalid_name(self, store):
        with pytest.raises(T2EError, match="invalid_gym_name"):
            store.register_gym(name="")

    def test_register_gym_invalid_checkin_method(self, store):
        with pytest.raises(T2EError, match="invalid_checkin_method"):
            store.register_gym(name="Gym", checkin_method="magic")

    def test_verify_gym_key(self, store, gym_with_key):
        gym, api_key = gym_with_key
        verified = store.verify_gym_key(api_key)
        assert verified is not None
        assert verified["gym_id"] == gym["gym_id"]

    def test_verify_gym_key_invalid(self, store):
        assert store.verify_gym_key("bad_key") is None

    def test_list_gyms(self, store, gym_with_key):
        gyms = store.list_gyms()
        assert len(gyms) == 1
        assert gyms[0]["name"] == "Test Gym Athens"


class TestMembership:
    def test_link_membership(self, store, gym_with_key):
        gym, _ = gym_with_key
        m = store.link_membership(
            earn_user_id="earn_test1",
            gym_id=gym["gym_id"],
            member_code="MEM001",
        )
        assert m["membership_id"].startswith("mem_")

    def test_link_membership_duplicate(self, store, gym_with_key):
        gym, _ = gym_with_key
        store.link_membership(
            earn_user_id="earn_test2", gym_id=gym["gym_id"],
            member_code="MEM002",
        )
        with pytest.raises(T2EError, match="membership_already_linked"):
            store.link_membership(
                earn_user_id="earn_test2", gym_id=gym["gym_id"],
                member_code="MEM003",
            )

    def test_link_membership_bad_gym(self, store):
        with pytest.raises(T2EError, match="gym_not_found"):
            store.link_membership(
                earn_user_id="earn_test3", gym_id="gym_nonexistent",
                member_code="MEM001",
            )

    def test_get_memberships(self, store, gym_with_key):
        gym, _ = gym_with_key
        store.link_membership(
            earn_user_id="earn_test4", gym_id=gym["gym_id"],
            member_code="MEM004",
        )
        memberships = store.get_memberships("earn_test4")
        assert len(memberships) == 1
        assert memberships[0]["gym_name"] == "Test Gym Athens"


class TestCheckin:
    def test_record_checkin(self, store, gym_with_key):
        gym, _ = gym_with_key
        store.link_membership(
            earn_user_id="earn_test5", gym_id=gym["gym_id"],
            member_code="MEM005",
        )
        result = store.record_checkin(
            earn_user_id="earn_test5", gym_id=gym["gym_id"],
        )
        assert result["activity_type"] == "checkin"
        assert result["activity_id"].startswith("act_")
        assert float(result["reward_thc"]) > 0

    def test_checkin_no_membership(self, store, gym_with_key):
        gym, _ = gym_with_key
        with pytest.raises(T2EError, match="no_active_membership"):
            store.record_checkin(
                earn_user_id="earn_nobody", gym_id=gym["gym_id"],
            )

    def test_daily_cap(self, store, gym_with_key):
        gym, _ = gym_with_key
        store.link_membership(
            earn_user_id="earn_capped", gym_id=gym["gym_id"],
            member_code="MEM_CAP",
        )
        for _ in range(3):
            store.record_checkin(
                earn_user_id="earn_capped", gym_id=gym["gym_id"],
            )
        with pytest.raises(T2EError, match="daily_cap_reached"):
            store.record_checkin(
                earn_user_id="earn_capped", gym_id=gym["gym_id"],
            )


class TestWorkout:
    def test_record_workout(self, store):
        result = store.record_workout(
            earn_user_id="earn_test6", duration_min=30,
        )
        assert result["activity_type"] == "workout"
        assert float(result["reward_thc"]) > 0

    def test_workout_too_short(self, store):
        with pytest.raises(T2EError, match="invalid_workout"):
            store.record_workout(earn_user_id="earn_test7", duration_min=5)

    def test_workout_60min_bonus(self, store):
        short = store.record_workout(
            earn_user_id="earn_test8", duration_min=30,
        )
        long = store.record_workout(
            earn_user_id="earn_test9", duration_min=60,
        )
        assert float(long["reward_thc"]) > float(short["reward_thc"])


class TestStats:
    def test_stats_empty(self, store):
        stats = store.get_stats("earn_new_user")
        assert stats["current_streak"] == 0
        assert stats["total_activities"] == 0

    def test_stats_after_workout(self, store):
        store.record_workout(
            earn_user_id="earn_test10", duration_min=30,
        )
        stats = store.get_stats("earn_test10")
        assert stats["total_activities"] == 1
        assert stats["current_streak"] == 1
        assert float(stats["total_thc_earned"]) > 0

    def test_history(self, store):
        store.record_workout(
            earn_user_id="earn_test11", duration_min=45,
            workout_type="cardio",
        )
        history = store.get_history("earn_test11")
        assert len(history) == 1
        assert history[0]["activity_type"] == "workout"


class TestTenantSubscriptionsAndOffers:
    def test_plan_catalog_is_explicit_and_separate_from_rewards(self):
        plans = TrainToEarnStore.plan_catalog()
        assert plans == [{
            "code": "gym_basic",
            "monthly_eur": "1.00",
            "includes_ad_package": True,
            "description": "Gym membership, tenant dashboard and Train2Earn offers",
        }]

    def test_provider_confirmed_subscription_is_idempotent(self, store, gym_with_key):
        gym, _ = gym_with_key
        start = int(time.time())
        first = store.reconcile_subscription(
            gym_id=gym["gym_id"], plan_code="gym_basic", provider="stripe",
            provider_ref="sub_provider_001", amount_eur="1.00",
            period_start=start, period_end=start + 30 * 86400,
        )
        second = store.reconcile_subscription(
            gym_id=gym["gym_id"], plan_code="gym_basic", provider="stripe",
            provider_ref="sub_provider_001", amount_eur="1.00",
            period_start=start, period_end=start + 30 * 86400,
        )
        assert first["subscription_id"] == second["subscription_id"]
        assert store.get_subscription(gym["gym_id"])["status"] == "active"

    def test_subscription_provider_reference_cannot_cross_tenant(self, store, gym_with_key):
        gym_a, _ = gym_with_key
        gym_b, _ = store.register_gym(name="Second Gym")
        start = int(time.time())
        store.reconcile_subscription(
            gym_id=gym_a["gym_id"], plan_code="gym_basic", provider="stripe",
            provider_ref="sub_shared", amount_eur="1.00",
            period_start=start, period_end=start + 30 * 86400,
        )
        with pytest.raises(T2EError, match="provider_reference_conflict"):
            store.reconcile_subscription(
                gym_id=gym_b["gym_id"], plan_code="gym_basic", provider="stripe",
                provider_ref="sub_shared", amount_eur="1.00",
                period_start=start, period_end=start + 30 * 86400,
            )

    def test_offer_catalog_is_tenant_scoped_and_does_not_credit_thc(self, store, gym_with_key):
        gym_a, _ = gym_with_key
        gym_b, _ = store.register_gym(name="Second Gym")
        offer = store.create_offer(
            gym_id=gym_a["gym_id"], offer_code="welcome", title="Welcome workout",
            description="Complete the introductory routine", status="active",
        )
        assert offer["offer_id"].startswith("offer_")
        assert len(store.list_offers(gym_a["gym_id"])) == 1
        assert store.list_offers(gym_b["gym_id"]) == []
        assert "reward_thc" not in offer

    def test_invalid_subscription_cannot_be_created_from_client_values(self, store, gym_with_key):
        gym, _ = gym_with_key
        start = int(time.time())
        with pytest.raises(T2EError, match="unknown_plan"):
            store.reconcile_subscription(
                gym_id=gym["gym_id"], plan_code="free_money", provider="browser",
                provider_ref="fake", amount_eur="999", period_start=start,
                period_end=start + 86400,
            )


class TestChallengesAndLeaderboard:
    def _challenge(self, store, gym_id, code="steps"):
        return store.create_challenge(
            gym_id=gym_id, challenge_code=code, title="First 10k steps",
            description="Complete a verified activity target", target_value="10",
            unit="steps", reward_t2e="2.50", status="active",
        )

    def test_challenge_enrollment_is_idempotent(self, store, gym_with_key):
        gym, _ = gym_with_key
        challenge = self._challenge(store, gym["gym_id"])
        first = store.enroll_challenge(
            earn_user_id="earn_athlete", challenge_id=challenge["challenge_id"],
        )
        second = store.enroll_challenge(
            earn_user_id="earn_athlete", challenge_id=challenge["challenge_id"],
        )
        assert first["progress_id"] == second["progress_id"]

    def test_progress_reaches_eligibility_without_crediting_thc(self, store, gym_with_key):
        gym, _ = gym_with_key
        challenge = self._challenge(store, gym["gym_id"])
        store.enroll_challenge(
            earn_user_id="earn_athlete", challenge_id=challenge["challenge_id"],
        )
        progress = store.record_challenge_progress(
            earn_user_id="earn_athlete", challenge_id=challenge["challenge_id"],
            value="12",
        )
        assert progress["status"] == "completed"
        assert progress["reward_status"] == "eligible"
        assert "thc" not in {key.lower() for key in progress}

    def test_completed_challenge_cannot_be_credited_twice(self, store, gym_with_key):
        gym, _ = gym_with_key
        challenge = self._challenge(store, gym["gym_id"])
        store.enroll_challenge(
            earn_user_id="earn_athlete", challenge_id=challenge["challenge_id"],
        )
        first = store.record_challenge_progress(
            earn_user_id="earn_athlete", challenge_id=challenge["challenge_id"], value="10",
        )
        second = store.record_challenge_progress(
            earn_user_id="earn_athlete", challenge_id=challenge["challenge_id"], value="10",
        )
        assert first["progress_id"] == second["progress_id"]
        assert second["current_value"] == "10"

    def test_leaderboard_is_tenant_scoped_and_pseudonymous(self, store, gym_with_key):
        gym_a, _ = gym_with_key
        gym_b, _ = store.register_gym(name="Second Gym")
        challenge_a = self._challenge(store, gym_a["gym_id"], code="a")
        challenge_b = self._challenge(store, gym_b["gym_id"], code="b")
        for user, challenge in (("earn_a", challenge_a), ("earn_b", challenge_b)):
            store.enroll_challenge(earn_user_id=user, challenge_id=challenge["challenge_id"])
            store.record_challenge_progress(
                earn_user_id=user, challenge_id=challenge["challenge_id"], value="10",
            )
        board = store.get_leaderboard(gym_a["gym_id"])
        assert len(board) == 1
        assert board[0]["display_ref"].startswith("athlete_")
        assert "earn_a" not in str(board[0])
        assert store.get_leaderboard(gym_b["gym_id"])[0]["display_ref"] != board[0]["display_ref"]
