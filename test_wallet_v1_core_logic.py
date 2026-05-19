"""
Backend Tests for Wallet V1 Core Security Logic (Flask-independent)

Tests the critical security properties of transaction verification:
- Signature verification logic
- Replay protection with nonce/timestamp
- Forbidden field detection
- Required field validation
"""

import json
import time
import hashlib
import hmac
import sys


def calculate_signature(tx_dict):
    tx_for_signing = {
        'from': tx_dict.get('from'),
        'to': tx_dict.get('to'),
        'amount': tx_dict.get('amount'),
        'token': tx_dict.get('token', 'THR'),
        'nonce': tx_dict.get('nonce'),
        'timestamp': tx_dict.get('timestamp')
    }
    message = json.dumps(tx_for_signing, sort_keys=True, separators=(',', ':'))
    public_key = tx_dict.get('publicKey', '')
    return hmac.new(
        public_key.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()


def verify_signed_envelope(signed_tx: dict) -> tuple:
    required_fields = ['from', 'to', 'amount', 'signature', 'publicKey', 'nonce', 'timestamp']
    for field in required_fields:
        if field not in signed_tx:
            return False, f"missing_required_field:{field}"

    forbidden_fields = ['secret', 'mnemonic', 'seed', 'privateKey', 'auth_secret', 'passphrase']
    for field in forbidden_fields:
        if field in signed_tx:
            return False, f"forbidden_field_in_envelope:{field}"

    return True, ""


def verify_signature(signed_tx: dict) -> tuple:
    signature = signed_tx.get('signature')
    public_key = signed_tx.get('publicKey')

    if not signature or not public_key:
        return False, "missing_signature_or_publickey"

    tx_for_signing = {
        'from': signed_tx.get('from'),
        'to': signed_tx.get('to'),
        'amount': signed_tx.get('amount'),
        'token': signed_tx.get('token', 'THR'),
        'nonce': signed_tx.get('nonce'),
        'timestamp': signed_tx.get('timestamp')
    }

    message = json.dumps(tx_for_signing, sort_keys=True, separators=(',', ':'))
    expected_signature = hmac.new(
        public_key.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        return False, "invalid_signature"

    return True, ""


NONCE_CACHE = {}
NONCE_CACHE_TTL = 300
MAX_TIMESTAMP_DRIFT = 60


def check_replay_protection(nonce: str, timestamp: int) -> tuple:
    current_time = int(time.time())
    timestamp_drift = abs(current_time - timestamp)

    if timestamp_drift > MAX_TIMESTAMP_DRIFT:
        return False, f"timestamp_outside_tolerance:drift_{timestamp_drift}s"

    if nonce in NONCE_CACHE:
        return False, "nonce_replay_detected"

    NONCE_CACHE[nonce] = time.time()

    current_time_s = time.time()
    expired_nonces = [n for n, t in NONCE_CACHE.items() if current_time_s - t > NONCE_CACHE_TTL]
    for n in expired_nonces:
        del NONCE_CACHE[n]

    return True, ""


class TestResults:
    def __init__(self):
        self.tests = []
        self.passed = 0
        self.failed = 0

    def add_test(self, name, passed, error=None):
        self.tests.append((name, passed, error))
        if passed:
            self.passed += 1
            print(f"✓ {name}")
        else:
            self.failed += 1
            print(f"✗ {name}")
            if error:
                print(f"  {error}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*70}")
        print(f"RESULTS: {self.passed}/{total} tests passed")
        print(f"{'='*70}\n")
        return self.failed == 0


def test_signature_verification():
    results = TestResults()
    tx = {
        'from': 'THR1234567890abcdef', 'to': 'THR0987654321fedcba',
        'amount': 100, 'token': 'THR', 'nonce': 'nonce_123',
        'timestamp': int(time.time()), 'publicKey': 'test_public_key'
    }
    tx['signature'] = calculate_signature(tx)

    is_valid, msg = verify_signature(tx)
    results.add_test("Valid signature accepted", is_valid, msg if not is_valid else None)

    tx_bad = tx.copy()
    tx_bad['signature'] = 'badbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadb'
    is_valid, msg = verify_signature(tx_bad)
    results.add_test("Invalid signature rejected", not is_valid)

    tx_tampered = tx.copy()
    tx_tampered['amount'] = 999999
    is_valid, msg = verify_signature(tx_tampered)
    results.add_test("Tampered amount detected", not is_valid)

    tx_tampered2 = tx.copy()
    tx_tampered2['from'] = 'THR_DIFFERENT_ADDRESS'
    is_valid, msg = verify_signature(tx_tampered2)
    results.add_test("Tampered from address detected", not is_valid)

    return results


def test_envelope_validation():
    results = TestResults()
    base_tx = {
        'from': 'THR1234567890abcdef', 'to': 'THR0987654321fedcba',
        'amount': 100, 'signature': 'sig_abc', 'publicKey': 'pub_key',
        'nonce': 'nonce_123', 'timestamp': int(time.time())
    }

    is_valid, msg = verify_signed_envelope(base_tx)
    results.add_test("All required fields present", is_valid)

    for field in ['from', 'signature', 'nonce', 'timestamp']:
        tx_missing = base_tx.copy()
        del tx_missing[field]
        is_valid, msg = verify_signed_envelope(tx_missing)
        results.add_test(f"Missing '{field}' rejected", not is_valid)

    return results


def test_forbidden_fields():
    results = TestResults()
    base_tx = {
        'from': 'THR1234567890abcdef', 'to': 'THR0987654321fedcba',
        'amount': 100, 'signature': 'sig_abc', 'publicKey': 'pub_key',
        'nonce': 'nonce_123', 'timestamp': int(time.time())
    }

    for field in ['secret', 'mnemonic', 'seed', 'privateKey', 'auth_secret', 'passphrase']:
        tx = base_tx.copy()
        tx[field] = 'should_not_be_here'
        is_valid, msg = verify_signed_envelope(tx)
        results.add_test(f"Forbidden field '{field}' rejected", not is_valid)

    return results


def test_replay_protection():
    results = TestResults()
    NONCE_CACHE.clear()
    current_time = int(time.time())

    nonce1 = 'unique_nonce_1'
    is_valid, msg = check_replay_protection(nonce1, current_time)
    results.add_test("Valid nonce and timestamp accepted", is_valid)

    is_valid, msg = check_replay_protection(nonce1, current_time)
    results.add_test("Replayed nonce rejected", not is_valid)

    is_valid, msg = check_replay_protection('unique_nonce_2', current_time - 120)
    results.add_test("Old timestamp (>60s) rejected", not is_valid)

    is_valid, msg = check_replay_protection('unique_nonce_3', current_time + 120)
    results.add_test("Future timestamp (>60s) rejected", not is_valid)

    is_valid, msg = check_replay_protection('unique_nonce_4', current_time + 30)
    results.add_test("Timestamp within tolerance accepted", is_valid)

    return results


def test_comprehensive_security_checks():
    results = TestResults()
    NONCE_CACHE.clear()
    current_time = int(time.time())
    tx = {
        'from': 'THR1111111111111111', 'to': 'THR2222222222222222',
        'amount': 50, 'token': 'THR', 'nonce': 'comprehensive_nonce_1',
        'timestamp': current_time, 'publicKey': 'comprehensive_test_key'
    }
    tx['signature'] = calculate_signature(tx)

    is_valid, msg = verify_signed_envelope(tx)
    results.add_test("STEP 1: Envelope structure valid", is_valid)

    if is_valid:
        is_valid, msg = verify_signature(tx)
        results.add_test("STEP 2: Signature verification valid", is_valid)

    if is_valid:
        is_valid, msg = check_replay_protection(tx['nonce'], tx['timestamp'])
        results.add_test("STEP 3: Replay protection passed", is_valid)

    if is_valid:
        is_valid, msg = check_replay_protection(tx['nonce'], tx['timestamp'])
        results.add_test("STEP 4: Replay attack detected", not is_valid)

    return results


def main():
    print("\n" + "="*70)
    print("WALLET V1 BACKEND SECURITY TESTS (Core Logic)")
    print("="*70 + "\n")

    test_suites = [
        ("SIGNATURE VERIFICATION", test_signature_verification()),
        ("ENVELOPE VALIDATION", test_envelope_validation()),
        ("FORBIDDEN FIELDS", test_forbidden_fields()),
        ("REPLAY PROTECTION", test_replay_protection()),
        ("COMPREHENSIVE FLOW", test_comprehensive_security_checks()),
    ]

    total_passed = 0
    total_failed = 0

    for suite_name, results in test_suites:
        print(f"\n{suite_name}:")
        print("-" * 70)
        total_passed += results.passed
        total_failed += results.failed

    print("\n" + "="*70)
    print(f"TOTAL RESULTS: {total_passed} passed, {total_failed} failed")
    print("="*70 + "\n")

    if total_failed == 0:
        print("✓ ALL BACKEND SECURITY TESTS PASSED")
        return 0
    else:
        print(f"✗ {total_failed} TEST(S) FAILED")
        return 1


if __name__ == '__main__':
    sys.exit(main())
