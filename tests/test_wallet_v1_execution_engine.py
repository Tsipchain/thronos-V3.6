import os
import sys

from flask import Flask

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from wallet_v1_blueprint import register_wallet_v1_routes
import wallet_v1_execution_adapter as adapter
import wallet_v1_production_final as wallet_v1_prod


class DummyRedis:
    def __init__(self):
        self.keys = set()

    def exists(self, key):
        return key in self.keys

    def setex(self, key, _ttl, _val):
        self.keys.add(key)
        return True


class FakeServerState:
    def __init__(self):
        self.ledger = {}
        self.chain = []
        self.txlog = []



def install_fake_server(monkeypatch, state):
    monkeypatch.setattr(adapter.server_module, "LEDGER_FILE", "ledger.json", raising=False)
    monkeypatch.setattr(adapter.server_module, "CHAIN_FILE", "chain.json", raising=False)

    def load_json(path, default):
        if path == "ledger.json":
            return dict(state.ledger)
        if path == "chain.json":
            return list(state.chain)
        return default

    def save_json(path, data):
        if path == "ledger.json":
            state.ledger = dict(data)
        elif path == "chain.json":
            state.chain = list(data)

    monkeypatch.setattr(adapter.server_module, "load_json", load_json)
    monkeypatch.setattr(adapter.server_module, "save_json", save_json)
    monkeypatch.setattr(adapter.server_module, "persist_normalized_tx", lambda tx: state.txlog.append(dict(tx)))
    monkeypatch.setattr(adapter.server_module, "split_and_credit_fee", lambda fee, source="": {"fee_total": fee, "source": source})
    monkeypatch.setattr(adapter.server_module, "calculate_fixed_burn_fee", lambda amount, speed="fast": round(max(0.001, float(amount) * 0.001), 6))
    monkeypatch.setattr(adapter.server_module, "validate_thr_address", lambda a: isinstance(a, str) and a.startswith("THR") and len(a) == 43)



def test_valid_signed_tx_executes_and_persists(monkeypatch, tmp_path):
    state = FakeServerState()
    from_addr = "THR" + "A" * 40
    to_addr = "THR" + "B" * 40
    state.ledger[from_addr] = 100.0
    install_fake_server(monkeypatch, state)
    monkeypatch.setattr(wallet_v1_prod, "verify_signed_transaction_core", lambda _tx: (True, ""))

    app = Flask(__name__)
    @app.get("/api/transfers")
    def api_transfers():
        return {"ok": True, "transfers": list(state.txlog)}, 200

    register_wallet_v1_routes(app, redis_client=DummyRedis(), node_role="master", read_only=False, sqlite_path=str(tmp_path / "ledger.sqlite3"))
    client = app.test_client()

    res = client.post("/api/v1/tx/send", json={"tx": {
        "from": from_addr,
        "to": to_addr,
        "amount": 10,
        "token": "THR",
        "nonce": "n1",
        "timestamp": 9999999999,
        "signature": "00",
        "publicKey": "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798",
    }})
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert state.txlog, "transfer should be persisted to normalized tx log"
    transfers = client.get("/api/transfers")
    assert transfers.status_code == 200
    assert len(transfers.get_json()["transfers"]) == 1


def test_insufficient_funds_rejected(monkeypatch):
    state = FakeServerState()
    from_addr = "THR" + "C" * 40
    to_addr = "THR" + "D" * 40
    state.ledger[from_addr] = 1.0
    install_fake_server(monkeypatch, state)
    ok, payload, status = adapter.execute_verified_signed_transfer({
        "from": from_addr, "to": to_addr, "amount": 10, "nonce": "n2", "token": "THR", "speed": "fast"
    })
    assert ok is False
    assert status == 400
    assert payload["error"] == "insufficient_balance"


def test_nonce_replay_rejected(monkeypatch, tmp_path):
    redis = DummyRedis()
    state = FakeServerState()
    state.ledger["THR" + "E" * 40] = 100.0
    install_fake_server(monkeypatch, state)
    app = Flask(__name__)
    register_wallet_v1_routes(app, redis_client=redis, node_role="master", read_only=False, sqlite_path=str(tmp_path / "ledger.sqlite3"))
    ok1, _ = wallet_v1_prod.check_nonce_redis("THR" + "E" * 40, "same-nonce")
    ok2, err2 = wallet_v1_prod.check_nonce_redis("THR" + "E" * 40, "same-nonce")
    assert ok1 is True
    assert ok2 is False
    assert err2 == "nonce_replay_detected"


def test_replica_write_still_503(tmp_path):
    app = Flask(__name__)
    register_wallet_v1_routes(app, redis_client=DummyRedis(), node_role="replica", read_only=True, sqlite_path=str(tmp_path / "ignored.sqlite3"))
    r = app.test_client().post("/api/v1/tx/send", json={"tx": {"from": "THR"+"1"*40, "to": "THR"+"2"*40, "amount": 1, "nonce": "n", "timestamp": 1, "signature": "x", "publicKey": "y"}})
    assert r.status_code == 503
