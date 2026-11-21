"""Explicit, operator-approved containment migration for legacy CPC campaigns."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any


MIGRATION_ID = "legacy-cpc-view-only-v1"
APPROVAL_PHRASE = f"APPROVE {MIGRATION_ID}"
_CANDIDATE_STATES = ("active", "paused", "approved", "funding_required")
_SCALE = Decimal("0.000001")


class CpcMigrationError(RuntimeError):
    pass


def _decimal_sum(rows: list[sqlite3.Row], *, signed: bool = False) -> Decimal:
    total = Decimal("0")
    for row in rows:
        amount = Decimal(str(row["amount"])).quantize(_SCALE)
        if signed and row["action"] != "deposit":
            amount = -amount
        total += amount
    return total.quantize(_SCALE)


def _inventory(connection: sqlite3.Connection) -> dict[str, Any]:
    connection.row_factory = sqlite3.Row
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(earn_ad_campaigns)")
    }
    required = {"migration_state", "policy_reason", "pricing_version"}
    if not required.issubset(columns):
        raise CpcMigrationError("view_only_schema_not_installed")
    campaigns = connection.execute(
        """SELECT campaign_id, status, total_budget, spent, migration_state
             FROM earn_ad_campaigns
            WHERE campaign_type='cpc'
            ORDER BY campaign_id"""
    ).fetchall()
    items = []
    reconciled = True
    candidate_count = 0
    for campaign in campaigns:
        campaign_id = str(campaign["campaign_id"])
        escrow = _decimal_sum(
            connection.execute(
                "SELECT action, amount FROM earn_ad_escrow WHERE campaign_id=?",
                (campaign_id,),
            ).fetchall(),
            signed=True,
        )
        reserved = _decimal_sum(
            connection.execute(
                """SELECT amount FROM earn_thc_reservations
                   WHERE source_ref=? AND reservation_type='ad_escrow'
                     AND state IN ('reserved','settling')""",
                (campaign_id,),
            ).fetchall(),
        )
        candidate = campaign["status"] in _CANDIDATE_STATES
        if candidate:
            candidate_count += 1
        matches = escrow >= 0 and escrow == reserved
        reconciled = reconciled and matches
        items.append({
            "campaign_id": campaign_id,
            "status": campaign["status"],
            "migration_state": campaign["migration_state"],
            "total_budget": str(Decimal(campaign["total_budget"]).quantize(_SCALE)),
            "spent": str(Decimal(campaign["spent"]).quantize(_SCALE)),
            "escrow_unspent": str(escrow),
            "reserved_unspent": str(reserved),
            "reconciled": matches,
            "candidate": candidate,
        })
    applied = False
    migration_table = connection.execute(
        """SELECT 1 FROM sqlite_master
           WHERE type='table' AND name='earn_operator_migrations'"""
    ).fetchone()
    if migration_table:
        applied = bool(connection.execute(
            "SELECT 1 FROM earn_operator_migrations WHERE migration_id=?",
            (MIGRATION_ID,),
        ).fetchone())
    return {
        "migration_id": MIGRATION_ID,
        "mode": "read_only_dry_run",
        "already_applied": applied,
        "legacy_cpc_campaigns": len(items),
        "candidate_campaigns": candidate_count,
        "escrow_reservations_reconciled": reconciled,
        "campaigns": items,
    }


def dry_run(db_path: str | Path) -> dict[str, Any]:
    path = Path(db_path).resolve()
    if not path.is_file():
        raise CpcMigrationError("database_not_found")
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        return _inventory(connection)
    finally:
        connection.close()


def _consistent_backup(db_path: Path, backup_dir: Path) -> tuple[Path, str]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"{db_path.stem}.{stamp}.{MIGRATION_ID}.sqlite3"
    source = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    destination = sqlite3.connect(backup_path)
    try:
        source.backup(destination)
        integrity = destination.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise CpcMigrationError("backup_integrity_check_failed")
    finally:
        destination.close()
        source.close()
    digest = hashlib.sha256(backup_path.read_bytes()).hexdigest()
    return backup_path, digest


def execute(
    db_path: str | Path,
    backup_dir: str | Path,
    approval: str,
) -> dict[str, Any]:
    if approval != APPROVAL_PHRASE:
        raise CpcMigrationError("operator_approval_required")
    path = Path(db_path).resolve()
    before = dry_run(path)
    if before["already_applied"]:
        return {**before, "mode": "execute", "result": "already_applied"}
    if not before["escrow_reservations_reconciled"]:
        raise CpcMigrationError("escrow_reservation_reconciliation_failed")
    backup_path, backup_sha256 = _consistent_backup(
        path, Path(backup_dir).resolve(),
    )
    connection = sqlite3.connect(path, timeout=30, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN IMMEDIATE")
        current = _inventory(connection)
        if current["already_applied"]:
            connection.execute("ROLLBACK")
            return {**current, "mode": "execute", "result": "already_applied"}
        if not current["escrow_reservations_reconciled"]:
            raise CpcMigrationError("escrow_reservation_reconciliation_changed")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS earn_operator_migrations (
                   migration_id TEXT PRIMARY KEY,
                   applied_at INTEGER NOT NULL,
                   backup_path TEXT NOT NULL,
                   backup_sha256 TEXT NOT NULL,
                   before_evidence TEXT NOT NULL
               )"""
        )
        cursor = connection.execute(
            """UPDATE earn_ad_campaigns
                  SET status='legacy_contract_review',
                      migration_state='cpc_contract_action_required',
                      policy_reason='cpc_contract_action_required',
                      pricing_version='legacy-cpc-contract'
                WHERE campaign_type='cpc'
                  AND status IN ('active','paused','approved','funding_required')"""
        )
        connection.execute(
            """INSERT INTO earn_operator_migrations
               (migration_id, applied_at, backup_path, backup_sha256,
                before_evidence)
               VALUES (?,strftime('%s','now'),?,?,?)""",
            (
                MIGRATION_ID,
                str(backup_path),
                backup_sha256,
                json.dumps(before, sort_keys=True, separators=(",", ":")),
            ),
        )
        connection.execute("COMMIT")
        changed = cursor.rowcount
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
    after = dry_run(path)
    evidence = {
        "migration_id": MIGRATION_ID,
        "mode": "execute",
        "result": "applied",
        "changed_campaigns": changed,
        "backup_path": str(backup_path),
        "backup_sha256": backup_sha256,
        "before": before,
        "after": after,
        "rollback_requires_offline_restore": True,
    }
    evidence_path = backup_path.with_suffix(".evidence.json")
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    evidence["evidence_path"] = str(evidence_path)
    return evidence
