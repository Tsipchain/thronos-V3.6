"""Actual server-boundary acceptance for the centralized Wallet V1 verifier."""

import hashlib
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils

import server
from wallet_v1_signed_request_verifier import (
    canonical_signed_request_bytes,
    derive_thr_address_from_public_key_hex,
)


def _signed_server_request():
    private_key = ec.derive_private_key(7, ec.SECP256K1())
    numbers = private_key.public_key().public_numbers()
    public_key = ("02" if numbers.y % 2 == 0 else "03") + f"{numbers.x:064x}"
    address = derive_thr_address_from_public_key_hex(public_key)
    request = {
        "canonical_v1_address": address,
        "from": address,
        "public_key": public_key,
        "bound_key_address": None,
        "signature_format": "secp256k1_compact",
        "action": "swap",
        "payload": {"synthetic": True},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "nonce": "server-boundary-synthetic-nonce",
    }
    message, _contract = canonical_signed_request_bytes(request)
    der = private_key.sign(message, ec.ECDSA(hashes.SHA256()))
    r, s = utils.decode_dss_signature(der)
    request["signature"] = f"{r:064x}{s:064x}"
    request["signing_payload_hash"] = hashlib.sha256(message).hexdigest()
    return request


def test_server_boundary_verifies_identity_and_atomically_rejects_replay(monkeypatch, tmp_path):
    request = _signed_server_request()
    monkeypatch.setattr(server, "REDIS_CLIENT", None)
    monkeypatch.setattr(
        server,
        "_WALLET_V1_SIGNED_NONCES_DB",
        str(tmp_path / "wallet_v1_signed_request_nonces.sqlite3"),
    )

    first_ok, first_error, first_address = server._verify_walletv1_new_format(request, "swap")
    replay_ok, replay_error, replay_address = server._verify_walletv1_new_format(request, "swap")

    assert first_ok is True
    assert first_error == {}
    assert first_address == request["canonical_v1_address"]
    assert replay_ok is False
    assert replay_error["error"] == "nonce_replay_detected"
    assert replay_address is None


def test_server_boundary_rejects_valid_key_claiming_an_unbound_wallet(monkeypatch, tmp_path):
    request = _signed_server_request()
    request["canonical_v1_address"] = "THR" + "F" * 40
    # Re-sign the forged claim so failure proves address binding, not malformed ECDSA.
    private_key = ec.derive_private_key(7, ec.SECP256K1())
    message, _contract = canonical_signed_request_bytes(request)
    der = private_key.sign(message, ec.ECDSA(hashes.SHA256()))
    r, s = utils.decode_dss_signature(der)
    request["signature"] = f"{r:064x}{s:064x}"
    request["signing_payload_hash"] = hashlib.sha256(message).hexdigest()

    monkeypatch.setattr(server, "REDIS_CLIENT", None)
    monkeypatch.setattr(
        server,
        "_WALLET_V1_SIGNED_NONCES_DB",
        str(tmp_path / "wallet_v1_signed_request_nonces.sqlite3"),
    )
    monkeypatch.setattr(server, "get_active_key_binding_for_address", lambda _address: None)

    ok, error, address = server._verify_walletv1_new_format(request, "swap")
    assert ok is False
    assert error["error"] == "no_active_binding"
    assert address is None


def test_server_boundary_fails_closed_for_non_object_request():
    ok, error = server.verify_wallet_v1_signed_request([], "swap")
    assert ok is False
    assert error["error"] == "invalid_request"
