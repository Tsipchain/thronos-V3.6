"""XRPL Watcher Service — read-only bridge monitor for GRD/XRP deposits.

Monitors an XRPL trust address for incoming payments and GRD token
transfers. When a deposit is confirmed, records it in a local ledger
and (when enabled) notifies the ThronosChain API to mint wrapped tokens.

DISABLED by default — set XRPL_WATCHER_ENABLED=true to activate.

This service is READ-ONLY: it never signs or submit XRPL transactions.
Signing (Ed25519) is handled by a separate service with env-var keys
that are never stored in source code.

Environment variables:
    XRPL_WATCHER_ENABLED    - "true" to activate (default: "false")
    XRPL_NODE_URL           - WebSocket URL of XRPL node (default: wss://xrplcluster.com)
    XRPL_TRUST_ADDRESS      - XRPL address to monitor for deposits
    XRPL_GRD_ISSUER         - XRPL issuer address for GRD trustline
    XRPL_POLL_SECONDS       - Poll interval in seconds (default: 10)
    XRPL_LEDGER_FILE        - Local ledger file (default: data/xrpl_watcher_ledger.json)
    THRONOS_API_URL         - ThronosChain API for mint notifications
    XRPL_MIN_CONFIRMATIONS  - Ledgers to wait before confirming (default: 1)
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

logger = logging.getLogger("xrpl_watcher")

_ENABLED = os.getenv("XRPL_WATCHER_ENABLED", "false").lower() == "true"
_NODE_URL = os.getenv("XRPL_NODE_URL", "wss://xrplcluster.com")
_TRUST_ADDRESS = os.getenv("XRPL_TRUST_ADDRESS", "")
_GRD_ISSUER = os.getenv("XRPL_GRD_ISSUER", "")
_POLL_SECONDS = int(os.getenv("XRPL_POLL_SECONDS", "10"))
_LEDGER_FILE = os.getenv("XRPL_LEDGER_FILE", "data/xrpl_watcher_ledger.json")
_API_URL = os.getenv("THRONOS_API_URL", "http://localhost:5000")
_MIN_CONFIRMATIONS = int(os.getenv("XRPL_MIN_CONFIRMATIONS", "1"))


def _load_ledger() -> list[dict]:
    path = Path(_LEDGER_FILE)
    if path.exists():
        return json.loads(path.read_text())
    return []


def _save_ledger(entries: list[dict]) -> None:
    path = Path(_LEDGER_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2))


def _processed_hashes(ledger: list[dict]) -> set[str]:
    return {e["xrpl_tx_hash"] for e in ledger}


class XRPLDepositEvent:
    """Represents a detected deposit on XRPL."""

    __slots__ = (
        "tx_hash", "ledger_index", "sender", "currency", "issuer",
        "amount", "destination_tag", "timestamp",
    )

    def __init__(self, *, tx_hash: str, ledger_index: int, sender: str,
                 currency: str, issuer: str, amount: Decimal,
                 destination_tag: int | None, timestamp: int):
        self.tx_hash = tx_hash
        self.ledger_index = ledger_index
        self.sender = sender
        self.currency = currency
        self.issuer = issuer
        self.amount = amount
        self.destination_tag = destination_tag
        self.timestamp = timestamp

    def to_dict(self) -> dict:
        return {
            "xrpl_tx_hash": self.tx_hash,
            "ledger_index": self.ledger_index,
            "sender": self.sender,
            "currency": self.currency,
            "issuer": self.issuer,
            "amount": str(self.amount),
            "destination_tag": self.destination_tag,
            "timestamp": self.timestamp,
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "status": "detected",
        }


def parse_payment_tx(tx: dict, meta: dict) -> XRPLDepositEvent | None:
    """Parse an XRPL Payment transaction into a deposit event.

    Returns None if the transaction is not a payment to our trust address
    or if it's not the right currency.
    """
    if tx.get("TransactionType") != "Payment":
        return None
    if tx.get("Destination") != _TRUST_ADDRESS:
        return None

    amount = tx.get("Amount")
    if amount is None:
        return None

    if isinstance(amount, str):
        return XRPLDepositEvent(
            tx_hash=tx.get("hash", ""),
            ledger_index=meta.get("ledger_index", 0),
            sender=tx.get("Account", ""),
            currency="XRP",
            issuer="",
            amount=Decimal(amount) / Decimal("1000000"),
            destination_tag=tx.get("DestinationTag"),
            timestamp=tx.get("date", 0),
        )

    if isinstance(amount, dict):
        currency = amount.get("currency", "")
        issuer = amount.get("issuer", "")
        if currency == "GRD" and issuer == _GRD_ISSUER:
            return XRPLDepositEvent(
                tx_hash=tx.get("hash", ""),
                ledger_index=meta.get("ledger_index", 0),
                sender=tx.get("Account", ""),
                currency="GRD",
                issuer=issuer,
                amount=Decimal(amount.get("value", "0")),
                destination_tag=tx.get("DestinationTag"),
                timestamp=tx.get("date", 0),
            )

    return None


def fetch_account_transactions(marker: str | None = None) -> tuple[list[dict], str | None]:
    """Fetch recent transactions for the trust address via XRPL JSON-RPC.

    Uses the HTTP fallback (s1.ripple.com) instead of WebSocket for
    simplicity in the polling model. Returns (transactions, next_marker).
    """
    import requests

    http_url = os.getenv("XRPL_HTTP_URL", "https://s1.ripple.com:51234/")
    payload = {
        "method": "account_tx",
        "params": [{
            "account": _TRUST_ADDRESS,
            "ledger_index_min": -1,
            "ledger_index_max": -1,
            "limit": 50,
            "forward": False,
        }],
    }
    if marker:
        payload["params"][0]["marker"] = marker

    try:
        resp = requests.post(http_url, json=payload, timeout=15)
        resp.raise_for_status()
        result = resp.json().get("result", {})
        txs = result.get("transactions", [])
        next_marker = result.get("marker")
        return txs, next_marker
    except Exception as exc:
        logger.error("XRPL fetch failed: %s", exc)
        return [], None


def check_deposits() -> list[XRPLDepositEvent]:
    """Poll XRPL for new deposits to the trust address."""
    if not _TRUST_ADDRESS:
        logger.warning("XRPL_TRUST_ADDRESS not set, skipping")
        return []

    ledger = _load_ledger()
    seen = _processed_hashes(ledger)
    new_events: list[XRPLDepositEvent] = []

    txs, _ = fetch_account_transactions()
    for tx_wrapper in txs:
        tx = tx_wrapper.get("tx", {})
        meta = tx_wrapper.get("meta", {})

        if meta.get("TransactionResult") != "tesSUCCESS":
            continue

        if tx.get("hash", "") in seen:
            continue

        event = parse_payment_tx(tx, meta)
        if event:
            new_events.append(event)
            ledger.append(event.to_dict())
            seen.add(event.tx_hash)
            logger.info(
                "Deposit detected: %s %s from %s (tx %s)",
                event.amount, event.currency, event.sender, event.tx_hash,
            )

    if new_events:
        _save_ledger(ledger)

    return new_events


def notify_thronos(event: XRPLDepositEvent) -> bool:
    """Notify ThronosChain API about a confirmed XRPL deposit.

    The API decides whether to mint wrapped tokens. This function
    only sends the notification — it never creates tokens directly.
    """
    import requests

    gateway_secret = os.getenv("GATEWAY_SECRET", "")
    if not gateway_secret:
        logger.warning("GATEWAY_SECRET not set, skipping notification for %s", event.tx_hash)
        return False

    try:
        resp = requests.post(
            f"{_API_URL}/api/bridge/xrpl/deposit",
            json={
                "tx_hash": event.tx_hash,
                "ledger_index": event.ledger_index,
                "sender": event.sender,
                "currency": event.currency,
                "amount": str(event.amount),
                "destination_tag": event.destination_tag,
                "timestamp": event.timestamp,
            },
            headers={
                "X-Internal-Key": gateway_secret,
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        if resp.status_code < 300:
            logger.info("ThronosChain notified for %s", event.tx_hash)
            return True
        else:
            logger.error("ThronosChain notification failed: HTTP %d", resp.status_code)
            return False
    except Exception as exc:
        logger.error("ThronosChain notification error: %s", exc)
        return False


def run_cycle() -> dict:
    """Run one watcher cycle: check deposits and notify."""
    if not _ENABLED:
        return {"status": "disabled"}

    events = check_deposits()
    notified = 0
    for event in events:
        if notify_thronos(event):
            notified += 1

    return {
        "status": "ok",
        "deposits_found": len(events),
        "notified": notified,
    }


def run_watcher() -> None:
    """Main loop — polls XRPL at the configured interval."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    if not _ENABLED:
        logger.info("XRPL watcher disabled (set XRPL_WATCHER_ENABLED=true)")
        return

    if not _TRUST_ADDRESS:
        logger.error("XRPL_TRUST_ADDRESS not configured")
        return

    logger.info("XRPL watcher started — monitoring %s every %ds", _TRUST_ADDRESS, _POLL_SECONDS)

    while True:
        try:
            result = run_cycle()
            if result.get("deposits_found"):
                logger.info("Cycle result: %s", result)
        except Exception as exc:
            logger.exception("Watcher cycle error: %s", exc)
        time.sleep(_POLL_SECONDS)


if __name__ == "__main__":
    run_watcher()
