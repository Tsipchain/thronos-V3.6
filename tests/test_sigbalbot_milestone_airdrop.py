"""
Tests for the SigBalBot Milestone Airdrop system.

Covers:
  1. State persistence
  2. Win recording and counting
  3. Milestone triggering at 100 wins
  4. Active subscriber filtering
  5. THR distribution with rewards_multiplier
  6. Ledger and chain file writes
  7. Status and progress reporting
  8. No airdrop when no active subscribers
  9. Multiple milestones
  10. History bounding
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
)


@pytest.fixture
def airdrop_env(tmp_path):
    """Set up temp directories for ledger, chain, subscriptions, and milestone state."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    bridge_dir = tmp_path / "bridge"
    bridge_dir.mkdir()

    ledger_file = str(data_dir / "ledger.json")
    chain_file = str(data_dir / "phantom_tx_chain.json")
    subs_file = str(data_dir / "sentinel_subscriptions.json")
    milestone_file = bridge_dir / "milestone_state.json"

    with open(ledger_file, "w") as f:
        json.dump({}, f)
    with open(chain_file, "w") as f:
        json.dump([], f)

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
        patch("sigbalbot_milestone_airdrop.SENTINEL_SUBSCRIPTIONS_FILE", subs_file),
        patch("sigbalbot_milestone_airdrop._MILESTONE_DIR", bridge_dir),
        patch("sigbalbot_milestone_airdrop._MILESTONE_FILE", milestone_file),
    ):
        yield {
            "data_dir": data_dir,
            "bridge_dir": bridge_dir,
            "ledger_file": ledger_file,
            "chain_file": chain_file,
            "subs_file": subs_file,
            "milestone_file": milestone_file,
        }


# ── 1. State persistence ────────────────────────────────────────────────────

def test_initial_state(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    assert airdrop.total_wins == 0
    assert airdrop.milestones_reached == 0
    assert airdrop.total_thr_distributed == 0.0


def test_state_persisted_after_win(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.record_win("sig-1", "BTC/USDT")
    assert airdrop_env["milestone_file"].exists()
    saved = json.loads(airdrop_env["milestone_file"].read_text())
    assert saved["total_wins"] == 1


# ── 2. Win recording ────────────────────────────────────────────────────────

def test_win_increments_count(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    for i in range(5):
        airdrop.record_win(f"sig-{i}", "BTC/USDT")
    assert airdrop.total_wins == 5


def test_win_below_milestone_returns_none(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    result = airdrop.record_win("sig-1", "BTC/USDT")
    assert result is None


# ── 3. Milestone triggering ─────────────────────────────────────────────────

def test_milestone_triggers_at_100_wins(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result = airdrop.record_win("sig-100", "BTC/USDT")
    assert result is not None
    assert result["milestone_number"] == 1
    assert result["wins_at_milestone"] == WINS_PER_MILESTONE
    assert airdrop.milestones_reached == 1


def test_no_premature_milestone(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 2
    result = airdrop.record_win("sig-99", "BTC/USDT")
    assert result is None
    assert airdrop.milestones_reached == 0


# ── 4. Active subscriber filtering ──────────────────────────────────────────

def test_active_subscribers_excludes_expired(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    active = airdrop._get_active_subscribers()
    addresses = [s["address"] for s in active]
    assert "THR1abc123" in addresses
    assert "THR2def456" in addresses
    assert "THR3ghi789" in addresses
    assert "THR_expired" not in addresses
    assert len(active) == 3


# ── 5. THR distribution with multiplier ─────────────────────────────────────

def test_distribution_applies_rewards_multiplier(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result = airdrop.record_win("sig-100", "BTC/USDT")

    distributions = {d["address"]: d for d in result["distributions"]}
    assert distributions["THR1abc123"]["amount"] == round(BASE_AIRDROP_AMOUNT * 1.0, 6)
    assert distributions["THR2def456"]["amount"] == round(BASE_AIRDROP_AMOUNT * 1.5, 6)
    assert distributions["THR3ghi789"]["amount"] == round(BASE_AIRDROP_AMOUNT * 2.5, 6)


def test_total_distributed_correct(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result = airdrop.record_win("sig-100", "BTC/USDT")

    expected = round(1.0 + 1.5 + 2.5, 6)
    assert result["total_distributed"] == expected


# ── 6. Ledger and chain writes ──────────────────────────────────────────────

def test_ledger_updated_after_airdrop(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    airdrop.record_win("sig-100", "BTC/USDT")

    with open(airdrop_env["ledger_file"]) as f:
        ledger = json.load(f)

    assert ledger["THR1abc123"] == 1.0
    assert ledger["THR2def456"] == 1.5
    assert ledger["THR3ghi789"] == 2.5


def test_chain_records_created(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    airdrop.record_win("sig-100", "BTC/USDT")

    with open(airdrop_env["chain_file"]) as f:
        chain = json.load(f)

    assert len(chain) == 3
    for tx in chain:
        assert tx["type"] == "sigbalbot_milestone_airdrop"
        assert tx["status"] == "confirmed"
        assert tx["tx_id"].startswith("SIGBAL-AIRDROP-1-")
        assert tx["details"]["milestone"] == 1
        assert tx["details"]["total_wins"] == WINS_PER_MILESTONE


def test_chain_tx_has_correct_amounts(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    airdrop.record_win("sig-100", "BTC/USDT")

    with open(airdrop_env["chain_file"]) as f:
        chain = json.load(f)

    tx_by_address = {tx["to"]: tx for tx in chain}
    assert tx_by_address["THR1abc123"]["amount"] == 1.0
    assert tx_by_address["THR2def456"]["amount"] == 1.5
    assert tx_by_address["THR3ghi789"]["amount"] == 2.5


# ── 7. Status and progress reporting ────────────────────────────────────────

def test_get_status(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = 60
    status = airdrop.get_status()

    assert status["total_wins"] == 60
    assert status["wins_until_next_milestone"] == 40
    assert status["milestones_reached"] == 0
    assert status["next_milestone_at"] == 100
    assert status["active_subscribers"] == 3


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


# ── 8. No airdrop when no active subscribers ─────────────────────────────────

def test_no_airdrop_without_subscribers(airdrop_env):
    with open(airdrop_env["subs_file"], "w") as f:
        json.dump({}, f)

    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = WINS_PER_MILESTONE - 1
    result = airdrop.record_win("sig-100", "BTC/USDT")

    assert result is not None
    assert result["active_subscribers"] == 0
    assert result["distributions"] == []
    assert result["total_distributed"] == 0.0


# ── 9. Multiple milestones ───────────────────────────────────────────────────

def test_second_milestone_triggers(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.total_wins = 2 * WINS_PER_MILESTONE - 1
    airdrop.milestones_reached = 1
    result = airdrop.record_win("sig-200", "ETH/USDT")

    assert result is not None
    assert result["milestone_number"] == 2
    assert result["wins_at_milestone"] == 200
    assert airdrop.milestones_reached == 2


def test_cumulative_thr_distributed(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    single_milestone_total = round(1.0 + 1.5 + 2.5, 6)

    airdrop.total_wins = WINS_PER_MILESTONE - 1
    airdrop.record_win("sig-100", "BTC/USDT")
    assert airdrop.total_thr_distributed == single_milestone_total

    airdrop.total_wins = 2 * WINS_PER_MILESTONE - 1
    airdrop.record_win("sig-200", "ETH/USDT")
    assert airdrop.total_thr_distributed == round(single_milestone_total * 2, 6)


# ── 10. History bounding ─────────────────────────────────────────────────────

def test_airdrop_history_bounded(airdrop_env):
    airdrop = SigBalBotMilestoneAirdrop()
    airdrop.airdrop_history = [{"fake": i} for i in range(60)]
    airdrop._save_state()

    saved = json.loads(airdrop_env["milestone_file"].read_text())
    assert len(saved["airdrop_history"]) <= 50
