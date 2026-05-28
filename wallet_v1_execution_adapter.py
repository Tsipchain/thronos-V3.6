"""Wallet V1 execution adapter.

Executes already-verified signed transactions using the same persistence
primitives used by production transfer routes in server.py.
"""

from __future__ import annotations

import secrets
import time
from typing import Any, Dict, Tuple

import server as server_module


def execute_verified_signed_transfer(signed_tx: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], int]:
    """Execute a verified THR transfer and persist to chain + tx log."""
    from_thr = (signed_tx.get("from") or "").strip()
    to_thr = (signed_tx.get("to") or "").strip()
    amount = float(signed_tx.get("amount") or 0.0)
    speed = (signed_tx.get("speed") or "fast").lower()
    tx_id = (signed_tx.get("nonce") or "").strip() or f"TX-{int(time.time())}-{secrets.token_hex(4)}"

    if not server_module.validate_thr_address(from_thr):
        return False, {"ok": False, "error": "invalid_from_address"}, 400
    if not server_module.validate_thr_address(to_thr):
        return False, {"ok": False, "error": "invalid_to_address"}, 400

    fee = server_module.calculate_fixed_burn_fee(amount, speed)
    total_cost = amount + fee

    ledger = server_module.load_json(server_module.LEDGER_FILE, {})
    sender_balance = float(ledger.get(from_thr, 0.0))
    if sender_balance < total_cost:
        return False, {
            "ok": False,
            "error": "insufficient_balance",
            "balance": round(sender_balance, 6),
            "required": round(total_cost, 6),
        }, 400

    ledger[from_thr] = round(sender_balance - total_cost, 6)
    ledger[to_thr] = round(float(ledger.get(to_thr, 0.0)) + amount, 6)
    server_module.save_json(server_module.LEDGER_FILE, ledger)
    fee_split_info = server_module.split_and_credit_fee(fee, source="wallet_v1_signed")

    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    tx = {
        "type": "transfer",
        "timestamp": ts,
        "from": from_thr,
        "to": to_thr,
        "amount": round(amount, 6),
        "fee_burned": fee,
        "fee_split": fee_split_info,
        "speed": speed,
        "tx_id": tx_id,
        "status": "confirmed",
        "source": "wallet_v1_signed",
    }

    chain = server_module.load_json(server_module.CHAIN_FILE, [])
    chain.append(tx)
    server_module.save_json(server_module.CHAIN_FILE, chain)
    server_module.persist_normalized_tx(tx)

    return True, {
        "ok": True,
        "accepted": True,
        "status": "confirmed",
        "tx": tx,
        "tx_id": tx_id,
        "new_balance": ledger[from_thr],
        "fee": fee,
        "fee_split": fee_split_info,
    }, 200
