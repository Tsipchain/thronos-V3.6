"""Default-disabled accounting inbox for canonical BTC settlement commands.

This module never converts BTC into THR/THC/L2E, never changes an existing user
balance, and never activates a wallet.  It proves the downstream atomic inbox,
BTC-denominated accounting journal, audit, and eligibility-evidence boundary
using a dedicated SQLite database.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
import secrets
import sqlite3
import time
from typing import Any, Mapping, Protocol


_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_EVENT_ID = re.compile(r"^main:([0-9a-f]{64}):([0-9]+)$")

BRIDGE_PLEDGE_ELIGIBILITY = "bridge_pledge_eligibility"
BRIDGE_DEPOSIT_ACCOUNTING = "bridge_deposit_accounting"
EARN_RESERVE_SETTLEMENT = "earn_reserve_settlement"
INBOUND_PURPOSES = frozenset(
    {
        BRIDGE_PLEDGE_ELIGIBILITY,
        BRIDGE_DEPOSIT_ACCOUNTING,
        EARN_RESERVE_SETTLEMENT,
    }
)


class BtcAccountingError(RuntimeError):
    pass


@dataclass(frozen=True)
class CanonicalSettlementCommand:
    command_id: str
    idempotency_key: str
    event_id: str
    network: str
    txid: str
    vout: int
    owner_ref: str
    amount_sats: int
    proof_ref: str
    purpose: str
    registry_version: str

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "CanonicalSettlementCommand":
        network = _text(raw.get("network"), "btc_command_network_invalid", 16)
        txid = str(raw.get("txid") or "").strip().lower()
        if not _HEX64.fullmatch(txid):
            raise BtcAccountingError("btc_command_txid_invalid")
        vout = _strict_int(raw.get("vout"), "btc_command_vout_invalid")
        event_id = _text(raw.get("event_id"), "btc_command_event_id_invalid", 160)
        idempotency_key = _text(
            raw.get("idempotency_key"), "btc_command_idempotency_key_invalid", 160
        )
        expected = f"{network}:{txid}:{vout}"
        if network != "main" or event_id != expected or idempotency_key != expected:
            raise BtcAccountingError("btc_command_canonical_identity_mismatch")
        command_id = _text(raw.get("command_id"), "btc_command_id_invalid", 180)
        if command_id != f"btc-settle:{expected}":
            raise BtcAccountingError("btc_command_id_mismatch")
        purpose = _text(raw.get("purpose"), "btc_command_purpose_invalid", 80)
        if purpose not in INBOUND_PURPOSES:
            raise BtcAccountingError("btc_command_purpose_not_inbound")
        proof_ref = _text(raw.get("proof_ref"), "btc_command_proof_ref_invalid", 160)
        if not proof_ref.startswith("btcp_"):
            raise BtcAccountingError("btc_command_proof_ref_invalid")
        return cls(
            command_id=command_id,
            idempotency_key=idempotency_key,
            event_id=event_id,
            network=network,
            txid=txid,
            vout=vout,
            owner_ref=_text(raw.get("owner_ref"), "btc_command_owner_ref_invalid", 200),
            amount_sats=_strict_int(
                raw.get("amount_sats"), "btc_command_amount_invalid", minimum=1
            ),
            proof_ref=proof_ref,
            purpose=purpose,
            registry_version=_text(
                raw.get("registry_version"), "btc_command_registry_version_invalid", 128
            ),
        )


@dataclass(frozen=True)
class AccountingReceipt:
    accounting_receipt_ref: str
    command_id: str
    idempotency_key: str
    state: str
    applied_at: int


class BtcPayoutCoordinator(Protocol):
    """Interface only; no signer, broadcaster, or withdrawal is implemented."""

    def reserve(self, reservation_id: str) -> Mapping[str, Any]:
        ...

    def verify_payout(
        self,
        reservation_id: str,
        *,
        txid: str,
        expected_address: str,
        expected_amount_sat: int,
    ) -> Mapping[str, Any]:
        ...

    def reconcile(self, reservation_id: str, reason: str) -> Mapping[str, Any]:
        ...


class BtcSettlementAccountingStore:
    def __init__(
        self,
        db_path: str,
        *,
        enabled: bool = False,
        now_fn=time.time,
    ) -> None:
        self.db_path = db_path
        self.enabled = enabled
        self.now_fn = now_fn
        self._init_db()

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
                CREATE TABLE IF NOT EXISTS btc_accounting_inbox (
                    command_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    payload_sha256 TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN (
                        'applied','reconciliation_required','held'
                    )),
                    accounting_receipt_ref TEXT NOT NULL UNIQUE,
                    received_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS btc_accounting_ledger (
                    entry_id TEXT PRIMARY KEY,
                    command_id TEXT NOT NULL UNIQUE,
                    event_id TEXT NOT NULL UNIQUE,
                    owner_ref TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    amount_sats INTEGER NOT NULL,
                    proof_ref TEXT NOT NULL,
                    registry_version TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('accounted','held')),
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    FOREIGN KEY(command_id)
                        REFERENCES btc_accounting_inbox(command_id)
                );
                CREATE TABLE IF NOT EXISTS btc_wallet_eligibility_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    command_id TEXT NOT NULL UNIQUE,
                    owner_ref TEXT NOT NULL,
                    proof_ref TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('verified','held')),
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    FOREIGN KEY(command_id)
                        REFERENCES btc_accounting_inbox(command_id)
                );
                CREATE TABLE IF NOT EXISTS btc_accounting_audit (
                    audit_id TEXT PRIMARY KEY,
                    command_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_ref TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    recorded_at INTEGER NOT NULL,
                    UNIQUE(command_id, event_type, event_ref),
                    FOREIGN KEY(command_id)
                        REFERENCES btc_accounting_inbox(command_id)
                );
                """
            )

    def consume(self, command: CanonicalSettlementCommand) -> AccountingReceipt:
        if not self.enabled:
            raise BtcAccountingError("btc_accounting_disabled")
        payload = asdict(command)
        encoded = _canonical_json(payload)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        receipt_ref = "btcar_" + hashlib.sha256(
            f"{command.command_id}:{digest}".encode()
        ).hexdigest()
        now = int(self.now_fn())
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            existing = con.execute(
                "SELECT * FROM btc_accounting_inbox WHERE command_id=? OR idempotency_key=?",
                (command.command_id, command.idempotency_key),
            ).fetchone()
            if existing:
                if (
                    existing["command_id"] != command.command_id
                    or existing["payload_sha256"] != digest
                ):
                    raise BtcAccountingError("btc_accounting_idempotency_conflict")
                return _receipt(existing)

            con.execute(
                """INSERT INTO btc_accounting_inbox
                   (command_id, idempotency_key, payload_sha256, payload_json,
                    state, accounting_receipt_ref, received_at, updated_at)
                   VALUES (?,?,?,?,'applied',?,?,?)""",
                (
                    command.command_id,
                    command.idempotency_key,
                    digest,
                    encoded,
                    receipt_ref,
                    now,
                    now,
                ),
            )
            con.execute(
                """INSERT INTO btc_accounting_ledger
                   (entry_id, command_id, event_id, owner_ref, purpose,
                    amount_sats, proof_ref, registry_version, state,
                    created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,'accounted',?,?)""",
                (
                    "btcl_" + hashlib.sha256(command.command_id.encode()).hexdigest(),
                    command.command_id,
                    command.event_id,
                    command.owner_ref,
                    command.purpose,
                    command.amount_sats,
                    command.proof_ref,
                    command.registry_version,
                    now,
                    now,
                ),
            )
            if command.purpose == BRIDGE_PLEDGE_ELIGIBILITY:
                con.execute(
                    """INSERT INTO btc_wallet_eligibility_evidence
                       (evidence_id, command_id, owner_ref, proof_ref, state,
                        created_at, updated_at)
                       VALUES (?,?,?,?,'verified',?,?)""",
                    (
                        "btce_" + hashlib.sha256(command.command_id.encode()).hexdigest(),
                        command.command_id,
                        command.owner_ref,
                        command.proof_ref,
                        now,
                        now,
                    ),
                )
            _audit_in_tx(
                con,
                command.command_id,
                "accounting_applied",
                receipt_ref,
                {
                    "amount_sats": command.amount_sats,
                    "purpose": command.purpose,
                    "proof_ref": command.proof_ref,
                },
                now,
            )
            row = con.execute(
                "SELECT * FROM btc_accounting_inbox WHERE command_id=?",
                (command.command_id,),
            ).fetchone()
            return _receipt(row)

    def hold_for_reorg(self, command_id: str, *, reason: str) -> AccountingReceipt:
        reason = _text(reason, "btc_reorg_reason_invalid", 200)
        now = int(self.now_fn())
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT * FROM btc_accounting_inbox WHERE command_id=?", (command_id,)
            ).fetchone()
            if not row:
                raise BtcAccountingError("btc_accounting_command_not_found")
            if row["state"] == "held":
                return _receipt(row)
            con.execute(
                """UPDATE btc_accounting_inbox
                   SET state='reconciliation_required', updated_at=?
                   WHERE command_id=?""",
                (now, command_id),
            )
            con.execute(
                """UPDATE btc_accounting_ledger
                   SET state='held', updated_at=? WHERE command_id=?""",
                (now, command_id),
            )
            con.execute(
                """UPDATE btc_wallet_eligibility_evidence
                   SET state='held', updated_at=? WHERE command_id=?""",
                (now, command_id),
            )
            event_ref = hashlib.sha256(reason.encode()).hexdigest()
            _audit_in_tx(
                con,
                command_id,
                "reorg_hold",
                event_ref,
                {"reason": reason, "policy": "hold_without_rewrite"},
                now,
            )
            con.execute(
                """UPDATE btc_accounting_inbox SET state='held', updated_at=?
                   WHERE command_id=?""",
                (now, command_id),
            )
            return _receipt(
                con.execute(
                    "SELECT * FROM btc_accounting_inbox WHERE command_id=?",
                    (command_id,),
                ).fetchone()
            )

    def ledger_entry(self, command_id: str) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM btc_accounting_ledger WHERE command_id=?", (command_id,)
            ).fetchone()
        return dict(row) if row else None

    def eligibility_evidence(self, command_id: str) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute(
                """SELECT * FROM btc_wallet_eligibility_evidence
                   WHERE command_id=?""",
                (command_id,),
            ).fetchone()
        return dict(row) if row else None

    def audit(self, command_id: str) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                """SELECT * FROM btc_accounting_audit
                   WHERE command_id=? ORDER BY rowid""",
                (command_id,),
            ).fetchall()
        return [dict(row) for row in rows]


def _audit_in_tx(
    con: sqlite3.Connection,
    command_id: str,
    event_type: str,
    event_ref: str,
    details: Mapping[str, Any],
    now: int,
) -> None:
    con.execute(
        """INSERT INTO btc_accounting_audit
           (audit_id, command_id, event_type, event_ref, details_json, recorded_at)
           VALUES (?,?,?,?,?,?)""",
        (
            "btca_" + secrets.token_hex(12),
            command_id,
            event_type,
            event_ref,
            _canonical_json(details),
            now,
        ),
    )


def _receipt(row: sqlite3.Row) -> AccountingReceipt:
    return AccountingReceipt(
        accounting_receipt_ref=str(row["accounting_receipt_ref"]),
        command_id=str(row["command_id"]),
        idempotency_key=str(row["idempotency_key"]),
        state=str(row["state"]),
        applied_at=int(row["received_at"]),
    )


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"))


def _text(value: Any, code: str, limit: int) -> str:
    result = str(value or "").strip()
    if not result or len(result) > limit:
        raise BtcAccountingError(code)
    return result


def _strict_int(value: Any, code: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise BtcAccountingError(code)
    return value
