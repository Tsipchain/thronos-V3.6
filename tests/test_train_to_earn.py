"""Tests for Train-to-Earn service."""
import os
import tempfile
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
