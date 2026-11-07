"""
Wallet & Pythia Pool Settlement Adapter

Bridges earn_account.py escrow operations to the authoritative THR wallet
ledger and Pythia pool accounting in server.py, without requiring Flask
context or auth_secret.

Auth is handled by the escrow intent system: the caller has already
verified a secp256k1 wallet signature before invoking the adapter.

The adapter uses a COMPENSATION pattern for atomicity across the JSON
wallet/pool ledgers and the SQLite escrow store:
  1. debit_thr  →  on success
  2. credit_pythia_pool  →  on failure: reverse_debit
  3. escrow row (SQLite)  →  on failure: reverse_debit

The underlying ledger functions live in services/thr_ledger.py, which
imports server.py's load_json/save_json and operates on the same data
files.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


# ── Result types ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class WalletDebitResult:
    tx_id: str
    from_address: str
    to_address: str
    amount: Decimal
    new_balance: Decimal
    fee: Decimal
    payload_hash: str


@dataclass(frozen=True)
class PoolCreditResult:
    pool_event_id: str
    position_id: str
    pool_id: str
    amount: Decimal
    lp_position_balance: Decimal
    thr_side_balance: Decimal


@dataclass(frozen=True)
class SettlementResult:
    wallet_tx: WalletDebitResult
    pool_receipt: PoolCreditResult
    escrow_id: str
    intent_id: str
    idempotency_key: str
    settlement_status: str


class WalletInsufficientBalance(Exception):
    pass


class PoolCreditFailed(Exception):
    pass


class SettlementRollbackError(Exception):
    pass


# ── Default pool for advertising escrow ──────────────────────────────

DEFAULT_AD_ESCROW_POOL = "bsc-usdt"


# ── Adapter ──────────────────────────────────────────────────────────


class WalletSettlementAdapter:
    """
    Concrete adapter for THR wallet debit and Pythia pool credit.

    Requires server.py to be importable (same process or PYTHONPATH).
    Does NOT require Flask app context or auth_secret.
    """

    def __init__(self, pool_id: str = DEFAULT_AD_ESCROW_POOL):
        self._pool_id = pool_id

    @staticmethod
    def _compute_payload_hash(intent: dict) -> str:
        signed = {
            "action": str(intent["action"]),
            "amount": str(intent["amount"]),
            "campaign_id": str(intent["campaign_id"]),
            "intent_id": str(intent["intent_id"]),
            "nonce": str(intent["nonce"]),
        }
        if intent.get("wallet_address"):
            signed["wallet_address"] = str(intent["wallet_address"])
        return hashlib.sha256(
            json.dumps(signed, sort_keys=True, separators=(",", ":")).encode(),
        ).hexdigest()

    @staticmethod
    def _get_system_address() -> str:
        import server
        return server.PYTHIA_SYSTEM_THR_ADDRESS

    def debit_thr(
        self,
        from_address: str,
        amount: Decimal,
        *,
        intent_id: str,
        payload_hash: str,
    ) -> WalletDebitResult:
        from services.thr_ledger import debit_thr_balance, get_thr_balance

        to_address = self._get_system_address()
        float_amount = float(amount)

        try:
            tx = debit_thr_balance(
                from_address, to_address, float_amount,
                source=f"ad_escrow:{intent_id}",
            )
        except ValueError as e:
            if "insufficient" in str(e):
                raise WalletInsufficientBalance(str(e)) from e
            raise

        new_bal = get_thr_balance(from_address)

        return WalletDebitResult(
            tx_id=tx["tx_id"],
            from_address=from_address,
            to_address=to_address,
            amount=Decimal(str(round(float_amount, 6))),
            new_balance=Decimal(str(new_bal)),
            fee=Decimal(str(tx["fee_burned"])),
            payload_hash=payload_hash,
        )

    def credit_pythia_pool(
        self,
        address: str,
        amount: Decimal,
        *,
        source_ref: str = "",
    ) -> PoolCreditResult:
        from services.thr_ledger import credit_pythia_pool

        float_amount = float(amount)

        try:
            result = credit_pythia_pool(
                self._pool_id, address, float_amount,
                source=f"ad_escrow:{source_ref}",
            )
        except (ValueError, Exception) as e:
            raise PoolCreditFailed(str(e)) from e

        pos = result["position"]
        position_id = f"{address}:{self._pool_id}"

        return PoolCreditResult(
            pool_event_id=result["pool_event_id"],
            position_id=position_id,
            pool_id=self._pool_id,
            amount=Decimal(str(round(float_amount, 6))),
            lp_position_balance=Decimal(str(pos["lp_position_balance"])),
            thr_side_balance=Decimal(str(pos["thr_side_balance"])),
        )

    def reverse_debit(
        self,
        tx_id: str,
        from_address: str,
        to_address: str,
        amount: Decimal,
        *,
        reason: str = "settlement_rollback",
    ) -> str:
        from services.thr_ledger import reverse_thr_debit

        try:
            tx = reverse_thr_debit(
                tx_id, from_address, to_address, float(amount),
                reason=reason,
            )
            return tx["tx_id"]
        except Exception as e:
            raise SettlementRollbackError(str(e)) from e

    def settle(
        self,
        intent: dict,
        wallet_address: str,
        amount: Decimal,
    ) -> tuple[WalletDebitResult, PoolCreditResult]:
        """
        Execute the full settlement: wallet debit + pool credit.
        On pool credit failure, automatically reverses the wallet debit.

        Returns (wallet_result, pool_result).
        Raises WalletInsufficientBalance or PoolCreditFailed.
        """
        payload_hash = self._compute_payload_hash(intent)

        wallet_tx = self.debit_thr(
            wallet_address, amount,
            intent_id=intent["intent_id"],
            payload_hash=payload_hash,
        )

        try:
            pool_receipt = self.credit_pythia_pool(
                wallet_address, amount,
                source_ref=intent["intent_id"],
            )
        except PoolCreditFailed:
            self.reverse_debit(
                wallet_tx.tx_id,
                wallet_address,
                self._get_system_address(),
                amount,
                reason=f"pool_credit_failed:{intent['intent_id']}",
            )
            raise

        return wallet_tx, pool_receipt
