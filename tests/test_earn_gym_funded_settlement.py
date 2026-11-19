import hashlib
import hmac
import inspect
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from services.earn_gym_eligibility_inbox import GymEligibilityInbox
from services.earn_gym_funded_settlement import (
    GymFundedSettlementPlanner,
    GymSettlementError,
    VerifiedGymFundingReservation,
    VerifiedGymRewardQuote,
)

SECRET = "gym-export-secret-that-is-at-least-32-bytes"
EVENT = "gym_" + "a" * 32
USER = "earn_user_1"
NOW = 1_800_000_100


def signed_receipt():
    payload = {
        "event_id": EVENT,
        "earn_user_ref": USER,
        "tenant_id": "gym_tenant_1",
        "challenge_id": "challenge_1",
        "reward_t2e": "5",
        "completed_at": 1_800_000_000,
        "status": "eligible",
        "source": "gym_verified_challenge",
    }
    signature = hmac.new(
        SECRET.encode(),
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
        hashlib.sha256,
    ).hexdigest()
    return {**payload, "signature": signature}


class QuoteVerifier:
    def __init__(self, **changes):
        self.changes = changes

    def verify(self, eligibility, candidate):
        assert candidate == {"opaque": "quote"}
        values = {
            "quote_id": "quote_1",
            "event_id": EVENT,
            "earn_user_ref": USER,
            "tenant_id": "gym_tenant_1",
            "source_asset": "T2E_ELIGIBILITY_ONLY",
            "source_amount": "5",
            "reward_asset": "THC",
            "reward_amount": "1.250000",
            "pricing_version": "gym-reward-v1",
            "authority_ref": "quote-authority-1",
            "expires_at": NOW + 300,
        }
        values.update(self.changes)
        return VerifiedGymRewardQuote(**values)


class FundingVerifier:
    def __init__(self, **changes):
        self.changes = changes

    def verify(self, eligibility, quote, candidate):
        assert candidate == {"opaque": "funding"}
        values = {
            "reservation_id": "reserve_1",
            "event_id": EVENT,
            "earn_user_ref": USER,
            "tenant_id": "gym_tenant_1",
            "asset": "THC",
            "reserved_amount": "1.250000",
            "purpose": "gym_reward_settlement",
            "authority_ref": "reservation-authority-1",
            "expires_at": NOW + 600,
        }
        values.update(self.changes)
        return VerifiedGymFundingReservation(**values)


@pytest.fixture
def setup(tmp_path):
    inbox = GymEligibilityInbox(tmp_path / "inbox.db", SECRET)
    inbox.ingest(signed_receipt(), expected_earn_user_ref=USER)

    def make(quote=None, funding=None, suffix=""):
        return GymFundedSettlementPlanner(
            tmp_path / f"plans{suffix}.db", inbox,
            quote or QuoteVerifier(), funding or FundingVerifier(),
        )

    return inbox, make


def prepare(planner, **changes):
    values = {
        "expected_earn_user_ref": USER,
        "quote_candidate": {"opaque": "quote"},
        "funding_candidate": {"opaque": "funding"},
        "now": NOW,
    }
    values.update(changes)
    return planner.prepare(EVENT, **values)


def test_verified_quote_and_funded_reservation_prepare_review_only(setup):
    _, make = setup
    result = prepare(make())
    assert result["state"] == "operator_review_required"
    assert result["source_asset"] == "T2E_ELIGIBILITY_ONLY"
    assert result["source_amount"] == "5"
    assert result["reward_asset"] == "THC"
    assert result["reward_amount"] == "1.250000"
    assert result["credit_authorized"] is False
    assert result["payout_enabled"] is False


def test_retry_and_restart_are_idempotent(setup):
    inbox, make = setup
    planner = make()
    assert prepare(planner)["idempotent"] is False
    reopened = GymFundedSettlementPlanner(
        planner._db_path, inbox, QuoteVerifier(), FundingVerifier(),
    )
    assert prepare(reopened)["idempotent"] is True
    status = reopened.recovery_status()
    assert status["operator_review_required"] == 1
    assert status["credit_authorized"] is False


def test_concurrent_duplicate_preparation_stores_one_plan(setup):
    _, make = setup
    planner = make()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: prepare(planner), range(8)))
    assert sum(not item["idempotent"] for item in results) == 1
    assert planner.recovery_status()["operator_review_required"] == 1


def test_missing_eligibility_and_wrong_account_fail_closed(setup):
    _, make = setup
    planner = make()
    with pytest.raises(GymSettlementError, match="gym_eligibility_not_found"):
        planner.prepare(
            "gym_missing", expected_earn_user_ref=USER,
            quote_candidate={}, funding_candidate={}, now=NOW,
        )
    with pytest.raises(GymSettlementError, match="wrong_earn_account"):
        prepare(planner, expected_earn_user_ref="earn_other")


@pytest.mark.parametrize("change,error", [
    ({"event_id": "gym_other"}, "gym_quote_binding_mismatch"),
    ({"earn_user_ref": "earn_other"}, "gym_quote_binding_mismatch"),
    ({"tenant_id": "other_tenant"}, "gym_quote_binding_mismatch"),
    ({"source_amount": "6"}, "gym_quote_binding_mismatch"),
    ({"reward_asset": "THR"}, "gym_quote_binding_mismatch"),
    ({"expires_at": NOW}, "gym_reward_quote_expired"),
    ({"reward_amount": "1.0000001"}, "invalid_gym_reward_amount_precision"),
])
def test_quote_binding_and_precision_fail_closed(setup, change, error):
    _, make = setup
    with pytest.raises(GymSettlementError, match=error):
        prepare(make(quote=QuoteVerifier(**change)))


@pytest.mark.parametrize("change,error", [
    ({"event_id": "gym_other"}, "gym_funding_binding_mismatch"),
    ({"earn_user_ref": "earn_other"}, "gym_funding_binding_mismatch"),
    ({"tenant_id": "other_tenant"}, "gym_funding_binding_mismatch"),
    ({"asset": "THR"}, "gym_funding_binding_mismatch"),
    ({"purpose": "general"}, "gym_funding_binding_mismatch"),
    ({"reserved_amount": "1.249999"}, "insufficient_gym_funding_reservation"),
    ({"expires_at": NOW}, "gym_funding_reservation_expired"),
])
def test_funding_binding_and_sufficiency_fail_closed(setup, change, error):
    _, make = setup
    with pytest.raises(GymSettlementError, match=error):
        prepare(make(funding=FundingVerifier(**change)))


def test_verifier_failure_is_unavailable_not_implicitly_trusted(setup):
    _, make = setup

    class Broken:
        def verify(self, *args):
            raise RuntimeError("authority offline")

    with pytest.raises(GymSettlementError, match="gym_settlement_evidence_unavailable"):
        prepare(make(quote=Broken()))


def test_changed_retry_conflicts_without_replacing_plan(setup):
    inbox, make = setup
    planner = make()
    prepare(planner)
    changed = GymFundedSettlementPlanner(
        planner._db_path, inbox,
        QuoteVerifier(reward_amount="1.000000"),
        FundingVerifier(reserved_amount="1.000000"),
    )
    with pytest.raises(GymSettlementError, match="gym_settlement_plan_conflict"):
        prepare(changed)
    assert planner.recovery_status()["operator_review_required"] == 1


def test_quote_or_reservation_cannot_be_reused_for_another_event(tmp_path):
    inbox = GymEligibilityInbox(tmp_path / "inbox.db", SECRET)
    inbox.ingest(signed_receipt(), expected_earn_user_ref=USER)
    planner = GymFundedSettlementPlanner(
        tmp_path / "plans.db", inbox, QuoteVerifier(), FundingVerifier(),
    )
    prepare(planner)
    with planner._tx() as connection:
        quote_count = connection.execute(
            "SELECT COUNT(*) FROM earn_gym_settlement_plans WHERE quote_id='quote_1'"
        ).fetchone()[0]
        reserve_count = connection.execute(
            "SELECT COUNT(*) FROM earn_gym_settlement_plans WHERE reservation_id='reserve_1'"
        ).fetchone()[0]
    assert quote_count == reserve_count == 1


def test_module_cannot_credit_convert_pay_or_broadcast():
    import services.earn_gym_funded_settlement as module

    source = inspect.getsource(module)
    assert "record_thc_credit" not in source
    assert "from services.earn_account" not in source
    assert "import services.earn_account" not in source
    assert "broadcast_transaction" not in source
    assert "def credit" not in source
    assert ".credit(" not in source
