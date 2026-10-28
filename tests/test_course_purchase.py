"""Tests for services/course_purchase.py — fiat course purchase store."""
from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.course_purchase import (
    CoursePurchaseError,
    CoursePurchaseStore,
)


def _tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return path


def _hash(payload: str = "{}") -> str:
    return hashlib.sha256(payload.encode()).hexdigest()


class TestCreateCheckout(unittest.TestCase):
    def setUp(self):
        self.db = _tmp_db()
        self.store = CoursePurchaseStore(self.db)

    def tearDown(self):
        os.unlink(self.db)

    def test_basic_checkout(self):
        r = self.store.create_checkout(
            earn_user_id="u1",
            course_id="c1",
            price_usd="100.00",
            teacher_wallet="thr1abc",
        )
        self.assertEqual(r["state"], "checkout_pending")
        self.assertTrue(r["purchase_id"].startswith("cp_"))
        self.assertEqual(r["price_usd"], "100.00")
        # teacher share = 70.00, stripe fee = 3.20, net = 26.80
        self.assertEqual(r["teacher_share_usd"], "70.00")
        # THC reward = min(5.00, 0.25 * 26.80) = min(5.00, 6.70) = 5.00
        self.assertEqual(r["thc_reward_usd"], "5.00")

    def test_invalid_price_rejected(self):
        with self.assertRaises(CoursePurchaseError):
            self.store.create_checkout(
                earn_user_id="u1", course_id="c1", price_usd="-5",
                teacher_wallet="thr1",
            )

    def test_missing_teacher_wallet_rejected(self):
        with self.assertRaises(CoursePurchaseError):
            self.store.create_checkout(
                earn_user_id="u1", course_id="c1", price_usd="10",
                teacher_wallet="",
            )

    def test_duplicate_returns_existing_pending(self):
        r1 = self.store.create_checkout(
            earn_user_id="u1", course_id="c1", price_usd="50",
            teacher_wallet="thr1",
        )
        r2 = self.store.create_checkout(
            earn_user_id="u1", course_id="c1", price_usd="50",
            teacher_wallet="thr1",
        )
        self.assertEqual(r1["purchase_id"], r2["purchase_id"])

    def test_already_enrolled_rejected(self):
        r = self.store.create_checkout(
            earn_user_id="u1", course_id="c1", price_usd="50",
            teacher_wallet="thr1",
        )
        # Simulate webhook completing
        self.store.handle_checkout_completed(
            event_id="evt_1",
            checkout_session_id="cs_1",
            payment_intent="pi_1",
            amount_total_cents=5000,
            metadata={"purchase_id": r["purchase_id"], "type": "course_purchase"},
            payload_hash=_hash(),
        )
        with self.assertRaises(CoursePurchaseError) as ctx:
            self.store.create_checkout(
                earn_user_id="u1", course_id="c1", price_usd="50",
                teacher_wallet="thr1",
            )
        self.assertIn("already_enrolled", str(ctx.exception))

    def test_repurchase_after_refund(self):
        r = self.store.create_checkout(
            earn_user_id="u1", course_id="c1", price_usd="50",
            teacher_wallet="thr1",
        )
        # Pay then refund
        self.store.handle_checkout_completed(
            event_id="evt_1", checkout_session_id="cs_1",
            payment_intent="pi_1", amount_total_cents=5000,
            metadata={"purchase_id": r["purchase_id"], "type": "course_purchase"},
            payload_hash=_hash(),
        )
        self.store.handle_refund(
            event_id="evt_2", payment_intent="pi_1", payload_hash=_hash(),
        )
        # Should be able to purchase again
        r2 = self.store.create_checkout(
            earn_user_id="u1", course_id="c1", price_usd="50",
            teacher_wallet="thr1",
        )
        self.assertNotEqual(r2["purchase_id"], r["purchase_id"])
        self.assertEqual(r2["state"], "checkout_pending")

    def test_low_price_thc_cap(self):
        # $5 course: stripe fee = 0.45, teacher share = 3.50, net = 1.05
        # thc = min(5% * 5 = 0.25, 25% * 1.05 = 0.26) = 0.25
        r = self.store.create_checkout(
            earn_user_id="u1", course_id="c1", price_usd="5.00",
            teacher_wallet="thr1",
        )
        self.assertEqual(r["thc_reward_usd"], "0.25")


class TestCheckoutCompleted(unittest.TestCase):
    def setUp(self):
        self.db = _tmp_db()
        self.store = CoursePurchaseStore(self.db)
        self.purchase = self.store.create_checkout(
            earn_user_id="u1", course_id="c1", price_usd="100",
            teacher_wallet="thr1",
        )

    def tearDown(self):
        os.unlink(self.db)

    def test_grants_access(self):
        result = self.store.handle_checkout_completed(
            event_id="evt_1",
            checkout_session_id="cs_1",
            payment_intent="pi_1",
            amount_total_cents=10000,
            metadata={
                "purchase_id": self.purchase["purchase_id"],
                "type": "course_purchase",
            },
            payload_hash=_hash(),
        )
        self.assertEqual(result["state"], "access_granted")
        self.assertTrue(self.store.has_access("u1", "c1"))

    def test_idempotent_event(self):
        args = dict(
            event_id="evt_1",
            checkout_session_id="cs_1",
            payment_intent="pi_1",
            amount_total_cents=10000,
            metadata={
                "purchase_id": self.purchase["purchase_id"],
                "type": "course_purchase",
            },
            payload_hash=_hash(),
        )
        r1 = self.store.handle_checkout_completed(**args)
        r2 = self.store.handle_checkout_completed(**args)
        self.assertFalse(r1.get("idempotent"))
        self.assertTrue(r2.get("idempotent"))

    def test_no_access_without_webhook(self):
        self.assertFalse(self.store.has_access("u1", "c1"))

    def test_unknown_purchase_ignored(self):
        result = self.store.handle_checkout_completed(
            event_id="evt_99",
            checkout_session_id="cs_99",
            payment_intent="pi_99",
            amount_total_cents=10000,
            metadata={"purchase_id": "cp_nonexistent", "type": "course_purchase"},
            payload_hash=_hash(),
        )
        self.assertIsNone(result)


class TestPaymentFailed(unittest.TestCase):
    def setUp(self):
        self.db = _tmp_db()
        self.store = CoursePurchaseStore(self.db)
        self.purchase = self.store.create_checkout(
            earn_user_id="u1", course_id="c1", price_usd="100",
            teacher_wallet="thr1",
        )
        self.store.attach_stripe_ids(
            self.purchase["purchase_id"],
            checkout_session_id="cs_1",
            payment_intent="pi_1",
        )

    def tearDown(self):
        os.unlink(self.db)

    def test_marks_failed(self):
        result = self.store.handle_payment_failed(
            event_id="evt_f1",
            payment_intent="pi_1",
            payload_hash=_hash(),
        )
        self.assertEqual(result["state"], "payment_failed")
        self.assertFalse(self.store.has_access("u1", "c1"))


class TestRefund(unittest.TestCase):
    def setUp(self):
        self.db = _tmp_db()
        self.store = CoursePurchaseStore(self.db)
        self.purchase = self.store.create_checkout(
            earn_user_id="u1", course_id="c1", price_usd="100",
            teacher_wallet="thr1",
        )
        self.store.handle_checkout_completed(
            event_id="evt_1",
            checkout_session_id="cs_1",
            payment_intent="pi_1",
            amount_total_cents=10000,
            metadata={
                "purchase_id": self.purchase["purchase_id"],
                "type": "course_purchase",
            },
            payload_hash=_hash(),
        )

    def tearDown(self):
        os.unlink(self.db)

    def test_revokes_access(self):
        self.assertTrue(self.store.has_access("u1", "c1"))
        result = self.store.handle_refund(
            event_id="evt_r1",
            payment_intent="pi_1",
            payload_hash=_hash(),
        )
        self.assertEqual(result["state"], "refunded")
        self.assertFalse(self.store.has_access("u1", "c1"))

    def test_reverses_settlements(self):
        self.store.create_settlement(
            purchase_id=self.purchase["purchase_id"],
            teacher_wallet="thr1",
            course_id="c1",
            thr_per_usd=0.1,
        )
        self.store.handle_refund(
            event_id="evt_r2",
            payment_intent="pi_1",
            payload_hash=_hash(),
        )
        settlements = self.store.teacher_settlements_for("thr1")
        self.assertEqual(len(settlements), 1)
        self.assertEqual(settlements[0]["state"], "reversed")

    def test_reverses_rewards(self):
        self.store.create_thc_reward(
            purchase_id=self.purchase["purchase_id"],
            earn_user_id="u1",
            course_id="c1",
        )
        self.store.handle_refund(
            event_id="evt_r3",
            payment_intent="pi_1",
            payload_hash=_hash(),
        )
        # Verify reward reversed
        with self.store._tx() as con:
            row = con.execute(
                "SELECT state FROM course_thc_rewards WHERE purchase_id = ?",
                (self.purchase["purchase_id"],),
            ).fetchone()
        self.assertEqual(row["state"], "reversed")


class TestDispute(unittest.TestCase):
    def setUp(self):
        self.db = _tmp_db()
        self.store = CoursePurchaseStore(self.db)
        self.purchase = self.store.create_checkout(
            earn_user_id="u1", course_id="c1", price_usd="100",
            teacher_wallet="thr1",
        )
        self.store.handle_checkout_completed(
            event_id="evt_1", checkout_session_id="cs_1",
            payment_intent="pi_1", amount_total_cents=10000,
            metadata={"purchase_id": self.purchase["purchase_id"],
                       "type": "course_purchase"},
            payload_hash=_hash(),
        )

    def tearDown(self):
        os.unlink(self.db)

    def test_dispute_suspends_access(self):
        result = self.store.handle_dispute(
            event_id="evt_d1",
            payment_intent="pi_1",
            payload_hash=_hash(),
        )
        self.assertEqual(result["state"], "disputed")
        self.assertFalse(self.store.has_access("u1", "c1"))

    def test_dispute_won_restores_access(self):
        self.store.handle_dispute(
            event_id="evt_d1",
            payment_intent="pi_1",
            payload_hash=_hash(),
        )
        result = self.store.handle_dispute_won(
            event_id="evt_dw1",
            payment_intent="pi_1",
            payload_hash=_hash(),
        )
        self.assertEqual(result["state"], "dispute_won")
        self.assertTrue(self.store.has_access("u1", "c1"))

    def test_chargeback_terminal(self):
        self.store.handle_dispute(
            event_id="evt_d1",
            payment_intent="pi_1",
            payload_hash=_hash(),
        )
        result = self.store.handle_chargeback(
            event_id="evt_cb1",
            payment_intent="pi_1",
            payload_hash=_hash(),
        )
        self.assertEqual(result["state"], "chargeback")
        self.assertFalse(self.store.has_access("u1", "c1"))

    def test_chargeback_reverses_rewards(self):
        self.store.create_thc_reward(
            purchase_id=self.purchase["purchase_id"],
            earn_user_id="u1", course_id="c1",
        )
        self.store.handle_dispute(
            event_id="evt_d1",
            payment_intent="pi_1",
            payload_hash=_hash(),
        )
        self.store.handle_chargeback(
            event_id="evt_cb1",
            payment_intent="pi_1",
            payload_hash=_hash(),
        )
        with self.store._tx() as con:
            row = con.execute(
                "SELECT state FROM course_thc_rewards WHERE purchase_id = ?",
                (self.purchase["purchase_id"],),
            ).fetchone()
        self.assertEqual(row["state"], "reversed")


class TestTeacherSettlement(unittest.TestCase):
    def setUp(self):
        self.db = _tmp_db()
        self.store = CoursePurchaseStore(self.db)
        self.purchase = self.store.create_checkout(
            earn_user_id="u1", course_id="c1", price_usd="100",
            teacher_wallet="thr1abc",
        )
        self.store.handle_checkout_completed(
            event_id="evt_1", checkout_session_id="cs_1",
            payment_intent="pi_1", amount_total_cents=10000,
            metadata={"purchase_id": self.purchase["purchase_id"],
                       "type": "course_purchase"},
            payload_hash=_hash(),
        )

    def tearDown(self):
        os.unlink(self.db)

    def test_create_settlement(self):
        r = self.store.create_settlement(
            purchase_id=self.purchase["purchase_id"],
            teacher_wallet="thr1abc",
            course_id="c1",
            thr_per_usd=0.1,
        )
        self.assertTrue(r["settlement_id"].startswith("stl_"))
        self.assertEqual(r["state"], "unsettled")
        self.assertEqual(r["amount_usd"], "70.00")
        # 70.00 / 0.1 = 700 THR
        self.assertEqual(r["amount_thr"], "700.000000")

    def test_settle_with_ref(self):
        s = self.store.create_settlement(
            purchase_id=self.purchase["purchase_id"],
            teacher_wallet="thr1abc",
            course_id="c1",
            thr_per_usd=0.1,
        )
        r = self.store.settle(s["settlement_id"], settlement_ref="tx_abc123")
        self.assertEqual(r["state"], "settled")
        self.assertEqual(r["settlement_ref"], "tx_abc123")

    def test_settle_requires_ref(self):
        s = self.store.create_settlement(
            purchase_id=self.purchase["purchase_id"],
            teacher_wallet="thr1abc",
            course_id="c1",
            thr_per_usd=0.1,
        )
        with self.assertRaises(CoursePurchaseError):
            self.store.settle(s["settlement_id"], settlement_ref="")

    def test_settlement_idempotent(self):
        s1 = self.store.create_settlement(
            purchase_id=self.purchase["purchase_id"],
            teacher_wallet="thr1abc", course_id="c1", thr_per_usd=0.1,
        )
        s2 = self.store.create_settlement(
            purchase_id=self.purchase["purchase_id"],
            teacher_wallet="thr1abc", course_id="c1", thr_per_usd=0.1,
        )
        self.assertEqual(s1["settlement_id"], s2["settlement_id"])

    def test_settlement_requires_wallet(self):
        with self.assertRaises(CoursePurchaseError):
            self.store.create_settlement(
                purchase_id=self.purchase["purchase_id"],
                teacher_wallet="", course_id="c1", thr_per_usd=0.1,
            )

    def test_settlement_requires_access_granted_state(self):
        pending = self.store.create_checkout(
            earn_user_id="u2", course_id="c2", price_usd="50",
            teacher_wallet="thr2",
        )
        with self.assertRaises(CoursePurchaseError):
            self.store.create_settlement(
                purchase_id=pending["purchase_id"],
                teacher_wallet="thr2", course_id="c2", thr_per_usd=0.1,
            )

    def test_teacher_settlement_list(self):
        self.store.create_settlement(
            purchase_id=self.purchase["purchase_id"],
            teacher_wallet="thr1abc", course_id="c1", thr_per_usd=0.1,
        )
        settlements = self.store.teacher_settlements_for("thr1abc")
        self.assertEqual(len(settlements), 1)
        self.assertEqual(settlements[0]["course_id"], "c1")


class TestTHCReward(unittest.TestCase):
    def setUp(self):
        self.db = _tmp_db()
        self.store = CoursePurchaseStore(self.db)
        self.purchase = self.store.create_checkout(
            earn_user_id="u1", course_id="c1", price_usd="100",
            teacher_wallet="thr1",
        )
        self.store.handle_checkout_completed(
            event_id="evt_1", checkout_session_id="cs_1",
            payment_intent="pi_1", amount_total_cents=10000,
            metadata={"purchase_id": self.purchase["purchase_id"],
                       "type": "course_purchase"},
            payload_hash=_hash(),
        )

    def tearDown(self):
        os.unlink(self.db)

    def test_create_reward(self):
        r = self.store.create_thc_reward(
            purchase_id=self.purchase["purchase_id"],
            earn_user_id="u1",
            course_id="c1",
            thc_entry_id="thc_abc",
        )
        self.assertTrue(r["reward_id"].startswith("ctr_"))
        self.assertEqual(r["state"], "pending")
        self.assertEqual(r["amount_thc"], "5.00")

    def test_reward_idempotent(self):
        r1 = self.store.create_thc_reward(
            purchase_id=self.purchase["purchase_id"],
            earn_user_id="u1", course_id="c1",
        )
        r2 = self.store.create_thc_reward(
            purchase_id=self.purchase["purchase_id"],
            earn_user_id="u1", course_id="c1",
        )
        self.assertEqual(r1["reward_id"], r2["reward_id"])

    def test_reward_requires_access_granted(self):
        pending = self.store.create_checkout(
            earn_user_id="u2", course_id="c2", price_usd="50",
            teacher_wallet="thr2",
        )
        with self.assertRaises(CoursePurchaseError):
            self.store.create_thc_reward(
                purchase_id=pending["purchase_id"],
                earn_user_id="u2", course_id="c2",
            )


class TestEventIdempotency(unittest.TestCase):
    def setUp(self):
        self.db = _tmp_db()
        self.store = CoursePurchaseStore(self.db)
        self.purchase = self.store.create_checkout(
            earn_user_id="u1", course_id="c1", price_usd="100",
            teacher_wallet="thr1",
        )
        self.store.handle_checkout_completed(
            event_id="evt_1", checkout_session_id="cs_1",
            payment_intent="pi_1", amount_total_cents=10000,
            metadata={"purchase_id": self.purchase["purchase_id"],
                       "type": "course_purchase"},
            payload_hash=_hash(),
        )

    def tearDown(self):
        os.unlink(self.db)

    def test_duplicate_refund_event_idempotent(self):
        r1 = self.store.handle_refund(
            event_id="evt_r1", payment_intent="pi_1", payload_hash=_hash(),
        )
        r2 = self.store.handle_refund(
            event_id="evt_r1", payment_intent="pi_1", payload_hash=_hash(),
        )
        self.assertFalse(r1.get("idempotent"))
        self.assertTrue(r2.get("idempotent"))

    def test_duplicate_dispute_event_idempotent(self):
        r1 = self.store.handle_dispute(
            event_id="evt_d1", payment_intent="pi_1", payload_hash=_hash(),
        )
        r2 = self.store.handle_dispute(
            event_id="evt_d1", payment_intent="pi_1", payload_hash=_hash(),
        )
        self.assertFalse(r1.get("idempotent"))
        self.assertTrue(r2.get("idempotent"))

    def test_event_log_recorded(self):
        with self.store._tx() as con:
            rows = con.execute("SELECT * FROM stripe_events_log").fetchall()
        # evt_1 from setUp
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event_type"], "checkout.session.completed")


class TestPurchaseQueries(unittest.TestCase):
    def setUp(self):
        self.db = _tmp_db()
        self.store = CoursePurchaseStore(self.db)

    def tearDown(self):
        os.unlink(self.db)

    def test_list_purchases(self):
        self.store.create_checkout(
            earn_user_id="u1", course_id="c1", price_usd="50",
            teacher_wallet="thr1",
        )
        self.store.create_checkout(
            earn_user_id="u1", course_id="c2", price_usd="75",
            teacher_wallet="thr1",
        )
        purchases = self.store.list_purchases("u1")
        self.assertEqual(len(purchases), 2)

    def test_get_purchase(self):
        r = self.store.create_checkout(
            earn_user_id="u1", course_id="c1", price_usd="50",
            teacher_wallet="thr1",
        )
        p = self.store.get_purchase(r["purchase_id"])
        self.assertIsNotNone(p)
        self.assertEqual(p["course_id"], "c1")

    def test_get_purchase_nonexistent(self):
        self.assertIsNone(self.store.get_purchase("cp_nope"))

    def test_get_by_checkout(self):
        r = self.store.create_checkout(
            earn_user_id="u1", course_id="c1", price_usd="50",
            teacher_wallet="thr1",
        )
        self.store.attach_stripe_ids(
            r["purchase_id"],
            checkout_session_id="cs_abc",
            payment_intent="pi_abc",
        )
        p = self.store.get_purchase_by_checkout("cs_abc")
        self.assertIsNotNone(p)
        self.assertEqual(p["purchase_id"], r["purchase_id"])


class TestStateMachine(unittest.TestCase):
    """Verify that state transitions follow the defined graph."""

    def setUp(self):
        self.db = _tmp_db()
        self.store = CoursePurchaseStore(self.db)

    def tearDown(self):
        os.unlink(self.db)

    def _make_access_granted(self, uid="u1", cid="c1", pi="pi_1"):
        p = self.store.create_checkout(
            earn_user_id=uid, course_id=cid, price_usd="100",
            teacher_wallet="thr1",
        )
        self.store.handle_checkout_completed(
            event_id=f"evt_{uid}_{cid}",
            checkout_session_id=f"cs_{uid}_{cid}",
            payment_intent=pi,
            amount_total_cents=10000,
            metadata={"purchase_id": p["purchase_id"],
                       "type": "course_purchase"},
            payload_hash=_hash(),
        )
        return p

    def test_checkout_pending_to_payment_failed(self):
        p = self.store.create_checkout(
            earn_user_id="u1", course_id="c1", price_usd="100",
            teacher_wallet="thr1",
        )
        self.store.attach_stripe_ids(
            p["purchase_id"],
            checkout_session_id="cs_1",
            payment_intent="pi_1",
        )
        r = self.store.handle_payment_failed(
            event_id="evt_f1", payment_intent="pi_1", payload_hash=_hash(),
        )
        self.assertEqual(r["state"], "payment_failed")

    def test_cannot_refund_non_granted(self):
        p = self.store.create_checkout(
            earn_user_id="u1", course_id="c1", price_usd="100",
            teacher_wallet="thr1",
        )
        self.store.attach_stripe_ids(
            p["purchase_id"], checkout_session_id="cs_1", payment_intent="pi_fail",
        )
        result = self.store.handle_refund(
            event_id="evt_r1", payment_intent="pi_fail", payload_hash=_hash(),
        )
        self.assertIsNone(result)

    def test_dispute_requires_access_granted(self):
        p = self.store.create_checkout(
            earn_user_id="u1", course_id="c1", price_usd="100",
            teacher_wallet="thr1",
        )
        self.store.attach_stripe_ids(
            p["purchase_id"], checkout_session_id="cs_1", payment_intent="pi_nope",
        )
        result = self.store.handle_dispute(
            event_id="evt_d1", payment_intent="pi_nope", payload_hash=_hash(),
        )
        self.assertIsNone(result)

    def test_full_lifecycle_dispute_won(self):
        p = self._make_access_granted()
        self.assertTrue(self.store.has_access("u1", "c1"))

        self.store.handle_dispute(
            event_id="evt_d1", payment_intent="pi_1", payload_hash=_hash(),
        )
        self.assertFalse(self.store.has_access("u1", "c1"))

        self.store.handle_dispute_won(
            event_id="evt_dw1", payment_intent="pi_1", payload_hash=_hash(),
        )
        self.assertTrue(self.store.has_access("u1", "c1"))

    def test_full_lifecycle_chargeback(self):
        p = self._make_access_granted()
        self.assertTrue(self.store.has_access("u1", "c1"))

        self.store.handle_dispute(
            event_id="evt_d1", payment_intent="pi_1", payload_hash=_hash(),
        )
        self.store.handle_chargeback(
            event_id="evt_cb1", payment_intent="pi_1", payload_hash=_hash(),
        )
        self.assertFalse(self.store.has_access("u1", "c1"))


class TestNoAccessWithoutWebhook(unittest.TestCase):
    """Access must never be granted by browser claims."""

    def setUp(self):
        self.db = _tmp_db()
        self.store = CoursePurchaseStore(self.db)

    def tearDown(self):
        os.unlink(self.db)

    def test_checkout_alone_gives_no_access(self):
        self.store.create_checkout(
            earn_user_id="u1", course_id="c1", price_usd="100",
            teacher_wallet="thr1",
        )
        self.assertFalse(self.store.has_access("u1", "c1"))

    def test_attach_stripe_ids_gives_no_access(self):
        p = self.store.create_checkout(
            earn_user_id="u1", course_id="c1", price_usd="100",
            teacher_wallet="thr1",
        )
        self.store.attach_stripe_ids(
            p["purchase_id"],
            checkout_session_id="cs_1",
            payment_intent="pi_1",
        )
        self.assertFalse(self.store.has_access("u1", "c1"))


class TestIsolation(unittest.TestCase):
    """Users don't see each other's data."""

    def setUp(self):
        self.db = _tmp_db()
        self.store = CoursePurchaseStore(self.db)

    def tearDown(self):
        os.unlink(self.db)

    def test_user_isolation(self):
        self.store.create_checkout(
            earn_user_id="u1", course_id="c1", price_usd="50",
            teacher_wallet="thr1",
        )
        self.store.create_checkout(
            earn_user_id="u2", course_id="c2", price_usd="75",
            teacher_wallet="thr1",
        )
        p1 = self.store.list_purchases("u1")
        p2 = self.store.list_purchases("u2")
        self.assertEqual(len(p1), 1)
        self.assertEqual(len(p2), 1)
        self.assertEqual(p1[0]["course_id"], "c1")
        self.assertEqual(p2[0]["course_id"], "c2")


class TestMarginCalculation(unittest.TestCase):
    """Verify THC reward never exceeds available margin."""

    def setUp(self):
        self.db = _tmp_db()
        self.store = CoursePurchaseStore(self.db)

    def tearDown(self):
        os.unlink(self.db)

    def test_tiny_price_zero_reward(self):
        # $1 course: stripe fee = 0.33, teacher share = 0.70, net = -0.03 → 0
        r = self.store.create_checkout(
            earn_user_id="u1", course_id="c1", price_usd="1.00",
            teacher_wallet="thr1",
        )
        # net is negative → clamped to 0, so reward is 0
        self.assertEqual(r["thc_reward_usd"], "0.00")

    def test_mid_price(self):
        # $25 course: stripe fee = 1.03, teacher = 17.50, net = 6.47
        # cap_price = 1.25, cap_margin = 1.62 → reward = 1.25
        r = self.store.create_checkout(
            earn_user_id="u1", course_id="c1", price_usd="25.00",
            teacher_wallet="thr1",
        )
        self.assertEqual(r["thc_reward_usd"], "1.25")

    def test_expensive_course(self):
        # $500 course: stripe = 14.80, teacher = 350, net = 135.20
        # cap_price = 25.00, cap_margin = 33.80 → reward = 25.00
        r = self.store.create_checkout(
            earn_user_id="u1", course_id="c1", price_usd="500.00",
            teacher_wallet="thr1",
        )
        self.assertEqual(r["thc_reward_usd"], "25.00")


if __name__ == "__main__":
    unittest.main()
