"""
Tests for Maker Agent — signer compatibility, agent workflow.

Verifies that the Maker Agent's wallet signer produces intents
and signatures that the Thronos node can verify.
"""

import copy
import hashlib
import json
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes

from maker_agent.signer import WalletSigner


def _generate_test_key():
    """Generate a fresh secp256k1 key pair for testing."""
    private_key = ec.generate_private_key(ec.SECP256K1())
    priv_bytes = private_key.private_numbers().private_value.to_bytes(32, 'big')
    return priv_bytes.hex()


class TestWalletSigner(unittest.TestCase):
    def setUp(self):
        self.key_hex = _generate_test_key()
        self.signer = WalletSigner(self.key_hex)

    def test_address_format(self):
        self.assertTrue(self.signer.address.startswith('THR'))
        self.assertEqual(len(self.signer.address), 43)

    def test_public_key_format(self):
        self.assertEqual(len(self.signer.public_key_hex), 66)
        self.assertIn(self.signer.public_key_hex[:2], ('02', '03'))

    def test_deterministic_address(self):
        signer2 = WalletSigner(self.key_hex)
        self.assertEqual(self.signer.address, signer2.address)
        self.assertEqual(self.signer.public_key_hex, signer2.public_key_hex)

    def test_from_key_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.key', delete=False) as f:
            f.write(self.key_hex)
            f.flush()
            signer2 = WalletSigner.from_key_file(f.name)
        os.unlink(f.name)
        self.assertEqual(signer2.address, self.signer.address)


class TestIntentCreation(unittest.TestCase):
    def setUp(self):
        self.signer = WalletSigner(_generate_test_key())

    def test_intent_has_required_fields(self):
        intent = self.signer.create_intent('physical_asset_produce', {'foo': 'bar'})
        required = ('type', 'version', 'action', 'wallet_id', 'from_thr',
                    'nonce', 'created_at', 'payload_hash')
        for field in required:
            self.assertIn(field, intent, f"missing field: {field}")

    def test_intent_type_and_version(self):
        intent = self.signer.create_intent('physical_asset_produce', {})
        self.assertEqual(intent['type'], 'thronos_wallet_action')
        self.assertEqual(intent['version'], '1')

    def test_intent_action(self):
        intent = self.signer.create_intent('physical_asset_produce', {})
        self.assertEqual(intent['action'], 'physical_asset_produce')

    def test_intent_from_thr(self):
        intent = self.signer.create_intent('physical_asset_produce', {})
        self.assertEqual(intent['from_thr'], self.signer.address)

    def test_payload_hash_matches(self):
        payload = {'batch_id': 'B1', 'quantity': 3}
        intent = self.signer.create_intent('physical_asset_produce', payload)
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        expected_hash = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
        self.assertEqual(intent['payload_hash'], expected_hash)

    def test_unique_nonces(self):
        i1 = self.signer.create_intent('physical_asset_produce', {})
        i2 = self.signer.create_intent('physical_asset_produce', {})
        self.assertNotEqual(i1['nonce'], i2['nonce'])

    def test_created_at_recent(self):
        intent = self.signer.create_intent('physical_asset_produce', {})
        ts = int(intent['created_at'])
        self.assertAlmostEqual(ts, int(time.time()), delta=5)


class TestSignatureVerification(unittest.TestCase):
    """Verify that signatures produced by the signer can be verified
    using the same algorithm the node uses."""

    def setUp(self):
        self.signer = WalletSigner(_generate_test_key())

    def _node_canonical(self, intent):
        """Replicate server_ext.py _canonical_wallet_action_intent()."""
        fields = ('action', 'amount', 'asset', 'chain', 'created_at', 'from_thr',
                  'nonce', 'payload_hash', 'recipient', 'type', 'version', 'wallet_id')
        parts = [f'"{k}":{json.dumps(str(intent.get(k, "")))}' for k in fields]
        return '{' + ','.join(parts) + '}'

    def _node_verify(self, intent, signature_hex, public_key_hex):
        """Replicate server_ext.py verification steps 7+8."""
        canonical = self._node_canonical(intent).encode('utf-8')
        pub_bytes = bytes.fromhex(public_key_hex)
        sig_bytes = bytes.fromhex(signature_hex)
        pub_obj = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256K1(), pub_bytes)
        pub_obj.verify(sig_bytes, canonical, ec.ECDSA(hashes.SHA256()))

    def test_signature_valid_on_node(self):
        payload = {'batch_id': 'B1', 'sku': 'TPC'}
        intent = self.signer.create_intent('physical_asset_produce', payload)
        sig = self.signer.sign_intent(intent)
        self._node_verify(intent, sig, self.signer.public_key_hex)

    def test_tampered_intent_rejected(self):
        payload = {'batch_id': 'B1'}
        intent = self.signer.create_intent('physical_asset_produce', payload)
        sig = self.signer.sign_intent(intent)

        tampered = dict(intent)
        tampered['action'] = 'nft_buy'

        with self.assertRaises(Exception):
            self._node_verify(tampered, sig, self.signer.public_key_hex)

    def test_wrong_key_rejected(self):
        other_signer = WalletSigner(_generate_test_key())
        payload = {'batch_id': 'B1'}
        intent = self.signer.create_intent('physical_asset_produce', payload)
        sig = self.signer.sign_intent(intent)

        with self.assertRaises(Exception):
            self._node_verify(intent, sig, other_signer.public_key_hex)


class TestAddressDerivation(unittest.TestCase):
    """Verify maker agent derives addresses the same way as the node."""

    def test_matches_node_derivation(self):
        import wallet_v1_production_final as wv1
        key_hex = _generate_test_key()
        signer = WalletSigner(key_hex)
        node_addr = wv1.derive_thronos_address(signer.public_key_hex)
        self.assertEqual(signer.address, node_addr)


class TestBuildSignedRequest(unittest.TestCase):
    def setUp(self):
        self.signer = WalletSigner(_generate_test_key())

    def test_request_structure(self):
        req = self.signer.build_signed_request(
            'physical_asset_produce', {'batch_id': 'B1'})
        self.assertIn('intent', req)
        self.assertIn('signature', req)
        self.assertIn('public_key', req)
        self.assertIn('payload', req)
        self.assertEqual(req['public_key'], self.signer.public_key_hex)
        self.assertEqual(req['payload'], {'batch_id': 'B1'})

    def test_payload_hash_in_request(self):
        payload = {'x': 1, 'y': 2}
        req = self.signer.build_signed_request('physical_asset_produce', payload)
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        expected = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
        self.assertEqual(req['intent']['payload_hash'], expected)


class TestFileHashing(unittest.TestCase):
    def test_hash_file(self):
        from maker_agent.agent import MakerAgent
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b'test 3mf content for hashing')
            f.flush()
            h = MakerAgent.hash_file(f.name)
        os.unlink(f.name)
        expected = hashlib.sha256(b'test 3mf content for hashing').hexdigest()
        self.assertEqual(h, expected)


if __name__ == '__main__':
    unittest.main()
