import os
import sys

from flask import Flask

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from wallet_v1_blueprint import register_wallet_v1_routes
import wallet_v1_production_final as wallet_v1_prod
import wallet_v1_migration as migration
import wallet_v1_activation as activation


class DummyRedis:
    def exists(self, _k):
        return False

    def setex(self, _k, _ttl, _v):
        return True


def _app(tmp_path):
    app = Flask(__name__)
    register_wallet_v1_routes(app, redis_client=DummyRedis(), node_role="master", read_only=False, sqlite_path=str(tmp_path / "ledger.sqlite3"))
    return app


def _tx(addr):
    return {
        "from": addr,
        "to": "THR" + "B" * 40,
        "amount": 1,
        "token": "THR",
        "nonce": "n-1",
        "timestamp": 1710000000,
        "signature": "00",
        "publicKey": "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798",
    }


def test_wrong_legacy_proof_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(migration.server_module, "load_json", lambda p, d: [{"thr_address": "THROLD", "send_seed_hash": "abc"}] if p == migration.server_module.PLEDGE_CHAIN else d, raising=False)
    monkeypatch.setattr(migration.server_module, "has_pledge_access", lambda a: True, raising=False)
    monkeypatch.setattr(migration.server_module, "is_wallet_whitelisted", lambda a: False, raising=False)
    res = _app(tmp_path).test_client().post("/api/v1/wallet/migrate", json={
        "old_thr_address": "THROLD", "legacy_secret": "bad", "new_compressed_public_key": "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
    })
    assert res.status_code == 400


def test_correct_proof_accepts_and_derives(monkeypatch, tmp_path):
    import hashlib
    secret = "secret123"
    seed_hash = hashlib.sha256(secret.encode()).hexdigest()
    fake_store = {
        "migrations": {"migrations": {}, "index_new": {}},
        "pledge": [{"thr_address": "THROLD", "send_seed_hash": seed_hash}],
        "ledger": {"THROLD": 12.5},
        "chain": [],
        "txlog": [],
    }
    def fake_load(path, default):
        if path == migration.server_module.PLEDGE_CHAIN:
            return fake_store["pledge"]
        if path == migration.server_module.LEDGER_FILE:
            return dict(fake_store["ledger"])
        if path == migration.server_module.CHAIN_FILE:
            return list(fake_store["chain"])
        if path == migration.MIGRATION_FILE:
            return fake_store["migrations"]
        return default
    monkeypatch.setattr(migration.server_module, "load_json", fake_load, raising=False)
    saved = {}
    def fake_save(path, data):
        saved[path] = data
        if path == migration.server_module.LEDGER_FILE:
            fake_store["ledger"] = dict(data)
        elif path == migration.server_module.CHAIN_FILE:
            fake_store["chain"] = list(data)
        elif path == migration.MIGRATION_FILE:
            fake_store["migrations"] = dict(data)
    monkeypatch.setattr(migration.server_module, "save_json", fake_save, raising=False)
    monkeypatch.setattr(migration.server_module, "persist_normalized_tx", lambda tx: fake_store["txlog"].append(dict(tx)), raising=False)
    monkeypatch.setattr(migration.server_module, "has_pledge_access", lambda a: True, raising=False)
    monkeypatch.setattr(migration.server_module, "is_wallet_whitelisted", lambda a: False, raising=False)

    res = _app(tmp_path).test_client().post("/api/v1/wallet/migrate", json={
        "old_thr_address": "THROLD", "legacy_secret": secret, "new_compressed_public_key": "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
    })
    assert res.status_code == 200
    assert res.get_json()["ok"] is True
    new_addr = res.get_json()["migration"]["new_v1_address"]
    assert new_addr.startswith("THR")
    assert fake_store["ledger"]["THROLD"] == 0.0
    assert fake_store["ledger"][new_addr] == 12.5
    assert fake_store["chain"][-1]["type"] == "wallet_v1_migration"
    assert fake_store["chain"][-1]["fee_burned"] == 0.0
    assert fake_store["txlog"][-1]["type"] == "wallet_v1_migration"


def test_already_migrated_rejected(monkeypatch):
    monkeypatch.setattr(migration.server_module, "load_json", lambda p, d: {"migrations": {"THROLD": {}}, "index_new": {}} if p == migration.MIGRATION_FILE else [], raising=False)
    monkeypatch.setattr(migration.server_module, "has_pledge_access", lambda a: True, raising=False)
    monkeypatch.setattr(migration.server_module, "is_wallet_whitelisted", lambda a: True, raising=False)
    try:
        migration.migrate_legacy_address("THROLD", "x", "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798")
        assert False
    except ValueError as e:
        assert str(e) == "already_migrated"


def test_migrated_old_cannot_write_and_new_can(monkeypatch, tmp_path):
    monkeypatch.setattr(wallet_v1_prod, "verify_signed_transaction_core", lambda _tx: (True, ""))
    monkeypatch.setattr(activation, "resolve_migration", lambda a: {"kind": "old"} if a == "THROLD" else ({"kind": "new"} if a == "THRNEW" else None))
    app = _app(tmp_path)
    r_old = app.test_client().post("/api/v1/tx/send", json={"tx": _tx("THROLD")})
    assert r_old.status_code == 403

    r_new = app.test_client().post("/api/v1/tx/send", json={"tx": _tx("THRNEW")})
    assert r_new.status_code == 200


def test_no_secrets_in_migration_response(monkeypatch, tmp_path):
    monkeypatch.setattr(migration, "migrate_legacy_address", lambda *_a, **_k: {
        "old_address": "THR1", "new_v1_address": "THR2", "migrated_at": 1, "old_read_only": True,
        "legacy_secret": "never"
    })
    res = _app(tmp_path).test_client().post("/api/v1/wallet/migrate", json={})
    body = res.get_json()
    assert "legacy_secret" not in str(body)
