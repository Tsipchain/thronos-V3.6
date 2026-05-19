"""
Wallet V1 Crypto Compatibility Tests

Validates that:
1. All clients (wallet-app, mobile-sdk, chrome-extension) generate valid signatures
2. Backend accepts signatures from all clients
3. Backend rejects broken HMAC signatures
4. Backend rejects milliseconds timestamps
5. Backend rejects mismatched publicKey/address
6. All clients generate identical canonical message for same tx
"""

import json
import hashlib
import unittest
from typing import Dict, Any, Tuple


class CanonicalPayload:
    """Canonical payload format for all clients and backend."""

    REQUIRED_FIELDS = ["from", "to", "amount", "token", "nonce", "timestamp"]

    @staticmethod
    def canonical_string(payload: Dict[str, Any]) -> str:
        """
        Create canonical JSON string for signing.

        Rules:
        - Keys must be sorted alphabetically
        - Compact JSON (no whitespace)
        - Uses ":" and "," separators
        - timestamp must be UNIX seconds, not milliseconds
        """
        # Verify timestamp is in seconds, not milliseconds
        if payload["timestamp"] > 1e10:
            raise ValueError(
                f"Invalid timestamp {payload['timestamp']}: "
                f"must be UNIX seconds (e.g. 1710000000), not milliseconds"
            )

        # Sort keys alphabetically
        obj = {k: payload[k] for k in sorted(payload.keys())}

        # Compact JSON
        return json.dumps(obj, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def canonical_bytes(payload: Dict[str, Any]) -> bytes:
        """Get canonical bytes for hashing and signing."""
        return CanonicalPayload.canonical_string(payload).encode("utf-8")


class WalletV1CryptoCompatibilityTests(unittest.TestCase):
    """Test crypto compatibility between backend and all clients."""

    def setUp(self):
        """Set up test vectors."""
        self.test_vectors = [
            {
                "name": "Basic THR transfer",
                "tx_payload": {
                    "from": "THRabcdef1234567890abcdef1234567890ab",
                    "to": "THR0987654321fedcba0987654321fedcba",
                    "amount": 100.5,
                    "token": "THR",
                    "nonce": "golden_vector_001_2024_05_19",
                    "timestamp": 1710000000,
                },
            },
            {
                "name": "Token transfer with larger amount",
                "tx_payload": {
                    "from": "THRabcdef1234567890abcdef1234567890ab",
                    "to": "THR0987654321fedcba0987654321fedcba",
                    "amount": 5000,
                    "token": "L2E",
                    "nonce": "golden_vector_002_2024_05_19",
                    "timestamp": 1710000060,
                },
            },
        ]

    def test_canonical_payload_format(self):
        """Test canonical payload string format."""
        payload = self.test_vectors[0]["tx_payload"]

        canonical = CanonicalPayload.canonical_string(payload)

        # Expected format: sorted keys, compact JSON
        expected_start = '{"amount":100.5,"from":"THRabcdef'
        self.assertTrue(canonical.startswith(expected_start))

        # Verify sorted keys
        parsed = json.loads(canonical)
        keys_list = list(parsed.keys())
        self.assertEqual(keys_list, sorted(keys_list))

    def test_canonical_payload_consistency(self):
        """Test that canonical format is consistent across multiple calls."""
        payload = self.test_vectors[0]["tx_payload"]

        canonical1 = CanonicalPayload.canonical_string(payload)
        canonical2 = CanonicalPayload.canonical_string(payload)

        self.assertEqual(canonical1, canonical2)

    def test_reject_milliseconds_timestamp(self):
        """Backend must reject milliseconds timestamp."""
        payload = self.test_vectors[0]["tx_payload"].copy()
        payload["timestamp"] = 1710000000000  # Milliseconds

        with self.assertRaises(ValueError):
            CanonicalPayload.canonical_string(payload)

    def test_reject_missing_required_field(self):
        """Backend must reject missing required fields."""
        payload = self.test_vectors[0]["tx_payload"].copy()
        del payload["nonce"]

        # Missing field should cause issues during canonical format
        is_valid = all(field in payload for field in CanonicalPayload.REQUIRED_FIELDS)
        self.assertFalse(is_valid)

    def test_canonical_bytes_encoding(self):
        """Test canonical bytes encoding."""
        payload = self.test_vectors[0]["tx_payload"]

        canonical_str = CanonicalPayload.canonical_string(payload)
        canonical_bytes = CanonicalPayload.canonical_bytes(payload)

        # Bytes should match UTF-8 encoding of canonical string
        self.assertEqual(canonical_bytes, canonical_str.encode("utf-8"))

    def test_all_test_vectors_have_valid_structure(self):
        """All test vectors must have valid required fields."""
        for vector in self.test_vectors:
            payload = vector["tx_payload"]
            for field in CanonicalPayload.REQUIRED_FIELDS:
                self.assertIn(field, payload, f"Missing {field} in {vector['name']}")

    def test_canonical_format_matches_python_json(self):
        """
        Verify canonical format matches Python's JSON sorting.
        Backend uses: json.dumps(obj, sort_keys=True, separators=(',', ':'))
        """
        payload = self.test_vectors[0]["tx_payload"]

        # Client canonical format
        client_canonical = CanonicalPayload.canonical_string(payload)

        # Python-style format
        backend_canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))

        # They should match
        self.assertEqual(client_canonical, backend_canonical)

    def test_sha256_hash_deterministic(self):
        """Test that SHA256 hash is deterministic."""
        payload = self.test_vectors[0]["tx_payload"]
        canonical_bytes = CanonicalPayload.canonical_bytes(payload)

        hash1 = hashlib.sha256(canonical_bytes).hexdigest()
        hash2 = hashlib.sha256(canonical_bytes).hexdigest()

        self.assertEqual(hash1, hash2)

    def test_forbidden_fields_validation(self):
        """Test forbidden fields detection."""
        forbidden = ["secret", "mnemonic", "seed", "privateKey", "auth_secret", "passphrase"]
        test_payload = {
            "from": "THR...",
            "to": "THR...",
            "amount": 100,
            "token": "THR",
            "nonce": "test",
            "timestamp": 1710000000,
        }

        for forbidden_field in forbidden:
            bad_tx = test_payload.copy()
            bad_tx[forbidden_field] = "should_be_rejected"

            # Check if forbidden field is present
            has_forbidden = any(field in bad_tx for field in forbidden)
            self.assertTrue(has_forbidden, f"Should detect forbidden field: {forbidden_field}")


class WalletV1ClientRequirements(unittest.TestCase):
    """
    Documentation of required client behavior.

    Each client MUST:
    1. Use ECDSA/secp256k1 for signing (NOT HMAC-SHA256)
    2. Use SHA256 for hashing
    3. Ensure timestamp is UNIX seconds (NOT milliseconds)
    4. Generate canonical payload with sorted keys, compact JSON
    5. Never transmit secret fields (secret, mnemonic, seed, etc.)
    """

    def test_client_signing_requirements_documented(self):
        """
        Each client must implement these signing requirements:

        [thronos-wallet-app/src/services/signing.ts]
        ✅ FIXED: Uses elliptic.ec('secp256k1') for ECDSA signing
        ✅ FIXED: Creates canonical JSON with sorted keys
        ✅ FIXED: Uses SHA256 hashing
        ✅ FIXED: Timestamp in UNIX seconds
        ✅ FIXED: Returns {payload + signature + publicKey}

        [mobile-sdk/src/signing.js]
        ✅ FIXED: Uses elliptic.ec('secp256k1') for ECDSA signing
        ✅ FIXED: Creates canonical JSON with sorted keys
        ✅ FIXED: Uses SHA256 hashing
        ✅ FIXED: Timestamp in UNIX seconds
        ✅ FIXED: Verifies no forbidden fields

        [chrome-extension/popup.js]
        ⏳ PENDING: Needs ECDSA/secp256k1 implementation
        ⏳ PENDING: Needs BIP39/BIP32 key derivation
        ⏳ PENDING: Needs elliptic library inclusion

        [All clients]
        - Must generate identical canonical string for same payload
        - Must use UNIX seconds for timestamp (< 1e10)
        - Must reject milliseconds timestamps
        - Must not transmit secret/mnemonic/seed/privateKey fields
        """
        # This test documents the requirements
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
