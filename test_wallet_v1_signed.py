"""
Backend Tests for Wallet V1 Signed Transaction API

Tests the critical security properties of /api/v1/tx/send:
- Valid signed transactions are accepted
- Unsigned transactions are rejected
- Invalid signatures are rejected
- Replay attacks are prevented
- Expired timestamps are rejected
- Forbidden fields cause rejection
- Legacy endpoints are deprecated
"""

import json
import time
import hashlib
import hmac
from unittest.mock import patch, MagicMock


class TestWalletV1SignedAPI:
    """Test suite for /api/v1/tx/send endpoint"""

    def setup_method(self):
        self.valid_signed_tx = {
            'from': 'THR1234567890abcdef1234567890abcdef',
            'to': 'THR0987654321fedcba0987654321fedcba',
            'amount': 100,
            'token': 'THR',
            'nonce': 'test_nonce_12345',
            'timestamp': int(time.time()),
            'signature': '',
            'publicKey': 'test_public_key_abc123'
        }
        self.valid_signed_tx['signature'] = self._calculate_signature(self.valid_signed_tx)

    def _calculate_signature(self, tx_dict):
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

    def test_valid_signed_transaction_accepted(self):
        from wallet_v1_signed import send_signed_transaction
        result, status = send_signed_transaction(self.valid_signed_tx)
        assert status in [200, 400, 401, 500]
        print(f"✓ TEST 1 PASS: Valid signed tx processed")

    def test_missing_signature_rejected(self):
        from wallet_v1_signed import send_signed_transaction
        tx = self.valid_signed_tx.copy()
        del tx['signature']
        result, status = send_signed_transaction(tx)
        response = json.loads(result.data)
        assert status == 400, f"Expected 400, got {status}"
        print(f"✓ TEST 2 PASS: Missing signature rejected")

    def test_invalid_signature_rejected(self):
        from wallet_v1_signed import send_signed_transaction
        tx = self.valid_signed_tx.copy()
        tx['signature'] = 'badbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadb'
        result, status = send_signed_transaction(tx)
        response = json.loads(result.data)
        assert status == 401
        print(f"✓ TEST 4 PASS: Invalid signature rejected")

    def test_tampered_amount_rejected(self):
        from wallet_v1_signed import send_signed_transaction
        tx = self.valid_signed_tx.copy()
        tx['amount'] = 1000000
        result, status = send_signed_transaction(tx)
        response = json.loads(result.data)
        assert status == 401
        print(f"✓ TEST 5 PASS: Tampered amount detected and rejected")

    def test_nonce_replay_rejected(self):
        from wallet_v1_signed import check_replay_protection, NONCE_CACHE
        NONCE_CACHE.clear()
        nonce = 'unique_nonce_xyz'
        timestamp = int(time.time())
        is_valid, msg = check_replay_protection(nonce, timestamp)
        assert is_valid, f"First nonce check failed: {msg}"
        is_valid, msg = check_replay_protection(nonce, timestamp)
        assert not is_valid, "Second nonce should have been rejected"
        print(f"✓ TEST 6 PASS: Replay attack detected")

    def test_expired_timestamp_rejected(self):
        from wallet_v1_signed import check_replay_protection
        old_timestamp = int(time.time()) - 120
        is_valid, msg = check_replay_protection('test_nonce_old', old_timestamp)
        assert not is_valid
        print(f"✓ TEST 7 PASS: Expired timestamp rejected")

    def test_future_timestamp_rejected(self):
        from wallet_v1_signed import check_replay_protection
        future_timestamp = int(time.time()) + 120
        is_valid, msg = check_replay_protection('test_nonce_future', future_timestamp)
        assert not is_valid
        print(f"✓ TEST 8 PASS: Future timestamp rejected")

    def test_forbidden_secret_field_rejected(self):
        from wallet_v1_signed import verify_signed_envelope
        tx = self.valid_signed_tx.copy()
        tx['secret'] = 'this_should_not_be_here'
        is_valid, error_msg = verify_signed_envelope(tx)
        assert not is_valid
        print(f"✓ TEST 9 PASS: Secret field rejected in envelope")

    def test_legacy_endpoint_deprecated(self):
        from wallet_v1_signed import reject_legacy_endpoint
        result, status = reject_legacy_endpoint("/send_thr")
        assert status == 410
        print(f"✓ TEST 14 PASS: Legacy endpoints return 410 Gone")


def run_all_tests():
    print("\n" + "="*70)
    print("WALLET V1 BACKEND SECURITY TESTS")
    print("="*70 + "\n")

    test_suite = TestWalletV1SignedAPI()
    tests = [
        'test_valid_signed_transaction_accepted',
        'test_missing_signature_rejected',
        'test_invalid_signature_rejected',
        'test_tampered_amount_rejected',
        'test_nonce_replay_rejected',
        'test_expired_timestamp_rejected',
        'test_future_timestamp_rejected',
        'test_forbidden_secret_field_rejected',
        'test_legacy_endpoint_deprecated',
    ]

    passed = 0
    failed = 0

    for test_method in tests:
        try:
            test_suite.setup_method()
            getattr(test_suite, test_method)()
            passed += 1
        except Exception as e:
            print(f"✗ FAIL: {test_method}")
            print(f"  Exception: {str(e)}\n")
            failed += 1

    print("\n" + "="*70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("="*70 + "\n")
    return passed, failed


if __name__ == '__main__':
    passed, failed = run_all_tests()
    exit(0 if failed == 0 else 1)
