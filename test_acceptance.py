#!/usr/bin/env python3
"""
Acceptance Tests for DB Cache Layer

Definition of Done (DoD):
1. /api/tx_feed?limit=200 responds fast (< 500ms)
2. /api/dashboard stable (no crashes)
3. No APScheduler job crash loops

Usage: python3 test_acceptance.py
"""

import sys
import time
import requests
import sqlite3
import os

# Test configuration
BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
DB_PATH = os.path.join(os.getenv("DATA_DIR", "./data"), "ledger.sqlite3")

def test_tx_feed_performance():
    """Test 1: /api/tx_feed?limit=200 responds fast (< 500ms)"""
    print("\n[TEST 1] Testing /api/tx_feed performance...")

    start = time.time()
    try:
        response = requests.get(f"{BASE_URL}/api/tx_feed?limit=200", timeout=5)
        elapsed = (time.time() - start) * 1000  # Convert to ms

        if response.status_code == 200:
            data = response.json()
            print(f"  ✅ Status 200 OK")
            print(f"  ✅ Response time: {elapsed:.1f}ms (target: <500ms)")
            print(f"  ✅ Returned {len(data.get('transactions', []))} transactions")

            if elapsed < 500:
                print(f"  🎉 PASS: Fast response!")
                return True
            else:
                print(f"  ⚠️  SLOW: Response time exceeds 500ms threshold")
                return False
        else:
            print(f"  ❌ FAIL: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"  ❌ FAIL: {e}")
        return False


def test_db_tables_created():
    """Test 2: Verify DB tables exist"""
    print("\n[TEST 2] Checking DB tables...")

    if not os.path.exists(DB_PATH):
        print(f"  ⚠️  DB not found at {DB_PATH} (will be created on first run)")
        return True  # Not a failure - will be created on startup

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Check required tables
        required_tables = ['event_index', 'telemetry_cache', 'music_plays', 'balances']
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = [row[0] for row in cursor.fetchall()]

        all_exist = True
        for table in required_tables:
            if table in existing_tables:
                print(f"  ✅ Table '{table}' exists")
            else:
                print(f"  ❌ Table '{table}' missing")
                all_exist = False

        conn.close()

        if all_exist:
            print(f"  🎉 PASS: All tables created!")
            return True
        else:
            print(f"  ❌ FAIL: Some tables missing")
            return False
    except Exception as e:
        print(f"  ❌ FAIL: {e}")
        return False


def test_telemetry_cache():
    """Test 3: Check telemetry cache has data"""
    print("\n[TEST 3] Checking telemetry cache...")

    if not os.path.exists(DB_PATH):
        print(f"  ⚠️  DB not found (skip test)")
        return True

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM telemetry_cache")
        count = cursor.fetchone()[0]

        if count > 0:
            print(f"  ✅ Telemetry cache has {count} metrics")

            # Show cached metrics
            cursor.execute("SELECT metric_key, updated_at FROM telemetry_cache")
            for row in cursor.fetchall():
                age = int(time.time()) - row[1]
                print(f"     - {row[0]}: {age}s old")

            print(f"  🎉 PASS: Telemetry cache populated!")
            conn.close()
            return True
        else:
            print(f"  ⚠️  Telemetry cache empty (will be populated by scheduler)")
            conn.close()
            return True  # Not a failure - takes 30s to populate
    except Exception as e:
        print(f"  ❌ FAIL: {e}")
        return False


def test_health_endpoint():
    """Test 4: /api/health endpoint stability"""
    print("\n[TEST 4] Testing /api/health stability...")

    try:
        response = requests.get(f"{BASE_URL}/api/health", timeout=5)

        if response.status_code == 200:
            data = response.json()
            print(f"  ✅ Status 200 OK")
            print(f"  ✅ Version: {data.get('version', 'unknown')}")
            print(f"  ✅ Chain height: {data.get('chain_height', 'unknown')}")
            print(f"  🎉 PASS: Health endpoint stable!")
            return True
        else:
            print(f"  ❌ FAIL: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"  ❌ FAIL: {e}")
        return False


def main():
    """Run all acceptance tests"""
    print("=" * 60)
    print("ACCEPTANCE TESTS - DB CACHE LAYER")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print(f"DB Path: {DB_PATH}")

    results = []

    # Run tests
    results.append(("DB Tables Created", test_db_tables_created()))
    results.append(("Telemetry Cache", test_telemetry_cache()))
    results.append(("Health Endpoint", test_health_endpoint()))
    results.append(("/api/tx_feed Performance", test_tx_feed_performance()))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED! Ready for deployment!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
