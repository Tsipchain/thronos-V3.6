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
import wallet_v1_handlers as handlers


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
    monkeypatch.setattr(migration.server_module, "load_json", lambda p, d: [{"thr_address": "THROLD", "send_seed_hash": seed_hash}] if p == migration.server_module.PLEDGE_CHAIN else {"migrations": {}, "index_new": {}}, raising=False)
    saved = {}
    monkeypatch.setattr(migration.server_module, "save_json", lambda p, d: saved.update({"data": d}), raising=False)
    monkeypatch.setattr(migration.server_module, "has_pledge_access", lambda a: True, raising=False)
    monkeypatch.setattr(migration.server_module, "is_wallet_whitelisted", lambda a: False, raising=False)

    res = _app(tmp_path).test_client().post("/api/v1/wallet/migrate", json={
        "old_thr_address": "THROLD", "legacy_secret": secret, "new_compressed_public_key": "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
    })
    assert res.status_code == 200
    assert res.get_json()["ok"] is True
    assert "new_v1_address" in res.get_json()["migration"]


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
    called = {"hit": False}
    monkeypatch.setattr(handlers, "execute_verified_signed_transfer", lambda _tx: (called.update({"hit": True}) or True, {"ok": True}, 200))

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
