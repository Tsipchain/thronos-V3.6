"""
Thronos Train-to-Earn — Fitness Reward Service

Users earn THC by completing verified fitness activities:
  - Gym check-ins (QR code scan at partner gyms)
  - Workout completions (duration-based)
  - Training milestones (streaks, personal records)

Integrates with the Earn ledger as source "train2earn".
No wallet required. No auto-mint. No payout logic here.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_THC_SCALE = Decimal("0.000001")
_CHECKIN_REWARD = Decimal(os.getenv("T2E_CHECKIN_REWARD_THC", "0.50"))
_WORKOUT_REWARD = Decimal(os.getenv("T2E_WORKOUT_REWARD_THC", "1.00"))
_MILESTONE_REWARD = Decimal(os.getenv("T2E_MILESTONE_REWARD_THC", "5.00"))
_DAILY_CAP = int(os.getenv("T2E_DAILY_CAP", "3"))
_WEEKLY_CAP = int(os.getenv("T2E_WEEKLY_CAP", "15"))

# Subscription and offer metadata deliberately stay outside the Earn/THC
# ledger.  A payment provider may reconcile a subscription later, but this
# service never accepts a browser claim as proof of payment.
T2E_PLAN_CATALOG = {
    "gym_basic": {
        "monthly_eur": Decimal("1.00"),
        "includes_ad_package": True,
        "description": "Gym membership, tenant dashboard and Train2Earn offers",
    },
}


class T2EError(Exception):
    pass


class TrainToEarnStore:
    def __init__(self, db_path: str | Path | None = None):
        self._db_path = str(
            db_path or os.getenv("T2E_DB_PATH", "data/train_to_earn.db")
        )
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._identity_key = (
            os.getenv("EARN_IDENTITY_SECRET", "t2e-dev-key-change-me")
            .encode("utf-8")
        )
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self._db_path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        return con

    @contextmanager
    def _tx(self):
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _init_schema(self):
        con = self._connect()
        try:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS t2e_gyms (
                    gym_id          TEXT PRIMARY KEY,
                    name            TEXT NOT NULL,
                    address         TEXT,
                    city            TEXT,
                    country         TEXT DEFAULT 'GR',
                    api_key_hash    TEXT NOT NULL,
                    checkin_method  TEXT NOT NULL DEFAULT 'qr',
                    reward_thc      TEXT,
                    is_active       INTEGER NOT NULL DEFAULT 1,
                    created_at      INTEGER NOT NULL,
                    updated_at      INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS t2e_memberships (
                    membership_id   TEXT PRIMARY KEY,
                    earn_user_id    TEXT NOT NULL,
                    gym_id          TEXT NOT NULL
                        REFERENCES t2e_gyms(gym_id),
                    member_code     TEXT NOT NULL,
                    is_active       INTEGER NOT NULL DEFAULT 1,
                    linked_at       INTEGER NOT NULL,
                    UNIQUE (earn_user_id, gym_id)
                );

                CREATE INDEX IF NOT EXISTS idx_t2e_memberships_user
                    ON t2e_memberships(earn_user_id);

                CREATE TABLE IF NOT EXISTS t2e_activities (
                    activity_id     TEXT PRIMARY KEY,
                    earn_user_id    TEXT NOT NULL,
                    gym_id          TEXT,
                    activity_type   TEXT NOT NULL,
                    duration_min    INTEGER,
                    reward_thc      TEXT NOT NULL,
                    thc_entry_id    TEXT,
                    verified        INTEGER NOT NULL DEFAULT 0,
                    created_at      INTEGER NOT NULL,
                    payload         TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_t2e_activities_user
                    ON t2e_activities(earn_user_id);
                CREATE INDEX IF NOT EXISTS idx_t2e_activities_date
                    ON t2e_activities(earn_user_id, created_at);

                CREATE TABLE IF NOT EXISTS t2e_subscriptions (
                    subscription_id TEXT PRIMARY KEY,
                    gym_id          TEXT NOT NULL REFERENCES t2e_gyms(gym_id),
                    plan_code       TEXT NOT NULL,
                    status          TEXT NOT NULL,
                    provider        TEXT NOT NULL,
                    provider_ref    TEXT NOT NULL,
                    amount_eur      TEXT NOT NULL,
                    period_start    INTEGER NOT NULL,
                    period_end      INTEGER NOT NULL,
                    created_at      INTEGER NOT NULL,
                    updated_at      INTEGER NOT NULL,
                    UNIQUE (provider, provider_ref)
                );

                CREATE INDEX IF NOT EXISTS idx_t2e_subscriptions_gym
                    ON t2e_subscriptions(gym_id, status, period_end);

                CREATE TABLE IF NOT EXISTS t2e_offers (
                    offer_id        TEXT PRIMARY KEY,
                    gym_id          TEXT NOT NULL REFERENCES t2e_gyms(gym_id),
                    offer_code      TEXT NOT NULL,
                    title           TEXT NOT NULL,
                    description     TEXT NOT NULL DEFAULT '',
                    status          TEXT NOT NULL DEFAULT 'draft',
                    created_at      INTEGER NOT NULL,
                    updated_at      INTEGER NOT NULL,
                    UNIQUE (gym_id, offer_code)
                );

                CREATE INDEX IF NOT EXISTS idx_t2e_offers_gym
                    ON t2e_offers(gym_id, status);

                CREATE TABLE IF NOT EXISTS t2e_challenges (
                    challenge_id     TEXT PRIMARY KEY,
                    gym_id           TEXT NOT NULL REFERENCES t2e_gyms(gym_id),
                    challenge_code   TEXT NOT NULL,
                    title            TEXT NOT NULL,
                    description      TEXT NOT NULL DEFAULT '',
                    target_value     TEXT NOT NULL,
                    unit             TEXT NOT NULL,
                    reward_t2e       TEXT NOT NULL,
                    status           TEXT NOT NULL DEFAULT 'draft',
                    starts_at        INTEGER,
                    ends_at          INTEGER,
                    created_at       INTEGER NOT NULL,
                    updated_at       INTEGER NOT NULL,
                    UNIQUE (gym_id, challenge_code)
                );

                CREATE INDEX IF NOT EXISTS idx_t2e_challenges_gym
                    ON t2e_challenges(gym_id, status, starts_at, ends_at);

                CREATE TABLE IF NOT EXISTS t2e_challenge_progress (
                    progress_id      TEXT PRIMARY KEY,
                    challenge_id     TEXT NOT NULL REFERENCES t2e_challenges(challenge_id),
                    earn_user_id     TEXT NOT NULL,
                    current_value    TEXT NOT NULL DEFAULT '0',
                    status           TEXT NOT NULL DEFAULT 'enrolled',
                    reward_status    TEXT NOT NULL DEFAULT 'not_eligible',
                    completed_at     INTEGER,
                    created_at       INTEGER NOT NULL,
                    updated_at       INTEGER NOT NULL,
                    UNIQUE (challenge_id, earn_user_id)
                );

                CREATE INDEX IF NOT EXISTS idx_t2e_progress_user
                    ON t2e_challenge_progress(earn_user_id, status);

                CREATE TABLE IF NOT EXISTS t2e_streaks (
                    earn_user_id    TEXT PRIMARY KEY,
                    current_streak  INTEGER NOT NULL DEFAULT 0,
                    longest_streak  INTEGER NOT NULL DEFAULT 0,
                    last_activity   INTEGER,
                    total_activities INTEGER NOT NULL DEFAULT 0,
                    total_thc_earned TEXT NOT NULL DEFAULT '0.00',
                    updated_at      INTEGER NOT NULL
                );
            """)
        finally:
            con.close()

    # ── Gym management ───────────────────────────────────────────────────

    def register_gym(
        self, *, name: str, address: str = "", city: str = "",
        country: str = "GR", checkin_method: str = "qr",
        reward_thc: str | None = None,
    ) -> tuple[dict[str, Any], str]:
        if not name or len(name) > 200:
            raise T2EError("invalid_gym_name")
        if checkin_method not in ("qr", "nfc", "code", "api"):
            raise T2EError("invalid_checkin_method")
        gym_id = "gym_" + secrets.token_urlsafe(12)
        api_key = "t2e_" + secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        now = int(time.time())
        with self._tx() as con:
            con.execute(
                """INSERT INTO t2e_gyms
                   (gym_id, name, address, city, country, api_key_hash,
                    checkin_method, reward_thc, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (gym_id, name, address, city, country, key_hash,
                 checkin_method, reward_thc, now, now),
            )
            gym = dict(con.execute(
                "SELECT * FROM t2e_gyms WHERE gym_id = ?", (gym_id,),
            ).fetchone())
        return gym, api_key

    def verify_gym_key(self, api_key: str) -> dict[str, Any] | None:
        if not api_key:
            return None
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        con = self._connect()
        try:
            row = con.execute(
                "SELECT * FROM t2e_gyms WHERE api_key_hash = ? AND is_active = 1",
                (key_hash,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            con.close()

    def list_gyms(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        con = self._connect()
        try:
            q = "SELECT gym_id, name, address, city, country, checkin_method, is_active FROM t2e_gyms"
            if active_only:
                q += " WHERE is_active = 1"
            q += " ORDER BY name"
            return [dict(r) for r in con.execute(q).fetchall()]
        finally:
            con.close()

    # ── Tenant subscription and offer catalog ───────────────────────────

    @staticmethod
    def plan_catalog() -> list[dict[str, Any]]:
        """Return public plan metadata; no payment state is inferred here."""
        return [
            {"code": code, **{k: (str(v) if isinstance(v, Decimal) else v)
                               for k, v in plan.items()}}
            for code, plan in T2E_PLAN_CATALOG.items()
        ]

    def reconcile_subscription(
        self, *, gym_id: str, plan_code: str, provider: str,
        provider_ref: str, amount_eur: str, period_start: int,
        period_end: int, status: str = "active",
    ) -> dict[str, Any]:
        """Record a provider-confirmed subscription idempotently.

        This is an accounting boundary only.  It requires a provider
        reference and must be called by a trusted reconciliation process;
        there is intentionally no public payment endpoint in this module.
        """
        if plan_code not in T2E_PLAN_CATALOG:
            raise T2EError("unknown_plan")
        if not provider or not provider_ref:
            raise T2EError("provider_reference_required")
        if status not in ("active", "past_due", "cancelled", "expired"):
            raise T2EError("invalid_subscription_status")
        try:
            amount = Decimal(str(amount_eur)).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        except Exception as exc:
            raise T2EError("invalid_subscription_amount") from exc
        if amount <= 0 or period_end <= period_start:
            raise T2EError("invalid_subscription_period")
        now = int(time.time())
        subscription_id = "sub_" + secrets.token_urlsafe(12)
        with self._tx() as con:
            gym = con.execute(
                "SELECT gym_id FROM t2e_gyms WHERE gym_id = ? AND is_active = 1",
                (gym_id,),
            ).fetchone()
            if not gym:
                raise T2EError("gym_not_found")
            existing = con.execute(
                "SELECT * FROM t2e_subscriptions WHERE provider = ? AND provider_ref = ?",
                (provider, provider_ref),
            ).fetchone()
            if existing:
                if existing["gym_id"] != gym_id or existing["plan_code"] != plan_code:
                    raise T2EError("provider_reference_conflict")
                con.execute(
                    """UPDATE t2e_subscriptions SET status=?, amount_eur=?,
                       period_start=?, period_end=?, updated_at=?
                       WHERE subscription_id=?""",
                    (status, str(amount), period_start, period_end, now,
                     existing["subscription_id"]),
                )
                row = con.execute(
                    "SELECT * FROM t2e_subscriptions WHERE subscription_id = ?",
                    (existing["subscription_id"],),
                ).fetchone()
                return dict(row)
            con.execute(
                """INSERT INTO t2e_subscriptions
                   (subscription_id, gym_id, plan_code, status, provider,
                    provider_ref, amount_eur, period_start, period_end,
                    created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (subscription_id, gym_id, plan_code, status, provider,
                 provider_ref, str(amount), period_start, period_end, now, now),
            )
            return dict(con.execute(
                "SELECT * FROM t2e_subscriptions WHERE subscription_id = ?",
                (subscription_id,),
            ).fetchone())

    def get_subscription(self, gym_id: str) -> dict[str, Any] | None:
        con = self._connect()
        try:
            row = con.execute(
                """SELECT * FROM t2e_subscriptions WHERE gym_id = ?
                   ORDER BY period_end DESC LIMIT 1""", (gym_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            con.close()

    def create_offer(
        self, *, gym_id: str, offer_code: str, title: str,
        description: str = "", status: str = "draft",
    ) -> dict[str, Any]:
        if not offer_code or not title or status not in ("draft", "active", "paused"):
            raise T2EError("invalid_offer")
        now = int(time.time())
        offer_id = "offer_" + secrets.token_urlsafe(12)
        with self._tx() as con:
            gym = con.execute(
                "SELECT gym_id FROM t2e_gyms WHERE gym_id = ? AND is_active = 1",
                (gym_id,),
            ).fetchone()
            if not gym:
                raise T2EError("gym_not_found")
            try:
                con.execute(
                    """INSERT INTO t2e_offers
                       (offer_id, gym_id, offer_code, title, description,
                        status, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (offer_id, gym_id, offer_code, title, description,
                     status, now, now),
                )
            except sqlite3.IntegrityError as exc:
                raise T2EError("offer_already_exists") from exc
            return dict(con.execute(
                "SELECT * FROM t2e_offers WHERE offer_id = ?", (offer_id,),
            ).fetchone())

    def list_offers(self, gym_id: str, *, active_only: bool = True) -> list[dict[str, Any]]:
        con = self._connect()
        try:
            query = "SELECT * FROM t2e_offers WHERE gym_id = ?"
            params: list[Any] = [gym_id]
            if active_only:
                query += " AND status = 'active'"
            query += " ORDER BY created_at DESC"
            return [dict(row) for row in con.execute(query, params).fetchall()]
        finally:
            con.close()

    # ── Challenges and pseudonymous leaderboard ─────────────────────────

    def create_challenge(
        self, *, gym_id: str, challenge_code: str, title: str,
        description: str, target_value: str, unit: str, reward_t2e: str,
        status: str = "draft", starts_at: int | None = None,
        ends_at: int | None = None,
    ) -> dict[str, Any]:
        if not challenge_code or not title or not unit:
            raise T2EError("invalid_challenge")
        if status not in ("draft", "active", "paused", "ended"):
            raise T2EError("invalid_challenge_status")
        try:
            target = Decimal(str(target_value))
            reward = Decimal(str(reward_t2e))
        except Exception as exc:
            raise T2EError("invalid_challenge_numbers") from exc
        if target <= 0 or reward < 0 or (ends_at and starts_at and ends_at <= starts_at):
            raise T2EError("invalid_challenge_numbers")
        now = int(time.time())
        challenge_id = "challenge_" + secrets.token_urlsafe(12)
        with self._tx() as con:
            gym = con.execute(
                "SELECT gym_id FROM t2e_gyms WHERE gym_id = ? AND is_active = 1",
                (gym_id,),
            ).fetchone()
            if not gym:
                raise T2EError("gym_not_found")
            try:
                con.execute(
                    """INSERT INTO t2e_challenges
                       (challenge_id, gym_id, challenge_code, title, description,
                        target_value, unit, reward_t2e, status, starts_at,
                        ends_at, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (challenge_id, gym_id, challenge_code, title, description,
                     str(target), unit, str(reward), status, starts_at, ends_at,
                     now, now),
                )
            except sqlite3.IntegrityError as exc:
                raise T2EError("challenge_already_exists") from exc
            return dict(con.execute(
                "SELECT * FROM t2e_challenges WHERE challenge_id = ?",
                (challenge_id,),
            ).fetchone())

    def list_challenges(self, gym_id: str, *, active_only: bool = True) -> list[dict[str, Any]]:
        con = self._connect()
        try:
            query = "SELECT * FROM t2e_challenges WHERE gym_id = ?"
            params: list[Any] = [gym_id]
            if active_only:
                query += " AND status = 'active'"
            query += " ORDER BY created_at DESC"
            return [dict(row) for row in con.execute(query, params).fetchall()]
        finally:
            con.close()

    def enroll_challenge(self, *, earn_user_id: str, challenge_id: str) -> dict[str, Any]:
        if not earn_user_id or not challenge_id:
            raise T2EError("missing_challenge_fields")
        now = int(time.time())
        progress_id = "progress_" + secrets.token_urlsafe(12)
        with self._tx() as con:
            challenge = con.execute(
                "SELECT * FROM t2e_challenges WHERE challenge_id = ? AND status = 'active'",
                (challenge_id,),
            ).fetchone()
            if not challenge:
                raise T2EError("challenge_not_found")
            existing = con.execute(
                "SELECT * FROM t2e_challenge_progress WHERE challenge_id = ? AND earn_user_id = ?",
                (challenge_id, earn_user_id),
            ).fetchone()
            if existing:
                return dict(existing)
            con.execute(
                """INSERT INTO t2e_challenge_progress
                   (progress_id, challenge_id, earn_user_id, current_value,
                    status, reward_status, created_at, updated_at)
                   VALUES (?,?,?,'0','enrolled','not_eligible',?,?)""",
                (progress_id, challenge_id, earn_user_id, now, now),
            )
            return dict(con.execute(
                "SELECT * FROM t2e_challenge_progress WHERE progress_id = ?",
                (progress_id,),
            ).fetchone())

    def record_challenge_progress(
        self, *, earn_user_id: str, challenge_id: str, value: str,
    ) -> dict[str, Any]:
        try:
            increment = Decimal(str(value))
        except Exception as exc:
            raise T2EError("invalid_progress_value") from exc
        if increment <= 0:
            raise T2EError("invalid_progress_value")
        now = int(time.time())
        with self._tx() as con:
            challenge = con.execute(
                "SELECT * FROM t2e_challenges WHERE challenge_id = ? AND status = 'active'",
                (challenge_id,),
            ).fetchone()
            if not challenge:
                raise T2EError("challenge_not_found")
            progress = con.execute(
                "SELECT * FROM t2e_challenge_progress WHERE challenge_id = ? AND earn_user_id = ?",
                (challenge_id, earn_user_id),
            ).fetchone()
            if not progress:
                raise T2EError("challenge_not_enrolled")
            if progress["status"] == "completed":
                return dict(progress)
            target = Decimal(challenge["target_value"])
            current = min(target, Decimal(progress["current_value"]) + increment)
            completed = current >= target
            status = "completed" if completed else "in_progress"
            reward_status = "eligible" if completed else "not_eligible"
            completed_at = now if completed else None
            con.execute(
                """UPDATE t2e_challenge_progress
                   SET current_value=?, status=?, reward_status=?,
                       completed_at=?, updated_at=? WHERE progress_id=?""",
                (str(current), status, reward_status, completed_at, now,
                 progress["progress_id"]),
            )
            return dict(con.execute(
                "SELECT * FROM t2e_challenge_progress WHERE progress_id = ?",
                (progress["progress_id"],),
            ).fetchone())

    def get_leaderboard(self, gym_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        con = self._connect()
        try:
            rows = con.execute(
                """SELECT p.earn_user_id, c.reward_t2e
                   FROM t2e_challenge_progress p
                   JOIN t2e_challenges c ON c.challenge_id = p.challenge_id
                   WHERE c.gym_id = ? AND p.status = 'completed'""",
                (gym_id,),
            ).fetchall()
            totals: dict[str, dict[str, Any]] = {}
            for row in rows:
                item = totals.setdefault(row["earn_user_id"], {
                    "completed_challenges": 0, "total_reward": Decimal("0"),
                })
                item["completed_challenges"] += 1
                item["total_reward"] += Decimal(row["reward_t2e"])
            ranked = sorted(
                totals.items(),
                key=lambda pair: (pair[1]["completed_challenges"], pair[1]["total_reward"]),
                reverse=True,
            )[:limit]
            result = []
            for position, (earn_user_id, item) in enumerate(ranked, start=1):
                digest = hmac.new(
                    self._identity_key, earn_user_id.encode("utf-8"), hashlib.sha256,
                ).hexdigest()[:10]
                result.append({
                    "rank": position,
                    "display_ref": f"athlete_{digest}",
                    "completed_challenges": item["completed_challenges"],
                    "total_reward_t2e": str(item["total_reward"].quantize(_THC_SCALE)),
                })
            return result
        finally:
            con.close()

    # ── Membership linking ───────────────────────────────────────────────

    def link_membership(
        self, *, earn_user_id: str, gym_id: str, member_code: str,
    ) -> dict[str, Any]:
        if not earn_user_id or not gym_id or not member_code:
            raise T2EError("missing_membership_fields")
        if len(member_code) > 100:
            raise T2EError("invalid_member_code")
        membership_id = "mem_" + secrets.token_urlsafe(12)
        now = int(time.time())
        with self._tx() as con:
            gym = con.execute(
                "SELECT 1 FROM t2e_gyms WHERE gym_id = ? AND is_active = 1",
                (gym_id,),
            ).fetchone()
            if not gym:
                raise T2EError("gym_not_found")
            existing = con.execute(
                "SELECT membership_id FROM t2e_memberships WHERE earn_user_id = ? AND gym_id = ?",
                (earn_user_id, gym_id),
            ).fetchone()
            if existing:
                raise T2EError("membership_already_linked")
            con.execute(
                """INSERT INTO t2e_memberships
                   (membership_id, earn_user_id, gym_id, member_code, linked_at)
                   VALUES (?,?,?,?,?)""",
                (membership_id, earn_user_id, gym_id, member_code, now),
            )
            return dict(con.execute(
                "SELECT * FROM t2e_memberships WHERE membership_id = ?",
                (membership_id,),
            ).fetchone())

    def get_memberships(self, earn_user_id: str) -> list[dict[str, Any]]:
        con = self._connect()
        try:
            rows = con.execute(
                """SELECT m.*, g.name as gym_name, g.checkin_method
                   FROM t2e_memberships m JOIN t2e_gyms g ON m.gym_id = g.gym_id
                   WHERE m.earn_user_id = ? AND m.is_active = 1""",
                (earn_user_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            con.close()

    # ── Activity recording ───────────────────────────────────────────────

    def _daily_count(self, con, earn_user_id: str) -> int:
        day_start = int(time.time()) - (int(time.time()) % 86400)
        row = con.execute(
            "SELECT COUNT(*) as cnt FROM t2e_activities WHERE earn_user_id = ? AND created_at >= ?",
            (earn_user_id, day_start),
        ).fetchone()
        return row["cnt"] if row else 0

    def _weekly_count(self, con, earn_user_id: str) -> int:
        week_start = int(time.time()) - (int(time.time()) % 604800)
        row = con.execute(
            "SELECT COUNT(*) as cnt FROM t2e_activities WHERE earn_user_id = ? AND created_at >= ?",
            (earn_user_id, week_start),
        ).fetchone()
        return row["cnt"] if row else 0

    def record_checkin(
        self, *, earn_user_id: str, gym_id: str, duration_min: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not earn_user_id or not gym_id:
            raise T2EError("missing_checkin_fields")
        now = int(time.time())
        with self._tx() as con:
            membership = con.execute(
                "SELECT * FROM t2e_memberships WHERE earn_user_id = ? AND gym_id = ? AND is_active = 1",
                (earn_user_id, gym_id),
            ).fetchone()
            if not membership:
                raise T2EError("no_active_membership")
            if self._daily_count(con, earn_user_id) >= _DAILY_CAP:
                raise T2EError("daily_cap_reached")
            if self._weekly_count(con, earn_user_id) >= _WEEKLY_CAP:
                raise T2EError("weekly_cap_reached")
            gym = con.execute(
                "SELECT * FROM t2e_gyms WHERE gym_id = ?", (gym_id,),
            ).fetchone()
            reward = Decimal(gym["reward_thc"]) if gym and gym["reward_thc"] else _CHECKIN_REWARD
            reward = reward.quantize(_THC_SCALE, rounding=ROUND_DOWN)
            activity_id = "act_" + secrets.token_urlsafe(18)
            payload_json = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"))
            con.execute(
                """INSERT INTO t2e_activities
                   (activity_id, earn_user_id, gym_id, activity_type, duration_min,
                    reward_thc, verified, created_at, payload)
                   VALUES (?,?,?,?,?,?,1,?,?)""",
                (activity_id, earn_user_id, gym_id, "checkin", duration_min,
                 str(reward), now, payload_json),
            )
            self._update_streak(con, earn_user_id, reward, now)
            return {
                "activity_id": activity_id,
                "reward_thc": str(reward),
                "activity_type": "checkin",
            }

    def record_workout(
        self, *, earn_user_id: str, duration_min: int,
        workout_type: str = "general", gym_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not earn_user_id or not duration_min or duration_min < 15:
            raise T2EError("invalid_workout")
        now = int(time.time())
        with self._tx() as con:
            if self._daily_count(con, earn_user_id) >= _DAILY_CAP:
                raise T2EError("daily_cap_reached")
            if self._weekly_count(con, earn_user_id) >= _WEEKLY_CAP:
                raise T2EError("weekly_cap_reached")
            reward = _WORKOUT_REWARD
            if duration_min >= 60:
                reward = reward * 2
            reward = reward.quantize(_THC_SCALE, rounding=ROUND_DOWN)
            activity_id = "act_" + secrets.token_urlsafe(18)
            payload_json = json.dumps(
                {**(payload or {}), "workout_type": workout_type},
                sort_keys=True, separators=(",", ":"),
            )
            con.execute(
                """INSERT INTO t2e_activities
                   (activity_id, earn_user_id, gym_id, activity_type, duration_min,
                    reward_thc, verified, created_at, payload)
                   VALUES (?,?,?,?,?,?,0,?,?)""",
                (activity_id, earn_user_id, gym_id, "workout", duration_min,
                 str(reward), now, payload_json),
            )
            self._update_streak(con, earn_user_id, reward, now)
            return {
                "activity_id": activity_id,
                "reward_thc": str(reward),
                "activity_type": "workout",
                "duration_min": duration_min,
            }

    def _update_streak(self, con, earn_user_id: str, reward: Decimal, now: int):
        existing = con.execute(
            "SELECT * FROM t2e_streaks WHERE earn_user_id = ?",
            (earn_user_id,),
        ).fetchone()
        day_start = now - (now % 86400)
        if existing:
            last = existing["last_activity"] or 0
            last_day = last - (last % 86400)
            if last_day == day_start:
                streak = existing["current_streak"]
            elif last_day == day_start - 86400:
                streak = existing["current_streak"] + 1
            else:
                streak = 1
            longest = max(streak, existing["longest_streak"])
            total = existing["total_activities"] + 1
            earned = Decimal(existing["total_thc_earned"]) + reward
            con.execute(
                """UPDATE t2e_streaks
                   SET current_streak = ?, longest_streak = ?,
                       last_activity = ?, total_activities = ?,
                       total_thc_earned = ?, updated_at = ?
                   WHERE earn_user_id = ?""",
                (streak, longest, now, total, str(earned), now, earn_user_id),
            )
        else:
            con.execute(
                """INSERT INTO t2e_streaks
                   (earn_user_id, current_streak, longest_streak,
                    last_activity, total_activities, total_thc_earned, updated_at)
                   VALUES (?,1,1,?,1,?,?)""",
                (earn_user_id, now, str(reward), now),
            )

    # ── Stats ────────────────────────────────────────────────────────────

    def get_stats(self, earn_user_id: str) -> dict[str, Any]:
        con = self._connect()
        try:
            streak = con.execute(
                "SELECT * FROM t2e_streaks WHERE earn_user_id = ?",
                (earn_user_id,),
            ).fetchone()
            today_count = self._daily_count(con, earn_user_id)
            week_count = self._weekly_count(con, earn_user_id)
            return {
                "current_streak": streak["current_streak"] if streak else 0,
                "longest_streak": streak["longest_streak"] if streak else 0,
                "total_activities": streak["total_activities"] if streak else 0,
                "total_thc_earned": streak["total_thc_earned"] if streak else "0.00",
                "today_count": today_count,
                "today_remaining": max(0, _DAILY_CAP - today_count),
                "week_count": week_count,
                "week_remaining": max(0, _WEEKLY_CAP - week_count),
            }
        finally:
            con.close()

    def get_history(
        self, earn_user_id: str, *, limit: int = 50,
    ) -> list[dict[str, Any]]:
        con = self._connect()
        try:
            rows = con.execute(
                """SELECT a.*, g.name as gym_name
                   FROM t2e_activities a
                   LEFT JOIN t2e_gyms g ON a.gym_id = g.gym_id
                   WHERE a.earn_user_id = ?
                   ORDER BY a.created_at DESC LIMIT ?""",
                (earn_user_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            con.close()


# ── Flask route registration ─────────────────────────────────────────────

def register_t2e_routes(app, earn_store):
    """Mount Train-to-Earn API routes on the Flask app."""
    from flask import request, jsonify

    t2e_store = TrainToEarnStore()

    def _gym_from_key():
        key = (request.headers.get("X-Gym-Key") or "").strip()
        if not key:
            return None
        return t2e_store.verify_gym_key(key)

    def _earn_user():
        auth = (request.headers.get("Authorization") or "").strip()
        if auth.startswith("Bearer "):
            token = auth[7:]
        else:
            token = request.cookies.get("earn_session")
        if not token:
            return None
        session = earn_store.get_session(token)
        if not session:
            return None
        return session

    if os.getenv("T2E_ENABLED", "0") != "1":
        return

    @app.get("/api/earn/t2e/gyms")
    def t2e_list_gyms():
        user = _earn_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        gyms = t2e_store.list_gyms()
        memberships = t2e_store.get_memberships(user["earn_user_id"])
        linked_ids = {m["gym_id"] for m in memberships}
        return jsonify(ok=True, gyms=[
            {**g, "linked": g["gym_id"] in linked_ids} for g in gyms
        ])

    @app.post("/api/earn/t2e/link")
    def t2e_link_membership():
        user = _earn_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        data = request.get_json(silent=True) or {}
        try:
            membership = t2e_store.link_membership(
                earn_user_id=user["earn_user_id"],
                gym_id=str(data.get("gym_id") or "").strip(),
                member_code=str(data.get("member_code") or "").strip(),
            )
            return jsonify(ok=True, membership_id=membership["membership_id"])
        except T2EError as e:
            return jsonify(ok=False, error=str(e)), 400

    @app.post("/api/earn/t2e/checkin")
    def t2e_checkin():
        gym = _gym_from_key()
        if not gym:
            return jsonify(ok=False, error="invalid_gym_key"), 401
        data = request.get_json(silent=True) or {}
        member_code = str(data.get("member_code") or "").strip()
        if not member_code:
            return jsonify(ok=False, error="missing_member_code"), 400
        con = t2e_store._connect()
        try:
            membership = con.execute(
                "SELECT * FROM t2e_memberships WHERE gym_id = ? AND member_code = ? AND is_active = 1",
                (gym["gym_id"], member_code),
            ).fetchone()
        finally:
            con.close()
        if not membership:
            return jsonify(ok=False, error="unknown_member"), 404
        try:
            result = t2e_store.record_checkin(
                earn_user_id=membership["earn_user_id"],
                gym_id=gym["gym_id"],
                duration_min=data.get("duration_min"),
                payload={"source": "gym_api", "gym": gym["name"]},
            )
            return jsonify(ok=True, **result)
        except T2EError as e:
            return jsonify(ok=False, error=str(e)), 400

    @app.post("/api/earn/t2e/workout")
    def t2e_workout():
        user = _earn_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        data = request.get_json(silent=True) or {}
        try:
            result = t2e_store.record_workout(
                earn_user_id=user["earn_user_id"],
                duration_min=int(data.get("duration_min") or 0),
                workout_type=str(data.get("workout_type") or "general").strip(),
                gym_id=data.get("gym_id"),
                payload={"source": "self_report"},
            )
            return jsonify(ok=True, **result)
        except (T2EError, ValueError) as e:
            return jsonify(ok=False, error=str(e)), 400

    @app.get("/api/earn/t2e/stats")
    def t2e_stats():
        user = _earn_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        stats = t2e_store.get_stats(user["earn_user_id"])
        return jsonify(ok=True, **stats)

    @app.get("/api/earn/t2e/history")
    def t2e_history():
        user = _earn_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        history = t2e_store.get_history(user["earn_user_id"])
        return jsonify(ok=True, activities=history)

    @app.get("/api/earn/t2e/dashboard")
    def t2e_dashboard():
        """Return the authenticated athlete's tenant-scoped dashboard."""
        user = _earn_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        memberships = t2e_store.get_memberships(user["earn_user_id"])
        tenants = []
        for membership in memberships:
            gym_id = membership["gym_id"]
            tenants.append({
                "gym": {"gym_id": gym_id, "name": membership["gym_name"]},
                "challenges": t2e_store.list_challenges(gym_id),
                "leaderboard": t2e_store.get_leaderboard(gym_id),
                "stats": t2e_store.get_stats(user["earn_user_id"]),
            })
        return jsonify(ok=True, earn_user_id=user["earn_user_id"], tenants=tenants)

    @app.post("/api/earn/t2e/challenges/<challenge_id>/enroll")
    def t2e_enroll_challenge(challenge_id: str):
        user = _earn_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        try:
            progress = t2e_store.enroll_challenge(
                earn_user_id=user["earn_user_id"], challenge_id=challenge_id,
            )
            return jsonify(ok=True, progress=progress)
        except T2EError as e:
            return jsonify(ok=False, error=str(e)), 400

    @app.post("/api/earn/t2e/challenges/<challenge_id>/progress")
    def t2e_challenge_progress(challenge_id: str):
        """Accept progress only from a verified gym key, never from a browser."""
        gym = _gym_from_key()
        if not gym:
            return jsonify(ok=False, error="invalid_gym_key"), 401
        data = request.get_json(silent=True) or {}
        member_code = str(data.get("member_code") or "").strip()
        if not member_code:
            return jsonify(ok=False, error="missing_member_code"), 400
        con = t2e_store._connect()
        try:
            membership = con.execute(
                """SELECT earn_user_id FROM t2e_memberships
                   WHERE gym_id = ? AND member_code = ? AND is_active = 1""",
                (gym["gym_id"], member_code),
            ).fetchone()
        finally:
            con.close()
        if not membership:
            return jsonify(ok=False, error="unknown_member"), 404
        try:
            progress = t2e_store.record_challenge_progress(
                earn_user_id=membership["earn_user_id"], challenge_id=challenge_id,
                value=str(data.get("value") or ""),
            )
            return jsonify(ok=True, progress=progress)
        except T2EError as e:
            return jsonify(ok=False, error=str(e)), 400

    @app.get("/api/earn/t2e/leaderboard/<gym_id>")
    def t2e_leaderboard(gym_id: str):
        user = _earn_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        if not any(m["gym_id"] == gym_id for m in t2e_store.get_memberships(user["earn_user_id"])):
            return jsonify(ok=False, error="gym_membership_required"), 403
        return jsonify(ok=True, gym_id=gym_id, leaderboard=t2e_store.get_leaderboard(gym_id))

    @app.post("/api/earn/t2e/gym/register")
    def t2e_register_gym():
        admin_key = os.getenv("T2E_ADMIN_KEY", "").strip()
        if not admin_key or request.headers.get("X-Admin-Key") != admin_key:
            return jsonify(ok=False, error="unauthorized"), 401
        data = request.get_json(silent=True) or {}
        try:
            gym, api_key = t2e_store.register_gym(
                name=str(data.get("name") or "").strip(),
                address=str(data.get("address") or "").strip(),
                city=str(data.get("city") or "").strip(),
                country=str(data.get("country") or "GR").strip(),
                checkin_method=str(data.get("checkin_method") or "qr").strip(),
                reward_thc=data.get("reward_thc"),
            )
            return jsonify(ok=True, gym_id=gym["gym_id"], api_key=api_key)
        except T2EError as e:
            return jsonify(ok=False, error=str(e)), 400

    @app.post("/api/earn/t2e/gym/challenge")
    def t2e_create_challenge():
        admin_key = os.getenv("T2E_ADMIN_KEY", "").strip()
        if not admin_key or request.headers.get("X-Admin-Key") != admin_key:
            return jsonify(ok=False, error="unauthorized"), 401
        data = request.get_json(silent=True) or {}
        try:
            challenge = t2e_store.create_challenge(
                gym_id=str(data.get("gym_id") or "").strip(),
                challenge_code=str(data.get("challenge_code") or "").strip(),
                title=str(data.get("title") or "").strip(),
                description=str(data.get("description") or "").strip(),
                target_value=str(data.get("target_value") or ""),
                unit=str(data.get("unit") or "").strip(),
                reward_t2e=str(data.get("reward_t2e") or "0"),
                status=str(data.get("status") or "draft").strip(),
                starts_at=data.get("starts_at"), ends_at=data.get("ends_at"),
            )
            return jsonify(ok=True, challenge=challenge)
        except T2EError as e:
            return jsonify(ok=False, error=str(e)), 400
