"""
Wallet & Pythia Pool Settlement Adapter — Interface Specification

This module defines the adapter interface that earn_account.py requires
to perform authoritative THR wallet debits and Pythia pool credits for
advertising escrow settlement.

STATUS: NOT YET IMPLEMENTED — the existing server.py primitives cannot
be safely called from earn_account.py. This file documents the exact
interface gap and what must be built to bridge it.

See PR #848 for context: the escrow intent-and-execute flow is complete
(biometric/PIN/passkey → signed intent → secp256k1 verification → nonce/
replay/idempotency checks) but final settlement writes only to the
earn_ad_escrow SQLite table. It does NOT yet debit the authoritative THR
wallet ledger or credit the Pythia pool.

────────────────────────────────────────────────────────────────────────
WHY THE EXISTING PRIMITIVES CANNOT BE CALLED DIRECTLY
────────────────────────────────────────────────────────────────────────

1. send_thr_internal (server.py:28812) — THR wallet debit
   ✗ Flask-bound: returns jsonify(), requires Flask request context
   ✗ Requires auth_secret (pledge send_secret) — the server must NEVER
     receive the user's private key, PIN, biometric data, send_secret,
     or pledge secret (hard constraint)
   ✗ Uses float arithmetic with round(..., 6) — earn_account.py uses
     Python Decimal with _THC_SCALE = Decimal("0.000001")
   ✗ Writes to JSON file (data/ledger.json) via load_json/save_json —
     no shared transaction boundary with SQLite

2. api_pools_deposit (server.py:25662) — Pythia pool credit
   ✗ HTTP endpoint (POST /api/pools/deposit), not a callable function
   ✗ Also Flask-bound with jsonify() return
   ✗ Writes to data/pool_liquidity_ledger.json and
     data/pool_positions.json via _load_pool_ledger/_save_pool_ledger
   ✗ No shared transaction boundary with SQLite

3. Storage model mismatch
   ✗ earn_account.py uses SQLite with _tx() context manager
     (BEGIN IMMEDIATE, WAL mode, atomic commit/rollback)
   ✗ Wallet ledger uses data/ledger.json (load_json/save_json)
   ✗ Pool ledger uses data/pool_liquidity_ledger.json
   ✗ Pool positions use data/pool_positions.json
   → No way to atomically commit or rollback across JSON files AND SQLite

4. Auth model mismatch
   ✗ send_thr_internal requires auth_secret (pledge send_secret hash
     verified via validate_effective_auth at server.py:2979)
   ✗ Escrow uses secp256k1 wallet-signed intents verified via
     _verify_escrow_signature — fundamentally different auth model
   ✗ The escrow service must NEVER hold the user's send_secret

────────────────────────────────────────────────────────────────────────
REQUIRED ADAPTER INTERFACE
────────────────────────────────────────────────────────────────────────

The following pure functions must be extracted or created from the
existing server.py wallet and pool code. They must:
  - Accept and return Python types (no Flask context)
  - Accept Decimal amounts (no float conversion)
  - Return structured results (no jsonify)
  - Support a compensation/rollback protocol since JSON file writes and
    SQLite writes cannot share a single ACID transaction
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


# ── Result types ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class WalletDebitResult:
    """Returned by a successful wallet debit."""
    tx_id: str                  # authoritative wallet transaction id
    from_address: str           # THR address debited
    to_address: str             # destination (e.g. PYTHIA_SYSTEM_THR_ADDRESS)
    amount: Decimal             # amount debited
    new_balance: Decimal        # sender's balance after debit
    payload_hash: str           # SHA-256 of the signed intent payload


@dataclass(frozen=True)
class PoolCreditResult:
    """Returned by a successful Pythia pool credit."""
    position_id: str            # pool position identifier
    receipt_id: str             # pool receipt/event identifier
    pool_id: str                # which Pythia pool received the credit
    amount: Decimal             # amount credited
    asset: str                  # asset identifier (e.g. "thr")


@dataclass(frozen=True)
class SettlementResult:
    """Composite result of atomic wallet debit + pool credit."""
    wallet_tx: WalletDebitResult
    pool_receipt: PoolCreditResult
    escrow_id: str              # earn_ad_escrow record id
    intent_id: str              # original signed intent id
    idempotency_key: str        # idempotency key used


class WalletInsufficientBalance(Exception):
    """Raised when the wallet address has insufficient THR balance."""
    pass


class PoolCreditFailed(Exception):
    """Raised when the Pythia pool credit fails."""
    pass


class SettlementRollbackError(Exception):
    """Raised when a rollback itself fails (requires manual intervention)."""
    pass


# ── Adapter interface ────────────────────────────────────────────────


class WalletSettlementAdapter(abc.ABC):
    """
    Abstract adapter that earn_account.py calls for authoritative
    wallet settlement.  An implementation must be wired into server.py
    where the real wallet and pool ledger functions live.

    IMPORTANT CONSTRAINTS:
    - Must NOT require auth_secret / send_secret / pledge secret
    - Must NOT require Flask request context
    - Must accept Decimal amounts (not float)
    - Auth is already handled by the escrow intent system:
      secp256k1 wallet signature verified before this adapter is called
    """

    @abc.abstractmethod
    def debit_thr(
        self,
        from_address: str,
        to_address: str,
        amount: Decimal,
        *,
        intent_id: str,
        payload_hash: str,
    ) -> WalletDebitResult:
        """
        Debit THR from from_address in the authoritative wallet ledger
        (data/ledger.json) and credit to_address.

        Must be extracted from send_thr_internal (server.py:28812) with
        these changes:
          - Remove Flask context dependency (no jsonify, no request)
          - Remove auth_secret / validate_effective_auth requirement
          - Accept Decimal, convert to float only at the JSON boundary
          - Return WalletDebitResult instead of Flask Response

        Raises WalletInsufficientBalance if from_address balance < amount.
        """
        ...

    @abc.abstractmethod
    def credit_pythia_pool(
        self,
        pool_id: str,
        from_address: str,
        amount: Decimal,
        *,
        asset: str = "thr",
        source_ref: str = "",
    ) -> PoolCreditResult:
        """
        Credit amount to the specified Pythia pool and record a position
        for from_address.

        Must be extracted from api_pools_deposit (server.py:25662) with
        these changes:
          - Remove HTTP endpoint / Flask context dependency
          - Remove send_thr_internal call (debit already handled above)
          - Accept Decimal, convert to float only at JSON boundary
          - Return PoolCreditResult instead of Flask Response

        Raises PoolCreditFailed on any pool ledger error.
        """
        ...

    @abc.abstractmethod
    def reverse_debit(
        self,
        tx_id: str,
        *,
        reason: str = "settlement_rollback",
    ) -> WalletDebitResult:
        """
        Compensating transaction: reverse a prior debit_thr by crediting
        back the original from_address.

        Used when credit_pythia_pool fails after debit_thr succeeds, to
        maintain the invariant that no THR is deducted without a
        corresponding pool position.

        Raises SettlementRollbackError if the reversal itself fails.
        """
        ...


# ── How escrow_execute will use this adapter ─────────────────────────
#
# Once implemented, escrow_execute in earn_account.py will:
#
#   1. Verify signed intent (already done — secp256k1 ECDSA)
#   2. Check nonce, expiry, replay, idempotency (already done)
#   3. Call adapter.debit_thr(advertiser_wallet, PYTHIA_SYSTEM_ADDR, amount)
#   4. Call adapter.credit_pythia_pool(pool_id, advertiser_wallet, amount)
#        → on failure: adapter.reverse_debit(wallet_tx.tx_id)
#   5. Write earn_ad_escrow row with wallet_tx_id, pool_receipt_id etc.
#        → on failure: adapter.reverse_debit(wallet_tx.tx_id)
#          (pool credit is idempotent or has its own reversal)
#
# Steps 3-5 use a COMPENSATION pattern (not a shared ACID transaction)
# because the wallet/pool JSON ledgers and SQLite cannot share a
# transaction boundary.  The pattern is:
#
#   try:
#       wallet_tx = adapter.debit_thr(...)
#       try:
#           pool_receipt = adapter.credit_pythia_pool(...)
#       except PoolCreditFailed:
#           adapter.reverse_debit(wallet_tx.tx_id)
#           raise EarnError("pool_credit_failed")
#       # ... write escrow row in SQLite ...
#   except WalletInsufficientBalance:
#       raise EarnError("insufficient_thr_balance")
#
# ── Schema additions for settlement tracking ─────────────────────────
#
# earn_ad_escrow table needs these columns:
#   wallet_tx_id        TEXT    — from WalletDebitResult.tx_id
#   pool_receipt_id     TEXT    — from PoolCreditResult.receipt_id
#   pool_position_id    TEXT    — from PoolCreditResult.position_id
#   payload_hash        TEXT    — SHA-256 of the signed intent payload
#   settlement_status   TEXT    — 'pending' | 'settled' | 'rolled_back'
#
# ── Implementation location ──────────────────────────────────────────
#
# The concrete adapter class should live in server.py (or a module
# importable from server.py) where it has direct access to:
#   - load_json / save_json  (data/ledger.json)
#   - _load_pool_ledger / _save_pool_ledger
#   - _load_pool_positions / _save_pool_positions
#   - calculate_fixed_burn_fee, split_and_credit_fee
#   - persist_normalized_tx
#   - PYTHIA_SYSTEM_THR_ADDRESS, LEDGER_FILE, etc.
#
# earn_account.py receives the adapter instance via dependency injection
# (constructor parameter), keeping it decoupled from server.py globals.
