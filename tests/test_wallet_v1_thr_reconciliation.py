from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OLD = "THR79ca94a7eb70a6aa99d12d7fdb01446ef246301a"
NEW = "THR683318ACF083723B3EDFE6C0A30AD62670F00353"
CORE = "THRa60e1cef9826da16a9b9c12f907614dacf49f74b"


def _install_reconciliation_fixtures(monkeypatch, *, ledger=None, txs=None, pools=None, migration=None):
    import server
    import wallet_v1_migration

    ledger_data = dict(ledger or {OLD: 0.0, NEW: 6.4001, CORE: 999.0})
    monkeypatch.setattr(server, "load_json", lambda path, default=None: ledger_data.copy() if path == server.LEDGER_FILE else (default if default is not None else []))
    monkeypatch.setattr(server, "_tx_feed", lambda **_kwargs: list(txs or []))
    monkeypatch.setattr(server, "load_pools", lambda: list(pools or []))
    monkeypatch.setattr(wallet_v1_migration, "_load_map", lambda: {OLD: dict(migration or {
        "new_v1_address": NEW,
        "status": "repaired",
        "moved_thr_amount": 0.0,
        "migrated_thr_amount": 0.0,
        "old_pre_migration_thr_balance": 42.0,
        "repair_tx_id": "repair:old:1",
        "assets_migrated": True,
    })})
    return server.app.test_client(), ledger_data


def test_thr_reconciliation_detects_old_pre_balance_with_zero_moved(monkeypatch):
    client, _ledger = _install_reconciliation_fixtures(monkeypatch)
    res = client.get(f"/api/v1/wallet/thr-reconciliation?old_address={OLD}&new_address={NEW}")
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["old_current_thr_balance"] == 0.0
    assert body["new_current_thr_balance"] == 6.4001
    assert body["old_pre_migration_thr_balance_if_available"] == 42.0
    assert body["moved_thr_amount_from_repair_records"] == 0.0
    assert "old_pre_migration_thr_present_but_no_thr_moved" in body["mismatch_flags"]
    assert body["suspected_missing_thr_amount"] == 42.0


def test_thr_reconciliation_counts_pending_locked_and_burned_separately(monkeypatch):
    txs = [
        {"type": "transfer", "from": OLD, "to": "THR" + "B" * 40, "amount": 3.0, "fee_burned": 0.1, "status": "confirmed"},
        {"type": "transfer", "from": "THR" + "C" * 40, "to": OLD, "amount": 5.0, "status": "pending"},
        {"type": "transfer", "from": NEW, "to": "THR" + "D" * 40, "amount": 1.0, "fee_burned": 0.02, "status": "confirmed"},
    ]
    pools = [{
        "id": "pool1",
        "token_a": "THR",
        "token_b": "7CEB",
        "reserves_a": 100.0,
        "reserves_b": 200.0,
        "total_shares": 10.0,
        "providers": {OLD: 2.0, NEW: 1.0},
    }]
    client, _ledger = _install_reconciliation_fixtures(monkeypatch, txs=txs, pools=pools, migration={
        "new_v1_address": NEW,
        "status": "repaired",
        "old_pre_migration_thr_balance": 42.0,
        "moved_thr_amount": 0.0,
    })
    body = client.get(f"/api/v1/wallet/thr-reconciliation?old_address={OLD}&new_address={NEW}").get_json()
    assert body["confirmed_outgoing_thr_old"] == 3.0
    assert body["pending_incoming_thr_old"] == 5.0
    assert body["pool_locked_thr_old"] == 20.0
    assert body["pool_locked_thr_new"] == 10.0
    assert body["fee_burned_from_old"] == 0.1
    assert body["fee_burned_from_new"] == 0.02
    assert body["total_burn_related_to_wallets"] == 0.12
    assert "thr_locked_in_liquidity_positions" in body["mismatch_flags"]
    assert "wallet_related_fee_burn_detected" in body["mismatch_flags"]


def test_thr_reconciliation_reward_totals_ignore_unrelated_core_miner(monkeypatch):
    txs = [
        {"type": "mining_reward", "miner": CORE, "to": OLD, "amount": 2.5, "status": "confirmed"},
        {"type": "mining_reward", "miner": CORE, "to": CORE, "amount": 99.0, "status": "confirmed"},
        {"type": "pool_reward", "wallet": NEW, "amount": 1.25, "status": "confirmed"},
        {"type": "ai_reward", "to": OLD, "amount": 0.75, "status": "confirmed"},
    ]
    client, _ledger = _install_reconciliation_fixtures(monkeypatch, txs=txs)
    body = client.get(f"/api/v1/wallet/thr-reconciliation?old_address={OLD}&new_address={NEW}").get_json()
    assert body["mining_rewards_to_old"] == 2.5
    assert body["mining_rewards_to_new"] == 0.0
    assert body["pool_rewards_to_new"] == 1.25
    assert body["ai_rewards_to_old"] == 0.75
    assert body["confirmed_incoming_thr_old"] == 3.25
    assert body["confirmed_incoming_thr_new"] == 1.25


def test_thr_reconciliation_diagnostics_endpoint_does_not_mutate(monkeypatch):
    client, ledger = _install_reconciliation_fixtures(monkeypatch)
    import server
    calls = []
    monkeypatch.setattr(server, "save_json", lambda *args, **kwargs: calls.append((args, kwargs)))
    before = ledger.copy()
    res = client.get(f"/api/v1/wallet/thr-reconciliation?old_address={OLD}&new_address={NEW}")
    assert res.status_code == 200
    assert ledger == before
    assert calls == []


def test_thr_reconciliation_dry_run_repair_does_not_change_balances(monkeypatch):
    client, ledger = _install_reconciliation_fixtures(monkeypatch)
    import server
    calls = []
    monkeypatch.setattr(server, "save_json", lambda *args, **kwargs: calls.append((args, kwargs)))
    res = client.post(
        "/api/v1/wallet/thr-reconciliation/repair",
        json={"old_address": OLD, "new_address": NEW, "dry_run": True, "secret": server.ADMIN_SECRET},
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["dry_run"] is True
    assert body["mutation_performed"] is False
    assert body["proposed_restore_amount"] == 42.0
    assert ledger[OLD] == 0.0
    assert ledger[NEW] == 6.4001
    assert calls == []


def test_core_miner_wallet_ignored_unless_explicitly_passed(monkeypatch):
    txs = [{"type": "mining_reward", "miner": CORE, "to": CORE, "amount": 99.0, "status": "confirmed"}]
    client, _ledger = _install_reconciliation_fixtures(monkeypatch, txs=txs)
    body = client.get(f"/api/v1/wallet/thr-reconciliation?old_address={OLD}&new_address={NEW}").get_json()
    assert body["mining_rewards_to_old"] == 0.0
    assert body["mining_rewards_to_new"] == 0.0
    assert "core_miner_wallet_explicitly_requested" not in body["mismatch_flags"]

    explicit = client.get(f"/api/v1/wallet/thr-reconciliation?old_address={CORE}&new_address={NEW}").get_json()
    assert "core_miner_wallet_explicitly_requested" in explicit["mismatch_flags"]
