import os
import sys

from flask import Flask

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from wallet_v1_blueprint import register_wallet_v1_routes
import wallet_v1_production_final as wallet_v1_prod
import wallet_v1_activation as activation
import wallet_v1_handlers as handlers


class DummyRedis:
    def exists(self, _k):
        return False

    def setex(self, _k, _ttl, _v):
        return True


def _signed_tx(from_addr="THR" + "A" * 40):
    return {
        "from": from_addr,
        "to": "THR" + "B" * 40,
        "amount": 1,
        "token": "THR",
        "nonce": "n-1",
        "timestamp": 1710000000,
        "signature": "00",
        "publicKey": "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798",
    }


def _app(tmp_path):
    app = Flask(__name__)
    register_wallet_v1_routes(app, redis_client=DummyRedis(), node_role="master", read_only=False, sqlite_path=str(tmp_path / "ledger.sqlite3"))
    return app


def test_valid_signature_inactive_address_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(wallet_v1_prod, "verify_signed_transaction_core", lambda _tx: (True, ""))
    monkeypatch.setattr(activation.server_module, "has_pledge_access", lambda _a: False, raising=False)
    monkeypatch.setattr(activation.server_module, "is_wallet_whitelisted", lambda _a: False, raising=False)

    app = _app(tmp_path)
    res = app.test_client().post("/api/v1/tx/send", json={"tx": _signed_tx()})
    assert res.status_code == 403
    assert res.get_json()["error"] == "inactive_thr_address"


def test_valid_signature_whitelisted_address_proceeds(monkeypatch, tmp_path):
    monkeypatch.setattr(wallet_v1_prod, "verify_signed_transaction_core", lambda _tx: (True, ""))
    monkeypatch.setattr(activation.server_module, "has_pledge_access", lambda _a: False, raising=False)
    monkeypatch.setattr(activation.server_module, "is_wallet_whitelisted", lambda _a: True, raising=False)

    called = {"hit": False}
    def fake_exec(_tx):
        called["hit"] = True
        return True, {"ok": True, "tx_id": "n-1"}, 200
    monkeypatch.setattr(handlers, "execute_verified_signed_transfer", fake_exec)

    app = _app(tmp_path)
    res = app.test_client().post("/api/v1/tx/send", json={"tx": _signed_tx()})
    assert res.status_code == 200
    assert called["hit"] is True


def test_valid_signature_btc_pledged_address_proceeds(monkeypatch, tmp_path):
    monkeypatch.setattr(wallet_v1_prod, "verify_signed_transaction_core", lambda _tx: (True, ""))
    monkeypatch.setattr(activation.server_module, "has_pledge_access", lambda _a: True, raising=False)

    called = {"hit": False}
    def fake_exec(_tx):
        called["hit"] = True
        return True, {"ok": True, "tx_id": "n-1"}, 200
    monkeypatch.setattr(handlers, "execute_verified_signed_transfer", fake_exec)

    app = _app(tmp_path)
    res = app.test_client().post("/api/v1/tx/send", json={"tx": _signed_tx()})
    assert res.status_code == 200
    assert called["hit"] is True


def test_invalid_signature_rejected_before_activation(monkeypatch, tmp_path):
    calls = {"activation_called": False}

    def fail_if_called(_a):
        calls["activation_called"] = True
        return True

    monkeypatch.setattr(wallet_v1_prod, "verify_signed_transaction_core", lambda _tx: (False, "signature_invalid:bad_sig"))
    monkeypatch.setattr(activation.server_module, "has_pledge_access", fail_if_called, raising=False)

    app = _app(tmp_path)
    res = app.test_client().post("/api/v1/tx/send", json={"tx": _signed_tx()})
    assert res.status_code == 400
    assert res.get_json()["error"] == "signature_invalid"
    assert calls["activation_called"] is False


def test_replica_write_still_returns_503(tmp_path):
    app = Flask(__name__)
    register_wallet_v1_routes(app, redis_client=DummyRedis(), node_role="replica", read_only=True, sqlite_path=str(tmp_path / "ignored.sqlite3"))
    res = app.test_client().post("/api/v1/tx/send", json={"tx": _signed_tx()})
    assert res.status_code == 503


def test_existing_execution_adapter_path_preserved(monkeypatch, tmp_path):
    monkeypatch.setattr(wallet_v1_prod, "verify_signed_transaction_core", lambda _tx: (True, ""))
    monkeypatch.setattr(activation.server_module, "has_pledge_access", lambda _a: True, raising=False)
    called = {"hit": False}

    def fake_exec(_tx):
        called["hit"] = True
        return True, {"ok": True, "tx_id": "n-1", "status": "confirmed"}, 200

    monkeypatch.setattr(handlers, "execute_verified_signed_transfer", fake_exec)
    app = _app(tmp_path)
    res = app.test_client().post("/api/v1/tx/send", json={"tx": _signed_tx()})
    assert res.status_code == 200
    assert res.get_json()["status"] == "confirmed"
    assert called["hit"] is True
