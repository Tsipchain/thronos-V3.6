"""
Pure ledger operations extracted from server.py.

These functions operate on the same JSON/SQLite data files as server.py
but do not require Flask context, auth_secret, or HTTP.  They are the
shared truth for THR wallet balances, pool reserves, pool positions,
and the tx chain.

Every function here uses the same file paths and the same
load_json/save_json semantics as server.py — they import those directly
from server so there is exactly ONE source of truth, not a copy.
"""

from __future__ import annotations

import os
import secrets
import time
from decimal import Decimal
from typing import Any


def _get_server_module():
    """Lazy import of server to avoid circular imports at module level."""
    import server
    return server


# ── THR wallet balance operations ────────────────────────────────────


def get_thr_balance(address: str) -> float:
    srv = _get_server_module()
    ledger = srv.load_json(srv.LEDGER_FILE, {})
    return float(ledger.get(address, 0.0))


def debit_thr_balance(
    from_address: str,
    to_address: str,
    amount: float,
    *,
    fee: float = 0.0,
    tx_id: str | None = None,
    speed: str = "fast",
    source: str = "escrow_settlement",
) -> dict[str, Any]:
    """
    Debit from_address and credit to_address in the authoritative
    THR ledger.  Computes and applies the network fee (burn + AI agent
    share) using the same logic as send_thr_internal.

    Returns a tx dict compatible with the tx chain format.
    Raises ValueError on insufficient balance or invalid amount.
    """
    srv = _get_server_module()

    if amount <= 0:
        raise ValueError("amount_must_be_positive")
    if not srv.validate_thr_address(from_address):
        raise ValueError(f"invalid_from_address: {from_address}")
    if not srv.validate_thr_address(to_address):
        raise ValueError(f"invalid_to_address: {to_address}")

    if fee <= 0:
        fee = srv.calculate_fixed_burn_fee(amount, speed)

    total_cost = amount + fee

    ledger = srv.load_json(srv.LEDGER_FILE, {})
    sender_balance = float(ledger.get(from_address, 0.0))

    if sender_balance < total_cost:
        raise ValueError("insufficient_thr_balance")

    ledger[from_address] = round(sender_balance - total_cost, 6)
    ledger[to_address] = round(float(ledger.get(to_address, 0.0)) + amount, 6)
    srv.save_json(srv.LEDGER_FILE, ledger)

    fee_split_info = srv.split_and_credit_fee(fee, source=source)

    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    final_tx_id = tx_id or f"TX-{int(time.time())}-{secrets.token_hex(4)}"
    tx = {
        "type": "transfer",
        "timestamp": ts,
        "from": from_address,
        "to": to_address,
        "amount": round(amount, 6),
        "fee_burned": fee,
        "fee_split": fee_split_info,
        "speed": speed,
        "tx_id": final_tx_id,
        "status": "confirmed",
        "source": source,
    }
    chain = srv.load_json(srv.CHAIN_FILE, [])
    chain.append(tx)
    srv.save_json(srv.CHAIN_FILE, chain)
    try:
        srv.persist_normalized_tx(tx)
    except RuntimeError:
        pass

    return tx


def reverse_thr_debit(
    original_tx_id: str,
    from_address: str,
    to_address: str,
    amount: float,
    *,
    reason: str = "settlement_rollback",
) -> dict[str, Any]:
    """
    Compensating transaction: credit back from_address and debit
    to_address by the transfer amount (no fee on reversals).

    Raises ValueError if to_address has insufficient balance for reversal.
    """
    srv = _get_server_module()

    ledger = srv.load_json(srv.LEDGER_FILE, {})
    to_balance = float(ledger.get(to_address, 0.0))
    if to_balance < amount:
        raise ValueError("reversal_insufficient_balance")

    ledger[to_address] = round(to_balance - amount, 6)
    ledger[from_address] = round(float(ledger.get(from_address, 0.0)) + amount, 6)
    srv.save_json(srv.LEDGER_FILE, ledger)

    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    reversal_tx_id = f"TX-REV-{int(time.time())}-{secrets.token_hex(4)}"
    tx = {
        "type": "reversal",
        "timestamp": ts,
        "from": to_address,
        "to": from_address,
        "amount": round(amount, 6),
        "fee_burned": 0.0,
        "speed": "instant",
        "tx_id": reversal_tx_id,
        "original_tx_id": original_tx_id,
        "reason": reason,
        "status": "confirmed",
    }
    chain = srv.load_json(srv.CHAIN_FILE, [])
    chain.append(tx)
    srv.save_json(srv.CHAIN_FILE, chain)
    try:
        srv.persist_normalized_tx(tx)
    except RuntimeError:
        pass

    return tx


# ── Pythia pool operations ───────────────────────────────────────────

# Canonical pool configs — imported from server at call time
def _pool_configs() -> dict:
    return _get_server_module()._POOL_CONFIGS


def credit_pythia_pool(
    pool_id: str,
    address: str,
    amount: float,
    *,
    asset: str = "THR",
    source: str = "escrow_settlement",
) -> dict[str, Any]:
    """
    Credit amount to a Pythia pool's THR reserve and record a position
    for address.  Uses the same pool ledger and position files as
    server.py.

    This does NOT debit the THR wallet — caller must do that first
    via debit_thr_balance.

    Returns dict with pool_event_id and position details.
    Raises ValueError on invalid pool or amount.
    """
    srv = _get_server_module()

    if amount <= 0:
        raise ValueError("amount_must_be_positive")

    configs = srv._POOL_CONFIGS
    if pool_id not in configs:
        raise ValueError(f"pool_not_found: {pool_id}")

    cfg = configs[pool_id]
    peid = f"POOL-{int(time.time())}-{secrets.token_hex(4).upper()}"
    now_iso = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

    ledger = srv._load_pool_ledger()
    pool = ledger[pool_id]
    pool["thr_reserve"] = round(float(pool.get("thr_reserve") or 0) + amount, 8)
    pool["last_updated"] = now_iso
    pool.setdefault("events", []).append({
        "pool_event_id": peid,
        "event_type": "pool_deposit",
        "address": address,
        "pool_id": pool_id,
        "side": "internal",
        "asset": asset,
        "amount": amount,
        "direction": "allocate",
        "status": "confirmed",
        "source": source,
        "chain": cfg["chain"],
        "asset_origin_chain": "thronos",
        "settlement_chain": "thronos",
        "timestamp": int(time.time()),
        "timestamp_iso": now_iso,
    })
    srv._save_pool_ledger(ledger)

    positions = srv._load_pool_positions()
    user_pos = positions.setdefault(address, {})
    pos = user_pos.setdefault(pool_id, {
        "address": address, "pool_id": pool_id,
        "lp_position_balance": 0.0,
        "external_side_balance": 0.0,
        "thr_side_balance": 0.0,
    })
    pos["lp_position_balance"] = round(
        float(pos.get("lp_position_balance", 0)) + amount, 8)
    pos["thr_side_balance"] = round(
        float(pos.get("thr_side_balance", 0)) + amount, 8)
    pos["last_updated"] = now_iso
    srv._save_pool_positions(positions)

    try:
        srv.add_wallet_history_event(
            thr_address=address,
            event_type="pool_deposit",
            chain=cfg["chain"],
            asset=asset,
            amount=amount,
            direction="allocate",
            internal_txid=peid,
            status="confirmed",
            note=f"Pool deposit {pool_id} side=internal {asset}={amount} source={source}",
        )
    except RuntimeError:
        pass

    return {
        "pool_event_id": peid,
        "pool_id": pool_id,
        "position": {
            "address": address,
            "pool_id": pool_id,
            "lp_position_balance": pos["lp_position_balance"],
            "thr_side_balance": pos["thr_side_balance"],
            "external_side_balance": pos["external_side_balance"],
        },
    }


def get_pool_position(address: str, pool_id: str) -> dict | None:
    srv = _get_server_module()
    positions = srv._load_pool_positions()
    user_pos = positions.get(address, {})
    return user_pos.get(pool_id)
