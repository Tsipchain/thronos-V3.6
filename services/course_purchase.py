"""
Thronos — Secure Fiat Course Purchase

Earn Account → select course → Stripe Checkout → verified webhook
→ access entitlement → teacher THR settlement → optional THC reward.

Access granted ONLY from verified Stripe webhook, never from browser claims.
Teacher settlement denominated in THR with auditable identity.
Refund / dispute / chargeback revokes access and reverses unspent THC rewards.

No BTC payout. No L2E for wallet-less students. No auto-mint.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PURCHASE_TRANSITIONS: dict[str, set[str]] = {
    "checkout_pending": {"paid", "payment_failed", "expired"},
    "paid":             {"access_granted"},
    "access_granted":   {"refunded", "disputed"},
    "payment_failed":   set(),
    "expired":          set(),
    "refunded":         set(),
    "disputed":         {"dispute_won", "chargeback"},
    "dispute_won":      set(),
    "chargeback":       set(),
}

_SETTLEMENT_TRANSITIONS: dict[str, set[str]] = {
    "unsettled": {"settled", "reversed"},
    "settled":   {"reversed"},
    "reversed":  set(),
}

_ACCESS_REVOKING_STATES = {"refunded", "chargeback"}
_ACCESS_RESTORING_STATES = {"dispute_won"}
_REWARD_REVERSING_STATES = {"refunded", "chargeback"}

_STRIPE_FEE_PCT = Decimal("0.029")
_STRIPE_FEE_FIXED = Decimal("0.30")
_DEFAULT_TEACHER_SHARE_PCT = Decimal("0.70")
_THC_REWARD_CAP_OF_PRICE = Decimal("0.05")
_THC_REWARD_CAP_OF_MARGIN = Decimal("0.25")


class CoursePurchaseError(ValueError):
    pass


class CoursePurchaseStore:
    """SQLite-backed fiat course purchase store."""

    def __init__(self, db_path: str, earn_db_path: str | None = None):
        self.db_path = db_path
        self._earn_db_path = earn_db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _tx(self):
        con = sqlite3.connect(self.db_path, timeout=15, isolation_level=None)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA foreign_keys = ON")
            con.execute("PRAGMA journal_mode = WAL")
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def _init_db(self) -> None:
        con = sqlite3.connect(self.db_path, timeout=15)
        try:
            con.executescript("""
                PRAGMA journal_mode = WAL;
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS course_purchases (
                    purchase_id         TEXT PRIMARY KEY,
                    earn_user_id        TEXT NOT NULL,
                    course_id           TEXT NOT NULL,
                    stripe_checkout_id  TEXT UNIQUE,
                    stripe_payment_intent TEXT,
                    stripe_event_id     TEXT,
                    price_usd           TEXT NOT NULL,
                    teacher_share_usd   TEXT NOT NULL,
                    platform_net_usd    TEXT NOT NULL,
                    thc_reward_usd      TEXT NOT NULL DEFAULT '0',
                    state               TEXT NOT NULL DEFAULT 'checkout_pending',
                    created_at          INTEGER NOT NULL,
                    updated_at          INTEGER NOT NULL,
                    UNIQUE(earn_user_id, course_id)
                );

                CREATE INDEX IF NOT EXISTS idx_cp_checkout
                    ON course_purchases(stripe_checkout_id);
                CREATE INDEX IF NOT EXISTS idx_cp_pi
                    ON course_purchases(stripe_payment_intent);
                CREATE INDEX IF NOT EXISTS idx_cp_user
                    ON course_purchases(earn_user_id);

                CREATE TABLE IF NOT EXISTS course_access (
                    earn_user_id    TEXT NOT NULL,
                    course_id       TEXT NOT NULL,
                    purchase_id     TEXT NOT NULL,
                    granted_at      INTEGER NOT NULL,
                    revoked_at      INTEGER,
                    restored_at     INTEGER,
                    active          INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (earn_user_id, course_id)
                );

                CREATE TABLE IF NOT EXISTS teacher_settlements (
                    settlement_id   TEXT PRIMARY KEY,
                    purchase_id     TEXT NOT NULL,
                    teacher_wallet  TEXT NOT NULL,
                    course_id       TEXT NOT NULL,
                    amount_thr      TEXT NOT NULL,
                    amount_usd      TEXT NOT NULL,
                    state           TEXT NOT NULL DEFAULT 'unsettled',
                    settlement_ref  TEXT,
                    created_at      INTEGER NOT NULL,
                    updated_at      INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_ts_teacher
                    ON teacher_settlements(teacher_wallet);
                CREATE INDEX IF NOT EXISTS idx_ts_purchase
                    ON teacher_settlements(purchase_id);

                CREATE TABLE IF NOT EXISTS course_thc_rewards (
                    reward_id       TEXT PRIMARY KEY,
                    purchase_id     TEXT NOT NULL,
                    earn_user_id    TEXT NOT NULL,
                    course_id       TEXT NOT NULL,
                    thc_entry_id    TEXT,
                    amount_thc      TEXT NOT NULL,
                    state           TEXT NOT NULL DEFAULT 'pending',
                    created_at      INTEGER NOT NULL,
                    updated_at      INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_ctr_purchase
                    ON course_thc_rewards(purchase_id);

                CREATE TABLE IF NOT EXISTS stripe_events_log (
                    stripe_event_id TEXT PRIMARY KEY,
                    event_type      TEXT NOT NULL,
                    processed_at    INTEGER NOT NULL,
                    purchase_id     TEXT,
                    payload_hash    TEXT NOT NULL
                );
            """)
        finally:
            con.close()

    # ── Stripe Checkout ─────────────────────────────────────────────────

    def create_checkout(
        self,
        *,
        earn_user_id: str,
        course_id: str,
        price_usd: str | float,
        teacher_wallet: str,
        teacher_share_pct: float | None = None,
    ) -> dict[str, Any]:
        try:
            price = Decimal(str(price_usd))
            if price <= 0:
                raise ValueError
        except (TypeError, ValueError, InvalidOperation):
            raise CoursePurchaseError("invalid_price")

        if not earn_user_id or not course_id:
            raise CoursePurchaseError("missing_required_fields")
        if not teacher_wallet:
            raise CoursePurchaseError("teacher_wallet_required")

        share_pct = (
            Decimal(str(teacher_share_pct))
            if teacher_share_pct is not None
            else _DEFAULT_TEACHER_SHARE_PCT
        )

        stripe_fee = (price * _STRIPE_FEE_PCT + _STRIPE_FEE_FIXED).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )
        teacher_share = (price * share_pct).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )
        platform_net = price - stripe_fee - teacher_share
        if platform_net < 0:
            platform_net = Decimal("0")

        cap_of_price = (price * _THC_REWARD_CAP_OF_PRICE).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )
        cap_of_margin = (platform_net * _THC_REWARD_CAP_OF_MARGIN).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )
        thc_reward = min(cap_of_price, cap_of_margin)
        if thc_reward < 0:
            thc_reward = Decimal("0")

        purchase_id = "cp_" + secrets.token_urlsafe(18)
        now = int(time.time())

        with self._tx() as con:
            existing = con.execute(
                "SELECT purchase_id, state FROM course_purchases WHERE earn_user_id = ? AND course_id = ?",
                (earn_user_id, course_id),
            ).fetchone()
            if existing:
                if existing["state"] in ("access_granted", "dispute_won"):
                    raise CoursePurchaseError("already_enrolled")
                if existing["state"] == "checkout_pending":
                    return dict(existing)
                if existing["state"] in ("payment_failed", "expired", "refunded", "chargeback"):
                    con.execute(
                        "DELETE FROM course_purchases WHERE purchase_id = ?",
                        (existing["purchase_id"],),
                    )

            con.execute(
                """INSERT INTO course_purchases
                   (purchase_id, earn_user_id, course_id,
                    price_usd, teacher_share_usd, platform_net_usd,
                    thc_reward_usd, state, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    purchase_id,
                    earn_user_id,
                    course_id,
                    str(price),
                    str(teacher_share),
                    str(platform_net),
                    str(thc_reward),
                    "checkout_pending",
                    now,
                    now,
                ),
            )

        return {
            "purchase_id": purchase_id,
            "price_usd": str(price),
            "teacher_share_usd": str(teacher_share),
            "platform_net_usd": str(platform_net),
            "thc_reward_usd": str(thc_reward),
            "state": "checkout_pending",
        }

    def attach_stripe_ids(
        self,
        purchase_id: str,
        *,
        checkout_session_id: str,
        payment_intent: str | None = None,
    ) -> None:
        with self._tx() as con:
            con.execute(
                """UPDATE course_purchases
                   SET stripe_checkout_id = ?, stripe_payment_intent = ?,
                       updated_at = ?
                   WHERE purchase_id = ? AND state = 'checkout_pending'""",
                (checkout_session_id, payment_intent, int(time.time()), purchase_id),
            )

    # ── Stripe Event Idempotency ────────────────────────────────────────

    def _is_event_processed(self, con: sqlite3.Connection, event_id: str) -> bool:
        row = con.execute(
            "SELECT 1 FROM stripe_events_log WHERE stripe_event_id = ?",
            (event_id,),
        ).fetchone()
        return row is not None

    def _log_event(
        self,
        con: sqlite3.Connection,
        event_id: str,
        event_type: str,
        purchase_id: str | None,
        payload_hash: str,
    ) -> None:
        con.execute(
            """INSERT OR IGNORE INTO stripe_events_log
               (stripe_event_id, event_type, processed_at, purchase_id, payload_hash)
               VALUES (?,?,?,?,?)""",
            (event_id, event_type, int(time.time()), purchase_id, payload_hash),
        )

    # ── Webhook: checkout.session.completed ──────────────────────────────

    def handle_checkout_completed(
        self,
        *,
        event_id: str,
        checkout_session_id: str,
        payment_intent: str | None,
        amount_total_cents: int,
        metadata: dict[str, str],
        payload_hash: str,
    ) -> dict[str, Any] | None:
        purchase_id = metadata.get("purchase_id", "")
        if not purchase_id:
            return None

        with self._tx() as con:
            if self._is_event_processed(con, event_id):
                return {"idempotent": True, "purchase_id": purchase_id}

            row = con.execute(
                "SELECT * FROM course_purchases WHERE purchase_id = ?",
                (purchase_id,),
            ).fetchone()
            if not row:
                return None
            if row["state"] != "checkout_pending":
                self._log_event(con, event_id, "checkout.session.completed", purchase_id, payload_hash)
                return {"idempotent": True, "purchase_id": purchase_id}

            now = int(time.time())

            con.execute(
                """UPDATE course_purchases
                   SET state = 'paid',
                       stripe_checkout_id = ?,
                       stripe_payment_intent = ?,
                       stripe_event_id = ?,
                       updated_at = ?
                   WHERE purchase_id = ?""",
                (checkout_session_id, payment_intent, event_id, now, purchase_id),
            )

            con.execute(
                """UPDATE course_purchases
                   SET state = 'access_granted', updated_at = ?
                   WHERE purchase_id = ?""",
                (now, purchase_id),
            )

            con.execute(
                """INSERT OR IGNORE INTO course_access
                   (earn_user_id, course_id, purchase_id, granted_at, active)
                   VALUES (?,?,?,?,1)""",
                (row["earn_user_id"], row["course_id"], purchase_id, now),
            )

            self._log_event(con, event_id, "checkout.session.completed", purchase_id, payload_hash)

        return {
            "purchase_id": purchase_id,
            "earn_user_id": row["earn_user_id"],
            "course_id": row["course_id"],
            "state": "access_granted",
            "thc_reward_usd": row["thc_reward_usd"],
        }

    # ── Webhook: payment_intent.payment_failed ───────────────────────────

    def handle_payment_failed(
        self,
        *,
        event_id: str,
        payment_intent: str,
        payload_hash: str,
    ) -> dict[str, Any] | None:
        with self._tx() as con:
            if self._is_event_processed(con, event_id):
                return {"idempotent": True}

            row = con.execute(
                "SELECT * FROM course_purchases WHERE stripe_payment_intent = ? AND state = 'checkout_pending'",
                (payment_intent,),
            ).fetchone()
            if not row:
                return None

            con.execute(
                "UPDATE course_purchases SET state = 'payment_failed', updated_at = ? WHERE purchase_id = ?",
                (int(time.time()), row["purchase_id"]),
            )
            self._log_event(con, event_id, "payment_intent.payment_failed", row["purchase_id"], payload_hash)

        return {"purchase_id": row["purchase_id"], "state": "payment_failed"}

    # ── Webhook: charge.refunded ─────────────────────────────────────────

    def handle_refund(
        self,
        *,
        event_id: str,
        payment_intent: str,
        payload_hash: str,
    ) -> dict[str, Any] | None:
        with self._tx() as con:
            if self._is_event_processed(con, event_id):
                return {"idempotent": True}

            row = con.execute(
                "SELECT * FROM course_purchases WHERE stripe_payment_intent = ? AND state = 'access_granted'",
                (payment_intent,),
            ).fetchone()
            if not row:
                return None

            now = int(time.time())
            con.execute(
                "UPDATE course_purchases SET state = 'refunded', updated_at = ? WHERE purchase_id = ?",
                (now, row["purchase_id"]),
            )
            con.execute(
                "UPDATE course_access SET active = 0, revoked_at = ? WHERE purchase_id = ?",
                (now, row["purchase_id"]),
            )
            self._reverse_rewards_in_tx(con, row["purchase_id"])
            self._reverse_settlement_in_tx(con, row["purchase_id"])
            self._log_event(con, event_id, "charge.refunded", row["purchase_id"], payload_hash)

        return {"purchase_id": row["purchase_id"], "state": "refunded"}

    # ── Webhook: charge.dispute.created ──────────────────────────────────

    def handle_dispute(
        self,
        *,
        event_id: str,
        payment_intent: str,
        payload_hash: str,
    ) -> dict[str, Any] | None:
        with self._tx() as con:
            if self._is_event_processed(con, event_id):
                return {"idempotent": True}

            row = con.execute(
                "SELECT * FROM course_purchases WHERE stripe_payment_intent = ? AND state = 'access_granted'",
                (payment_intent,),
            ).fetchone()
            if not row:
                return None

            now = int(time.time())
            con.execute(
                "UPDATE course_purchases SET state = 'disputed', updated_at = ? WHERE purchase_id = ?",
                (now, row["purchase_id"]),
            )
            con.execute(
                "UPDATE course_access SET active = 0, revoked_at = ? WHERE purchase_id = ?",
                (now, row["purchase_id"]),
            )
            self._log_event(con, event_id, "charge.dispute.created", row["purchase_id"], payload_hash)

        return {"purchase_id": row["purchase_id"], "state": "disputed"}

    # ── Webhook: charge.dispute.closed (won) ─────────────────────────────

    def handle_dispute_won(
        self,
        *,
        event_id: str,
        payment_intent: str,
        payload_hash: str,
    ) -> dict[str, Any] | None:
        with self._tx() as con:
            if self._is_event_processed(con, event_id):
                return {"idempotent": True}

            row = con.execute(
                "SELECT * FROM course_purchases WHERE stripe_payment_intent = ? AND state = 'disputed'",
                (payment_intent,),
            ).fetchone()
            if not row:
                return None

            now = int(time.time())
            con.execute(
                "UPDATE course_purchases SET state = 'dispute_won', updated_at = ? WHERE purchase_id = ?",
                (now, row["purchase_id"]),
            )
            con.execute(
                "UPDATE course_access SET active = 1, restored_at = ? WHERE purchase_id = ?",
                (now, row["purchase_id"]),
            )
            self._log_event(con, event_id, "charge.dispute.closed", row["purchase_id"], payload_hash)

        return {"purchase_id": row["purchase_id"], "state": "dispute_won"}

    # ── Webhook: charge.dispute.closed (lost = chargeback) ───────────────

    def handle_chargeback(
        self,
        *,
        event_id: str,
        payment_intent: str,
        payload_hash: str,
    ) -> dict[str, Any] | None:
        with self._tx() as con:
            if self._is_event_processed(con, event_id):
                return {"idempotent": True}

            row = con.execute(
                "SELECT * FROM course_purchases WHERE stripe_payment_intent = ? AND state = 'disputed'",
                (payment_intent,),
            ).fetchone()
            if not row:
                return None

            now = int(time.time())
            con.execute(
                "UPDATE course_purchases SET state = 'chargeback', updated_at = ? WHERE purchase_id = ?",
                (now, row["purchase_id"]),
            )
            self._reverse_rewards_in_tx(con, row["purchase_id"])
            self._reverse_settlement_in_tx(con, row["purchase_id"])
            self._log_event(con, event_id, "charge.dispute.closed", row["purchase_id"], payload_hash)

        return {"purchase_id": row["purchase_id"], "state": "chargeback"}

    # ── Teacher Settlement ──────────────────────────────────────────────

    def create_settlement(
        self,
        *,
        purchase_id: str,
        teacher_wallet: str,
        course_id: str,
        thr_per_usd: float,
    ) -> dict[str, Any]:
        if not teacher_wallet:
            raise CoursePurchaseError("teacher_wallet_required")
        with self._tx() as con:
            purchase = con.execute(
                "SELECT * FROM course_purchases WHERE purchase_id = ?",
                (purchase_id,),
            ).fetchone()
            if not purchase:
                raise CoursePurchaseError("purchase_not_found")
            if purchase["state"] not in ("access_granted", "dispute_won"):
                raise CoursePurchaseError("purchase_not_settled_eligible")

            existing = con.execute(
                "SELECT * FROM teacher_settlements WHERE purchase_id = ? AND state != 'reversed'",
                (purchase_id,),
            ).fetchone()
            if existing:
                return dict(existing)

            usd_amount = Decimal(purchase["teacher_share_usd"])
            thr_amount = (usd_amount / Decimal(str(thr_per_usd))).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP,
            )

            settlement_id = "stl_" + secrets.token_urlsafe(18)
            now = int(time.time())
            con.execute(
                """INSERT INTO teacher_settlements
                   (settlement_id, purchase_id, teacher_wallet, course_id,
                    amount_thr, amount_usd, state, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    settlement_id,
                    purchase_id,
                    teacher_wallet,
                    course_id,
                    str(thr_amount),
                    str(usd_amount),
                    "unsettled",
                    now,
                    now,
                ),
            )

        return {
            "settlement_id": settlement_id,
            "teacher_wallet": teacher_wallet,
            "amount_thr": str(thr_amount),
            "amount_usd": str(usd_amount),
            "state": "unsettled",
        }

    def settle(self, settlement_id: str, *, settlement_ref: str) -> dict[str, Any]:
        if not settlement_ref:
            raise CoursePurchaseError("settlement_ref_required")
        with self._tx() as con:
            row = con.execute(
                "SELECT * FROM teacher_settlements WHERE settlement_id = ?",
                (settlement_id,),
            ).fetchone()
            if not row:
                raise CoursePurchaseError("settlement_not_found")
            if row["state"] == "settled":
                return dict(row)
            if "settled" not in _SETTLEMENT_TRANSITIONS.get(row["state"], set()):
                raise CoursePurchaseError("invalid_settlement_transition")
            con.execute(
                """UPDATE teacher_settlements
                   SET state = 'settled', settlement_ref = ?, updated_at = ?
                   WHERE settlement_id = ?""",
                (settlement_ref, int(time.time()), settlement_id),
            )
            return dict(
                con.execute(
                    "SELECT * FROM teacher_settlements WHERE settlement_id = ?",
                    (settlement_id,),
                ).fetchone(),
            )

    def _reverse_settlement_in_tx(
        self, con: sqlite3.Connection, purchase_id: str,
    ) -> None:
        con.execute(
            """UPDATE teacher_settlements
               SET state = 'reversed', updated_at = ?
               WHERE purchase_id = ? AND state != 'reversed'""",
            (int(time.time()), purchase_id),
        )

    # ── THC Course Reward ───────────────────────────────────────────────

    def create_thc_reward(
        self,
        *,
        purchase_id: str,
        earn_user_id: str,
        course_id: str,
        thc_entry_id: str | None = None,
    ) -> dict[str, Any]:
        with self._tx() as con:
            purchase = con.execute(
                "SELECT * FROM course_purchases WHERE purchase_id = ?",
                (purchase_id,),
            ).fetchone()
            if not purchase:
                raise CoursePurchaseError("purchase_not_found")
            if purchase["state"] not in ("access_granted", "dispute_won"):
                raise CoursePurchaseError("purchase_not_reward_eligible")

            existing = con.execute(
                "SELECT * FROM course_thc_rewards WHERE purchase_id = ?",
                (purchase_id,),
            ).fetchone()
            if existing:
                return dict(existing)

            reward_id = "ctr_" + secrets.token_urlsafe(18)
            now = int(time.time())
            con.execute(
                """INSERT INTO course_thc_rewards
                   (reward_id, purchase_id, earn_user_id, course_id,
                    thc_entry_id, amount_thc, state, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    reward_id,
                    purchase_id,
                    earn_user_id,
                    course_id,
                    thc_entry_id,
                    purchase["thc_reward_usd"],
                    "pending",
                    now,
                    now,
                ),
            )

        return {
            "reward_id": reward_id,
            "amount_thc": purchase["thc_reward_usd"],
            "state": "pending",
        }

    def _reverse_rewards_in_tx(
        self, con: sqlite3.Connection, purchase_id: str,
    ) -> None:
        con.execute(
            """UPDATE course_thc_rewards
               SET state = 'reversed', updated_at = ?
               WHERE purchase_id = ? AND state != 'reversed'""",
            (int(time.time()), purchase_id),
        )

    # ── Access Queries ──────────────────────────────────────────────────

    def has_access(self, earn_user_id: str, course_id: str) -> bool:
        with self._tx() as con:
            row = con.execute(
                "SELECT active FROM course_access WHERE earn_user_id = ? AND course_id = ?",
                (earn_user_id, course_id),
            ).fetchone()
            return bool(row and row["active"])

    def list_purchases(
        self, earn_user_id: str, *, limit: int = 50,
    ) -> list[dict[str, Any]]:
        with self._tx() as con:
            rows = con.execute(
                """SELECT p.*, a.active as has_access
                   FROM course_purchases p
                   LEFT JOIN course_access a
                     ON a.earn_user_id = p.earn_user_id AND a.course_id = p.course_id
                   WHERE p.earn_user_id = ?
                   ORDER BY p.created_at DESC LIMIT ?""",
                (earn_user_id, min(max(limit, 1), 200)),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_purchase(self, purchase_id: str) -> dict[str, Any] | None:
        with self._tx() as con:
            row = con.execute(
                "SELECT * FROM course_purchases WHERE purchase_id = ?",
                (purchase_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_purchase_by_checkout(self, checkout_session_id: str) -> dict[str, Any] | None:
        with self._tx() as con:
            row = con.execute(
                "SELECT * FROM course_purchases WHERE stripe_checkout_id = ?",
                (checkout_session_id,),
            ).fetchone()
            return dict(row) if row else None

    def teacher_settlements_for(
        self, teacher_wallet: str, *, limit: int = 50,
    ) -> list[dict[str, Any]]:
        with self._tx() as con:
            rows = con.execute(
                """SELECT * FROM teacher_settlements
                   WHERE teacher_wallet = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (teacher_wallet, min(max(limit, 1), 200)),
            ).fetchall()
            return [dict(r) for r in rows]


# ── Flask route registration ─────────────────────────────────────────────


def register_course_purchase_routes(
    app: Any,
    store: CoursePurchaseStore,
    *,
    get_stripe: Any = None,
    get_earn_store: Any = None,
    get_course_fn: Any = None,
    stripe_webhook_secret_fn: Any = None,
) -> None:
    from flask import jsonify, request

    def _current_earn_user():
        if not get_earn_store:
            return None
        earn_store = get_earn_store()
        if not earn_store:
            return None
        token = (
            request.headers.get("Authorization", "")
            .removeprefix("Bearer ")
            .strip()
        )
        return earn_store.user_for_session(token)

    @app.post("/api/earn/courses/checkout")
    def earn_course_checkout():
        stripe_mod = get_stripe() if get_stripe else None
        if not stripe_mod:
            return jsonify(ok=False, error="stripe_not_configured"), 503

        user = _current_earn_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401

        data = request.get_json(silent=True) or {}
        course_id = (data.get("course_id") or "").strip()
        if not course_id:
            return jsonify(ok=False, error="missing_course_id"), 400

        course_loader = get_course_fn() if get_course_fn else None
        if not course_loader:
            return jsonify(ok=False, error="courses_not_available"), 503
        course = course_loader(course_id)
        if not course:
            return jsonify(ok=False, error="course_not_found"), 404

        teacher = course.get("teacher", "")
        if not teacher:
            return jsonify(ok=False, error="course_has_no_teacher"), 400

        price_usd = course.get("price_fiat_estimate_usd")
        if not price_usd or float(price_usd) <= 0:
            return jsonify(ok=False, error="course_has_no_fiat_price"), 400

        try:
            result = store.create_checkout(
                earn_user_id=user["earn_user_id"],
                course_id=course_id,
                price_usd=price_usd,
                teacher_wallet=teacher,
            )
        except CoursePurchaseError as exc:
            code = 409 if "already" in str(exc) else 400
            return jsonify(ok=False, error=str(exc)), code

        if "stripe_checkout_id" in result:
            return jsonify(ok=True, **result)

        domain = os.getenv("DOMAIN_URL", "http://localhost:5000")
        try:
            session = stripe_mod.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": course.get("title", "Course"),
                            "description": f"Thronos Course: {course.get('title', '')}",
                        },
                        "unit_amount": int(Decimal(str(price_usd)) * 100),
                    },
                    "quantity": 1,
                }],
                mode="payment",
                success_url=domain + f"/courses/{course_id}?purchase=success&session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=domain + f"/courses/{course_id}?purchase=cancel",
                metadata={
                    "type": "course_purchase",
                    "purchase_id": result["purchase_id"],
                    "earn_user_id": user["earn_user_id"],
                    "course_id": course_id,
                },
            )
            store.attach_stripe_ids(
                result["purchase_id"],
                checkout_session_id=session.id,
                payment_intent=session.get("payment_intent"),
            )
            return jsonify(
                ok=True,
                checkout_url=session.url,
                checkout_session_id=session.id,
                purchase_id=result["purchase_id"],
            )
        except Exception as exc:
            logger.error("Stripe checkout creation failed: %s", exc)
            return jsonify(ok=False, error="stripe_checkout_failed"), 502

    @app.post("/api/earn/courses/webhook")
    def earn_course_webhook():
        stripe_mod = get_stripe() if get_stripe else None
        if not stripe_mod:
            return jsonify(status="ignored"), 200

        payload = request.get_data(as_text=True)
        sig_header = request.headers.get("Stripe-Signature", "")
        webhook_secret = stripe_webhook_secret_fn() if stripe_webhook_secret_fn else ""

        if not webhook_secret:
            return jsonify(error="webhook_not_configured"), 503

        try:
            event = stripe_mod.Webhook.construct_event(
                payload, sig_header, webhook_secret,
            )
        except ValueError:
            return jsonify(error="invalid_payload"), 400
        except Exception:
            return jsonify(error="invalid_signature"), 400

        event_id = event.get("id", "")
        event_type = event.get("type", "")
        payload_hash = hashlib.sha256(payload.encode()).hexdigest()

        obj = event.get("data", {}).get("object", {})
        metadata = obj.get("metadata", {})

        if metadata.get("type") != "course_purchase":
            return jsonify(status="ignored"), 200

        result = None

        if event_type == "checkout.session.completed":
            result = store.handle_checkout_completed(
                event_id=event_id,
                checkout_session_id=obj.get("id", ""),
                payment_intent=obj.get("payment_intent"),
                amount_total_cents=obj.get("amount_total", 0),
                metadata=metadata,
                payload_hash=payload_hash,
            )
            if result and not result.get("idempotent"):
                _post_access_grant(result)

        elif event_type == "payment_intent.payment_failed":
            pi = obj.get("id", "")
            result = store.handle_payment_failed(
                event_id=event_id,
                payment_intent=pi,
                payload_hash=payload_hash,
            )

        elif event_type == "charge.refunded":
            pi = obj.get("payment_intent", "")
            result = store.handle_refund(
                event_id=event_id,
                payment_intent=pi,
                payload_hash=payload_hash,
            )
            if result and not result.get("idempotent"):
                _post_refund(result)

        elif event_type == "charge.dispute.created":
            charge = obj
            pi = charge.get("payment_intent", "")
            result = store.handle_dispute(
                event_id=event_id,
                payment_intent=pi,
                payload_hash=payload_hash,
            )

        elif event_type == "charge.dispute.closed":
            charge = obj.get("charge", obj)
            pi = (
                obj.get("payment_intent")
                or (charge.get("payment_intent") if isinstance(charge, dict) else "")
                or ""
            )
            status = obj.get("status", "")
            if status == "won":
                result = store.handle_dispute_won(
                    event_id=event_id,
                    payment_intent=pi,
                    payload_hash=payload_hash,
                )
            else:
                result = store.handle_chargeback(
                    event_id=event_id,
                    payment_intent=pi,
                    payload_hash=payload_hash,
                )
                if result and not result.get("idempotent"):
                    _post_refund(result)

        return jsonify(status="ok", result=result), 200

    def _post_access_grant(result: dict) -> None:
        earn_store = get_earn_store() if get_earn_store else None
        if not earn_store:
            return
        thc_usd = result.get("thc_reward_usd", "0")
        try:
            thc_amount = float(thc_usd)
        except (TypeError, ValueError):
            thc_amount = 0.0
        if thc_amount > 0:
            try:
                entry, created = earn_store.record_thc_credit(
                    result["earn_user_id"],
                    "course_purchase",
                    result["purchase_id"],
                    thc_amount,
                    note=f"course:{result['course_id']}",
                )
                if created:
                    store.create_thc_reward(
                        purchase_id=result["purchase_id"],
                        earn_user_id=result["earn_user_id"],
                        course_id=result["course_id"],
                        thc_entry_id=entry.get("entry_id"),
                    )
            except Exception as exc:
                logger.warning("THC reward creation failed: %s", exc)

    def _post_refund(result: dict) -> None:
        earn_store = get_earn_store() if get_earn_store else None
        if not earn_store:
            return
        purchase_id = result.get("purchase_id", "")
        with store._tx() as con:
            reward = con.execute(
                "SELECT thc_entry_id FROM course_thc_rewards WHERE purchase_id = ?",
                (purchase_id,),
            ).fetchone()
        if reward and reward["thc_entry_id"]:
            try:
                earn_store.transition_thc(reward["thc_entry_id"], "reversed")
            except Exception as exc:
                logger.warning("THC reversal failed: %s", exc)

    @app.get("/api/earn/courses/access")
    def earn_course_access():
        user = _current_earn_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        course_id = request.args.get("course_id", "").strip()
        if not course_id:
            return jsonify(ok=False, error="missing_course_id"), 400
        has = store.has_access(user["earn_user_id"], course_id)
        return jsonify(ok=True, has_access=has, course_id=course_id)

    @app.get("/api/earn/courses/purchases")
    def earn_course_purchases():
        user = _current_earn_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        purchases = store.list_purchases(user["earn_user_id"])
        return jsonify(ok=True, purchases=purchases)
