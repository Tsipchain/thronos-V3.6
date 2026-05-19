"""
Production Wallet V1 - Secure Signed Transaction Backend

Implements:
- HMAC-SHA256 signature verification
- Database-backed nonce/replay protection (durable)
- Strict timestamp validation (±5 minute window)
- Forbidden field rejection
- All required security tests
"""

import hashlib
import hmac
import json
import time
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, Optional

# Database path for durable nonce tracking
NONCE_DB = "/tmp/wallet_v1_nonces.db"
NONCE_VALID_MINUTES = 5
MAX_TIMESTAMP_DRIFT = 300  # ±5 minutes = 300 seconds

# Initialize database (PRODUCTION: use real database)
def init_nonce_db():
    """Initialize SQLite database for durable nonce tracking"""
    conn = sqlite3.connect(NONCE_DB)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS used_nonces (
            nonce TEXT PRIMARY KEY,
            timestamp INTEGER,
            created_at REAL
        )
    ''')
    conn.commit()
    conn.close()


def check_nonce_production(nonce: str) -> Tuple[bool, str]:
    """
    Production-grade nonce checking with database persistence.
    Prevents replay attacks across server restarts.
    """
    try:
        init_nonce_db()
        conn = sqlite3.connect(NONCE_DB)
        cursor = conn.cursor()

        # Check if nonce already exists
        cursor.execute('SELECT created_at FROM used_nonces WHERE nonce = ?', (nonce,))
        existing = cursor.fetchone()

        if existing:
            conn.close()
            return False, "nonce_replay_detected"

        # Store nonce (with expiration cleanup)
        current_time = time.time()
        cursor.execute('INSERT INTO used_nonces (nonce, timestamp, created_at) VALUES (?, ?, ?)',
                      (nonce, int(time.time()), current_time))

        # Clean expired nonces (older than NONCE_VALID_MINUTES)
        expiry_threshold = current_time - (NONCE_VALID_MINUTES * 60)
        cursor.execute('DELETE FROM used_nonces WHERE created_at < ?', (expiry_threshold,))

        conn.commit()
        conn.close()
        return True, ""

    except Exception as e:
        return False, f"nonce_check_failed:{str(e)}"


def verify_timestamp(timestamp: int) -> Tuple[bool, str]:
    """
    Verify timestamp is within acceptable window.
    Prevents old/future transaction replays.
    """
    current_time = int(time.time())
    time_diff = abs(current_time - timestamp)

    if time_diff > MAX_TIMESTAMP_DRIFT:
        return False, f"timestamp_outside_tolerance:drift_{time_diff}s"

    return True, ""


def verify_signature(signed_tx: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Verify HMAC-SHA256 signature.
    Signature is computed over canonical JSON representation of transaction.
    """
    signature = signed_tx.get('signature')
    public_key = signed_tx.get('publicKey')

    if not signature or not public_key:
        return False, "missing_signature_or_publickey"

    # Create canonical message
    tx_for_signing = {
        'from': signed_tx.get('from'),
        'to': signed_tx.get('to'),
        'amount': signed_tx.get('amount'),
        'token': signed_tx.get('token', 'THR'),
        'nonce': signed_tx.get('nonce'),
        'timestamp': signed_tx.get('timestamp')
    }

    # Canonical JSON (sorted keys, no spaces)
    message = json.dumps(tx_for_signing, sort_keys=True, separators=(',', ':'))

    # Verify HMAC-SHA256
    expected_signature = hmac.new(
        public_key.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    # Constant-time comparison
    if not hmac.compare_digest(signature, expected_signature):
        return False, "invalid_signature"

    return True, ""


def verify_no_forbidden_fields(signed_tx: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Reject any request containing secrets or sensitive fields.
    This is the CRITICAL gate that prevents secret transmission.
    """
    forbidden = ['secret', 'mnemonic', 'seed', 'privateKey', 'auth_secret', 'passphrase']

    for field in forbidden:
        if field in signed_tx:
            return False, f"forbidden_field:{field}_present"

    return True, ""


def verify_required_fields(signed_tx: Dict[str, Any]) -> Tuple[bool, str]:
    """Verify all required fields are present"""
    required = ['from', 'to', 'amount', 'signature', 'publicKey', 'nonce', 'timestamp']

    for field in required:
        if field not in signed_tx:
            return False, f"missing_field:{field}"

    return True, ""


def verify_signed_transaction_complete(signed_tx: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Complete transaction verification:
    1. Required fields present
    2. No forbidden fields
    3. Signature valid
    4. Timestamp valid
    5. Nonce not replayed
    """
    # Step 1: Required fields
    is_valid, error = verify_required_fields(signed_tx)
    if not is_valid:
        return False, f"validation_failed:{error}"

    # Step 2: No forbidden fields (CRITICAL)
    is_valid, error = verify_no_forbidden_fields(signed_tx)
    if not is_valid:
        return False, f"security_violation:{error}"

    # Step 3: Valid signature
    is_valid, error = verify_signature(signed_tx)
    if not is_valid:
        return False, f"signature_invalid:{error}"

    # Step 4: Valid timestamp
    timestamp = signed_tx.get('timestamp')
    is_valid, error = verify_timestamp(timestamp)
    if not is_valid:
        return False, f"timestamp_invalid:{error}"

    # Step 5: Nonce not replayed (production)
    nonce = signed_tx.get('nonce')
    is_valid, error = check_nonce_production(nonce)
    if not is_valid:
        return False, f"replay_detected:{error}"

    return True, ""


def test_all_security_checks():
    """
    Test all 8 required security checks.
    Returns: (passed, failed, output)
    """
    # Clean nonce database before tests
    try:
        conn = sqlite3.connect(NONCE_DB)
        conn.execute('DELETE FROM used_nonces')
        conn.commit()
        conn.close()
    except:
        pass

    tests = []
    passed = 0
    failed = 0

    # Test 1: Valid signed transaction
    print("\n[TEST 1] Valid signed transaction accepted")
    tx = {
        'from': 'THR1234567890abcdef',
        'to': 'THR0987654321fedcba',
        'amount': 100,
        'token': 'THR',
        'nonce': 'test_nonce_valid',
        'timestamp': int(time.time()),
        'publicKey': 'test_pub_key_123'
    }

    # Calculate valid signature
    tx_for_sig = {k: tx[k] for k in ['from', 'to', 'amount', 'token', 'nonce', 'timestamp']}
    msg = json.dumps(tx_for_sig, sort_keys=True, separators=(',', ':'))
    tx['signature'] = hmac.new(
        'test_pub_key_123'.encode(),
        msg.encode(),
        hashlib.sha256
    ).hexdigest()

    is_valid, error = verify_signed_transaction_complete(tx)
    if is_valid:
        print("✅ PASS - Valid transaction accepted")
        passed += 1
    else:
        print(f"❌ FAIL - {error}")
        failed += 1

    # Test 2: Missing signature rejected
    print("\n[TEST 2] Missing signature rejected")
    tx2 = tx.copy()
    del tx2['signature']
    is_valid, error = verify_signed_transaction_complete(tx2)
    if not is_valid and 'missing_field' in error:
        print("✅ PASS - Missing signature rejected")
        passed += 1
    else:
        print(f"❌ FAIL - {error}")
        failed += 1

    # Test 3: Invalid signature rejected
    print("\n[TEST 3] Invalid signature rejected")
    tx3 = tx.copy()
    tx3['signature'] = 'badbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadb'
    is_valid, error = verify_signed_transaction_complete(tx3)
    if not is_valid and 'signature' in error:
        print("✅ PASS - Invalid signature rejected")
        passed += 1
    else:
        print(f"❌ FAIL - {error}")
        failed += 1

    # Test 4: Replayed nonce rejected
    print("\n[TEST 4] Replayed nonce rejected")
    tx4a = tx.copy()
    tx4a['nonce'] = 'test_nonce_replay_' + str(int(time.time() * 1000))

    # Recalculate signature with new nonce
    tx_for_sig = {k: tx4a[k] for k in ['from', 'to', 'amount', 'token', 'nonce', 'timestamp']}
    msg = json.dumps(tx_for_sig, sort_keys=True, separators=(',', ':'))
    tx4a['signature'] = hmac.new(
        'test_pub_key_123'.encode(),
        msg.encode(),
        hashlib.sha256
    ).hexdigest()

    is_valid1, _ = verify_signed_transaction_complete(tx4a)
    is_valid2, error2 = verify_signed_transaction_complete(tx4a)  # Same nonce again

    if is_valid1 and not is_valid2:
        print("✅ PASS - Replay attack detected")
        passed += 1
    else:
        print(f"❌ FAIL - First: {is_valid1}, Second: {is_valid2} ({error2})")
        failed += 1

    # Test 5: Expired timestamp rejected
    print("\n[TEST 5] Expired timestamp rejected")
    tx5 = tx.copy()
    tx5['timestamp'] = int(time.time()) - 400  # >5 min old
    # Recalculate signature with new timestamp
    tx5_for_sig = {k: tx5[k] for k in ['from', 'to', 'amount', 'token', 'nonce', 'timestamp']}
    msg = json.dumps(tx5_for_sig, sort_keys=True, separators=(',', ':'))
    tx5['signature'] = hmac.new('test_pub_key_123'.encode(), msg.encode(), hashlib.sha256).hexdigest()
    is_valid, error = verify_signed_transaction_complete(tx5)
    if not is_valid and 'timestamp' in error:
        print("✅ PASS - Expired timestamp rejected")
        passed += 1
    else:
        print(f"❌ FAIL - {error}")
        failed += 1

    # Test 6: Future timestamp rejected
    print("\n[TEST 6] Future timestamp rejected")
    tx6 = tx.copy()
    tx6['timestamp'] = int(time.time()) + 400  # >5 min in future
    # Recalculate signature with new timestamp
    tx6_for_sig = {k: tx6[k] for k in ['from', 'to', 'amount', 'token', 'nonce', 'timestamp']}
    msg = json.dumps(tx6_for_sig, sort_keys=True, separators=(',', ':'))
    tx6['signature'] = hmac.new('test_pub_key_123'.encode(), msg.encode(), hashlib.sha256).hexdigest()
    is_valid, error = verify_signed_transaction_complete(tx6)
    if not is_valid and 'timestamp' in error:
        print("✅ PASS - Future timestamp rejected")
        passed += 1
    else:
        print(f"❌ FAIL - {error}")
        failed += 1

    # Test 7: Forbidden field 'secret' rejected
    print("\n[TEST 7] Forbidden field 'secret' rejected")
    tx7 = tx.copy()
    tx7['secret'] = 'should_not_be_here'
    is_valid, error = verify_signed_transaction_complete(tx7)
    if not is_valid and 'forbidden' in error:
        print("✅ PASS - Secret field rejected")
        passed += 1
    else:
        print(f"❌ FAIL - {error}")
        failed += 1

    # Test 8: Forbidden field 'mnemonic' rejected
    print("\n[TEST 8] Forbidden field 'mnemonic' rejected")
    tx8 = tx.copy()
    tx8['mnemonic'] = 'word1 word2 word3...'
    is_valid, error = verify_signed_transaction_complete(tx8)
    if not is_valid and 'forbidden' in error:
        print("✅ PASS - Mnemonic field rejected")
        passed += 1
    else:
        print(f"❌ FAIL - {error}")
        failed += 1

    print(f"\n{'='*70}")
    print(f"RESULTS: {passed} passed, {failed} failed out of {passed+failed} tests")
    print(f"{'='*70}\n")

    return passed, failed


if __name__ == '__main__':
    passed, failed = test_all_security_checks()
    exit(0 if failed == 0 else 1)
