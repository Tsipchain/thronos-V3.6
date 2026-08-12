"""
SigBalBot Milestone Airdrop — Distributes THR tokens to active Sentinel
subscribers when SigBalBot signal wins reach milestones.

Rule: Every 100 qualifying wins → 1 THR per active subscriber (scaled by
the subscriber's rewards_multiplier from their package tier).

Milestone state persisted at /app/data/sigbalbot_bridge/milestone_state.json.

Uses the same ledger/chain patterns as _distribute_ai_pool_to_address().
"""
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_DIR = os.environ.get("DATA_DIR", "data")
LEDGER_FILE = os.path.join(DATA_DIR, "ledger.json")
CHAIN_FILE = os.path.join(DATA_DIR, "phantom_tx_chain.json")
SENTINEL_SUBSCRIPTIONS_FILE = os.path.join(DATA_DIR, "sentinel_subscriptions.json")

_MILESTONE_DIR = Path(os.getenv("SIGBALBOT_BRIDGE_STATE_DIR", "/app/data/sigbalbot_bridge"))
_MILESTONE_FILE = _MILESTONE_DIR / "milestone_state.json"

WINS_PER_MILESTONE = 100
BASE_AIRDROP_AMOUNT = 1.0


def load_json(path: str, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


def save_json(path: str, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


class SigBalBotMilestoneAirdrop:
    """Tracks SigBalBot qualifying wins and distributes THR at milestones."""

    def __init__(self):
        self.state = self._load_state()
        self.total_wins: int = self.state.get("total_wins", 0)
        self.milestones_reached: int = self.state.get("milestones_reached", 0)
        self.total_thr_distributed: float = self.state.get("total_thr_distributed", 0.0)
        self.last_airdrop_at: Optional[str] = self.state.get("last_airdrop_at")
        self.airdrop_history: List[Dict[str, Any]] = self.state.get("airdrop_history", [])

    def _load_state(self) -> Dict[str, Any]:
        if not _MILESTONE_FILE.exists():
            return {
                "total_wins": 0,
                "milestones_reached": 0,
                "total_thr_distributed": 0.0,
                "airdrop_history": [],
            }
        try:
            with open(_MILESTONE_FILE) as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("[milestone-airdrop] could not load state: %s", exc)
            return {
                "total_wins": 0,
                "milestones_reached": 0,
                "total_thr_distributed": 0.0,
                "airdrop_history": [],
            }

    def _save_state(self) -> None:
        _MILESTONE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(_MILESTONE_FILE, "w") as f:
                json.dump({
                    "total_wins": self.total_wins,
                    "milestones_reached": self.milestones_reached,
                    "total_thr_distributed": self.total_thr_distributed,
                    "last_airdrop_at": self.last_airdrop_at,
                    "airdrop_history": self.airdrop_history[-50:],
                }, f)
        except Exception as exc:
            logger.warning("[milestone-airdrop] could not save state: %s", exc)

    def record_win(self, signal_id: str, symbol: str) -> Optional[Dict[str, Any]]:
        """Record a qualifying signal win. Returns airdrop summary if milestone triggered."""
        self.total_wins += 1
        logger.info(
            "[milestone-airdrop] win #%d recorded (signal=%s, symbol=%s)",
            self.total_wins, signal_id, symbol,
        )

        expected_milestones = self.total_wins // WINS_PER_MILESTONE
        if expected_milestones > self.milestones_reached:
            milestone_number = self.milestones_reached + 1
            self.milestones_reached = expected_milestones
            result = self._execute_airdrop(milestone_number)
            self._save_state()
            return result

        self._save_state()
        return None

    def _get_active_subscribers(self) -> List[Dict[str, Any]]:
        """Load active Sentinel subscribers with valid THR addresses."""
        subs = load_json(SENTINEL_SUBSCRIPTIONS_FILE, {})
        now_ts = int(time.time())
        active = []

        for address, sub in subs.items():
            if not address or not isinstance(sub, dict):
                continue
            if sub.get("expires_at", 0) <= now_ts:
                continue
            active.append({
                "address": address,
                "tier": sub.get("tier", "starter"),
                "rewards_multiplier": float(sub.get("rewards_multiplier", 1.0)),
                "expires_at": sub.get("expires_at"),
            })

        return active

    def _execute_airdrop(self, milestone_number: int) -> Dict[str, Any]:
        """Distribute THR to all active subscribers for a milestone."""
        subscribers = self._get_active_subscribers()
        ts_str = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

        result: Dict[str, Any] = {
            "milestone_number": milestone_number,
            "wins_at_milestone": milestone_number * WINS_PER_MILESTONE,
            "active_subscribers": len(subscribers),
            "distributions": [],
            "total_distributed": 0.0,
            "timestamp": ts_str,
        }

        if not subscribers:
            logger.info("[milestone-airdrop] milestone #%d reached but no active subscribers", milestone_number)
            self.airdrop_history.append(result)
            return result

        logger.info(
            "[milestone-airdrop] MILESTONE #%d — distributing THR to %d active subscribers",
            milestone_number, len(subscribers),
        )

        ledger = load_json(LEDGER_FILE, {})
        chain = load_json(CHAIN_FILE, [])

        for sub in subscribers:
            address = sub["address"]
            amount = round(BASE_AIRDROP_AMOUNT * sub["rewards_multiplier"], 6)

            ledger[address] = round(float(ledger.get(address, 0)) + amount, 6)

            tx_id = f"SIGBAL-AIRDROP-{milestone_number}-{int(time.time())}-{secrets.token_hex(4)}"
            tx = {
                "type": "sigbalbot_milestone_airdrop",
                "from": "ai_pool",
                "to": address,
                "amount": amount,
                "timestamp": ts_str,
                "tx_id": tx_id,
                "status": "confirmed",
                "details": {
                    "milestone": milestone_number,
                    "total_wins": milestone_number * WINS_PER_MILESTONE,
                    "subscriber_tier": sub["tier"],
                    "rewards_multiplier": sub["rewards_multiplier"],
                    "base_amount": BASE_AIRDROP_AMOUNT,
                },
            }
            chain.append(tx)

            result["distributions"].append({
                "address": address,
                "amount": amount,
                "tier": sub["tier"],
                "tx_id": tx_id,
            })
            result["total_distributed"] += amount
            self.total_thr_distributed += amount

            logger.info(
                "[milestone-airdrop] distributed %.6f THR to %s (tier=%s, mult=%.1fx)",
                amount, address[:12] + "...", sub["tier"], sub["rewards_multiplier"],
            )

        save_json(LEDGER_FILE, ledger)
        save_json(CHAIN_FILE, chain)

        result["total_distributed"] = round(result["total_distributed"], 6)
        self.last_airdrop_at = ts_str
        self.airdrop_history.append(result)

        logger.info(
            "[milestone-airdrop] milestone #%d complete — %.6f THR distributed to %d subscribers",
            milestone_number, result["total_distributed"], len(subscribers),
        )

        return result

    def get_status(self) -> Dict[str, Any]:
        """Return milestone airdrop status for health/status endpoints."""
        next_milestone_at = (self.milestones_reached + 1) * WINS_PER_MILESTONE
        return {
            "total_wins": self.total_wins,
            "wins_until_next_milestone": next_milestone_at - self.total_wins,
            "milestones_reached": self.milestones_reached,
            "next_milestone_at": next_milestone_at,
            "total_thr_distributed": round(self.total_thr_distributed, 6),
            "last_airdrop_at": self.last_airdrop_at,
            "active_subscribers": len(self._get_active_subscribers()),
        }

    def get_progress(self) -> Dict[str, Any]:
        """Return progress toward next milestone (for dashboard display)."""
        next_milestone_at = (self.milestones_reached + 1) * WINS_PER_MILESTONE
        wins_in_current = self.total_wins - (self.milestones_reached * WINS_PER_MILESTONE)
        return {
            "current_wins": self.total_wins,
            "wins_in_current_milestone": wins_in_current,
            "wins_needed": WINS_PER_MILESTONE,
            "progress_pct": round((wins_in_current / WINS_PER_MILESTONE) * 100, 1),
            "next_milestone_number": self.milestones_reached + 1,
            "next_milestone_at": next_milestone_at,
            "base_reward": BASE_AIRDROP_AMOUNT,
        }
