"""
Tests for the SigBalBot Milestone Airdrop system — security-hardened version.

Covers:
  1. State persistence
  2. Win recording and counting
  3. Milestone triggering creates PENDING allocation (not auto-distribute)
  4. Active subscriber filtering (expired, invalid wallet, unapproved)
  5. Admin approval lifecycle (pending → approved → executed)
  6. Idempotency: duplicate submission prevented
  7. Treasury balance check (insufficient balance)
  8. Chain verification after write
  9. Invalid wallet format rejected
  10. Payout audit trail (all required fields)
  11. Dry-run mode (no writes)
  12. Promoter ledger separation
  13. Multiple milestones
  14. History bounding
  15. Status and progress reporting
  16. Controlled e2e: dry-run then real execution
"""
import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from sigbalbot_milestone_airdrop import (
    SigBalBotMilestoneAirdrop,
    WINS_PER_MILESTONE,
    BASE_AIRDROP_AMOUNT,
    CHAIN_NETWORK_ID,
    validate_thr_address,
    _idempotency_key,
)


@pytest.fixture
def airdrop_env(tmp_path):
    """Set up temp directories for ledger, chain, ai_pool, subscriptions,
    promoter ledger, and milestone state."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    bridge_dir = tmp_path / "bridge"
    bridge_dir.mkdir()

    ledger_file = str(data_dir / "ledger.json")
    chain_file = str(data_dir / "phantom_tx_chain.json")
    ai_pool_file = str(data_dir / "ai_pool.json")
    subs_file = str(data_dir / "sentinel_subscriptions.json")
    promoter_file = str(data_dir / "promoter_commissions_ledger.json")
    milestone_file = bridge_dir / "milestone_state.json"
    allocations_file = bridge_dir / "allocations.json"

    with open(ledger_file, "w") as f:
        json.dump({}, f)
    with open(chain_file, "w") as f:
        json.dump([], f)
    with open(ai_pool_file, "w") as f:
        json.dump({"ai_pool_balance": 100.0, "total_ai_distributed": 0.0}, f)
    with open(promoter_file, "w") as f:
        json.dump({}, f)

    now_ts = int(time.time())
    subs = {
        "THR1abc123": {
            "tier": "starter",
            "subscribed_at": now_ts - 86400,
            "expires_at": now_ts + 86400 * 29,
            "rewards_multiplier": 1.0,
        },
        "THR2def456": {
            "tier": "pro",
            "subscribed_at": now_ts - 86400,
            "expires_at": now_ts + 86400 * 29,
            "rewards_multiplier": 1.5,
        },
        "THR3ghi789": {
            "tier": "elite",
            "subscribed_at": now_ts - 86400,
            "expires_at": now_ts + 86400 * 29,
            "rewards_multiplier": 2.5,
        },
        "THR_expired": {
            "tier": "starter",
            "subscribed_at": now_ts - 86400 * 60,
            "expires_at": now_ts - 86400,
            "rewards_multiplier": 1.0,
        },
    }
    with open(subs_file, "w") as f:
        json.dump(subs, f)

    with (
        patch("sigbalbot_milestone_airdrop.LEDGER_FILE", ledger_file),
        patch("sigbalbot_milestone_airdrop.CHAIN_FILE", chain_file),
        patch("sigbalbot_milestone_airdrop.AI_POOL_FILE", ai_pool_file),
        patch("sigbalbot_milestone_airdrop.SENTINEL_SUBSCRIPTIONS_FILE", subs_file),
        patch("sigbalbot_milestone_airdrop.PROMOTER_LEDGER_FILE", promoter_file),
        patch("sigbalbot_milestone_airdrop._MILESTONE_DIR", bridge_dir),
        patch("sigbalbot_milestone_airdrop._MILESTONE_FILE", milestone_file),
        patch("sigbalbot_milestone_airdrop._ALLOCATIONS_FILE", allocations_file),
    ):
        yield {
            "data_dir": data_dir,
            "bridge_dir": bridge_dir,
            "ledger_file": ledger_file,
            "chain_file": chain_file,
            "ai_pool_file": ai_pool_file,
            "subs_file": subs_file,
            "promoter_file": promoter_file,
            "milestone_file": milestone_file,
            "allocations_file": allocations_file,
        }


# ── 1. State persistence ──────────────────────────────────────────────────

def test_initial_state(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    assert airdrop.total_wins == 0
    assert airdrop.milestones_reached == 0
    assert airdrop.total_thr_distributed == 0.0
    assert airdrop.dry_run is False


def test_state_persisted_after_win(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.record_win("sig-1", "BTC/USDT")
    assert airdrop_env["milestone_file"].exists()
    saved = json.loads(airdrop_env["milestone_file"].read_text())
    assert saved["total_wins"] == 1


# ── 2. Win recording ──────────────────────────────────────────────────────

def test_win_increments_count(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    for i in range(5):
        airdrop.record_win(f"sig-{i}", "BTC/USDT")
    assert airdrop.total_wins == 5


def test_win_below_milestone_returns_none(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    result = airdrop.record_win("sig-1", "BTC/USDT")
    assert result is None


# ── 3. Milestone creates PENDING allocation (not auto-distribute) ────────

def test_milestone_creates_pending_allocation(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result = airdrop.record_win("sig-100", "BTC/USDT")

    assert result is not None
    assert result["status"] == "pending"
    assert result["requires_admin_approval"] is True
    assert result["milestone_number"] == 1
    assert "batch_id" in result
    assert result["active_subscribers"] == 3
    assert result["total_required_thr"] == round(1.0 + 1.5 + 2.5, 6)

    # Ledger should NOT have been written
    with open(airdrop_env["ledger_file"]) as f:
        ledger = json.load(f)
    assert ledger == {}

    # Chain should NOT have been written
    with open(airdrop_env["chain_file"]) as f:
        chain = json.load(f)
    assert chain == []


def test_no_premature_milestone(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 2
    result = airdrop.record_win("sig-99", "BTC/USDT")
    assert result is None
    assert airdrop.milestones_reached == 0


# ── 4. Active subscriber filtering ────────────────────────────────────────

def test_active_subscribers_excludes_expired(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    active = airdrop._get_active_subscribers()
    addresses = [s["address"] for s in active]
    assert "THR1abc123" in addresses
    assert "THR2def456" in addresses
    assert "THR3ghi789" in addresses
    assert "THR_expired" not in addresses
    assert len(active) == 3


def test_active_subscribers_excludes_invalid_wallet(airdrop_env):
    now_ts = int(time.time())
    subs = {
        "THR1abc123": {
            "tier": "starter",
            "expires_at": now_ts + 86400,
            "rewards_multiplier": 1.0,
        },
        "invalid-no-thr-prefix": {
            "tier": "starter",
            "expires_at": now_ts + 86400,
            "rewards_multiplier": 1.0,
        },
        "": {
            "tier": "starter",
            "expires_at": now_ts + 86400,
            "rewards_multiplier": 1.0,
        },
    }
    with open(airdrop_env["subs_file"], "w") as f:
        json.dump(subs, f)

    airdrop = SigBalBotMilestoneAirdrop()
    active = airdrop._get_active_subscribers()
    assert len(active) == 1
    assert active[0]["address"] == "THR1abc123"


def test_active_subscribers_excludes_unapproved(airdrop_env):
    now_ts = int(time.time())
    subs = {
        "THR1abc123": {
            "tier": "starter",
            "expires_at": now_ts + 86400,
            "rewards_multiplier": 1.0,
            "approved": True,
        },
        "THR2unapproved": {
            "tier": "starter",
            "expires_at": now_ts + 86400,
            "rewards_multiplier": 1.0,
            "approved": False,
        },
    }
    with open(airdrop_env["subs_file"], "w") as f:
        json.dump(subs, f)

    airdrop = SigBalBotMilestoneAirdrop()
    active = airdrop._get_active_subscribers()
    assert len(active) == 1
    assert active[0]["address"] == "THR1abc123"


# ── 5. Admin approval lifecycle ───────────────────────────────────────────

def test_approve_pending_allocation(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result = airdrop.record_win("sig-100", "BTC/USDT")
    batch_id = result["batch_id"]

    approve_result = airdrop.approve_allocation(batch_id)
    assert approve_result["status"] == "approved"
    assert approve_result["approved_at"] is not None


def test_approve_nonexistent_allocation(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    result = airdrop.approve_allocation("nonexistent-batch")
    assert result["error"] == "allocation_not_found"


def test_approve_already_approved_allocation(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result = airdrop.record_win("sig-100", "BTC/USDT")
    batch_id = result["batch_id"]

    airdrop.approve_allocation(batch_id)
    second_approve = airdrop.approve_allocation(batch_id)
    assert second_approve["error"] == "invalid_status"
    assert second_approve["current_status"] == "approved"


def test_execute_unapproved_allocation_rejected(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result = airdrop.record_win("sig-100", "BTC/USDT")
    batch_id = result["batch_id"]

    exec_result = airdrop.execute_approved_allocation(batch_id)
    assert exec_result["error"] == "invalid_status"
    assert exec_result["current_status"] == "pending"


# ── 6. Idempotency: duplicate submission prevented ────────────────────────

def test_duplicate_submission_skipped(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result = airdrop.record_win("sig-100", "BTC/USDT")
    batch_id = result["batch_id"]

    airdrop.approve_allocation(batch_id)
    first_exec = airdrop.execute_approved_allocation(batch_id)
    assert first_exec["confirmed"] == 3
    assert first_exec["skipped_duplicate"] == 0

    # Simulate re-execution attempt: reload from disk, force status back to
    # "submitted" so the execution path runs — the idempotency check should
    # detect all payouts already exist on chain and skip them.
    airdrop2 = SigBalBotMilestoneAirdrop()
    alloc = airdrop2.allocations[batch_id]
    alloc["status"] = "submitted"
    for p in alloc["payouts"]:
        p["status"] = "pending"
        p["submitted_at"] = None
        p["confirmed_at"] = None
        p["tx_hash"] = None

    second_exec = airdrop2.execute_approved_allocation(batch_id)
    assert second_exec["skipped_duplicate"] == 3
    assert second_exec["confirmed"] == 0
    assert second_exec["total_distributed"] == 0.0


def test_idempotency_key_deterministic(airdrop_env):
    key1 = _idempotency_key("batch-1", "THR1abc123")
    key2 = _idempotency_key("batch-1", "THR1abc123")
    key3 = _idempotency_key("batch-1", "THR2def456")
    assert key1 == key2
    assert key1 != key3


# ── 7. Treasury balance check ─────────────────────────────────────────────

def test_insufficient_treasury_balance(airdrop_env):
    with open(airdrop_env["ai_pool_file"], "w") as f:
        json.dump({"ai_pool_balance": 0.5}, f)

    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result = airdrop.record_win("sig-100", "BTC/USDT")
    batch_id = result["batch_id"]

    airdrop.approve_allocation(batch_id)
    exec_result = airdrop.execute_approved_allocation(batch_id)

    # Only enough balance for the first payout (1.0 THR for starter, but
    # order isn't guaranteed; at most one should succeed with 0.5 THR)
    assert exec_result["failed_insufficient_balance"] > 0
    total_confirmed = exec_result["confirmed"]
    assert total_confirmed < 3


def test_zero_treasury_balance_fails_all(airdrop_env):
    with open(airdrop_env["ai_pool_file"], "w") as f:
        json.dump({"ai_pool_balance": 0.0}, f)

    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result = airdrop.record_win("sig-100", "BTC/USDT")
    batch_id = result["batch_id"]

    airdrop.approve_allocation(batch_id)
    exec_result = airdrop.execute_approved_allocation(batch_id)

    assert exec_result["confirmed"] == 0
    assert exec_result["failed_insufficient_balance"] == 3
    assert exec_result["total_distributed"] == 0.0

    # Ledger should not have been touched
    with open(airdrop_env["ledger_file"]) as f:
        ledger = json.load(f)
    assert ledger == {}


# ── 8. Chain verification ──────────────────────────────────────────────────

def test_chain_entry_verified_after_write(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result = airdrop.record_win("sig-100", "BTC/USDT")
    batch_id = result["batch_id"]

    airdrop.approve_allocation(batch_id)
    exec_result = airdrop.execute_approved_allocation(batch_id)

    assert exec_result["confirmed"] == 3

    with open(airdrop_env["chain_file"]) as f:
        chain = json.load(f)

    assert len(chain) == 3
    for tx in chain:
        assert tx["status"] == "confirmed"
        assert "confirmed_at" in tx
        assert tx["idempotency_key"] is not None
        assert tx["chain_network_id"] == CHAIN_NETWORK_ID


def test_chain_tx_has_full_audit_trail(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result = airdrop.record_win("sig-100", "BTC/USDT")
    batch_id = result["batch_id"]

    airdrop.approve_allocation(batch_id)
    airdrop.execute_approved_allocation(batch_id)

    with open(airdrop_env["chain_file"]) as f:
        chain = json.load(f)

    for tx in chain:
        assert tx["type"] == "sigbalbot_milestone_airdrop"
        assert tx["from"] == "ai_pool"
        assert tx["to"].startswith("THR")
        assert tx["amount"] > 0
        assert tx["tx_id"].startswith("SIGBAL-AIRDROP-")
        assert tx["idempotency_key"]
        assert tx["chain_network_id"] == CHAIN_NETWORK_ID
        assert tx["timestamp"]
        assert tx["confirmed_at"]
        details = tx["details"]
        assert "batch_id" in details
        assert "allocation_id" in details
        assert "milestone" in details
        assert "wallet_snapshot" in details
        ws = details["wallet_snapshot"]
        assert "address" in ws
        assert "tier" in ws
        assert "rewards_multiplier" in ws
        assert "snapshot_at" in ws


def test_chain_verification_failure_marks_failed(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result = airdrop.record_win("sig-100", "BTC/USDT")
    batch_id = result["batch_id"]

    airdrop.approve_allocation(batch_id)

    with patch.object(airdrop, "_verify_chain_entry", return_value=False):
        exec_result = airdrop.execute_approved_allocation(batch_id)

    assert exec_result["failed"] == 3
    assert exec_result["confirmed"] == 0
    for err in exec_result["errors"]:
        assert err["reason"] == "chain_verification_failed"


# ── 9. Invalid wallet format ──────────────────────────────────────────────

def test_validate_thr_address_valid(airdrop_env):
    assert validate_thr_address("THR1abc123") is True
    assert validate_thr_address("THR_valid_addr") is True
    assert validate_thr_address("THRxyz") is True


def test_validate_thr_address_invalid(airdrop_env):
    assert validate_thr_address("") is False
    assert validate_thr_address("BTC123") is False
    assert validate_thr_address("thr_lowercase") is False
    assert validate_thr_address("TH") is False
    assert validate_thr_address(None) is False
    assert validate_thr_address(12345) is False


def test_invalid_wallet_in_payout_skipped(airdrop_env):
    now_ts = int(time.time())
    subs = {
        "THR1abc123": {
            "tier": "starter",
            "expires_at": now_ts + 86400,
            "rewards_multiplier": 1.0,
        },
    }
    with open(airdrop_env["subs_file"], "w") as f:
        json.dump(subs, f)

    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result = airdrop.record_win("sig-100", "BTC/USDT")
    batch_id = result["batch_id"]

    # Tamper with the allocation to inject an invalid address
    alloc = airdrop.allocations[batch_id]
    alloc["payouts"].append({
        "allocation_id": f"{batch_id}-INVALID",
        "address": "INVALID_ADDR",
        "amount": 1.0,
        "chain_network_id": CHAIN_NETWORK_ID,
        "idempotency_key": _idempotency_key(batch_id, "INVALID_ADDR"),
        "wallet_snapshot": {"address": "INVALID_ADDR", "tier": "starter",
                          "rewards_multiplier": 1.0, "expires_at": now_ts + 86400,
                          "snapshot_at": "now"},
        "status": "pending",
        "tx_hash": None,
        "submitted_at": None,
        "confirmed_at": None,
    })

    airdrop.approve_allocation(batch_id)
    exec_result = airdrop.execute_approved_allocation(batch_id)

    assert exec_result["skipped_invalid_wallet"] == 1
    assert exec_result["confirmed"] == 1


# ── 10. Payout audit trail (req 4) ────────────────────────────────────────

def test_payout_has_all_required_fields(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result = airdrop.record_win("sig-100", "BTC/USDT")
    batch_id = result["batch_id"]

    airdrop.approve_allocation(batch_id)
    exec_result = airdrop.execute_approved_allocation(batch_id)

    for dist in exec_result["distributions"]:
        assert "address" in dist
        assert "amount" in dist
        assert "tier" in dist
        assert "tx_hash" in dist
        assert "idempotency_key" in dist
        assert "status" in dist
        assert dist["status"] == "confirmed"

    alloc = airdrop.get_allocation(batch_id)
    for payout in alloc["payouts"]:
        assert "allocation_id" in payout
        assert "address" in payout
        assert "amount" in payout
        assert "chain_network_id" in payout
        assert payout["chain_network_id"] == CHAIN_NETWORK_ID
        assert "idempotency_key" in payout
        assert "wallet_snapshot" in payout
        assert "submitted_at" in payout
        assert "confirmed_at" in payout
        assert "tx_hash" in payout
        assert payout["status"] == "confirmed"


# ── 11. Dry-run mode ──────────────────────────────────────────────────────

def test_dry_run_no_ledger_writes(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop(dry_run=True)
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result = airdrop.record_win("sig-100", "BTC/USDT")
    batch_id = result["batch_id"]

    airdrop.approve_allocation(batch_id)
    exec_result = airdrop.execute_approved_allocation(batch_id)

    assert exec_result["dry_run"] is True
    assert exec_result["confirmed"] == 3
    assert exec_result["total_distributed"] == round(1.0 + 1.5 + 2.5, 6)

    # Ledger should NOT have been modified
    with open(airdrop_env["ledger_file"]) as f:
        ledger = json.load(f)
    assert ledger == {}

    # Chain should NOT have been modified
    with open(airdrop_env["chain_file"]) as f:
        chain = json.load(f)
    assert chain == []

    # AI pool should NOT have been debited
    with open(airdrop_env["ai_pool_file"]) as f:
        pool = json.load(f)
    assert pool["ai_pool_balance"] == 100.0


def test_dry_run_status_reports_flag(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop(dry_run=True)
    status = airdrop.get_status()
    assert status["dry_run"] is True


# ── 12. Promoter ledger separation ────────────────────────────────────────

def test_promoter_ledger_file_exists_separately(airdrop_env):
    assert os.path.exists(airdrop_env["promoter_file"])
    with open(airdrop_env["promoter_file"]) as f:
        promoter_data = json.load(f)
    assert promoter_data == {}

    # After airdrop, promoter file should still be empty
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result = airdrop.record_win("sig-100", "BTC/USDT")
    batch_id = result["batch_id"]
    airdrop.approve_allocation(batch_id)
    airdrop.execute_approved_allocation(batch_id)

    with open(airdrop_env["promoter_file"]) as f:
        promoter_data = json.load(f)
    assert promoter_data == {}


# ── 13. Multiple milestones ───────────────────────────────────────────────

def test_second_milestone_creates_separate_allocation(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()

    # First milestone
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result1 = airdrop.record_win("sig-100", "BTC/USDT")
    batch_id_1 = result1["batch_id"]

    # Execute first
    airdrop.approve_allocation(batch_id_1)
    airdrop.execute_approved_allocation(batch_id_1)

    # Second milestone
    airdrop.total_wins = 2 * WINS_PER_MILESTONE - 1
    result2 = airdrop.record_win("sig-200", "ETH/USDT")
    batch_id_2 = result2["batch_id"]

    assert batch_id_1 != batch_id_2
    assert result2["milestone_number"] == 2
    assert airdrop.milestones_reached == 2


# ── 14. History bounding ──────────────────────────────────────────────────

def test_airdrop_history_bounded(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.airdrop_history = [{"fake": i} for i in range(60)]
    airdrop._save_state()

    saved = json.loads(airdrop_env["milestone_file"].read_text())
    assert len(saved["airdrop_history"]) <= 50


# ── 15. Status and progress reporting ─────────────────────────────────────

def test_get_status(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = 60
    status = airdrop.get_status()

    assert status["total_wins"] == 60
    assert status["wins_until_next_milestone"] == 40
    assert status["milestones_reached"] == 0
    assert status["next_milestone_at"] == 100
    assert status["active_subscribers"] == 3
    assert "pending_allocations" in status


def test_get_progress(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = 60
    progress = airdrop.get_progress()

    assert progress["current_wins"] == 60
    assert progress["wins_in_current_milestone"] == 60
    assert progress["wins_needed"] == 100
    assert progress["progress_pct"] == 60.0
    assert progress["next_milestone_number"] == 1
    assert progress["base_reward"] == BASE_AIRDROP_AMOUNT


def test_get_progress_after_milestone(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = 130
    airdrop.milestones_reached = 1
    progress = airdrop.get_progress()

    assert progress["wins_in_current_milestone"] == 30
    assert progress["progress_pct"] == 30.0
    assert progress["next_milestone_number"] == 2


# ── 16. No airdrop when no active subscribers ─────────────────────────────

def test_no_airdrop_without_subscribers(airdrop_env):
    with open(airdrop_env["subs_file"], "w") as f:
        json.dump({}, f)

    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result = airdrop.record_win("sig-100", "BTC/USDT")

    assert result is not None
    assert result["active_subscribers"] == 0
    assert result["total_required_thr"] == 0.0


# ── 17. Allocation queries ────────────────────────────────────────────────

def test_list_allocations_with_filter(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result = airdrop.record_win("sig-100", "BTC/USDT")
    batch_id = result["batch_id"]

    pending = airdrop.list_allocations(status_filter="pending")
    assert len(pending) == 1
    assert pending[0]["batch_id"] == batch_id

    approved = airdrop.list_allocations(status_filter="approved")
    assert len(approved) == 0


def test_get_allocation_details(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result = airdrop.record_win("sig-100", "BTC/USDT")
    batch_id = result["batch_id"]

    alloc = airdrop.get_allocation(batch_id)
    assert alloc is not None
    assert alloc["status"] == "pending"
    assert len(alloc["payouts"]) == 3
    assert alloc["treasury_balance_at_creation"] == 100.0


# ── 18. Treasury debit verified ───────────────────────────────────────────

def test_treasury_debited_after_execution(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result = airdrop.record_win("sig-100", "BTC/USDT")
    batch_id = result["batch_id"]

    airdrop.approve_allocation(batch_id)
    airdrop.execute_approved_allocation(batch_id)

    with open(airdrop_env["ai_pool_file"]) as f:
        pool = json.load(f)

    expected_debit = round(1.0 + 1.5 + 2.5, 6)
    assert pool["ai_pool_balance"] == round(100.0 - expected_debit, 6)


# ── 19. Ledger updated correctly ──────────────────────────────────────────

def test_ledger_updated_after_execution(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result = airdrop.record_win("sig-100", "BTC/USDT")
    batch_id = result["batch_id"]

    airdrop.approve_allocation(batch_id)
    airdrop.execute_approved_allocation(batch_id)

    with open(airdrop_env["ledger_file"]) as f:
        ledger = json.load(f)

    assert ledger["THR1abc123"] == 1.0
    assert ledger["THR2def456"] == 1.5
    assert ledger["THR3ghi789"] == 2.5


# ── 20. E2E: dry-run then real execution (req 13) ─────────────────────────

def test_e2e_dry_run_then_real(airdrop_env):
    # Phase 1: Dry run
    dry_airdrop = SigBalBotMilestoneAirdrop(dry_run=True)
    dry_airdrop.total_wins = WINS_PER_MILESTONE - 1
    milestone_result = dry_airdrop.record_win("sig-100", "BTC/USDT")
    batch_id = milestone_result["batch_id"]

    dry_airdrop.approve_allocation(batch_id)
    dry_result = dry_airdrop.execute_approved_allocation(batch_id)

    assert dry_result["dry_run"] is True
    assert dry_result["confirmed"] == 3

    # Verify no actual writes happened
    with open(airdrop_env["ledger_file"]) as f:
        assert json.load(f) == {}
    with open(airdrop_env["chain_file"]) as f:
        assert json.load(f) == []
    with open(airdrop_env["ai_pool_file"]) as f:
        assert json.load(f)["ai_pool_balance"] == 100.0

    # Phase 2: Real execution — fresh instance, same batch
    real_airdrop = SigBalBotMilestoneAirdrop(dry_run=False)
    # Re-create the pending allocation since dry_run instance state wasn't saved
    # to the real files (dry_run still saves allocation metadata)
    alloc = real_airdrop.get_allocation(batch_id)
    if not alloc:
        real_airdrop.total_wins = WINS_PER_MILESTONE - 1
        milestone_result = real_airdrop.record_win("sig-100-real", "BTC/USDT")
        batch_id = milestone_result["batch_id"]

    # Reset payout statuses for fresh execution
    alloc = real_airdrop.get_allocation(batch_id)
    for p in alloc["payouts"]:
        p["status"] = "pending"
        p["tx_hash"] = None
        p["submitted_at"] = None
        p["confirmed_at"] = None
    alloc["status"] = "pending"

    real_airdrop.approve_allocation(batch_id)
    real_result = real_airdrop.execute_approved_allocation(batch_id)

    assert real_result["dry_run"] is False
    assert real_result["confirmed"] == 3
    assert real_result["total_distributed"] == round(1.0 + 1.5 + 2.5, 6)

    # Verify real writes happened
    with open(airdrop_env["ledger_file"]) as f:
        ledger = json.load(f)
    assert ledger["THR1abc123"] == 1.0

    with open(airdrop_env["chain_file"]) as f:
        chain = json.load(f)
    assert len(chain) == 3
    for tx in chain:
        assert tx["status"] == "confirmed"

    with open(airdrop_env["ai_pool_file"]) as f:
        pool = json.load(f)
    assert pool["ai_pool_balance"] == round(100.0 - 5.0, 6)


# ── 21. Never mark paid on HTTP 200 alone (req 8) ─────────────────────────

def test_status_transitions_through_submitted_to_confirmed(airdrop_env):
    """Verify payout goes through submitted → confirmed, not directly confirmed."""
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result = airdrop.record_win("sig-100", "BTC/USDT")
    batch_id = result["batch_id"]

    airdrop.approve_allocation(batch_id)

    alloc = airdrop.get_allocation(batch_id)
    for p in alloc["payouts"]:
        assert p["status"] == "pending"

    airdrop.execute_approved_allocation(batch_id)

    alloc = airdrop.get_allocation(batch_id)
    for p in alloc["payouts"]:
        assert p["status"] == "confirmed"
        assert p["submitted_at"] is not None
        assert p["confirmed_at"] is not None


# ── 22. Cumulative distribution tracked ───────────────────────────────────

def test_cumulative_thr_distributed(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    single_milestone_total = round(1.0 + 1.5 + 2.5, 6)

    # First milestone
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result1 = airdrop.record_win("sig-100", "BTC/USDT")
    airdrop.approve_allocation(result1["batch_id"])
    airdrop.execute_approved_allocation(result1["batch_id"])
    assert airdrop.total_thr_distributed == single_milestone_total

    # Second milestone
    airdrop.total_wins = 2 * WINS_PER_MILESTONE - 1
    result2 = airdrop.record_win("sig-200", "ETH/USDT")
    airdrop.approve_allocation(result2["batch_id"])
    airdrop.execute_approved_allocation(result2["batch_id"])
    assert airdrop.total_thr_distributed == round(single_milestone_total * 2, 6)
