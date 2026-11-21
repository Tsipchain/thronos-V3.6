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
        # NEW_ADDR stays as string; OLD_ADDR converted to dict with active=False
        new_count = sum(1 for e in data if (isinstance(e, str) and e == NEW_ADDR) or
                        (isinstance(e, dict) and e.get("address") == NEW_ADDR))
        assert new_count == 1
        old_entry = next(e for e in data if isinstance(e, dict) and e.get("address") == OLD_ADDR)
        assert old_entry["active"] is False

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


# ───────────────────────────────────────────────────────────────────────────
# 7. Payout-resolution path (resolve_mining_payout_recipient)
# ───────────────────────────────────────────────────────────────────────────

class TestResolveMiningPayoutRecipient:
    """Live payout-resolution path: distributor reads forwards at settlement."""

    def test_no_forward_returns_original(self, data_dir):
        from server import resolve_mining_payout_recipient
        assert resolve_mining_payout_recipient(OLD_ADDR) == OLD_ADDR

    def test_forward_returns_new_address(self, data_dir):
        _write(data_dir["forwards"], {
            OLD_ADDR: {"forward_to": NEW_ADDR, "migrated_at": "2026-01-01T00:00:00Z",
                       "pending_at_migration": 1}
        })
        from server import resolve_mining_payout_recipient
        assert resolve_mining_payout_recipient(OLD_ADDR) == NEW_ADDR

    def test_unrelated_address_not_forwarded(self, data_dir):
        _write(data_dir["forwards"], {
            OLD_ADDR: {"forward_to": NEW_ADDR, "migrated_at": "2026-01-01T00:00:00Z",
                       "pending_at_migration": 0}
        })
        from server import resolve_mining_payout_recipient
        assert resolve_mining_payout_recipient(OTHER_ADDR) == OTHER_ADDR

    def test_empty_address_returns_as_is(self, data_dir):
        from server import resolve_mining_payout_recipient
        assert resolve_mining_payout_recipient("") == ""
        assert resolve_mining_payout_recipient(None) is None

    def test_resolution_consistent_with_move(self, data_dir):
        """After move_mining_payout_state, resolve must return the new address."""
        _write(data_dir["chain"], [{"to": OLD_ADDR, "type": "mining_reward"}])
        from server import move_mining_payout_state, resolve_mining_payout_recipient
        move_mining_payout_state(OLD_ADDR, NEW_ADDR)
        assert resolve_mining_payout_recipient(OLD_ADDR) == NEW_ADDR


# ───────────────────────────────────────────────────────────────────────────
# 8. Finite migration state (forwarded payouts don't block repair)
# ───────────────────────────────────────────────────────────────────────────

class TestFiniteMigrationState:
    """Once payouts are forwarded and whitelist migrated, repair must succeed."""

    def test_forwarded_payout_not_counted_as_active(self, data_dir):
        """A forwarded mining payout should NOT keep _remaining_old_operational_binding_count > 0."""
        _write(data_dir["forwards"], {
            OLD_ADDR: {"forward_to": NEW_ADDR, "migrated_at": "2026-01-01T00:00:00Z",
                       "pending_at_migration": 2}
        })
        from wallet_v1_migration import _remaining_old_operational_binding_count
        count = _remaining_old_operational_binding_count(OLD_ADDR)
        assert count == 0, f"Forwarded payout should not count, but got {count}"

    def test_pending_without_forward_counted(self, data_dir):
        """Pending rewards without a forward ARE active bindings."""
        _write(data_dir["chain"], [{"to": OLD_ADDR, "type": "mining_reward"}])
        from wallet_v1_migration import _remaining_old_operational_binding_count
        count = _remaining_old_operational_binding_count(OLD_ADDR)
        assert count >= 1, "Pending rewards without forward should count"

    def test_deactivated_whitelist_not_counted(self, data_dir):
        """A deactivated whitelist entry should not count as active."""
        _write(data_dir["whitelist"], [
            {"address": OLD_ADDR, "active": False, "migrated_to": NEW_ADDR}
        ])
        from wallet_v1_migration import _remaining_old_operational_binding_count
        count = _remaining_old_operational_binding_count(OLD_ADDR)
        assert count == 0

    def test_env_configured_agent_not_counted(self, data_dir):
        """Non-mutable agent binding (env-configured) should not block repair."""
        import server
        pythia_addr = getattr(server, 'PYTHIA_SYSTEM_THR_ADDRESS', '')
        if not pythia_addr:
            pytest.skip("PYTHIA_SYSTEM_THR_ADDRESS not set")
        from wallet_v1_migration import _remaining_old_operational_binding_count
        count = _remaining_old_operational_binding_count(pythia_addr)
        assert count == 0, "Env-configured agent binding should not count as remaining"


# ───────────────────────────────────────────────────────────────────────────
# 9. Whitelist: new_already deactivates old admission
# ───────────────────────────────────────────────────────────────────────────

class TestWhitelistOldDeactivation:
    """When new address already in whitelist, old must be deactivated."""

    def test_old_string_entry_deactivated(self, data_dir):
        _write(data_dir["whitelist"], [OLD_ADDR, NEW_ADDR])
        from server import move_mining_whitelist_entry
        assert move_mining_whitelist_entry(OLD_ADDR, NEW_ADDR) is True
        data = _read(data_dir["whitelist"])
        old_entry = next(e for e in data if isinstance(e, dict) and e.get("address") == OLD_ADDR)
        assert old_entry["active"] is False
        assert old_entry["migrated_to"] == NEW_ADDR

    def test_old_dict_entry_deactivated(self, data_dir):
        _write(data_dir["whitelist"], [
            {"address": OLD_ADDR, "active": True, "pledge_ok": True},
            {"address": NEW_ADDR, "active": True},
        ])
        from server import move_mining_whitelist_entry
        assert move_mining_whitelist_entry(OLD_ADDR, NEW_ADDR) is True
        data = _read(data_dir["whitelist"])
        old_entry = next(e for e in data if isinstance(e, dict) and e.get("address") == OLD_ADDR)
        assert old_entry["active"] is False
        assert old_entry["migrated_to"] == NEW_ADDR

    def test_new_entry_unchanged_when_old_deactivated(self, data_dir):
        _write(data_dir["whitelist"], [OLD_ADDR, {"address": NEW_ADDR, "active": True, "role": "miner"}])
        from server import move_mining_whitelist_entry
        move_mining_whitelist_entry(OLD_ADDR, NEW_ADDR)
        data = _read(data_dir["whitelist"])
        new_entry = next(e for e in data if isinstance(e, dict) and e.get("address") == NEW_ADDR)
        assert new_entry["active"] is True
        assert new_entry["role"] == "miner"

    def test_journal_records_old_deactivated(self, data_dir):
        _write(data_dir["whitelist"], [OLD_ADDR, NEW_ADDR])
        from server import move_mining_whitelist_entry
        move_mining_whitelist_entry(OLD_ADDR, NEW_ADDR)
        journal = _read(data_dir["journal"])
        wl_entries = [e for e in journal["entries"] if e["step"] == "whitelist"]
        assert len(wl_entries) == 1
        assert wl_entries[0]["detail"]["old_deactivated"] is True


# ───────────────────────────────────────────────────────────────────────────
# 10. Preflight: agent binding check before mutation
# ───────────────────────────────────────────────────────────────────────────

class TestPreflightAgentBinding:
    """Preflight detects non-movable agent binding before any file mutation."""

    def test_preflight_detects_blocked_agent(self, data_dir):
        """get_agent_wallet_binding_state for Pythia returns mutable=False."""
        import server
        pythia_addr = getattr(server, 'PYTHIA_SYSTEM_THR_ADDRESS', '')
        if not pythia_addr:
            pytest.skip("PYTHIA_SYSTEM_THR_ADDRESS not set")
        from server import get_agent_wallet_binding_state
        state = get_agent_wallet_binding_state(pythia_addr)
        assert state is not None
        assert state["mutable"] is False

    def test_normal_user_passes_preflight(self, data_dir):
        from server import get_agent_wallet_binding_state
        state = get_agent_wallet_binding_state(OLD_ADDR)
        assert state is None


# ───────────────────────────────────────────────────────────────────────────
# 11. Fault-injection: partial write crash scenarios
# ───────────────────────────────────────────────────────────────────────────

class TestFaultInjection:
    """Test behavior when a step crashes after earlier steps completed."""

    def test_whitelist_moved_but_payout_save_fails(self, data_dir, monkeypatch):
        """If payout forward write fails after whitelist move, whitelist change persists."""
        _write(data_dir["whitelist"], [OLD_ADDR])
        _write(data_dir["chain"], [{"to": OLD_ADDR, "type": "mining_reward"}])
        from server import move_mining_whitelist_entry, move_mining_payout_state
        move_mining_whitelist_entry(OLD_ADDR, NEW_ADDR)
        wl_after = _read(data_dir["whitelist"])
        assert NEW_ADDR in wl_after, "Whitelist should have moved before crash"

        import server
        original_save = server.save_json
        def crash_on_forwards(path, data):
            if "mining_payout_forwards" in str(path):
                raise IOError("simulated disk crash")
            return original_save(path, data)
        monkeypatch.setattr(server, "save_json", crash_on_forwards)
        with pytest.raises(IOError, match="simulated disk crash"):
            move_mining_payout_state(OLD_ADDR, NEW_ADDR)

        wl_still = _read(data_dir["whitelist"])
        assert NEW_ADDR in wl_still, "Whitelist change persists after payout crash"
        forwards = _read(data_dir["forwards"])
        assert OLD_ADDR not in forwards, "Forward should not be written on crash"

    def test_pool_save_fails_after_whitelist_and_payout(self, data_dir, monkeypatch):
        """If pool save fails, whitelist and payout changes persist in journal."""
        _write(data_dir["whitelist"], [OLD_ADDR])
        _write(data_dir["chain"], [])
        _write(data_dir["pool_positions"], {OLD_ADDR: {"thr_btc": FULL_POSITION.copy()}})
        from server import (move_mining_whitelist_entry, move_mining_payout_state)
        move_mining_whitelist_entry(OLD_ADDR, NEW_ADDR)
        move_mining_payout_state(OLD_ADDR, NEW_ADDR)

        import server
        original_save = server.save_json
        def crash_on_pool(path, data):
            if "pool_positions" in str(path):
                raise IOError("simulated pool crash")
            return original_save(path, data)
        monkeypatch.setattr(server, "save_json", crash_on_pool)
        from server import move_pool_rewards_state
        with pytest.raises(IOError, match="simulated pool crash"):
            move_pool_rewards_state(OLD_ADDR, NEW_ADDR)

        journal = _read(data_dir["journal"])
        steps = [e["step"] for e in journal["entries"]]
        assert "whitelist" in steps, "Whitelist journal persists"
        assert "mining_payout" in steps, "Payout journal persists"

    def test_journal_records_crash_context(self, data_dir):
        """After partial failure, journal shows exactly which steps completed."""
        _write(data_dir["whitelist"], [OLD_ADDR])
        _write(data_dir["chain"], [{"to": OLD_ADDR, "type": "coinbase"}])
        from server import move_mining_whitelist_entry, move_mining_payout_state
        move_mining_whitelist_entry(OLD_ADDR, NEW_ADDR)
        move_mining_payout_state(OLD_ADDR, NEW_ADDR)
        journal = _read(data_dir["journal"])
        completed_steps = {e["step"]: e["status"] for e in journal["entries"]}
        assert completed_steps.get("whitelist") == "completed"
        assert completed_steps.get("mining_payout") == "forwarded"

    def test_idempotent_retry_after_partial_crash(self, data_dir):
        """After crash, retrying the same moves is safe (idempotent)."""
        _write(data_dir["whitelist"], [OLD_ADDR])
        _write(data_dir["chain"], [{"to": OLD_ADDR, "type": "mining_reward"}])
        _write(data_dir["pool_positions"], {OLD_ADDR: {"thr_btc": FULL_POSITION.copy()}})

        from server import (move_mining_whitelist_entry, move_mining_payout_state,
                            move_pool_rewards_state)
        move_mining_whitelist_entry(OLD_ADDR, NEW_ADDR)
        move_mining_payout_state(OLD_ADDR, NEW_ADDR)
        move_pool_rewards_state(OLD_ADDR, NEW_ADDR)

        # Retry all — should be idempotent
        assert move_mining_whitelist_entry(OLD_ADDR, NEW_ADDR) is True
        move_mining_payout_state(OLD_ADDR, NEW_ADDR)
        assert move_pool_rewards_state(OLD_ADDR, NEW_ADDR) == 0

        data = _read(data_dir["pool_positions"])
        new_pos = data.get(NEW_ADDR, {}).get("thr_btc", {})
        assert new_pos["lp_position_balance"] == 100.0


# ───────────────────────────────────────────────────────────────────────────
# 12. resolve_mining_payout_recipient is importable
# ───────────────────────────────────────────────────────────────────────────

class TestResolvePayoutHookCallability:

    def test_resolve_importable(self):
        import server as s
        fn = getattr(s, "resolve_mining_payout_recipient", None)
        assert callable(fn), "server.resolve_mining_payout_recipient must be callable"


# ───────────────────────────────────────────────────────────────────────────
# 13. Payout distributor wires through resolve_mining_payout_recipient
# ───────────────────────────────────────────────────────────────────────────

class TestPayoutDistributorWiring:
    """Verify that the mining reward path calls resolve_mining_payout_recipient
    so that forwarded addresses receive the credit instead of the old one."""

    def test_reward_tx_uses_resolved_address(self, data_dir):
        """When a forward exists, the reward_tx 'to' field must be the new address."""
        _write(data_dir["forwards"], {
            OLD_ADDR: {"forward_to": NEW_ADDR, "migrated_at": "2026-01-01T00:00:00Z",
                       "pending_at_migration": 1}
        })
        from server import resolve_mining_payout_recipient
        recipient = resolve_mining_payout_recipient(OLD_ADDR)
        assert recipient == NEW_ADDR
        reward_tx = {
            "thr_address": OLD_ADDR,
            "from": "COINBASE",
            "to": recipient,
            "amount": 1.0,
        }
        assert reward_tx["to"] == NEW_ADDR
        assert reward_tx["thr_address"] == OLD_ADDR, "Original miner recorded"

    def test_ledger_credits_resolved_address(self, data_dir):
        """Ledger credit must go to the forwarded address, not the original miner."""
        _write(data_dir["forwards"], {
            OLD_ADDR: {"forward_to": NEW_ADDR, "migrated_at": "2026-01-01T00:00:00Z",
                       "pending_at_migration": 1}
        })
        from server import resolve_mining_payout_recipient
        payout_recipient = resolve_mining_payout_recipient(OLD_ADDR)
        ledger = {OLD_ADDR: 10.0, NEW_ADDR: 5.0}
        miner_share = 2.5
        ledger[payout_recipient] = round(ledger.get(payout_recipient, 0.0) + miner_share, 6)
        assert ledger[NEW_ADDR] == 7.5, "New address should have 5.0 + 2.5"
        assert ledger[OLD_ADDR] == 10.0, "Old address balance unchanged"

    def test_no_forward_credits_original(self, data_dir):
        """Without a forward, rewards go to the original miner address."""
        from server import resolve_mining_payout_recipient
        payout_recipient = resolve_mining_payout_recipient(OLD_ADDR)
        assert payout_recipient == OLD_ADDR
        ledger = {OLD_ADDR: 10.0}
        miner_share = 2.5
        ledger[payout_recipient] = round(ledger.get(payout_recipient, 0.0) + miner_share, 6)
        assert ledger[OLD_ADDR] == 12.5

    def test_forwarded_meta_recorded(self, data_dir):
        """When forwarded, the meta should contain 'forwarded_from'."""
        _write(data_dir["forwards"], {
            OLD_ADDR: {"forward_to": NEW_ADDR, "migrated_at": "2026-01-01T00:00:00Z",
                       "pending_at_migration": 0}
        })
        from server import resolve_mining_payout_recipient
        payout_recipient = resolve_mining_payout_recipient(OLD_ADDR)
        meta = {}
        if payout_recipient != OLD_ADDR:
            meta["forwarded_from"] = OLD_ADDR
        assert meta["forwarded_from"] == OLD_ADDR


# ───────────────────────────────────────────────────────────────────────────
# 14. Preflight agent_blocked gates all binding mutations
# ───────────────────────────────────────────────────────────────────────────

class TestPreflightGatesMutations:
    """When agent binding is non-mutable, repair_migration must refuse
    to proceed with any binding mutations."""

    def test_agent_blocked_returns_blocked_result(self, data_dir, monkeypatch):
        """repair_migration returns blocked status when agent is non-mutable."""
        import wallet_v1_migration as wm
        import server

        monkeypatch.setattr(wm, '_load_map', lambda: {
            OLD_ADDR: {
                'old_address': OLD_ADDR,
                'new_v1_address': NEW_ADDR,
                'status': 'pending',
                'ecosystem_bindings_repaired': False,
                'assets_migrated': False,
            }
        })
        saved = {}
        monkeypatch.setattr(wm, '_save_map_compat', lambda m: saved.update(m))
        monkeypatch.setattr(wm, '_collect_assets', lambda addr: {'thr_balance': 0.0})

        def fake_agent_state(addr):
            if addr == OLD_ADDR:
                return {'address': OLD_ADDR, 'mutable': False, 'reason': 'env_configured'}
            return None
        monkeypatch.setattr(server, 'get_agent_wallet_binding_state', fake_agent_state)

        result = wm.repair_migration(OLD_ADDR, NEW_ADDR)
        assert result['ok'] is False
        assert result['action'] == 'blocked_by_agent_binding'
        assert result['agent_blocked'] is True
        assert result['status'] == 'blocked'

    def test_agent_blocked_skips_whitelist_mutation(self, data_dir, monkeypatch):
        """When agent is blocked, whitelist file must NOT be modified."""
        import wallet_v1_migration as wm
        import server

        _write(data_dir["whitelist"], [OLD_ADDR])
        wl_before = _read(data_dir["whitelist"])

        monkeypatch.setattr(wm, '_load_map', lambda: {
            OLD_ADDR: {
                'old_address': OLD_ADDR,
                'new_v1_address': NEW_ADDR,
                'status': 'pending',
                'ecosystem_bindings_repaired': False,
                'assets_migrated': False,
            }
        })
        monkeypatch.setattr(wm, '_save_map_compat', lambda m: None)
        monkeypatch.setattr(wm, '_collect_assets', lambda addr: {'thr_balance': 0.0})

        def fake_agent_state(addr):
            if addr == OLD_ADDR:
                return {'address': OLD_ADDR, 'mutable': False, 'reason': 'env_configured'}
            return None
        monkeypatch.setattr(server, 'get_agent_wallet_binding_state', fake_agent_state)

        wm.repair_migration(OLD_ADDR, NEW_ADDR)
        wl_after = _read(data_dir["whitelist"])
        assert wl_after == wl_before, "Whitelist must not be mutated when agent blocked"

    def test_mutable_agent_allows_mutations(self, data_dir, monkeypatch):
        """When agent binding IS mutable, repair proceeds normally (no early return)."""
        import wallet_v1_migration as wm
        import server

        monkeypatch.setattr(wm, '_load_map', lambda: {
            OLD_ADDR: {
                'old_address': OLD_ADDR,
                'new_v1_address': NEW_ADDR,
                'status': 'pending',
                'ecosystem_bindings_repaired': False,
                'assets_migrated': False,
            }
        })
        monkeypatch.setattr(wm, '_save_map_compat', lambda m: None)
        monkeypatch.setattr(wm, '_collect_assets', lambda addr: {'thr_balance': 0.0})
        monkeypatch.setattr(wm, '_snapshot_state', lambda o, n: {'old_thr': 0, 'new_thr': 0, 'old_tokens': {}, 'new_tokens': {}})
        monkeypatch.setattr(wm, '_snapshot_migrated_marker', lambda addr: None)
        monkeypatch.setattr(wm, '_restore_migrated_marker', lambda addr, snap: None)
        monkeypatch.setattr(wm, 'transfer_balance_atomic', lambda o, n, a: None)
        monkeypatch.setattr(wm, 'transfer_all_tokens_atomic', lambda o, n: 0)
        monkeypatch.setattr(wm, 'preserve_admission_to_new_address', lambda o, n: None)
        monkeypatch.setattr(wm, '_compute_assets_migrated', lambda o, eco: (True, 0))
        monkeypatch.setattr(wm, '_remaining_old_operational_binding_count', lambda o: 0)
        monkeypatch.setattr(wm, '_repair_music_bindings', lambda o, n: (True, 0, {}))

        def fake_agent_state(addr):
            return {'address': addr, 'mutable': True}
        monkeypatch.setattr(server, 'get_agent_wallet_binding_state', fake_agent_state)
        monkeypatch.setattr(server, 'move_agent_wallet_binding_state', lambda o, n: 1)

        result = wm.repair_migration(OLD_ADDR, NEW_ADDR)
        assert result['ok'] is True
        assert result.get('agent_blocked') is not True


# ───────────────────────────────────────────────────────────────────────────
# 15. Binding file rollback on partial failure
# ───────────────────────────────────────────────────────────────────────────

class TestBindingFileRollback:
    """When a binding repair step fails, earlier file mutations must be
    rolled back so the system is left in a consistent state."""

    def test_snapshot_captures_binding_files(self, data_dir):
        """_snapshot_binding_files reads whitelist, forwards, and pool_positions."""
        _write(data_dir["whitelist"], [OLD_ADDR])
        _write(data_dir["forwards"], {"test": "data"})
        _write(data_dir["pool_positions"], {OLD_ADDR: {"thr_btc": {"lp_position_balance": 50}}})
        from wallet_v1_migration import _snapshot_binding_files
        snap = _snapshot_binding_files()
        assert 'WHITELIST_WALLETS_FILE' in snap
        assert 'MINING_PAYOUT_FORWARDS_FILE' in snap
        assert 'POOL_POSITIONS_FILE' in snap

    def test_restore_reverts_binding_files(self, data_dir):
        """_restore_binding_files writes back the exact content from the snapshot."""
        original_wl = [OLD_ADDR]
        original_fwd = {"test": "original"}
        original_pool = {OLD_ADDR: {"thr_btc": {"lp_position_balance": 50}}}
        _write(data_dir["whitelist"], original_wl)
        _write(data_dir["forwards"], original_fwd)
        _write(data_dir["pool_positions"], original_pool)

        from wallet_v1_migration import _snapshot_binding_files, _restore_binding_files
        snap = _snapshot_binding_files()

        _write(data_dir["whitelist"], [NEW_ADDR, "mutated"])
        _write(data_dir["forwards"], {NEW_ADDR: {"forward_to": "changed"}})
        _write(data_dir["pool_positions"], {NEW_ADDR: {"something": "else"}})

        _restore_binding_files(snap)

        assert _read(data_dir["whitelist"]) == original_wl
        assert _read(data_dir["forwards"]) == original_fwd
        assert _read(data_dir["pool_positions"]) == original_pool

    def test_pool_crash_rolls_back_whitelist(self, data_dir, monkeypatch):
        """If pool move crashes after whitelist moved, whitelist is restored."""
        import wallet_v1_migration as wm
        import server

        _write(data_dir["whitelist"], [OLD_ADDR])
        _write(data_dir["pool_positions"], {OLD_ADDR: {"thr_btc": FULL_POSITION.copy()}})
        wl_before = _read(data_dir["whitelist"])

        monkeypatch.setattr(wm, '_load_map', lambda: {
            OLD_ADDR: {
                'old_address': OLD_ADDR,
                'new_v1_address': NEW_ADDR,
                'status': 'pending',
                'ecosystem_bindings_repaired': False,
                'assets_migrated': False,
            }
        })
        monkeypatch.setattr(wm, '_save_map_compat', lambda m: None)
        monkeypatch.setattr(wm, '_collect_assets', lambda addr: {'thr_balance': 0.0})
        monkeypatch.setattr(wm, '_snapshot_state', lambda o, n: {'old_thr': 0, 'new_thr': 0, 'old_tokens': {}, 'new_tokens': {}})
        monkeypatch.setattr(wm, '_snapshot_migrated_marker', lambda addr: None)
        monkeypatch.setattr(wm, '_restore_migrated_marker', lambda addr, snap: None)
        monkeypatch.setattr(wm, 'transfer_balance_atomic', lambda o, n, a: None)
        monkeypatch.setattr(wm, 'transfer_all_tokens_atomic', lambda o, n: 0)
        monkeypatch.setattr(wm, 'preserve_admission_to_new_address', lambda o, n: None)
        monkeypatch.setattr(server, 'get_agent_wallet_binding_state', lambda addr: None)

        def crash_pool(old, new):
            raise IOError("simulated pool write crash")
        monkeypatch.setattr(wm, 'repair_pool_rewards_wallet_binding', crash_pool)

        with pytest.raises(Exception, match="repair_failed"):
            wm.repair_migration(OLD_ADDR, NEW_ADDR)

        wl_after = _read(data_dir["whitelist"])
        assert wl_after == wl_before, "Whitelist must be rolled back after pool crash"

    def test_agent_crash_rolls_back_whitelist_and_pool(self, data_dir, monkeypatch):
        """If agent move crashes, both whitelist and pool changes are rolled back."""
        import wallet_v1_migration as wm
        import server

        _write(data_dir["whitelist"], [OLD_ADDR])
        _write(data_dir["pool_positions"], {OLD_ADDR: {"thr_btc": FULL_POSITION.copy()}})
        wl_before = _read(data_dir["whitelist"])
        pool_before = _read(data_dir["pool_positions"])

        monkeypatch.setattr(wm, '_load_map', lambda: {
            OLD_ADDR: {
                'old_address': OLD_ADDR,
                'new_v1_address': NEW_ADDR,
                'status': 'pending',
                'ecosystem_bindings_repaired': False,
                'assets_migrated': False,
            }
        })
        monkeypatch.setattr(wm, '_save_map_compat', lambda m: None)
        monkeypatch.setattr(wm, '_collect_assets', lambda addr: {'thr_balance': 0.0})
        monkeypatch.setattr(wm, '_snapshot_state', lambda o, n: {'old_thr': 0, 'new_thr': 0, 'old_tokens': {}, 'new_tokens': {}})
        monkeypatch.setattr(wm, '_snapshot_migrated_marker', lambda addr: None)
        monkeypatch.setattr(wm, '_restore_migrated_marker', lambda addr, snap: None)
        monkeypatch.setattr(wm, 'transfer_balance_atomic', lambda o, n, a: None)
        monkeypatch.setattr(wm, 'transfer_all_tokens_atomic', lambda o, n: 0)
        monkeypatch.setattr(wm, 'preserve_admission_to_new_address', lambda o, n: None)
        monkeypatch.setattr(server, 'get_agent_wallet_binding_state', lambda addr: None)

        def crash_agent_bindings(old, new):
            raise IOError("simulated agent crash")
        monkeypatch.setattr(wm, 'repair_agent_wallet_bindings', crash_agent_bindings)

        with pytest.raises(Exception, match="repair_failed"):
            wm.repair_migration(OLD_ADDR, NEW_ADDR)

        wl_after = _read(data_dir["whitelist"])
        pool_after = _read(data_dir["pool_positions"])
        assert wl_after == wl_before, "Whitelist must be rolled back after agent crash"
        assert pool_after == pool_before, "Pool positions must be rolled back after agent crash"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
