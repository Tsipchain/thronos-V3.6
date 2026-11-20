"""Real-route Wallet V1 activation admission tests with synthetic identities.

The route, ECDSA verifier and activation resolver are production code. Only
the backend pledge/migration records and final ledger executor are isolated.
"""

import json
import time
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from flask import Flask

from wallet_v1_blueprint import register_wallet_v1_routes
import wallet_v1_activation as activation
import wallet_v1_handlers as handlers
import wallet_v1_production_final as wallet_v1_prod


class DummyRedis:
    def __init__(self):
        self.keys = set()

    def exists(self, key):
        return key in self.keys

    def setex(self, key, _ttl, _value):
        self.keys.add(key)
        return True


def _signed_tx(private_value=101, nonce="activation-nonce"):
    private_key = ec.derive_private_key(private_value, ec.SECP256K1())
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.CompressedPoint,
    ).hex()
    from_address = wallet_v1_prod.derive_thronos_address(public_key)
    tx = {
        "from": from_address,
        "to": "THR" + "B" * 40,
        "amount": 1,
        "token": "THR",
        "nonce": nonce,
        "timestamp": int(time.time()),
        "publicKey": public_key,
    }
    message = json.dumps(
        {key: tx[key] for key in ("from", "to", "amount", "token", "nonce", "timestamp")},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    tx["signature"] = private_key.sign(message, ec.ECDSA(hashes.SHA256())).hex()
    return tx


def _app(tmp_path, *, role="master", read_only=False):
    app = Flask(__name__)
    register_wallet_v1_routes(
        app,
        redis_client=DummyRedis(),
        node_role=role,
        read_only=read_only,
        sqlite_path=str(tmp_path / "ledger.sqlite3"),
    )
    return app


def _backend(*, pledge_state=None, btc_access=False, whitelisted=False, calls=None):
    calls = calls if calls is not None else []

    def resolve(address):
        calls.append(("resolve_wallet_pledge_state", address))
        return dict(pledge_state or {})

    def has_btc(address):
        calls.append(("has_pledge_access", address))
        return btc_access

    return SimpleNamespace(
        resolve_wallet_pledge_state=resolve,
        has_pledge_access=has_btc,
        is_wallet_whitelisted=lambda _address: whitelisted,
        get_mining_whitelist_entry=lambda _address: None,
        _whitelist_allows_no_pledge=lambda _entry: False,
    )


@pytest.fixture(autouse=True)
def isolated_activation(monkeypatch):
    monkeypatch.setattr(activation, "resolve_migration", lambda _address: None)
    monkeypatch.setattr(
        handlers,
        "execute_verified_signed_transfer",
        lambda tx: ({"ok": True, "status": "confirmed", "tx_id": tx["nonce"]}, 200),
    )


def test_active_usdt_pledged_wallet_is_admitted_through_real_route(monkeypatch, tmp_path):
    tx = _signed_tx(nonce="usdt-active")
    monkeypatch.setattr(
        activation,
        "_server",
        lambda: _backend(pledge_state={"active": True, "pledge_type": "usdt_bnb"}),
    )
    response = _app(tmp_path).test_client().post("/api/v1/tx/send", json={"tx": tx})
    assert response.status_code == 200
    assert response.get_json()["tx_id"] == "usdt-active"


def test_active_btc_pledged_wallet_is_admitted_through_real_route(monkeypatch, tmp_path):
    tx = _signed_tx(private_value=102, nonce="btc-active")
    calls = []
    monkeypatch.setattr(
        activation,
        "_server",
        lambda: _backend(btc_access=True, calls=calls),
    )
    response = _app(tmp_path).test_client().post("/api/v1/tx/send", json={"tx": tx})
    assert response.status_code == 200
    assert ("has_pledge_access", tx["from"]) in calls


def test_completed_migrated_canonical_wallet_is_admitted(monkeypatch, tmp_path):
    tx = _signed_tx(private_value=103, nonce="migrated-canonical")
    old_address = "THR" + "C" * 40
    record = {
        "old_address": old_address,
        "new_v1_address": tx["from"],
        "status": "completed",
    }
    monkeypatch.setattr(activation, "resolve_migration", lambda address: record if address in {old_address, tx["from"]} else None)
    monkeypatch.setattr(activation, "_server", lambda: _backend())
    response = _app(tmp_path).test_client().post("/api/v1/tx/send", json={"tx": tx})
    assert response.status_code == 200


def test_migrated_old_address_remains_read_only(monkeypatch, tmp_path):
    tx = _signed_tx(private_value=104, nonce="migrated-old")
    new_address = "THR" + "D" * 40
    record = {
        "old_address": tx["from"],
        "new_v1_address": new_address,
        "status": "repaired",
    }
    monkeypatch.setattr(activation, "resolve_migration", lambda address: record if address in {tx["from"], new_address} else None)
    monkeypatch.setattr(activation, "_server", lambda: _backend())
    response = _app(tmp_path).test_client().post("/api/v1/tx/send", json={"tx": tx})
    assert response.status_code == 403
    assert response.get_json()["error"] == "legacy_address_migrated_read_only"


def test_unpledged_unapproved_address_is_rejected(monkeypatch, tmp_path):
    tx = _signed_tx(private_value=105, nonce="inactive")
    monkeypatch.setattr(activation, "_server", lambda: _backend())
    response = _app(tmp_path).test_client().post("/api/v1/tx/send", json={"tx": tx})
    assert response.status_code == 403
    assert response.get_json()["error"] == "inactive_thr_address"


def test_invalid_cryptographic_signature_is_rejected_before_activation_or_execution(
    monkeypatch, tmp_path
):
    tx = _signed_tx(private_value=106, nonce="invalid-signature")
    tx["amount"] = 2
    activation_calls = []
    execution_calls = []
    monkeypatch.setattr(
        activation,
        "_server",
        lambda: _backend(pledge_state={"active": True}, calls=activation_calls),
    )
    monkeypatch.setattr(
        handlers,
        "execute_verified_signed_transfer",
        lambda _tx: execution_calls.append(True),
    )
    response = _app(tmp_path).test_client().post("/api/v1/tx/send", json={"tx": tx})
    assert response.status_code == 400
    assert response.get_json()["error"] == "signature_invalid"
    assert activation_calls == []
    assert execution_calls == []


def test_replica_rejects_mutation_before_signature_or_activation(monkeypatch, tmp_path):
    activation_calls = []
    monkeypatch.setattr(
        activation,
        "_server",
        lambda: _backend(pledge_state={"active": True}, calls=activation_calls),
    )
    response = _app(tmp_path, role="replica", read_only=True).test_client().post(
        "/api/v1/tx/send", json={"tx": _signed_tx(private_value=107, nonce="replica")}
    )
    assert response.status_code == 503
    assert response.get_json()["error"] == "read_only_replica"
    assert activation_calls == []
