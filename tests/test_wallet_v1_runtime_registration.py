import os
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


def test_tx_send_calls_execution_adapter(monkeypatch):
    app = _app(monkeypatch)
    monkeypatch.setattr(wallet_v1_prod, 'NODE_ROLE', 'master')
    monkeypatch.setattr(wallet_v1_prod, 'READ_ONLY', False)
    monkeypatch.setattr(wallet_v1_prod, 'verify_signed_transaction_core', lambda _tx: (True, ''))
    monkeypatch.setattr(wallet_v1_handlers, 'require_active_thr_address', lambda _a: True)

    called = {}
    def _exec(tx):
        called['nonce'] = tx.get('nonce')
        return ({'ok': True}, 200, {'Content-Type': 'application/json'})

    monkeypatch.setattr(wallet_v1_handlers, 'execute_verified_signed_transfer', _exec)
    r = app.test_client().post('/api/v1/tx/send', json={'tx': {'from':'A','to':'B','amount':1,'token':'THR','nonce':'n','timestamp':1}})
    assert r.status_code == 200
    assert called['nonce'] == 'n'


def test_repair_route_requires_admin_token(monkeypatch):
    app = _app(monkeypatch)
    monkeypatch.setenv('WALLET_V1_REPAIR_TOKEN', 'secret')
    r = app.test_client().post('/api/v1/wallet/migration/repair', json={'old_address': 'A', 'new_v1_address': 'B'})
    assert r.status_code == 403
