"""Durable local outbox for confirmed Bitcoin deposit observations.

The outbox provides at-least-once delivery with an idempotency key understood by
the adapter. It never applies balances itself.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3
import time
from typing import Any
import uuid


class BtcDepositOutboxError(RuntimeError):
    pass


@dataclass(frozen=True)
class OutboxItem:
    idempotency_key: str
    payload: dict[str, Any]
    attempts: int
    lease_until: int


class BtcDepositOutbox:
    def __init__(self, db_path: str, *, network: str, genesis_hash: str) -> None:
        self.db_path = db_path
        self.network = network
        self.genesis_hash = genesis_hash.lower()
        self._init_db()
        self.bind_network()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=FULL")
        return con

    def _init_db(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS btc_observer_identity (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    network TEXT NOT NULL,
                    genesis_hash TEXT NOT NULL,
                    bound_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS btc_deposit_outbox (
                    idempotency_key TEXT PRIMARY KEY,
                    local_event_id TEXT NOT NULL,
                    network TEXT NOT NULL,
                    genesis_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at INTEGER NOT NULL DEFAULT 0,
                    lease_until INTEGER NOT NULL DEFAULT 0,
                    claim_token TEXT,
                    last_error TEXT,
                    created_at INTEGER NOT NULL,
                    acknowledged_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_btc_outbox_delivery
                    ON btc_deposit_outbox(status, next_attempt_at, lease_until, created_at);
                """
            )

    def bind_network(self) -> None:
        now = int(time.time())
        with self._connect() as con:
            row = con.execute(
                "SELECT network, genesis_hash FROM btc_observer_identity WHERE singleton=1"
            ).fetchone()
            if row:
                if (
                    str(row["network"]) != self.network
                    or str(row["genesis_hash"]).lower() != self.genesis_hash
                ):
                    raise BtcDepositOutboxError("btc_observer_database_network_mismatch")
                return
            con.execute(
                """INSERT INTO btc_observer_identity(singleton, network, genesis_hash, bound_at)
                   VALUES(1,?,?,?)""",
                (self.network, self.genesis_hash, now),
            )

    def _global_reconciliation_required(self, con: sqlite3.Connection) -> bool:
        rows = con.execute(
            """SELECT key, value FROM btc_observer_meta
               WHERE key IN ('observer_reconciliation_required','zmq_gap_detected')"""
        ).fetchall()
        return any(int(row["value"]) != 0 for row in rows)

    def enqueue_confirmed(self, *, minimum_confirmations: int) -> int:
        """Insert missing confirmed events into the outbox.

        This is safe to call repeatedly. No event is queued while any global or
        event-level reconciliation flag is active.
        """
        now = int(time.time())
        inserted = 0
        with self._connect() as con:
            if self._global_reconciliation_required(con):
                raise BtcDepositOutboxError("btc_observer_global_reconciliation_required")

            rows = con.execute(
                """SELECT event_id, txid, vout, address, owner_ref, amount_sats,
                          confirmations, block_hash, block_height,
                          requires_reconciliation
                   FROM btc_observer_deposits
                   WHERE state='confirmed'
                     AND requires_reconciliation=0
                     AND confirmations>=?
                     AND block_hash IS NOT NULL
                     AND block_height IS NOT NULL
                   ORDER BY first_seen_at, event_id""",
                (int(minimum_confirmations),),
            ).fetchall()

            for row in rows:
                key = f"{self.network}:{row['txid']}:{int(row['vout'])}"
                payload = {
                    "network": self.network,
                    "genesis_hash": self.genesis_hash,
                    "event_id": key,
                    "idempotency_key": key,
                    "txid": str(row["txid"]),
                    "vout": int(row["vout"]),
                    "address": str(row["address"]),
                    "owner_ref": str(row["owner_ref"]),
                    "amount_sats": int(row["amount_sats"]),
                    "confirmations": int(row["confirmations"]),
                    "minimum_confirmations": int(minimum_confirmations),
                    "block_hash": str(row["block_hash"]),
                    "block_height": int(row["block_height"]),
                    "requires_reconciliation": False,
                }
                encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
                cur = con.execute(
                    """INSERT OR IGNORE INTO btc_deposit_outbox
                       (idempotency_key, local_event_id, network, genesis_hash,
                        payload_json, status, attempts, next_attempt_at,
                        lease_until, claim_token, last_error, created_at,
                        acknowledged_at)
                       VALUES (?,?,?,?,?,'pending',0,0,0,NULL,NULL,?,NULL)""",
                    (
                        key,
                        str(row["event_id"]),
                        self.network,
                        self.genesis_hash,
                        encoded,
                        now,
                    ),
                )
                inserted += int(cur.rowcount > 0)
        return inserted

    def claim_next(self, *, lease_seconds: int = 60) -> OutboxItem | None:
        now = int(time.time())
        token = uuid.uuid4().hex
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if self._global_reconciliation_required(con):
                raise BtcDepositOutboxError("btc_observer_global_reconciliation_required")

            row = con.execute(
                """SELECT o.*
                   FROM btc_deposit_outbox o
                   JOIN btc_observer_deposits d ON d.event_id=o.local_event_id
                   WHERE (
                       (o.status IN ('pending','failed') AND o.next_attempt_at<=?)
                       OR (o.status='claimed' AND o.lease_until<=?)
                   )
                     AND d.state='confirmed'
                     AND d.requires_reconciliation=0
                     AND d.block_hash IS NOT NULL
                     AND d.block_height IS NOT NULL
                   ORDER BY o.created_at, o.idempotency_key
                   LIMIT 1""",
                (now, now),
            ).fetchone()
            if row is None:
                return None

            attempts = int(row["attempts"]) + 1
            lease_until = now + max(10, int(lease_seconds))
            con.execute(
                """UPDATE btc_deposit_outbox
                   SET status='claimed', attempts=?, lease_until=?,
                       claim_token=?, last_error=NULL
                   WHERE idempotency_key=?""",
                (attempts, lease_until, token, str(row["idempotency_key"])),
            )
            payload = json.loads(str(row["payload_json"]))
            return OutboxItem(
                idempotency_key=str(row["idempotency_key"]),
                payload=payload,
                attempts=attempts,
                lease_until=lease_until,
            )

    def acknowledge(self, idempotency_key: str) -> None:
        now = int(time.time())
        with self._connect() as con:
            cur = con.execute(
                """UPDATE btc_deposit_outbox
                   SET status='acknowledged', acknowledged_at=?, lease_until=0,
                       claim_token=NULL, last_error=NULL
                   WHERE idempotency_key=? AND status='claimed'""",
                (now, idempotency_key),
            )
            if cur.rowcount != 1:
                raise BtcDepositOutboxError("btc_outbox_ack_state_conflict")

    def fail(self, idempotency_key: str, error: str) -> None:
        now = int(time.time())
        with self._connect() as con:
            row = con.execute(
                "SELECT attempts FROM btc_deposit_outbox WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            if row is None:
                raise BtcDepositOutboxError("btc_outbox_event_not_found")
            attempts = int(row["attempts"])
            delay = min(300, max(5, 2 ** min(attempts, 8)))
            con.execute(
                """UPDATE btc_deposit_outbox
                   SET status='failed', next_attempt_at=?, lease_until=0,
                       claim_token=NULL, last_error=?
                   WHERE idempotency_key=?""",
                (now + delay, str(error)[:500], idempotency_key),
            )

    def counts(self) -> dict[str, int]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT status, COUNT(*) AS n FROM btc_deposit_outbox GROUP BY status"
            ).fetchall()
        return {str(row["status"]): int(row["n"]) for row in rows}
