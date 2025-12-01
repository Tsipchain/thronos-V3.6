#!/usr/bin/env python3
"""
Thronos THR Sender (CLI client)

Χρησιμοποιεί το /send_thr API του server:
 - Ελέγχει auth_secret (send_secret από το pledge)
 - Ενημερώνει ledger & chain στο server
"""

import sys
import json
import requests

SERVER = "https://thrchain.up.railway.app"  # άλλαξέ το αν τρέχεις local


def send_thr(from_addr, to_addr, amount, auth_secret):
    payload = {
        "from_thr": from_addr,
        "to_thr": to_addr,
        "amount": amount,
        "auth_secret": auth_secret,
    }

    url = f"{SERVER}/send_thr"
    try:
        r = requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"❌ Network error: {e}")
        return

    try:
        data = r.json()
    except Exception:
        print("❌ Invalid JSON response:", r.text[:500])
        return

    print(f"HTTP {r.status_code}")
    print(json.dumps(data, indent=2))

    if r.ok and data.get("status") == "ok":
        print("✅ Send successful!")
        print("   TX ID:", data["tx"]["tx_id"])
        print("   New sender balance:", data["new_balance_from"])
        print("   New receiver balance:", data["new_balance_to"])
    else:
        print("⚠️ Send failed.")


if __name__ == "__main__":
    # Usage: python send_thr.py FROM_THR TO_THR AMOUNT AUTH_SECRET
    if len(sys.argv) != 5:
        print("Usage: python send_thr.py <from_thr> <to_thr> <amount> <auth_secret>")
        sys.exit(1)

    from_thr = sys.argv[1]
    to_thr = sys.argv[2]
    amount = sys.argv[3]
    auth_secret = sys.argv[4]

    send_thr(from_thr, to_thr, amount, auth_secret)
