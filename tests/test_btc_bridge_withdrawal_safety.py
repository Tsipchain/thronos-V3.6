"""Safety tests: simulated BTC sends must never be recorded as completed withdrawals."""

import tempfile
import unittest
from pathlib import Path

from btc_bridge_withdrawal import (
    BTCBridgeWithdrawal,
    WithdrawalRequest,
)


class BtcWithdrawalSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="btc_withdrawal_safety_")
        self.bridge = BTCBridgeWithdrawal(data_dir=self.tmp.name)
        self.request_id = "test-withdrawal-1"
        self.request = WithdrawalRequest(
            request_id=self.request_id,
            wallet_address="THR_TEST_ADDRESS",
            btc_address="bc1qexampledestination",
            thr_amount=100.0,
            btc_amount=0.001,
            status="pending",
            created_at="2026-10-28T00:00:00Z",
        )
        self.bridge.withdrawals[self.request_id] = self.request
        self.bridge._save_withdrawals()

    def tearDown(self):
        self.tmp.cleanup()

    def test_processing_is_blocked_without_live_backend(self):
        ok, message = self.bridge.process_withdrawal(self.request_id)

        self.assertFalse(ok)
        self.assertIn("not implemented", message.lower())
        self.assertIn("no funds were moved", message.lower())
        status = self.bridge.get_withdrawal_status(self.request_id)
        self.assertEqual(status["status"], "pending")
        self.assertIsNone(status["btc_txid"])
        self.assertIsNone(status["burn_txid"])
        self.assertEqual(self.bridge.stats.total_btc_withdrawn, 0.0)
        self.assertEqual(self.bridge.stats.total_thr_burned, 0.0)
        self.assertFalse((Path(self.tmp.name) / "thr_burn_ledger.jsonl").exists())

    def test_burn_adapter_does_not_generate_fake_txid(self):
        with self.assertRaises(NotImplementedError):
            self.bridge._burn_thr("THR_TEST_ADDRESS", 100.0)

    def test_btc_sender_does_not_generate_fake_txid(self):
        with self.assertRaises(NotImplementedError):
            self.bridge._send_btc("bc1qexampledestination", 0.001)

    def test_missing_request_is_handled(self):
        ok, message = self.bridge.process_withdrawal("missing")
        self.assertFalse(ok)
        self.assertEqual(message, "Withdrawal request not found")


if __name__ == "__main__":
    unittest.main()
