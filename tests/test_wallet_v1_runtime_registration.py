import importlib
import os
import sys
import types

import pytest
from flask import Flask

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from wallet_v1_blueprint import register_wallet_v1_routes


class DummyRedis:
    def exists(self, _k):
        return False

    def setex(self, _k, _ttl, _v):
        return True


def test_blueprint_registers_with_valid_config(tmp_path):
    app = Flask(__name__)
    db_path = tmp_path / "ledger.sqlite3"
    register_wallet_v1_routes(
        app,
        redis_client=DummyRedis(),
        node_role="master",
        read_only=False,
        sqlite_path=str(db_path),
    )
    client = app.test_client()

    tx_res = client.post("/api/v1/tx/send", json={})
    assert tx_res.status_code == 400
    assert tx_res.get_json()["error"] == "missing_tx_envelope"

    health = client.get("/api/v1/wallet/health")
    body = health.get_json()
    assert health.status_code == 200
    assert body["wallet_v1_loaded"] is True
    assert body["redis_present"] is True
    assert body["sqlite_path_present"] is True


def test_missing_redis_keeps_app_alive_and_exposes_diagnostics():
    app = Flask(__name__)

    @app.get("/api/dashboard")
    def dashboard():
        return {"ok": True}, 200

    @app.get("/api/transfers")
    def transfers():
        return {"ok": True}, 200

    with pytest.raises(RuntimeError):
        register_wallet_v1_routes(app, redis_client=None, node_role="master", read_only=False, sqlite_path="/tmp/x.sqlite3")

    client = app.test_client()
    assert client.get("/api/dashboard").status_code == 200
    assert client.get("/api/transfers").status_code == 200

    tx_res = client.post("/api/v1/tx/send", json={})
    assert tx_res.status_code == 503

    health = client.get("/api/v1/wallet/health")
    body = health.get_json()
    assert health.status_code == 200
    assert body["wallet_v1_loaded"] is False
    assert body["redis_present"] is False


def test_replica_mode_rejects_write_with_503(tmp_path):
    app = Flask(__name__)
    register_wallet_v1_routes(
        app,
        redis_client=DummyRedis(),
        node_role="replica",
        read_only=True,
        sqlite_path=str(tmp_path / "ignored.sqlite3"),
    )

    res = app.test_client().post(
        "/api/v1/tx/send",
        json={"tx": {"from": "THRA", "to": "THRB", "amount": 1, "nonce": "n1", "timestamp": 1}},
    )
    assert res.status_code == 503
    assert res.get_json()["error"] == "read_only_replica"


def test_server_ext_import_does_not_crash_when_wallet_registration_fails(monkeypatch):
    fake_server = types.ModuleType("server")
    fake_server.app = Flask("fake")
    fake_server.NODE_ROLE = "master"
    fake_server.READ_ONLY = False
    fake_server.REDIS_CLIENT = None
    fake_server.LEDGER_DB_FILE = "/tmp/ledger.sqlite3"

    monkeypatch.setitem(sys.modules, "server", fake_server)
    sys.modules.pop("server_ext", None)

    mod = importlib.import_module("server_ext")
    assert hasattr(mod, "app")
