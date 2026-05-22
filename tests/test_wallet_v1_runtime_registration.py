import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask import Flask

import wallet_v1_blueprint
import wallet_v1_handlers
import wallet_v1_production_final as wallet_v1_prod


def _app(monkeypatch):
    app = Flask(__name__)
    monkeypatch.setattr(wallet_v1_prod, "init_wallet_v1", lambda *a, **k: None)
    wallet_v1_blueprint.register_wallet_v1_routes(app, redis_client=object(), node_role="master", read_only=False, sqlite_path="/tmp/db.sqlite")
    return app


def test_wallet_health_route_exists(monkeypatch):
    app = _app(monkeypatch)
    resp = app.test_client().get("/api/v1/wallet/health")
    assert resp.status_code == 200
    assert resp.get_json().get("ok") is True


def test_unsigned_tx_is_400_not_404(monkeypatch):
    app = _app(monkeypatch)
    resp = app.test_client().post("/api/v1/tx/send", json={})
    assert resp.status_code == 400


def test_initialized_valid_tx_calls_execution_adapter(monkeypatch):
    app = _app(monkeypatch)

    monkeypatch.setattr(wallet_v1_prod, "NODE_ROLE", "master")
    monkeypatch.setattr(wallet_v1_prod, "READ_ONLY", False)
    monkeypatch.setattr(wallet_v1_prod, "verify_signed_transaction_core", lambda _tx: (True, ""))
    monkeypatch.setattr(wallet_v1_handlers, "require_active_thr_address", lambda _a: True)

    called = {}

    def _exec(tx):
        called["tx"] = tx
        return ({"ok": True, "tx_id": "abc"}, 200, {"Content-Type": "application/json"})

    monkeypatch.setattr(wallet_v1_handlers, "execute_verified_signed_transfer", _exec)

    payload = {"tx": {"from": "THR1", "to": "THR2", "amount": 1, "token": "THR", "nonce": "abc", "timestamp": 1}}
    resp = app.test_client().post("/api/v1/tx/send", json=payload)
    assert resp.status_code == 200
    assert called["tx"]["nonce"] == "abc"


def test_wallet_migrate_route_still_exists(monkeypatch):
    app = _app(monkeypatch)
    monkeypatch.setattr(wallet_v1_handlers, "migrate_legacy_address", lambda *a, **k: {"old_address": "A", "new_v1_address": "B", "migrated_at": "T", "old_read_only": True})
    resp = app.test_client().post("/api/v1/wallet/migrate", json={"old_thr_address": "A", "legacy_secret": "s", "new_compressed_public_key": "02" + "11" * 32})
    assert resp.status_code == 200
