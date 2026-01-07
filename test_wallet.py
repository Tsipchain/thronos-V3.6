#!/usr/bin/env python3
"""
Test script for Thronos Wallet API
Tests sending tokens and swapping
"""
import requests
import json
import time

# Wallet credentials
FROM_ADDRESS = "THR24d877dd21c6b0c9d8a702f24842fc34052a5689"
SEND_SECRET = "eb9f8e3f6e05d6346f146a71260a3add"
BASE_URL = "https://thrchain.up.railway.app"

# Test addresses - using self-transfer for testing
TEST_TO_ADDRESS = FROM_ADDRESS  # Self-transfer for testing

def test_send_token():
    """Test sending 1 JAM token"""
    print("\n=== Testing Token Send ===")

    url = f"{BASE_URL}/api/send_token"
    payload = {
        "from_thr": FROM_ADDRESS,
        "send_seed": SEND_SECRET,
        "to_thr": TEST_TO_ADDRESS,
        "amount": 1.0,
        "token_symbol": "JAM",
        "note": "Test transaction from Pytheia"
    }

    print(f"Sending 1 JAM to {TEST_TO_ADDRESS}...")
    response = requests.post(url, json=payload)

    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

    return response.json()

def test_swap():
    """Test swapping THR for JAM"""
    print("\n=== Testing Token Swap ===")

    # First, get available pools
    pools_url = f"{BASE_URL}/api/v1/pools"
    pools_response = requests.get(pools_url)
    pools = pools_response.json().get("pools", [])

    print(f"Available pools: {len(pools)}")

    # Find THR/JAM pool
    jam_pool = None
    for pool in pools:
        if (pool.get("token_a") == "THR" and pool.get("token_b") == "JAM") or \
           (pool.get("token_a") == "JAM" and pool.get("token_b") == "THR"):
            jam_pool = pool
            print(f"Found THR/JAM pool: {pool['id']}")
            print(f"  Reserves: {pool['reserves_a']} {pool['token_a']}, {pool['reserves_b']} {pool['token_b']}")
            break

    if not jam_pool:
        print("No THR/JAM pool found!")
        return None

    # Execute swap: 10 THR → JAM
    swap_url = f"{BASE_URL}/api/v1/pools/swap"
    payload = {
        "pool_id": jam_pool["id"],
        "trader_thr": FROM_ADDRESS,
        "auth_secret": SEND_SECRET,
        "amount_in": 10.0,
        "token_in": "THR",
        "token_out": "JAM",
        "min_amount_out": 0.1  # Minimum JAM we accept
    }

    print(f"Swapping 10 THR → JAM (min 0.1 JAM)...")
    response = requests.post(swap_url, json=payload)

    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

    return response.json()

def check_wallet_balance():
    """Check current wallet balance"""
    print("\n=== Checking Wallet Balance ===")

    url = f"{BASE_URL}/wallet_data/{FROM_ADDRESS}"
    response = requests.get(url)
    data = response.json()

    print(f"THR Balance: {data.get('balance', 0)}")
    print(f"Tokens:")
    for token in data.get("tokens", []):
        if token.get("balance", 0) > 0:
            print(f"  - {token['symbol']}: {token['balance']}")

    return data

def check_transaction_history():
    """Check recent transactions"""
    print("\n=== Checking Transaction History ===")

    url = f"{BASE_URL}/api/tx_feed?wallet={FROM_ADDRESS}"
    response = requests.get(url)
    txs = response.json()

    if isinstance(txs, list):
        print(f"Recent transactions: {len(txs)}")
        for tx in txs[:5]:  # Show last 5
            print(f"  - {tx.get('kind', 'unknown')}: {tx.get('amount', 0)} {tx.get('asset_symbol', 'THR')} ({tx.get('status', 'pending')})")
    else:
        print(f"Error: {txs}")

    return txs

if __name__ == "__main__":
    print("=" * 50)
    print("Thronos Wallet API Test")
    print("=" * 50)

    # Check initial balance
    initial_balance = check_wallet_balance()

    # Check transaction history
    check_transaction_history()

    # Test sending token
    try:
        send_result = test_send_token()
        if send_result.get("status") == "success" or send_result.get("status") == "pending":
            print("✅ Token send successful!")
            time.sleep(2)  # Wait for confirmation
        else:
            print(f"❌ Token send failed: {send_result}")
    except Exception as e:
        print(f"❌ Error sending token: {e}")

    # Test swap
    try:
        swap_result = test_swap()
        if swap_result and swap_result.get("status") == "success":
            print("✅ Swap successful!")
        else:
            print(f"❌ Swap failed: {swap_result}")
    except Exception as e:
        print(f"❌ Error swapping: {e}")

    # Check final balance
    print("\n" + "=" * 50)
    final_balance = check_wallet_balance()

    print("\n" + "=" * 50)
    print("Test completed!")
    print("=" * 50)
