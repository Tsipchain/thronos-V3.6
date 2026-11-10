"""Signed, atomic internal THC wallet-unlock purchase invariants.

No HTTP route or Wallet V1 issuance is enabled by these store-level tests.
"""
import hashlib
import json
from decimal import Decimal

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils

from services.earn_account import EarnAccountStore, EarnError
from wallet_v1_address_derivation import derive_thronos_address


@pytest.fixture
def store(tmp_path):
    return EarnAccountStore(str(tmp_path / "earn.db"), "wallet-unlock-test-key")


@pytest.fixture
def uid(store):
    return store.register("buyer@example.com", "password123")["earn_user_id"]


@pytest.fixture
def wallet():
    private = ec.generate_private_key(ec.SECP256K1())
    public = private.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint,
    ).hex()
    return private, public, derive_thronos_address(public)


def _fund(store, uid, amount="10020"):
    entry, _ = store.record_thc_credit(uid, "test_reward", "reward-1", amount)
    store.transition_thc(entry["entry_id"], "confirmed")


def _signed(challenge, uid, wallet):
    private, public, address = wallet
    keys = ["action", "challenge_id", "expires_at", "nonce", "wallet_address"]
    for optional in ("approval", "amount_thc", "treasury_account"):
        if optional in challenge:
            keys.append(optional)
    payload = {key: str(challenge[key]) for key in keys}
    message = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    der = private.sign(
        hashlib.sha256(message).digest(), ec.ECDSA(utils.Prehashed(hashes.SHA256())),
    )
    r, s = utils.decode_dss_signature(der)
    return dict(challenge_id=challenge["challenge_id"], earn_user_id=uid,
                wallet_address=address, public_key=public,
                signature=f"{r:064x}{s:064x}")


def test_pending_rewards_cannot_start_purchase(store, uid, wallet):
    store.record_thc_credit(uid, "test_reward", "pending-1", "20000")
    assert store.paid_wallet_unlock_quote(uid)["eligible"] is False
    with pytest.raises(EarnError, match="wallet_unlock_not_eligible"):
        store.paid_wallet_unlock_challenge(uid, wallet[2])


def test_atomic_thc_spend_and_treasury_receipt(store, uid, wallet):
    _fund(store, uid)
    challenge = store.paid_wallet_unlock_challenge(uid, wallet[2])
    assert challenge["amount_thc"] == "10000.000000"
    assert challenge["treasury_account"] == "thronos_earn_treasury"
    receipt = store.complete_paid_wallet_unlock(**_signed(challenge, uid, wallet))
    assert receipt["amount_thc"] == "10000.000000"
    assert store.wallet_link_for_user(uid)["wallet_address"] == wallet[2]
    balance = store.thc_balance(uid)
    assert Decimal(balance["available"]) == Decimal("20")
    assert Decimal(balance["total_earned"]) == Decimal("10020")
    assert Decimal(balance["wallet_unlock_spent"]) == Decimal("10000")
    assert store.loyalty_status(uid)["vip"] is True
    with store._tx() as con:
        treasury = con.execute(
            "SELECT * FROM earn_treasury_thc_credits WHERE purchase_id=?",
            (receipt["purchase_id"],),
        ).fetchone()
        assert treasury["amount_thc"] == receipt["amount_thc"]
        assert treasury["treasury_ref"] == receipt["treasury_ref"]


def test_signed_replay_is_idempotent_and_second_purchase_rejected(store, uid, wallet):
    _fund(store, uid, "21000")
    first_challenge = store.paid_wallet_unlock_challenge(uid, wallet[2])
    second_challenge = store.paid_wallet_unlock_challenge(uid, wallet[2])
    args = _signed(first_challenge, uid, wallet)
    first = store.complete_paid_wallet_unlock(**args)
    assert store.complete_paid_wallet_unlock(**args)["purchase_id"] == first["purchase_id"]
    assert Decimal(store.thc_balance(uid)["available"]) == Decimal("11000")
    with pytest.raises(EarnError, match="wallet_unlock_already_purchased"):
        store.complete_paid_wallet_unlock(**_signed(second_challenge, uid, wallet))
    with store._tx() as con:
        assert con.execute("SELECT COUNT(*) FROM earn_treasury_thc_credits").fetchone()[0] == 1


def test_other_user_wallet_or_link_challenge_cannot_pay(store, uid, wallet):
    _fund(store, uid)
    other_uid = store.register("other@example.com", "password456")["earn_user_id"]
    challenge = store.paid_wallet_unlock_challenge(uid, wallet[2])
    args = _signed(challenge, uid, wallet)
    for forged in (
        {**args, "earn_user_id": other_uid},
        {**args, "wallet_address": "THR" + "B" * 40},
    ):
        with pytest.raises(EarnError, match="invalid_or_expired_wallet_challenge"):
            store.complete_paid_wallet_unlock(**forged)
    link_challenge = store.wallet_link_challenge(uid, wallet[2])
    with pytest.raises(EarnError, match="invalid_or_expired_wallet_challenge"):
        store.complete_paid_wallet_unlock(**_signed(link_challenge, uid, wallet))
    with pytest.raises(EarnError, match="invalid_wallet_proof"):
        store.complete_paid_wallet_unlock(**{**args, "signature": "0" * 128})
    assert store.wallet_link_for_user(uid) is None


def test_stake_after_quote_rejects_without_charge(store, uid, wallet):
    _fund(store, uid, "10000")
    challenge = store.paid_wallet_unlock_challenge(uid, wallet[2])
    pool = next(p for p in store.staking_pools() if p["token"] == "THC")
    store.create_stake(uid, pool["pool_id"], pool["min_stake"])
    with pytest.raises(EarnError, match="insufficient_thc_balance"):
        store.complete_paid_wallet_unlock(**_signed(challenge, uid, wallet))
    assert store.wallet_link_for_user(uid) is None
    with store._tx() as con:
        assert con.execute("SELECT COUNT(*) FROM earn_treasury_thc_credits").fetchone()[0] == 0


def test_existing_link_does_not_pay_to_get_loyalty(store, uid, wallet):
    _fund(store, uid)
    link_challenge = store.wallet_link_challenge(uid, wallet[2])
    store.complete_wallet_link(
        challenge_id=link_challenge["challenge_id"], earn_user_id=uid,
        wallet_address=wallet[2], public_key=wallet[1],
    )
    assert store.paid_wallet_unlock_quote(uid)["eligible"] is False
    assert store.loyalty_status(uid)["vip"] is True
    assert store.thc_balance(uid)["wallet_unlock_spent"] == "0.000000"


def test_treasury_write_failure_rolls_back_spend_and_link(store, uid, wallet):
    _fund(store, uid)
    challenge = store.paid_wallet_unlock_challenge(uid, wallet[2])
    with store._tx() as con:
        con.execute("""CREATE TRIGGER reject_unlock_treasury
            BEFORE INSERT ON earn_treasury_thc_credits
            BEGIN SELECT RAISE(ABORT, 'treasury unavailable'); END""")
    with pytest.raises(Exception, match="treasury unavailable"):
        store.complete_paid_wallet_unlock(**_signed(challenge, uid, wallet))
    assert store.wallet_link_for_user(uid) is None
    assert Decimal(store.thc_balance(uid)["available"]) == Decimal("10020")
    with store._tx() as con:
        assert con.execute("SELECT COUNT(*) FROM earn_wallet_unlock_purchases").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM earn_treasury_thc_credits").fetchone()[0] == 0
