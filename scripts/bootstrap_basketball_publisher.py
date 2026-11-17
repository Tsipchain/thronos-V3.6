#!/usr/bin/env python3
"""Idempotently provision the canonical Basketball publisher without logging secrets."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.earn_account import EarnAccountStore, EarnError  # noqa: E402


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--earn-user-id", required=True)
    parser.add_argument(
        "--db-path",
        default=str(
            Path(os.getenv("MUSIC_VOLUME", os.getenv("DATA_DIR", "data")))
            / "earn_accounts.db"
        ),
    )
    parser.add_argument(
        "--site-url", default="https://tranfermarktbasket.com"
    )
    parser.add_argument(
        "--secret-stdin",
        action="store_true",
        help="Read one secret line from stdin instead of a hidden prompt",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = _arguments()
    identity_key = os.getenv("EARN_IDENTITY_KEY", "")
    if not identity_key:
        print("error: EARN_IDENTITY_KEY is not configured", file=sys.stderr)
        return 2

    if args.secret_stdin:
        publisher_secret = sys.stdin.readline().rstrip("\r\n")
    else:
        publisher_secret = getpass.getpass("Basketball publisher secret: ")

    try:
        store = EarnAccountStore(args.db_path, identity_key)
        result = store.bootstrap_basketball_publisher(
            args.earn_user_id, publisher_secret, args.site_url
        )
    except EarnError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        publisher_secret = ""

    print(f"publisher_id={result['publisher_id']}")
    print("publisher active: yes")
    print("sidebar placement active: yes")
    print("header interstitial placement active: yes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
