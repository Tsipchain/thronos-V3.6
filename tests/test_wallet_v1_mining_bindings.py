"""
Tests for mining/pool/agent wallet binding continuity during V1 migration.
Exercises the server.py hooks that wallet_v1_migration.repair_*() calls
against real store-shaped JSON data with tmp_path isolation.

Addresses issue #507.
"""

import json
import os
import pytest
from pathlib import Path


OLD_ADDR = "THROLD0000000000000000000000000000000000000"
NEW_ADDR = "THRNEW0000000000000000000000000000000000000"
OTHER_ADDR = "THROTHER000000000000000000000000000000000000"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Point all data files at tmp_path so tests never touch real data."""
    wl = tmp_path / "whitelist_wallets.json"
    wl.write_text("[]")
    chain = tmp_path / "phantom_tx_chain.json"
    chain.write_text("[]")
    pool_pos = tmp_path / "pool_positions.json"
    pool_pos.write_text("{}")
    forwards = tmp_path / "mining_payout_forwards.json"
    forwards.write_text("{}")
    journal = tmp_path / "binding_migration_journal.json"
    journal.write_text('{"entries":[]}')

    monkeypatch.setattr("server.WHITELIST_WALLETS_FILE", str(wl))
    monkeypatch.setattr("server.CHAIN_FILE", str(chain))
    monkeypatch.setattr("server.POOL_POSITIONS_FILE", str(pool_pos))
    monkeypatch.setattr("server.MINING_PAYOUT_FORWARDS_FILE", str(forwards))
    monkeypatch.setattr("server.BINDING_MIGRATION_JOURNAL_FILE", str(journal))

    return {
        "whitelist": wl,
        "chain": chain,
        "pool_positions": pool_pos,
        "forwards": forwards,
        "journal": journal,
    }


def _write(path, data):
    path.write_text(json.dumps(data))


def _read(path):
    return json.loads(path.read_text())


# ───────────────────────────────────────────────────────────────────────────
# 1. Whitelist entry rebinding
# ───────────────────────────────────────────────────────────────────────────

class TestMoveMiningWhitelistEntry:

    def test_move_string_entry(self, data_dir):
        _write(data_dir["whitelist"], [OLD_ADDR, OTHER_ADDR])
        from server import move_mining_whitelist_entry
        assert move_mining_whitelist_entry(OLD_ADDR, NEW_ADDR) is True
        data = _read(data_dir["whitelist"])
        assert NEW_ADDR in data
        assert OLD_ADDR not in data
        assert OTHER_ADDR in data

    def test_move_dict_entry_preserves_all_fields(self, data_dir):
        entry = {"address": OLD_ADDR, "thr_address": OLD_ADDR,
                 "active": True, "pledge_ok": True, "role": "miner",
                 "whitelist_legacy": True}
        _write(data_dir["whitelist"], [entry])
        from server import move_mining_whitelist_entry
        assert move_mining_whitelist_entry(OLD_ADDR, NEW_ADDR) is True
        data = _read(data_dir["whitelist"])
        moved = data[0]
        assert moved["address"] == NEW_ADDR
        assert moved["thr_address"] == NEW_ADDR
        assert moved["active"] is True
        assert moved["pledge_ok"] is True
        assert moved["role"] == "miner"
        assert moved["whitelist_legacy"] is True
        assert moved["migrated_from"] == OLD_ADDR

    def test_idempotent_when_new_already_exists(self, data_dir):
        _write(data_dir["whitelist"], [OLD_ADDR, NEW_ADDR])
        from server import move_mining_whitelist_entry
        assert move_mining_whitelist_entry(OLD_ADDR, NEW_ADDR) is True
        data = _read(data_dir["whitelist"])
        assert data.count(NEW_ADDR) == 1

    def test_no_entry_returns_false(self, data_dir):
        _write(data_dir["whitelist"], [OTHER_ADDR])
        from server import move_mining_whitelist_entry
        assert move_mining_whitelist_entry(OLD_ADDR, NEW_ADDR) is False

    def test_repeat_move_does_not_duplicate(self, data_dir):
        _write(data_dir["whitelist"], [OLD_ADDR])
        from server import move_mining_whitelist_entry
        move_mining_whitelist_entry(OLD_ADDR, NEW_ADDR)
        move_mining_whitelist_entry(OLD_ADDR, NEW_ADDR)
        data = _read(data_dir["whitelist"])
        assert data.count(NEW_ADDR) == 1

    def test_journal_entry_written(self, data_dir):
        _write(data_dir["whitelist"], [OLD_ADDR])
        from server import move_mining_whitelist_entry
        move_mining_whitelist_entry(OLD_ADDR, NEW_ADDR)
        journal = _read(data_dir["journal"])
        wl_entries = [e for e in journal["entries"] if e["step"] == "whitelist"]
        assert len(wl_entries) == 1
        assert wl_entries[0]["status"] == "completed"


# ───────────────────────────────────────────────────────────────────────────
# 2. Mining payout forwarding (NOT chain mutation)
# ───────────────────────────────────────────────────────────────────────────

class TestGetMiningPayoutState:

    def test_no_pending_returns_none(self, data_dir):
        _write(data_dir["chain"], [
            {"to": OLD_ADDR, "type": "mining_reward", "confirmed": True},
        ])
        from server import get_mining_payout_state
        assert get_mining_payout_state(OLD_ADDR) is None

    def test_pending_detected(self, data_dir):
        _write(data_dir["chain"], [
            {"to": OLD_ADDR, "type": "mining_reward"},
            {"to": OLD_ADDR, "type": "coinbase"},
            {"to": OLD_ADDR, "type": "mining_reward", "confirmed": True},
        ])
        from server import get_mining_payout_state
        state = get_mining_payout_state(OLD_ADDR)
        assert state is not None
        assert state["pending_count"] == 2


class TestMoveMiningPayoutState:

    def test_creates_forward_not_chain_mutation(self, data_dir):
        """Core invariant: chain.json must NOT be modified."""
        chain_data = [
            {"to": OLD_ADDR, "type": "mining_reward", "amount": 10.0},
            {"to": OLD_ADDR, "type": "coinbase", "amount": 5.0},
            {"to": OLD_ADDR, "type": "mining_reward", "confirmed": True, "amount": 50.0},
        ]
        _write(data_dir["chain"], chain_data)
        from server import move_mining_payout_state
        count = move_mining_payout_state(OLD_ADDR, NEW_ADDR)
        assert count == 2
        chain_after = _read(data_dir["chain"])
        assert chain_after == chain_data, "chain.json must not be modified"
        forwards = _read(data_dir["forwards"])
        assert OLD_ADDR in forwards
        fwd = forwards[OLD_ADDR]
        assert fwd["forward_to"] == NEW_ADDR
        assert fwd["pending_at_migration"] == 2

    def test_idempotent_overwrites_forward(self, data_dir):
        _write(data_dir["chain"], [
            {"to": OLD_ADDR, "type": "mining_reward"},
        ])
        from server import move_mining_payout_state
        move_mining_payout_state(OLD_ADDR, NEW_ADDR)
        move_mining_payout_state(OLD_ADDR, NEW_ADDR)
        forwards = _read(data_dir["forwards"])
        assert forwards[OLD_ADDR]["forward_to"] == NEW_ADDR

    def test_zero_pending_still_creates_forward(self, data_dir):
        _write(data_dir["chain"], [])
        from server import move_mining_payout_state
        count = move_mining_payout_state(OLD_ADDR, NEW_ADDR)
        assert count == 0
        forwards = _read(data_dir["forwards"])
        assert forwards[OLD_ADDR]["forward_to"] == NEW_ADDR
        assert forwards[OLD_ADDR]["pending_at_migration"] == 0

    def test_journal_entry_written(self, data_dir):
        _write(data_dir["chain"], [{"to": OLD_ADDR, "type": "coinbase"}])
        from server import move_mining_payout_state
        move_mining_payout_state(OLD_ADDR, NEW_ADDR)
        journal = _read(data_dir["journal"])
        payout_entries = [e for e in journal["entries"] if e["step"] == "mining_payout"]
        assert len(payout_entries) == 1
        assert payout_entries[0]["status"] == "forwarded"


# ───────────────────────────────────────────────────────────────────────────
# 3. Pool position transfer (complete balance ownership)
# ───────────────────────────────────────────────────────────────────────────

FULL_POSITION = {
    "address": OLD_ADDR,
    "pool_id": "thr_btc",
    "lp_position_balance": 100.0,
    "external_side_balance": 25.5,
    "thr_side_balance": 74.5,
    "last_updated": "2026-01-01T00:00:00Z",
}


class TestGetPoolRewardsState:

    def test_no_position_returns_none(self, data_dir):
        _write(data_dir["pool_positions"], {})
        from server import get_pool_rewards_state
        assert get_pool_rewards_state(OLD_ADDR) is None

    def test_detects_position_with_any_nonzero_balance(self, data_dir):
        """A position with external_side_balance > 0 but lp == 0 is still active."""
        _write(data_dir["pool_positions"], {
            OLD_ADDR: {"thr_btc": {
                "lp_position_balance": 0,
                "external_side_balance": 10.0,
                "thr_side_balance": 0,
            }}
        })
        from server import get_pool_rewards_state
        state = get_pool_rewards_state(OLD_ADDR)
        assert state is not None
        assert "thr_btc" in state["active_pools"]

    def test_all_zero_returns_none(self, data_dir):
        _write(data_dir["pool_positions"], {
            OLD_ADDR: {"thr_btc": {
                "lp_position_balance": 0,
                "external_side_balance": 0,
                "thr_side_balance": 0,
            }}
        })
        from server import get_pool_rewards_state
        assert get_pool_rewards_state(OLD_ADDR) is None


class TestMovePoolRewardsState:

    def test_transfers_all_balance_fields(self, data_dir):
        """Core invariant: ALL balance fields must move; old must be zeroed."""
        _write(data_dir["pool_positions"], {OLD_ADDR: {"thr_btc": FULL_POSITION.copy()}})
        from server import move_pool_rewards_state
        moved = move_pool_rewards_state(OLD_ADDR, NEW_ADDR)
        assert moved == 1
        data = _read(data_dir["pool_positions"])
        new_p = data[NEW_ADDR]["thr_btc"]
        assert new_p["lp_position_balance"] == 100.0
        assert new_p["external_side_balance"] == 25.5
        assert new_p["thr_side_balance"] == 74.5
        assert new_p["address"] == NEW_ADDR
        assert new_p["migrated_from"] == OLD_ADDR
        old_p = data[OLD_ADDR]["thr_btc"]
        assert old_p["lp_position_balance"] == 0
        assert old_p["external_side_balance"] == 0
        assert old_p["thr_side_balance"] == 0
        assert old_p["migrated_to"] == NEW_ADDR

    def test_old_address_cannot_withdraw_after_move(self, data_dir):
        """Withdrawal gate: external_side_balance on old must be 0."""
        _write(data_dir["pool_positions"], {OLD_ADDR: {"thr_btc": FULL_POSITION.copy()}})
        from server import move_pool_rewards_state
        move_pool_rewards_state(OLD_ADDR, NEW_ADDR)
        data = _read(data_dir["pool_positions"])
        old_ext = float(data[OLD_ADDR]["thr_btc"].get("external_side_balance", 0))
        assert old_ext == 0, "old address must not have withdrawable balance"

    def test_idempotent_when_new_has_balance(self, data_dir):
        _write(data_dir["pool_positions"], {
            OLD_ADDR: {"thr_btc": FULL_POSITION.copy()},
            NEW_ADDR: {"thr_btc": {
                "lp_position_balance": 200.0,
                "external_side_balance": 50.0,
                "thr_side_balance": 150.0,
            }},
        })
        from server import move_pool_rewards_state
        assert move_pool_rewards_state(OLD_ADDR, NEW_ADDR) == 0

    def test_multiple_pools_moved(self, data_dir):
        pos_a = {**FULL_POSITION, "pool_id": "thr_btc"}
        pos_b = {**FULL_POSITION, "pool_id": "thr_usdt",
                 "lp_position_balance": 50.0, "external_side_balance": 30.0,
                 "thr_side_balance": 20.0}
        _write(data_dir["pool_positions"], {
            OLD_ADDR: {"thr_btc": pos_a, "thr_usdt": pos_b}
        })
        from server import move_pool_rewards_state
        assert move_pool_rewards_state(OLD_ADDR, NEW_ADDR) == 2
        data = _read(data_dir["pool_positions"])
        assert data[NEW_ADDR]["thr_btc"]["lp_position_balance"] == 100.0
        assert data[NEW_ADDR]["thr_usdt"]["lp_position_balance"] == 50.0
        assert data[OLD_ADDR]["thr_btc"]["external_side_balance"] == 0
        assert data[OLD_ADDR]["thr_usdt"]["external_side_balance"] == 0

    def test_repeat_move_does_not_double_balance(self, data_dir):
        _write(data_dir["pool_positions"], {OLD_ADDR: {"thr_btc": FULL_POSITION.copy()}})
        from server import move_pool_rewards_state
        move_pool_rewards_state(OLD_ADDR, NEW_ADDR)
        move_pool_rewards_state(OLD_ADDR, NEW_ADDR)
        data = _read(data_dir["pool_positions"])
        assert data[NEW_ADDR]["thr_btc"]["lp_position_balance"] == 100.0

    def test_journal_entry_written(self, data_dir):
        _write(data_dir["pool_positions"], {OLD_ADDR: {"thr_btc": FULL_POSITION.copy()}})
        from server import move_pool_rewards_state
        move_pool_rewards_state(OLD_ADDR, NEW_ADDR)
        journal = _read(data_dir["journal"])
        pool_entries = [e for e in journal["entries"] if e["step"] == "pool_positions"]
        assert len(pool_entries) == 1
        assert pool_entries[0]["detail"]["pools_moved"] == 1


# ───────────────────────────────────────────────────────────────────────────
# 4. Agent wallet bindings (env-configured, read-only)
# ───────────────────────────────────────────────────────────────────────────

class TestAgentWalletBindings:

    def test_pythia_wallet_detected(self):
        from server import get_agent_wallet_binding_state, PYTHIA_SYSTEM_THR_ADDRESS
        if PYTHIA_SYSTEM_THR_ADDRESS:
            state = get_agent_wallet_binding_state(PYTHIA_SYSTEM_THR_ADDRESS)
            assert state is not None
            assert state["role"] == "pythia_system"
            assert state["mutable"] is False

    def test_normal_user_has_no_binding(self):
        from server import get_agent_wallet_binding_state
        assert get_agent_wallet_binding_state(OLD_ADDR) is None

    def test_move_returns_negative_when_binding_exists(self):
        from server import move_agent_wallet_binding_state, PYTHIA_SYSTEM_THR_ADDRESS
        if PYTHIA_SYSTEM_THR_ADDRESS:
            result = move_agent_wallet_binding_state(PYTHIA_SYSTEM_THR_ADDRESS, NEW_ADDR)
            assert result == -1, "must signal that binding exists but cannot be moved"

    def test_move_returns_zero_when_no_binding(self, data_dir):
        from server import move_agent_wallet_binding_state
        assert move_agent_wallet_binding_state(OLD_ADDR, NEW_ADDR) == 0

    def test_journal_records_blocked_when_binding_exists(self, data_dir):
        from server import move_agent_wallet_binding_state, PYTHIA_SYSTEM_THR_ADDRESS
        if PYTHIA_SYSTEM_THR_ADDRESS:
            move_agent_wallet_binding_state(PYTHIA_SYSTEM_THR_ADDRESS, NEW_ADDR)
            journal = _read(data_dir["journal"])
            agent_entries = [e for e in journal["entries"] if e["step"] == "agent_binding"]
            assert len(agent_entries) == 1
            assert agent_entries[0]["status"] == "blocked_env_configured"


# ───────────────────────────────────────────────────────────────────────────
# 5. Migration journal reconciliation
# ───────────────────────────────────────────────────────────────────────────

class TestMigrationJournal:

    def test_full_migration_sequence_journal(self, data_dir):
        """Run all three binding movers; journal must record each step."""
        _write(data_dir["whitelist"], [OLD_ADDR])
        _write(data_dir["chain"], [{"to": OLD_ADDR, "type": "mining_reward"}])
        _write(data_dir["pool_positions"], {OLD_ADDR: {"thr_btc": FULL_POSITION.copy()}})
        from server import (move_mining_whitelist_entry, move_mining_payout_state,
                            move_pool_rewards_state)
        move_mining_whitelist_entry(OLD_ADDR, NEW_ADDR)
        move_mining_payout_state(OLD_ADDR, NEW_ADDR)
        move_pool_rewards_state(OLD_ADDR, NEW_ADDR)
        journal = _read(data_dir["journal"])
        steps = [e["step"] for e in journal["entries"]]
        assert "whitelist" in steps
        assert "mining_payout" in steps
        assert "pool_positions" in steps
        for entry in journal["entries"]:
            assert "at" in entry
            assert "old_address" in entry
            assert "new_v1_address" in entry

    def test_journal_survives_multiple_migrations(self, data_dir):
        """Journal accumulates entries across multiple address pairs."""
        _write(data_dir["whitelist"], [OLD_ADDR, OTHER_ADDR])
        from server import move_mining_whitelist_entry
        move_mining_whitelist_entry(OLD_ADDR, NEW_ADDR)
        move_mining_whitelist_entry(OTHER_ADDR, NEW_ADDR)
        journal = _read(data_dir["journal"])
        assert len(journal["entries"]) >= 2


# ───────────────────────────────────────────────────────────────────────────
# 6. Integration: repair_migration hook callability
# ───────────────────────────────────────────────────────────────────────────

class TestRepairMigrationHookCallability:
    """Verify wallet_v1_migration.py can call all hooks via getattr."""

    def test_all_hooks_importable(self):
        import server as s
        hooks = [
            "move_mining_whitelist_entry",
            "get_mining_payout_state",
            "move_mining_payout_state",
            "get_pool_rewards_state",
            "move_pool_rewards_state",
            "get_agent_wallet_binding_state",
            "move_agent_wallet_binding_state",
        ]
        for name in hooks:
            fn = getattr(s, name, None)
            assert callable(fn), f"server.{name} must be callable"

    def test_repair_functions_use_getattr_pattern(self):
        src = Path("wallet_v1_migration.py").read_text()
        for fn_name in ["move_mining_whitelist_entry", "move_mining_payout_state",
                        "move_pool_rewards_state", "move_agent_wallet_binding_state"]:
            assert fn_name in src, f"wallet_v1_migration.py must reference {fn_name}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
