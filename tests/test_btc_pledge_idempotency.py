"""Transactional BTC pledge idempotency journal regression tests."""
import json
import sqlite3
import unittest

from btc_pledge_idempotency import (
    credit_btc_pledge_once,
    record_existing_btc_pledge_without_credit,
)


class BtcPledgeIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""
            CREATE TABLE balances (
                ledger_type TEXT NOT NULL,
                address TEXT NOT NULL,
                balance REAL NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (ledger_type, address)
            )
        """)
        self.conn.execute(
            "INSERT INTO balances (ledger_type, address, balance, updated_at) VALUES (?, ?, ?, ?)",
            ("thr", "THR_A", 100.0, 1),
        )
        self.conn.commit()
        self.tx = {
            "type": "btc_pledge",
            "tx_id": "BTC_PLEDGE-test-001",
            "btc_txid": "a" * 64,
            "btc_address": "bc1qfunding",
            "thr_address": "THR_A",
            "btc_amount": 0.001,
            "thr_amount": 25.0,
            "status": "confirmed",
        }
        self.kwargs = dict(
            btc_txid=self.tx["btc_txid"],
            btc_address=self.tx["btc_address"],
            thr_address=self.tx["thr_address"],
            btc_amount=self.tx["btc_amount"],
            thr_amount=self.tx["thr_amount"],
            tx_record=self.tx,
            now_ts=123,
        )

    def tearDown(self):
        self.conn.close()

    def test_same_txid_is_credited_only_once(self):
        first = credit_btc_pledge_once(self.conn, **self.kwargs)
        second = credit_btc_pledge_once(self.conn, **self.kwargs)

        self.assertEqual(first["status"], "created")
        self.assertEqual(second["status"], "duplicate")
        self.assertEqual(second["tx_record"]["tx_id"], first["tx_record"]["tx_id"])
        self.assertEqual(second["new_balance"], 125.0)
        self.assertEqual(second["ledger"]["THR_A"], 125.0)
        count = self.conn.execute(
            "SELECT COUNT(*) FROM btc_pledge_idempotency WHERE btc_txid = ?",
            (self.tx["btc_txid"],),
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_same_txid_with_changed_payload_is_rejected(self):
        first = credit_btc_pledge_once(self.conn, **self.kwargs)
        changed = {**self.kwargs, "thr_amount": 999.0}
        second = credit_btc_pledge_once(self.conn, **changed)

        self.assertEqual(first["status"], "created")
        self.assertEqual(second["status"], "conflict")
        self.assertEqual(second["reason"], "btc_txid_payload_conflict")
        balance = self.conn.execute(
            "SELECT balance FROM balances WHERE ledger_type='thr' AND address='THR_A'"
        ).fetchone()[0]
        self.assertEqual(balance, 125.0)

    def test_different_txids_credit_independently(self):
        first = credit_btc_pledge_once(self.conn, **self.kwargs)
        second_tx = {**self.tx, "tx_id": "BTC_PLEDGE-test-002", "btc_txid": "b" * 64}
        second_kwargs = {**self.kwargs, "btc_txid": "b" * 64, "tx_record": second_tx}
        second = credit_btc_pledge_once(self.conn, **second_kwargs)

        self.assertEqual(first["status"], "created")
        self.assertEqual(second["status"], "created")
        self.assertEqual(second["new_balance"], 150.0)

    def test_existing_legacy_chain_entry_is_journaled_without_second_credit(self):
        # Simulate legacy data where the chain/THR credit already exists but there
        # is no idempotency journal yet.
        legacy = credit_btc_pledge_once(self.conn, **self.kwargs)
        self.assertEqual(legacy["new_balance"], 125.0)

        # Remove only the journal record to model an older deployment. Keep the
        # already credited balance and existing chain event.
        self.conn.execute("DELETE FROM btc_pledge_idempotency WHERE btc_txid = ?", (self.tx["btc_txid"],))
        self.conn.commit()
        adopted = record_existing_btc_pledge_without_credit(self.conn, **self.kwargs)

        self.assertEqual(adopted["status"], "duplicate")
        self.assertEqual(adopted["new_balance"], 125.0)
        balance = self.conn.execute(
            "SELECT balance FROM balances WHERE ledger_type='thr' AND address='THR_A'"
        ).fetchone()[0]
        self.assertEqual(balance, 125.0)

    def test_exact_duplicate_keeps_original_transaction_record(self):
        original = {**self.tx, "tx_id": "BTC_PLEDGE-original"}
        first_kwargs = {**self.kwargs, "tx_record": original}
        credit_btc_pledge_once(self.conn, **first_kwargs)
        retry_record = {**self.tx, "tx_id": "BTC_PLEDGE-retry"}
        second_kwargs = {**self.kwargs, "tx_record": retry_record}

        second = credit_btc_pledge_once(self.conn, **second_kwargs)
        self.assertEqual(second["status"], "duplicate")
        self.assertEqual(second["tx_record"]["tx_id"], "BTC_PLEDGE-original")
        self.assertEqual(second["new_balance"], 125.0)


if __name__ == "__main__":
    unittest.main()
