"""THR stake preflight proves a signer accepted the exact pool and fee."""

import hashlib
import json
import time

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from services.earn_thr_stake_authorization import (
    StakeAuthorizationError, verify_thr_stake_authorization,
)
from wallet_action_verify import canonical_wallet_action_intent, verify_wallet_action_signature
from services.earn_account import EarnAccountStore, EarnError


@pytest.fixture
def signed_stake():
    import wallet_v1_production_final as wallet

    key = ec.generate_private_key(ec.SECP256K1())
    pub = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint,
    ).hex()
    address = wallet.derive_thronos_address(pub).upper()
    vault = "THR" + "A" * 40
    payload = {
        "pool_id": "pool_thr_staking", "token": "THR", "amount": "10.000000",
        "term": "flex",
        "fee": "0.009000", "fee_bps": 9, "idempotency_key": "request-1",
    }
    intent = {
        "type": "thronos_wallet_action", "version": "1", "action": "earn_thr_stake",
        "wallet_id": address, "from_thr": address, "recipient": vault,
        "chain": "thronos", "asset": "THR", "amount": "10.000000",
        "nonce": "random-nonce", "created_at": str(int(time.time())),
    }

    def sign(body):
        intent["payload_hash"] = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode(),
        ).hexdigest()
        sig = key.sign(canonical_wallet_action_intent(intent).encode(), ec.ECDSA(hashes.SHA256())).hex()
        return dict(intent), sig

    return address, vault, pub, payload, sign


def test_signed_pool_and_fee(signed_stake):
    address, vault, pub, payload, sign = signed_stake
    intent, sig = sign(payload)
    result = verify_thr_stake_authorization(
        intent=intent, signature=sig, public_key=pub, payload=payload,
        linked_wallet=address, pool_id=payload["pool_id"], vault_address=vault,
    )
    assert result["fee"] == "0.009000"
    assert result["total_debit"] == "10.009000"
    assert result["term"] == "flex"


@pytest.mark.parametrize("term", ["flex", "six_months", "one_year"])
def test_all_signed_lock_terms_are_preserved(signed_stake, term):
    address, vault, pub, payload, sign = signed_stake
    payload = {**payload, "term": term}
    intent, sig = sign(payload)
    result = verify_thr_stake_authorization(
        intent=intent, signature=sig, public_key=pub, payload=payload,
        linked_wallet=address, pool_id=payload["pool_id"], vault_address=vault,
    )
    assert result["term"] == term


def test_signed_term_cannot_be_switched_or_omitted(signed_stake):
    address, vault, pub, payload, sign = signed_stake
    intent, sig = sign(payload)
    with pytest.raises(StakeAuthorizationError, match="payload_hash_mismatch"):
        verify_thr_stake_authorization(
            intent=intent, signature=sig, public_key=pub,
            payload={**payload, "term": "one_year"}, linked_wallet=address,
            pool_id=payload["pool_id"], vault_address=vault,
        )
    for bad in (None, "", "two_years"):
        changed = {**payload}
        if bad is None:
            del changed["term"]
        else:
            changed["term"] = bad
        signed, proof = sign(changed)
        with pytest.raises(StakeAuthorizationError, match="invalid_stake_term"):
            verify_thr_stake_authorization(
                intent=signed, signature=proof, public_key=pub,
                payload=changed, linked_wallet=address,
                pool_id=payload["pool_id"], vault_address=vault,
            )


def test_reserved_signed_action_is_idempotent_and_replay_safe(tmp_path, signed_stake):
    address, vault, pub, payload, sign = signed_stake
    store = EarnAccountStore(str(tmp_path / "earn.db"), "thr-reservation-test-key")
    user = store.register("stake@example.com", "password123")
    uid = user["earn_user_id"]
    with store._tx() as con:
        con.execute(
            "INSERT INTO earn_wallet_links(wallet_address, earn_user_id, public_key, linked_at) VALUES (?,?,?,?)",
            (address, uid, pub, int(time.time())),
        )
    intent, sig = sign(payload)
    verified = verify_thr_stake_authorization(
        intent=intent, signature=sig, public_key=pub, payload=payload,
        linked_wallet=address, pool_id=payload["pool_id"], vault_address=vault,
    )
    first = store.reserve_thr_stake_authorization(uid, verified)
    assert first["status"] == "reserved"
    assert store.reserve_thr_stake_authorization(uid, verified) == first
    with store._tx() as con:
        assert con.execute("SELECT COUNT(*) FROM earn_thr_stake_reservations").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM earn_staking_positions").fetchone()[0] == 0
    with pytest.raises(EarnError, match="stake_idempotency_conflict"):
        store.reserve_thr_stake_authorization(uid, {**verified, "nonce": "different"})
    with pytest.raises(EarnError, match="nonce_reused"):
        store.reserve_thr_stake_authorization(uid, {**verified, "idempotency_key": "another"})
    with pytest.raises(EarnError, match="wallet_link_mismatch"):
        other = store.register("other@example.com", "password123")
        store.reserve_thr_stake_authorization(other["earn_user_id"], verified)
    with pytest.raises(EarnError, match="intent_expired"):
        store.reserve_thr_stake_authorization(uid, {**verified, "created_at": 1})


def test_stake_action_is_rejected_by_generic_wallet_verifier(signed_stake):
    _, _, pub, payload, sign = signed_stake
    intent, sig = sign(payload)
    ok, error, _ = verify_wallet_action_signature(intent, sig, pub)
    assert not ok and error == "invalid_action"


@pytest.mark.parametrize("field,value,error", [
    ("fee", "0.000000", "payload_hash_mismatch"),
    ("pool_id", "other", "pool_mismatch"),
    ("amount", "11.000000", "payload_hash_mismatch"),
])
def test_payload_tampering_rejected(signed_stake, field, value, error):
    address, vault, pub, payload, sign = signed_stake
    intent, sig = sign(payload)
    changed = {**payload, field: value}
    with pytest.raises(StakeAuthorizationError, match=error):
        verify_thr_stake_authorization(
            intent=intent, signature=sig, public_key=pub, payload=changed,
            linked_wallet=address, pool_id=payload["pool_id"], vault_address=vault,
        )


def test_wrong_link_and_fee_even_when_signed(signed_stake):
    address, vault, pub, payload, sign = signed_stake
    intent, sig = sign(payload)
    with pytest.raises(StakeAuthorizationError, match="wallet_link_mismatch"):
        verify_thr_stake_authorization(
            intent=intent, signature=sig, public_key=pub, payload=payload,
            linked_wallet="THR" + "B" * 40, pool_id=payload["pool_id"], vault_address=vault,
        )
    altered = {**payload, "fee": "0.008999"}
    intent, sig = sign(altered)
    with pytest.raises(StakeAuthorizationError, match="signed_fee_mismatch"):
        verify_thr_stake_authorization(
            intent=intent, signature=sig, public_key=pub, payload=altered,
            linked_wallet=address, pool_id=payload["pool_id"], vault_address=vault,
        )


def test_signature_and_expiry_rejected(signed_stake):
    address, vault, pub, payload, sign = signed_stake
    intent, sig = sign(payload)
    with pytest.raises(StakeAuthorizationError, match="invalid_signature"):
        verify_thr_stake_authorization(
            intent=intent, signature=sig[:-2] + "00", public_key=pub, payload=payload,
            linked_wallet=address, pool_id=payload["pool_id"], vault_address=vault,
        )
    intent["created_at"] = str(int(time.time()) - 500)
    with pytest.raises(StakeAuthorizationError, match="intent_expired"):
        verify_thr_stake_authorization(
            intent=intent, signature=sig, public_key=pub, payload=payload,
            linked_wallet=address, pool_id=payload["pool_id"], vault_address=vault,
        )
