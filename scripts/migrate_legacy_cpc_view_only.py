#!/usr/bin/env python3
"""Dry-run or explicitly execute the legacy CPC containment migration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.earn_ad_cpc_migration import (  # noqa: E402
    APPROVAL_PHRASE,
    CpcMigrationError,
    dry_run,
    execute,
)


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--backup-dir")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--operator-approval", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _arguments(argv)
    try:
        if args.execute:
            if not args.backup_dir:
                raise CpcMigrationError("backup_dir_required")
            report = execute(
                args.db_path, args.backup_dir, args.operator_approval,
            )
        else:
            report = dry_run(args.db_path)
    except (CpcMigrationError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({"ok": True, **report}, indent=2, sort_keys=True))
    if not args.execute:
        print(f"execution requires --operator-approval '{APPROVAL_PHRASE}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
