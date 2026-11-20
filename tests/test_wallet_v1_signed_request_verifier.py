import hashlib
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils

from wallet_v1_signed_request_verifier import (
    ADAPTER_CONTRACT,
    LEGACY_WEB_CONTRACT,
    canonical_signed_request_bytes,
    derive_thr_address_from_public_key_hex,
    verify_signed_request,
)


def _key_material(private_value):
    private_key = ec.derive_private_key(private_value, ec.SECP256K1())
    numbers = private_key.public_key().public_numbers()
    public_key = ("02" if numbers.y % 2 == 0 else "03") + f"{numbers.x:064x}"
    return private_key, public_key, derive_thr_address_from_public_key_hex(public_key)


def _sign_request(private_key, request):
    message, _ = canonical_signed_request_bytes(request)
    der = private_key.sign(message, ec.ECDSA(hashes.SHA256()))
    r, s = utils.decode_dss_signature(der)
    request["signature"] = f"{r:064x}{s:064x}"
    request["signing_payload_hash"] = hashlib.sha256(message).hexdigest()
    return request


class NonceGuard:
    def __init__(self):
        self.seen = set()

    def __call__(self, address, nonce, _timestamp):
        key = (address, nonce)
        if key in self.seen:
            return False, "nonce_replay_detected"
        self.seen.add(key)
        return True, ""


def _direct_request(private_value=1, signature_format="secp256k1_compact"):
    private_key, public_key, address = _key_material(private_value)
    now = time.time()
    timestamp = (
        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
        if signature_format == "secp256k1_compact"
        else int(now)
    )
    request = {
        "canonical_v1_address": address,
        "from": address,
        "public_key": public_key,
        "bound_key_address": None,
        "signature_format": signature_format,
        "action": "swap",
        "payload": {"amount": "1.25", "asset": "THR"},
        "timestamp": timestamp,
        "nonce": "synthetic-nonce-0001",
    }
    return _sign_request(private_key, request), now


def test_valid_direct_wallet_legacy_web_contract():
    request, now = _direct_request()
    ok, details = verify_signed_request(
        request,
        "swap",
        binding_lookup=lambda _address: None,
        nonce_guard=NonceGuard(),
        now=now,
    )
    assert ok is True
    assert details["signature_contract"] == LEGACY_WEB_CONTRACT
    assert details["is_bound_signer"] is False


def test_valid_direct_wallet_adapter_contract():
    request, now = _direct_request(signature_format="compact_secp256k1_hex")
    ok, details = verify_signed_request(
        request,
        "swap",
        binding_lookup=lambda _address: None,
        nonce_guard=NonceGuard(),
        now=now,
    )
    assert ok is True
    assert details["signature_contract"] == ADAPTER_CONTRACT


def test_wrong_signature_is_rejected():
    request, now = _direct_request()
    request["signature"] = "00" * 64
    ok, details = verify_signed_request(
        request, "swap", binding_lookup=lambda _address: None, nonce_guard=NonceGuard(), now=now
    )
    assert ok is False
    assert details["error"] == "invalid_signature"


def test_forged_address_is_rejected_without_binding():
    request, now = _direct_request()
    _, _, forged_address = _key_material(2)
    request["canonical_v1_address"] = forged_address
    # Re-signing proves key ownership but must not prove ownership of the forged address.
    private_key, _, _ = _key_material(1)
    _sign_request(private_key, request)
    ok, details = verify_signed_request(
        request, "swap", binding_lookup=lambda _address: None, nonce_guard=NonceGuard(), now=now
    )
    assert ok is False
    assert details["error"] == "no_active_binding"


def test_active_legacy_binding_preserves_migrated_wallet_identity():
    signer_private, signer_public, signer_address = _key_material(2)
    _, _, canonical_address = _key_material(1)
    now = time.time()
    request = {
        "canonical_v1_address": canonical_address,
        "from": canonical_address,
        "public_key": signer_public,
        "bound_key_address": signer_address,
        "signature_format": "secp256k1_compact",
        "action": "swap",
        "payload": {"amount": "1.25"},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "nonce": "synthetic-bound-nonce",
    }
    _sign_request(signer_private, request)
    legacy_binding_without_status = {
        "address": canonical_address,
        "public_key": signer_public,
        "public_key_address": signer_address,
    }
    ok, details = verify_signed_request(
        request,
        "swap",
        binding_lookup=lambda address: legacy_binding_without_status if address == canonical_address else None,
        nonce_guard=NonceGuard(),
        now=now,
    )
    assert ok is True
    assert details["is_bound_signer"] is True
    assert details["canonical_v1_address"] == canonical_address


def test_unrelated_public_key_cannot_use_existing_binding():
    request, now = _direct_request(private_value=3)
    _, bound_public, bound_address = _key_material(2)
    _, _, canonical_address = _key_material(1)
    request["canonical_v1_address"] = canonical_address
    request["from"] = canonical_address
    private_key, _, _ = _key_material(3)
    _sign_request(private_key, request)
    binding = {"public_key": bound_public, "public_key_address": bound_address}
    ok, details = verify_signed_request(
        request, "swap", binding_lookup=lambda _address: binding, nonce_guard=NonceGuard(), now=now
    )
    assert ok is False
    assert details["error"] == "public_key_mismatch"


def test_modified_adapter_payload_invalidates_signature():
    request, now = _direct_request(signature_format="compact_secp256k1_hex")
    request["payload"]["amount"] = "999"
    ok, details = verify_signed_request(
        request, "swap", binding_lookup=lambda _address: None, nonce_guard=NonceGuard(), now=now
    )
    assert ok is False
    assert details["error"] == "signing_payload_hash_mismatch"


def test_replay_is_rejected_after_first_valid_verification():
    request, now = _direct_request()
    guard = NonceGuard()
    first_ok, _ = verify_signed_request(
        request, "swap", binding_lookup=lambda _address: None, nonce_guard=guard, now=now
    )
    second_ok, second = verify_signed_request(
        request, "swap", binding_lookup=lambda _address: None, nonce_guard=guard, now=now
    )
    assert first_ok is True
    assert second_ok is False
    assert second["error"] == "nonce_replay_detected"


def test_expired_request_fails_before_nonce_consumption():
    request, now = _direct_request()
    guard = NonceGuard()
    ok, details = verify_signed_request(
        request, "swap", binding_lookup=lambda _address: None, nonce_guard=guard, now=now + 301
    )
    assert ok is False
    assert details["error"] == "timestamp_out_of_range"
    assert guard.seen == set()
