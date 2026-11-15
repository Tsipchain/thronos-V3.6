import hashlib
import hmac
import json

import pytest

from services.earn_gym_eligibility_proof import GymProofError, verify_gym_eligibility

SECRET = "gym-test-export-key"
USER = "earn_user_test"


def signed_event(**changes):
    data = {
        "event_id": "gym_" + "a" * 32,
        "earn_user_ref": USER,
        "tenant_id": "gym_tenant_1",
        "challenge_id": "challenge_1",
        "reward_t2e": "5",
        "completed_at": 1700000000,
        "status": "eligible",
        "source": "gym_verified_challenge",
    }
    data.update(changes)
    signature = hmac.new(
        SECRET.encode(),
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode(),
        hashlib.sha256,
    ).hexdigest()
    return {**data, "signature": signature}


def test_valid_gym_receipt_is_eligibility_only_not_thc_credit():
    event = signed_event()
    result = verify_gym_eligibility(event, expected_earn_user_ref=USER, export_secret=SECRET)
    assert result["event_id"] == "gym_" + "a" * 32
    assert result["reward_t2e"] == "5"
    assert "signature" not in result
    assert "thc_amount" not in result
    assert "credit_status" not in result


@pytest.mark.parametrize("override", [
    {"status": "paid"}, {"source": "browser_workout"},
    {"earn_user_ref": "other_user"}, {"reward_t2e": "1.1234567"},
    {"reward_t2e": "NaN"}, {"reward_t2e": "-1"},
    {"event_id": "random_event"}, {"completed_at": 0},
    {"tenant_id": ""}, {"challenge_id": ""},
])
def test_signed_but_invalid_gym_receipts_are_rejected(override):
    with pytest.raises(GymProofError):
        verify_gym_eligibility(signed_event(**override), expected_earn_user_ref=USER, export_secret=SECRET)


def test_tampering_rejected_even_if_other_fields_are_valid():
    event = signed_event()
    event["reward_t2e"] = "99999"
    with pytest.raises(GymProofError, match="invalid_gym_signature"):
        verify_gym_eligibility(event, expected_earn_user_ref=USER, export_secret=SECRET)


def test_unknown_fields_and_missing_signature_fail_closed():
    event = signed_event()
    del event["signature"]
    with pytest.raises(GymProofError):
        verify_gym_eligibility(event, expected_earn_user_ref=USER, export_secret=SECRET)
    event = signed_event(extra="untrusted")
    with pytest.raises(GymProofError):
        verify_gym_eligibility(event, expected_earn_user_ref=USER, export_secret=SECRET)


def test_bridge_secret_is_mandatory_and_account_is_bound():
    with pytest.raises(GymProofError):
        verify_gym_eligibility(signed_event(), expected_earn_user_ref=USER, export_secret="")
    with pytest.raises(GymProofError, match="gym_receipt_wrong_earn_account"):
        verify_gym_eligibility(signed_event(), expected_earn_user_ref="other_user", export_secret=SECRET)
