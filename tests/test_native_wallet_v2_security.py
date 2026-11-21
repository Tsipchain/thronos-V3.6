"""Native wallet V2 security acceptance with synthetic state only."""

import hashlib
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils

import server
import server_ext  # noqa: F401 - registers the mobile compatibility routes
from wallet_v1_signed_request_verifier import (
    FULL_PAYLOAD_CHAIN_ID,
    FULL_PAYLOAD_DOMAIN,
    FULL_PAYLOAD_PROTOCOL_VERSION,
    FULL_PAYLOAD_SIGNATURE_FORMAT,
    canonical_signed_request_bytes,
    derive_thr_address_from_public_key_hex,
)


ROOT = Path(__file__).parents[1]


def _signed_request(action, payload, nonce, private_value=811):
    private_key = ec.derive_private_key(private_value, ec.SECP256K1())
    numbers = private_key.public_key().public_numbers()
    public_key = ("02" if numbers.y % 2 == 0 else "03") + f"{numbers.x:064x}"
    address = derive_thr_address_from_public_key_hex(public_key)
    issued_at = int(time.time())
    request = {
        "signature_format": FULL_PAYLOAD_SIGNATURE_FORMAT,
        "protocol_version": FULL_PAYLOAD_PROTOCOL_VERSION,
        "domain": FULL_PAYLOAD_DOMAIN,
        "chain_id": FULL_PAYLOAD_CHAIN_ID,
        "action": action,
        "canonical_v1_address": address,
        "from": address,
        "signer_address": address,
        "public_key": public_key,
        "payload": payload,
        "issued_at": str(issued_at),
        "expires_at": str(issued_at + 120),
        "nonce": nonce,
    }
    message, _ = canonical_signed_request_bytes(request)
    der = private_key.sign(message, ec.ECDSA(hashes.SHA256()))
    r, s = utils.decode_dss_signature(der)
    request["signature"] = f"{r:064x}{s:064x}"
    request["signing_payload_hash"] = hashlib.sha256(message).hexdigest()
    return request


@pytest.fixture(autouse=True)
def isolated_nonce_store(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "REDIS_CLIENT", None)
    monkeypatch.setattr(
        server,
        "_WALLET_V1_SIGNED_NONCES_DB",
        str(tmp_path / "native_wallet_nonces.sqlite3"),
    )


def test_native_sources_do_not_transmit_private_keys_or_legacy_secrets():
    api = (ROOT / "thronos-wallet-app/src/services/api.ts").read_text()
    cross_chain = (ROOT / "thronos-wallet-app/src/services/crossChain.ts").read_text()
    screens = "\n".join(
        (ROOT / "thronos-wallet-app/src/screens" / name).read_text()
        for name in ("PoolsScreen.tsx", "CreateTokenScreen.tsx", "NFTScreen.tsx", "SwapScreen.tsx")
    )
    assert "private_key_hex" not in api
    assert "private_key_hex" not in cross_chain
    assert "/api/wallet/v1/btc-address-from-key" not in cross_chain
    assert "private_key_hex" not in screens
    assert "auth_secret:" not in screens
    assert "signWalletV1FullPayloadRequest" in screens


def test_native_sdk_network_paths_never_serialize_stored_secret():
    kotlin = (ROOT / "mobile-sdk/android/ThronosSDK.kt").read_text()
    swift = (ROOT / "mobile-sdk/ios/ThronosSDK.swift").read_text()
    js = (ROOT / "mobile-sdk/src/index.js").read_text()
    assert 'url("$apiUrl/api/wallet/send")' not in kotlin
    assert 'URL(string: "\\(apiUrl)/api/wallet/send")' not in swift
    assert "secret: wallet.secret" not in js
    assert "/api/v1/tx/send" in kotlin
    assert "/api/v1/tx/send" in swift


def test_server_retires_private_key_btc_derivation_endpoint():
    response = server.app.test_client().post(
        "/api/wallet/v1/btc-address-from-key",
        json={"private_key_hex": "11" * 32},
    )
    assert response.status_code == 410
    assert response.get_json()["error"] == "private_key_input_retired"


@pytest.mark.parametrize(
    ("action", "payload"),
    [
        ("token_create", {"name": "Synthetic", "symbol": "SYN", "total_supply": "100", "decimals": "8"}),
        ("nft_mint", {"name": "Synthetic NFT", "description": "test", "category": "art", "price": "2", "royalties": "5", "max_mint_fee": "1"}),
        ("nft_buy", {"nft_id": "NFT-SYNTHETIC", "max_price": "3"}),
    ],
)
def test_mobile_actions_have_strict_v2_execution_schemas(action, payload):
    trusted, error = server._wallet_v1_v2_trusted_execution_data(
        _signed_request(action, payload, f"schema-{action}"), action)
    assert error is None
    assert trusted["canonical_v1_address"] == trusted["from"]
    assert trusted[server._WALLET_V1_V2_ACTION_SCHEMAS[action]["sender_field"]] == trusted["from"]


def test_unsigned_mobile_action_override_is_rejected_before_nonce_consumption(monkeypatch):
    request = _signed_request(
        "token_create",
        {"name": "Synthetic", "symbol": "SYN", "total_supply": "100", "decimals": "8"},
        "token-override",
    )
    request["total_supply"] = "999999"
    calls = []
    real_verify = server.verify_wallet_v1_signed_request

    def tracked(*args, **kwargs):
        calls.append(True)
        return real_verify(*args, **kwargs)

    monkeypatch.setattr(server, "verify_wallet_v1_signed_request", tracked)
    response = server.app.test_client().post("/api/wallet/v1/create_token", json=request)
    assert response.status_code == 400
    assert response.get_json()["error"] == "unsigned_top_level_fields"
    assert calls == []


def test_v2_token_create_executes_only_signed_payload(monkeypatch):
    tokens = []
    balances = {}
    chain = []
    monkeypatch.setattr(server, "load_tokens", lambda: tokens)
    monkeypatch.setattr(server, "save_tokens", lambda value: tokens.__setitem__(slice(None), value))
    monkeypatch.setattr(server, "load_token_balances", lambda: balances)
    monkeypatch.setattr(server, "save_token_balances", lambda value: balances.update(value))
    monkeypatch.setattr(server, "load_json", lambda _path, _default=None: chain)
    monkeypatch.setattr(server, "save_json", lambda _path, value: chain.__setitem__(slice(None), value))
    monkeypatch.setattr(server, "update_last_block", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "broadcast_tx", lambda *_args, **_kwargs: None)

    request = _signed_request(
        "token_create",
        {"name": "Synthetic", "symbol": "SYN", "total_supply": "100", "decimals": "8"},
        "token-create-runtime",
    )
    response = server.app.test_client().post("/api/wallet/v1/create_token", json=request)
    assert response.status_code == 201
    body = response.get_json()
    assert body["token"]["total_supply"] == 100
    assert body["token"]["owner"] == request["canonical_v1_address"]
    assert balances["SYN"][request["canonical_v1_address"]] == 100


def test_nft_buy_price_cannot_exceed_signed_maximum(monkeypatch):
    request = _signed_request(
        "nft_buy", {"nft_id": "NFT-SYNTHETIC", "max_price": "2"}, "nft-max-price")
    address = request["canonical_v1_address"]
    registry = {"nfts": [{
        "id": "NFT-SYNTHETIC", "name": "Synthetic", "price": 3,
        "royalties": 5, "creator": "THR" + "A" * 40,
        "owner": "THR" + "B" * 40, "for_sale": True,
    }]}
    monkeypatch.setattr(server, "load_nft_registry", lambda: registry)
    monkeypatch.setattr(server, "load_json", lambda _path, _default=None: {address: 100})
    response = server.app.test_client().post("/api/wallet/v1/nfts/buy", json=request)
    assert response.status_code == 409
    assert response.get_json()["error"] == "nft_price_exceeds_signed_maximum"


def test_withdrawal_and_cross_chain_liquidity_are_fail_closed_in_native_client():
    api = (ROOT / "thronos-wallet-app/src/services/api.ts").read_text()
    pools = (ROOT / "thronos-wallet-app/src/screens/PoolsScreen.tsx").read_text()
    assert "wallet_v1_v2_withdrawal_contract_required" in api
    assert "addLiquidityCrossChain" not in api
    assert "Cross-chain liquidity is disabled" in pools


def test_unreviewed_financial_actions_are_network_fail_closed():
    api = (ROOT / "thronos-wallet-app/src/services/api.ts").read_text()
    for gate in (
        "wallet_v1_v2_staking_contract_required",
        "wallet_v1_v2_governance_contract_required",
        "wallet_v1_v2_bridge_contract_required",
        "wallet_v1_v2_bridge_withdrawal_contract_required",
        "wallet_v1_v2_pythia_deposit_contract_required",
        "wallet_v1_v2_pythia_withdrawal_contract_required",
    ):
        assert gate in api
    for unsafe_route in (
        "request('/api/pledge/stake'",
        "request('/api/v1/governance/vote'",
        "request('/api/bridge/execute'",
        "request('/api/bridge/burn'",
        "request('/api/pools/deposit'",
        "request('/api/pools/withdraw-intent'",
    ):
        assert unsafe_route not in api


def test_mutations_are_never_retried_against_replica():
    api = (ROOT / "thronos-wallet-app/src/services/api.ts").read_text()
    assert "const baseUrls = method === 'GET' || method === 'HEAD' ? [BASE, BASE_REPLICA] : [BASE]" in api
