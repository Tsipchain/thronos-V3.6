"""Transactional, idempotent BTC pledge credits for the Thronos Master ledger.

A confirmed BTC txid may arrive more than once when a watcher retries after a timeout.
The txid journal and THR balance increment therefore commit in the same SQLite transaction.
The chain JSON is a downstream materialized view and can be repaired from the journal.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any


def _normalized_payload(btc_address: str, thr_address: str, btc_amount: float, thr_amount: float) -> dict[str, Any]:
    return {
        "btc_address": str(btc_address),
        "thr_address": str(thr_address),
        "btc_amount": round(float(btc_amount), 8),
        "thr_amount": round(float(thr_amount), 6),
    }


def _payload_hash(payload: dict[str, Any]) -> str:
    packed = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(packed.encode("utf-8")).hexdigest()


def _ensure_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS btc_pledge_idempotency (
            btc_txid TEXT PRIMARY KEY,
            payload_hash TEXT NOT NULL,
            tx_json TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
        """
    )
    conn.commit()


def _ledger_snapshot(conn) -> dict[str, float]:
    rows = conn.execute(
        "SELECT address, balance FROM balances WHERE ledger_type = ?",
        ("thr",),
    ).fetchall()
    return {str(row["address"] if hasattr(row, "keys") else row[0]): float(row["balance"] if hasattr(row, "keys") else row[1]) for row in rows}


def _current_balance(conn, thr_address: str) -> float:
    row = conn.execute(
        "SELECT balance FROM balances WHERE ledger_type = ? AND address = ?",
        ("thr", thr_address),
    ).fetchone()
    if row is None:
        return 0.0
    return float(row["balance"] if hasattr(row, "keys") else row[0])


def credit_btc_pledge_once(
    conn,
    *,
    btc_txid: str,
    btc_address: str,
    thr_address: str,
    btc_amount: float,
    thr_amount: float,
    tx_record: dict[str, Any],
    now_ts: int | None = None,
) -> dict[str, Any]:
    """Atomically credit THR once for a BTC txid and persist the recovery record."""
    _ensure_table(conn)
    payload = _normalized_payload(btc_address, thr_address, btc_amount, thr_amount)
    digest = _payload_hash(payload)
    now = int(time.time()) if now_ts is None else int(now_ts)

    conn.execute("BEGIN IMMEDIATE")
    try:
        existing = conn.execute(
            "SELECT payload_hash, tx_json FROM btc_pledge_idempotency WHERE btc_txid = ?",
            (btc_txid,),
        ).fetchone()
        if existing is not None:
            stored_hash = existing["payload_hash"] if hasattr(existing, "keys") else existing[0]
            stored_json = existing["tx_json"] if hasattr(existing, "keys") else existing[1]
            stored_tx = json.loads(stored_json)
            if stored_hash != digest:
                conn.rollback()
                return {"status": "conflict", "reason": "btc_txid_payload_conflict"}
            conn.rollback()
            return {
                "status": "duplicate",
                "tx_record": stored_tx,
                "new_balance": _current_balance(conn, thr_address),
                "ledger": _ledger_snapshot(conn),
            }

        current = _current_balance(conn, thr_address)
        new_balance = round(current + payload["thr_amount"], 6)
        conn.execute(
            """
            INSERT INTO balances (ledger_type, address, balance, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ledger_type, address)
            DO UPDATE SET balance = excluded.balance, updated_at = excluded.updated_at
            """,
            ("thr", thr_address, new_balance, now),
        )
        conn.execute(
            """
            INSERT INTO btc_pledge_idempotency (btc_txid, payload_hash, tx_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (btc_txid, digest, json.dumps(tx_record, sort_keys=True), now),
        )
        conn.commit()
        return {
            "status": "created",
            "tx_record": tx_record,
            "new_balance": new_balance,
            "ledger": _ledger_snapshot(conn),
        }
    except Exception:
        conn.rollback()
        raise


def record_existing_btc_pledge_without_credit(
    conn,
    *,
    btc_txid: str,
    btc_address: str,
    thr_address: str,
    btc_amount: float,
    thr_amount: float,
    tx_record: dict[str, Any],
    now_ts: int | None = None,
) -> dict[str, Any]:
    """Adopt a pre-journal chain record without incrementing the balance again."""
    _ensure_table(conn)
    payload = _normalized_payload(btc_address, thr_address, btc_amount, thr_amount)
    digest = _payload_hash(payload)
    now = int(time.time()) if now_ts is None else int(now_ts)

    conn.execute("BEGIN IMMEDIATE")
    try:
        existing = conn.execute(
            "SELECT payload_hash, tx_json FROM btc_pledge_idempotency WHERE btc_txid = ?",
            (btc_txid,),
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO btc_pledge_idempotency (btc_txid, payload_hash, tx_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (btc_txid, digest, json.dumps(tx_record, sort_keys=True), now),
            )
            conn.commit()
            return {
                "status": "duplicate",
                "tx_record": tx_record,
                "new_balance": _current_balance(conn, thr_address),
                "ledger": _ledger_snapshot(conn),
            }

        stored_hash = existing["payload_hash"] if hasattr(existing, "keys") else existing[0]
        stored_json = existing["tx_json"] if hasattr(existing, "keys") else existing[1]
        stored_tx = json.loads(stored_json)
        if stored_hash != digest:
            conn.rollback()
            return {"status": "conflict", "reason": "btc_txid_payload_conflict"}
        if stored_tx.get("tx_id") != tx_record.get("tx_id"):
            conn.rollback()
            return {"status": "conflict", "reason": "btc_txid_registry_mismatch"}
        conn.rollback()
        return {
            "status": "duplicate",
            "tx_record": stored_tx,
            "new_balance": _current_balance(conn, thr_address),
            "ledger": _ledger_snapshot(conn),
        }
    except Exception:
        conn.rollback()
        raise
