"""
THC Reservation Interface — cross-service coordination for shared THC balance.

Problem
-------
Two independent services deduct from the same user's THC balance:

  1. **Staking** (earn_account.py) — locks THC into staking positions.
     Checks: confirmed + payable - staked - staking_fees.
     Does NOT see in-flight cashout requests.

  2. **Cashout** (earn_btc_cashout.py) — locks THC for BTC withdrawal.
     Checks: available_thc (from ThcBalanceProvider) - in-flight cashouts.
     Does NOT see active staking locks.

Because each service only sees its own locks, a concurrent stake + cashout
can together exceed the user's real available balance (double-spend on THC).

Interface
---------
A single ``ThcReservationLedger`` that both services call through. It holds
ALL current THC commitments in one place and answers "how much can this user
actually commit right now?" atomically.

Design constraints
------------------
- earn_account.py MUST NOT be edited by this PR (parallel THR stake work).
- No money movement — reservation is advisory; actual deduction stays in
  each service's own flow.
- No secrets, no simulated success.
- SQLite BEGIN IMMEDIATE for atomicity (same pattern as cashout inflight).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol


class ThcLedgerReader(Protocol):
    """Reads confirmed + payable THC for a user from the Earn ledger.

    This is the source of truth for how much THC the user has earned.
    Implemented by EarnAccountStore or a thin wrapper around it.
    """

    def gross_thc(self, earn_user_id: str) -> Decimal:
        """confirmed + payable THC (before any locks)."""
        ...


class ThcReservationLedger:
    """Unified view of all THC commitments across services.

    Each service registers its lock type. When any service wants to commit
    THC, it calls ``try_reserve`` which checks the user's gross THC against
    ALL existing reservations (staking + cashout + ad escrow + future).

    Reservation lifecycle:
        try_reserve()  → reservation_id  (THC locked)
        confirm()      → marks settled    (lock consumed)
        release()      → frees the lock   (cancelled / failed)

    Storage: single SQLite table ``thc_reservations`` in its own DB file,
    accessed with BEGIN IMMEDIATE for atomic balance checks.
    """

    # ── Lock types ──────────────────────────────────────────────────────

    LOCK_STAKING = "staking"
    LOCK_CASHOUT = "cashout"
    LOCK_AD_ESCROW = "ad_escrow"

    ACTIVE_STATES = ("reserved", "settling")

    # ── Schema ──────────────────────────────────────────────────────────

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS thc_reservations (
        reservation_id  TEXT PRIMARY KEY,
        earn_user_id    TEXT NOT NULL,
        lock_type       TEXT NOT NULL,
        thc_amount      TEXT NOT NULL,
        state           TEXT NOT NULL DEFAULT 'reserved',
        source_id       TEXT,
        created_at      INTEGER NOT NULL,
        updated_at      INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_res_user_state
        ON thc_reservations(earn_user_id, state);
    """

    # ── Core operations ─────────────────────────────────────────────────

    def try_reserve(
        self,
        *,
        earn_user_id: str,
        lock_type: str,
        thc_amount: Decimal,
        source_id: str | None = None,
    ) -> str:
        """Atomically check balance and create reservation.

        Returns reservation_id on success.
        Raises InsufficientThcError if gross_thc - total_reserved < thc_amount.

        Implementation (pseudocode inside BEGIN IMMEDIATE):
            gross = self._ledger.gross_thc(earn_user_id)
            reserved = SUM(thc_amount) FROM thc_reservations
                       WHERE earn_user_id = ? AND state IN ('reserved', 'settling')
            available = gross - reserved
            if thc_amount > available:
                raise InsufficientThcError(available=available, requested=thc_amount)
            INSERT INTO thc_reservations(...)
            return reservation_id
        """
        raise NotImplementedError("PR #881 — interface definition only")

    def confirm(self, reservation_id: str) -> None:
        """Mark reservation as settled (lock consumed by the service).

        Called after the staking position is created, or the cashout tx is
        confirmed, or the ad escrow is executed. The THC is now permanently
        committed and this reservation is no longer "in flight".
        """
        raise NotImplementedError("PR #881 — interface definition only")

    def release(self, reservation_id: str) -> None:
        """Free the reservation (service cancelled or failed).

        The THC returns to available balance.
        """
        raise NotImplementedError("PR #881 — interface definition only")

    def total_reserved(self, earn_user_id: str) -> Decimal:
        """Sum of all active reservations for the user."""
        raise NotImplementedError("PR #881 — interface definition only")

    def reservations_by_type(
        self, earn_user_id: str, lock_type: str,
    ) -> list[dict[str, Any]]:
        """List active reservations for a user filtered by lock type."""
        raise NotImplementedError("PR #881 — interface definition only")


class InsufficientThcError(Exception):
    """Raised when a reservation would exceed the user's available THC."""

    def __init__(self, *, available: Decimal, requested: Decimal) -> None:
        self.available = available
        self.requested = requested
        super().__init__(
            f"insufficient_thc:available={available}:requested={requested}"
        )


# ── Integration plan ────────────────────────────────────────────────────
#
# 1. earn_btc_cashout.py (this PR's scope):
#    - Constructor accepts optional ThcReservationLedger.
#    - request_cashout() calls try_reserve(lock_type="cashout") instead of
#      its own inflight check. Falls back to current behavior if ledger
#      is None (backward compatible).
#    - confirm_cashout() calls confirm(reservation_id).
#    - cancel/fail calls release(reservation_id).
#
# 2. earn_account.py (separate PR — do NOT edit in this PR):
#    - _available_thc_for_staking() calls total_reserved() to subtract
#      ALL cross-service locks, not just staking positions.
#    - create_stake() calls try_reserve(lock_type="staking").
#    - unstake calls release().
#
# 3. earn_thc_ad_packages.py (separate PR):
#    - Campaign activation calls try_reserve(lock_type="ad_escrow")
#      before creating the escrow intent.
#    - Escrow execution calls confirm().
#    - Campaign cancellation calls release().
#
# 4. ThcLedgerReader implementation:
#    - Thin wrapper around EarnAccountStore that reads gross THC from
#      the Earn DB (confirmed + payable rows from thc_ledger table).
#    - Does NOT subtract staking or fees — that's the reservation
#      ledger's job now.
