"""Tests for the device-owned Earn wallet unlock handoff."""
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from flask import Flask

from services.earn_account import EarnAccountStore, register_earn_account_routes
from wallet_v1_address_derivation import derive_thronos_address


@pytest.fixture()
def store(tmp_path):
    store = EarnAccountStore(str(tmp_path / "earn.db"), "unlock-device-test")
    user = store.register("unlock@example.com", "password123")
    store.record_thc_credit(user["earn_user_id"], "test", "unlock-funds", "10025.000000")
    entry = store.thc_history(user["earn_user_id"])[0]
    store.transition_thc(entry["entry_id"], "confirmed")
    return store


@pytest.fixture()
def user(store):
    return store.user_by_email("unlock@example.com")


@pytest.fixture()
def client(store):
    app = Flask(__name__)
    app.config["TESTING"] = True
    register_earn_account_routes(app, store)
    return app.test_client()


def _auth(client):
    login = client.post("/api/earn/login", json={
        "email": "unlock@example.com", "password": "password123",
    }).get_json()
    return {"Authorization": "Bearer " + login["access_token"]}


def _keypair():
    private = ec.generate_private_key(ec.SECP256K1())
    public_key = private.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint,
    ).hex()
    return private, public_key, derive_thronos_address(public_key)


def _proof(private, public_key, wallet, challenge):
    keys = ["action", "challenge_id", "expires_at", "nonce", "wallet_address"]
    if challenge.get("approval"):
        keys.append("approval")
    message = json.dumps(
        {key: str(challenge[key]) for key in keys},
        sort_keys=True, separators=(",", ":"),
    ).encode()
    der = private.sign(
        hashlib.sha256(message).digest(),
        ec.ECDSA(utils.Prehashed(hashes.SHA256())),
    )
    r, s = utils.decode_dss_signature(der)
    return {
        "challenge_id": challenge["challenge_id"], "wallet_address": wallet,
        "public_key": public_key, "signature": f"{r:064x}{s:064x}",
    }


def test_unlock_feature_is_closed_by_default(client):
    response = client.post("/api/earn/wallet-unlock/pledge", headers=_auth(client), json={
        "idempotency_key": "closed",
    })
    assert response.status_code == 409
    assert response.get_json()["error"] == "earn_wallet_unlock_not_enabled"


def test_signed_first_wallet_link_settles_pledge_atomically(client, store, user):
    headers = _auth(client)
    with patch.dict(os.environ, {"EARN_WALLET_UNLOCK_ENABLED": "1"}):
        pledged = client.post("/api/earn/wallet-unlock/pledge", headers=headers, json={
            "idempotency_key": "first-wallet",
        })
        assert pledged.status_code == 201
        pledge = pledged.get_json()
        private, public_key, wallet = _keypair()
        challenge = client.post("/api/earn/wallet-link/challenge", headers=headers, json={
            "wallet_address": wallet,
        }).get_json()
        proof = _proof(private, public_key, wallet, challenge)
        proof["wallet_unlock_pledge_id"] = pledge["pledge_id"]
        completed = client.post("/api/earn/wallet-link/complete", headers=headers, json=proof)
    assert completed.status_code == 200
    receipt = store.wallet_unlock_pledges(user["earn_user_id"])[0]
    assert receipt["status"] == "settled"
    assert receipt["wallet_address"] == wallet
    assert store.wallet_link_for_user(user["earn_user_id"])["wallet_address"] == wallet


def test_bad_proof_cannot_link_or_consume_pledge(client, store, user):
    headers = _auth(client)
    with patch.dict(os.environ, {"EARN_WALLET_UNLOCK_ENABLED": "1"}):
        pledge = client.post("/api/earn/wallet-unlock/pledge", headers=headers, json={
            "idempotency_key": "bad-proof",
        }).get_json()
        private, public_key, wallet = _keypair()
        challenge = client.post("/api/earn/wallet-link/challenge", headers=headers, json={
            "wallet_address": wallet,
        }).get_json()
        proof = _proof(private, public_key, wallet, challenge)
        proof["wallet_unlock_pledge_id"] = pledge["pledge_id"]
        proof["signature"] = "00" * 64
        rejected = client.post("/api/earn/wallet-link/complete", headers=headers, json=proof)
    assert rejected.status_code == 403
    assert store.wallet_unlock_pledges(user["earn_user_id"])[0]["status"] == "reserved"
    assert store.wallet_link_for_user(user["earn_user_id"]) is None


def test_pwa_handoff_does_not_send_recovery_material():
    app_js = (Path(__file__).parent.parent / "public" / "wallet-pwa" / "app.js").read_text()
    block = app_js[app_js.index("async function _linkActiveWalletToEarn"):
                   app_js.index("function _formatEarnThc")]
    assert "walletUnlockPledgeId = null" in block
    assert "wallet_unlock_pledge_id: walletUnlockPledgeId" in block
    assert "mnemonic" not in block.lower()
    assert "recovery phrase" not in block.lower()
