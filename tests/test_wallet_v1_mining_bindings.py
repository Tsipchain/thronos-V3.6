"""
Tests for mining/pool/agent wallet binding continuity during V1 migration.
Verifies the server.py hooks that wallet_v1_migration.repair_*() calls.

Addresses issue #507.
"""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch


WHITELIST_FILE = "data/whitelist_wallets.json"
CHAIN_FILE = "data/chain.json"
POOL_POSITIONS_FILE = "data/pool_positions.json"

OLD_ADDR = "THROLD0000000000000000000000000000000000000"
NEW_ADDR = "THRNEW0000000000000000000000000000000000000"


def _load_json(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


class TestMoveMiningWhitelistEntry:
    """move_mining_whitelist_entry must rebind address idempotently."""

    def test_move_string_entry(self, tmp_path, monkeypatch):
        wl = tmp_path / "whitelist_wallets.json"
        wl.write_text(json.dumps([OLD_ADDR, "OTHER_ADDR"]))
        monkeypatch.setattr("server.WHITELIST_WALLETS_FILE", str(wl))
        from server import move_mining_whitelist_entry
        result = move_mining_whitelist_entry(OLD_ADDR, NEW_ADDR)
        assert result is True
        data = json.loads(wl.read_text())
        assert NEW_ADDR in data
        assert OLD_ADDR not in data
        assert "OTHER_ADDR" in data

    def test_move_dict_entry(self, tmp_path, monkeypatch):
        wl = tmp_path / "whitelist_wallets.json"
        entry = {"address": OLD_ADDR, "active": True, "pledge_ok": True, "role": "miner"}
        wl.write_text(json.dumps([entry]))
        monkeypatch.setattr("server.WHITELIST_WALLETS_FILE", str(wl))
        from server import move_mining_whitelist_entry
        result = move_mining_whitelist_entry(OLD_ADDR, NEW_ADDR)
        assert result is True
        data = json.loads(wl.read_text())
        moved = data[0]
        assert moved["address"] == NEW_ADDR
        assert moved["active"] is True
        assert moved["migrated_from"] == OLD_ADDR

    def test_idempotent_when_new_already_exists(self, tmp_path, monkeypatch):
        wl = tmp_path / "whitelist_wallets.json"
        wl.write_text(json.dumps([OLD_ADDR, NEW_ADDR]))
        monkeypatch.setattr("server.WHITELIST_WALLETS_FILE", str(wl))
        from server import move_mining_whitelist_entry
        result = move_mining_whitelist_entry(OLD_ADDR, NEW_ADDR)
        assert result is True
        data = json.loads(wl.read_text())
        assert data.count(NEW_ADDR) == 1

    def test_no_entry_returns_false(self, tmp_path, monkeypatch):
        wl = tmp_path / "whitelist_wallets.json"
        wl.write_text(json.dumps(["OTHER_ADDR"]))
        monkeypatch.setattr("server.WHITELIST_WALLETS_FILE", str(wl))
        from server import move_mining_whitelist_entry
        result = move_mining_whitelist_entry(OLD_ADDR, NEW_ADDR)
        assert result is False

    def test_repeat_move_does_not_duplicate(self, tmp_path, monkeypatch):
        wl = tmp_path / "whitelist_wallets.json"
        wl.write_text(json.dumps([OLD_ADDR]))
        monkeypatch.setattr("server.WHITELIST_WALLETS_FILE", str(wl))
        from server import move_mining_whitelist_entry
        move_mining_whitelist_entry(OLD_ADDR, NEW_ADDR)
        move_mining_whitelist_entry(OLD_ADDR, NEW_ADDR)
        data = json.loads(wl.read_text())
        assert data.count(NEW_ADDR) == 1


class TestGetMiningPayoutState:
    """get_mining_payout_state returns pending mining rewards or None."""

    def test_no_pending_returns_none(self, tmp_path, monkeypatch):
        cf = tmp_path / "chain.json"
        cf.write_text(json.dumps([
            {"to": OLD_ADDR, "type": "mining_reward", "confirmed": True}
        ]))
        monkeypatch.setattr("server.CHAIN_FILE", str(cf))
        from server import get_mining_payout_state
        assert get_mining_payout_state(OLD_ADDR) is None

    def test_pending_detected(self, tmp_path, monkeypatch):
        cf = tmp_path / "chain.json"
        cf.write_text(json.dumps([
            {"to": OLD_ADDR, "type": "mining_reward"},
            {"to": OLD_ADDR, "type": "coinbase"},
        ]))
        monkeypatch.setattr("server.CHAIN_FILE", str(cf))
        from server import get_mining_payout_state
        state = get_mining_payout_state(OLD_ADDR)
        assert state is not None
        assert state["pending_count"] == 2


class TestMoveMiningPayoutState:
    """move_mining_payout_state redirects pending rewards."""

    def test_move_pending_rewards(self, tmp_path, monkeypatch):
        cf = tmp_path / "chain.json"
        cf.write_text(json.dumps([
            {"to": OLD_ADDR, "type": "mining_reward"},
            {"to": OLD_ADDR, "type": "mining_reward", "confirmed": True},
            {"to": OLD_ADDR, "type": "transfer"},
        ]))
        monkeypatch.setattr("server.CHAIN_FILE", str(cf))
        from server import move_mining_payout_state
        moved = move_mining_payout_state(OLD_ADDR, NEW_ADDR)
        assert moved == 1
        data = json.loads(cf.read_text())
        pending = [tx for tx in data if tx.get("to") == NEW_ADDR]
        assert len(pending) == 1
        assert pending[0]["migrated_from"] == OLD_ADDR

    def test_idempotent_no_pending(self, tmp_path, monkeypatch):
        cf = tmp_path / "chain.json"
        cf.write_text(json.dumps([]))
        monkeypatch.setattr("server.CHAIN_FILE", str(cf))
        from server import move_mining_payout_state
        assert move_mining_payout_state(OLD_ADDR, NEW_ADDR) == 0


class TestGetPoolRewardsState:
    """get_pool_rewards_state detects active LP positions."""

    def test_no_position_returns_none(self, tmp_path, monkeypatch):
        pf = tmp_path / "pool_positions.json"
        pf.write_text(json.dumps({}))
        monkeypatch.setattr("server.POOL_POSITIONS_FILE", str(pf))
        from server import get_pool_rewards_state
        assert get_pool_rewards_state(OLD_ADDR) is None

    def test_active_position_detected(self, tmp_path, monkeypatch):
        pf = tmp_path / "pool_positions.json"
        pf.write_text(json.dumps({
            OLD_ADDR: {"thr_btc": {"lp_position_balance": 100.0}}
        }))
        monkeypatch.setattr("server.POOL_POSITIONS_FILE", str(pf))
        from server import get_pool_rewards_state
        state = get_pool_rewards_state(OLD_ADDR)
        assert state is not None
        assert "thr_btc" in state["active_pools"]


class TestMovePoolRewardsState:
    """move_pool_rewards_state moves LP positions idempotently."""

    def test_move_position(self, tmp_path, monkeypatch):
        pf = tmp_path / "pool_positions.json"
        pf.write_text(json.dumps({
            OLD_ADDR: {"thr_btc": {"lp_position_balance": 100.0}}
        }))
        monkeypatch.setattr("server.POOL_POSITIONS_FILE", str(pf))
        from server import move_pool_rewards_state
        moved = move_pool_rewards_state(OLD_ADDR, NEW_ADDR)
        assert moved == 1
        data = json.loads(pf.read_text())
        assert data[NEW_ADDR]["thr_btc"]["lp_position_balance"] == 100.0
        assert data[OLD_ADDR]["thr_btc"]["lp_position_balance"] == 0

    def test_idempotent_already_moved(self, tmp_path, monkeypatch):
        pf = tmp_path / "pool_positions.json"
        pf.write_text(json.dumps({
            OLD_ADDR: {"thr_btc": {"lp_position_balance": 0}},
            NEW_ADDR: {"thr_btc": {"lp_position_balance": 100.0}}
        }))
        monkeypatch.setattr("server.POOL_POSITIONS_FILE", str(pf))
        from server import move_pool_rewards_state
        assert move_pool_rewards_state(OLD_ADDR, NEW_ADDR) == 0

    def test_no_duplicate_on_repeat(self, tmp_path, monkeypatch):
        pf = tmp_path / "pool_positions.json"
        pf.write_text(json.dumps({
            OLD_ADDR: {"thr_btc": {"lp_position_balance": 50.0}}
        }))
        monkeypatch.setattr("server.POOL_POSITIONS_FILE", str(pf))
        from server import move_pool_rewards_state
        move_pool_rewards_state(OLD_ADDR, NEW_ADDR)
        move_pool_rewards_state(OLD_ADDR, NEW_ADDR)
        data = json.loads(pf.read_text())
        assert data[NEW_ADDR]["thr_btc"]["lp_position_balance"] == 50.0


class TestAgentWalletBindings:
    """Agent wallet bindings are env-configured; state check is read-only."""

    def test_pythia_wallet_detected(self):
        from server import get_agent_wallet_binding_state, PYTHIA_SYSTEM_THR_ADDRESS
        if PYTHIA_SYSTEM_THR_ADDRESS:
            state = get_agent_wallet_binding_state(PYTHIA_SYSTEM_THR_ADDRESS)
            assert state is not None
            assert state["role"] == "pythia_system"

    def test_normal_user_has_no_binding(self):
        from server import get_agent_wallet_binding_state
        assert get_agent_wallet_binding_state(OLD_ADDR) is None

    def test_move_returns_zero(self):
        from server import move_agent_wallet_binding_state
        assert move_agent_wallet_binding_state(OLD_ADDR, NEW_ADDR) == 0


class TestRepairMigrationIntegration:
    """Verify repair_migration computes ecosystem_bindings_repaired correctly."""

    def test_repair_result_has_binding_fields(self):
        src = Path("wallet_v1_migration.py").read_text()
        idx = src.index("def repair_migration(")
        block = src[idx:idx + 3000]
        assert "mining_bindings_repaired" in block or "mining_ok" in block
        assert "pool_rewards_repaired" in block or "pool_ok" in block
        assert "agent_bindings_repaired" in block or "agent_ok" in block
        assert "ecosystem_bindings_repaired" in block or "ecosystem_ok" in block

    def test_ecosystem_ok_requires_all_bindings(self):
        src = Path("wallet_v1_migration.py").read_text()
        idx = src.index("ecosystem_ok")
        line = src[idx:src.index("\n", idx)]
        assert "mining_ok" in line
        assert "pool_ok" in line
        assert "agent_ok" in line
        assert "music_ok" in line

    def test_remaining_operational_count_function_exists(self):
        src = Path("wallet_v1_migration.py").read_text()
        assert "_remaining_old_operational_binding_count" in src
        idx = src.index("def _remaining_old_operational_binding_count")
        block = src[idx:idx + 500]
        assert "get_mining_whitelist_entry" in block
        assert "get_mining_payout_state" in block
        assert "get_pool_rewards_state" in block


class TestServerHooksRegistered:
    """Verify all required hooks exist in server.py."""

    def test_all_hooks_are_callable(self):
        import server
        hooks = [
            "get_mining_whitelist_entry",
            "move_mining_whitelist_entry",
            "get_mining_payout_state",
            "move_mining_payout_state",
            "get_pool_rewards_state",
            "move_pool_rewards_state",
            "get_agent_wallet_binding_state",
            "move_agent_wallet_binding_state",
        ]
        for name in hooks:
            fn = getattr(server, name, None)
            assert callable(fn), f"server.{name} must be callable"
