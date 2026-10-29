"""Safety tests for the disabled-by-default BitcoTasks Earn adapter."""
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.earn_account import (
    EarnAccountStore,
    verify_bitcotasks_postback_signature,
)


class TestBitcoTasksEarnAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = EarnAccountStore(
            str(Path(self.tmp.name) / "earn.db"), "unit-test-identity-key",
        )
        self.user = self.store.register("bitcotasks@example.com", "password123")
        self.provider_id = self.store.provider_user_id(
            self.user["earn_user_id"], "bitcotasks",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _record(self, trans_id="bt-transaction-1", status=1):
        return self.store.record_bitcotasks_receipt(
            trans_id=trans_id,
            provider_user_id=self.provider_id,
            status=status,
            reward_thc="0.100000",
            payout_usd="0.01",
            offer_name="Test offer",
            offer_type="offer",
            payload={"transId": trans_id, "status": str(status)},
        )

    def test_provider_identity_is_short_stable_and_opaque(self):
        again = self.store.provider_user_id(self.user["earn_user_id"], "bitcotasks")
        self.assertEqual(self.provider_id, again)
        self.assertLessEqual(len(self.provider_id), 32)
        self.assertTrue(self.provider_id.startswith("bt_"))
        self.assertNotIn("@", self.provider_id)

    def test_credit_is_pending_and_idempotent(self):
        receipt, created = self._record()
        self.assertTrue(created)
        self.assertEqual(receipt["status"], 1)
        self.assertEqual(self.store.thc_balance(self.user["earn_user_id"])["pending"], "0.100000")
        _, created_again = self._record()
        self.assertFalse(created_again)
        self.assertEqual(len(self.store.thc_history(self.user["earn_user_id"])), 1)

    def test_chargeback_reverses_the_original_pending_credit(self):
        first, _ = self._record()
        reversed_receipt, changed = self._record(status=2)
        self.assertTrue(changed)
        self.assertEqual(reversed_receipt["status"], 2)
        history = self.store.thc_history(self.user["earn_user_id"])
        self.assertEqual(history[0]["entry_id"], first["thc_entry_id"])
        self.assertEqual(history[0]["state"], "reversed")

    def test_bitcotasks_signature_matches_documented_raw_reward_formula(self):
        with patch.dict(os.environ, {"BITCOTASKS_SECRET_KEY": "test-secret"}, clear=False):
            raw_reward = "0.10"
            signature = hashlib.md5(
                f"{self.provider_id}tx-9{raw_reward}test-secret".encode(),
            ).hexdigest()
            self.assertTrue(verify_bitcotasks_postback_signature(
                self.provider_id, "tx-9", raw_reward, signature,
            ))
            self.assertFalse(verify_bitcotasks_postback_signature(
                self.provider_id, "tx-9", raw_reward, "forged",
            ))

    def test_unknown_provider_identity_cannot_credit_any_account(self):
        with self.assertRaisesRegex(ValueError, "unknown_provider_user"):
            self.store.record_bitcotasks_receipt(
                trans_id="unknown-user", provider_user_id="bt_not_a_real_identity",
                status=1, reward_thc="1", payload={},
            )


if __name__ == "__main__":
    unittest.main()
