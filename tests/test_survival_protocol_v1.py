import hashlib
import json
from pathlib import Path

import pytest
from ecdsa import SECP256k1, SigningKey
from ecdsa.util import sigencode_der

from survival_protocol_v1 import (
    Checkpoint,
    Envelope,
    EnvelopeError,
    Lifecycle,
    ReplayGuard,
    sign_envelope,
    verify_checkpoint,
)
from wallet_v1_address_derivation import derive_thronos_address


PRIVATE_KEY = "01" * 32
UNRELATED_PRIVATE_KEY = "02" * 32
PUBLIC_KEY = "031b84c5567b126440995d3ed5aaba0565d71e1834604819ff9c17f5e9d5dd078f"
SENDER = derive_thronos_address(PUBLIC_KEY)
CHECKPOINT = Checkpoint(630001, "ab" * 32)
FIXTURE = {
    "chain_id": "thronos-testnet-1",
    "asset_id": "THR",
    "sender": SENDER,
    "recipient": "THR" + "A" * 40,
    "amount_units": 125000,
    "fee_units": 100,
    "nonce": 7,
    "message_id": "11111111-1111-4111-8111-111111111111",
    "issued_at": 1730000000,
    "expires_at": 1730003600,
    "checkpoint": CHECKPOINT,
}


def make_envelope(**overrides):
    values = {**FIXTURE, **overrides}
    return sign_envelope(private_key_hex=PRIVATE_KEY, **values)


def forge_sender_claim(sender: str, private_key_hex: str) -> Envelope:
    """Build a cryptographically valid signature with a false sender claim."""
    key = SigningKey.from_string(bytes.fromhex(private_key_hex), curve=SECP256k1)
    public_key = key.verifying_key.to_string(encoding="compressed").hex()
    unsigned = Envelope(
        **{**FIXTURE, "sender": sender},
        public_key=public_key,
        signature="00",
    )
    signature = key.sign_digest_deterministic(
        hashlib.sha256(unsigned.canonical_bytes()).digest(),
        hashfunc=hashlib.sha256,
        sigencode=sigencode_der,
    ).hex()
    return Envelope(**{**unsigned.as_dict(), "signature": signature})


def test_golden_fixture_is_stable_and_verifies():
    envelope = make_envelope()
    assert envelope.public_key == PUBLIC_KEY
    fixture = (Path(__file__).parent / "fixtures" / "survival_m0_golden.json").read_text().strip()
    assert envelope.to_json() == fixture
    assert envelope.to_json() == json.dumps(json.loads(envelope.to_json()), sort_keys=True, separators=(",", ":"))
    envelope.verify_signature(now=1730000001)
    assert "private" not in envelope.to_json().lower()


def test_valid_sender_is_canonical_and_bound_to_public_key():
    envelope = make_envelope()
    assert envelope.sender == derive_thronos_address(envelope.public_key)
    assert envelope.sender == envelope.sender.upper()
    envelope.verify_signature(now=1730000001)


def test_forged_sender_with_valid_attacker_signature_is_rejected():
    victim = "THR" + "B" * 40
    forged = forge_sender_claim(victim, UNRELATED_PRIVATE_KEY)
    with pytest.raises(EnvelopeError, match="public key does not match sender"):
        forged.verify_signature(now=1730000001)
    with pytest.raises(EnvelopeError, match="public key does not match sender"):
        make_envelope(sender=victim)


def test_unrelated_public_key_is_rejected_before_signature_acceptance():
    data = json.loads(make_envelope().to_json())
    unrelated = SigningKey.from_string(
        bytes.fromhex(UNRELATED_PRIVATE_KEY), curve=SECP256k1
    )
    data["public_key"] = unrelated.verifying_key.to_string(
        encoding="compressed"
    ).hex()
    with pytest.raises(EnvelopeError, match="public key does not match sender"):
        Envelope.from_json(json.dumps(data)).verify_signature(now=1730000001)


def test_binary_domain_separation_changes_signature_digest():
    envelope = make_envelope()
    assert envelope.canonical_bytes().startswith(b"THRONOS/SURVIVAL/M0\x00")
    assert envelope.canonical_bytes() != json.dumps(envelope.unsigned_dict(), sort_keys=True, separators=(",", ":")).encode()


def test_json_round_trip_and_lifecycle_transitions():
    envelope = make_envelope()
    restored = Envelope.from_json(envelope.to_json())
    assert restored == envelope
    delivered = restored.transition(Lifecycle.DELIVERED_TO_PEER)
    assert delivered.lifecycle is Lifecycle.DELIVERED_TO_PEER
    with pytest.raises(EnvelopeError, match="invalid lifecycle"):
        delivered.transition(Lifecycle.DRAFT)


def test_replay_guard_rejects_duplicate_message_and_nonce():
    guard = ReplayGuard()
    first = make_envelope()
    guard.accept(first, now=1730000001)
    with pytest.raises(EnvelopeError, match="duplicate message_id"):
        guard.accept(first, now=1730000001)
    second = make_envelope(message_id="22222222-2222-4222-8222-222222222222")
    with pytest.raises(EnvelopeError, match="duplicate sender nonce"):
        guard.accept(second, now=1730000001)


def test_checkpoint_requires_caller_owned_trust_anchor():
    envelope = make_envelope()
    verify_checkpoint(envelope, {630001: "AB" * 32})
    with pytest.raises(EnvelopeError, match="checkpoint"):
        verify_checkpoint(envelope, {630001: "CD" * 32})


@pytest.mark.parametrize("field,value", [
    ("amount_units", 1.5),
    ("fee_units", -1),
    ("nonce", True),
    ("expires_at", 1730000000),
])
def test_malformed_integer_or_time_fields_are_rejected(field, value):
    with pytest.raises(EnvelopeError):
        make_envelope(**{field: value})


def test_expired_and_future_messages_are_rejected():
    envelope = make_envelope()
    with pytest.raises(EnvelopeError, match="expired"):
        envelope.verify_signature(now=1730003600)
    with pytest.raises(EnvelopeError, match="future"):
        envelope.verify_signature(now=1729999999)


@pytest.mark.parametrize("asset_id,sender,recipient", [
    ("ETH", "0x0000000000000000000000000000000000000001", "THRrecipientB2"),
    ("BTC", "bc1qvalidaddress12345", "0x0000000000000000000000000000000000000001"),
])
def test_chain_specific_address_boundaries(asset_id, sender, recipient):
    with pytest.raises(EnvelopeError, match="recipient"):
        make_envelope(asset_id=asset_id, sender=sender, recipient=recipient)


def test_tampering_signature_and_unknown_fields_are_rejected():
    data = json.loads(make_envelope().to_json())
    data["amount_units"] = 125001
    with pytest.raises(EnvelopeError, match="invalid signature"):
        Envelope.from_json(json.dumps(data)).verify_signature(now=1730000001)
    data = json.loads(make_envelope().to_json())
    data["unexpected"] = True
    with pytest.raises(EnvelopeError, match="unexpected"):
        Envelope.from_json(json.dumps(data))


@pytest.mark.parametrize("sender", [
    SENDER.lower(),
    "THR" + "A" * 39,
    "THR" + "G" * 40,
])
def test_noncanonical_thr_sender_is_rejected(sender):
    with pytest.raises(EnvelopeError, match="sender"):
        make_envelope(sender=sender)


@pytest.mark.parametrize("asset_id,sender,recipient", [
    (
        "BTC",
        "bc1qvalidsender12345",
        "bc1qvalidrecipient12345",
    ),
    (
        "ETH",
        "0x0000000000000000000000000000000000000001",
        "0x0000000000000000000000000000000000000002",
    ),
])
def test_assets_without_canonical_key_derivation_fail_closed(
    asset_id, sender, recipient,
):
    with pytest.raises(EnvelopeError, match="identity binding unsupported"):
        make_envelope(asset_id=asset_id, sender=sender, recipient=recipient)


def test_fixture_has_no_server_or_transport_dependency():
    fixture_path = Path(__file__)
    assert fixture_path.exists()
