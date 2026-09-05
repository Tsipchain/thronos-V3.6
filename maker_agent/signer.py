"""
Wallet Action Intent Signer for Maker Agent.

Creates and signs wallet action intents that the Thronos node can verify
via _verify_wallet_action_intent() in server_ext.py.

Canonical format, SHA-256 hashing, and ECDSA/secp256k1 DER signatures
must match the node's verification exactly.
"""

import hashlib
import json
import os
import time
import uuid

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
)


class WalletSigner:
    def __init__(self, private_key_hex: str):
        priv_bytes = bytes.fromhex(private_key_hex)
        priv_int = int.from_bytes(priv_bytes, 'big')
        self._private_key = ec.derive_private_key(priv_int, ec.SECP256K1())
        self._public_key = self._private_key.public_key()

        pub_bytes = self._public_key.public_bytes(
            Encoding.X962, PublicFormat.CompressedPoint)
        self.public_key_hex = pub_bytes.hex()

        self.address = self._derive_address(self.public_key_hex)

    @staticmethod
    def _derive_address(public_key_hex: str) -> str:
        pub_bytes = bytes.fromhex(public_key_hex)
        sha256_hash = hashlib.sha256(pub_bytes).digest()
        ripemd160 = hashlib.new('ripemd160')
        ripemd160.update(sha256_hash)
        return 'THR' + ripemd160.digest().hex().upper()[:40]

    @staticmethod
    def from_key_file(path: str) -> 'WalletSigner':
        with open(path, 'r') as f:
            key_hex = f.read().strip()
        return WalletSigner(key_hex)

    def create_intent(
        self,
        action: str,
        payload: dict,
        wallet_id: str = '',
    ) -> dict:
        payload_canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        payload_hash = hashlib.sha256(payload_canonical.encode('utf-8')).hexdigest()

        intent = {
            'type': 'thronos_wallet_action',
            'version': '1',
            'action': action,
            'wallet_id': wallet_id or self.address,
            'from_thr': self.address,
            'nonce': uuid.uuid4().hex,
            'created_at': str(int(time.time())),
            'payload_hash': payload_hash,
            'amount': '',
            'asset': '',
            'chain': '',
            'recipient': '',
        }
        return intent

    def _canonical_intent_msg(self, intent: dict) -> str:
        fields = ('action', 'amount', 'asset', 'chain', 'created_at', 'from_thr',
                  'nonce', 'payload_hash', 'recipient', 'type', 'version', 'wallet_id')
        parts = [f'"{k}":{json.dumps(str(intent.get(k, "")))}' for k in fields]
        return '{' + ','.join(parts) + '}'

    def sign_intent(self, intent: dict) -> str:
        canonical = self._canonical_intent_msg(intent).encode('utf-8')
        sig = self._private_key.sign(canonical, ec.ECDSA(hashes.SHA256()))
        return sig.hex()

    def build_signed_request(
        self,
        action: str,
        payload: dict,
        wallet_id: str = '',
    ) -> dict:
        intent = self.create_intent(action, payload, wallet_id)
        signature = self.sign_intent(intent)
        return {
            'intent': intent,
            'signature': signature,
            'public_key': self.public_key_hex,
            'payload': payload,
        }
