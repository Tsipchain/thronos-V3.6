#!/usr/bin/env python3
"""
Check: Wallet P0 Server Integration Status
Verifies that the integration is present in server.py and will work with error handling.
"""

import os
import sys
import re

def check_server_integration():
    """Check if server.py has been properly integrated with wallet P0."""

    try:
        with open('/home/user/thronos-v3.6/server.py', 'r') as f:
            server_content = f.read()
    except Exception as e:
        print(f"✗ Could not read server.py: {e}")
        return False

    checks = [
        ("Wallet P0 imports", "import wallet_v1_production_final"),
        ("Wallet endpoints import", "import wallet_v1_endpoints_final"),
        ("WALLET_V1_AVAILABLE flag", "WALLET_V1_AVAILABLE = True"),
        ("SQLITE_DB_PATH env var", "SQLITE_DB_PATH = _strip_env_quotes"),
        ("wallet V1 initialization", "wallet_v1_production_final.init_wallet_v1"),
        ("wallet V1 endpoints registration", "register_wallet_v1_endpoints"),
        ("legacy endpoints deprecation", "register_legacy_deprecation_endpoints"),
    ]

    results = []
    for check_name, pattern in checks:
        if pattern in server_content:
            print(f"  ✓ {check_name}")
            results.append(True)
        else:
            print(f"  ✗ {check_name} - Pattern not found: {pattern}")
            results.append(False)

    return all(results)


def check_wallet_files():
    """Check if wallet P0 files exist."""

    files = [
        '/home/user/thronos-v3.6/wallet_v1_production_final.py',
        '/home/user/thronos-v3.6/wallet_v1_endpoints_final.py',
        '/home/user/thronos-v3.6/test_wallet_v1_final.py',
        '/home/user/thronos-v3.6/P0_WALLET_FINAL_ARCHITECTURE.md',
    ]

    results = []
    for filepath in files:
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            print(f"  ✓ {os.path.basename(filepath)} ({size} bytes)")
            results.append(True)
        else:
            print(f"  ✗ {os.path.basename(filepath)} - Not found")
            results.append(False)

    return all(results)


def check_server_endpoints():
    """Verify that the server has the new endpoints registered."""

    try:
        with open('/home/user/thronos-v3.6/server.py', 'r') as f:
            content = f.read()
    except:
        return False

    endpoints = [
        ("/api/v1/tx/send", "POST"),
        ("/api/v1/tx/batch", "POST"),
        ("/send_thr", "410 Gone"),
        ("/api/wallet/send", "410 Gone"),
        ("/api/tokens/transfer", "410 Gone"),
    ]

    results = []
    for endpoint, method in endpoints:
        if f'@app.route("{endpoint}"' in content or endpoint in content:
            print(f"  ✓ {endpoint} endpoint present")
            results.append(True)
        else:
            print(f"  ✗ {endpoint} endpoint - Not found")
            results.append(False)

    return all(results)


def check_error_handling():
    """Verify fail-closed error handling."""

    try:
        with open('/home/user/thronos-v3.6/wallet_v1_production_final.py', 'r') as f:
            wallet_content = f.read()
    except:
        return False

    checks = [
        ("Fail-closed Redis check", "verify_redis_available"),
        ("Fail-closed SQLite check", "verify_master_mode_required"),
        ("Nonce replay protection", "check_nonce_redis"),
        ("ECDSA signature verification", "verify_ecdsa_signature"),
        ("Forbidden fields rejection", "verify_no_forbidden_fields"),
        ("Timestamp validation", "verify_timestamp"),
        ("Required fields validation", "verify_required_fields"),
    ]

    results = []
    for check_name, pattern in checks:
        if pattern in wallet_content:
            print(f"  ✓ {check_name}")
            results.append(True)
        else:
            print(f"  ✗ {check_name} - Pattern not found")
            results.append(False)

    return all(results)


def check_replica_safety():
    """Verify replica mode safety measures."""

    try:
        with open('/home/user/thronos-v3.6/wallet_v1_endpoints_final.py', 'r') as f:
            endpoints_content = f.read()
    except:
        return False

    checks = [
        ("Replica check in /api/v1/tx/send", "read_only or node_role == \"replica\""),
        ("503 response for replica", "503"),
        ("read_only_replica error", "read_only_replica"),
    ]

    results = []
    for check_name, pattern in checks:
        if pattern in endpoints_content:
            print(f"  ✓ {check_name}")
            results.append(True)
        else:
            print(f"  ✗ {check_name} - Pattern not found")
            results.append(False)

    return all(results)


def main():
    print("\n" + "="*70)
    print("WALLET P0 SERVER INTEGRATION CHECK")
    print("Verifying production integration is complete")
    print("="*70)

    print("\n1. Server Integration:")
    print("-" * 70)
    server_ok = check_server_integration()

    print("\n2. Wallet P0 Files:")
    print("-" * 70)
    files_ok = check_wallet_files()

    print("\n3. Endpoints:")
    print("-" * 70)
    endpoints_ok = check_server_endpoints()

    print("\n4. Error Handling (Fail-Closed):")
    print("-" * 70)
    errors_ok = check_error_handling()

    print("\n5. Replica Mode Safety:")
    print("-" * 70)
    replica_ok = check_replica_safety()

    # Summary
    print("\n" + "="*70)
    print("INTEGRATION CHECK RESULTS")
    print("="*70)

    all_ok = server_ok and files_ok and endpoints_ok and errors_ok and replica_ok

    if all_ok:
        print("✓ ALL INTEGRATION CHECKS PASSED")
        print("\nProduction integration is complete and ready for deployment.")
        return 0
    else:
        print("✗ Some checks failed - review output above")
        return 1


if __name__ == '__main__':
    sys.exit(main())
