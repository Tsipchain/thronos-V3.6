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

FIRST = "THR5E055A72DC04C10C18C3F74D17AB34CEE4A9BA24"


def test_v1_split_diagnostics_detects_first_wallet_current_zero_and_old_lp(monkeypatch):
    import server
    txs = [
        {"type": "wallet_v1_migration", "tx_id": "MIGRATE-1779560081-46301a-A9BA24", "old_address": OLD, "new_v1_address": FIRST, "migrated_thr_amount": 14041.167132, "status": "confirmed"},
        {"type": "wallet_v1_migration", "tx_id": "MIGRATE-1779560089-46301a-F00353", "old_address": OLD, "new_v1_address": NEW, "migrated_thr_amount": 0.0, "status": "confirmed"},
    ]
    pools = [{"id": "jam-thr", "token_a": "JAM", "token_b": "THR", "reserves_a": 1000, "reserves_b": 514.969064, "total_shares": 10, "providers": {OLD: 10}}]
    client, _ledger = _install_reconciliation_fixtures(
        monkeypatch,
        ledger={OLD: 0.0, NEW: 6.4001, FIRST: 14041.167132},
        txs=txs,
        pools=pools,
        migration={"new_v1_address": NEW, "status": "repaired", "moved_thr_amount": 0.0},
    )
    body = client.get(f"/api/v1/wallet/v1-split-diagnostics?old_address={OLD}&current_v1_address={NEW}").get_json()
    assert body["ok"] is True
    assert body["detected_first_v1_thr_wallets"] == [FIRST]
    assert body["first_v1_wallet_balances"][FIRST] == 14041.167132
    assert body["current_v1_balance"] == 6.4001
    assert any(ev["new_v1_address"] == NEW and ev["migrated_thr_amount"] == 0.0 for ev in body["migrated_thr_events"])
    assert body["old_locked_thr_total"] == 514.969064
    assert body["current_locked_thr_total"] == 0.0
    assert body["old_liquidity_positions"][0]["pool_id"] == "jam-thr"


def test_liquidity_provider_migration_dry_run_does_not_mutate(monkeypatch):
    import server
    pools = [{"id": "p1", "token_a": "THR", "token_b": "7CEB", "reserves_a": 100, "reserves_b": 200, "total_shares": 10, "providers": {OLD: 2}}]
    _client, ledger = _install_reconciliation_fixtures(monkeypatch, ledger={OLD: 0.0, NEW: 6.4001}, pools=pools)
    saved = []
    monkeypatch.setattr(server, "save_pools", lambda p: saved.append(p))
    res = server.app.test_client().post(
        "/api/v1/wallet/liquidity-provider-migration",
        json={"old_address": OLD, "new_v1_address": NEW, "dry_run": True, "secret": server.ADMIN_SECRET},
    )
    body = res.get_json()
    assert res.status_code == 200
    assert body["mutation_performed"] is False
    assert body["affected_pools"][0]["pool_id"] == "p1"
    assert pools[0]["providers"] == {OLD: 2}
    assert ledger[NEW] == 6.4001
    assert saved == []


def test_liquidity_provider_real_mutation_requires_admin_token(monkeypatch):
    import server
    _client, _ledger = _install_reconciliation_fixtures(monkeypatch, pools=[{"id": "p1", "token_a": "THR", "token_b": "7CEB", "reserves_a": 100, "reserves_b": 200, "total_shares": 10, "providers": {OLD: 2}}])
    res = server.app.test_client().post(
        "/api/v1/wallet/liquidity-provider-migration",
        json={"old_address": OLD, "new_v1_address": NEW, "dry_run": False},
    )
    assert res.status_code == 401
    assert res.get_json()["error"] == "admin_auth_required"


def test_liquidity_provider_real_migration_is_idempotent_and_preserves_ledger(monkeypatch):
    import server
    state = {"pools": [{"id": "p1", "token_a": "THR", "token_b": "7CEB", "reserves_a": 100, "reserves_b": 200, "total_shares": 10, "providers": {OLD: 2, NEW: 1}}]}
    ledger = {OLD: 0.0, NEW: 6.4001}
    import wallet_v1_migration
    monkeypatch.setattr(server, "load_json", lambda path, default=None: ledger.copy() if path == server.LEDGER_FILE else (default if default is not None else []))
    monkeypatch.setattr(server, "_tx_feed", lambda **_kwargs: [])
    monkeypatch.setattr(server, "load_pools", lambda: state["pools"])
    monkeypatch.setattr(server, "save_pools", lambda pools: state.update({"pools": pools}))
    monkeypatch.setattr(wallet_v1_migration, "_load_map", lambda: {})

    client = server.app.test_client()
    first = client.post(
        "/api/v1/wallet/liquidity-provider-migration",
        json={"old_address": OLD, "new_v1_address": NEW, "dry_run": False, "secret": server.ADMIN_SECRET},
    )
    assert first.status_code == 200
    assert first.get_json()["mutation_performed"] is True
    assert state["pools"][0]["total_shares"] == 10
    assert state["pools"][0]["reserves_a"] == 100
    assert state["pools"][0]["reserves_b"] == 200
    assert state["pools"][0]["providers"] == {NEW: 3.0}
    assert ledger == {OLD: 0.0, NEW: 6.4001}

    second = client.post(
        "/api/v1/wallet/liquidity-provider-migration",
        json={"old_address": OLD, "new_v1_address": NEW, "dry_run": False, "secret": server.ADMIN_SECRET},
    )
    assert second.status_code == 200
    assert second.get_json()["mutation_performed"] is False
    assert state["pools"][0]["providers"] == {NEW: 3.0}


def test_liquidity_provider_migration_blocks_core_miner_wallet(monkeypatch):
    import server
    _client, _ledger = _install_reconciliation_fixtures(monkeypatch, pools=[{"id": "p1", "token_a": "THR", "token_b": "7CEB", "reserves_a": 100, "reserves_b": 200, "total_shares": 10, "providers": {CORE: 2}}])
    res = server.app.test_client().post(
        "/api/v1/wallet/liquidity-provider-migration",
        json={"old_address": CORE, "new_v1_address": NEW, "dry_run": False, "secret": server.ADMIN_SECRET},
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "core_miner_wallet_not_allowed"


def test_v1_split_consolidation_requires_proven_first_wallet(monkeypatch):
    import server
    txs = [{"type": "wallet_v1_migration", "tx_id": "MIGRATE-1", "old_address": OLD, "new_v1_address": FIRST, "migrated_thr_amount": 14041.167132}]
    _client, _ledger = _install_reconciliation_fixtures(monkeypatch, ledger={FIRST: 14041.167132, NEW: 6.4001}, txs=txs)
    res = server.app.test_client().post(
        "/api/v1/wallet/v1-split-consolidation",
        json={"first_v1_wallet": "THR" + "9" * 40, "current_v1_wallet": NEW, "dry_run": True, "secret": server.ADMIN_SECRET},
    )
    assert res.status_code == 404
    assert res.get_json()["error"] == "first_v1_wallet_not_proven_by_migration_tx"

    res = server.app.test_client().post(
        "/api/v1/wallet/v1-split-consolidation",
        json={"first_v1_wallet": FIRST, "current_v1_wallet": NEW, "dry_run": True, "secret": server.ADMIN_SECRET},
    )
    body = res.get_json()
    assert res.status_code == 200
    assert body["mutation_performed"] is False
    assert body["first_v1_balance"] == 14041.167132
    assert body["proven_by_migration_event"]["new_v1_address"] == FIRST
