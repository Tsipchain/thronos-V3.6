"""Wallet-proven Earn Account linking tests.

These tests deliberately exercise only identity/session binding.  They do not
authorize settlement, THC transfers, wallet creation, or payouts.
"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from flask import Flask
from services.earn_account import (
    EarnAccountStore,
    EarnError,
    register_earn_account_routes,
    verify_earn_wallet_proof,
)
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
        keys = ["action", "challenge_id", "expires_at", "nonce", "wallet_address"]
        if challenge.get("approval"):
            keys.append("approval")
        payload = {key: str(challenge[key]) for key in keys}
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

    def test_expired_link_challenge_is_rejected_before_proof(self):
        user = self._register()
        challenge = self.store.wallet_link_challenge(user["earn_user_id"], self.wallet)
        with self.store._tx() as con:
            con.execute(
                "UPDATE earn_wallet_challenges SET expires_at = 1 WHERE challenge_id = ?",
                (challenge["challenge_id"],),
            )
        with self.assertRaisesRegex(EarnError, "invalid_or_expired_wallet_challenge"):
            self.store.wallet_challenge_for_proof(
                challenge_id=challenge["challenge_id"], purpose="link",
                wallet_address=self.wallet, earn_user_id=user["earn_user_id"],
            )

    def test_link_proof_is_bound_to_biometric_passkey_requirement(self):
        user = self._register()
        challenge = self.store.wallet_link_challenge(user["earn_user_id"], self.wallet)
        self.assertEqual(challenge["approval"], "biometric_passkey")
        proof = self._proof(challenge)
        self.assertTrue(verify_earn_wallet_proof(
            challenge, wallet_address=self.wallet,
            public_key=proof["public_key"], signature=proof["signature"],
        ))
        downgraded = dict(challenge)
        downgraded.pop("approval")
        self.assertFalse(verify_earn_wallet_proof(
            downgraded, wallet_address=self.wallet,
            public_key=proof["public_key"], signature=proof["signature"],
        ))

    def test_wallet_link_isolated_to_one_earn_account(self):
        alice = self._register()
        bob = self.store.register("wallet-b@example.com", "password456")
        challenge = self.store.wallet_link_challenge(alice["earn_user_id"], self.wallet)
        proof = self._proof(challenge)
        self.store.complete_wallet_link(
            challenge_id=challenge["challenge_id"], earn_user_id=alice["earn_user_id"],
            wallet_address=self.wallet, public_key=proof["public_key"],
        )
        second = self.store.wallet_link_challenge(bob["earn_user_id"], self.wallet)
        second_proof = self._proof(second)
        with self.assertRaisesRegex(EarnError, "wallet_already_linked"):
            self.store.complete_wallet_link(
                challenge_id=second["challenge_id"], earn_user_id=bob["earn_user_id"],
                wallet_address=self.wallet, public_key=second_proof["public_key"],
            )
        self.assertEqual(self.store.wallet_link_for_user(alice["earn_user_id"])["wallet_address"], self.wallet)
        self.assertIsNone(self.store.wallet_link_for_user(bob["earn_user_id"]))

    def test_server_requires_live_mobile_approval_when_wallet_has_3fa(self):
        user = self._register()
        app = Flask(__name__)
        app.config["TESTING"] = True
        register_earn_account_routes(app, self.store)
        client = app.test_client()
        login = client.post("/api/earn/login", json={
            "email": "wallet@example.com", "password": "password123",
        }).get_json()
        headers = {"Authorization": "Bearer " + login["access_token"]}
        challenge = client.post("/api/earn/wallet-link/challenge", headers=headers, json={
            "wallet_address": self.wallet,
        }).get_json()
        proof = self._proof(challenge)
        with patch("services.earn_account._wallet_link_requires_mobile_approval", return_value=True), \
             patch("services.earn_account._verified_mobile_wallet_approval", return_value=False):
            denied = client.post("/api/earn/wallet-link/complete", headers=headers, json=proof)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.get_json()["error"], "mobile_wallet_approval_required")

    def test_http_link_completion_rejects_unsigned_challenge(self):
        user = self._register()
        app = Flask(__name__)
        app.config["TESTING"] = True
        register_earn_account_routes(app, self.store)
        client = app.test_client()
        login = client.post("/api/earn/login", json={
            "email": "wallet@example.com", "password": "password123",
        }).get_json()
        headers = {"Authorization": "Bearer " + login["access_token"]}
        challenge = client.post("/api/earn/wallet-link/challenge", headers=headers, json={
            "wallet_address": self.wallet,
        }).get_json()
        proof = self._proof(challenge)
        proof["signature"] = "00" * 64
        rejected = client.post("/api/earn/wallet-link/complete", headers=headers, json=proof)
        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(rejected.get_json()["error"], "invalid_wallet_proof")
        self.assertIsNone(self.store.wallet_link_for_user(user["earn_user_id"]))

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
        self.assertIn("linkEarnWalletFromActivity", app)
        self.assertIn("await _linkActiveWalletToEarn(earnBase)", app)
        self.assertNotIn("cashout_execute", app)
        self.assertIn("earn_data_unavailable", app)
        self.assertIn("No zero balance is assumed", app)
        self.assertIn("Provider amount pending", app)
        self.assertIn("requireTxApproval({", app)
        link_block = app[
            app.index("async function _linkActiveWalletToEarn"):
            app.index("function _formatEarnThc")
        ]
        self.assertLess(
            link_block.index("const biometricApproved = await requireTxApproval"),
            link_block.index("const proof = await _signEarnWalletChallenge(challenge)"),
        )
        self.assertIn("mobile_approval_id", app)
        self.assertIn("Clearance date not yet received from provider.", app)
        self.assertNotIn("return '0.00';", app[app.index("function _formatEarnThc"):app.index("async function showEarn")])


if __name__ == "__main__":
    unittest.main()
