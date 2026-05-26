import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask import Flask
import wallet_v1_blueprint
import wallet_v1_handlers
import wallet_v1_production_final as wallet_v1_prod


def _app(monkeypatch):
    app = Flask(__name__)
    monkeypatch.setattr(wallet_v1_prod, 'init_wallet_v1', lambda *a, **k: None)
    wallet_v1_blueprint.register_wallet_v1_routes(app, redis_client=object(), node_role='master', read_only=False, sqlite_path='/tmp/db.sqlite')
    return app


def test_tx_send_still_executes(monkeypatch):
    app = _app(monkeypatch)
    monkeypatch.setattr(wallet_v1_prod, 'NODE_ROLE', 'master')
    monkeypatch.setattr(wallet_v1_prod, 'READ_ONLY', False)
    monkeypatch.setattr(wallet_v1_prod, 'verify_signed_transaction_core', lambda _tx: (True, ''))
    monkeypatch.setattr(wallet_v1_handlers, 'require_active_thr_address', lambda _a: True)
    called = {}
    monkeypatch.setattr(wallet_v1_handlers, 'execute_verified_signed_transfer', lambda tx: (called.setdefault('n', tx.get('nonce')) and ({'ok': True}, 200, {'Content-Type': 'application/json'})))
    r = app.test_client().post('/api/v1/tx/send', json={'tx': {'from':'A','to':'B','amount':1,'token':'THR','nonce':'n','timestamp':1}})
    assert r.status_code == 200
    assert called['n'] == 'n'


def test_repair_requires_token(monkeypatch):
    app = _app(monkeypatch)
    monkeypatch.setenv('WALLET_V1_REPAIR_TOKEN', 'secret')
    r = app.test_client().post('/api/v1/wallet/migration/repair', json={'old_address':'A','new_v1_address':'B'})
    assert r.status_code == 403


def test_status_requires_token(monkeypatch):
    app = _app(monkeypatch)
    monkeypatch.setenv('WALLET_V1_REPAIR_TOKEN', 'secret')
    r = app.test_client().post('/api/v1/wallet/migration/status', json={'old_address':'A'})
    assert r.status_code == 403


def test_status_returns_record_and_no_mutation(monkeypatch):
    app = _app(monkeypatch)
    monkeypatch.setenv('WALLET_V1_REPAIR_TOKEN', 'secret')
    rec = {
        'old_address': 'OLD',
        'new_v1_address': 'NEW',
        'status': 'completed',
        'admission_only': False,
        'assets_migrated': True,
        'migration_tx': {'tx_id': 'm1', 'legacy_secret': 'x', 'privateKey': 'y'}
    }
    monkeypatch.setattr(wallet_v1_handlers, 'resolve_migration', lambda old: rec if old == 'OLD' else None)
    c = app.test_client()
    r = c.post('/api/v1/wallet/migration/status', json={'old_address':'OLD'}, headers={'X-Repair-Token':'secret'})
    assert r.status_code == 200
    body = r.get_json()
    assert body['new_v1_address'] == 'NEW'
    assert body['migration_tx'] == 'm1'
    assert 'repair_tx_id' in body
    assert 'moved_token_count' in body
    assert 'remaining_old_token_count' in body
    assert 'ecosystem_bindings_repaired' in body
    assert 'music_bindings_repaired' in body
    dumped = str(body)
    assert 'legacy_secret' not in dumped
    assert 'privateKey' not in dumped


def test_status_not_found(monkeypatch):
    app = _app(monkeypatch)
    monkeypatch.setenv('WALLET_V1_REPAIR_TOKEN', 'secret')
    monkeypatch.setattr(wallet_v1_handlers, 'resolve_migration', lambda _old: None)
    r = app.test_client().post('/api/v1/wallet/migration/status', json={'old_address':'MISS'}, headers={'X-Repair-Token':'secret'})
    assert r.status_code == 404
    assert r.get_json().get('error') == 'migration_record_not_found'
