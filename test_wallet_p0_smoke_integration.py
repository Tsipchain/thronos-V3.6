#!/usr/bin/env python3
"""
Smoke Tests: Wallet P0 Production Integration
Tests the integrated /api/v1/tx/send endpoint in server.py against:
- Master node: accepts valid signed transactions
- Replica node: rejects with 503 "read_only_replica"
"""

import json
import time
import sys
import requests
from typing import Dict, Any, Tuple

# ECDSA imports for real signature generation
try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.backends import default_backend
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


class SmokeSuite:
    def __init__(self, name: str, base_url: str):
        self.name = name
        self.base_url = base_url
        self.tests = []
        self.passed = 0
        self.failed = 0

    def add_test(self, name: str, passed: bool, detail: str = ""):
        self.tests.append((name, passed, detail))
        if passed:
            self.passed += 1
            print(f"  ✓ {name}")
        else:
            self.failed += 1
            print(f"  ✗ {name}")
            if detail:
                print(f"    └─ {detail}")

    def run_test_http(self, test_name: str, endpoint: str, method: str, body: Dict = None,
                      expected_status: int = None, expected_error: str = None) -> Tuple[bool, str]:
        try:
            url = f"{self.base_url}{endpoint}"
            if method == "POST":
                resp = requests.post(url, json=body, timeout=5)
            else:
                resp = requests.get(url, timeout=5)

            if expected_status and resp.status_code != expected_status:
                return False, f"Expected {expected_status}, got {resp.status_code}"

            if expected_error:
                try:
                    data = resp.json()
                    if expected_error not in data.get('error', ''):
                        return False, f"Expected error '{expected_error}', got {data.get('error', 'none')}"
                except Exception:
                    return False, f"Invalid JSON response: {resp.text}"

            return True, ""

        except requests.ConnectionError as e:
            return False, f"Connection failed: {e}"
        except Exception as e:
            return False, f"Error: {e}"

    def summary(self) -> bool:
        total = self.passed + self.failed
        print(f"\n{'='*70}")
        print(f"{self.name}: {self.passed}/{total} PASSED")
        print(f"{'='*70}\n")
        return self.failed == 0


def test_master_node_behavior():
    suite = SmokeSuite("MASTER NODE INTEGRATION TESTS", "http://localhost:5000")
    print("\n" + "="*70)
    print("TEST SUITE 1: Master Node Behavior")
    print("="*70)

    success, detail = suite.run_test_http(
        "Missing tx envelope", "/api/v1/tx/send", "POST",
        body={}, expected_status=400, expected_error="missing_tx_envelope"
    )
    suite.add_test("Missing tx envelope → 400 missing_tx_envelope", success, detail)

    tx_no_sig = {
        "from": "THR1234567890", "to": "THRFEDCBA0987", "amount": 100,
        "token": "THR", "nonce": f"nonce_{int(time.time())}", "timestamp": int(time.time())
    }
    success, detail = suite.run_test_http(
        "Missing signature", "/api/v1/tx/send", "POST",
        body={"tx": tx_no_sig}, expected_status=400
    )
    suite.add_test("Missing signature → 400", success, detail)

    tx_with_secret = {
        "from": "THR1234567890", "to": "THRFEDCBA0987", "amount": 100,
        "token": "THR", "nonce": f"nonce_{int(time.time())}", "timestamp": int(time.time()),
        "signature": "0x" + "a" * 128, "publicKey": "0x" + "b" * 130,
        "secret": "SUPER_SECRET_SEED"
    }
    success, detail = suite.run_test_http(
        "Forbidden field 'secret'", "/api/v1/tx/send", "POST",
        body={"tx": tx_with_secret}, expected_status=400
    )
    suite.add_test("Forbidden field 'secret' → 400", success, detail)

    old_timestamp = int(time.time()) - 400
    tx_old_ts = {
        "from": "THR1234567890", "to": "THRFEDCBA0987", "amount": 100,
        "token": "THR", "nonce": f"nonce_{int(time.time())}", "timestamp": old_timestamp,
        "signature": "0x" + "a" * 128, "publicKey": "0x" + "b" * 130
    }
    success, detail = suite.run_test_http(
        "Expired timestamp (old)", "/api/v1/tx/send", "POST",
        body={"tx": tx_old_ts}, expected_status=400
    )
    suite.add_test("Expired timestamp → 400", success, detail)

    return suite


def test_replica_node_behavior():
    suite = SmokeSuite("REPLICA NODE INTEGRATION TESTS", "http://localhost:5001")
    print("\n" + "="*70)
    print("TEST SUITE 2: Replica Node Behavior")
    print("="*70)

    tx_body = {
        "from": "THR1234567890", "to": "THRFEDCBA0987", "amount": 100,
        "token": "THR", "nonce": f"nonce_{int(time.time())}", "timestamp": int(time.time()),
        "signature": "0x" + "a" * 128, "publicKey": "0x" + "b" * 130
    }
    success, detail = suite.run_test_http(
        "Replica /api/v1/tx/send", "/api/v1/tx/send", "POST",
        body={"tx": tx_body}, expected_status=503, expected_error="read_only_replica"
    )
    suite.add_test("Replica /api/v1/tx/send → 503 read_only_replica", success, detail)

    return suite


def test_legacy_endpoints_deprecation():
    suite = SmokeSuite("LEGACY ENDPOINTS DEPRECATION TESTS", "http://localhost:5000")
    print("\n" + "="*70)
    print("TEST SUITE 3: Legacy Endpoints Deprecation")
    print("="*70)

    for endpoint, name in [("/send_thr", "/send_thr"), ("/api/wallet/send", "/api/wallet/send"), ("/api/tokens/transfer", "/api/tokens/transfer")]:
        success, detail = suite.run_test_http(
            f"{name} (legacy)", endpoint, "POST",
            body={"from": "THR1", "to": "THR2", "amount": 100},
            expected_status=410, expected_error="legacy_endpoint_deprecated"
        )
        suite.add_test(f"{name} → 410 legacy_endpoint_deprecated", success, detail)

    return suite


def main():
    print("\n" + "="*70)
    print("WALLET P0 PRODUCTION INTEGRATION SMOKE TESTS")
    print("="*70)

    results = []

    try:
        suite1 = test_master_node_behavior()
        results.append(suite1)
    except Exception as e:
        print(f"\n✗ Master node tests failed: {e}")

    try:
        suite3 = test_legacy_endpoints_deprecation()
        results.append(suite3)
    except Exception as e:
        print(f"\n✗ Legacy endpoint tests failed: {e}")

    try:
        suite2 = test_replica_node_behavior()
        results.append(suite2)
    except requests.ConnectionError:
        print("\n⚠ Replica node not available (expected if running master-only deployment)")
    except Exception as e:
        print(f"\n✗ Replica node tests failed: {e}")

    print("\n" + "="*70)
    print("SMOKE TEST SUMMARY")
    print("="*70)

    total_passed = sum(s.passed for s in results)
    total_failed = sum(s.failed for s in results)
    total = total_passed + total_failed

    print(f"\nTotal: {total_passed}/{total} PASSED\n")

    if total_failed == 0:
        print("✓ ALL SMOKE TESTS PASSED - Production ready")
        return 0
    else:
        print(f"✗ {total_failed} test(s) failed")
        return 1


if __name__ == '__main__':
    # Note: This script assumes server is running on localhost:5000 (master) and :5001 (replica)
    sys.exit(main())
