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


def test_v1_split_diagnostics_detects_first_v1_wallet_with_thr(monkeypatch):
    """Test that split diagnostics detect the first V1 wallet that received THR."""
    first_v1 = "THR5E055A72DC04C10C18C3F74D17AB34CEE4A9BA24"
    migration_txs = [
        {
            "type": "wallet_v1_migration",
            "tx_id": "MIGRATE-1779560081-46301a-A9BA24",
            "old_address": OLD,
            "new_v1_address": first_v1,
            "migrated_thr_amount": 14041.167132,
            "status": "confirmed",
        },
        {
            "type": "wallet_v1_migration",
            "tx_id": "MIGRATE-1779560089-46301a-F00353",
            "old_address": OLD,
            "new_v1_address": NEW,
            "migrated_thr_amount": 0.0,
            "status": "confirmed",
        },
    ]
    ledger = {OLD: 0.0, first_v1: 14041.167132, NEW: 6.4001}
    client, _ledger = _install_reconciliation_fixtures(monkeypatch, ledger=ledger, txs=migration_txs)

    res = client.get(f"/api/v1/wallet/v1-split-diagnostics?old_address={OLD}&current_v1_address={NEW}")
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["old_address"] == OLD
    assert body["current_v1_address"] == NEW
    assert first_v1 in body["detected_first_v1_thr_wallets"]
    assert body["first_v1_wallet_balances"][first_v1] == 14041.167132
    assert body["current_v1_balance"] == 6.4001
    assert len(body["migrated_thr_events"]) == 2


def test_v1_split_diagnostics_detects_old_liquidity_positions(monkeypatch):
    """Test that split diagnostics detect liquidity positions on old wallet."""
    pools = [{
        "id": "pool1",
        "token_a": "THR",
        "token_b": "7CEB",
        "reserves_a": 1000.0,
        "reserves_b": 2000.0,
        "total_shares": 10.0,
        "providers": {OLD: 2.0, NEW: 1.0},
    }]
    client, _ledger = _install_reconciliation_fixtures(monkeypatch, pools=pools)

    res = client.get(f"/api/v1/wallet/v1-split-diagnostics?old_address={OLD}&current_v1_address={NEW}")
    assert res.status_code == 200
    body = res.get_json()
    assert body["old_locked_thr_total"] == 200.0  # 2/10 * 1000 THR
    assert body["current_locked_thr_total"] == 100.0  # 1/10 * 1000 THR
    assert len(body["old_liquidity_positions"]) == 1
    assert body["old_liquidity_positions"][0]["pool_id"] == "pool1"
    assert body["old_liquidity_positions"][0]["locked_thr"] == 200.0


def test_liquidity_provider_migration_dry_run_returns_proposal(monkeypatch):
    """Test that LP migration dry-run returns proposal without mutations."""
    pools = [{
        "id": "pool1",
        "token_a": "THR",
        "token_b": "7CEB",
        "reserves_a": 1000.0,
        "reserves_b": 2000.0,
        "total_shares": 10.0,
        "providers": {OLD: 2.0, NEW: 1.0},
    }]
    client, _ledger = _install_reconciliation_fixtures(monkeypatch, pools=pools)
    import server
    calls = []
    monkeypatch.setattr(server, "save_pools", lambda _pools: calls.append(_pools))

    pools_before = [p.copy() for p in pools]
    res = client.post(
        "/api/v1/wallet/liquidity-provider-migration",
        json={"old_address": OLD, "new_v1_address": NEW, "dry_run": True, "secret": server.ADMIN_SECRET},
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["dry_run"] is True
    assert body["mutation_performed"] is False
    assert len(body["affected_pools"]) == 1
    assert body["affected_pools"][0]["pool_id"] == "pool1"
    assert body["affected_pools"][0]["user_shares"] == 2.0
    assert calls == []  # save_pools should not be called for dry_run


def test_liquidity_provider_migration_real_mutation_moves_shares(monkeypatch):
    """Test that LP migration with dry_run=false moves provider ownership."""
    pools = [{
        "id": "pool1",
        "token_a": "THR",
        "token_b": "7CEB",
        "reserves_a": 1000.0,
        "reserves_b": 2000.0,
        "total_shares": 10.0,
        "providers": {OLD: 2.0, NEW: 0.0},
    }]
    client, _ledger = _install_reconciliation_fixtures(monkeypatch, pools=pools)
    import server

    captured_pools = []

    def capture_save_pools(new_pools):
        captured_pools.append(new_pools)

    monkeypatch.setattr(server, "save_pools", capture_save_pools)

    res = client.post(
        "/api/v1/wallet/liquidity-provider-migration",
        json={"old_address": OLD, "new_v1_address": NEW, "dry_run": False, "secret": server.ADMIN_SECRET},
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["mutation_performed"] is True
    assert body["dry_run"] is False

    # Check that save_pools was called and pools were modified
    assert len(captured_pools) == 1
    updated_pool = captured_pools[0][0]
    assert OLD not in updated_pool["providers"]
    assert updated_pool["providers"][NEW] == 2.0
    assert updated_pool["total_shares"] == 10.0
    assert updated_pool["reserves_a"] == 1000.0  # Reserves unchanged


def test_liquidity_provider_migration_is_idempotent(monkeypatch):
    """Test that LP migration is idempotent."""
    pools = [{
        "id": "pool1",
        "token_a": "THR",
        "token_b": "7CEB",
        "reserves_a": 1000.0,
        "reserves_b": 2000.0,
        "total_shares": 10.0,
        "providers": {NEW: 2.0},  # Already migrated
    }]
    client, _ledger = _install_reconciliation_fixtures(monkeypatch, pools=pools)

    res = client.get(f"/api/v1/wallet/v1-split-diagnostics?old_address={OLD}&current_v1_address={NEW}")
    assert res.status_code == 200
    body = res.get_json()
    assert len(body["old_liquidity_positions"]) == 0


def test_liquidity_provider_migration_blocks_core_miner_wallet(monkeypatch):
    """Test that LP migration blocks core/miner wallet."""
    pools = [{
        "id": "pool1",
        "token_a": "THR",
        "token_b": "7CEB",
        "reserves_a": 1000.0,
        "reserves_b": 2000.0,
        "total_shares": 10.0,
        "providers": {CORE: 2.0},
    }]
    client, _ledger = _install_reconciliation_fixtures(monkeypatch, pools=pools)
    import server

    res = client.post(
        "/api/v1/wallet/liquidity-provider-migration",
        json={"old_address": CORE, "new_v1_address": NEW, "dry_run": True, "secret": server.ADMIN_SECRET},
    )
    assert res.status_code == 400
    body = res.get_json()
    assert "core_miner_wallet" in body["error"]


def test_v1_split_consolidation_requires_proof_of_migration(monkeypatch):
    """Test that consolidation requires proof of migration."""
    first_v1 = "THR5E055A72DC04C10C18C3F74D17AB34CEE4A9BA24"
    migration_txs = [
        {
            "type": "wallet_v1_migration",
            "old_address": OLD,
            "new_v1_address": first_v1,
            "migrated_thr_amount": 14041.167132,
            "status": "confirmed",
        },
    ]
    client, _ledger = _install_reconciliation_fixtures(monkeypatch, txs=migration_txs)
    import server

    res = client.post(
        "/api/v1/wallet/v1-split-consolidation",
        json={"first_v1_wallet": first_v1, "current_v1_wallet": NEW, "dry_run": True, "secret": server.ADMIN_SECRET},
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["proof"]["migrated_thr_amount"] == 14041.167132
    assert body["proof"]["migration_source_old_address"] == OLD


def test_v1_split_consolidation_rejects_unproven_wallet(monkeypatch):
    """Test that consolidation rejects wallet without migration proof."""
    fake_v1 = "THRFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF"
    client, _ledger = _install_reconciliation_fixtures(monkeypatch)
    import server

    res = client.post(
        "/api/v1/wallet/v1-split-consolidation",
        json={"first_v1_wallet": fake_v1, "current_v1_wallet": NEW, "dry_run": True, "secret": server.ADMIN_SECRET},
    )
    assert res.status_code == 400
    body = res.get_json()
    assert body["ok"] is False
    assert "no_migration_proof_found" in body["error"]


def test_v1_split_consolidation_dry_run_only(monkeypatch):
    """Test that consolidation is dry-run only and returns proposal."""
    first_v1 = "THR5E055A72DC04C10C18C3F74D17AB34CEE4A9BA24"
    migration_txs = [
        {
            "type": "wallet_v1_migration",
            "old_address": OLD,
            "new_v1_address": first_v1,
            "migrated_thr_amount": 14041.167132,
            "status": "confirmed",
        },
    ]
    client, _ledger = _install_reconciliation_fixtures(monkeypatch, txs=migration_txs)
    import server
    calls = []
    monkeypatch.setattr(server, "save_json", lambda *args, **kwargs: calls.append((args, kwargs)))

    res = client.post(
        "/api/v1/wallet/v1-split-consolidation",
        json={"first_v1_wallet": first_v1, "current_v1_wallet": NEW, "dry_run": True, "secret": server.ADMIN_SECRET},
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["dry_run"] is True
    assert body["mutation_performed"] is False
    assert calls == []  # No mutations


def test_v1_split_diagnostics_rejects_core_miner_wallet(monkeypatch):
    """Test that split diagnostics rejects core/miner wallet."""
    client, _ledger = _install_reconciliation_fixtures(monkeypatch)

    res = client.get(f"/api/v1/wallet/v1-split-diagnostics?old_address={CORE}&current_v1_address={NEW}")
    assert res.status_code == 400
    body = res.get_json()
    assert "core_miner_wallet" in body["error"]

    res = client.get(f"/api/v1/wallet/v1-split-diagnostics?old_address={OLD}&current_v1_address={CORE}")
    assert res.status_code == 400
