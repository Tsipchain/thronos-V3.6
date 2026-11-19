"""Read-only accounting reconciliation for CPX/TimeWall BTC revenue.

The observer records Bitcoin Core evidence.  This module matches that evidence
to explicit provider statements using ``main:txid:vout``.  It never credits a
user, mints an asset, reserves funds, signs, broadcasts, or delivers deposits
to the settlement adapter.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import time
from typing import Any


PURPOSE = "earn_provider_revenue"
NETWORK = "main"
MAINNET_GENESIS_HASH = "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
REVENUE_ADDRESS = "1N5ddgzVp5it6FgxninDD1R56Rh72D9HKy"
PROVIDERS = frozenset({"cpx", "timewall"})
MINIMUM_CONFIRMATIONS = 6

OBSERVATION_PENDING = "observation_pending"
CONFIRMATION_PENDING = "confirmation_pending"
VERIFICATION_PENDING = "verification_pending"
MATCHED = "matched"
CONFLICT = "conflict"
REORG_REVIEW = "reorg_review"


class ProviderRevenueError(RuntimeError):
    pass


def _provider(value: object) -> str:
    provider = str(value or "").strip().lower()
    if provider not in PROVIDERS:
        raise ProviderRevenueError("unsupported_revenue_provider")
    return provider


def _text(value: object, error: str, limit: int) -> str:
    result = str(value or "").strip()
    if not result or len(result) > limit:
        raise ProviderRevenueError(error)
    return result


def _txid(value: object) -> str:
    result = str(value or "").strip().lower()
    if len(result) != 64 or any(char not in "0123456789abcdef" for char in result):
        raise ProviderRevenueError("invalid_revenue_txid")
    return result


def _integer(value: object, error: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ProviderRevenueError(error)
    return value


@dataclass(frozen=True)
class ProviderStatement:
    provider: str
    statement_id: str
    idempotency_key: str
    txid: str
    vout: int
    expected_sats: int
    period_ref: str


class ProviderRevenueStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self, *, readonly: bool = False) -> sqlite3.Connection:
        if readonly:
            database = Path(self.db_path).resolve()
            if not database.is_file():
                raise ProviderRevenueError("revenue_database_not_found")
            con = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=30)
        else:
            con = sqlite3.connect(self.db_path, timeout=30)
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=FULL")
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def _init_db(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS btc_provider_revenue_statements (
                    provider TEXT NOT NULL,
                    statement_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    txid TEXT NOT NULL,
                    vout INTEGER NOT NULL,
                    expected_sats INTEGER NOT NULL,
                    period_ref TEXT NOT NULL,
                    recorded_at INTEGER NOT NULL,
                    PRIMARY KEY(provider, statement_id),
                    UNIQUE(txid, vout)
                );
                CREATE TABLE IF NOT EXISTS btc_provider_revenue_reconciliation (
                    idempotency_key TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    observed_sats INTEGER,
                    confirmations INTEGER,
                    block_hash TEXT,
                    block_height INTEGER,
                    detail TEXT NOT NULL,
                    first_reviewed_at INTEGER NOT NULL,
                    last_reviewed_at INTEGER NOT NULL,
                    FOREIGN KEY(idempotency_key)
                        REFERENCES btc_provider_revenue_statements(idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS btc_provider_revenue_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    idempotency_key TEXT NOT NULL,
                    previous_status TEXT,
                    status TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    recorded_at INTEGER NOT NULL,
                    FOREIGN KEY(idempotency_key)
                        REFERENCES btc_provider_revenue_statements(idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS idx_btc_provider_revenue_status
                    ON btc_provider_revenue_reconciliation(status, last_reviewed_at);
                """
            )

    @classmethod
    def open_existing_readonly(cls, db_path: str) -> "ProviderRevenueStore":
        """Open an existing database without schema creation or WAL mutation."""
        store = cls.__new__(cls)
        store.db_path = db_path
        return store

    def record_statement(
        self,
        *,
        provider: str,
        statement_id: str,
        txid: str,
        vout: int,
        expected_sats: int,
        period_ref: str,
        recorded_at: int | None = None,
    ) -> ProviderStatement:
        provider = _provider(provider)
        statement_id = _text(statement_id, "invalid_revenue_statement_id", 200)
        txid = _txid(txid)
        vout = _integer(vout, "invalid_revenue_vout")
        expected_sats = _integer(expected_sats, "invalid_revenue_satoshi_amount", minimum=1)
        period_ref = _text(period_ref, "invalid_revenue_period_ref", 100)
        key = f"{NETWORK}:{txid}:{vout}"
        now = int(time.time()) if recorded_at is None else int(recorded_at)
        values = (provider, statement_id, key, txid, vout, expected_sats, period_ref, now)
        try:
            with self._connect() as con:
                con.execute(
                    """INSERT INTO btc_provider_revenue_statements
                       (provider, statement_id, idempotency_key, txid, vout,
                        expected_sats, period_ref, recorded_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    values,
                )
        except sqlite3.IntegrityError:
            with self._connect(readonly=True) as con:
                row = con.execute(
                    """SELECT provider, statement_id, idempotency_key, txid, vout,
                              expected_sats, period_ref
                       FROM btc_provider_revenue_statements
                       WHERE provider=? AND statement_id=?""",
                    (provider, statement_id),
                ).fetchone()
            if row is None or tuple(row) != values[:-1]:
                raise ProviderRevenueError("revenue_statement_identity_conflict")
        return ProviderStatement(*values[:-1])

    @staticmethod
    def _global_reconciliation_required(con: sqlite3.Connection) -> bool:
        if con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='btc_observer_meta'"
        ).fetchone() is None:
            return True
        rows = con.execute(
            """SELECT value FROM btc_observer_meta
               WHERE key IN ('observer_reconciliation_required','zmq_gap_detected',
                             'observer_unverified_history')"""
        ).fetchall()
        return any(int(row["value"]) != 0 for row in rows)

    def _classification(
        self, con: sqlite3.Connection, statement: sqlite3.Row
    ) -> tuple[str, str, sqlite3.Row | None]:
        if self._global_reconciliation_required(con):
            return VERIFICATION_PENDING, "observer_reconciliation_required", None
        if con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='btc_observer_deposits'"
        ).fetchone() is None:
            return VERIFICATION_PENDING, "observer_schema_unavailable", None
        event = con.execute(
            "SELECT * FROM btc_observer_deposits WHERE event_id=?",
            (f"{statement['txid']}:{int(statement['vout'])}",),
        ).fetchone()
        if event is None:
            return OBSERVATION_PENDING, "canonical_output_not_observed", None
        if (
            str(event["address"]) != REVENUE_ADDRESS
            or str(event["owner_ref"]) != PURPOSE
            or int(event["amount_sats"]) != int(statement["expected_sats"])
        ):
            return CONFLICT, "observed_output_conflicts_with_statement", event
        if int(event["requires_reconciliation"]):
            return REORG_REVIEW, "observed_output_requires_reconciliation", event
        if str(event["state"]) in {"reorged", "dropped"}:
            return REORG_REVIEW, "observed_output_reorged_or_dropped", event
        if str(event["state"]) == "credited" or event["credited_at"] is not None:
            return CONFLICT, "revenue_output_was_unexpectedly_credited", event
        if event["block_hash"] is None or event["block_height"] is None:
            return VERIFICATION_PENDING, "canonical_block_evidence_unavailable", event
        if int(event["confirmations"]) < MINIMUM_CONFIRMATIONS or str(event["state"]) != "confirmed":
            return CONFIRMATION_PENDING, "minimum_confirmations_not_reached", event
        return MATCHED, "provider_statement_matches_canonical_output", event

    def reconcile(self, idempotency_key: str, *, reviewed_at: int | None = None) -> dict[str, Any]:
        key = _text(idempotency_key, "invalid_revenue_idempotency_key", 80)
        now = int(time.time()) if reviewed_at is None else int(reviewed_at)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            statement = con.execute(
                "SELECT * FROM btc_provider_revenue_statements WHERE idempotency_key=?",
                (key,),
            ).fetchone()
            if statement is None:
                raise ProviderRevenueError("revenue_statement_not_found")
            previous = con.execute(
                "SELECT status, first_reviewed_at FROM btc_provider_revenue_reconciliation WHERE idempotency_key=?",
                (key,),
            ).fetchone()
            status, detail, event = self._classification(con, statement)
            observed_sats = int(event["amount_sats"]) if event is not None else None
            confirmations = int(event["confirmations"]) if event is not None else None
            block_hash = str(event["block_hash"]) if event is not None and event["block_hash"] else None
            block_height = int(event["block_height"]) if event is not None and event["block_height"] is not None else None
            first_reviewed = int(previous["first_reviewed_at"]) if previous else now
            con.execute(
                """INSERT INTO btc_provider_revenue_reconciliation
                   (idempotency_key, status, observed_sats, confirmations,
                    block_hash, block_height, detail, first_reviewed_at,
                    last_reviewed_at)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(idempotency_key) DO UPDATE SET
                     status=excluded.status, observed_sats=excluded.observed_sats,
                     confirmations=excluded.confirmations, block_hash=excluded.block_hash,
                     block_height=excluded.block_height, detail=excluded.detail,
                     last_reviewed_at=excluded.last_reviewed_at""",
                (key, status, observed_sats, confirmations, block_hash, block_height,
                 detail, first_reviewed, now),
            )
            previous_status = str(previous["status"]) if previous else None
            if previous_status != status:
                con.execute(
                    """INSERT INTO btc_provider_revenue_audit
                       (idempotency_key, previous_status, status, detail, recorded_at)
                       VALUES (?,?,?,?,?)""",
                    (key, previous_status, status, detail, now),
                )
        return {
            "idempotency_key": key,
            "provider": str(statement["provider"]),
            "statement_id": str(statement["statement_id"]),
            "expected_sats": int(statement["expected_sats"]),
            "observed_sats": observed_sats,
            "confirmations": confirmations,
            "status": status,
            "detail": detail,
            "credit_authorized": False,
            "delivery_authorized": False,
        }

    def reconcile_all(self, *, reviewed_at: int | None = None) -> list[dict[str, Any]]:
        """Idempotently refresh every imported provider statement."""
        with self._connect(readonly=True) as con:
            keys = [
                str(row["idempotency_key"])
                for row in con.execute(
                    "SELECT idempotency_key FROM btc_provider_revenue_statements ORDER BY recorded_at"
                ).fetchall()
            ]
        return [self.reconcile(key, reviewed_at=reviewed_at) for key in keys]

    def read_only_report(self) -> dict[str, Any]:
        """Read reconciliation state without creating schema or touching WAL."""
        with self._connect(readonly=True) as con:
            rows = con.execute(
                """SELECT s.provider, s.statement_id, s.idempotency_key,
                          s.expected_sats, s.period_ref, s.recorded_at,
                          r.status, r.observed_sats, r.confirmations,
                          r.block_hash, r.block_height, r.detail,
                          r.last_reviewed_at
                   FROM btc_provider_revenue_statements s
                   LEFT JOIN btc_provider_revenue_reconciliation r
                     ON r.idempotency_key=s.idempotency_key
                   ORDER BY s.recorded_at, s.provider, s.statement_id"""
            ).fetchall()
            counts = {
                str(row["status"] or "unreviewed"): int(row["count"])
                for row in con.execute(
                    """SELECT COALESCE(r.status, 'unreviewed') AS status, COUNT(*) AS count
                       FROM btc_provider_revenue_statements s
                       LEFT JOIN btc_provider_revenue_reconciliation r
                         ON r.idempotency_key=s.idempotency_key
                       GROUP BY COALESCE(r.status, 'unreviewed')"""
                ).fetchall()
            }
        return {
            "purpose": PURPOSE,
            "network": NETWORK,
            "address": REVENUE_ADDRESS,
            "minimum_confirmations": MINIMUM_CONFIRMATIONS,
            "counts": counts,
            "records": [dict(row) for row in rows],
            "credits_applied": 0,
            "delivery_enabled": False,
        }
