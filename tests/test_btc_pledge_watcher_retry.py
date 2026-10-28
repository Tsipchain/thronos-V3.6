"""Regression tests for durable BTC pledge retry handling."""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import btc_pledge_watcher as watcher


class BtcPledgeWatcherRetryTests(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.mkdtemp(prefix="btc_pledge_retry_")
        self.paths = {
            "PROCESSED_TXS_FILE": watcher.PROCESSED_TXS_FILE,
            "UNRESOLVED_TXS_FILE": getattr(watcher, "UNRESOLVED_TXS_FILE", None),
            "USER_REGISTRY_FILE": watcher.USER_REGISTRY_FILE,
            "PLEDGE_CHAIN_FILE": watcher.PLEDGE_CHAIN_FILE,
        }
        watcher.PROCESSED_TXS_FILE = os.path.join(self.data_dir, "btc_pledge_processed.json")
        watcher.UNRESOLVED_TXS_FILE = os.path.join(self.data_dir, "btc_pledge_unresolved.json")
        watcher.USER_REGISTRY_FILE = os.path.join(self.data_dir, "btc_user_registry.json")
        watcher.PLEDGE_CHAIN_FILE = os.path.join(self.data_dir, "pledge_chain.json")
        self.tx = {
            "txid": "btc-tx-001",
            "address": "bc1qsource",
            "to": "bc1qvault",
            "amount": 0.002,
            "confirmations": 2,
            "timestamp": 1760000000,
        }
        with open(watcher.PROCESSED_TXS_FILE, "w") as handle:
            json.dump([], handle)

    def tearDown(self):
        watcher.PROCESSED_TXS_FILE = self.paths["PROCESSED_TXS_FILE"]
        watcher.UNRESOLVED_TXS_FILE = self.paths["UNRESOLVED_TXS_FILE"] or os.path.join(self.data_dir, "btc_pledge_unresolved.json")
        watcher.USER_REGISTRY_FILE = self.paths["USER_REGISTRY_FILE"]
        watcher.PLEDGE_CHAIN_FILE = self.paths["PLEDGE_CHAIN_FILE"]
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def _run_cycle(self, txs, resolver, create):
        with patch.object(watcher, "sync_pledge_chain_from_fallback"):
            with patch.object(watcher, "get_vault_transactions", return_value=txs):
                with patch.object(watcher, "resolve_user_from_tx", side_effect=resolver):
                    with patch.object(watcher, "create_pledge_transaction", side_effect=create):
                        watcher.watch_btc_pledges()

    def _read_json(self, path, default):
        try:
            with open(path) as handle:
                return json.load(handle)
        except FileNotFoundError:
            return default

    def test_unresolved_user_is_not_marked_processed(self):
        self._run_cycle([self.tx], lambda _tx: None, lambda *_: True)

        processed = self._read_json(watcher.PROCESSED_TXS_FILE, [])
        unresolved = self._read_json(watcher.UNRESOLVED_TXS_FILE, [])

        self.assertNotIn(self.tx["txid"], processed)
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["last_reason"], "user_unresolved")
        self.assertEqual(unresolved[0]["transaction"]["txid"], self.tx["txid"])

    def test_unresolved_deposit_retries_after_it_leaves_recent_api_results(self):
        self._run_cycle([self.tx], lambda _tx: None, lambda *_: True)
        user = {"thr_address": "THRTEST", "btc_address": self.tx["address"]}

        # No fresh API result this cycle: the stored transaction is still retried.
        create = unittest.mock.Mock(return_value=True)
        self._run_cycle([], lambda _tx: user, create)

        processed = self._read_json(watcher.PROCESSED_TXS_FILE, [])
        unresolved = self._read_json(watcher.UNRESOLVED_TXS_FILE, [])
        self.assertIn(self.tx["txid"], processed)
        self.assertEqual(unresolved, [])
        create.assert_called_once_with(user, self.tx["amount"], self.tx["txid"])

    def test_master_failure_is_persisted_and_retried(self):
        user = {"thr_address": "THRTEST", "btc_address": self.tx["address"]}
        self._run_cycle([self.tx], lambda _tx: user, lambda *_: False)

        unresolved = self._read_json(watcher.UNRESOLVED_TXS_FILE, [])
        processed = self._read_json(watcher.PROCESSED_TXS_FILE, [])
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["last_reason"], "master_node_failed")
        self.assertNotIn(self.tx["txid"], processed)

        self._run_cycle([], lambda _tx: user, lambda *_: True)
        processed = self._read_json(watcher.PROCESSED_TXS_FILE, [])
        unresolved = self._read_json(watcher.UNRESOLVED_TXS_FILE, [])
        self.assertIn(self.tx["txid"], processed)
        self.assertEqual(unresolved, [])

    def test_unconfirmed_transaction_is_not_credited_or_marked_processed(self):
        unconfirmed = {**self.tx, "confirmations": 0}
        create = unittest.mock.Mock(return_value=True)
        self._run_cycle([unconfirmed], lambda _tx: {"thr_address": "THRTEST"}, create)
        self.assertEqual(self._read_json(watcher.PROCESSED_TXS_FILE, []), [])
        self.assertEqual(self._read_json(watcher.UNRESOLVED_TXS_FILE, []), [])
        create.assert_not_called()

    def test_unconfirmed_transaction_is_credited_once_it_confirms(self):
        user = {"thr_address": "THRTEST", "btc_address": self.tx["address"]}
        self._run_cycle([{**self.tx, "confirmations": 0}], lambda _tx: user, lambda *_: True)
        create = unittest.mock.Mock(return_value=True)
        self._run_cycle([self.tx], lambda _tx: user, create)
        self.assertIn(self.tx["txid"], self._read_json(watcher.PROCESSED_TXS_FILE, []))
        create.assert_called_once_with(user, self.tx["amount"], self.tx["txid"])

    def test_duplicate_observations_for_same_tx_are_processed_once_per_cycle(self):
        user = {"thr_address": "THRTEST", "btc_address": self.tx["address"]}
        create = unittest.mock.Mock(return_value=True)
        self._run_cycle([self.tx, dict(self.tx)], lambda _tx: user, create)
        create.assert_called_once_with(user, self.tx["amount"], self.tx["txid"])
        self.assertEqual(self._read_json(watcher.PROCESSED_TXS_FILE, []).count(self.tx["txid"]), 1)

    def test_corrupt_processed_state_fails_closed(self):
        with open(watcher.PROCESSED_TXS_FILE, "w") as handle:
            handle.write("{bad-json")
        fresh = unittest.mock.Mock(return_value=[self.tx])
        with patch.object(watcher, "sync_pledge_chain_from_fallback"):
            with patch.object(watcher, "get_vault_transactions", fresh):
                watcher.watch_btc_pledges()
        fresh.assert_not_called()

    def test_corrupt_unresolved_state_fails_closed_without_overwriting_it(self):
        with open(watcher.UNRESOLVED_TXS_FILE, "w") as handle:
            handle.write("{bad-json")
        fresh = unittest.mock.Mock(return_value=[self.tx])
        with patch.object(watcher, "sync_pledge_chain_from_fallback"):
            with patch.object(watcher, "get_vault_transactions", fresh):
                watcher.watch_btc_pledges()
        fresh.assert_not_called()
        with open(watcher.UNRESOLVED_TXS_FILE) as handle:
            self.assertEqual(handle.read(), "{bad-json")


if __name__ == "__main__":
    unittest.main()
