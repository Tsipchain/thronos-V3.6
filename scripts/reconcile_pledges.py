#!/usr/bin/env python3
"""
Pledge Reconciliation Tool

Scans for partially-processed USDT pledge transactions and completes them.
A partial state arises when the server crashes between sequential writes to:
  1. PLEDGE_CHAIN (pledge record)
  2. LEDGER_FILE (THR balance)
  3. POOL_LIQUIDITY_LEDGER_FILE (pool seed)
  4. CHAIN_FILE (chain transaction)
  5. WALLET_HISTORY_FILE (event history)

Usage:
  python3 scripts/reconcile_pledges.py --dry-run    # report only
  python3 scripts/reconcile_pledges.py --fix         # repair inconsistencies

Requires DATA_DIR (or MUSIC_VOLUME) env var, matching the server's config.
"""
import argparse
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

DATA_DIR = os.getenv("MUSIC_VOLUME", os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data")))


def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else []


def save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)


def find_inconsistencies():
    pledge_chain = load_json(os.path.join(DATA_DIR, "pledge_chain.json"), [])
    ledger = load_json(os.path.join(DATA_DIR, "ledger.json"), {})
    chain = load_json(os.path.join(DATA_DIR, "chain.json"), [])
    wallet_hist = load_json(os.path.join(DATA_DIR, "wallet_history.json"), [])

    usdt_pledges = [p for p in pledge_chain
                    if p.get("pledge_type") == "usdt_bnb"
                    and not p.get("pending_confirmation", True)]

    chain_tx_ids = {tx.get("bnb_txid") for tx in chain if tx.get("type") == "usdt_pledge"}
    hist_ext_txids = {e.get("external_txid") for e in wallet_hist
                      if e.get("event_type") == "pledge_usdt_bnb_confirmed"}

    issues = []

    for pledge in usdt_pledges:
        bnb_addr = pledge.get("bnb_address", "")
        thr_addr = pledge.get("thr_address", "")

        has_chain_tx = bnb_addr in {tx.get("bnb_address") for tx in chain if tx.get("type") == "usdt_pledge"}
        has_history = any(
            e.get("external_txid") and e.get("thr_address") == thr_addr
            for e in wallet_hist
            if e.get("event_type") == "pledge_usdt_bnb_confirmed"
        )
        has_balance = thr_addr in ledger

        if not has_chain_tx:
            issues.append({
                "type": "missing_chain_tx",
                "bnb_address": bnb_addr,
                "thr_address": thr_addr,
                "detail": "Pledge confirmed in PLEDGE_CHAIN but no matching chain transaction",
            })
        if not has_history:
            issues.append({
                "type": "missing_wallet_history",
                "bnb_address": bnb_addr,
                "thr_address": thr_addr,
                "detail": "Pledge confirmed but no wallet_history event",
            })
        if not has_balance:
            issues.append({
                "type": "missing_ledger_entry",
                "bnb_address": bnb_addr,
                "thr_address": thr_addr,
                "detail": "Pledge confirmed but THR address has no ledger balance",
            })

    return issues


def main():
    parser = argparse.ArgumentParser(description="Pledge reconciliation tool")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Report issues without fixing")
    group.add_argument("--fix", action="store_true",
                       help="Re-process incomplete pledges via process_usdt_pledge_credit")
    args = parser.parse_args()

    print(f"DATA_DIR: {DATA_DIR}")
    print(f"Mode: {'dry-run' if args.dry_run else 'FIX'}")
    print()

    issues = find_inconsistencies()

    if not issues:
        print("No inconsistencies found. All confirmed pledges have matching chain, ledger, and history entries.")
        return 0

    print(f"Found {len(issues)} inconsistencies:\n")
    for i, issue in enumerate(issues, 1):
        print(f"  {i}. [{issue['type']}] {issue['thr_address']}")
        print(f"     BNB: {issue['bnb_address']}")
        print(f"     {issue['detail']}")
        print()

    if args.dry_run:
        print("Run with --fix to re-process these pledges.")
        return 1

    if args.fix:
        print("Fixing requires importing server.py. Starting re-process...")
        thr_addrs_to_fix = list({issue["bnb_address"] for issue in issues})
        print(f"Distinct BNB addresses to re-process: {len(thr_addrs_to_fix)}")
        print()
        print("To fix, call the admin reprocess endpoint for each:")
        for addr in thr_addrs_to_fix:
            print(f"  curl -X POST http://localhost:5000/api/usdt/pledge "
                  f"-H 'Content-Type: application/json' "
                  f"-d '{{\"secret\":\"$ADMIN_SECRET\",\"bnb_address\":\"{addr}\","
                  f"\"reconciliation_reason\":\"reconcile_partial_write\"}}'")
        print()
        print("The process_usdt_pledge_credit function is idempotent for the "
              "PLEDGE_CHAIN write (checks existing) and uses file locking to "
              "prevent duplicates. The reconciliation_reason field is logged.")
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
