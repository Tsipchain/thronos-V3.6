"""XRPL Bridge Blueprint — receive deposit notifications from the XRPL watcher.

Endpoints are internal-only (require GATEWAY_SECRET). The watcher service
detects deposits on the XRPL trust address and calls these endpoints to
record them in the crosschain event bus.

No signing happens here. No funds are moved. This Blueprint only records
deposit events for downstream processing (wrapped-token minting, etc.).
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from flask import Blueprint, jsonify, request

logger = logging.getLogger("xrpl_bridge")

xrpl_bridge_bp = Blueprint("xrpl_bridge", __name__)

_GATEWAY_SECRET = os.getenv("GATEWAY_SECRET", "")
_DATA_DIR = os.getenv("DATA_DIR", "data")
_XRPL_DEPOSITS_FILE = os.path.join(_DATA_DIR, "xrpl_deposits.json")


def _require_internal(f):
    """Decorator: require GATEWAY_SECRET in X-Internal-Key header."""
    from functools import wraps

    @wraps(f)
    def wrapper(*args, **kwargs):
        key = request.headers.get("X-Internal-Key", "")
        if not _GATEWAY_SECRET or key != _GATEWAY_SECRET:
            return jsonify(error="Unauthorized"), 401
        return f(*args, **kwargs)

    return wrapper


def _load_deposits() -> list[dict]:
    path = Path(_XRPL_DEPOSITS_FILE)
    if path.exists():
        return json.loads(path.read_text())
    return []


def _save_deposits(deposits: list[dict]) -> None:
    path = Path(_XRPL_DEPOSITS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(deposits, indent=2))


@xrpl_bridge_bp.route("/api/bridge/xrpl/deposit", methods=["POST"])
@_require_internal
def receive_xrpl_deposit():
    """Record an XRPL deposit notification from the watcher service."""
    data = request.get_json(silent=True) or {}

    tx_hash = data.get("tx_hash", "").strip()
    if not tx_hash:
        return jsonify(error="tx_hash required"), 400

    currency = data.get("currency", "").strip()
    amount = data.get("amount", "0")
    sender = data.get("sender", "").strip()

    deposits = _load_deposits()
    existing = {d["tx_hash"] for d in deposits}
    if tx_hash in existing:
        return jsonify(status="duplicate", tx_hash=tx_hash), 200

    entry = {
        "tx_hash": tx_hash,
        "ledger_index": data.get("ledger_index"),
        "sender": sender,
        "currency": currency,
        "amount": str(amount),
        "destination_tag": data.get("destination_tag"),
        "timestamp": data.get("timestamp"),
        "received_at": int(time.time()),
        "status": "pending_mint",
    }
    deposits.append(entry)
    _save_deposits(deposits)

    logger.info("XRPL deposit recorded: %s %s from %s (tx %s)", amount, currency, sender, tx_hash)

    return jsonify(status="recorded", tx_hash=tx_hash, currency=currency, amount=str(amount)), 201


@xrpl_bridge_bp.route("/api/bridge/xrpl/deposits", methods=["GET"])
@_require_internal
def list_xrpl_deposits():
    """List recorded XRPL deposits."""
    deposits = _load_deposits()
    status_filter = request.args.get("status")
    if status_filter:
        deposits = [d for d in deposits if d.get("status") == status_filter]

    limit = min(int(request.args.get("limit", 50)), 200)
    return jsonify(
        total=len(deposits),
        deposits=deposits[-limit:],
    )


@xrpl_bridge_bp.route("/api/bridge/xrpl/stats", methods=["GET"])
@_require_internal
def xrpl_bridge_stats():
    """Summary stats for the XRPL bridge."""
    deposits = _load_deposits()
    by_status: dict[str, int] = {}
    by_currency: dict[str, str] = {}
    for d in deposits:
        s = d.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1
        c = d.get("currency", "XRP")
        from decimal import Decimal
        by_currency[c] = str(
            Decimal(by_currency.get(c, "0")) + Decimal(d.get("amount", "0"))
        )

    return jsonify(
        total_deposits=len(deposits),
        by_status=by_status,
        by_currency=by_currency,
    )
