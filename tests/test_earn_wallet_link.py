"""Wallet-proven Earn Account linking tests.

These tests deliberately exercise only identity/session binding.  They do not
authorize settlement, THC transfers, wallet creation, or payouts.
"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from services.earn_account import EarnAccountStore, EarnError, verify_earn_wallet_proof
from wallet_v1_address_derivation import derive_thronos_address


class EarnWalletLinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = EarnAccountStore(
            str(Path(self.tmp.name) / "earn.db"), "wallet-link-test-key",
        )
        self.private = ec.generate_private_key(ec.SECP256K1())
        self.public_key = self.private.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint,
        ).hex()
        self.wallet = derive_thronos_address(self.public_key)

    def tearDown(self):
        self.tmp.cleanup()

    def _proof(self, challenge):
        payload = {key: str(challenge[key]) for key in (
            "action", "challenge_id", "expires_at", "nonce", "wallet_address",
        )}
        message = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        der = self.private.sign(
            hashlib.sha256(message).digest(),
            ec.ECDSA(utils.Prehashed(hashes.SHA256())),
        )
        r, s = utils.decode_dss_signature(der)
        return {
            "challenge_id": challenge["challenge_id"],
            "wallet_address": self.wallet,
            "public_key": self.public_key,
            "signature": f"{r:064x}{s:064x}",
        }

    def _register(self):
        return self.store.register("wallet@example.com", "password123")

    def test_signed_link_then_wallet_session_login(self):
        user = self._register()
        challenge = self.store.wallet_link_challenge(user["earn_user_id"], self.wallet)
        proof = self._proof(challenge)
        self.assertTrue(verify_earn_wallet_proof(
            challenge, wallet_address=self.wallet,
            public_key=proof["public_key"], signature=proof["signature"],
        ))
        complete = self.store.complete_wallet_link(
            challenge_id=challenge["challenge_id"], earn_user_id=user["earn_user_id"],
            wallet_address=self.wallet, public_key=proof["public_key"],
        )
        self.assertEqual(complete["wallet_address"], self.wallet)

        login_challenge = self.store.wallet_login_challenge(self.wallet)
        login_proof = self._proof(login_challenge)
        self.assertTrue(verify_earn_wallet_proof(
            login_challenge, wallet_address=self.wallet,
            public_key=login_proof["public_key"], signature=login_proof["signature"],
        ))
        linked_user, token = self.store.complete_wallet_login(
            challenge_id=login_challenge["challenge_id"], wallet_address=self.wallet,
        )
        self.assertEqual(linked_user["earn_user_id"], user["earn_user_id"])
        self.assertIsNotNone(self.store.user_for_session(token))

    def test_link_challenge_cannot_be_replayed(self):
        user = self._register()
        challenge = self.store.wallet_link_challenge(user["earn_user_id"], self.wallet)
        proof = self._proof(challenge)
        self.store.complete_wallet_link(
            challenge_id=challenge["challenge_id"], earn_user_id=user["earn_user_id"],
            wallet_address=self.wallet, public_key=proof["public_key"],
        )
        with self.assertRaisesRegex(EarnError, "invalid_or_expired_wallet_challenge"):
            self.store.complete_wallet_link(
                challenge_id=challenge["challenge_id"], earn_user_id=user["earn_user_id"],
                wallet_address=self.wallet, public_key=proof["public_key"],
            )

    def test_tampered_signature_is_rejected(self):
        user = self._register()
        challenge = self.store.wallet_link_challenge(user["earn_user_id"], self.wallet)
        proof = self._proof(challenge)
        proof["signature"] = "00" * 64
        self.assertFalse(verify_earn_wallet_proof(
            challenge, wallet_address=self.wallet,
            public_key=proof["public_key"], signature=proof["signature"],
        ))

    def test_pwa_activity_button_uses_the_authenticated_activity_handoff(self):
        root = Path(__file__).parent.parent / "public" / "wallet-pwa"
        index = (root / "index.html").read_text()
        handoff = (root / "earn-activity-handoff.js").read_text()
        app = (root / "app.js").read_text()
        self.assertIn("earn-activity-handoff.js", index)
        self.assertIn("#openEarnCenterBtn", handoff)
        self.assertIn("window.__thronosOpenEarnActivity", handoff)
        self.assertNotIn("/earn?view=activity", handoff)
        self.assertIn("window.__thronosOpenEarnActivity = openEarnActivity", app)
        self.assertIn("Pending receipts remain unavailable until provider clearance.", app)
        self.assertIn("_formatEarnThc", app)


if __name__ == "__main__":
    unittest.main()
