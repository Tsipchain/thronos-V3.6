"""
SigBalBot Milestone Airdrop — Security-hardened THR distribution.

Distributes THR tokens to active Sentinel subscribers when SigBalBot signal
wins reach milestones. Follows admin-approval pattern with full audit trail.

Flow:
  1. record_win() counts qualifying wins
  2. At milestone threshold → creates PENDING allocation batch
  3. Admin calls approve_allocation(batch_id) → APPROVED
  4. execute_approved_allocation(batch_id) processes:
     - Validates wallet format and subscriber eligibility
     - Checks treasury balance before each payout
     - Derives deterministic idempotency key per payout
     - Checks for duplicate submissions before writing
     - Writes to ledger (status=submitted)
     - Verifies chain entry (status=confirmed)
  5. Full audit trail prevents double-pay

Security invariants:
  - Never stores or logs treasury seed phrases, private keys, or auth tokens
  - Every payout carries: allocation_id, batch_id, wallet_snapshot, amount,
    chain_network_id, tx_hash, submitted_at, confirmed_at, final_status
  - Idempotency key derived from batch_id + address (deterministic)
  - Treasury balance checked before every distribution
  - Promoter commissions tracked in separate ledger file
"""
import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)

DATA_DIR = os.environ.get("DATA_DIR", "data")
LEDGER_FILE = os.path.join(DATA_DIR, "ledger.json")
CHAIN_FILE = os.path.join(DATA_DIR, "phantom_tx_chain.json")
AI_POOL_FILE = os.path.join(DATA_DIR, "ai_pool.json")
SENTINEL_SUBSCRIPTIONS_FILE = os.path.join(DATA_DIR, "sentinel_subscriptions.json")
PROMOTER_LEDGER_FILE = os.path.join(DATA_DIR, "promoter_commissions_ledger.json")

_MILESTONE_DIR = Path(os.getenv("SIGBALBOT_BRIDGE_STATE_DIR", "/app/data/sigbalbot_bridge"))
_MILESTONE_FILE = _MILESTONE_DIR / "milestone_state.json"
_ALLOCATIONS_FILE = _MILESTONE_DIR / "allocations.json"

WINS_PER_MILESTONE = 100
BASE_AIRDROP_AMOUNT = 1.0
CHAIN_NETWORK_ID = "thronos-mainnet"

_THR_ADDRESS_RE = re.compile(r"^THR[A-Za-z0-9_]{3,64}$")

AllocationStatus = Literal["pending", "approved", "submitted", "confirmed", "failed"]


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


def _utc_now_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())


def _idempotency_key(batch_id: str, address: str) -> str:
    raw = f"{batch_id}:{address}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def validate_thr_address(address: str) -> bool:
    if not address or not isinstance(address, str):
        return False
    return bool(_THR_ADDRESS_RE.match(address))


class SigBalBotMilestoneAirdrop:
    """Tracks SigBalBot qualifying wins and distributes THR at milestones
    with admin-approval gating and idempotent payout execution."""

    def __init__(self, *, dry_run: bool = False):
        self.dry_run = dry_run
        self.state = self._load_state()
        self.total_wins: int = self.state.get("total_wins", 0)
        self.milestones_reached: int = self.state.get("milestones_reached", 0)
        self.total_thr_distributed: float = self.state.get("total_thr_distributed", 0.0)
        self.last_airdrop_at: Optional[str] = self.state.get("last_airdrop_at")
        self.airdrop_history: List[Dict[str, Any]] = self.state.get("airdrop_history", [])
        self.allocations: Dict[str, Dict[str, Any]] = self._load_allocations()

    # ── State persistence ───────────────────────────────────────────────

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

    def _load_allocations(self) -> Dict[str, Dict[str, Any]]:
        if not _ALLOCATIONS_FILE.exists():
            return {}
        try:
            with open(_ALLOCATIONS_FILE) as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("[milestone-airdrop] could not load allocations: %s", exc)
            return {}

    def _save_allocations(self) -> None:
        _MILESTONE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(_ALLOCATIONS_FILE, "w") as f:
                json.dump(self.allocations, f, indent=2)
        except Exception as exc:
            logger.warning("[milestone-airdrop] could not save allocations: %s", exc)

    # ── Win recording ───────────────────────────────────────────────────

    def record_win(self, signal_id: str, symbol: str) -> Optional[Dict[str, Any]]:
        """Record a qualifying signal win. At milestone, creates a PENDING
        allocation batch (does NOT auto-distribute). Returns batch summary
        if milestone triggered, None otherwise."""
        self.total_wins += 1
        logger.info(
            "[milestone-airdrop] win #%d recorded (signal=%s, symbol=%s)",
            self.total_wins, signal_id, symbol,
        )

        expected_milestones = self.total_wins // WINS_PER_MILESTONE
        if expected_milestones > self.milestones_reached:
            milestone_number = self.milestones_reached + 1
            self.milestones_reached = expected_milestones
            result = self._create_pending_allocation(milestone_number)
            self._save_state()
            return result

        self._save_state()
        return None

    # ── Subscriber validation ───────────────────────────────────────────

    def _get_active_subscribers(self) -> List[Dict[str, Any]]:
        """Load active Sentinel subscribers with valid THR addresses.
        Excludes: expired, missing wallet, invalid wallet format."""
        subs = load_json(SENTINEL_SUBSCRIPTIONS_FILE, {})
        now_ts = int(time.time())
        active = []

        for address, sub in subs.items():
            if not address or not isinstance(sub, dict):
                continue
            if sub.get("expires_at", 0) <= now_ts:
                logger.debug("[milestone-airdrop] skip expired subscriber %s", address[:12])
                continue
            if not validate_thr_address(address):
                logger.warning("[milestone-airdrop] skip invalid wallet format: %s", address[:12])
                continue
            if not sub.get("approved", True):
                logger.debug("[milestone-airdrop] skip unapproved subscriber %s", address[:12])
                continue
            active.append({
                "address": address,
                "tier": sub.get("tier", "starter"),
                "rewards_multiplier": float(sub.get("rewards_multiplier", 1.0)),
                "expires_at": sub.get("expires_at"),
                "subscribed_at": sub.get("subscribed_at"),
            })

        return active

    # ── Treasury operations ─────────────────────────────────────────────

    def _get_treasury_balance(self) -> float:
        pool = load_json(AI_POOL_FILE, {"ai_pool_balance": 0.0})
        return float(pool.get("ai_pool_balance", 0.0))

    def _debit_treasury(self, amount: float) -> bool:
        """Debit amount from AI pool. Returns True if successful."""
        if self.dry_run:
            logger.info("[milestone-airdrop] DRY RUN: would debit %.6f THR from treasury", amount)
            return True

        pool = load_json(AI_POOL_FILE, {"ai_pool_balance": 0.0})
        balance = float(pool.get("ai_pool_balance", 0.0))
        if balance < amount:
            logger.warning(
                "[milestone-airdrop] insufficient treasury balance: %.6f < %.6f",
                balance, amount,
            )
            return False

        pool["ai_pool_balance"] = round(balance - amount, 6)
        pool["total_ai_distributed"] = round(
            float(pool.get("total_ai_distributed", 0)) + amount, 6
        )
        pool["last_distribution_time"] = _utc_now_str()
        pool["total_ai_rewards_count"] = int(pool.get("total_ai_rewards_count", 0)) + 1
        save_json(AI_POOL_FILE, pool)
        return True

    # ── Chain operations ────────────────────────────────────────────────

    def _check_existing_tx(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        """Check if a transaction with this idempotency key already exists."""
        chain = load_json(CHAIN_FILE, [])
        if not isinstance(chain, list):
            return None
        for tx in chain:
            if isinstance(tx, dict) and tx.get("idempotency_key") == idempotency_key:
                return tx
        return None

    def _verify_chain_entry(self, tx_id: str) -> bool:
        """Confirm a transaction exists in the chain file after write."""
        chain = load_json(CHAIN_FILE, [])
        if not isinstance(chain, list):
            return False
        return any(
            isinstance(tx, dict) and tx.get("tx_id") == tx_id
            for tx in chain
        )

    # ── Allocation lifecycle ────────────────────────────────────────────

    def _create_pending_allocation(self, milestone_number: int) -> Dict[str, Any]:
        """Create a PENDING allocation batch for admin review. Does NOT
        write to ledger or chain — only records what WOULD be distributed."""
        subscribers = self._get_active_subscribers()
        ts_str = _utc_now_str()
        batch_id = f"sigbal-batch-{milestone_number}-{int(time.time())}"

        payouts = []
        total_required = 0.0

        for sub in subscribers:
            address = sub["address"]
            amount = round(BASE_AIRDROP_AMOUNT * sub["rewards_multiplier"], 6)
            idem_key = _idempotency_key(batch_id, address)

            payouts.append({
                "allocation_id": f"{batch_id}-{address}",
                "address": address,
                "amount": amount,
                "chain_network_id": CHAIN_NETWORK_ID,
                "idempotency_key": idem_key,
                "wallet_snapshot": {
                    "address": address,
                    "tier": sub["tier"],
                    "rewards_multiplier": sub["rewards_multiplier"],
                    "expires_at": sub["expires_at"],
                    "subscribed_at": sub.get("subscribed_at"),
                    "snapshot_at": ts_str,
                },
                "status": "pending",
                "tx_hash": None,
                "submitted_at": None,
                "confirmed_at": None,
            })
            total_required += amount

        allocation = {
            "batch_id": batch_id,
            "milestone_number": milestone_number,
            "wins_at_milestone": milestone_number * WINS_PER_MILESTONE,
            "status": "pending",
            "created_at": ts_str,
            "approved_at": None,
            "completed_at": None,
            "active_subscribers": len(subscribers),
            "total_required_thr": round(total_required, 6),
            "total_distributed_thr": 0.0,
            "treasury_balance_at_creation": self._get_treasury_balance(),
            "payouts": payouts,
        }

        self.allocations[batch_id] = allocation
        self._save_allocations()

        logger.info(
            "[milestone-airdrop] PENDING allocation %s created — milestone #%d, "
            "%d subscribers, %.6f THR required",
            batch_id, milestone_number, len(subscribers), total_required,
        )

        return {
            "milestone_number": milestone_number,
            "batch_id": batch_id,
            "status": "pending",
            "active_subscribers": len(subscribers),
            "total_required_thr": round(total_required, 6),
            "treasury_balance": allocation["treasury_balance_at_creation"],
            "requires_admin_approval": True,
        }

    def approve_allocation(self, batch_id: str) -> Dict[str, Any]:
        """Admin approves a pending allocation for execution."""
        allocation = self.allocations.get(batch_id)
        if not allocation:
            return {"error": "allocation_not_found", "batch_id": batch_id}

        if allocation["status"] != "pending":
            return {
                "error": "invalid_status",
                "batch_id": batch_id,
                "current_status": allocation["status"],
                "message": f"Can only approve pending allocations, current={allocation['status']}",
            }

        allocation["status"] = "approved"
        allocation["approved_at"] = _utc_now_str()
        self._save_allocations()

        logger.info("[milestone-airdrop] allocation %s APPROVED by admin", batch_id)

        return {
            "batch_id": batch_id,
            "status": "approved",
            "approved_at": allocation["approved_at"],
            "total_required_thr": allocation["total_required_thr"],
            "active_subscribers": allocation["active_subscribers"],
        }

    def execute_approved_allocation(self, batch_id: str) -> Dict[str, Any]:
        """Execute an approved allocation — debits treasury, writes ledger
        and chain with full audit trail. Idempotent: skips already-confirmed
        payouts. Returns execution result."""
        allocation = self.allocations.get(batch_id)
        if not allocation:
            return {"error": "allocation_not_found", "batch_id": batch_id}

        if allocation["status"] not in ("approved", "submitted"):
            return {
                "error": "invalid_status",
                "batch_id": batch_id,
                "current_status": allocation["status"],
                "message": f"Can only execute approved/submitted allocations, current={allocation['status']}",
            }

        treasury_balance = self._get_treasury_balance()
        ts_str = _utc_now_str()

        result = {
            "batch_id": batch_id,
            "milestone_number": allocation["milestone_number"],
            "dry_run": self.dry_run,
            "treasury_balance_before": treasury_balance,
            "submitted": 0,
            "confirmed": 0,
            "skipped_duplicate": 0,
            "skipped_invalid_wallet": 0,
            "failed": 0,
            "failed_insufficient_balance": 0,
            "distributions": [],
            "total_distributed": 0.0,
            "errors": [],
        }

        allocation["status"] = "submitted"
        remaining_balance = treasury_balance

        for payout in allocation["payouts"]:
            address = payout["address"]
            amount = payout["amount"]
            idem_key = payout["idempotency_key"]

            if payout["status"] == "confirmed":
                result["skipped_duplicate"] += 1
                continue

            existing_tx = self._check_existing_tx(idem_key)
            if existing_tx:
                payout["status"] = "confirmed"
                payout["tx_hash"] = existing_tx.get("tx_id")
                payout["confirmed_at"] = existing_tx.get("timestamp")
                result["skipped_duplicate"] += 1
                logger.info(
                    "[milestone-airdrop] skip duplicate: idem_key=%s already on chain",
                    idem_key[:16],
                )
                continue

            if not validate_thr_address(address):
                payout["status"] = "failed"
                result["skipped_invalid_wallet"] += 1
                result["errors"].append({
                    "address": address[:12],
                    "reason": "invalid_wallet_format",
                })
                logger.warning("[milestone-airdrop] invalid wallet: %s", address[:12])
                continue

            if not self.dry_run and remaining_balance < amount:
                payout["status"] = "failed"
                result["failed_insufficient_balance"] += 1
                result["errors"].append({
                    "address": address[:12],
                    "reason": "insufficient_treasury_balance",
                    "required": amount,
                    "available": remaining_balance,
                })
                logger.warning(
                    "[milestone-airdrop] insufficient balance for %s: need %.6f, have %.6f",
                    address[:12], amount, remaining_balance,
                )
                continue

            if not self._debit_treasury(amount):
                payout["status"] = "failed"
                result["failed_insufficient_balance"] += 1
                result["errors"].append({
                    "address": address[:12],
                    "reason": "treasury_debit_failed",
                })
                continue

            remaining_balance -= amount
            payout["submitted_at"] = ts_str
            payout["status"] = "submitted"

            tx_hash = f"SIGBAL-AIRDROP-{allocation['milestone_number']}-{_idempotency_key(batch_id, address)[:12]}"

            if not self.dry_run:
                ledger = load_json(LEDGER_FILE, {})
                ledger[address] = round(float(ledger.get(address, 0)) + amount, 6)
                save_json(LEDGER_FILE, ledger)

                chain = load_json(CHAIN_FILE, [])
                tx = {
                    "type": "sigbalbot_milestone_airdrop",
                    "from": "ai_pool",
                    "to": address,
                    "amount": amount,
                    "timestamp": ts_str,
                    "tx_id": tx_hash,
                    "idempotency_key": idem_key,
                    "chain_network_id": CHAIN_NETWORK_ID,
                    "status": "submitted",
                    "details": {
                        "batch_id": batch_id,
                        "allocation_id": payout["allocation_id"],
                        "milestone": allocation["milestone_number"],
                        "total_wins": allocation["wins_at_milestone"],
                        "subscriber_tier": payout["wallet_snapshot"]["tier"],
                        "rewards_multiplier": payout["wallet_snapshot"]["rewards_multiplier"],
                        "base_amount": BASE_AIRDROP_AMOUNT,
                        "wallet_snapshot": payout["wallet_snapshot"],
                    },
                }
                chain.append(tx)
                save_json(CHAIN_FILE, chain)

                if self._verify_chain_entry(tx_hash):
                    payout["status"] = "confirmed"
                    payout["tx_hash"] = tx_hash
                    payout["confirmed_at"] = _utc_now_str()
                    result["confirmed"] += 1

                    chain = load_json(CHAIN_FILE, [])
                    for entry in chain:
                        if isinstance(entry, dict) and entry.get("tx_id") == tx_hash:
                            entry["status"] = "confirmed"
                            entry["confirmed_at"] = payout["confirmed_at"]
                            break
                    save_json(CHAIN_FILE, chain)
                else:
                    payout["status"] = "failed"
                    result["failed"] += 1
                    result["errors"].append({
                        "address": address[:12],
                        "reason": "chain_verification_failed",
                        "tx_hash": tx_hash,
                    })
                    logger.error(
                        "[milestone-airdrop] chain verification FAILED for tx %s",
                        tx_hash,
                    )
                    continue
            else:
                payout["status"] = "confirmed"
                payout["tx_hash"] = tx_hash
                payout["confirmed_at"] = ts_str
                result["confirmed"] += 1
                logger.info(
                    "[milestone-airdrop] DRY RUN: would distribute %.6f THR to %s",
                    amount, address[:12],
                )

            result["submitted"] += 1
            result["total_distributed"] += amount
            self.total_thr_distributed += amount

            result["distributions"].append({
                "address": address,
                "amount": amount,
                "tier": payout["wallet_snapshot"]["tier"],
                "tx_hash": tx_hash,
                "idempotency_key": idem_key,
                "status": payout["status"],
            })

            logger.info(
                "[milestone-airdrop] distributed %.6f THR to %s (tier=%s, status=%s)",
                amount, address[:12] + "...",
                payout["wallet_snapshot"]["tier"],
                payout["status"],
            )

        all_confirmed = all(p["status"] == "confirmed" for p in allocation["payouts"])
        any_failed = any(p["status"] == "failed" for p in allocation["payouts"])

        if all_confirmed:
            allocation["status"] = "confirmed"
        elif any_failed and not any(p["status"] in ("pending", "submitted") for p in allocation["payouts"]):
            allocation["status"] = "failed"

        result["total_distributed"] = round(result["total_distributed"], 6)
        allocation["total_distributed_thr"] = round(
            sum(p["amount"] for p in allocation["payouts"] if p["status"] == "confirmed"),
            6,
        )
        allocation["completed_at"] = _utc_now_str()

        self.last_airdrop_at = ts_str
        self.airdrop_history.append({
            "batch_id": batch_id,
            "milestone_number": allocation["milestone_number"],
            "status": allocation["status"],
            "total_distributed": result["total_distributed"],
            "confirmed": result["confirmed"],
            "failed": result["failed"],
            "skipped_duplicate": result["skipped_duplicate"],
            "timestamp": ts_str,
            "dry_run": self.dry_run,
        })

        self._save_state()
        self._save_allocations()

        logger.info(
            "[milestone-airdrop] execution complete — batch=%s status=%s "
            "confirmed=%d failed=%d skipped_dup=%d total=%.6f THR",
            batch_id, allocation["status"],
            result["confirmed"], result["failed"],
            result["skipped_duplicate"], result["total_distributed"],
        )

        return result

    # ── Allocation queries ──────────────────────────────────────────────

    def get_allocation(self, batch_id: str) -> Optional[Dict[str, Any]]:
        return self.allocations.get(batch_id)

    def list_allocations(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        results = []
        for batch_id, alloc in self.allocations.items():
            if status_filter and alloc.get("status") != status_filter:
                continue
            results.append({
                "batch_id": batch_id,
                "milestone_number": alloc["milestone_number"],
                "status": alloc["status"],
                "created_at": alloc["created_at"],
                "approved_at": alloc.get("approved_at"),
                "active_subscribers": alloc["active_subscribers"],
                "total_required_thr": alloc["total_required_thr"],
                "total_distributed_thr": alloc.get("total_distributed_thr", 0.0),
            })
        return results

    # ── Status and progress ─────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        next_milestone_at = (self.milestones_reached + 1) * WINS_PER_MILESTONE
        pending_count = sum(1 for a in self.allocations.values() if a["status"] == "pending")
        return {
            "total_wins": self.total_wins,
            "wins_until_next_milestone": next_milestone_at - self.total_wins,
            "milestones_reached": self.milestones_reached,
            "next_milestone_at": next_milestone_at,
            "total_thr_distributed": round(self.total_thr_distributed, 6),
            "last_airdrop_at": self.last_airdrop_at,
            "active_subscribers": len(self._get_active_subscribers()),
            "pending_allocations": pending_count,
            "dry_run": self.dry_run,
        }

    def get_progress(self) -> Dict[str, Any]:
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
