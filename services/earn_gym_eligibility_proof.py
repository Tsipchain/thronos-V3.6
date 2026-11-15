"""Pure verification of Train2Earn gym eligibility receipts; zero Earn ledger writes.

A gym completion does not imply funded THC, THR, BTC, or monetary payout.
The Gym exporter signs canonical JSON with T2E_EARN_EXPORT_SECRET; the
independent Earn settlement coordinator must approve any later conversion.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from decimal import Decimal
from typing import Any


class GymProofError(ValueError):
    pass


_RECEIPT_FIELDS = frozenset({
    "event_id", "earn_user_ref", "tenant_id", "challenge_id", "reward_t2e",
    "completed_at", "status", "source",
})
_EVENT_ID = re.compile(r"^gym_[a-f0-9]{32}$")
_T2E_UNITS = re.compile(r"^\d+(?:\.\d{1,6})?$")


def verify_gym_eligibility(
    receipt: dict[str, Any],
    *,
    expected_earn_user_ref: str,
    export_secret: str,
) -> dict[str, Any]:
    """Read-only receipt verification. Does not authorize Earn reward credits."""
    if not export_secret or not expected_earn_user_ref:
        raise GymProofError("gym_bridge_not_configured")
    if not isinstance(receipt, dict):
        raise GymProofError("invalid_gym_receipt")
    signature = receipt.get("signature")
    payload = {key: value for key, value in receipt.items() if key != "signature"}
    if not isinstance(signature, str) or not re.fullmatch(r"[0-9a-f]{64}", signature):
        raise GymProofError("invalid_gym_signature")
    if set(payload) != _RECEIPT_FIELDS:
        raise GymProofError("invalid_gym_receipt_fields")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    expected_signature = hmac.new(
        export_secret.encode(), canonical.encode(), hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise GymProofError("invalid_gym_signature")
    if payload["earn_user_ref"] != expected_earn_user_ref:
        raise GymProofError("gym_receipt_wrong_earn_account")
    if payload["status"] != "eligible" or payload["source"] != "gym_verified_challenge":
        raise GymProofError("gym_receipt_not_eligible")
    if not isinstance(payload["event_id"], str) or not _EVENT_ID.fullmatch(payload["event_id"]):
        raise GymProofError("invalid_gym_event_id")
    if not all(isinstance(payload[key], str) and payload[key].strip()
               for key in ("tenant_id", "challenge_id")):
        raise GymProofError("invalid_gym_event_scope")
    amount = payload["reward_t2e"]
    if not isinstance(amount, str) or not _T2E_UNITS.fullmatch(amount):
        raise GymProofError("invalid_gym_reward_units")
    if Decimal(amount) < 0:
        raise GymProofError("invalid_gym_reward_units")
    completed = payload["completed_at"]
    if isinstance(completed, bool) or not isinstance(completed, int) or completed <= 0:
        raise GymProofError("invalid_gym_completed_at")
    # The caller may store the verified T2E eligibility event by stable event_id,
    # but must never infer a spendable THC amount or mark a payout from this data.
    return dict(payload)
