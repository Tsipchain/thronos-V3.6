"""Verify a THR staking instruction before any wallet or pool mutation.

This module deliberately does not debit funds or consume a nonce.  The caller
must reserve the nonce and settle the wallet and stake receipts together.
"""

import hashlib
import json
from decimal import Decimal, InvalidOperation, ROUND_UP

from wallet_action_verify import verify_wallet_action_signature

SCALE = Decimal("0.000001")
FEE_BPS = 9
ALLOWED_TERMS = frozenset({"flex", "six_months", "one_year"})


class StakeAuthorizationError(ValueError):
    pass


def _amount(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount <= 0 or amount != amount.quantize(SCALE):
            raise StakeAuthorizationError("invalid_stake_amount")
        return amount
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise StakeAuthorizationError("invalid_stake_amount") from exc


def verify_thr_stake_authorization(
    *, intent, signature, public_key, payload, linked_wallet, pool_id, vault_address,
):
    """Return a canonical stake request only when the full signed quote matches.

    Nonce reservation, ledger settlement and receipt creation are separate
    mandatory steps.  This preflight cannot enable staking on its own.
    """
    if not isinstance(intent, dict) or not isinstance(payload, dict):
        raise StakeAuthorizationError("invalid_stake_intent")
    ok, error, _ = verify_wallet_action_signature(
        intent, signature, public_key, allowed_actions=frozenset({"earn_thr_stake"}),
    )
    if not ok:
        raise StakeAuthorizationError(error)
    if intent.get("action") != "earn_thr_stake" or intent.get("asset") != "THR":
        raise StakeAuthorizationError("wrong_stake_action")
    if str(intent.get("from_thr", "")).upper() != linked_wallet.upper():
        raise StakeAuthorizationError("wallet_link_mismatch")
    if str(intent.get("wallet_id", "")).upper() != linked_wallet.upper():
        raise StakeAuthorizationError("wallet_link_mismatch")
    if intent.get("chain") != "thronos":
        raise StakeAuthorizationError("wrong_stake_chain")
    if str(intent.get("recipient", "")).upper() != vault_address.upper():
        raise StakeAuthorizationError("pool_vault_mismatch")
    if payload.get("pool_id") != pool_id or payload.get("token") != "THR":
        raise StakeAuthorizationError("pool_mismatch")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    if hashlib.sha256(canonical.encode()).hexdigest() != intent.get("payload_hash"):
        raise StakeAuthorizationError("payload_hash_mismatch")
    amount = _amount(payload.get("amount"))
    term = payload.get("term")
    if not isinstance(term, str) or term not in ALLOWED_TERMS:
        raise StakeAuthorizationError("invalid_stake_term")
    if str(intent.get("amount")) != str(amount.quantize(SCALE)):
        raise StakeAuthorizationError("signed_amount_mismatch")
    fee = (amount * Decimal(FEE_BPS) / Decimal(10000)).quantize(SCALE, rounding=ROUND_UP)
    if payload.get("fee_bps") != FEE_BPS or str(payload.get("fee")) != str(fee):
        raise StakeAuthorizationError("signed_fee_mismatch")
    if not isinstance(payload.get("idempotency_key"), str) or not payload["idempotency_key"]:
        raise StakeAuthorizationError("missing_idempotency_key")
    return {
        "amount": str(amount.quantize(SCALE)), "fee": str(fee),
        "total_debit": str(amount + fee), "pool_id": pool_id,
        "wallet_address": linked_wallet, "nonce": str(intent["nonce"]),
        "idempotency_key": payload["idempotency_key"],
        "payload_hash": intent["payload_hash"],
        "term": term,
    }
