"""
Comprehensive tests for CPX Rewards integration.

Tests cover:
  - Pre-wallet account registration and authentication
  - User isolation (accounts cannot access each other's data)
  - RPT ledger credit/debit/balance
  - CPX secure_hash generation (server-side, MD5 spec)
  - Postback signature verification
  - Idempotent callback processing (duplicates, reversals)
  - Currency factor handling (no double-conversion)
  - Concurrent callback processing (file locking)
  - Account-wallet linking
  - Transaction history

Run:
  python3 -m pytest tests/test_cpx_rewards.py -v
  python3 -m unittest tests.test_cpx_rewards -v
"""

import hashlib
import hmac
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from services.cpx_rewards import (
    init_cpx_rewards,
    register_account,
    authenticate_account,
    link_wallet,
    get_rpt_balance,
    credit_rpt,
    debit_rpt,
    generate_cpx_secure_hash,
    build_offerwall_url,
    verify_cpx_signature,
    process_cpx_callback,
    get_account_by_ext_user_id,
    get_transaction_history,
    _load_json,
    _save_json,
    _hash_email,
)
import services.cpx_rewards as cpx_mod


class CPXTestBase(unittest.TestCase):
    """Base class that sets up a temp DATA_DIR for each test."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="cpx_test_")
        # Set test env vars
        os.environ["CPX_APP_ID"] = "37719"
        os.environ["CPX_APP_SECURE_HASH"] = "test_secret_for_unit_tests"
        init_cpx_rewards(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
        os.environ.pop("CPX_APP_ID", None)
        os.environ.pop("CPX_APP_SECURE_HASH", None)


# ---------------------------------------------------------------------------
# Account registration tests
# ---------------------------------------------------------------------------

class TestAccountRegistration(CPXTestBase):

    def test_register_success(self):
        result = register_account("user@example.com", "securePass123")
        self.assertTrue(result["ok"])
        self.assertTrue(result["ext_user_id"].startswith("CPX"))
        self.assertEqual(len(result["ext_user_id"]), 35)  # "CPX" + 32 hex

    def test_register_duplicate_email(self):
        register_account("user@example.com", "securePass123")
        result = register_account("user@example.com", "differentPass")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "account_exists")

    def test_register_case_insensitive_email(self):
        register_account("User@Example.COM", "securePass123")
        result = register_account("user@example.com", "differentPass")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "account_exists")

    def test_register_invalid_email(self):
        result = register_account("notanemail", "securePass123")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "invalid_email")

    def test_register_short_password(self):
        result = register_account("user@example.com", "short")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "password_too_short")

    def test_register_empty_fields(self):
        result = register_account("", "securePass123")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "missing_fields")

    def test_register_rate_limit(self):
        ip = "192.168.1.100"
        for i in range(5):
            register_account(f"user{i}@example.com", "securePass123", ip)
        result = register_account("user99@example.com", "securePass123", ip)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "rate_limited")

    def test_register_initializes_rpt_balance(self):
        result = register_account("user@example.com", "securePass123")
        balance = get_rpt_balance(result["ext_user_id"])
        self.assertTrue(balance["ok"])
        self.assertEqual(balance["balance"], 0)
        self.assertEqual(balance["total_earned"], 0)


# ---------------------------------------------------------------------------
# Authentication tests
# ---------------------------------------------------------------------------

class TestAuthentication(CPXTestBase):

    def setUp(self):
        super().setUp()
        self.reg = register_account("auth@example.com", "myPassword99")

    def test_login_success(self):
        result = authenticate_account("auth@example.com", "myPassword99")
        self.assertTrue(result["ok"])
        self.assertEqual(result["ext_user_id"], self.reg["ext_user_id"])

    def test_login_wrong_password(self):
        result = authenticate_account("auth@example.com", "wrongPassword")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "invalid_credentials")

    def test_login_nonexistent_email(self):
        result = authenticate_account("nobody@example.com", "anyPass123")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "invalid_credentials")

    def test_login_case_insensitive(self):
        result = authenticate_account("Auth@Example.COM", "myPassword99")
        self.assertTrue(result["ok"])


# ---------------------------------------------------------------------------
# User isolation
# ---------------------------------------------------------------------------

class TestUserIsolation(CPXTestBase):

    def setUp(self):
        super().setUp()
        self.user_a = register_account("alice@example.com", "alicePass99")
        self.user_b = register_account("bob@example.com", "bobPass9999")

    def test_different_ext_user_ids(self):
        self.assertNotEqual(self.user_a["ext_user_id"], self.user_b["ext_user_id"])

    def test_balance_isolation(self):
        credit_rpt(self.user_a["ext_user_id"], 500)
        balance_a = get_rpt_balance(self.user_a["ext_user_id"])
        balance_b = get_rpt_balance(self.user_b["ext_user_id"])
        self.assertEqual(balance_a["balance"], 500)
        self.assertEqual(balance_b["balance"], 0)

    def test_history_isolation(self):
        process_cpx_callback("tx_a1", self.user_a["ext_user_id"], 100, 1)
        process_cpx_callback("tx_b1", self.user_b["ext_user_id"], 200, 1)
        hist_a = get_transaction_history(self.user_a["ext_user_id"])
        hist_b = get_transaction_history(self.user_b["ext_user_id"])
        self.assertEqual(len(hist_a), 1)
        self.assertEqual(len(hist_b), 1)
        self.assertEqual(hist_a[0]["amount"], 100)
        self.assertEqual(hist_b[0]["amount"], 200)


# ---------------------------------------------------------------------------
# RPT Ledger
# ---------------------------------------------------------------------------

class TestRPTLedger(CPXTestBase):

    def setUp(self):
        super().setUp()
        self.reg = register_account("ledger@example.com", "ledgerPass9")
        self.uid = self.reg["ext_user_id"]

    def test_credit_increases_balance(self):
        credit_rpt(self.uid, 100)
        balance = get_rpt_balance(self.uid)
        self.assertEqual(balance["balance"], 100)
        self.assertEqual(balance["total_earned"], 100)

    def test_multiple_credits_accumulate(self):
        credit_rpt(self.uid, 100)
        credit_rpt(self.uid, 250)
        credit_rpt(self.uid, 50)
        balance = get_rpt_balance(self.uid)
        self.assertEqual(balance["balance"], 400)
        self.assertEqual(balance["total_earned"], 400)

    def test_debit_decreases_balance(self):
        credit_rpt(self.uid, 500)
        debit_rpt(self.uid, 200)
        balance = get_rpt_balance(self.uid)
        self.assertEqual(balance["balance"], 300)

    def test_debit_cannot_go_negative(self):
        credit_rpt(self.uid, 100)
        debit_rpt(self.uid, 999)
        balance = get_rpt_balance(self.uid)
        self.assertEqual(balance["balance"], 0)

    def test_credit_zero_rejected(self):
        result = credit_rpt(self.uid, 0)
        self.assertFalse(result)

    def test_credit_negative_rejected(self):
        result = credit_rpt(self.uid, -50)
        self.assertFalse(result)

    def test_debit_nonexistent_user(self):
        result = debit_rpt("CPXnonexistent", 100)
        self.assertFalse(result)

    def test_balance_unknown_user_returns_zero(self):
        balance = get_rpt_balance("CPXunknown")
        self.assertEqual(balance["balance"], 0)


# ---------------------------------------------------------------------------
# Secure hash generation
# ---------------------------------------------------------------------------

class TestSecureHashGeneration(CPXTestBase):

    def test_hash_matches_md5_spec(self):
        ext_user_id = "CPXabc123"
        expected = hashlib.md5(
            f"{ext_user_id}-test_secret_for_unit_tests".encode()
        ).hexdigest()
        result = generate_cpx_secure_hash(ext_user_id)
        self.assertEqual(result, expected)

    def test_hash_different_for_different_users(self):
        h1 = generate_cpx_secure_hash("CPXuser1")
        h2 = generate_cpx_secure_hash("CPXuser2")
        self.assertNotEqual(h1, h2)

    def test_hash_deterministic(self):
        h1 = generate_cpx_secure_hash("CPXsameuser")
        h2 = generate_cpx_secure_hash("CPXsameuser")
        self.assertEqual(h1, h2)

    def test_hash_raises_without_secret(self):
        old = cpx_mod.CPX_APP_SECURE_HASH
        cpx_mod.CPX_APP_SECURE_HASH = ""
        try:
            with self.assertRaises(ValueError):
                generate_cpx_secure_hash("CPXtest")
        finally:
            cpx_mod.CPX_APP_SECURE_HASH = old

    def test_offerwall_url_contains_params(self):
        url = build_offerwall_url("CPXtestuser")
        self.assertIn("app_id=37719", url)
        self.assertIn("ext_user_id=CPXtestuser", url)
        self.assertIn("secure_hash=", url)
        self.assertTrue(url.startswith("https://offers.cpx-research.com/"))


# ---------------------------------------------------------------------------
# Postback signature verification
# ---------------------------------------------------------------------------

class TestSignatureVerification(CPXTestBase):

    def _make_valid_hash(self, trans_id):
        return hashlib.md5(
            f"{trans_id}-test_secret_for_unit_tests".encode()
        ).hexdigest()

    def test_valid_signature_passes(self):
        self.assertTrue(verify_cpx_signature("tx123", self._make_valid_hash("tx123")))

    def test_invalid_signature_fails(self):
        self.assertFalse(verify_cpx_signature("tx123", "deadbeef" * 4))

    def test_empty_trans_id_fails(self):
        self.assertFalse(verify_cpx_signature("", self._make_valid_hash("")))

    def test_empty_hash_fails(self):
        self.assertFalse(verify_cpx_signature("tx123", ""))

    def test_case_insensitive_hash(self):
        h = self._make_valid_hash("tx456").upper()
        self.assertTrue(verify_cpx_signature("tx456", h))

    def test_wrong_secret_fails(self):
        wrong_hash = hashlib.md5(b"tx789-wrong_secret").hexdigest()
        self.assertFalse(verify_cpx_signature("tx789", wrong_hash))


# ---------------------------------------------------------------------------
# Callback processing (idempotency, reversals, currency factor)
# ---------------------------------------------------------------------------

class TestCallbackProcessing(CPXTestBase):

    def setUp(self):
        super().setUp()
        self.reg = register_account("callback@example.com", "callbackPass1")
        self.uid = self.reg["ext_user_id"]

    def test_credit_callback(self):
        result = process_cpx_callback("tx001", self.uid, 340.0, 1)
        self.assertTrue(result["ok"])
        balance = get_rpt_balance(self.uid)
        self.assertEqual(balance["balance"], 340)

    def test_duplicate_callback_idempotent(self):
        process_cpx_callback("tx002", self.uid, 500.0, 1)
        result = process_cpx_callback("tx002", self.uid, 500.0, 1)
        self.assertTrue(result["ok"])
        self.assertTrue(result.get("duplicate"))
        balance = get_rpt_balance(self.uid)
        self.assertEqual(balance["balance"], 500)

    def test_reversal_callback(self):
        process_cpx_callback("tx003", self.uid, 200.0, 1)
        result = process_cpx_callback("tx003", self.uid, 200.0, 2)
        self.assertTrue(result["ok"])
        self.assertTrue(result.get("reversed"))
        balance = get_rpt_balance(self.uid)
        self.assertEqual(balance["balance"], 0)

    def test_reversal_without_prior_credit(self):
        result = process_cpx_callback("tx004", self.uid, 100.0, 2)
        self.assertTrue(result["ok"])
        balance = get_rpt_balance(self.uid)
        self.assertEqual(balance["balance"], 0)

    def test_unknown_user_rejected(self):
        result = process_cpx_callback("tx005", "CPXnonexistent", 100.0, 1)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "unknown_user")

    def test_negative_amount_rejected(self):
        result = process_cpx_callback("tx006", self.uid, -50.0, 1)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "negative_amount")

    def test_amount_local_is_final_no_double_conversion(self):
        """
        With Currency Factor 680, CPX sends amount_local = 340 for a $0.50 survey.
        We store 340 RPT directly — NOT 340 * 680.
        """
        process_cpx_callback("tx007", self.uid, 340.0, 1)
        balance = get_rpt_balance(self.uid)
        self.assertEqual(balance["balance"], 340)
        # NOT 340 * 680 = 231200

    def test_amount_rounded_to_integer(self):
        process_cpx_callback("tx008", self.uid, 123.7, 1)
        balance = get_rpt_balance(self.uid)
        self.assertEqual(balance["balance"], 124)  # rounded

    def test_multiple_callbacks_accumulate(self):
        process_cpx_callback("tx009", self.uid, 100.0, 1)
        process_cpx_callback("tx010", self.uid, 200.0, 1)
        process_cpx_callback("tx011", self.uid, 50.0, 1)
        balance = get_rpt_balance(self.uid)
        self.assertEqual(balance["balance"], 350)


# ---------------------------------------------------------------------------
# Concurrent callback processing
# ---------------------------------------------------------------------------

class TestConcurrentCallbacks(CPXTestBase):

    def setUp(self):
        super().setUp()
        self.reg = register_account("concurrent@example.com", "concurrentP1")
        self.uid = self.reg["ext_user_id"]

    def test_concurrent_same_trans_id(self):
        """Only one of two concurrent callbacks for the same trans_id should credit."""
        results = []
        barrier = threading.Barrier(2, timeout=5)

        def worker():
            barrier.wait()
            r = process_cpx_callback("tx_concurrent", self.uid, 100.0, 1)
            results.append(r)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        ok_count = sum(1 for r in results if r.get("ok"))
        dup_count = sum(1 for r in results if r.get("duplicate"))
        concurrent_count = sum(1 for r in results if r.get("error") == "concurrent_processing")

        # Exactly one credit + one (duplicate or concurrent rejection)
        self.assertEqual(ok_count + concurrent_count, 2)
        balance = get_rpt_balance(self.uid)
        self.assertEqual(balance["balance"], 100)

    def test_sequential_different_trans_ids_accumulate(self):
        """Sequential callbacks with different trans_ids both credit correctly."""
        r1 = process_cpx_callback("tx_a", self.uid, 100.0, 1)
        r2 = process_cpx_callback("tx_b", self.uid, 200.0, 1)
        self.assertTrue(r1["ok"])
        self.assertTrue(r2["ok"])
        balance = get_rpt_balance(self.uid)
        self.assertEqual(balance["balance"], 300)
        txns = _load_json(cpx_mod.CPX_TRANSACTIONS_FILE, {})
        self.assertIn("tx_a", txns)
        self.assertIn("tx_b", txns)


# ---------------------------------------------------------------------------
# Wallet linking
# ---------------------------------------------------------------------------

class TestWalletLinking(CPXTestBase):

    def setUp(self):
        super().setUp()
        self.reg = register_account("linker@example.com", "linkerPass99")
        self.uid = self.reg["ext_user_id"]

    def test_link_wallet_success(self):
        result = link_wallet("linker@example.com", "linkerPass99", "THR" + "a" * 40)
        self.assertTrue(result["ok"])
        self.assertEqual(result["thr_address"], "THR" + "A" * 40)

    def test_link_wallet_wrong_password(self):
        result = link_wallet("linker@example.com", "wrongPass", "THR" + "a" * 40)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "invalid_credentials")

    def test_link_wallet_invalid_address(self):
        result = link_wallet("linker@example.com", "linkerPass99", "INVALID")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "invalid_thr_address")

    def test_account_shows_linked_wallet(self):
        link_wallet("linker@example.com", "linkerPass99", "THR" + "b" * 40)
        account = get_account_by_ext_user_id(self.uid)
        self.assertTrue(account["wallet_linked"])
        self.assertEqual(account["thr_address"], "THR" + "B" * 40)


# ---------------------------------------------------------------------------
# Transaction history
# ---------------------------------------------------------------------------

class TestTransactionHistory(CPXTestBase):

    def setUp(self):
        super().setUp()
        self.reg = register_account("history@example.com", "historyPass1")
        self.uid = self.reg["ext_user_id"]

    def test_empty_history(self):
        hist = get_transaction_history(self.uid)
        self.assertEqual(len(hist), 0)

    def test_history_after_credits(self):
        process_cpx_callback("tx_h1", self.uid, 100.0, 1)
        process_cpx_callback("tx_h2", self.uid, 200.0, 1)
        hist = get_transaction_history(self.uid)
        self.assertEqual(len(hist), 2)

    def test_history_includes_reversals(self):
        process_cpx_callback("tx_h3", self.uid, 300.0, 1)
        process_cpx_callback("tx_h3", self.uid, 300.0, 2)
        hist = get_transaction_history(self.uid)
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["status"], 2)

    def test_history_limit(self):
        for i in range(10):
            process_cpx_callback(f"tx_lim_{i}", self.uid, 10.0, 1)
        hist = get_transaction_history(self.uid, limit=5)
        self.assertEqual(len(hist), 5)

    def test_history_sorted_newest_first(self):
        process_cpx_callback("tx_old", self.uid, 10.0, 1)
        time.sleep(0.01)
        process_cpx_callback("tx_new", self.uid, 20.0, 1)
        hist = get_transaction_history(self.uid)
        self.assertEqual(hist[0]["trans_id"], "tx_new")
        self.assertEqual(hist[1]["trans_id"], "tx_old")


# ---------------------------------------------------------------------------
# Email hashing
# ---------------------------------------------------------------------------

class TestEmailHashing(CPXTestBase):

    def test_email_normalized_lowercase(self):
        h1 = _hash_email("USER@Example.COM")
        h2 = _hash_email("user@example.com")
        self.assertEqual(h1, h2)

    def test_email_stripped(self):
        h1 = _hash_email("  user@example.com  ")
        h2 = _hash_email("user@example.com")
        self.assertEqual(h1, h2)

    def test_hash_is_sha256(self):
        expected = hashlib.sha256(b"user@example.com").hexdigest()
        self.assertEqual(_hash_email("user@example.com"), expected)


# ---------------------------------------------------------------------------
# JSON persistence
# ---------------------------------------------------------------------------

class TestJSONPersistence(CPXTestBase):

    def test_accounts_survive_reload(self):
        register_account("persist@example.com", "persistPass1")
        accounts = _load_json(cpx_mod.CPX_ACCOUNTS_FILE, {})
        email_hash = _hash_email("persist@example.com")
        self.assertIn(email_hash, accounts)

    def test_ledger_survives_reload(self):
        reg = register_account("persist2@example.com", "persistPass2")
        credit_rpt(reg["ext_user_id"], 999)
        ledger = _load_json(cpx_mod.RPT_LEDGER_FILE, {})
        self.assertEqual(ledger[reg["ext_user_id"]]["balance"], 999)

    def test_transactions_survive_reload(self):
        reg = register_account("persist3@example.com", "persistPass3")
        process_cpx_callback("tx_persist", reg["ext_user_id"], 100.0, 1)
        txns = _load_json(cpx_mod.CPX_TRANSACTIONS_FILE, {})
        self.assertIn("tx_persist", txns)


# ---------------------------------------------------------------------------
# Account lookup
# ---------------------------------------------------------------------------

class TestAccountLookup(CPXTestBase):

    def test_lookup_existing_account(self):
        reg = register_account("lookup@example.com", "lookupPass99")
        account = get_account_by_ext_user_id(reg["ext_user_id"])
        self.assertIsNotNone(account)
        self.assertEqual(account["ext_user_id"], reg["ext_user_id"])

    def test_lookup_nonexistent_returns_none(self):
        account = get_account_by_ext_user_id("CPXdoesnotexist")
        self.assertIsNone(account)


if __name__ == "__main__":
    unittest.main()
