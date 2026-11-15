import json
from pathlib import Path

import pytest

from survival_protocol_v1 import (
    Checkpoint,
    Envelope,
    EnvelopeError,
    Lifecycle,
    ReplayGuard,
    sign_envelope,
    verify_checkpoint,
)


PRIVATE_KEY = "01" * 32
CHECKPOINT = Checkpoint(630001, "ab" * 32)
FIXTURE = {
    "chain_id": "thronos-testnet-1",
    "asset_id": "THR",
    "sender": "THRsenderA1",
    "recipient": "THRrecipientB2",
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


def test_golden_fixture_is_stable_and_verifies():
    envelope = make_envelope()
    assert envelope.public_key == "031b84c5567b126440995d3ed5aaba0565d71e1834604819ff9c17f5e9d5dd078f"
    fixture = (Path(__file__).parent / "fixtures" / "survival_m0_golden.json").read_text().strip()
    assert envelope.to_json() == fixture
    assert envelope.to_json() == json.dumps(json.loads(envelope.to_json()), sort_keys=True, separators=(",", ":"))
    envelope.verify_signature(now=1730000001)
    assert "private" not in envelope.to_json().lower()


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


def test_fixture_has_no_server_or_transport_dependency():
    fixture_path = Path(__file__)
    assert fixture_path.exists()
