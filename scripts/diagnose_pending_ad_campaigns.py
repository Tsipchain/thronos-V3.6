#!/usr/bin/env python3
"""Read-only, secret-free diagnosis for non-final ad campaigns."""

from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path
import sqlite3


_PENDING = (
    "draft", "policy_check", "manual_review", "funding_required", "approved",
    "active", "paused", "legacy_contract_review",
)
_SCALE = Decimal("0.000001")


def _sum(rows, *, escrow=False):
    total = Decimal("0")
    for row in rows:
        amount = Decimal(str(row["amount"])).quantize(_SCALE)
        if escrow and row["action"] != "deposit":
            amount = -amount
        total += amount
    return str(total.quantize(_SCALE))


def diagnose(db_path: str | Path) -> dict:
    path = Path(db_path).resolve()
    if not path.is_file():
        raise ValueError("database_not_found")
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        placeholders = ",".join("?" for _ in _PENDING)
        campaigns = connection.execute(
            f"""SELECT campaign_id, name, campaign_type, status,
                       policy_status, policy_reason, migration_state,
                       placement, total_budget, spent, pricing_version
                  FROM earn_ad_campaigns
                 WHERE status IN ({placeholders})
                 ORDER BY created_at, campaign_id""",
            _PENDING,
        ).fetchall()
        rows = []
        for campaign in campaigns:
            campaign_id = campaign["campaign_id"]
            escrow = _sum(connection.execute(
                "SELECT action, amount FROM earn_ad_escrow WHERE campaign_id=?",
                (campaign_id,),
            ).fetchall(), escrow=True)
            reserved = _sum(connection.execute(
                """SELECT amount FROM earn_thc_reservations
                   WHERE source_ref=? AND reservation_type='ad_escrow'
                     AND state IN ('reserved','settling')""",
                (campaign_id,),
            ).fetchall())
            creative_counts = {
                row["status"]: row["cnt"] for row in connection.execute(
                    """SELECT status, COUNT(*) AS cnt FROM earn_ad_creatives
                       WHERE campaign_id=? GROUP BY status""",
                    (campaign_id,),
                ).fetchall()
            }
            placement_active = bool(connection.execute(
                """SELECT 1 FROM earn_publisher_placements pp
                   JOIN earn_publishers p ON p.publisher_id=pp.publisher_id
                   WHERE pp.placement_type=? AND pp.status='active'
                     AND p.status='active' LIMIT 1""",
                (campaign["placement"],),
            ).fetchone()) or campaign["placement"] == "earn"
            rows.append({
                **dict(campaign),
                "escrow_unspent": escrow,
                "reserved_unspent": reserved,
                "escrow_reservation_match": escrow == reserved,
                "creative_counts": creative_counts,
                "placement_active": placement_active,
            })
        return {
            "mode": "read_only",
            "pending_campaign_count": len(rows),
            "campaigns": rows,
        }
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", required=True)
    args = parser.parse_args()
    try:
        result = diagnose(args.db_path)
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({"ok": True, **result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
