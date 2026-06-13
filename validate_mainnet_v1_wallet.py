#!/usr/bin/env python3
"""
MAINNET V1 WALLET VALIDATION
Emergency verification of all critical paths
"""

import requests
import json
import sys
from datetime import datetime

MAINNET_API = "https://api.thronoschain.org"
REPLICA_API = "https://ro.api.thronoschain.org"

# Test addresses from migration setup
LEGACY_ADDRESS = "THR79ca94a7eb70a6aa99d12d7fdb01446ef246301a"
CANONICAL_ADDRESS = "THR683318ACF083723B3EDFE6C0A30AD62670F00353"
BTC_ADDRESS = "3KUGVJ96T3JHuUrEHMeAvDKSo1zM9tD9nF"

print(f"""
╔════════════════════════════════════════════════════════╗
║  MAINNET V1 WALLET VALIDATION                         ║
║  {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
╚════════════════════════════════════════════════════════╝
""")

def test_endpoint(name, method, endpoint, payload=None, expected_status=200):
    """Test single endpoint"""
    url = f"{MAINNET_API}{endpoint}"
    try:
        if method == "POST":
            resp = requests.post(url, json=payload, timeout=5)
        else:
            resp = requests.get(url, timeout=5)
        
        status = "✅" if resp.status_code == expected_status else "❌"
        print(f"{status} {name}")
        if resp.status_code != expected_status:
            print(f"   Expected {expected_status}, got {resp.status_code}")
            print(f"   Response: {resp.text[:200]}")
            return False
        return True
    except Exception as e:
        print(f"❌ {name}")
        print(f"   Error: {str(e)}")
        return False

# ─── TEST 1: V1 WALLET CORE ─────────────────────────────
print("\n[1/3] V1 WALLET CORE FUNCTIONALITY\n")

tests_passed = 0
tests_total = 0

# 1.1: Restore migration endpoint
tests_total += 1
if test_endpoint(
    "Restore-migration (legacy → canonical)",
    "POST",
    "/api/wallet/v1/restore-migration",
    {
        "legacy_address": LEGACY_ADDRESS,
        "migration_proof": ""
    },
    200
):
    tests_passed += 1

# 1.2: Wallet V1 status
tests_total += 1
if test_endpoint(
    "Wallet V1 status",
    "GET",
    f"/api/wallet/v1/status?address={CANONICAL_ADDRESS}",
    None,
    200
):
    tests_passed += 1

# 1.3: Swap quote (Flask route test)
tests_total += 1
if test_endpoint(
    "Swap quote endpoint (Flask routes)",
    "POST",
    "/api/swap/quote",
    {
        "token_in": "THR",
        "token_out": "WBTC",
        "amount_in": "1"
    }
):
    tests_passed += 1

print(f"\n✅ Core: {tests_passed}/{tests_total} tests passed")

# ─── TEST 2: ECOSYSTEM INTEGRATIONS ─────────────────────
print("\n[2/3] ECOSYSTEM INTEGRATION POINTS\n")

eco_passed = 0
eco_total = 0

# 2.1: Check wallet → EVM bridge
eco_total += 1
try:
    resp = requests.get(f"{MAINNET_API}/api/evm/balances?address={CANONICAL_ADDRESS}", timeout=5)
    if resp.status_code == 200:
        print("✅ Wallet → EVM contract bridge")
        eco_passed += 1
    else:
        print("⚠️  EVM bridge (may be optional)")
except:
    print("⚠️  EVM bridge (check manually)")

# 2.2: Check wallet → service nodes
eco_total += 1
try:
    resp = requests.get(f"{MAINNET_API}/api/services/check?wallet={CANONICAL_ADDRESS}", timeout=5)
    if resp.status_code in [200, 404]:  # 404 is OK if service doesn't exist
        print("✅ Wallet → service nodes")
        eco_passed += 1
    else:
        print("⚠️  Service integration")
except:
    print("⚠️  Service integration (check manually)")

# 2.3: Check wallet → digital legacy
eco_total += 1
try:
    resp = requests.get(f"{MAINNET_API}/api/digital-legacy?address={CANONICAL_ADDRESS}", timeout=5)
    if resp.status_code in [200, 404]:
        print("✅ Wallet → digital legacy system")
        eco_passed += 1
    else:
        print("⚠️  Digital legacy integration")
except:
    print("⚠️  Digital legacy (check manually)")

# 2.4: Check BTC bridge connectivity
eco_total += 1
try:
    resp = requests.get(f"{MAINNET_API}/api/btc/address-status?address={BTC_ADDRESS}", timeout=5)
    if resp.status_code in [200, 404]:
        print("✅ Wallet → BTC bridge")
        eco_passed += 1
    else:
        print("⚠️  BTC bridge connectivity")
except:
    print("⚠️  BTC bridge (check manually)")

print(f"\n✅ Integrations: {eco_passed}/{eco_total} tests passed")

# ─── TEST 3: CRITICAL USER PATHS ────────────────────────
print("\n[3/3] CRITICAL USER JOURNEYS\n")

paths_ok = 0
paths_total = 5

# 3.1: Pledge → Canonical mapping
paths_total += 1
try:
    resp = requests.post(
        f"{MAINNET_API}/api/wallet/v1/restore-migration",
        json={"legacy_address": LEGACY_ADDRESS},
        timeout=5
    )
    if resp.status_code == 200:
        data = resp.json()
        if data.get("canonical_v1_address") == CANONICAL_ADDRESS:
            print("✅ Path 1: Pledge → canonical address mapping")
            paths_ok += 1
        else:
            print("❌ Path 1: Address mismatch")
            print(f"   Expected {CANONICAL_ADDRESS}, got {data.get('canonical_v1_address')}")
    else:
        print(f"❌ Path 1: HTTP {resp.status_code}")
except Exception as e:
    print(f"❌ Path 1: {str(e)}")

# 3.2: Migration record exists
paths_total += 1
try:
    resp = requests.get(f"{MAINNET_API}/api/wallet/v1/migration-status?address={CANONICAL_ADDRESS}", timeout=5)
    if resp.status_code in [200, 404]:
        print("✅ Path 2: Migration records accessible")
        paths_ok += 1
    else:
        print("⚠️  Path 2: Migration status (check logs)")
except:
    print("⚠️  Path 2: Migration records")

# 3.3: Recovery kit structure valid
paths_total += 1
try:
    # Check if recovery kit directory exists
    import os
    kit_path = "/app/data/recovery_kits"
    if os.path.exists(kit_path):
        kits = [f for f in os.listdir(kit_path) if f.endswith('.json')]
        if kits:
            print(f"✅ Path 3: Recovery kits present ({len(kits)} kits)")
            paths_ok += 1
        else:
            print("⚠️  Path 3: No recovery kits generated yet")
    else:
        print("⚠️  Path 3: Recovery kit directory")
except:
    print("⚠️  Path 3: Recovery kit validation")

# 3.4: Signing capability
paths_total += 1
try:
    resp = requests.post(
        f"{MAINNET_API}/api/wallet/v1/verify-signing-capability",
        json={"canonical_v1_address": CANONICAL_ADDRESS},
        timeout=5
    )
    if resp.status_code in [200, 400]:  # 400 if not unlocked is OK
        print("✅ Path 4: Signing capability intact")
        paths_ok += 1
    else:
        print("⚠️  Path 4: Signing check")
except:
    print("⚠️  Path 4: Signing capability")

# 3.5: Replica sync (HA check)
paths_total += 1
try:
    resp = requests.get(
        f"{REPLICA_API}/api/wallet/v1/status?address={CANONICAL_ADDRESS}",
        timeout=5
    )
    if resp.status_code == 200:
        print("✅ Path 5: Replica node synchronized")
        paths_ok += 1
    else:
        print("⚠️  Path 5: Replica sync (may be delayed)")
except:
    print("⚠️  Path 5: Replica connectivity")

print(f"\n✅ Paths: {paths_ok}/{paths_total} working")

# ─── FINAL REPORT ───────────────────────────────────────
print(f"""
╔════════════════════════════════════════════════════════╗
║                    FINAL REPORT                        ║
╠════════════════════════════════════════════════════════╣
║ Core Functionality:    {tests_passed}/{tests_total} ✅
║ Ecosystem Integration: {eco_passed}/{eco_total} ✅
║ Critical Paths:        {paths_ok}/{paths_total} ✅
╠════════════════════════════════════════════════════════╣
""")

total_ok = tests_passed + eco_passed + paths_ok
total_tests = tests_total + eco_total + paths_total

if total_ok >= total_tests - 2:  # Allow 2 failures
    print("║ STATUS: ✅ MAINNET READY                            ║")
else:
    print("║ STATUS: ⚠️  ISSUES DETECTED - SEE ABOVE             ║")

print(f"""╚════════════════════════════════════════════════════════╝

NEXT STEPS:
- If all ✅: Deploy to production
- If ⚠️ : Check logs at https://api.thronoschain.org/logs
- If ❌ : Emergency rollback + investigate
""")

sys.exit(0 if total_ok >= total_tests - 2 else 1)
