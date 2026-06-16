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


def execute_verified_signed_token_transfer(symbol: str, signed_tx: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], int]:
    """Execute a verified custom-token transfer and persist to chain + tx log.

    Mirrors server_module.transfer_custom_token, but skips the legacy
    auth_secret/BTC-pledge gate (validate_effective_auth) because ownership
    of `from_thr` was already proven upstream via ECDSA signature
    verification (verify_signed_transaction_core) — re-imposing the pledge
    requirement here would defeat the purpose of the V1 signed-envelope flow.
    """
    from_thr = (signed_tx.get("from") or "").strip()
    to_thr = (signed_tx.get("to") or "").strip()
    speed = (signed_tx.get("speed") or "fast").lower()

    try:
        amount = float(signed_tx.get("amount") or 0.0)
    except (TypeError, ValueError):
        return False, {"ok": False, "error": "invalid_amount"}, 400

    if not server_module.validate_thr_address(from_thr):
        return False, {"ok": False, "error": "invalid_from_address"}, 400
    if not server_module.validate_thr_address(to_thr):
        return False, {"ok": False, "error": "invalid_to_address"}, 400
    if amount <= 0:
        return False, {"ok": False, "error": "invalid_amount"}, 400

    tokens = server_module.load_custom_tokens()
    token = tokens.get(symbol)
    if not token:
        return False, {"ok": False, "error": f"Token {symbol} not found"}, 404
    if not token.get("transferable", True):
        return False, {"ok": False, "error": "This token is not transferable"}, 403

    token_ledger = server_module.load_custom_token_ledger(token["id"])
    sender_token_balance = float(token_ledger.get(from_thr, 0.0))
    if sender_token_balance < amount:
        return False, {
            "ok": False,
            "error": f"Insufficient {symbol} balance",
            "balance": round(sender_token_balance, token["decimals"]),
            "required": amount,
        }, 400

    if speed == "slow":
        thr_fee = round(max(0.001, amount * 0.0009), 6)
    else:
        thr_fee = round(max(0.001, server_module.calculate_dynamic_fee(amount)), 6)

    thr_ledger = server_module.load_json(server_module.LEDGER_FILE, {})
    sender_thr_balance = float(thr_ledger.get(from_thr, 0.0))
    if sender_thr_balance < thr_fee:
        return False, {
            "ok": False,
            "error": "Insufficient THR balance for transaction fee",
            "thr_balance": round(sender_thr_balance, 6),
            "fee_required": thr_fee,
            "token_balance": round(sender_token_balance, token["decimals"]),
        }, 400

    thr_ledger[from_thr] = round(sender_thr_balance - thr_fee, 6)
    server_module.save_json(server_module.LEDGER_FILE, thr_ledger)

    token_ledger[from_thr] = round(sender_token_balance - amount, token["decimals"])
    token_ledger[to_thr] = round(float(token_ledger.get(to_thr, 0.0)) + amount, token["decimals"])
    server_module.save_custom_token_ledger(token["id"], token_ledger)

    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    tx_id = (signed_tx.get("nonce") or "").strip() or f"TOKEN_TRANSFER-{symbol}-{int(time.time())}-{secrets.token_hex(4)}"
    tx = {
        "type": "token_transfer",
        "kind": "token_transfer",
        "category": "tokens",
        "token_symbol": symbol,
        "asset_symbol": symbol,
        "asset": symbol,
        "token_id": token["id"],
        "from": from_thr,
        "to": to_thr,
        "amount": round(amount, token["decimals"]),
        "fee_burned_thr": thr_fee,
        "speed": speed,
        "timestamp": ts,
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
        "new_balance": token_ledger[from_thr],
        "new_thr_balance": thr_ledger[from_thr],
        "fee": thr_fee,
        "fee_burned": thr_fee,
    }, 200
