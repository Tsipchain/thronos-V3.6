"""Durable, read-only inbox for authenticated Train2Earn eligibility receipts.

This boundary stores independently verified eligibility evidence.  It never
credits THC, converts T2E, creates a payout, or writes to the Earn ledger.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from services.earn_gym_eligibility_proof import (
    GymProofError,
    verify_gym_eligibility,
)


class GymInboxError(ValueError):
    pass


class GymExportError(RuntimeError):
    pass


class GymEligibilitySource(Protocol):
    def fetch_eligibility(self, earn_user_ref: str) -> list[dict[str, Any]]:
        ...


@dataclass(frozen=True)
class GymReconciliationResult:
    earn_user_ref: str
    received: int
    stored: int
    idempotent: int
    credit_authorized: bool = False
    payout_enabled: bool = False

    def public_dict(self) -> dict[str, str | int | bool]:
        return {
            "earn_user_ref": self.earn_user_ref,
            "received": self.received,
            "stored": self.stored,
            "idempotent": self.idempotent,
            "credit_authorized": self.credit_authorized,
            "payout_enabled": self.payout_enabled,
        }


class GymEligibilityExportClient:
    """Authenticated, server-side reader for the standalone Gym exporter."""

    def __init__(
        self,
        base_url: str,
        export_secret: str,
        *,
        opener: Callable[..., Any] = urlopen,
        timeout: float = 5.0,
    ) -> None:
        self._base_url = str(base_url or "").strip().rstrip("/")
        self._secret = str(export_secret or "").strip()
        self._opener = opener
        self._timeout = timeout
        if not self._base_url.startswith("https://"):
            raise GymExportError("gym_export_https_required")
        if len(self._secret) < 32:
            raise GymExportError("gym_export_not_configured")

    def fetch_eligibility(self, earn_user_ref: str) -> list[dict[str, Any]]:
        if not earn_user_ref or len(earn_user_ref) > 200:
            raise GymExportError("invalid_earn_user_ref")
        request = Request(
            f"{self._base_url}/api/internal/earn/eligibility/"
            f"{quote(earn_user_ref, safe='')}",
            headers={
                "Accept": "application/json",
                "X-T2E-Earn-Export-Key": self._secret,
            },
            method="GET",
        )
        try:
            with self._opener(request, timeout=self._timeout) as response:
                raw = response.read(1_048_577)
                if len(raw) > 1_048_576:
                    raise GymExportError("gym_export_response_too_large")
                payload = json.loads(raw.decode("utf-8"))
        except GymExportError:
            raise
        except (HTTPError, URLError, OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise GymExportError("gym_export_unavailable") from exc
        if (not isinstance(payload, dict) or payload.get("ok") is not True
                or payload.get("reward_currency") != "T2E_ELIGIBILITY_ONLY"
                or not isinstance(payload.get("receipts"), list)):
            raise GymExportError("invalid_gym_export_response")
        if any(not isinstance(item, dict) for item in payload["receipts"]):
            raise GymExportError("invalid_gym_export_response")
        return payload["receipts"]


class GymEligibilityInbox:
    """Persistent evidence inbox with event and challenge-scope idempotency."""

    def __init__(self, db_path: str | Path, export_secret: str) -> None:
        self._db_path = str(db_path)
        self._secret = str(export_secret or "")
        if len(self._secret) < 32:
            raise GymInboxError("gym_bridge_not_configured")
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @contextmanager
    def _tx(self):
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self._tx() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS earn_gym_eligibility_receipts (
                    event_id       TEXT PRIMARY KEY,
                    earn_user_ref  TEXT NOT NULL,
                    tenant_id      TEXT NOT NULL,
                    challenge_id   TEXT NOT NULL,
                    reward_t2e     TEXT NOT NULL,
                    completed_at   INTEGER NOT NULL,
                    source         TEXT NOT NULL,
                    state          TEXT NOT NULL
                        CHECK(state='verified_eligibility_only'),
                    payload_sha256 TEXT NOT NULL,
                    received_at    INTEGER NOT NULL,
                    UNIQUE(earn_user_ref, tenant_id, challenge_id)
                );
                CREATE INDEX IF NOT EXISTS idx_gym_eligibility_user
                    ON earn_gym_eligibility_receipts(
                        earn_user_ref, received_at, event_id
                    );
                """
            )

    @staticmethod
    def _public(row: sqlite3.Row | dict[str, Any], *, idempotent: bool) -> dict[str, Any]:
        return {
            "event_id": row["event_id"],
            "earn_user_ref": row["earn_user_ref"],
            "tenant_id": row["tenant_id"],
            "challenge_id": row["challenge_id"],
            "reward_t2e": row["reward_t2e"],
            "completed_at": row["completed_at"],
            "source": row["source"],
            "state": row["state"],
            "idempotent": idempotent,
            "credit_authorized": False,
            "payout_enabled": False,
        }

    def ingest(
        self, receipt: dict[str, Any], *, expected_earn_user_ref: str,
    ) -> dict[str, Any]:
        try:
            verified = verify_gym_eligibility(
                receipt,
                expected_earn_user_ref=expected_earn_user_ref,
                export_secret=self._secret,
            )
        except GymProofError as exc:
            raise GymInboxError(str(exc)) from exc
        canonical = json.dumps(verified, sort_keys=True, separators=(",", ":"))
        payload_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        now = int(time.time())
        with self._tx() as connection:
            existing = connection.execute(
                "SELECT * FROM earn_gym_eligibility_receipts WHERE event_id=?",
                (verified["event_id"],),
            ).fetchone()
            if existing:
                if existing["payload_sha256"] != payload_hash:
                    raise GymInboxError("gym_event_conflict")
                return self._public(existing, idempotent=True)
            scoped = connection.execute(
                """SELECT event_id FROM earn_gym_eligibility_receipts
                   WHERE earn_user_ref=? AND tenant_id=? AND challenge_id=?""",
                (
                    verified["earn_user_ref"], verified["tenant_id"],
                    verified["challenge_id"],
                ),
            ).fetchone()
            if scoped:
                raise GymInboxError("gym_eligibility_scope_conflict")
            connection.execute(
                """INSERT INTO earn_gym_eligibility_receipts
                   (event_id, earn_user_ref, tenant_id, challenge_id,
                    reward_t2e, completed_at, source, state, payload_sha256,
                    received_at)
                   VALUES (?,?,?,?,?,?,?,'verified_eligibility_only',?,?)""",
                (
                    verified["event_id"], verified["earn_user_ref"],
                    verified["tenant_id"], verified["challenge_id"],
                    verified["reward_t2e"], verified["completed_at"],
                    verified["source"], payload_hash, now,
                ),
            )
            stored = connection.execute(
                "SELECT * FROM earn_gym_eligibility_receipts WHERE event_id=?",
                (verified["event_id"],),
            ).fetchone()
            return self._public(stored, idempotent=False)

    def for_user(self, earn_user_ref: str) -> list[dict[str, Any]]:
        if not earn_user_ref:
            raise GymInboxError("invalid_earn_user_ref")
        connection = self._connect()
        try:
            rows = connection.execute(
                """SELECT * FROM earn_gym_eligibility_receipts
                   WHERE earn_user_ref=? ORDER BY received_at,event_id""",
                (earn_user_ref,),
            ).fetchall()
            return [self._public(row, idempotent=True) for row in rows]
        finally:
            connection.close()


def reconcile_gym_eligibility(
    inbox: GymEligibilityInbox,
    source: GymEligibilitySource,
    *,
    earn_user_ref: str,
) -> GymReconciliationResult:
    """Fetch and persist eligibility only; never produce a reward ledger entry."""
    if inbox is None or source is None or not earn_user_ref:
        raise GymInboxError("gym_reconciliation_not_configured")
    receipts = source.fetch_eligibility(earn_user_ref)
    stored = 0
    idempotent = 0
    for receipt in receipts:
        result = inbox.ingest(receipt, expected_earn_user_ref=earn_user_ref)
        if result["idempotent"]:
            idempotent += 1
        else:
            stored += 1
    return GymReconciliationResult(
        earn_user_ref=earn_user_ref,
        received=len(receipts),
        stored=stored,
        idempotent=idempotent,
    )
