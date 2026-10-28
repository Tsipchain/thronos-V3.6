import os
import tempfile
import threading
import unittest
from unittest.mock import patch

try:
    from flask import Flask
except ImportError:  # Minimal ledger-only CI environment.
    Flask = None

from services.earn_center import (
    EarnError, EarnStore, build_cpx_offerwall_url, register_earn_routes,
    verify_cpx_postback_signature,
)


class EarnStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = EarnStore(os.path.join(self.tmp.name, "earn.db"), "test-key")
        self.user = self.store.user_for_wallet("THRTESTWALLET000000000001")

    def tearDown(self):
        self.tmp.cleanup()

    def test_server_generated_cpx_identity_is_stable_and_not_wallet(self):
        again = self.store.user_for_wallet("thrtestwallet000000000001")
        self.assertEqual(self.user["earn_user_id"], again["earn_user_id"])
        self.assertNotEqual(self.user["cpx_external_user_id"], self.user["wallet_address"])

    def test_same_provider_event_is_idempotent(self):
        one, created = self.store.record_provider_reward("cpx", "tx-1", self.user["cpx_external_user_id"], "THR", "2.5", {"x": 1})
        two, duplicate = self.store.record_provider_reward("cpx", "tx-1", self.user["cpx_external_user_id"], "THR", "2.5", {"x": 1})
        self.assertTrue(created)
        self.assertFalse(duplicate)
        self.assertEqual(one["reward_id"], two["reward_id"])
        self.assertEqual(len(self.store.history(self.user["earn_user_id"])), 1)

    def test_conflicting_reused_provider_event_is_rejected(self):
        self.store.record_provider_reward("cpx", "tx-1", self.user["cpx_external_user_id"], "THR", "2", {})
        with self.assertRaisesRegex(EarnError, "provider_event_conflict"):
            self.store.record_provider_reward("cpx", "tx-1", self.user["cpx_external_user_id"], "BTC", "2", {})

    def test_paid_requires_real_settlement_identifier(self):
        reward, _ = self.store.record_provider_reward("cpx", "tx-2", self.user["cpx_external_user_id"], "THR", "1", {})
        self.store.transition(reward["reward_id"], "confirmed")
        self.store.transition(reward["reward_id"], "payable")
        with self.assertRaisesRegex(EarnError, "settlement_txid_required"):
            self.store.transition(reward["reward_id"], "paid")
        paid = self.store.transition(reward["reward_id"], "paid", "THR-real-chain-tx")
        self.assertEqual(paid["state"], "paid")

    def test_two_distinct_callbacks_do_not_lose_a_credit(self):
        failures = []
        def add(i):
            try:
                self.store.record_provider_reward("cpx", f"parallel-{i}", self.user["cpx_external_user_id"], "THR", "1", {})
            except Exception as exc:
                failures.append(exc)
        threads = [threading.Thread(target=add, args=(i,)) for i in range(12)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(failures, [])
        self.assertEqual(len(self.store.history(self.user["earn_user_id"])), 12)

    def test_cpx_receipt_is_idempotent_and_reversal_is_retained(self):
        receipt, created = self.store.record_cpx_receipt(
            trans_id="cpx-1", cpx_external_user_id=self.user["cpx_external_user_id"], status=1,
            amount_local="680", amount_usd="1.00", offer_id="offer-1", payload={"status": "1"},
        )
        duplicate, duplicate_created = self.store.record_cpx_receipt(
            trans_id="cpx-1", cpx_external_user_id=self.user["cpx_external_user_id"], status=1,
            amount_local="680", payload={"status": "1"},
        )
        reversed_receipt, changed = self.store.record_cpx_receipt(
            trans_id="cpx-1", cpx_external_user_id=self.user["cpx_external_user_id"], status=2,
            amount_local="680", payload={"status": "2"},
        )
        self.assertTrue(created)
        self.assertFalse(duplicate_created)
        self.assertEqual(receipt["trans_id"], duplicate["trans_id"])
        self.assertTrue(changed)
        self.assertEqual(reversed_receipt["status"], 2)

    def test_cpx_offerwall_hash_is_server_computed_and_callback_mode_is_explicit(self):
        env = {"CPX_APP_ID": "app-1", "CPX_APP_SECURE_HASH": "server-secret", "CPX_POSTBACK_SIGNATURE_MODE": "md5_trans_id_dash_secret_v1"}
        with patch.dict(os.environ, env, clear=False):
            url = build_cpx_offerwall_url(self.user["cpx_external_user_id"])
            self.assertIn("app_id=app-1", url)
            self.assertNotIn("server-secret", url)
            self.assertTrue(verify_cpx_postback_signature("tx-1", "b6b10a51094f564bd112376e1bbcbf3a"))
        with patch.dict(os.environ, {"CPX_POSTBACK_SIGNATURE_MODE": ""}, clear=False):
            self.assertFalse(verify_cpx_postback_signature("tx-1", "b6b10a51094f564bd112376e1bbcbf3a"))

    @unittest.skipUnless(Flask is not None, "Flask is required for route coverage")
    def test_api_uses_verified_wallet_not_browser_selected_user(self):
        app = Flask(__name__)
        register_earn_routes(
            app, self.store,
            lambda proof: (proof.get("signature") == "verified", proof.get("wallet", ""), "bad_proof"),
        )
        client = app.test_client()
        denied = client.post("/api/earn/authenticate", json={"wallet": self.user["wallet_address"]})
        self.assertEqual(denied.status_code, 403)
        authenticated = client.post("/api/earn/authenticate", json={
            "wallet": self.user["wallet_address"], "signature": "verified", "nonce": "one", "issued_at": 1,
        })
        self.assertEqual(authenticated.status_code, 200)
        token = authenticated.get_json()["access_token"]
        me = client.get("/api/earn/me?earn_user_id=attacker-selected", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.get_json()["earn_user_id"], self.user["earn_user_id"])
        callback = client.post("/api/earn/cpx/postback", json={"trans_id": "pretend-credit"})
        self.assertEqual(callback.status_code, 503)


if __name__ == "__main__":
    unittest.main()
