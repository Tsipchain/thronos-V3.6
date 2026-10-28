#!/usr/bin/env python3
"""
Pledge Reconciliation Tool

Scans for partially-processed USDT pledge transactions and reports or repairs
them. A partial state arises when the server crashes between sequential writes:
  1. PLEDGE_CHAIN (pledge record)
  2. LEDGER_FILE (THR balance)
  3. POOL_LIQUIDITY_LEDGER_FILE (pool seed)
  4. CHAIN_FILE (chain transaction)
  5. WALLET_HISTORY_FILE (event history)

Usage:
  python3 scripts/reconcile_pledges.py --dry-run     # report only
  python3 scripts/reconcile_pledges.py --suggest      # report + print curl commands
  python3 scripts/reconcile_pledges.py --repair       # idempotent repair via admin API

Requires DATA_DIR (or MUSIC_VOLUME) env var, matching the server's config.
For --repair, ADMIN_SECRET and the running server URL are required.
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


def find_inconsistencies():
    pledge_chain = load_json(os.path.join(DATA_DIR, "pledge_chain.json"), [])
    ledger = load_json(os.path.join(DATA_DIR, "ledger.json"), {})
    chain = load_json(os.path.join(DATA_DIR, "chain.json"), [])
    wallet_hist = load_json(os.path.join(DATA_DIR, "wallet_history.json"), [])
    registry = load_json(os.path.join(DATA_DIR, "bnb_user_registry.json"), {})

    usdt_pledges = [p for p in pledge_chain
                    if p.get("pledge_type") == "usdt_bnb"
                    and not p.get("pending_confirmation", True)]

    chain_tx_hashes = {tx.get("bnb_txid") for tx in chain if tx.get("type") == "usdt_pledge"}
    hist_ext_txids = {e.get("external_txid") for e in wallet_hist
                      if e.get("event_type") == "pledge_usdt_bnb_confirmed"}

    issues = []

    for pledge in usdt_pledges:
        bnb_addr = pledge.get("bnb_address", "")
        thr_addr = pledge.get("thr_address", "")
        pledge_hash = pledge.get("pledge_hash", "")

        reg_entry = registry.get(bnb_addr, {})
        reg_thr = reg_entry.get("thr_address", "")
        if reg_thr and reg_thr != thr_addr:
            issues.append({
                "type": "registry_thr_mismatch",
                "bnb_address": bnb_addr,
                "thr_address": thr_addr,
                "detail": f"Registry maps to {reg_thr} but pledge credits {thr_addr}",
                "ambiguous": True,
            })

        matching_chain_txs = [
            tx for tx in chain
            if tx.get("type") == "usdt_pledge" and tx.get("bnb_txid")
            and tx.get("bnb_address") == bnb_addr
        ]
        has_chain_tx = len(matching_chain_txs) > 0

        matching_hist = [
            e for e in wallet_hist
            if e.get("event_type") == "pledge_usdt_bnb_confirmed"
            and e.get("thr_address") == thr_addr
            and e.get("external_txid")
        ]
        has_history = len(matching_hist) > 0

        has_balance = thr_addr in ledger and float(ledger.get(thr_addr, 0)) > 0

        if not has_chain_tx:
            issues.append({
                "type": "missing_chain_tx",
                "bnb_address": bnb_addr,
                "thr_address": thr_addr,
                "pledge_hash": pledge_hash,
                "detail": "Pledge confirmed in PLEDGE_CHAIN but no matching chain transaction found by bnb_address + type",
                "ambiguous": False,
            })
        if not has_history:
            issues.append({
                "type": "missing_wallet_history",
                "bnb_address": bnb_addr,
                "thr_address": thr_addr,
                "pledge_hash": pledge_hash,
                "detail": "Pledge confirmed but no wallet_history event with external_txid for this thr_address",
                "ambiguous": False,
            })
        if not has_balance:
            issues.append({
                "type": "missing_ledger_entry",
                "bnb_address": bnb_addr,
                "thr_address": thr_addr,
                "pledge_hash": pledge_hash,
                "detail": "Pledge confirmed but THR address has zero or missing ledger balance",
                "ambiguous": False,
            })

    return issues


def do_repair(issues, server_url, admin_secret):
    try:
        import requests
    except ImportError:
        print("ERROR: 'requests' library required for --repair. Install with: pip install requests")
        return 1

    ambiguous = [i for i in issues if i.get("ambiguous")]
    repairable = [i for i in issues if not i.get("ambiguous")]

    if ambiguous:
        print(f"SKIPPING {len(ambiguous)} ambiguous issues (require manual review):")
        for issue in ambiguous:
            print(f"  [{issue['type']}] {issue['bnb_address']} — {issue['detail']}")
        print()

    bnb_addrs = list({issue["bnb_address"] for issue in repairable})
    if not bnb_addrs:
        print("No repairable issues found.")
        return 0

    print(f"Attempting idempotent repair for {len(bnb_addrs)} BNB address(es)...")
    failures = 0
    for addr in bnb_addrs:
        url = f"{server_url.rstrip('/')}/api/usdt/pledge"
        payload = {
            "secret": admin_secret,
            "bnb_address": addr,
            "reconciliation_reason": "reconcile_partial_write",
        }
        try:
            resp = requests.post(url, json=payload, timeout=30)
            data = resp.json()
            status_str = "OK" if data.get("ok") else f"FAIL ({data.get('error', 'unknown')})"
            print(f"  {addr}: {status_str}")
            if not data.get("ok") and data.get("error") != "duplicate_tx_already_processed":
                failures += 1
        except Exception as e:
            print(f"  {addr}: ERROR — {e}")
            failures += 1

    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description="Pledge reconciliation tool")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Report issues without fixing")
    group.add_argument("--suggest", action="store_true",
                       help="Report issues and print curl commands (does NOT repair)")
    group.add_argument("--repair", action="store_true",
                       help="Idempotent repair via the admin /api/usdt/pledge endpoint")
    parser.add_argument("--server-url", default="http://localhost:5000",
                        help="Server base URL for --repair (default: http://localhost:5000)")
    args = parser.parse_args()

    print(f"DATA_DIR: {DATA_DIR}")
    mode = "dry-run" if args.dry_run else ("suggest" if args.suggest else "REPAIR")
    print(f"Mode: {mode}")
    print()

    issues = find_inconsistencies()

    if not issues:
        print("No inconsistencies found. All confirmed pledges have matching chain, ledger, and history entries.")
        return 0

    print(f"Found {len(issues)} inconsistencies:\n")
    for i, issue in enumerate(issues, 1):
        flag = " [AMBIGUOUS]" if issue.get("ambiguous") else ""
        print(f"  {i}. [{issue['type']}]{flag} {issue['thr_address']}")
        print(f"     BNB: {issue['bnb_address']}")
        if issue.get("pledge_hash"):
            print(f"     Pledge hash: {issue['pledge_hash']}")
        print(f"     {issue['detail']}")
        print()

    if args.dry_run:
        print("Run with --suggest to see repair commands, or --repair to fix.")
        return 1

    if args.suggest:
        bnb_addrs = list({issue["bnb_address"] for issue in issues if not issue.get("ambiguous")})
        if bnb_addrs:
            print("Suggested curl commands (does NOT auto-execute):")
            for addr in bnb_addrs:
                print(f"  curl -X POST http://localhost:5000/api/usdt/pledge "
                      f"-H 'Content-Type: application/json' "
                      f"-d '{{\"secret\":\"$ADMIN_SECRET\",\"bnb_address\":\"{addr}\","
                      f"\"reconciliation_reason\":\"reconcile_partial_write\"}}'")
            print()
        ambiguous = [i for i in issues if i.get("ambiguous")]
        if ambiguous:
            print(f"{len(ambiguous)} ambiguous issue(s) require manual review (not auto-repairable).")
        return 1

    if args.repair:
        admin_secret = os.getenv("ADMIN_SECRET")
        if not admin_secret:
            print("ERROR: ADMIN_SECRET env var required for --repair mode.")
            return 1
        return do_repair(issues, args.server_url, admin_secret)

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
