"""
Thronos Earn — Account-First Beta

Email/password Earn Account with:
  - PBKDF2-SHA256 password hashing
  - Bearer-token sessions with rotation
  - Login rate limiting (5 attempts / 15 min, 30 min lockout)
  - Server-side CPX ext_user_id (HMAC from earn_user_id)
  - Dedicated THC reward ledger (pending → confirmed → payable → paid/reversed)
  - CPX receipt storage with idempotent postback handling
  - Balance excludes pending entries

No wallet required. No auto-mint. No BTC payout. No L2E/THR mixing.
"""
from __future__ import annotations

import hashlib
import ipaddress
import calendar
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP, ROUND_UP
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

_THC_SCALE = Decimal("0.000001")
_STAKING_FEE_BPS = 9  # Owner-approved 0.09% per stake/unstake, 2026-11-10.
_STAKING_FEE_POLICY = "earn-stake-fee-v1"
_STAKING_FEE_RESERVE = "pythia_thc_staking_fee_reserve"
_THC_STAKE_TERMS = {"flex": 0, "six_months": 6, "one_year": 12}
_THC_FLEX_ILLUSTRATIVE_APY_BPS = 300  # Model only; no rewards accrue or become payable here.


def _stake_unlock_at(staked_at: int, term: str) -> int | None:
    """Fixed terms mature on the same UTC clock time after calendar months."""
    if term not in _THC_STAKE_TERMS:
        raise EarnError("invalid_stake_term")
    months = _THC_STAKE_TERMS[term]
    if not months:
        return None
    start = datetime.fromtimestamp(staked_at, timezone.utc)
    year, month = divmod(start.year * 12 + start.month - 1 + months, 12)
    return int(start.replace(
        year=year, month=month + 1,
        day=min(start.day, calendar.monthrange(year, month + 1)[1]),
    ).timestamp())
# First authorized 30-day beta cycle: Athens midnight, end exclusive. Fixed
# boundaries survive deploys/restarts; a new cycle requires a separate release.
_LEADERBOARD_START = int(datetime.fromisoformat("2026-11-05T00:00:00+02:00").timestamp())
_LEADERBOARD_END = _LEADERBOARD_START + 30 * 86400
_LEADERBOARD_CAMPAIGN = "earn-beta-2026-11-05"
_EARN_HOLD_SECONDS = 7 * 86400
_EARN_HOLD_POLICY = "earn-seven-day-v1"
_VERIFIED_PROVIDER_RECEIPT_SQL = """(
                       (l.source IN ('cpx_survey', 'cpx') AND EXISTS (
                         SELECT 1 FROM cpx_receipts r WHERE r.trans_id=l.source_ref
                         AND r.earn_user_id=l.earn_user_id AND r.thc_entry_id=l.entry_id AND r.status=1))
                       OR (l.source='bitcotasks' AND EXISTS (
                         SELECT 1 FROM bitcotasks_receipts r WHERE r.trans_id=l.source_ref
                         AND r.earn_user_id=l.earn_user_id AND r.thc_entry_id=l.entry_id AND r.status=1))
                       OR (l.source='pure' AND EXISTS (
                         SELECT 1 FROM pure_receipts r WHERE r.trans_id=l.source_ref
                         AND r.earn_user_id=l.earn_user_id AND r.thc_entry_id=l.entry_id AND r.status=1))
                       OR (l.source='timewall' AND EXISTS (
                         SELECT 1 FROM timewall_receipts r WHERE r.event_id=l.source_ref
                         AND r.earn_user_id=l.earn_user_id AND r.thc_entry_id=l.entry_id))
                     )"""
_CLEARANCE_DAYS = int(os.getenv("EARN_CLEARANCE_DAYS", "7"))

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
_MIN_PASSWORD_LEN = 8
_MAX_PASSWORD_LEN = 128
_MAX_EMAIL_LEN = 254
_PBKDF2_ITERATIONS = 260_000
# Earn is an account product, not a one-page form.  The durable server-side
# session lets the same account move between /earn and /courses until it
# explicitly signs out.  Tokens remain revocable because only their hashes
# are stored in SQLite.
_SESSION_TTL = max(900, min(int(os.getenv("EARN_SESSION_TTL_SECONDS", str(30 * 24 * 60 * 60))), 90 * 24 * 60 * 60))
_SESSION_COOKIE = "thr_earn_session"
_RATE_WINDOW = 900
_RATE_MAX_ATTEMPTS = 5
_RATE_LOCKOUT = 1800
_WALLET_CHALLENGE_TTL = 300
_ESCROW_INTENT_TTL = 300

_THC_TRANSITIONS = {
    "pending":   {"confirmed", "reversed"},
    "confirmed": {"payable", "reversed"},
    "payable":   {"paid", "reversed"},
    "paid":      {"reversed"},
    "reversed":  set(),
}


class EarnError(ValueError):
    pass


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(32)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS,
    )
    return f"pbkdf2:sha256:{_PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        parts = stored.split("$")
        if len(parts) != 3:
            return False
        header, salt_hex, dk_hex = parts
        iterations = int(header.rsplit(":", 1)[1])
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(dk_hex)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations,
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _validate_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not email or len(email) > _MAX_EMAIL_LEN or not _EMAIL_RE.match(email):
        raise EarnError("invalid_email")
    return email


def _validate_password(password: str) -> str:
    if not password or len(password) < _MIN_PASSWORD_LEN:
        raise EarnError("password_too_short")
    if len(password) > _MAX_PASSWORD_LEN:
        raise EarnError("password_too_long")
    return password


class EarnAccountStore:
    """SQLite-backed account-first Earn store."""

    def __init__(self, db_path: str, identity_key: str, settlement_adapter=None):
        if not identity_key or identity_key == "CHANGE_ME":
            raise EarnError("earn_identity_key_not_configured")
        self.db_path = db_path
        self._identity_key = identity_key.encode("utf-8")
        self._settlement_adapter = settlement_adapter
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
        con.row_factory = sqlite3.Row
        try:
            con.executescript("""
                PRAGMA journal_mode = WAL;
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS earn_accounts (
                    earn_user_id    TEXT PRIMARY KEY,
                    email           TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash   TEXT NOT NULL,
                    email_verified  INTEGER NOT NULL DEFAULT 0,
                    email_verified_at TEXT,
                    cpx_ext_user_id TEXT NOT NULL UNIQUE,
                    created_at      INTEGER NOT NULL,
                    updated_at      INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS earn_sessions (
                    token_hash      TEXT PRIMARY KEY,
                    earn_user_id    TEXT NOT NULL
                        REFERENCES earn_accounts(earn_user_id),
                    expires_at      INTEGER NOT NULL,
                    created_at      INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_earn_sessions_user
                    ON earn_sessions(earn_user_id);

                CREATE TABLE IF NOT EXISTS earn_login_attempts (
                    attempt_key     TEXT PRIMARY KEY,
                    attempts        INTEGER NOT NULL DEFAULT 0,
                    window_start    INTEGER NOT NULL,
                    locked_until    INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS thc_ledger (
                    entry_id        TEXT PRIMARY KEY,
                    earn_user_id    TEXT NOT NULL
                        REFERENCES earn_accounts(earn_user_id),
                    source          TEXT NOT NULL,
                    source_ref      TEXT NOT NULL,
                    amount          TEXT NOT NULL,
                    state           TEXT NOT NULL DEFAULT 'pending',
                    note            TEXT NOT NULL DEFAULT '',
                    settlement_ref  TEXT,
                    -- These fields describe only provider-originated reward
                    -- evidence.  They never calculate clearance locally.
                    provider_status TEXT,
                    received_at     INTEGER,
                    estimated_clearance_at INTEGER,
                    cleared_at      INTEGER,
                    reversal_reason TEXT,
                    created_at      INTEGER NOT NULL,
                    updated_at      INTEGER NOT NULL,
                    UNIQUE(source, source_ref)
                );

                CREATE INDEX IF NOT EXISTS idx_thc_ledger_user
                    ON thc_ledger(earn_user_id, created_at DESC);

                -- An append-only, deduplicated audit trail for provider
                -- clearance/reversal events.  It is deliberately separate
                -- from the balance projection in thc_ledger: a verified
                -- transition updates the original entry, never creates a
                -- second credit.
                CREATE TABLE IF NOT EXISTS thc_ledger_audit (
                    audit_id        TEXT PRIMARY KEY,
                    entry_id        TEXT NOT NULL
                        REFERENCES thc_ledger(entry_id),
                    event_ref       TEXT NOT NULL,
                    event_type      TEXT NOT NULL,
                    state           TEXT NOT NULL,
                    provider_status TEXT,
                    occurred_at     INTEGER NOT NULL,
                    details         TEXT NOT NULL DEFAULT '',
                    UNIQUE(entry_id, event_ref)
                );

                CREATE INDEX IF NOT EXISTS idx_thc_ledger_audit_entry
                    ON thc_ledger_audit(entry_id, occurred_at ASC);

                CREATE TABLE IF NOT EXISTS cpx_receipts (
                    trans_id        TEXT PRIMARY KEY,
                    earn_user_id    TEXT NOT NULL
                        REFERENCES earn_accounts(earn_user_id),
                    status          INTEGER NOT NULL,
                    amount_local    TEXT NOT NULL,
                    amount_usd      TEXT,
                    offer_id        TEXT,
                    thc_entry_id    TEXT,
                    received_at     INTEGER NOT NULL,
                    payload         TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_cpx_receipts_user
                    ON cpx_receipts(earn_user_id);

                -- Provider-specific public identifiers are short, stable and
                -- opaque.  They never expose an email or a wallet address.
                CREATE TABLE IF NOT EXISTS earn_provider_identities (
                    provider        TEXT NOT NULL,
                    provider_user_id TEXT NOT NULL,
                    earn_user_id    TEXT NOT NULL
                        REFERENCES earn_accounts(earn_user_id),
                    created_at      INTEGER NOT NULL,
                    PRIMARY KEY (provider, provider_user_id),
                    UNIQUE (provider, earn_user_id)
                );

                CREATE TABLE IF NOT EXISTS bitcotasks_receipts (
                    trans_id        TEXT PRIMARY KEY,
                    earn_user_id    TEXT NOT NULL
                        REFERENCES earn_accounts(earn_user_id),
                    status          INTEGER NOT NULL,
                    amount_thc      TEXT NOT NULL,
                    payout_usd      TEXT,
                    offer_name      TEXT,
                    offer_type      TEXT,
                    thc_entry_id    TEXT,
                    received_at     INTEGER NOT NULL,
                    payload         TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_bitcotasks_receipts_user
                    ON bitcotasks_receipts(earn_user_id);

                CREATE TABLE IF NOT EXISTS pure_receipts (
                    trans_id        TEXT PRIMARY KEY,
                    earn_user_id    TEXT NOT NULL
                        REFERENCES earn_accounts(earn_user_id),
                    status          INTEGER NOT NULL,
                    amount_thc      TEXT NOT NULL,
                    payout_usd      TEXT,
                    survey_id       TEXT,
                    thc_entry_id    TEXT,
                    received_at     INTEGER NOT NULL,
                    payload         TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_pure_receipts_user
                    ON pure_receipts(earn_user_id);

                CREATE TABLE IF NOT EXISTS timewall_receipts (
                    event_id        TEXT PRIMARY KEY,
                    earn_user_id    TEXT NOT NULL
                        REFERENCES earn_accounts(earn_user_id),
                    revenue_raw     TEXT NOT NULL,
                    amount_thc      TEXT NOT NULL,
                    event_type      TEXT,
                    reason          TEXT,
                    offer_name      TEXT,
                    offer_detail    TEXT,
                    thc_entry_id    TEXT,
                    received_at     INTEGER NOT NULL,
                    payload         TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_timewall_receipts_user
                    ON timewall_receipts(earn_user_id);

                -- Revenue attribution is a snapshot only: the referral cap
                -- is not a wallet credit, a funded reserve, or a payout.
                CREATE TABLE IF NOT EXISTS earn_timewall_revenue_allocations (
                    event_id TEXT PRIMARY KEY REFERENCES timewall_receipts(event_id),
                    provider_revenue_usd TEXT NOT NULL,
                    player_share_usd TEXT NOT NULL,
                    referral_cap_usd TEXT NOT NULL,
                    platform_before_referrals_usd TEXT NOT NULL,
                    platform_after_full_referrals_usd TEXT NOT NULL,
                    credited_player_thc TEXT NOT NULL,
                    conversion_multiplier TEXT NOT NULL,
                    conversion_allow_decimals INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending_reconciliation',
                    created_at INTEGER NOT NULL
                );

                -- A wallet link is a cryptographic identity binding, never a
                -- user-supplied address claim.  One wallet and one Earn
                -- account are intentionally a 1:1 relation for this beta.
                CREATE TABLE IF NOT EXISTS earn_wallet_links (
                    wallet_address TEXT PRIMARY KEY,
                    earn_user_id   TEXT NOT NULL UNIQUE
                        REFERENCES earn_accounts(earn_user_id),
                    public_key     TEXT NOT NULL,
                    linked_at      INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS earn_wallet_challenges (
                    challenge_id   TEXT PRIMARY KEY,
                    purpose        TEXT NOT NULL,
                    earn_user_id   TEXT
                        REFERENCES earn_accounts(earn_user_id),
                    wallet_address TEXT NOT NULL,
                    nonce          TEXT NOT NULL UNIQUE,
                    expires_at     INTEGER NOT NULL,
                    consumed_at    INTEGER
                );

                CREATE INDEX IF NOT EXISTS idx_earn_wallet_challenges_expiry
                    ON earn_wallet_challenges(expires_at);

                CREATE TABLE IF NOT EXISTS earn_staking_pools (
                    pool_id          TEXT PRIMARY KEY,
                    token            TEXT NOT NULL,
                    label            TEXT NOT NULL,
                    base_apy_bps     INTEGER NOT NULL,
                    boosted_apy_bps  INTEGER NOT NULL,
                    min_stake        TEXT NOT NULL,
                    status           TEXT NOT NULL DEFAULT 'active',
                    created_at       INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS earn_staking_positions (
                    position_id          TEXT PRIMARY KEY,
                    pool_id              TEXT NOT NULL
                        REFERENCES earn_staking_pools(pool_id),
                    earn_user_id         TEXT NOT NULL
                        REFERENCES earn_accounts(earn_user_id),
                    wallet_address       TEXT NOT NULL,
                    amount               TEXT NOT NULL,
                    status               TEXT NOT NULL DEFAULT 'active',
                    staked_at            INTEGER NOT NULL,
                    unstake_requested_at INTEGER,
                    wallet_tx_id         TEXT,
                    idempotency_key      TEXT,
                    fee_policy_version   TEXT NOT NULL DEFAULT 'legacy_fee_free',
                    term                 TEXT NOT NULL DEFAULT 'flex',
                    unlock_at            INTEGER
                );

                CREATE TABLE IF NOT EXISTS earn_staking_fees (
                    position_id TEXT NOT NULL REFERENCES earn_staking_positions(position_id),
                    action TEXT NOT NULL CHECK (action IN ('stake', 'unstake')),
                    earn_user_id TEXT NOT NULL REFERENCES earn_accounts(earn_user_id),
                    token TEXT NOT NULL CHECK (token = 'THC'),
                    amount TEXT NOT NULL,
                    fee_bps INTEGER NOT NULL,
                    reserve_account TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (position_id, action)
                );

                CREATE INDEX IF NOT EXISTS idx_earn_staking_positions_user
                    ON earn_staking_positions(earn_user_id);

                -- Cross-service THC commitment ledger.  Reservations remain
                -- active until the consuming settlement updates the Earn ledger
                -- or an explicit failure releases them.  This protects the same
                -- cleared THC from concurrent stake/cashout/escrow flows.
                CREATE TABLE IF NOT EXISTS earn_thc_reservations (
                    reservation_id  TEXT PRIMARY KEY,
                    earn_user_id    TEXT NOT NULL
                        REFERENCES earn_accounts(earn_user_id),
                    reservation_type TEXT NOT NULL CHECK (
                        reservation_type IN ('cashout', 'ad_escrow', 'wallet_settlement', 'wallet_unlock')
                    ),
                    amount          TEXT NOT NULL,
                    state           TEXT NOT NULL DEFAULT 'reserved' CHECK (
                        state IN ('reserved', 'settling', 'settled', 'released')
                    ),
                    source_ref      TEXT,
                    idempotency_key TEXT,
                    created_at      INTEGER NOT NULL,
                    updated_at      INTEGER NOT NULL,
                    released_at     INTEGER,
                    UNIQUE(earn_user_id, reservation_type, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS idx_earn_thc_reservations_active
                    ON earn_thc_reservations(earn_user_id, state);

                -- Wallet-unlock pledges use the same reservation ledger as
                -- cashout/staking protection. There is no public route here:
                -- wallet creation must later be coordinated with this state.
                CREATE TABLE IF NOT EXISTS earn_wallet_unlock_pledges (
                    pledge_id            TEXT PRIMARY KEY,
                    earn_user_id         TEXT NOT NULL
                        REFERENCES earn_accounts(earn_user_id),
                    reservation_id       TEXT NOT NULL UNIQUE
                        REFERENCES earn_thc_reservations(reservation_id),
                    pledge_kind          TEXT NOT NULL CHECK (
                        pledge_kind IN ('standard', 'sponsored')
                    ),
                    total_thc            TEXT NOT NULL,
                    permanently_locked_thc TEXT NOT NULL,
                    burn_eligible_thc    TEXT NOT NULL,
                    status               TEXT NOT NULL DEFAULT 'reserved' CHECK (
                        status IN ('reserved', 'settled', 'released')
                    ),
                    wallet_address       TEXT,
                    wallet_creation_ref  TEXT,
                    idempotency_key      TEXT NOT NULL,
                    created_at           INTEGER NOT NULL,
                    settled_at           INTEGER,
                    released_at          INTEGER,
                    UNIQUE(earn_user_id, pledge_kind, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS idx_earn_wallet_unlock_pledges_user
                    ON earn_wallet_unlock_pledges(earn_user_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS earn_ads (
                    ad_id       TEXT PRIMARY KEY,
                    title       TEXT NOT NULL,
                    image_url   TEXT NOT NULL,
                    target_url  TEXT NOT NULL,
                    placement   TEXT NOT NULL DEFAULT 'earn',
                    priority    INTEGER NOT NULL DEFAULT 0,
                    status      TEXT NOT NULL DEFAULT 'active',
                    impressions INTEGER NOT NULL DEFAULT 0,
                    clicks      INTEGER NOT NULL DEFAULT 0,
                    created_at  INTEGER NOT NULL,
                    expires_at  INTEGER
                );

                CREATE TABLE IF NOT EXISTS earn_referrals (
                    referrer_id    TEXT NOT NULL,
                    referred_id    TEXT NOT NULL,
                    ref_code       TEXT NOT NULL,
                    created_at     INTEGER NOT NULL,
                    PRIMARY KEY (referred_id)
                );
                CREATE INDEX IF NOT EXISTS idx_earn_referrals_referrer
                    ON earn_referrals(referrer_id);

                CREATE TABLE IF NOT EXISTS earn_ad_campaigns (
                    campaign_id    TEXT PRIMARY KEY,
                    advertiser_id  TEXT NOT NULL,
                    name           TEXT NOT NULL,
                    campaign_type  TEXT NOT NULL DEFAULT 'cpm',
                    bid_amount     TEXT NOT NULL DEFAULT '1.000000',
                    daily_budget   TEXT NOT NULL DEFAULT '0',
                    total_budget   TEXT NOT NULL DEFAULT '0',
                    country_targets TEXT DEFAULT '',
                    placement      TEXT NOT NULL DEFAULT 'earn',
                    status         TEXT NOT NULL DEFAULT 'pending_review',
                    reject_reason  TEXT,
                    impressions    INTEGER NOT NULL DEFAULT 0,
                    clicks         INTEGER NOT NULL DEFAULT 0,
                    spent          TEXT NOT NULL DEFAULT '0.000000',
                    created_at     INTEGER NOT NULL,
                    updated_at     INTEGER NOT NULL,
                    starts_at      INTEGER,
                    ends_at        INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_earn_ad_campaigns_advertiser
                    ON earn_ad_campaigns(advertiser_id);
                CREATE INDEX IF NOT EXISTS idx_earn_ad_campaigns_status
                    ON earn_ad_campaigns(status);

                CREATE TABLE IF NOT EXISTS earn_ad_creatives (
                    creative_id  TEXT PRIMARY KEY,
                    campaign_id  TEXT NOT NULL
                        REFERENCES earn_ad_campaigns(campaign_id),
                    title        TEXT NOT NULL,
                    image_url    TEXT NOT NULL,
                    target_url   TEXT NOT NULL,
                    status       TEXT NOT NULL DEFAULT 'pending_review',
                    reject_reason TEXT,
                    created_at   INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_earn_ad_creatives_campaign
                    ON earn_ad_creatives(campaign_id);

                CREATE TABLE IF NOT EXISTS earn_ad_escrow (
                    escrow_id      TEXT PRIMARY KEY,
                    campaign_id    TEXT NOT NULL
                        REFERENCES earn_ad_campaigns(campaign_id),
                    advertiser_id  TEXT NOT NULL,
                    action         TEXT NOT NULL,
                    amount         TEXT NOT NULL,
                    balance_after  TEXT NOT NULL,
                    note           TEXT,
                    idempotency_key TEXT UNIQUE,
                    intent_id      TEXT,
                    wallet_tx_id       TEXT,
                    pool_receipt_id    TEXT,
                    pool_position_id   TEXT,
                    payload_hash       TEXT,
                    settlement_status  TEXT NOT NULL DEFAULT 'pending',
                    created_at     INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_earn_ad_escrow_campaign
                    ON earn_ad_escrow(campaign_id);

                CREATE TABLE IF NOT EXISTS earn_escrow_intents (
                    intent_id       TEXT PRIMARY KEY,
                    earn_user_id    TEXT NOT NULL
                        REFERENCES earn_accounts(earn_user_id),
                    campaign_id     TEXT NOT NULL
                        REFERENCES earn_ad_campaigns(campaign_id),
                    action          TEXT NOT NULL,
                    amount          TEXT NOT NULL,
                    nonce           TEXT NOT NULL UNIQUE,
                    idempotency_key TEXT NOT NULL,
                    wallet_address  TEXT,
                    requires_wallet_sig INTEGER NOT NULL DEFAULT 1,
                    expires_at      INTEGER NOT NULL,
                    consumed_at     INTEGER,
                    created_at      INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_earn_escrow_intents_nonce
                    ON earn_escrow_intents(nonce);
                CREATE INDEX IF NOT EXISTS idx_earn_escrow_intents_idem
                    ON earn_escrow_intents(idempotency_key);

                CREATE TABLE IF NOT EXISTS earn_ad_events (
                    event_id      TEXT PRIMARY KEY,
                    campaign_id   TEXT NOT NULL,
                    creative_id   TEXT NOT NULL,
                    event_type    TEXT NOT NULL,
                    country       TEXT DEFAULT '',
                    earn_user_id  TEXT,
                    cost          TEXT NOT NULL DEFAULT '0.000000',
                    created_at    INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_earn_ad_events_campaign
                    ON earn_ad_events(campaign_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_earn_ad_events_type
                    ON earn_ad_events(event_type, created_at);

                CREATE TABLE IF NOT EXISTS earn_publishers (
                    publisher_id     TEXT PRIMARY KEY,
                    earn_user_id     TEXT NOT NULL
                        REFERENCES earn_accounts(earn_user_id),
                    provider         TEXT NOT NULL,
                    provider_pub_id  TEXT,
                    label            TEXT NOT NULL DEFAULT '',
                    postback_url     TEXT,
                    postback_secret  TEXT,
                    status           TEXT NOT NULL DEFAULT 'pending_review',
                    reject_reason    TEXT,
                    approved_at      INTEGER,
                    created_at       INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_earn_publishers_user
                    ON earn_publishers(earn_user_id);
                CREATE INDEX IF NOT EXISTS idx_earn_publishers_provider
                    ON earn_publishers(provider, provider_pub_id);

                CREATE TABLE IF NOT EXISTS earn_publisher_placements (
                    placement_id   TEXT PRIMARY KEY,
                    publisher_id   TEXT NOT NULL
                        REFERENCES earn_publishers(publisher_id),
                    placement_type TEXT NOT NULL DEFAULT 'survey',
                    site_url       TEXT,
                    status         TEXT NOT NULL DEFAULT 'active',
                    created_at     INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_earn_publisher_placements_pub
                    ON earn_publisher_placements(publisher_id);
            """)
            # Existing production Earn databases predate the provider
            # clearance and separate internal hold fields. SQLite lacks ADD COLUMN IF NOT
            # EXISTS, so use a narrow, fixed migration list rather than any
            # dynamic SQL based on external input.
            existing = {
                row[1] for row in con.execute("PRAGMA table_info(thc_ledger)")
            }
            for column, definition in (
                ("provider_status", "TEXT"),
                ("received_at", "INTEGER"),
                ("estimated_clearance_at", "INTEGER"),
                ("cleared_at", "INTEGER"),
                ("reversal_reason", "TEXT"),
                ("earn_hold_started_at", "INTEGER"),
                ("earn_hold_until", "INTEGER"),
                ("earn_hold_released_at", "INTEGER"),
                ("earn_hold_policy", "TEXT"),
            ):
                if column not in existing:
                    con.execute(f"ALTER TABLE thc_ledger ADD COLUMN {column} {definition}")
            con.commit()
            con.execute("BEGIN IMMEDIATE")
            # Apply the newly authorized internal policy only to verified,
            # still-pending receipts; never relock an existing available balance.
            rows = con.execute(
                f"""SELECT l.entry_id, COALESCE(l.received_at, l.created_at) AS first_received
                    FROM thc_ledger l WHERE l.state='pending' AND l.earn_hold_until IS NULL
                    AND {_VERIFIED_PROVIDER_RECEIPT_SQL}""",
            ).fetchall()
            for row in rows:
                self._attach_earn_hold_in_tx(con, row["entry_id"], row["first_received"])
            con.commit()
            # Migration: add wallet_tx_id to staking positions for existing DBs
            pos_cols = {
                row[1] for row in con.execute("PRAGMA table_info(earn_staking_positions)")
            }
            if "wallet_tx_id" not in pos_cols:
                con.execute("ALTER TABLE earn_staking_positions ADD COLUMN wallet_tx_id TEXT")
                con.commit()
            if "idempotency_key" not in pos_cols:
                con.execute("ALTER TABLE earn_staking_positions ADD COLUMN idempotency_key TEXT")
                con.commit()
            if "fee_policy_version" not in pos_cols:
                con.execute("ALTER TABLE earn_staking_positions ADD COLUMN fee_policy_version TEXT NOT NULL DEFAULT 'legacy_fee_free'")
                con.commit()
            if "term" not in pos_cols:
                con.execute("ALTER TABLE earn_staking_positions ADD COLUMN term TEXT NOT NULL DEFAULT 'flex'")
                con.commit()
            if "unlock_at" not in pos_cols:
                con.execute("ALTER TABLE earn_staking_positions ADD COLUMN unlock_at INTEGER")
                con.commit()
        finally:
            con.close()

    # ── CPX identity (server-side only) ──────────────────────────────────

    def _cpx_id(self, earn_user_id: str) -> str:
        digest = hmac.new(
            self._identity_key, earn_user_id.encode(), hashlib.sha256,
        ).hexdigest()
        return "thr_" + digest[:40]

    def provider_user_id(self, earn_user_id: str, provider: str) -> str:
        """Return a stable opaque provider identity (max 32 chars).

        Provider walls must never receive an email, wallet address, or the
        account primary key.  The mapping is written before a provider URL is
        issued, so an incoming postback can only resolve a user who actually
        opened that provider through Earn.
        """
        provider = (provider or "").strip().lower()
        if provider not in ("bitcotasks", "pure", "timewall"):
            raise EarnError("unsupported_earn_provider")
        with self._tx() as con:
            existing = con.execute(
                """SELECT provider_user_id FROM earn_provider_identities
                   WHERE provider = ? AND earn_user_id = ?""",
                (provider, earn_user_id),
            ).fetchone()
            if existing:
                return str(existing["provider_user_id"])
            user = con.execute(
                "SELECT 1 FROM earn_accounts WHERE earn_user_id = ?",
                (earn_user_id,),
            ).fetchone()
            if not user:
                raise EarnError("unknown_earn_user")
            digest = hmac.new(
                self._identity_key,
                f"{provider}:{earn_user_id}".encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            prefix = {"bitcotasks": "bt_", "pure": "ps_", "timewall": "tw_"}[provider]
            provider_user_id = prefix + digest[:28]
            con.execute(
                """INSERT INTO earn_provider_identities
                   (provider, provider_user_id, earn_user_id, created_at)
                   VALUES (?,?,?,?)""",
                (provider, provider_user_id, earn_user_id, int(time.time())),
            )
            return provider_user_id

    # ── Registration ─────────────────────────────────────────────────────

    def register(
        self, email: str, password: str, ref_code: str | None = None,
    ) -> dict[str, Any]:
        email = _validate_email(email)
        password = _validate_password(password)
        uid = "earn_" + secrets.token_urlsafe(18)
        cpx_id = self._cpx_id(uid)
        now = int(time.time())
        pw_hash = _hash_password(password)
        with self._tx() as con:
            existing = con.execute(
                "SELECT 1 FROM earn_accounts WHERE email = ?", (email,),
            ).fetchone()
            if existing:
                raise EarnError("email_already_registered")
            con.execute(
                """INSERT INTO earn_accounts
                   (earn_user_id, email, password_hash, email_verified,
                    cpx_ext_user_id, created_at, updated_at)
                   VALUES (?,?,?,0,?,?,?)""",
                (uid, email, pw_hash, cpx_id, now, now),
            )
            if ref_code:
                referrer = con.execute(
                    "SELECT earn_user_id FROM earn_accounts WHERE earn_user_id = ?",
                    (ref_code,),
                ).fetchone()
                if referrer:
                    con.execute(
                        """INSERT OR IGNORE INTO earn_referrals
                           (referrer_id, referred_id, ref_code, created_at)
                           VALUES (?,?,?,?)""",
                        (ref_code, uid, ref_code, now),
                    )
        return {"earn_user_id": uid, "email": email, "email_verified": False}

    # ── Rate limiting ────────────────────────────────────────────────────

    def _check_rate_limit(self, con: sqlite3.Connection, email: str) -> None:
        key = hashlib.sha256(email.lower().encode()).hexdigest()
        now = int(time.time())
        row = con.execute(
            "SELECT * FROM earn_login_attempts WHERE attempt_key = ?", (key,),
        ).fetchone()
        if row and row["locked_until"] > now:
            raise EarnError("account_temporarily_locked")
        if row and now - row["window_start"] > _RATE_WINDOW:
            con.execute(
                "DELETE FROM earn_login_attempts WHERE attempt_key = ?", (key,),
            )
            row = None
        if row and row["attempts"] >= _RATE_MAX_ATTEMPTS:
            con.execute(
                "UPDATE earn_login_attempts SET locked_until = ? WHERE attempt_key = ?",
                (now + _RATE_LOCKOUT, key),
            )
            raise EarnError("account_temporarily_locked")
        if not row:
            con.execute(
                "INSERT INTO earn_login_attempts VALUES (?, 0, ?, 0)",
                (key, now),
            )

    def _record_failed_attempt(self, con: sqlite3.Connection, email: str) -> None:
        key = hashlib.sha256(email.lower().encode()).hexdigest()
        now = int(time.time())
        con.execute(
            "UPDATE earn_login_attempts SET attempts = attempts + 1 WHERE attempt_key = ?",
            (key,),
        )
        row = con.execute(
            "SELECT attempts FROM earn_login_attempts WHERE attempt_key = ?",
            (key,),
        ).fetchone()
        if row and row["attempts"] >= _RATE_MAX_ATTEMPTS:
            con.execute(
                "UPDATE earn_login_attempts SET locked_until = ? WHERE attempt_key = ?",
                (now + _RATE_LOCKOUT, key),
            )

    def _clear_rate_limit(self, con: sqlite3.Connection, email: str) -> None:
        key = hashlib.sha256(email.lower().encode()).hexdigest()
        con.execute(
            "DELETE FROM earn_login_attempts WHERE attempt_key = ?", (key,),
        )

    # ── Login ────────────────────────────────────────────────────────────

    def login(self, email: str, password: str) -> tuple[dict[str, Any], str]:
        email = _validate_email(email)
        if not password:
            raise EarnError("invalid_credentials")

        # TX 1: rate-limit gate (commits whether it passes or raises)
        with self._tx() as con:
            self._check_rate_limit(con, email)

        # TX 2: credential check + record outcome (commits before raise)
        failed = False
        account_row = None
        with self._tx() as con:
            row = con.execute(
                "SELECT * FROM earn_accounts WHERE email = ?", (email,),
            ).fetchone()
            if not row or not _verify_password(password, row["password_hash"]):
                self._record_failed_attempt(con, email)
                failed = True
            else:
                account_row = dict(row)

        if failed:
            raise EarnError("invalid_credentials")

        # TX 3: success — clear rate limit, create session
        with self._tx() as con:
            self._clear_rate_limit(con, email)
            token = secrets.token_urlsafe(32)
            now = int(time.time())
            con.execute(
                "INSERT INTO earn_sessions VALUES (?,?,?,?)",
                (
                    hashlib.sha256(token.encode()).hexdigest(),
                    account_row["earn_user_id"],
                    now + _SESSION_TTL,
                    now,
                ),
            )

        return {
            "earn_user_id": account_row["earn_user_id"],
            "email": account_row["email"],
            "email_verified": bool(account_row["email_verified"]),
        }, token

    # ── Session ──────────────────────────────────────────────────────────

    def user_for_session(self, token: str) -> dict[str, Any] | None:
        if not token:
            return None
        key = hashlib.sha256(token.encode()).hexdigest()
        with self._tx() as con:
            row = con.execute(
                """SELECT a.earn_user_id, a.email, a.email_verified,
                          a.cpx_ext_user_id
                   FROM earn_sessions s
                   JOIN earn_accounts a ON a.earn_user_id = s.earn_user_id
                   WHERE s.token_hash = ? AND s.expires_at >= ?""",
                (key, int(time.time())),
            ).fetchone()
            return dict(row) if row else None

    def logout(self, token: str) -> bool:
        if not token:
            return False
        key = hashlib.sha256(token.encode()).hexdigest()
        with self._tx() as con:
            cur = con.execute(
                "DELETE FROM earn_sessions WHERE token_hash = ?", (key,),
            )
            return cur.rowcount > 0

    def rotate_session(self, old_token: str) -> tuple[str, int] | None:
        if not old_token:
            return None
        old_key = hashlib.sha256(old_token.encode()).hexdigest()
        with self._tx() as con:
            row = con.execute(
                "SELECT earn_user_id FROM earn_sessions WHERE token_hash = ? AND expires_at >= ?",
                (old_key, int(time.time())),
            ).fetchone()
            if not row:
                return None
            con.execute(
                "DELETE FROM earn_sessions WHERE token_hash = ?", (old_key,),
            )
            new_token = secrets.token_urlsafe(32)
            now = int(time.time())
            expires = now + _SESSION_TTL
            con.execute(
                "INSERT INTO earn_sessions VALUES (?,?,?,?)",
                (
                    hashlib.sha256(new_token.encode()).hexdigest(),
                    row["earn_user_id"],
                    expires,
                    now,
                ),
            )
            return new_token, expires

    # ── Wallet proof / account linking ───────────────────────────────────

    @staticmethod
    def _wallet_address(wallet_address: str) -> str:
        wallet_address = (wallet_address or "").strip().upper()
        if not re.fullmatch(r"THR[A-F0-9]{40}", wallet_address):
            raise EarnError("invalid_wallet_address")
        return wallet_address

    def _create_wallet_challenge(
        self, *, purpose: str, wallet_address: str, earn_user_id: str | None,
    ) -> dict[str, str]:
        wallet_address = self._wallet_address(wallet_address)
        if purpose not in ("link", "login"):
            raise EarnError("invalid_wallet_challenge")
        now = int(time.time())
        challenge = {
            "action": "earn_wallet_link" if purpose == "link" else "earn_wallet_login",
            "challenge_id": "ewc_" + secrets.token_urlsafe(18),
            "wallet_address": wallet_address,
            "nonce": secrets.token_urlsafe(24),
            "expires_at": str(now + _WALLET_CHALLENGE_TTL),
        }
        # Linking changes the account's sign-in authority.  The wallet PWA/APK
        # must pass its existing biometric/passkey gate before it signs this
        # exact server challenge.  The requirement is included in the signed
        # payload, so a proof for a login challenge cannot be repurposed.
        if purpose == "link":
            challenge["approval"] = "biometric_passkey"
        with self._tx() as con:
            con.execute("DELETE FROM earn_wallet_challenges WHERE expires_at < ?", (now,))
            con.execute(
                """INSERT INTO earn_wallet_challenges
                   (challenge_id, purpose, earn_user_id, wallet_address,
                    nonce, expires_at, consumed_at)
                   VALUES (?,?,?,?,?,?,NULL)""",
                (
                    challenge["challenge_id"], purpose, earn_user_id,
                    wallet_address, challenge["nonce"], int(challenge["expires_at"]),
                ),
            )
        return challenge

    def wallet_link_challenge(
        self, earn_user_id: str, wallet_address: str,
    ) -> dict[str, str]:
        return self._create_wallet_challenge(
            purpose="link", wallet_address=wallet_address, earn_user_id=earn_user_id,
        )

    def wallet_login_challenge(self, wallet_address: str) -> dict[str, str]:
        return self._create_wallet_challenge(
            purpose="login", wallet_address=wallet_address, earn_user_id=None,
        )

    def wallet_challenge_for_proof(
        self, *, challenge_id: str, purpose: str, wallet_address: str,
        earn_user_id: str | None = None,
    ) -> dict[str, str]:
        wallet_address = self._wallet_address(wallet_address)
        now = int(time.time())
        with self._tx() as con:
            row = con.execute(
                """SELECT * FROM earn_wallet_challenges
                   WHERE challenge_id = ? AND purpose = ?
                     AND wallet_address = ? AND consumed_at IS NULL
                     AND expires_at >= ?""",
                (challenge_id, purpose, wallet_address, now),
            ).fetchone()
            if not row or (earn_user_id is not None and row["earn_user_id"] != earn_user_id):
                raise EarnError("invalid_or_expired_wallet_challenge")
            proof = {
                "action": "earn_wallet_link" if purpose == "link" else "earn_wallet_login",
                "challenge_id": row["challenge_id"],
                "wallet_address": row["wallet_address"],
                "nonce": row["nonce"],
                "expires_at": str(row["expires_at"]),
            }
            if purpose == "link":
                proof["approval"] = "biometric_passkey"
            return proof

    def complete_wallet_link(
        self, *, challenge_id: str, earn_user_id: str, wallet_address: str,
        public_key: str,
    ) -> dict[str, str]:
        wallet_address = self._wallet_address(wallet_address)
        now = int(time.time())
        with self._tx() as con:
            challenge = con.execute(
                """SELECT * FROM earn_wallet_challenges
                   WHERE challenge_id = ? AND purpose = 'link'
                     AND earn_user_id = ? AND wallet_address = ?
                     AND consumed_at IS NULL AND expires_at >= ?""",
                (challenge_id, earn_user_id, wallet_address, now),
            ).fetchone()
            if not challenge:
                raise EarnError("invalid_or_expired_wallet_challenge")
            existing_wallet = con.execute(
                "SELECT earn_user_id FROM earn_wallet_links WHERE wallet_address = ?",
                (wallet_address,),
            ).fetchone()
            existing_user = con.execute(
                "SELECT wallet_address FROM earn_wallet_links WHERE earn_user_id = ?",
                (earn_user_id,),
            ).fetchone()
            if existing_wallet and existing_wallet["earn_user_id"] != earn_user_id:
                raise EarnError("wallet_already_linked")
            if existing_user and existing_user["wallet_address"] != wallet_address:
                raise EarnError("earn_account_already_linked")
            con.execute(
                """INSERT OR REPLACE INTO earn_wallet_links
                   (wallet_address, earn_user_id, public_key, linked_at)
                   VALUES (?,?,?,?)""",
                (wallet_address, earn_user_id, public_key.lower(), now),
            )
            con.execute(
                "UPDATE earn_wallet_challenges SET consumed_at = ? WHERE challenge_id = ?",
                (now, challenge_id),
            )
            return {"wallet_address": wallet_address, "earn_user_id": earn_user_id}

    def complete_wallet_login(
        self, *, challenge_id: str, wallet_address: str,
    ) -> tuple[dict[str, Any], str]:
        wallet_address = self._wallet_address(wallet_address)
        now = int(time.time())
        with self._tx() as con:
            challenge = con.execute(
                """SELECT * FROM earn_wallet_challenges
                   WHERE challenge_id = ? AND purpose = 'login'
                     AND wallet_address = ? AND consumed_at IS NULL
                     AND expires_at >= ?""",
                (challenge_id, wallet_address, now),
            ).fetchone()
            link = con.execute(
                """SELECT a.earn_user_id, a.email, a.email_verified
                   FROM earn_wallet_links l JOIN earn_accounts a
                     ON a.earn_user_id = l.earn_user_id
                   WHERE l.wallet_address = ?""",
                (wallet_address,),
            ).fetchone()
            if not challenge:
                raise EarnError("invalid_or_expired_wallet_challenge")
            if not link:
                raise EarnError("wallet_not_linked")
            con.execute(
                "UPDATE earn_wallet_challenges SET consumed_at = ? WHERE challenge_id = ?",
                (now, challenge_id),
            )
            token = secrets.token_urlsafe(32)
            con.execute(
                "INSERT INTO earn_sessions VALUES (?,?,?,?)",
                (hashlib.sha256(token.encode()).hexdigest(), link["earn_user_id"], now + _SESSION_TTL, now),
            )
            return dict(link), token

    def wallet_link_for_user(self, earn_user_id: str) -> dict[str, str] | None:
        with self._tx() as con:
            row = con.execute(
                "SELECT wallet_address, linked_at FROM earn_wallet_links WHERE earn_user_id = ?",
                (earn_user_id,),
            ).fetchone()
            return dict(row) if row else None

    # ── THC Ledger ───────────────────────────────────────────────────────

    def record_thc_credit(
        self,
        earn_user_id: str,
        source: str,
        source_ref: str,
        amount: str | int,
        *,
        note: str = "",
    ) -> tuple[dict[str, Any], bool]:
        try:
            amt = Decimal(str(amount)).quantize(_THC_SCALE, rounding=ROUND_DOWN)
            if amt <= 0:
                raise ValueError
        except (TypeError, ValueError, InvalidOperation):
            raise EarnError("invalid_thc_amount")
        amt = str(amt)
        if not source_ref or len(source_ref) > 200:
            raise EarnError("invalid_source_ref")
        with self._tx() as con:
            user = con.execute(
                "SELECT 1 FROM earn_accounts WHERE earn_user_id = ?",
                (earn_user_id,),
            ).fetchone()
            if not user:
                raise EarnError("unknown_earn_user")
            existing = con.execute(
                "SELECT * FROM thc_ledger WHERE source = ? AND source_ref = ?",
                (source, source_ref),
            ).fetchone()
            if existing:
                if existing["earn_user_id"] != earn_user_id:
                    raise EarnError("thc_source_conflict")
                return self._ledger_dict(existing), False
            now = int(time.time())
            entry_id = "thc_" + secrets.token_urlsafe(18)
            con.execute(
                """INSERT INTO thc_ledger
                   (entry_id, earn_user_id, source, source_ref, amount,
                    state, note, created_at, updated_at)
                   VALUES (?,?,?,?,?,'pending',?,?,?)""",
                (entry_id, earn_user_id, source, source_ref, amt, note, now, now),
            )
            row = con.execute(
                "SELECT * FROM thc_ledger WHERE entry_id = ?", (entry_id,),
            ).fetchone()
            return self._ledger_dict(row), True

    def transition_thc(
        self,
        entry_id: str,
        new_state: str,
        *,
        settlement_ref: str | None = None,
    ) -> dict[str, Any]:
        if new_state not in _THC_TRANSITIONS:
            raise EarnError("invalid_thc_state")
        with self._tx() as con:
            row = con.execute(
                "SELECT * FROM thc_ledger WHERE entry_id = ?", (entry_id,),
            ).fetchone()
            if not row:
                raise EarnError("thc_entry_not_found")
            if row["state"] == new_state:
                return self._ledger_dict(row)
            if row["state"] == "pending" and new_state in ("confirmed", "payable", "paid") and row["earn_hold_until"]:
                raise EarnError("earn_hold_requires_server_release")
            if new_state not in _THC_TRANSITIONS[row["state"]]:
                raise EarnError("invalid_thc_transition")
            if new_state == "paid" and not settlement_ref:
                raise EarnError("settlement_ref_required")
            con.execute(
                """UPDATE thc_ledger
                   SET state = ?, settlement_ref = ?, updated_at = ?
                   WHERE entry_id = ?""",
                (
                    new_state,
                    settlement_ref or row["settlement_ref"],
                    int(time.time()),
                    entry_id,
                ),
            )
            return self._ledger_dict(
                con.execute(
                    "SELECT * FROM thc_ledger WHERE entry_id = ?", (entry_id,),
                ).fetchone(),
            )

    def loyalty_status(self, earn_user_id: str | None) -> dict[str, Any]:
        linked = bool(earn_user_id and self.wallet_link_for_user(earn_user_id))
        return {
            "wallet_linked": linked, "vip": linked,
            "tier": "wallet_loyalty_vip" if linked else "earn_account",
            "basis": "verified_wallet_link" if linked else "wallet_not_linked",
        }

    def _attach_earn_hold_in_tx(self, con, entry_id: str, received_at: int) -> None:
        row = con.execute("SELECT * FROM thc_ledger WHERE entry_id=?", (entry_id,)).fetchone()
        if not row or row["state"] != "pending" or row["earn_hold_until"]:
            return
        amount = Decimal(row["amount"])
        if not amount.is_finite() or amount <= 0 or not received_at or int(received_at) <= 0:
            return
        started = int(received_at)
        con.execute(
            """UPDATE thc_ledger SET earn_hold_started_at=?, earn_hold_until=?,
               earn_hold_policy=? WHERE entry_id=? AND earn_hold_until IS NULL""",
            (started, started + _EARN_HOLD_SECONDS, _EARN_HOLD_POLICY, entry_id),
        )
        self._append_ledger_audit_in_tx(
            con, entry_id=entry_id, event_ref=f"earn:hold:start:{entry_id}",
            event_type="earn_hold_started", state="pending", occurred_at=started,
            provider_status=row["provider_status"], details=_EARN_HOLD_POLICY,
        )

    def release_mature_earn_holds(self) -> int:
        """Master scheduler only: release the internal hold, never send money."""
        def setting(name, default):
            return os.getenv(name, default).strip().strip("\"'").lower()
        if (setting("NODE_ROLE", "") != "master"
                or setting("READ_ONLY", "0") in ("1", "true", "yes")
                or setting("SCHEDULER_ENABLED", "0") not in ("1", "true", "yes")):
            return 0
        now = int(time.time())
        released = 0
        with self._tx() as con:
            rows = con.execute(
                f"""SELECT l.* FROM thc_ledger l WHERE l.state='pending'
                    AND l.earn_hold_policy=? AND l.earn_hold_until<=?
                    AND l.earn_hold_until=l.earn_hold_started_at+?
                    AND l.earn_hold_released_at IS NULL
                    AND {_VERIFIED_PROVIDER_RECEIPT_SQL}
                    ORDER BY l.earn_hold_until LIMIT 500""", (_EARN_HOLD_POLICY, now, _EARN_HOLD_SECONDS),
            ).fetchall()
            for row in rows:
                amount = Decimal(row["amount"])
                if not amount.is_finite() or amount <= 0:
                    continue
                con.execute(
                    """UPDATE thc_ledger SET state='confirmed', earn_hold_released_at=?,
                       updated_at=? WHERE entry_id=? AND state='pending'""",
                    (now, now, row["entry_id"]),
                )
                self._append_ledger_audit_in_tx(
                    con, entry_id=row["entry_id"], event_ref=f"earn:hold:release:{row['entry_id']}",
                    event_type="earn_hold_released", state="confirmed", occurred_at=now,
                    provider_status=row["provider_status"], details=_EARN_HOLD_POLICY,
                )
                released += 1
        return released

    def thc_balance(self, earn_user_id: str) -> dict[str, Any]:
        now = int(time.time())
        with self._tx() as con:
            rows = con.execute(
                "SELECT state, amount, created_at, estimated_clearance_at, earn_hold_until"
                " FROM thc_ledger WHERE earn_user_id = ?",
                (earn_user_id,),
            ).fetchall()
            staked_rows = con.execute(
                """SELECT sp.amount FROM earn_staking_positions sp
                   JOIN earn_staking_pools p ON p.pool_id = sp.pool_id
                   WHERE sp.earn_user_id = ? AND sp.status = 'active' AND p.token = 'THC'""",
                (earn_user_id,),
            ).fetchall()
            fee_rows = con.execute(
                "SELECT amount FROM earn_staking_fees WHERE earn_user_id = ? AND token = 'THC'",
                (earn_user_id,),
            ).fetchall()
            reserved_thc = self._active_thc_reservations_in_tx(con, earn_user_id)
        staked_thc = sum((Decimal(r["amount"]) for r in staked_rows), Decimal(0))
        staking_fees = sum((Decimal(r["amount"]) for r in fee_rows), Decimal(0))
        by_state: dict[str, Decimal] = {}
        earliest_clears: int | None = None
        earliest_hold: int | None = None
        for r in rows:
            s = r["state"]
            by_state[s] = by_state.get(s, Decimal("0")) + Decimal(r["amount"])
            if s == "pending":
                hold = int(r["earn_hold_until"] or 0)
                if hold and (earliest_hold is None or hold < earliest_hold):
                    earliest_hold = hold
                eta = int(r["estimated_clearance_at"] or 0)
                if eta and (earliest_clears is None or eta < earliest_clears):
                    earliest_clears = eta
        confirmed = by_state.get("confirmed", Decimal("0"))
        payable = by_state.get("payable", Decimal("0"))
        paid = by_state.get("paid", Decimal("0"))
        pending = by_state.get("pending", Decimal("0"))
        available = max(Decimal(0), confirmed + payable - staked_thc - staking_fees - reserved_thc)
        result: dict[str, Any] = {
            "available": str(available.quantize(_THC_SCALE)),
            "pending": str(pending.quantize(_THC_SCALE)),
            "total_earned": str((confirmed + payable + paid).quantize(_THC_SCALE)),
            "paid_out": str(paid.quantize(_THC_SCALE)),
            "staked": str(staked_thc.quantize(_THC_SCALE)),
            "reserved": str(reserved_thc.quantize(_THC_SCALE)),
            "staking_fees_paid": str(staking_fees.quantize(_THC_SCALE)),
            "clearance_status": "provider_eta_pending",
            "clearance_message": "Clearance date not yet received from provider.",
        }
        if earliest_clears:
            remaining = max(0, earliest_clears - now)
            result["earliest_clears_at"] = earliest_clears
            result["days_remaining"] = remaining // 86400 + (1 if remaining % 86400 else 0)
        if earliest_hold:
            remaining = max(0, earliest_hold - now)
            result.update(
                earliest_earn_hold_until=earliest_hold,
                earn_hold_days_remaining=(remaining + 86399) // 86400,
                earn_hold_seconds_remaining=remaining,
                clearance_status="earn_hold_active" if remaining else "earn_hold_due",
                clearance_message="Seven-day Earn hold after verified provider receipt.",
            )
        return result

    def thc_history(
        self, earn_user_id: str, *, limit: int = 100,
    ) -> list[dict[str, Any]]:
        with self._tx() as con:
            rows = con.execute(
                """SELECT entry_id, source, source_ref, amount, state,
                          note, settlement_ref, provider_status, received_at,
                          estimated_clearance_at, cleared_at, reversal_reason,
                          earn_hold_started_at, earn_hold_until, earn_hold_released_at, earn_hold_policy,
                          created_at, updated_at
                   FROM thc_ledger WHERE earn_user_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (earn_user_id, min(max(limit, 1), 200)),
            ).fetchall()
            return [self._ledger_dict(r) for r in rows]

    def thc_receipt_details(self, earn_user_id: str, entry_id: str) -> dict[str, Any]:
        """Read only the caller's receipt and safe audit fields, never raw payloads."""
        with self._tx() as con:
            row = con.execute(
                """SELECT entry_id, source, source_ref, amount, state, note,
                          settlement_ref, provider_status, received_at,
                          estimated_clearance_at, cleared_at, reversal_reason,
                          earn_hold_started_at, earn_hold_until, earn_hold_released_at, earn_hold_policy,
                          created_at, updated_at
                   FROM thc_ledger WHERE earn_user_id = ? AND entry_id = ?""",
                (earn_user_id, entry_id),
            ).fetchone()
            if not row:
                raise EarnError("receipt_not_found")
            events = con.execute(
                """SELECT event_ref, event_type, state, provider_status, occurred_at
                   FROM thc_ledger_audit WHERE entry_id = ?
                   ORDER BY occurred_at, rowid""", (entry_id,),
            ).fetchall()
            return {"entry": self._ledger_dict(row), "events": [dict(e) for e in events]}

    def validate_timewall_identity(self, provider_user_id: str) -> None:
        """Read-only callback preflight. Does not create an identity or reward."""
        with self._tx() as con:
            row = con.execute(
                """SELECT 1 FROM earn_provider_identities
                   WHERE provider = 'timewall' AND provider_user_id = ?""",
                (provider_user_id,),
            ).fetchone()
            if not row:
                raise EarnError("unknown_provider_user")

    _VALID_LEADERBOARD_PERIODS = ("weekly", "monthly", "all_time")

    def leaderboard(
        self, *, limit: int = 50, caller_user_id: str | None = None,
        at_time: int | None = None, period: str = "monthly",
    ) -> dict[str, Any]:
        """Verified receipts leaderboard with period filtering.

        Only durable provider receipts may contribute. This read never clears
        rewards, releases funds or awards competition prizes. Boundaries use
        receipt time, so later clearance does not move a reward to another cycle.

        period: 'weekly' (7 days), 'monthly' (30-day cycle, default), 'all_time'.
        """
        if period not in self._VALID_LEADERBOARD_PERIODS:
            period = "monthly"
        now = int(time.time()) if at_time is None else int(at_time)
        limit = min(max(limit, 1), 50)

        if period == "weekly":
            period_start = max(_LEADERBOARD_START, now - 7 * 86400)
            period_end = _LEADERBOARD_END
        elif period == "all_time":
            period_start = 0
            period_end = now + 1
        else:
            period_start = _LEADERBOARD_START
            period_end = _LEADERBOARD_END

        with self._tx() as con:
            rows = con.execute(
                f"""SELECT l.earn_user_id, l.amount, l.state
                   FROM thc_ledger l
                   WHERE l.state IN ('pending', 'confirmed', 'payable', 'paid')
                     AND COALESCE(l.received_at, l.created_at) >= ?
                     AND COALESCE(l.received_at, l.created_at) < ?
                     AND COALESCE(l.received_at, l.created_at) <= ?
                     AND {_VERIFIED_PROVIDER_RECEIPT_SQL}""",
                (period_start, period_end, now),
            ).fetchall()

        totals: dict[str, dict[str, Any]] = {}
        for row in rows:
            amount = Decimal(row["amount"])
            if not amount.is_finite() or amount <= 0:
                continue
            uid = row["earn_user_id"]
            total = totals.setdefault(uid, {"pending": Decimal("0"), "cleared": Decimal("0"), "completions": 0})
            total["pending" if row["state"] == "pending" else "cleared"] += amount
            total["completions"] += 1

        def alias(uid):
            digest = hmac.new(self._identity_key, f"leaderboard:{uid}".encode(), hashlib.sha256).hexdigest()
            return "Earner-" + digest[:10].upper()

        ranked = sorted(totals, key=lambda uid: (-(totals[uid]["pending"] + totals[uid]["cleared"]), alias(uid)))
        entries = []
        your_rank = None
        your_score = {"total_earned": "0.000000", "pending_earned": "0.000000", "cleared_earned": "0.000000", "completions": 0}
        previous_score = None
        rank = 0
        for position, uid in enumerate(ranked, 1):
            total = totals[uid]
            score = total["pending"] + total["cleared"]
            if score != previous_score:
                rank = position
            previous_score = score
            entry = {
                "rank": rank, "display_name": alias(uid),
                "total_earned": str(score.quantize(_THC_SCALE)),
                "completions": total["completions"],
                "is_caller": uid == caller_user_id,
            }
            if uid == caller_user_id:
                your_rank = rank
                your_score = {
                    "total_earned": str(score.quantize(_THC_SCALE)),
                    "pending_earned": str(total["pending"].quantize(_THC_SCALE)),
                    "cleared_earned": str(total["cleared"].quantize(_THC_SCALE)),
                    "completions": total["completions"],
                }
            if position <= limit:
                entries.append(entry)

        return {
            "campaign_id": _LEADERBOARD_CAMPAIGN,
            "period": period,
            "starts_at": period_start, "ends_at": period_end,
            "server_now": now, "seconds_remaining": max(0, period_end - now),
            "phase": "upcoming" if now < period_start else "running" if now < period_end else "ended",
            "score_policy": "verified_provider_receipts_pending_and_cleared",
            "provisional": any(t["pending"] > 0 for t in totals.values()),
            "prizes_enabled": False,
            "total_active": len(ranked), "your_rank": your_rank,
            "your_score": your_score, "entries": entries,
            "loyalty": self.loyalty_status(caller_user_id),
            "last_updated": now,
        }

    # ── Staking Pool ────────────────────────────────────────────────────

    _DEFAULT_POOLS = [
        {
            "pool_id": "pool_thc_loyalty",
            "token": "THC",
            "label": "THC Loyalty Pool",
            "base_apy_bps": 800,
            "boosted_apy_bps": 1200,
            "min_stake": "10",
        },
        {
            "pool_id": "pool_thr_staking",
            "token": "THR",
            "label": "THR Staking Pool",
            "base_apy_bps": 500,
            "boosted_apy_bps": 800,
            "min_stake": "1",
        },
    ]

    def _ensure_staking_pools(self, con: sqlite3.Connection) -> None:
        now = int(time.time())
        for pool in self._DEFAULT_POOLS:
            existing = con.execute(
                "SELECT 1 FROM earn_staking_pools WHERE pool_id = ?",
                (pool["pool_id"],),
            ).fetchone()
            if not existing:
                con.execute(
                    """INSERT INTO earn_staking_pools
                       (pool_id, token, label, base_apy_bps, boosted_apy_bps,
                        min_stake, status, created_at)
                       VALUES (?,?,?,?,?,?,'active',?)""",
                    (
                        pool["pool_id"], pool["token"], pool["label"],
                        pool["base_apy_bps"], pool["boosted_apy_bps"],
                        pool["min_stake"], now,
                    ),
                )

    def staking_pools(self) -> list[dict[str, Any]]:
        with self._tx() as con:
            self._ensure_staking_pools(con)
            pools = con.execute(
                "SELECT * FROM earn_staking_pools WHERE status = 'active'"
            ).fetchall()
            result = []
            for p in pools:
                stats = con.execute(
                    """SELECT COUNT(*) AS cnt,
                              COALESCE(SUM(CASE WHEN amount != '' THEN 1 ELSE 0 END), 0) AS pos_count
                       FROM earn_staking_positions
                       WHERE pool_id = ? AND status = 'active'""",
                    (p["pool_id"],),
                ).fetchone()
                active_rows = con.execute(
                    "SELECT amount FROM earn_staking_positions WHERE pool_id = ? AND status = 'active'",
                    (p["pool_id"],),
                ).fetchall()
                total_staked = sum((Decimal(r["amount"]) for r in active_rows), Decimal(0))
                result.append({
                    "pool_id": p["pool_id"],
                    "token": p["token"],
                    "label": p["label"],
                    "base_apy_bps": p["base_apy_bps"],
                    "boosted_apy_bps": p["boosted_apy_bps"],
                    "base_apy": str(Decimal(p["base_apy_bps"]) / 100),
                    "flex_apy": str(Decimal(_THC_FLEX_ILLUSTRATIVE_APY_BPS) / 100) if p["token"] == "THC" else None,
                    "boosted_apy": str(Decimal(p["boosted_apy_bps"]) / 100),
                    "min_stake": p["min_stake"],
                    "fee_bps": _STAKING_FEE_BPS,
                    "fee_policy_version": _STAKING_FEE_POLICY,
                    "total_staked": str(total_staked.quantize(_THC_SCALE)),
                    "stakers": stats["cnt"] if stats else 0,
                })
            return result

    def staking_positions(self, earn_user_id: str) -> list[dict[str, Any]]:
        now = int(time.time())
        with self._tx() as con:
            self._ensure_staking_pools(con)
            rows = con.execute(
                """SELECT sp.*, p.token, p.label AS pool_label,
                          p.base_apy_bps, p.boosted_apy_bps
                   FROM earn_staking_positions sp
                   JOIN earn_staking_pools p ON p.pool_id = sp.pool_id
                   WHERE sp.earn_user_id = ?
                   ORDER BY sp.staked_at DESC""",
                (earn_user_id,),
            ).fetchall()
            result = []
            for r in rows:
                amt = Decimal(r["amount"])
                end_at = (r["unstake_requested_at"] or r["staked_at"]) if r["status"] == "unstaked" else now
                staked_seconds = max(end_at - r["staked_at"], 0)
                apy_bps = (_THC_FLEX_ILLUSTRATIVE_APY_BPS
                           if r["token"] == "THC" and r["term"] == "flex"
                           else r["base_apy_bps"])
                projected_annual = amt * Decimal(apy_bps) / Decimal(10000)
                projected_earned = (
                    projected_annual * Decimal(staked_seconds)
                    / Decimal(365 * 86400)
                ).quantize(_THC_SCALE)
                result.append({
                    "position_id": r["position_id"],
                    "pool_id": r["pool_id"],
                    "pool_label": r["pool_label"],
                    "token": r["token"],
                    "amount": str(amt.quantize(_THC_SCALE)),
                    "status": r["status"],
                    "staked_at": r["staked_at"],
                    "unstake_requested_at": r["unstake_requested_at"],
                    "apy": str(Decimal(apy_bps) / 100),
                    "projected_rewards": str(projected_earned),
                    "unstake_fee": str(self.staking_fee(amt)) if r["fee_policy_version"] == _STAKING_FEE_POLICY else "0.000000",
                    "fee_policy_version": r["fee_policy_version"],
                    "term": r["term"], "unlock_at": r["unlock_at"],
                })
            return result

    def _debit_wallet_for_stake(
        self, wallet_address: str, amount: Decimal,
    ) -> str | None:
        """Debit THR from wallet to staking pool vault (no fee). Returns tx_id or None if ledger unavailable."""
        try:
            from services.thr_ledger import stake_thr
        except (ImportError, Exception):
            return None
        try:
            tx = stake_thr(wallet_address, amount)
        except ValueError as exc:
            raise EarnError(str(exc))
        return tx["tx_id"]

    def _credit_wallet_for_unstake(
        self, wallet_address: str, amount: Decimal, original_tx_id: str | None,
    ) -> str | None:
        """Credit THR back from staking pool vault to wallet (no fee). Returns tx_id or None if ledger unavailable."""
        try:
            from services.thr_ledger import unstake_thr
        except (ImportError, Exception):
            return None
        try:
            tx = unstake_thr(wallet_address, amount, original_tx_id or "")
        except ValueError as exc:
            raise EarnError(str(exc))
        return tx["tx_id"]

    _THC_RESERVATION_TYPES = frozenset({"cashout", "ad_escrow", "wallet_settlement", "wallet_unlock"})
    _ACTIVE_THC_RESERVATION_STATES = ("reserved", "settling", "settled")

    def _active_thc_reservations_in_tx(
        self, con: sqlite3.Connection, earn_user_id: str,
    ) -> Decimal:
        rows = con.execute(
            """SELECT amount FROM earn_thc_reservations
               WHERE earn_user_id = ?
                 AND state IN ('reserved', 'settling', 'settled')""",
            (earn_user_id,),
        ).fetchall()
        return sum((Decimal(item["amount"]) for item in rows), Decimal(0))

    def reserve_thc(
        self,
        earn_user_id: str,
        amount: str,
        *,
        reservation_type: str,
        source_ref: str = "",
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        """Atomically reserve cleared THC for a cross-service settlement.

        This does not move or burn THC.  A reservation remains unavailable
        until its consumer releases it after a failed/cancelled flow or
        reconciles its Earn-ledger debit.  Callers must supply an idempotency
        key so retries cannot create duplicate commitments.
        """
        if reservation_type not in self._THC_RESERVATION_TYPES:
            raise EarnError("invalid_thc_reservation_type")
        if not idempotency_key or len(idempotency_key) > 160:
            raise EarnError("reservation_idempotency_key_required")
        try:
            requested = Decimal(str(amount))
            if (not requested.is_finite() or requested <= 0
                    or requested != requested.quantize(_THC_SCALE)):
                raise ValueError
        except (InvalidOperation, TypeError, ValueError):
            raise EarnError("invalid_thc_reservation_amount")
        now = int(time.time())
        with self._tx() as con:
            existing = con.execute(
                """SELECT * FROM earn_thc_reservations
                   WHERE earn_user_id=? AND reservation_type=?
                     AND idempotency_key=?""",
                (earn_user_id, reservation_type, idempotency_key),
            ).fetchone()
            if existing:
                if (Decimal(existing["amount"]) != requested
                        or (existing["source_ref"] or "") != source_ref):
                    raise EarnError("thc_reservation_idempotency_conflict")
                return dict(existing)
            available = self._available_thc_for_staking(con, earn_user_id)
            if available < requested:
                raise EarnError("insufficient_thc_balance")
            reservation_id = "thcr_" + secrets.token_urlsafe(18)
            con.execute(
                """INSERT INTO earn_thc_reservations
                   (reservation_id, earn_user_id, reservation_type, amount,
                    state, source_ref, idempotency_key, created_at, updated_at)
                   VALUES (?,?,?,?, 'reserved', ?,?,?,?)""",
                (reservation_id, earn_user_id, reservation_type, str(requested),
                 source_ref or None, idempotency_key, now, now),
            )
            return dict(con.execute(
                "SELECT * FROM earn_thc_reservations WHERE reservation_id=?",
                (reservation_id,),
            ).fetchone())

    def transition_thc_reservation(
        self, earn_user_id: str, reservation_id: str, state: str,
    ) -> dict[str, Any]:
        """Advance a reservation without ever silently freeing THC."""
        if state not in ("settling", "settled", "released"):
            raise EarnError("invalid_thc_reservation_state")
        now = int(time.time())
        with self._tx() as con:
            row = con.execute(
                """SELECT * FROM earn_thc_reservations
                   WHERE reservation_id=? AND earn_user_id=?""",
                (reservation_id, earn_user_id),
            ).fetchone()
            if not row:
                raise EarnError("thc_reservation_not_found")
            current = row["state"]
            if current == state:
                return dict(row)
            allowed = {
                "reserved": {"settling", "released"},
                "settling": {"settled", "released"},
                "settled": set(),
                "released": set(),
            }
            if state not in allowed[current]:
                raise EarnError("invalid_thc_reservation_transition")
            con.execute(
                """UPDATE earn_thc_reservations
                   SET state=?, updated_at=?, released_at=?
                   WHERE reservation_id=?""",
                (state, now, now if state == "released" else None, reservation_id),
            )
            return dict(con.execute(
                "SELECT * FROM earn_thc_reservations WHERE reservation_id=?",
                (reservation_id,),
            ).fetchone())

    def thc_reservations(self, earn_user_id: str) -> list[dict[str, Any]]:
        with self._tx() as con:
            rows = con.execute(
                """SELECT reservation_id, reservation_type, amount, state,
                          source_ref, created_at, updated_at, released_at
                   FROM earn_thc_reservations WHERE earn_user_id=?
                   ORDER BY created_at DESC""",
                (earn_user_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    _WALLET_UNLOCK_THC = Decimal("10025.000000")
    _WALLET_UNLOCK_LOCK_RATIO = Decimal("0.5")

    def create_wallet_unlock_pledge(
        self, earn_user_id: str, *, idempotency_key: str,
    ) -> dict[str, Any]:
        """Atomically reserve the approved THC wallet-unlock pledge.

        This stores no private material and does not itself create a wallet.
        A later wallet-factory adapter must settle or release the pledge.
        """
        if not idempotency_key or len(idempotency_key) > 160:
            raise EarnError("pledge_idempotency_key_required")
        total = self._WALLET_UNLOCK_THC
        locked = (total * self._WALLET_UNLOCK_LOCK_RATIO).quantize(_THC_SCALE)
        burn_eligible = (total - locked).quantize(_THC_SCALE)
        now = int(time.time())
        with self._tx() as con:
            existing = con.execute(
                """SELECT * FROM earn_wallet_unlock_pledges
                   WHERE earn_user_id=? AND pledge_kind='standard'
                     AND idempotency_key=?""",
                (earn_user_id, idempotency_key),
            ).fetchone()
            if existing:
                return dict(existing)
            available = self._available_thc_for_staking(con, earn_user_id)
            if available < total:
                raise EarnError("insufficient_thc_balance")
            pledge_id = "ewp_" + secrets.token_urlsafe(18)
            reservation_id = "thcr_" + secrets.token_urlsafe(18)
            con.execute(
                """INSERT INTO earn_thc_reservations
                   (reservation_id, earn_user_id, reservation_type, amount,
                    state, source_ref, idempotency_key, created_at, updated_at)
                   VALUES (?,?,?,?, 'reserved', ?,?,?,?)""",
                (reservation_id, earn_user_id, "wallet_unlock", str(total),
                 pledge_id, idempotency_key, now, now),
            )
            con.execute(
                """INSERT INTO earn_wallet_unlock_pledges
                   (pledge_id, earn_user_id, reservation_id, pledge_kind,
                    total_thc, permanently_locked_thc, burn_eligible_thc,
                    status, idempotency_key, created_at)
                   VALUES (?,?,?,?,?,?,?,'reserved',?,?)""",
                (pledge_id, earn_user_id, reservation_id, "standard",
                 str(total), str(locked), str(burn_eligible),
                 idempotency_key, now),
            )
            return dict(con.execute(
                "SELECT * FROM earn_wallet_unlock_pledges WHERE pledge_id=?",
                (pledge_id,),
            ).fetchone())

    def settle_wallet_unlock_pledge(
        self, earn_user_id: str, pledge_id: str, *,
        wallet_address: str, wallet_creation_ref: str,
    ) -> dict[str, Any]:
        """Commit a pre-reserved pledge after an external wallet factory succeeds."""
        if not wallet_creation_ref or len(wallet_creation_ref) > 200:
            raise EarnError("wallet_creation_ref_required")
        wallet_address = self._wallet_address(wallet_address)
        now = int(time.time())
        with self._tx() as con:
            pledge = con.execute(
                """SELECT * FROM earn_wallet_unlock_pledges
                   WHERE pledge_id=? AND earn_user_id=?""",
                (pledge_id, earn_user_id),
            ).fetchone()
            if not pledge:
                raise EarnError("wallet_unlock_pledge_not_found")
            if pledge["status"] == "settled":
                if (pledge["wallet_address"] != wallet_address
                        or pledge["wallet_creation_ref"] != wallet_creation_ref):
                    raise EarnError("wallet_unlock_pledge_idempotency_conflict")
                return dict(pledge)
            if pledge["status"] != "reserved":
                raise EarnError("invalid_wallet_unlock_pledge_transition")
            updated = con.execute(
                """UPDATE earn_thc_reservations SET state='settled', updated_at=?
                   WHERE reservation_id=? AND earn_user_id=?
                     AND reservation_type='wallet_unlock' AND state='reserved'""",
                (now, pledge["reservation_id"], earn_user_id),
            )
            if updated.rowcount != 1:
                raise EarnError("wallet_unlock_reservation_not_settleable")
            con.execute(
                """UPDATE earn_wallet_unlock_pledges
                   SET status='settled', wallet_address=?, wallet_creation_ref=?,
                       settled_at=? WHERE pledge_id=?""",
                (wallet_address, wallet_creation_ref, now, pledge_id),
            )
            return dict(con.execute(
                "SELECT * FROM earn_wallet_unlock_pledges WHERE pledge_id=?",
                (pledge_id,),
            ).fetchone())

    def release_wallet_unlock_pledge(
        self, earn_user_id: str, pledge_id: str,
    ) -> dict[str, Any]:
        """Release only an unconsumed pledge after wallet creation failed."""
        now = int(time.time())
        with self._tx() as con:
            pledge = con.execute(
                """SELECT * FROM earn_wallet_unlock_pledges
                   WHERE pledge_id=? AND earn_user_id=?""",
                (pledge_id, earn_user_id),
            ).fetchone()
            if not pledge:
                raise EarnError("wallet_unlock_pledge_not_found")
            if pledge["status"] == "released":
                return dict(pledge)
            if pledge["status"] != "reserved":
                raise EarnError("invalid_wallet_unlock_pledge_transition")
            updated = con.execute(
                """UPDATE earn_thc_reservations
                   SET state='released', updated_at=?, released_at=?
                   WHERE reservation_id=? AND earn_user_id=?
                     AND reservation_type='wallet_unlock' AND state='reserved'""",
                (now, now, pledge["reservation_id"], earn_user_id),
            )
            if updated.rowcount != 1:
                raise EarnError("wallet_unlock_reservation_not_releasable")
            con.execute(
                """UPDATE earn_wallet_unlock_pledges
                   SET status='released', released_at=? WHERE pledge_id=?""",
                (now, pledge_id),
            )
            return dict(con.execute(
                "SELECT * FROM earn_wallet_unlock_pledges WHERE pledge_id=?",
                (pledge_id,),
            ).fetchone())

    def wallet_unlock_pledges(self, earn_user_id: str) -> list[dict[str, Any]]:
        with self._tx() as con:
            rows = con.execute(
                """SELECT pledge_id, reservation_id, pledge_kind, total_thc,
                          permanently_locked_thc, burn_eligible_thc, status,
                          wallet_address, wallet_creation_ref, created_at,
                          settled_at, released_at
                   FROM earn_wallet_unlock_pledges WHERE earn_user_id=?
                   ORDER BY created_at DESC""",
                (earn_user_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def _available_thc_for_staking(self, con: sqlite3.Connection, earn_user_id: str) -> Decimal:
        """Available THC minus active THC staking locks."""
        rows = con.execute(
            "SELECT state, amount FROM thc_ledger WHERE earn_user_id = ?",
            (earn_user_id,),
        ).fetchall()
        confirmed = sum((Decimal(r["amount"]) for r in rows if r["state"] == "confirmed"), Decimal(0))
        payable = sum((Decimal(r["amount"]) for r in rows if r["state"] == "payable"), Decimal(0))
        staked_rows = con.execute(
            """SELECT sp.amount FROM earn_staking_positions sp
               JOIN earn_staking_pools p ON p.pool_id = sp.pool_id
               WHERE sp.earn_user_id = ? AND sp.status = 'active' AND p.token = 'THC'""",
            (earn_user_id,),
        ).fetchall()
        staked = sum((Decimal(r["amount"]) for r in staked_rows), Decimal(0))
        fees = con.execute(
            "SELECT amount FROM earn_staking_fees WHERE earn_user_id = ? AND token = 'THC'",
            (earn_user_id,),
        ).fetchall()
        fees_paid = sum((Decimal(r["amount"]) for r in fees), Decimal(0))
        reservations = self._active_thc_reservations_in_tx(con, earn_user_id)
        return max(Decimal(0), confirmed + payable - staked - fees_paid - reservations)

    @staticmethod
    def staking_fee(amount: Decimal) -> Decimal:
        return (amount * Decimal(_STAKING_FEE_BPS) / Decimal(10000)).quantize(
            _THC_SCALE, rounding=ROUND_UP,
        )

    def staking_fee_quote(self, pool_id: str, amount: str, term: str = "flex") -> dict[str, Any]:
        with self._tx() as con:
            self._ensure_staking_pools(con)
            pool = con.execute("SELECT token, min_stake, base_apy_bps FROM earn_staking_pools WHERE pool_id = ? AND status = 'active'", (pool_id,)).fetchone()
        if not pool:
            raise EarnError("pool_not_found")
        try:
            raw = Decimal(str(amount))
            if not raw.is_finite() or raw <= 0 or raw != raw.quantize(_THC_SCALE):
                raise ValueError
        except (InvalidOperation, ValueError, TypeError):
            raise EarnError("invalid_stake_amount")
        if raw < Decimal(pool["min_stake"]):
            raise EarnError("below_minimum_stake")
        if term not in _THC_STAKE_TERMS:
            raise EarnError("invalid_stake_term")
        fee = self.staking_fee(raw)
        return {
            "pool_id": pool_id, "token": pool["token"], "amount": str(raw.quantize(_THC_SCALE)),
            "fee": str(fee), "total_debit": str(raw + fee),
            "unstake_net": str(raw - fee), "fee_bps": _STAKING_FEE_BPS,
            "fee_policy_version": _STAKING_FEE_POLICY,
            "fee_destination": _STAKING_FEE_RESERVE if pool["token"] == "THC" else "pythia_thr_staking_fee_reserve",
            "execution_enabled": pool["token"] == "THC",
            "term": term, "term_months": _THC_STAKE_TERMS[term],
            "estimated_unlock_at": _stake_unlock_at(int(time.time()), term),
            "illustrative_apy": str(Decimal(_THC_FLEX_ILLUSTRATIVE_APY_BPS if pool["token"] == "THC" and term == "flex" else pool["base_apy_bps"]) / 100),
        }

    def create_stake(
        self, earn_user_id: str, pool_id: str, amount: str,
        idempotency_key: str = "", accepted_fee: str | None = None,
        term: str = "flex",
    ) -> dict[str, Any]:
        try:
            amt = Decimal(str(amount)).quantize(_THC_SCALE, rounding=ROUND_DOWN)
            if not amt.is_finite() or amt <= 0:
                raise ValueError
        except (TypeError, ValueError, InvalidOperation):
            raise EarnError("invalid_stake_amount")
        if term not in _THC_STAKE_TERMS:
            raise EarnError("invalid_stake_term")
        with self._tx() as con:
            self._ensure_staking_pools(con)
            if idempotency_key:
                existing = con.execute(
                    """SELECT sp.*, p.token FROM earn_staking_positions sp
                       JOIN earn_staking_pools p ON p.pool_id = sp.pool_id
                       WHERE sp.idempotency_key = ? AND sp.earn_user_id = ?""",
                    (idempotency_key, earn_user_id),
                ).fetchone()
                if existing:
                    if (existing["pool_id"] != pool_id or
                            Decimal(existing["amount"]) != amt or
                            existing["term"] != term):
                        raise EarnError("stake_idempotency_conflict")
                    return {
                        "position_id": existing["position_id"],
                        "pool_id": existing["pool_id"],
                        "token": existing["token"],
                        "amount": existing["amount"],
                        "status": existing["status"],
                        "staked_at": existing["staked_at"],
                        "wallet_address": existing["wallet_address"],
                        "wallet_tx_id": existing["wallet_tx_id"],
                        "fee": str(self.staking_fee(Decimal(existing["amount"]))) if existing["fee_policy_version"] == _STAKING_FEE_POLICY else "0.000000",
                        "fee_destination": _STAKING_FEE_RESERVE,
                        "term": existing["term"], "unlock_at": existing["unlock_at"],
                    }
            pool = con.execute(
                "SELECT * FROM earn_staking_pools WHERE pool_id = ? AND status = 'active'",
                (pool_id,),
            ).fetchone()
            if not pool:
                raise EarnError("pool_not_found")
            if amt < Decimal(pool["min_stake"]):
                raise EarnError("below_minimum_stake")
            link = con.execute(
                "SELECT wallet_address FROM earn_wallet_links WHERE earn_user_id = ?",
                (earn_user_id,),
            ).fetchone()
            token = pool["token"]
            if token == "THR" and not link:
                raise EarnError("wallet_not_linked")
            wallet_address = link["wallet_address"] if link else ""
            wallet_tx_id = None
            if token == "THR":
                # An Earn cookie alone cannot authorize a linked wallet debit.
                # This invariant also protects callers bypassing the HTTP route.
                raise EarnError("thr_stake_requires_signed_wallet_intent")
            elif token == "THC":
                available = self._available_thc_for_staking(con, earn_user_id)
                fee = self.staking_fee(amt)
                if accepted_fee != str(fee):
                    raise EarnError("staking_fee_quote_required")
                if available < amt + fee:
                    raise EarnError("insufficient_thc_balance")
            now = int(time.time())
            unlock_at = _stake_unlock_at(now, term)
            position_id = "pos_" + secrets.token_urlsafe(18)
            con.execute(
                """INSERT INTO earn_staking_positions
                   (position_id, pool_id, earn_user_id, wallet_address,
                    amount, status, staked_at, wallet_tx_id, idempotency_key,
                    fee_policy_version, term, unlock_at)
                   VALUES (?,?,?,?,?,'active',?,?,?,?,?,?)""",
                (
                    position_id, pool_id, earn_user_id,
                    wallet_address, str(amt), now, wallet_tx_id,
                    idempotency_key or None, _STAKING_FEE_POLICY, term, unlock_at,
                ),
            )
            if token == "THC":
                con.execute(
                    """INSERT INTO earn_staking_fees
                       (position_id, action, earn_user_id, token, amount, fee_bps,
                        reserve_account, policy_version, created_at)
                       VALUES (?, 'stake', ?, 'THC', ?, ?, ?, ?, ?)""",
                    (position_id, earn_user_id, str(fee), _STAKING_FEE_BPS,
                     _STAKING_FEE_RESERVE, _STAKING_FEE_POLICY, now),
                )
            return {
                "position_id": position_id,
                "pool_id": pool_id,
                "token": token,
                "amount": str(amt),
                "status": "active",
                "staked_at": now,
                "wallet_address": wallet_address,
                "wallet_tx_id": wallet_tx_id,
                "fee": str(fee), "fee_destination": _STAKING_FEE_RESERVE,
                "term": term, "unlock_at": unlock_at,
            }

    def request_unstake(
        self, earn_user_id: str, position_id: str, accepted_fee: str | None = None,
    ) -> dict[str, Any]:
        with self._tx() as con:
            row = con.execute(
                """SELECT sp.*, p.token FROM earn_staking_positions sp
                   JOIN earn_staking_pools p ON p.pool_id = sp.pool_id
                   WHERE sp.position_id = ? AND sp.earn_user_id = ?""",
                (position_id, earn_user_id),
            ).fetchone()
            if not row:
                raise EarnError("position_not_found")
            if row["status"] == "unstaked":
                prior_fee = con.execute("SELECT amount FROM earn_staking_fees WHERE position_id=? AND action='unstake'", (position_id,)).fetchone()
                return {
                    "position_id": position_id,
                    "status": "unstaked",
                    "unstake_requested_at": row["unstake_requested_at"],
                    "unstake_tx_id": None,
                    "fee": prior_fee["amount"] if prior_fee else "0.000000",
                }
            if row["status"] != "active":
                raise EarnError("position_not_found")
            now = int(time.time())
            if row["token"] == "THC" and row["unlock_at"] is not None and now < row["unlock_at"]:
                raise EarnError("stake_locked_until_maturity")
            amt = Decimal(row["amount"])
            unstake_tx_id = None
            if row["token"] == "THR":
                unstake_tx_id = self._credit_wallet_for_unstake(
                    row["wallet_address"], amt, row["wallet_tx_id"],
                )
            elif row["fee_policy_version"] == _STAKING_FEE_POLICY:
                fee = self.staking_fee(amt)
                if accepted_fee != str(fee):
                    raise EarnError("staking_fee_quote_required")
                con.execute(
                    """INSERT INTO earn_staking_fees
                       (position_id, action, earn_user_id, token, amount, fee_bps,
                        reserve_account, policy_version, created_at)
                       VALUES (?, 'unstake', ?, 'THC', ?, ?, ?, ?, ?)""",
                    (position_id, earn_user_id, str(fee), _STAKING_FEE_BPS,
                     _STAKING_FEE_RESERVE, _STAKING_FEE_POLICY, now),
                )
            con.execute(
                """UPDATE earn_staking_positions
                   SET status = 'unstaked', unstake_requested_at = ?
                   WHERE position_id = ?""",
                (now, position_id),
            )
            return {
                "position_id": position_id,
                "status": "unstaked",
                "unstake_requested_at": now,
                "unstake_tx_id": unstake_tx_id,
                "fee": str(self.staking_fee(amt)) if row["token"] == "THC" and row["fee_policy_version"] == _STAKING_FEE_POLICY else "0.000000",
            }

    def list_ads(self, placement: str = "earn") -> list[dict[str, Any]]:
        now = int(time.time())
        with self._tx() as con:
            rows = con.execute(
                """SELECT ad_id, title, image_url, target_url, placement,
                          priority, impressions, clicks
                     FROM earn_ads
                    WHERE status = 'active'
                      AND placement = ?
                      AND (expires_at IS NULL OR expires_at > ?)
                 ORDER BY priority DESC, created_at DESC""",
                (placement, now),
            ).fetchall()
            return [dict(r) for r in rows]

    def record_ad_impression(self, ad_id: str) -> None:
        with self._tx() as con:
            con.execute(
                "UPDATE earn_ads SET impressions = impressions + 1 WHERE ad_id = ?",
                (ad_id,),
            )

    def record_ad_click(self, ad_id: str) -> None:
        with self._tx() as con:
            con.execute(
                "UPDATE earn_ads SET clicks = clicks + 1 WHERE ad_id = ?",
                (ad_id,),
            )

    def create_ad(
        self,
        title: str,
        image_url: str,
        target_url: str,
        placement: str = "earn",
        priority: int = 0,
        expires_at: int | None = None,
    ) -> dict[str, Any]:
        ad_id = "ad_" + secrets.token_hex(8)
        now = int(time.time())
        with self._tx() as con:
            con.execute(
                """INSERT INTO earn_ads
                   (ad_id, title, image_url, target_url, placement,
                    priority, status, impressions, clicks, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'active', 0, 0, ?, ?)""",
                (ad_id, title, image_url, target_url, placement,
                 priority, now, expires_at),
            )
        return {"ad_id": ad_id, "title": title, "placement": placement}

    def delete_ad(self, ad_id: str) -> bool:
        with self._tx() as con:
            cur = con.execute(
                "UPDATE earn_ads SET status = 'inactive' WHERE ad_id = ?",
                (ad_id,),
            )
            return cur.rowcount > 0

    # ── Referrals ──────────────────────────────────────────────────────

    def referral_code(self, earn_user_id: str) -> str:
        return earn_user_id

    def referral_stats(self, earn_user_id: str) -> dict[str, Any]:
        with self._tx() as con:
            first = con.execute(
                "SELECT COUNT(*) AS cnt FROM earn_referrals WHERE referrer_id = ?",
                (earn_user_id,),
            ).fetchone()
            second = con.execute(
                """SELECT COUNT(*) AS cnt FROM earn_referrals child
                   JOIN earn_referrals parent
                     ON parent.referred_id = child.referrer_id
                  WHERE parent.referrer_id = ?""",
                (earn_user_id,),
            ).fetchone()
            return {
                "referral_count": first["cnt"],
                "level2_count": second["cnt"],
            }

    def referral_list(self, earn_user_id: str) -> list[dict[str, Any]]:
        with self._tx() as con:
            direct = con.execute(
                """SELECT r.created_at, a.email
                   FROM earn_referrals r
                   JOIN earn_accounts a ON a.earn_user_id = r.referred_id
                   WHERE r.referrer_id = ?
                   ORDER BY r.created_at DESC LIMIT 50""",
                (earn_user_id,),
            ).fetchall()
            second = con.execute(
                """SELECT child.created_at, a.email
                   FROM earn_referrals child
                   JOIN earn_referrals parent
                     ON parent.referred_id = child.referrer_id
                   JOIN earn_accounts a ON a.earn_user_id = child.referred_id
                  WHERE parent.referrer_id = ?
                  ORDER BY child.created_at DESC LIMIT 50""",
                (earn_user_id,),
            ).fetchall()
            return [
                {"level": level, "created_at": row["created_at"],
                 "email_hint": row["email"][:2] + "***"}
                for level, rows in ((1, direct), (2, second))
                for row in rows
            ]

    # ── Ad Marketplace — Campaigns ────────────────────────────────────

    def create_campaign(
        self,
        advertiser_id: str,
        name: str,
        campaign_type: str = "cpm",
        bid_amount: str = "1.000000",
        daily_budget: str = "0",
        total_budget: str = "0",
        country_targets: str = "",
        placement: str = "earn",
        starts_at: int | None = None,
        ends_at: int | None = None,
    ) -> dict[str, Any]:
        if campaign_type not in ("cpm", "cpc"):
            raise EarnError("invalid_campaign_type")
        bid = Decimal(bid_amount)
        if bid <= 0:
            raise EarnError("bid_must_be_positive")
        campaign_id = "camp_" + secrets.token_hex(8)
        now = int(time.time())
        with self._tx() as con:
            user = con.execute(
                "SELECT 1 FROM earn_accounts WHERE earn_user_id = ?",
                (advertiser_id,),
            ).fetchone()
            if not user:
                raise EarnError("advertiser_not_found")
            con.execute(
                """INSERT INTO earn_ad_campaigns
                   (campaign_id, advertiser_id, name, campaign_type,
                    bid_amount, daily_budget, total_budget,
                    country_targets, placement, status,
                    impressions, clicks, spent,
                    created_at, updated_at, starts_at, ends_at)
                   VALUES (?,?,?,?,?,?,?,?,?,'pending_review',
                           0,0,'0.000000',?,?,?,?)""",
                (campaign_id, advertiser_id, name, campaign_type,
                 str(bid.quantize(_THC_SCALE)),
                 str(Decimal(daily_budget).quantize(_THC_SCALE)),
                 str(Decimal(total_budget).quantize(_THC_SCALE)),
                 country_targets, placement,
                 now, now, starts_at, ends_at),
            )
        return {
            "campaign_id": campaign_id,
            "name": name,
            "status": "pending_review",
        }

    def get_campaign(self, campaign_id: str) -> dict[str, Any] | None:
        with self._tx() as con:
            row = con.execute(
                "SELECT * FROM earn_ad_campaigns WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_advertiser_campaigns(
        self, advertiser_id: str,
    ) -> list[dict[str, Any]]:
        with self._tx() as con:
            rows = con.execute(
                """SELECT * FROM earn_ad_campaigns
                   WHERE advertiser_id = ?
                   ORDER BY created_at DESC""",
                (advertiser_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    _CAMPAIGN_UPDATABLE = frozenset((
        "name", "bid_amount", "daily_budget", "total_budget",
        "country_targets", "starts_at", "ends_at",
    ))
    _CAMPAIGN_EDITABLE_STATES = frozenset((
        "pending_review", "approved", "paused",
    ))

    def update_campaign(
        self, campaign_id: str, advertiser_id: str, **kwargs: Any,
    ) -> dict[str, Any]:
        fields = {
            k: v for k, v in kwargs.items()
            if k in self._CAMPAIGN_UPDATABLE and v is not None
        }
        if not fields:
            raise EarnError("nothing_to_update")
        for money_col in ("bid_amount", "daily_budget", "total_budget"):
            if money_col in fields:
                fields[money_col] = str(
                    Decimal(fields[money_col]).quantize(_THC_SCALE),
                )
        if "bid_amount" in fields and Decimal(fields["bid_amount"]) <= 0:
            raise EarnError("bid_must_be_positive")
        now = int(time.time())
        fields["updated_at"] = now
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        vals = list(fields.values())
        with self._tx() as con:
            row = con.execute(
                "SELECT status FROM earn_ad_campaigns WHERE campaign_id = ? AND advertiser_id = ?",
                (campaign_id, advertiser_id),
            ).fetchone()
            if not row:
                raise EarnError("campaign_not_found")
            if row["status"] not in self._CAMPAIGN_EDITABLE_STATES:
                raise EarnError("campaign_not_editable")
            con.execute(
                f"UPDATE earn_ad_campaigns SET {set_clause} WHERE campaign_id = ?",
                vals + [campaign_id],
            )
        return {"campaign_id": campaign_id, "updated": True}

    def pause_campaign(
        self, campaign_id: str, advertiser_id: str,
    ) -> dict[str, Any]:
        now = int(time.time())
        with self._tx() as con:
            row = con.execute(
                "SELECT status FROM earn_ad_campaigns WHERE campaign_id = ? AND advertiser_id = ?",
                (campaign_id, advertiser_id),
            ).fetchone()
            if not row:
                raise EarnError("campaign_not_found")
            if row["status"] != "active":
                raise EarnError("only_active_campaigns_can_pause")
            con.execute(
                "UPDATE earn_ad_campaigns SET status = 'paused', updated_at = ? WHERE campaign_id = ?",
                (now, campaign_id),
            )
        return {"campaign_id": campaign_id, "status": "paused"}

    def resume_campaign(
        self, campaign_id: str, advertiser_id: str,
    ) -> dict[str, Any]:
        now = int(time.time())
        with self._tx() as con:
            row = con.execute(
                "SELECT status FROM earn_ad_campaigns WHERE campaign_id = ? AND advertiser_id = ?",
                (campaign_id, advertiser_id),
            ).fetchone()
            if not row:
                raise EarnError("campaign_not_found")
            if row["status"] != "paused":
                raise EarnError("only_paused_campaigns_can_resume")
            con.execute(
                "UPDATE earn_ad_campaigns SET status = 'active', updated_at = ? WHERE campaign_id = ?",
                (now, campaign_id),
            )
        return {"campaign_id": campaign_id, "status": "active"}

    # ── Ad Marketplace — Creatives ────────────────────────────────────

    def add_creative(
        self,
        campaign_id: str,
        advertiser_id: str,
        title: str,
        image_url: str,
        target_url: str,
    ) -> dict[str, Any]:
        creative_id = "crtv_" + secrets.token_hex(8)
        now = int(time.time())
        with self._tx() as con:
            row = con.execute(
                "SELECT 1 FROM earn_ad_campaigns WHERE campaign_id = ? AND advertiser_id = ?",
                (campaign_id, advertiser_id),
            ).fetchone()
            if not row:
                raise EarnError("campaign_not_found")
            con.execute(
                """INSERT INTO earn_ad_creatives
                   (creative_id, campaign_id, title, image_url,
                    target_url, status, created_at)
                   VALUES (?,?,?,?,?,'pending_review',?)""",
                (creative_id, campaign_id, title, image_url,
                 target_url, now),
            )
        return {
            "creative_id": creative_id,
            "campaign_id": campaign_id,
            "status": "pending_review",
        }

    def list_creatives(
        self, campaign_id: str, advertiser_id: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._tx() as con:
            if advertiser_id:
                owner = con.execute(
                    "SELECT 1 FROM earn_ad_campaigns WHERE campaign_id = ? AND advertiser_id = ?",
                    (campaign_id, advertiser_id),
                ).fetchone()
                if not owner:
                    raise EarnError("campaign_not_found")
            rows = con.execute(
                "SELECT * FROM earn_ad_creatives WHERE campaign_id = ? ORDER BY created_at DESC",
                (campaign_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Ad Marketplace — Moderation ───────────────────────────────────

    def moderate_campaign(
        self, campaign_id: str, action: str, reason: str = "",
    ) -> dict[str, Any]:
        if action not in ("approve", "reject"):
            raise EarnError("invalid_moderation_action")
        now = int(time.time())
        with self._tx() as con:
            row = con.execute(
                "SELECT status FROM earn_ad_campaigns WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            if not row:
                raise EarnError("campaign_not_found")
            if action == "approve":
                con.execute(
                    "UPDATE earn_ad_campaigns SET status = 'approved', updated_at = ? WHERE campaign_id = ?",
                    (now, campaign_id),
                )
                return {"campaign_id": campaign_id, "status": "approved"}
            con.execute(
                "UPDATE earn_ad_campaigns SET status = 'rejected', reject_reason = ?, updated_at = ? WHERE campaign_id = ?",
                (reason, now, campaign_id),
            )
            return {"campaign_id": campaign_id, "status": "rejected"}

    def moderate_creative(
        self, creative_id: str, action: str, reason: str = "",
    ) -> dict[str, Any]:
        if action not in ("approve", "reject"):
            raise EarnError("invalid_moderation_action")
        with self._tx() as con:
            row = con.execute(
                "SELECT status FROM earn_ad_creatives WHERE creative_id = ?",
                (creative_id,),
            ).fetchone()
            if not row:
                raise EarnError("creative_not_found")
            if action == "approve":
                con.execute(
                    "UPDATE earn_ad_creatives SET status = 'approved' WHERE creative_id = ?",
                    (creative_id,),
                )
                return {"creative_id": creative_id, "status": "approved"}
            con.execute(
                "UPDATE earn_ad_creatives SET status = 'rejected', reject_reason = ? WHERE creative_id = ?",
                (reason, creative_id),
            )
            return {"creative_id": creative_id, "status": "rejected"}

    # ── Ad Marketplace — Escrow Accounting ────────────────────────────
    #
    # Escrow deposits and refunds follow the wallet-signed intent model:
    #   1. Client requests an intent (server issues nonce + idempotency key)
    #   2. PWA/APK shows biometric/PIN/passkey approval gate
    #   3. Wallet signs the intent payload locally
    #   4. Client submits signed intent to execute endpoint
    #   5. Server verifies nonce is unused, idempotency key is fresh,
    #      wallet is linked, and signature covers the exact payload
    #   6. Atomic: debit wallet ledger → credit escrow (or reverse for refund)
    #
    # The server NEVER receives or stores the user's private key, PIN,
    # biometric data, send_secret, or pledge secret.
    #
    # Pythia pool accounting remains separate — no auto-conversion of
    # CPX/TimeWall rewards into THR, staking, or pool liquidity.
    # BTC payouts are never marked paid without a real broadcast tx hash.

    def escrow_create_intent(
        self,
        earn_user_id: str,
        campaign_id: str,
        action: str,
        amount: str,
    ) -> dict[str, Any]:
        if action not in ("deposit", "refund"):
            raise EarnError("invalid_escrow_action")
        amt = Decimal(amount).quantize(_THC_SCALE)
        if amt <= 0:
            raise EarnError("amount_must_be_positive")
        now = int(time.time())
        intent_id = "esci_" + secrets.token_urlsafe(18)
        nonce = secrets.token_urlsafe(24)
        idem_key = secrets.token_hex(16)
        with self._tx() as con:
            camp = con.execute(
                "SELECT advertiser_id FROM earn_ad_campaigns WHERE campaign_id = ? AND advertiser_id = ?",
                (campaign_id, earn_user_id),
            ).fetchone()
            if not camp:
                raise EarnError("campaign_not_found")
            link = con.execute(
                "SELECT wallet_address FROM earn_wallet_links WHERE earn_user_id = ?",
                (earn_user_id,),
            ).fetchone()
            wallet_address = link["wallet_address"] if link else None
            if action == "refund":
                bal = self._escrow_balance_in_tx(con, campaign_id)
                if amt > bal:
                    raise EarnError("insufficient_escrow_balance")
            con.execute(
                "DELETE FROM earn_escrow_intents WHERE expires_at < ?",
                (now,),
            )
            con.execute(
                """INSERT INTO earn_escrow_intents
                   (intent_id, earn_user_id, campaign_id, action, amount,
                    nonce, idempotency_key, wallet_address,
                    requires_wallet_sig, expires_at, consumed_at, created_at)
                   VALUES (?,?,?,?,?,?,?,?,1,?,NULL,?)""",
                (intent_id, earn_user_id, campaign_id, action,
                 str(amt), nonce, idem_key, wallet_address,
                 now + _ESCROW_INTENT_TTL, now),
            )
        return {
            "intent_id": intent_id,
            "action": action,
            "campaign_id": campaign_id,
            "amount": str(amt),
            "nonce": nonce,
            "idempotency_key": idem_key,
            "wallet_address": wallet_address,
            "requires_wallet_sig": True,
            "approval": "biometric_passkey",
            "expires_at": now + _ESCROW_INTENT_TTL,
        }

    @staticmethod
    def _verify_escrow_signature(
        intent: dict, wallet_signature: str, public_key: str,
    ) -> bool:
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import ec, utils
            public_key = str(public_key or "").strip().lower()
            wallet_signature = str(wallet_signature or "").strip().lower()
            if len(public_key) < 4 or len(wallet_signature) < 4:
                return False
            signed = {
                "action": str(intent["action"]),
                "amount": str(intent["amount"]),
                "campaign_id": str(intent["campaign_id"]),
                "intent_id": str(intent["intent_id"]),
                "nonce": str(intent["nonce"]),
            }
            if intent.get("wallet_address"):
                signed["wallet_address"] = str(intent["wallet_address"])
            message = json.dumps(signed, sort_keys=True, separators=(",", ":")).encode()
            digest = hashlib.sha256(message).digest()
            pub_bytes = bytes.fromhex(public_key)
            if pub_bytes[0] not in (2, 3, 4):
                return False
            verifier = ec.EllipticCurvePublicKey.from_encoded_point(
                ec.SECP256K1(), pub_bytes,
            )
            sig_bytes = bytes.fromhex(wallet_signature)
            der_signature = utils.encode_dss_signature(
                int.from_bytes(sig_bytes[:32], "big"),
                int.from_bytes(sig_bytes[32:], "big"),
            )
            verifier.verify(
                der_signature, digest,
                ec.ECDSA(utils.Prehashed(hashes.SHA256())),
            )
            return True
        except Exception:
            return False

    def escrow_execute(
        self,
        intent_id: str,
        earn_user_id: str,
        nonce: str,
        wallet_signature: str | None = None,
    ) -> dict[str, Any]:
        now = int(time.time())
        with self._tx() as con:
            intent = con.execute(
                """SELECT * FROM earn_escrow_intents
                   WHERE intent_id = ? AND earn_user_id = ?
                     AND consumed_at IS NULL AND expires_at >= ?""",
                (intent_id, earn_user_id, now),
            ).fetchone()
            if not intent:
                raise EarnError("invalid_or_expired_intent")
            if intent["nonce"] != nonce:
                raise EarnError("nonce_mismatch")
            existing = con.execute(
                "SELECT escrow_id FROM earn_ad_escrow WHERE idempotency_key = ?",
                (intent["idempotency_key"],),
            ).fetchone()
            if existing:
                raise EarnError("duplicate_intent")
            if intent["requires_wallet_sig"]:
                if not wallet_signature:
                    raise EarnError("wallet_signature_required")
                link = con.execute(
                    "SELECT wallet_address, public_key FROM earn_wallet_links WHERE earn_user_id = ?",
                    (earn_user_id,),
                ).fetchone()
                if not link:
                    raise EarnError("wallet_not_linked")
                if intent["wallet_address"] and link["wallet_address"] != intent["wallet_address"]:
                    raise EarnError("wallet_address_mismatch")
                if not self._verify_escrow_signature(
                    dict(intent), wallet_signature, link["public_key"],
                ):
                    raise EarnError("invalid_wallet_signature")
            con.execute(
                "UPDATE earn_escrow_intents SET consumed_at = ? WHERE intent_id = ?",
                (now, intent_id),
            )
            campaign_id = intent["campaign_id"]
            action = intent["action"]
            amt = Decimal(intent["amount"]).quantize(_THC_SCALE)
            escrow_id = "esc_" + secrets.token_hex(8)
            bal = self._escrow_balance_in_tx(con, campaign_id)
            if action == "deposit":
                new_bal = (bal + amt).quantize(_THC_SCALE)
            elif action == "refund":
                if amt > bal:
                    raise EarnError("insufficient_escrow_balance")
                new_bal = (bal - amt).quantize(_THC_SCALE)
            else:
                raise EarnError("invalid_escrow_action")
            signed_fields = {
                "action": str(intent["action"]),
                "amount": str(intent["amount"]),
                "campaign_id": str(intent["campaign_id"]),
                "intent_id": str(intent["intent_id"]),
                "nonce": str(intent["nonce"]),
            }
            if intent["wallet_address"]:
                signed_fields["wallet_address"] = str(intent["wallet_address"])
            payload_hash = hashlib.sha256(
                json.dumps(signed_fields, sort_keys=True, separators=(",", ":")).encode(),
            ).hexdigest()

            wallet_tx_id = None
            pool_receipt_id = None
            pool_position_id = None
            settlement_status = "pending"

            if self._settlement_adapter and action == "deposit":
                wallet_address = (
                    intent["wallet_address"]
                    or (link["wallet_address"] if intent["requires_wallet_sig"] and link else None)
                )
                if wallet_address:
                    from services.wallet_settlement_adapter import (
                        WalletInsufficientBalance, PoolCreditFailed,
                    )
                    try:
                        wallet_tx, pool_receipt = self._settlement_adapter.settle(
                            dict(intent), wallet_address, amt,
                        )
                        wallet_tx_id = wallet_tx.tx_id
                        pool_receipt_id = pool_receipt.pool_event_id
                        pool_position_id = pool_receipt.position_id
                        settlement_status = "settled"
                    except WalletInsufficientBalance:
                        raise EarnError("insufficient_thr_balance")
                    except PoolCreditFailed:
                        raise EarnError("pool_credit_failed")

            con.execute(
                """INSERT INTO earn_ad_escrow
                   (escrow_id, campaign_id, advertiser_id, action,
                    amount, balance_after, note, idempotency_key,
                    intent_id, wallet_tx_id, pool_receipt_id,
                    pool_position_id, payload_hash,
                    settlement_status, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (escrow_id, campaign_id, earn_user_id, action,
                 str(amt), str(new_bal),
                 f"escrow {action} via signed intent",
                 intent["idempotency_key"], intent_id,
                 wallet_tx_id, pool_receipt_id, pool_position_id,
                 payload_hash, settlement_status, now),
            )
        return {
            "escrow_id": escrow_id,
            "action": action,
            "amount": str(amt),
            "balance_after": str(new_bal),
            "idempotency_key": intent["idempotency_key"],
            "payload_hash": payload_hash,
            "settlement_status": settlement_status,
            "wallet_tx_id": wallet_tx_id,
            "pool_receipt_id": pool_receipt_id,
            "pool_position_id": pool_position_id,
        }

    def _escrow_balance_in_tx(
        self, con: sqlite3.Connection, campaign_id: str,
    ) -> Decimal:
        rows = con.execute(
            "SELECT action, amount FROM earn_ad_escrow WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchall()
        bal = Decimal("0")
        for r in rows:
            amt = Decimal(r["amount"]).quantize(_THC_SCALE)
            if r["action"] == "deposit":
                bal += amt
            else:
                bal -= amt
        return bal.quantize(_THC_SCALE)

    def escrow_balance(self, campaign_id: str) -> str:
        with self._tx() as con:
            return str(self._escrow_balance_in_tx(con, campaign_id))

    def _escrow_spend_in_tx(
        self,
        con: sqlite3.Connection,
        campaign_id: str,
        advertiser_id: str,
        amount: Decimal,
    ) -> None:
        bal = self._escrow_balance_in_tx(con, campaign_id)
        new_bal = (bal - amount).quantize(_THC_SCALE)
        if new_bal < 0:
            new_bal = Decimal("0").quantize(_THC_SCALE)
        escrow_id = "esc_" + secrets.token_hex(8)
        now = int(time.time())
        con.execute(
            """INSERT INTO earn_ad_escrow
               (escrow_id, campaign_id, advertiser_id, action,
                amount, balance_after, note, created_at)
               VALUES (?,?,?,'spend',?,?,?,?)""",
            (escrow_id, campaign_id, advertiser_id,
             str(amount.quantize(_THC_SCALE)),
             str(new_bal), "ad spend", now),
        )

    # ── Ad Marketplace — Serving ──────────────────────────────────────

    def serve_campaign_ads(
        self,
        placement: str = "earn",
        country: str = "",
        viewer_id: str | None = None,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        now = int(time.time())
        with self._tx() as con:
            rows = con.execute(
                """SELECT c.campaign_id, c.advertiser_id, c.campaign_type,
                          c.bid_amount, c.total_budget, c.spent,
                          c.daily_budget, c.country_targets,
                          cr.creative_id, cr.title, cr.image_url,
                          cr.target_url
                     FROM earn_ad_campaigns c
                     JOIN earn_ad_creatives cr ON cr.campaign_id = c.campaign_id
                    WHERE c.status = 'active'
                      AND c.placement = ?
                      AND cr.status = 'approved'
                      AND (c.starts_at IS NULL OR c.starts_at <= ?)
                      AND (c.ends_at IS NULL OR c.ends_at > ?)
                 ORDER BY c.bid_amount DESC
                    LIMIT ?""",
                (placement, now, now, limit * 5),
            ).fetchall()
            sorted_rows = sorted(
                rows, key=lambda r: Decimal(r["bid_amount"]), reverse=True,
            )
            results: list[dict[str, Any]] = []
            day_start = now - (now % 86400)
            for r in sorted_rows:
                if len(results) >= limit:
                    break
                targets = str(r["country_targets"] or "").strip()
                if targets:
                    allowed = {
                        c.strip().upper() for c in targets.split(",") if c.strip()
                    }
                    if not country or country.upper() not in allowed:
                        continue
                tb = Decimal(r["total_budget"])
                if tb > 0 and Decimal(r["spent"]) >= tb:
                    continue
                db = Decimal(r["daily_budget"])
                if db > 0:
                    cost_rows = con.execute(
                        """SELECT cost FROM earn_ad_events
                           WHERE campaign_id = ? AND created_at >= ?""",
                        (r["campaign_id"], day_start),
                    ).fetchall()
                    day_spent = sum(
                        (Decimal(cr["cost"]) for cr in cost_rows), Decimal("0"),
                    )
                    if day_spent >= db:
                        continue
                results.append({
                    "campaign_id": r["campaign_id"],
                    "creative_id": r["creative_id"],
                    "title": r["title"],
                    "image_url": r["image_url"],
                    "target_url": r["target_url"],
                    "campaign_type": r["campaign_type"],
                })
            return results

    def record_campaign_event(
        self,
        campaign_id: str,
        creative_id: str,
        event_type: str,
        country: str = "",
        viewer_id: str | None = None,
    ) -> dict[str, Any]:
        if event_type not in ("impression", "click"):
            raise EarnError("invalid_event_type")
        event_id = "evt_" + secrets.token_hex(8)
        now = int(time.time())
        with self._tx() as con:
            camp = con.execute(
                "SELECT campaign_type, bid_amount, advertiser_id, total_budget, spent FROM earn_ad_campaigns WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            if not camp:
                raise EarnError("campaign_not_found")
            bid = Decimal(camp["bid_amount"])
            if camp["campaign_type"] == "cpm" and event_type == "impression":
                cost = (bid / 1000).quantize(_THC_SCALE)
            elif camp["campaign_type"] == "cpc" and event_type == "click":
                cost = bid.quantize(_THC_SCALE)
            else:
                cost = Decimal("0").quantize(_THC_SCALE)
            con.execute(
                """INSERT INTO earn_ad_events
                   (event_id, campaign_id, creative_id, event_type,
                    country, earn_user_id, cost, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (event_id, campaign_id, creative_id, event_type,
                 country, viewer_id,
                 str(cost), now),
            )
            cur_spent = Decimal(camp["spent"])
            new_spent_str = str((cur_spent + cost).quantize(_THC_SCALE))
            if event_type == "impression":
                con.execute(
                    "UPDATE earn_ad_campaigns SET impressions = impressions + 1, spent = ? WHERE campaign_id = ?",
                    (new_spent_str, campaign_id),
                )
            else:
                con.execute(
                    "UPDATE earn_ad_campaigns SET clicks = clicks + 1, spent = ? WHERE campaign_id = ?",
                    (new_spent_str, campaign_id),
                )
            if cost > 0:
                self._escrow_spend_in_tx(
                    con, campaign_id, camp["advertiser_id"], cost,
                )
            tb = Decimal(camp["total_budget"])
            if tb > 0 and Decimal(new_spent_str) >= tb:
                con.execute(
                    "UPDATE earn_ad_campaigns SET status = 'completed' WHERE campaign_id = ?",
                    (campaign_id,),
                )
        return {"event_id": event_id, "cost": str(cost)}

    # ── Ad Marketplace — Reporting ────────────────────────────────────

    def campaign_report(
        self, campaign_id: str, advertiser_id: str,
    ) -> dict[str, Any]:
        with self._tx() as con:
            camp = con.execute(
                "SELECT * FROM earn_ad_campaigns WHERE campaign_id = ? AND advertiser_id = ?",
                (campaign_id, advertiser_id),
            ).fetchone()
            if not camp:
                raise EarnError("campaign_not_found")
            camp_d = dict(camp)
            imps = camp_d["impressions"]
            clicks = camp_d["clicks"]
            ctr = round(clicks / imps * 100, 2) if imps > 0 else 0.0
            bal = str(self._escrow_balance_in_tx(con, campaign_id))
            cutoff = int(time.time()) - 30 * 86400
            daily_rows = con.execute(
                """SELECT (created_at / 86400) AS day_bucket,
                          event_type, cost
                     FROM earn_ad_events
                    WHERE campaign_id = ? AND created_at >= ?
                 ORDER BY day_bucket""",
                (campaign_id, cutoff),
            ).fetchall()
            day_buckets: dict[int, dict[str, Any]] = {}
            for r in daily_rows:
                b = r["day_bucket"]
                if b not in day_buckets:
                    day_buckets[b] = {"imps": 0, "clks": 0, "cost": Decimal("0")}
                if r["event_type"] == "impression":
                    day_buckets[b]["imps"] += 1
                else:
                    day_buckets[b]["clks"] += 1
                day_buckets[b]["cost"] += Decimal(r["cost"])
            events_by_day = [
                {
                    "date": time.strftime(
                        "%Y-%m-%d", time.gmtime(b * 86400),
                    ),
                    "impressions": v["imps"],
                    "clicks": v["clks"],
                    "cost": str(v["cost"].quantize(_THC_SCALE)),
                }
                for b, v in sorted(day_buckets.items())
            ]
            country_rows = con.execute(
                """SELECT COALESCE(NULLIF(country,''), 'unknown') AS cc,
                          COUNT(*) AS cnt
                     FROM earn_ad_events
                    WHERE campaign_id = ?
                 GROUP BY cc ORDER BY cnt DESC""",
                (campaign_id,),
            ).fetchall()
            events_by_country = [
                {"country": r["cc"], "events": r["cnt"]}
                for r in country_rows
            ]
        return {
            "campaign_id": campaign_id,
            "name": camp_d["name"],
            "status": camp_d["status"],
            "impressions": imps,
            "clicks": clicks,
            "ctr": ctr,
            "spent": camp_d["spent"],
            "escrow_balance": bal,
            "events_by_day": events_by_day,
            "events_by_country": events_by_country,
        }

    def campaign_report_daily(
        self, campaign_id: str, advertiser_id: str, days: int = 30,
    ) -> list[dict[str, Any]]:
        with self._tx() as con:
            row = con.execute(
                "SELECT 1 FROM earn_ad_campaigns WHERE campaign_id = ? AND advertiser_id = ?",
                (campaign_id, advertiser_id),
            ).fetchone()
            if not row:
                raise EarnError("campaign_not_found")
            cutoff = int(time.time()) - days * 86400
            rows = con.execute(
                """SELECT (created_at / 86400) AS day_bucket,
                          event_type, cost
                     FROM earn_ad_events
                    WHERE campaign_id = ? AND created_at >= ?
                 ORDER BY day_bucket""",
                (campaign_id, cutoff),
            ).fetchall()
            buckets: dict[int, dict[str, Any]] = {}
            for r in rows:
                b = r["day_bucket"]
                if b not in buckets:
                    buckets[b] = {"imps": 0, "clks": 0, "cost": Decimal("0")}
                if r["event_type"] == "impression":
                    buckets[b]["imps"] += 1
                else:
                    buckets[b]["clks"] += 1
                buckets[b]["cost"] += Decimal(r["cost"])
            return [
                {
                    "date": time.strftime(
                        "%Y-%m-%d", time.gmtime(b * 86400),
                    ),
                    "impressions": v["imps"],
                    "clicks": v["clks"],
                    "cost": str(v["cost"].quantize(_THC_SCALE)),
                }
                for b, v in sorted(buckets.items())
            ]

    # ── Publisher system (isolated from advertiser and Earn identity) ────

    def publisher_register(self, earn_user_id: str, provider: str, label: str = "",
                           provider_pub_id: str | None = None) -> dict[str, Any]:
        publisher_id = "pub_" + secrets.token_urlsafe(18)
        now = int(time.time())
        with self._tx() as con:
            existing = con.execute(
                "SELECT publisher_id FROM earn_publishers WHERE earn_user_id = ? AND provider = ?",
                (earn_user_id, provider),
            ).fetchone()
            if existing:
                raise EarnError("publisher_already_registered")
            con.execute(
                """INSERT INTO earn_publishers
                   (publisher_id, earn_user_id, provider, provider_pub_id, label,
                    status, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (publisher_id, earn_user_id, provider, provider_pub_id,
                 label, "pending_review", now),
            )
        return {"publisher_id": publisher_id, "status": "pending_review"}

    def publisher_get(self, earn_user_id: str) -> list[dict[str, Any]]:
        with self._tx() as con:
            rows = con.execute(
                "SELECT * FROM earn_publishers WHERE earn_user_id = ? ORDER BY created_at DESC",
                (earn_user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def publisher_update_postback(self, publisher_id: str, earn_user_id: str,
                                  postback_url: str, postback_secret: str | None = None) -> dict[str, Any]:
        with self._tx() as con:
            pub = con.execute(
                "SELECT * FROM earn_publishers WHERE publisher_id = ? AND earn_user_id = ?",
                (publisher_id, earn_user_id),
            ).fetchone()
            if not pub:
                raise EarnError("publisher_not_found")
            con.execute(
                "UPDATE earn_publishers SET postback_url = ?, postback_secret = ? WHERE publisher_id = ?",
                (postback_url, postback_secret, publisher_id),
            )
        return {"publisher_id": publisher_id, "postback_url": postback_url}

    def publisher_moderate(self, publisher_id: str, action: str, reason: str | None = None) -> dict[str, Any]:
        now = int(time.time())
        if action not in ("approve", "reject"):
            raise EarnError("invalid_moderation_action")
        with self._tx() as con:
            pub = con.execute(
                "SELECT * FROM earn_publishers WHERE publisher_id = ?",
                (publisher_id,),
            ).fetchone()
            if not pub:
                raise EarnError("publisher_not_found")
            if action == "approve":
                con.execute(
                    "UPDATE earn_publishers SET status = 'active', approved_at = ?, reject_reason = NULL WHERE publisher_id = ?",
                    (now, publisher_id),
                )
            else:
                con.execute(
                    "UPDATE earn_publishers SET status = 'rejected', reject_reason = ? WHERE publisher_id = ?",
                    (reason or "", publisher_id),
                )
        return {"publisher_id": publisher_id, "status": "active" if action == "approve" else "rejected"}

    def publisher_add_placement(self, publisher_id: str, earn_user_id: str,
                                placement_type: str = "survey", site_url: str | None = None) -> dict[str, Any]:
        placement_id = "plc_" + secrets.token_urlsafe(18)
        now = int(time.time())
        with self._tx() as con:
            pub = con.execute(
                "SELECT * FROM earn_publishers WHERE publisher_id = ? AND earn_user_id = ?",
                (publisher_id, earn_user_id),
            ).fetchone()
            if not pub:
                raise EarnError("publisher_not_found")
            con.execute(
                "INSERT INTO earn_publisher_placements (placement_id, publisher_id, placement_type, site_url, created_at) VALUES (?,?,?,?,?)",
                (placement_id, publisher_id, placement_type, site_url, now),
            )
        return {"placement_id": placement_id, "publisher_id": publisher_id}

    def publisher_get_placements(self, publisher_id: str, earn_user_id: str) -> list[dict[str, Any]]:
        with self._tx() as con:
            pub = con.execute(
                "SELECT publisher_id FROM earn_publishers WHERE publisher_id = ? AND earn_user_id = ?",
                (publisher_id, earn_user_id),
            ).fetchone()
            if not pub:
                raise EarnError("publisher_not_found")
            rows = con.execute(
                "SELECT * FROM earn_publisher_placements WHERE publisher_id = ? ORDER BY created_at DESC",
                (publisher_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def publisher_report(self, publisher_id: str, earn_user_id: str) -> dict[str, Any]:
        with self._tx() as con:
            pub = con.execute(
                "SELECT * FROM earn_publishers WHERE publisher_id = ? AND earn_user_id = ?",
                (publisher_id, earn_user_id),
            ).fetchone()
            if not pub:
                raise EarnError("publisher_not_found")
            placements = con.execute(
                "SELECT * FROM earn_publisher_placements WHERE publisher_id = ?",
                (publisher_id,),
            ).fetchall()
        return {
            "publisher_id": publisher_id,
            "provider": dict(pub)["provider"],
            "status": dict(pub)["status"],
            "placements": [dict(p) for p in placements],
        }

    @staticmethod
    def _ledger_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        if "amount" in d:
            d["amount"] = str(Decimal(d["amount"]).quantize(_THC_SCALE))
        d.pop("password_hash", None)
        until = int(d.get("earn_hold_until") or 0)
        if until:
            left = max(0, until - int(time.time()))
            d["earn_hold_seconds_remaining"] = left
            d["earn_hold_days_remaining"] = (left + 86399) // 86400
            d["earn_hold_phase"] = (
                "cancelled" if d.get("state") == "reversed" else
                "released" if d.get("earn_hold_released_at") else
                "waiting" if left else "due"
            )
            d["earn_pending_reason"] = (
                "provider_reversed" if d.get("state") == "reversed" else
                "earn_hold_active" if d["earn_hold_phase"] == "waiting" else
                "earn_hold_due" if d["earn_hold_phase"] == "due" else ""
            )
        return d

    @staticmethod
    def _provider_time(value: int | str | None, *, field: str) -> int | None:
        """Validate provider-supplied timestamps without manufacturing one.

        An ETA is optional evidence, not a product timer.  Callers that do not
        possess a verified provider timestamp must pass None; this method
        intentionally never derives an estimate from the local clock.
        """
        if value is None or value == "":
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            raise EarnError(f"invalid_{field}")
        if parsed <= 0:
            raise EarnError(f"invalid_{field}")
        return parsed

    @staticmethod
    def _provider_status(value: str) -> str:
        status = str(value or "").strip()
        if not status or len(status) > 100:
            raise EarnError("invalid_provider_status")
        return status

    @staticmethod
    def _append_ledger_audit_in_tx(
        con: sqlite3.Connection,
        *,
        entry_id: str,
        event_ref: str,
        event_type: str,
        state: str,
        provider_status: str | None,
        occurred_at: int,
        details: str = "",
    ) -> bool:
        """Append an event once; event_ref is the durable idempotency key."""
        if not event_ref or len(event_ref) > 240:
            raise EarnError("invalid_provider_event_ref")
        existing = con.execute(
            "SELECT 1 FROM thc_ledger_audit WHERE entry_id = ? AND event_ref = ?",
            (entry_id, event_ref),
        ).fetchone()
        if existing:
            return False
        con.execute(
            """INSERT INTO thc_ledger_audit
               (audit_id, entry_id, event_ref, event_type, state,
                provider_status, occurred_at, details)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                "thca_" + secrets.token_urlsafe(18), entry_id, event_ref,
                event_type, state, provider_status, occurred_at, details[:500],
            ),
        )
        return True

    def record_verified_clearance(
        self,
        *,
        source: str,
        source_ref: str,
        event_ref: str,
        new_state: str,
        provider_status: str,
        estimated_clearance_at: int | str | None = None,
        cleared_at: int | str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Apply one *already verified* provider clearance event.

        This is intentionally a store-only operation: there is no browser
        route and no UI action that calls it.  A provider adapter must verify
        its receipt/policy before calling this method.  The original ledger
        entry remains the sole balance record; this function only advances its
        state and writes an immutable audit event.
        """
        if new_state not in ("confirmed", "payable"):
            raise EarnError("invalid_clearance_state")
        if not source or len(source) > 100 or not source_ref or len(source_ref) > 200:
            raise EarnError("invalid_clearance_reference")
        provider_status = self._provider_status(provider_status)
        eta = self._provider_time(estimated_clearance_at, field="estimated_clearance_at")
        provider_cleared_at = self._provider_time(cleared_at, field="cleared_at")
        now = int(time.time())
        with self._tx() as con:
            row = con.execute(
                "SELECT * FROM thc_ledger WHERE source = ? AND source_ref = ?",
                (source, source_ref),
            ).fetchone()
            if not row:
                raise EarnError("thc_entry_not_found")
            # A retransmitted verified clearance is harmless and must not
            # create a second balance entry or a second audit record.
            already_applied = con.execute(
                "SELECT 1 FROM thc_ledger_audit WHERE entry_id = ? AND event_ref = ?",
                (row["entry_id"], event_ref),
            ).fetchone()
            if already_applied:
                return self._ledger_dict(row), False
            if row["state"] == "reversed":
                raise EarnError("invalid_thc_transition")
            if row["state"] == "pending" and row["earn_hold_until"]:
                if new_state != "confirmed":
                    raise EarnError("invalid_thc_transition")
                con.execute(
                    """UPDATE thc_ledger SET provider_status=?,
                       estimated_clearance_at=COALESCE(?, estimated_clearance_at),
                       cleared_at=?, updated_at=? WHERE entry_id=?""",
                    (provider_status, eta, provider_cleared_at or now, now, row["entry_id"]),
                )
                self._append_ledger_audit_in_tx(
                    con, entry_id=row["entry_id"], event_ref=event_ref,
                    event_type="provider_clearance", state="pending",
                    provider_status=provider_status, occurred_at=provider_cleared_at or now,
                )
                return self._ledger_dict(con.execute(
                    "SELECT * FROM thc_ledger WHERE entry_id=?", (row["entry_id"],),
                ).fetchone()), True
            if row["state"] != new_state:
                if new_state not in _THC_TRANSITIONS.get(row["state"], set()):
                    raise EarnError("invalid_thc_transition")
                con.execute(
                    """UPDATE thc_ledger
                       SET state = ?, provider_status = ?,
                           estimated_clearance_at = COALESCE(?, estimated_clearance_at),
                           cleared_at = ?, updated_at = ?
                       WHERE entry_id = ?""",
                    (
                        new_state, provider_status, eta,
                        provider_cleared_at or now, now, row["entry_id"],
                    ),
                )
            else:
                # A distinct verified receipt may enrich provider metadata,
                # but it still cannot duplicate a balance credit.
                con.execute(
                    """UPDATE thc_ledger
                       SET provider_status = ?,
                           estimated_clearance_at = COALESCE(?, estimated_clearance_at),
                           cleared_at = COALESCE(?, cleared_at), updated_at = ?
                       WHERE entry_id = ?""",
                    (provider_status, eta, provider_cleared_at, now, row["entry_id"]),
                )
            self._append_ledger_audit_in_tx(
                con,
                entry_id=row["entry_id"],
                event_ref=event_ref,
                event_type="provider_clearance",
                state=new_state,
                provider_status=provider_status,
                occurred_at=provider_cleared_at or now,
            )
            updated = con.execute(
                "SELECT * FROM thc_ledger WHERE entry_id = ?", (row["entry_id"],),
            ).fetchone()
            return self._ledger_dict(updated), True

    # ── BitcoTasks receipt handling ───────────────────────────────────────

    def record_bitcotasks_receipt(
        self,
        *,
        trans_id: str,
        provider_user_id: str,
        status: int,
        reward_thc: str,
        payout_usd: str = "",
        offer_name: str = "",
        offer_type: str = "",
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        """Record one signed BitcoTasks transaction atomically.

        BitcoTasks sends a credit as status 1 and a chargeback as status 2.
        Its configured reward is already denominated in THC; we do not infer
        or re-price it from USD at callback time.
        """
        if status not in (1, 2) or not trans_id or len(trans_id) > 200:
            raise EarnError("invalid_bitcotasks_receipt")
        if not provider_user_id or len(provider_user_id) > 32:
            raise EarnError("invalid_bitcotasks_user")
        try:
            amount = Decimal(str(reward_thc)).quantize(_THC_SCALE, rounding=ROUND_DOWN)
            if amount < 0:
                raise ValueError
        except (TypeError, ValueError, InvalidOperation):
            raise EarnError("invalid_bitcotasks_amount")
        now = int(time.time())
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        with self._tx() as con:
            identity = con.execute(
                """SELECT earn_user_id FROM earn_provider_identities
                   WHERE provider = 'bitcotasks' AND provider_user_id = ?""",
                (provider_user_id,),
            ).fetchone()
            if not identity:
                raise EarnError("unknown_provider_user")
            uid = identity["earn_user_id"]
            prior = con.execute(
                "SELECT * FROM bitcotasks_receipts WHERE trans_id = ?",
                (trans_id,),
            ).fetchone()
            if prior:
                if prior["earn_user_id"] != uid:
                    raise EarnError("bitcotasks_receipt_conflict")
                if prior["status"] == status:
                    return dict(prior), False
                if status != 2:
                    raise EarnError("invalid_bitcotasks_transition")
                con.execute(
                    """UPDATE bitcotasks_receipts
                       SET status = 2, received_at = ?, payload = ?
                       WHERE trans_id = ?""",
                    (now, payload_json, trans_id),
                )
                if prior["thc_entry_id"]:
                    self._reverse_thc_in_tx(con, prior["thc_entry_id"])
                return dict(con.execute(
                    "SELECT * FROM bitcotasks_receipts WHERE trans_id = ?",
                    (trans_id,),
                ).fetchone()), True

            # A lone chargeback has no credit to reverse; store it only to
            # make retries harmless and to block a later forged credit.
            entry_id = None
            if status == 1:
                if amount <= 0:
                    raise EarnError("invalid_bitcotasks_amount")
                entry_id = "thc_" + secrets.token_urlsafe(18)
                con.execute(
                    """INSERT INTO thc_ledger
                       (entry_id, earn_user_id, source, source_ref, amount,
                        state, note, created_at, updated_at)
                       VALUES (?,?,?,?,?,'pending',?,?,?)""",
                    (
                        entry_id, uid, "bitcotasks", trans_id, str(amount),
                        f"{offer_type}:{offer_name}"[:300], now, now,
                    ),
                )
            con.execute(
                """INSERT INTO bitcotasks_receipts
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    trans_id, uid, status, str(amount), str(payout_usd),
                    str(offer_name)[:500], str(offer_type)[:100], entry_id,
                    now, payload_json,
                ),
            )
            if entry_id:
                self._attach_earn_hold_in_tx(con, entry_id, now)
            return dict(con.execute(
                "SELECT * FROM bitcotasks_receipts WHERE trans_id = ?", (trans_id,),
            ).fetchone()), True

    # ── PureSpectrum receipt handling ────────────────────────────────────

    def record_pure_receipt(
        self,
        *,
        trans_id: str,
        provider_user_id: str,
        status: int,
        reward_thc: str,
        payout_usd: str = "",
        survey_id: str = "",
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        """Record one PureSpectrum S2S completion or reversal.

        Status 1 = completion (credit), status 2 = reversal (chargeback).
        Reward is denominated in THC via the conversion rate.
        """
        if status not in (1, 2) or not trans_id or len(trans_id) > 200:
            raise EarnError("invalid_pure_receipt")
        if not provider_user_id or len(provider_user_id) > 32:
            raise EarnError("invalid_pure_user")
        try:
            amount = Decimal(str(reward_thc)).quantize(_THC_SCALE, rounding=ROUND_DOWN)
            if amount < 0:
                raise ValueError
        except (TypeError, ValueError, InvalidOperation):
            raise EarnError("invalid_pure_amount")
        now = int(time.time())
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        with self._tx() as con:
            identity = con.execute(
                """SELECT earn_user_id FROM earn_provider_identities
                   WHERE provider = 'pure' AND provider_user_id = ?""",
                (provider_user_id,),
            ).fetchone()
            if not identity:
                raise EarnError("unknown_provider_user")
            uid = identity["earn_user_id"]
            prior = con.execute(
                "SELECT * FROM pure_receipts WHERE trans_id = ?",
                (trans_id,),
            ).fetchone()
            if prior:
                if prior["earn_user_id"] != uid:
                    raise EarnError("pure_receipt_conflict")
                if prior["status"] == status:
                    return dict(prior), False
                if status != 2:
                    raise EarnError("invalid_pure_transition")
                con.execute(
                    """UPDATE pure_receipts
                       SET status = 2, received_at = ?, payload = ?
                       WHERE trans_id = ?""",
                    (now, payload_json, trans_id),
                )
                if prior["thc_entry_id"]:
                    self._reverse_thc_in_tx(con, prior["thc_entry_id"])
                return dict(con.execute(
                    "SELECT * FROM pure_receipts WHERE trans_id = ?",
                    (trans_id,),
                ).fetchone()), True

            entry_id = None
            if status == 1:
                if amount <= 0:
                    raise EarnError("invalid_pure_amount")
                entry_id = "thc_" + secrets.token_urlsafe(18)
                con.execute(
                    """INSERT INTO thc_ledger
                       (entry_id, earn_user_id, source, source_ref, amount,
                        state, note, created_at, updated_at)
                       VALUES (?,?,?,?,?,'pending',?,?,?)""",
                    (
                        entry_id, uid, "pure", trans_id, str(amount),
                        f"survey:{survey_id}"[:300], now, now,
                    ),
                )
            con.execute(
                """INSERT INTO pure_receipts
                   (trans_id, earn_user_id, status, amount_thc, payout_usd,
                    survey_id, thc_entry_id, received_at, payload)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    trans_id, uid, status, str(amount), str(payout_usd),
                    str(survey_id)[:200], entry_id, now, payload_json,
                ),
            )
            if entry_id:
                self._attach_earn_hold_in_tx(con, entry_id, now)
            return dict(con.execute(
                "SELECT * FROM pure_receipts WHERE trans_id = ?", (trans_id,),
            ).fetchone()), True

    def record_timewall_receipt(
        self,
        *,
        event_id: str,
        provider_user_id: str,
        revenue_raw: str,
        event_type: str = "",
        reason: str = "",
        offer_name: str = "",
        offer_detail: str = "",
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        """Record one verified TimeWall event as a pending THC receipt.

        TimeWall's signed callback supplies revenue in the exact string form
        received from its query parameter.  We preserve that raw value for
        audit/hash purposes and convert it with the configured placement rate;
        no UI or browser action can clear the resulting ledger entry.
        """
        if not event_id or len(event_id) > 200:
            raise EarnError("invalid_timewall_event")
        if not provider_user_id or len(provider_user_id) > 32:
            raise EarnError("invalid_timewall_user")
        # TimeWall sends a signed, zero-value Install milestone before the
        # first paid game level. Acknowledge its progress without fabricating
        # a THC credit, clearance hold, revenue allocation, or leaderboard score.
        try:
            revenue_decimal = Decimal(str(revenue_raw))
            if not revenue_decimal.is_finite() or revenue_decimal < 0:
                raise EarnError("invalid_timewall_revenue")
        except (InvalidOperation, TypeError) as exc:
            raise EarnError("invalid_timewall_revenue") from exc
        if revenue_decimal == 0:
            return self.record_timewall_zero_milestone(
                event_id=event_id, provider_user_id=provider_user_id,
                revenue_raw=revenue_raw, event_type=event_type, reason=reason,
                offer_name=offer_name, offer_detail=offer_detail, payload=payload,
            )
        conversion_raw = os.getenv("TIMEWALL_THC_CONVERSION", "670")
        allow_decimals = os.getenv("TIMEWALL_ALLOW_DECIMALS", "0") == "1"
        ledger_amount = timewall_reward_amount(
            revenue_raw, conversion_raw=conversion_raw,
            allow_decimals=allow_decimals,
        )
        from services.earn_revenue_allocation import allocate_timewall_revenue
        allocation = allocate_timewall_revenue(revenue_raw)
        now = int(time.time())
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        with self._tx() as con:
            identity = con.execute(
                """SELECT earn_user_id FROM earn_provider_identities
                   WHERE provider = 'timewall' AND provider_user_id = ?""",
                (provider_user_id,),
            ).fetchone()
            if not identity:
                raise EarnError("unknown_provider_user")
            uid = identity["earn_user_id"]
            prior = con.execute(
                "SELECT * FROM timewall_receipts WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if prior:
                if (prior["earn_user_id"] != uid or
                        Decimal(prior["revenue_raw"]) != Decimal(str(revenue_raw))):
                    raise EarnError("timewall_receipt_conflict")
                return dict(prior), False
            entry_id = "thc_" + secrets.token_urlsafe(18)
            con.execute(
                """INSERT INTO thc_ledger
                   (entry_id, earn_user_id, source, source_ref, amount,
                    state, note, provider_status, received_at, created_at, updated_at)
                   VALUES (?,?,?,?,?,'pending',?,'received_pending_clearance',?,?,?)""",
                (
                    entry_id, uid, "timewall", event_id, str(ledger_amount),
                    f"{event_type}:{offer_name}"[:300], now, now, now,
                ),
            )
            con.execute(
                """INSERT INTO timewall_receipts
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    event_id, uid, str(revenue_raw), str(ledger_amount),
                    str(event_type)[:100], str(reason)[:500],
                    str(offer_name)[:500], str(offer_detail)[:1000],
                    entry_id, now, payload_json,
                ),
            )
            con.execute(
                """INSERT INTO earn_timewall_revenue_allocations
                   (event_id, provider_revenue_usd, player_share_usd,
                    referral_cap_usd, platform_before_referrals_usd,
                    platform_after_full_referrals_usd, credited_player_thc,
                    conversion_multiplier, conversion_allow_decimals,
                    created_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (event_id, allocation["provider_revenue_usd"],
                 allocation["player_share_usd"], allocation["referral_cap_usd"],
                 allocation["platform_before_referrals_usd"],
                 allocation["platform_after_full_referrals_usd"],
                 str(ledger_amount), str(conversion_raw), int(allow_decimals), now),
            )
            self._append_ledger_audit_in_tx(
                con, entry_id=entry_id,
                event_ref=f"timewall:receipt:{event_id}",
                event_type="provider_receipt", state="pending",
                provider_status="received_pending_clearance", occurred_at=now,
            )
            if entry_id:
                self._attach_earn_hold_in_tx(con, entry_id, now)
            return dict(con.execute(
                "SELECT * FROM timewall_receipts WHERE event_id = ?",
                (event_id,),
            ).fetchone()), True

    def record_timewall_zero_milestone(
        self, *, event_id: str, provider_user_id: str, revenue_raw: str,
        event_type: str, reason: str, offer_name: str, offer_detail: str,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        """Store an authenticated, non-paying milestone exactly once."""
        now = int(time.time())
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        with self._tx() as con:
            identity = con.execute(
                """SELECT earn_user_id FROM earn_provider_identities
                   WHERE provider = 'timewall' AND provider_user_id = ?""",
                (provider_user_id,),
            ).fetchone()
            if not identity:
                raise EarnError("unknown_provider_user")
            uid = identity["earn_user_id"]
            prior = con.execute(
                "SELECT * FROM timewall_receipts WHERE event_id = ?", (event_id,),
            ).fetchone()
            if prior:
                if (prior["earn_user_id"] != uid or
                        Decimal(prior["revenue_raw"]) != 0):
                    raise EarnError("timewall_receipt_conflict")
                return dict(prior), False
            con.execute(
                """INSERT INTO timewall_receipts
                   (event_id, earn_user_id, revenue_raw, amount_thc, event_type,
                    reason, offer_name, offer_detail, thc_entry_id, received_at, payload)
                   VALUES (?,?,?,?,?,?,?,?,NULL,?,?)""",
                (event_id, uid, str(revenue_raw), "0.000000",
                 str(event_type)[:100], str(reason)[:500],
                 str(offer_name)[:500], str(offer_detail)[:1000], now, payload_json),
            )
            return dict(con.execute(
                "SELECT * FROM timewall_receipts WHERE event_id = ?", (event_id,),
            ).fetchone()), True

    def goblins_wood_progress(self, earn_user_id: str) -> dict[str, Any]:
        """Show provider-reported milestones to their owner, never prize eligibility.

        TimeWall signs only the user ID and revenue; the offer title/detail and
        event ID are not cryptographically bound. These records are therefore
        useful for personal progress but cannot determine contest winners.
        """
        with self._tx() as con:
            rows = con.execute(
                """SELECT r.event_id, r.offer_detail, r.revenue_raw,
                          r.amount_thc, r.received_at, l.state
                   FROM timewall_receipts r
                   LEFT JOIN thc_ledger l ON l.entry_id = r.thc_entry_id
                     AND l.earn_user_id = r.earn_user_id
                   WHERE r.earn_user_id = ?
                     AND (lower(r.offer_name) LIKE '%goblins wood%'
                          OR lower(r.offer_detail) LIKE '%goblins wood%')
                   ORDER BY r.received_at DESC, r.event_id DESC LIMIT 100""",
                (earn_user_id,),
            ).fetchall()
        return {
            "verification": "provider_reported_not_contest_eligible",
            "milestones": [
                {"event_id": row["event_id"],
                 "detail": row["offer_detail"],
                 "amount_thc": row["amount_thc"],
                 "received_at": row["received_at"],
                 "state": row["state"] or "progress_only"}
                for row in rows
            ],
        }

    # ── CPX receipt handling ──────────────────────────────────────────────

    def record_cpx_receipt(
        self,
        *,
        trans_id: str,
        cpx_ext_user_id: str,
        status: int,
        amount_local: str,
        amount_usd: str = "",
        offer_id: str = "",
        payload: dict[str, Any],
        estimated_clearance_at: int | str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        if status not in (1, 2) or not trans_id or len(trans_id) > 200:
            raise EarnError("invalid_cpx_receipt")
        try:
            amt_dec = Decimal(str(amount_local)).quantize(_THC_SCALE, rounding=ROUND_DOWN)
            if amt_dec < 0:
                raise ValueError
        except (TypeError, ValueError, InvalidOperation):
            raise EarnError("invalid_cpx_amount")
        amount_local = str(amt_dec)
        # CPX does not currently publish an official clearance ETA in its
        # signed receipt contract, so the route below leaves this as None.
        # A future verified adapter may supply a documented provider value;
        # never derive one from a local policy or browser clock.
        provider_eta = self._provider_time(
            estimated_clearance_at, field="estimated_clearance_at",
        )
        with self._tx() as con:
            user = con.execute(
                "SELECT earn_user_id FROM earn_accounts WHERE cpx_ext_user_id = ?",
                (cpx_ext_user_id,),
            ).fetchone()
            if not user:
                raise EarnError("unknown_external_user")
            uid = user["earn_user_id"]
            prior = con.execute(
                "SELECT * FROM cpx_receipts WHERE trans_id = ?", (trans_id,),
            ).fetchone()
            now = int(time.time())
            payload_json = json.dumps(
                payload, sort_keys=True, separators=(",", ":"),
            )
            if prior:
                if prior["earn_user_id"] != uid:
                    raise EarnError("cpx_receipt_conflict")
                if prior["status"] == status:
                    return dict(prior), False
                if status == 2:
                    con.execute(
                        """UPDATE cpx_receipts
                           SET status = 2, received_at = ?, payload = ?
                           WHERE trans_id = ?""",
                        (now, payload_json, trans_id),
                    )
                    if prior["thc_entry_id"]:
                        try:
                            self._reverse_thc_in_tx(
                                con, prior["thc_entry_id"],
                                provider_status="reversed",
                                reversal_reason=str(
                                    payload.get("reversal_reason") or payload.get("reason") or ""
                                ).strip()[:300] or None,
                                event_ref=f"cpx:reversal:{trans_id}",
                            )
                        except EarnError:
                            pass
                    return dict(
                        con.execute(
                            "SELECT * FROM cpx_receipts WHERE trans_id = ?",
                            (trans_id,),
                        ).fetchone(),
                    ), True
                raise EarnError("invalid_cpx_receipt_transition")

            thc_entry_id = None
            if status == 1:
                thc_entry_id = "thc_" + secrets.token_urlsafe(18)
                con.execute(
                    """INSERT INTO thc_ledger
                       (entry_id, earn_user_id, source, source_ref, amount,
                        state, note, provider_status, received_at,
                        estimated_clearance_at, created_at, updated_at)
                       VALUES (?,?,?,?,?,'pending',?,?,?,?,?,?)""",
                    (
                        thc_entry_id,
                        uid,
                        "cpx_survey",
                        trans_id,
                        str(amount_local),
                        f"offer:{offer_id}" if offer_id else "",
                        "received_pending_clearance",
                        now,
                        provider_eta,
                        now,
                        now,
                    ),
                )
                self._append_ledger_audit_in_tx(
                    con,
                    entry_id=thc_entry_id,
                    event_ref=f"cpx:receipt:{trans_id}",
                    event_type="provider_receipt",
                    state="pending",
                    provider_status="received_pending_clearance",
                    occurred_at=now,
                )

            con.execute(
                """INSERT INTO cpx_receipts
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    trans_id,
                    uid,
                    status,
                    str(amount_local),
                    str(amount_usd),
                    offer_id,
                    thc_entry_id,
                    now,
                    payload_json,
                ),
            )
            if thc_entry_id:
                self._attach_earn_hold_in_tx(con, thc_entry_id, now)
            return dict(
                con.execute(
                    "SELECT * FROM cpx_receipts WHERE trans_id = ?",
                    (trans_id,),
                ).fetchone(),
            ), True

    def _reverse_thc_in_tx(
        self,
        con: sqlite3.Connection,
        entry_id: str,
        *,
        provider_status: str | None = None,
        reversal_reason: str | None = None,
        event_ref: str | None = None,
    ) -> None:
        row = con.execute(
            "SELECT state FROM thc_ledger WHERE entry_id = ?", (entry_id,),
        ).fetchone()
        if not row or row["state"] == "reversed":
            return
        if "reversed" not in _THC_TRANSITIONS.get(row["state"], set()):
            raise EarnError("invalid_thc_transition")
        now = int(time.time())
        con.execute(
            """UPDATE thc_ledger
               SET state = 'reversed', provider_status = COALESCE(?, provider_status),
                   reversal_reason = COALESCE(?, reversal_reason), updated_at = ?
               WHERE entry_id = ?""",
            (provider_status, reversal_reason, now, entry_id),
        )
        if event_ref:
            self._append_ledger_audit_in_tx(
                con,
                entry_id=entry_id,
                event_ref=event_ref,
                event_type="provider_reversal",
                state="reversed",
                provider_status=provider_status,
                occurred_at=now,
                details=reversal_reason or "",
            )


# ── CPX helpers (reused from earn_center pattern) ────────────────────────


def build_cpx_offerwall_url(cpx_ext_user_id: str) -> str:
    app_id = os.getenv("CPX_APP_ID", "").strip()
    app_secret = os.getenv("CPX_APP_SECURE_HASH", "").strip()
    if not app_id or not app_secret:
        raise EarnError("cpx_not_configured")
    secure_hash = hashlib.md5(
        f"{cpx_ext_user_id}-{app_secret}".encode("utf-8"),
    ).hexdigest()
    query = urlencode({
        "app_id": app_id,
        "ext_user_id": cpx_ext_user_id,
        "secure_hash": secure_hash,
    })
    base = os.getenv(
        "CPX_OFFERWALL_URL", "https://offers.cpx-research.com/index.php",
    )
    return f"{base}?{query}"


def build_bitcotasks_offerwall_url(provider_user_id: str) -> str:
    api_key = os.getenv("BITCOTASKS_API_KEY", "").strip()
    if not api_key:
        raise EarnError("bitcotasks_not_configured")
    if not provider_user_id or len(provider_user_id) > 32:
        raise EarnError("invalid_bitcotasks_user")
    return f"https://bitcotasks.com/offerwall/{api_key}/{provider_user_id}"


def verify_bitcotasks_postback_signature(
    sub_id: str, trans_id: str, reward: str, signature: str,
) -> bool:
    """Verify BitcoTasks' documented md5(subId + transId + reward + secret)."""
    secret = os.getenv("BITCOTASKS_SECRET_KEY", "").strip()
    if not secret or not sub_id or not trans_id or not reward or not signature:
        return False
    expected = hashlib.md5(
        f"{sub_id}{trans_id}{reward}{secret}".encode("utf-8"),
    ).hexdigest()
    return hmac.compare_digest(expected, str(signature).strip().lower())


def build_pure_offerwall_url(provider_user_id: str) -> str:
    publisher_id = os.getenv("PURE_PUBLISHER_ID", "").strip()
    if not publisher_id:
        raise EarnError("pure_not_configured")
    if not provider_user_id or len(provider_user_id) > 32:
        raise EarnError("invalid_pure_user")
    query = urlencode({
        "publisherId": publisher_id,
        "countryCode": "en_US",
        "respondentId": provider_user_id,
        "memberId": provider_user_id,
        "currency": "THC",
        "conversion": os.getenv("PURE_THC_CONVERSION", "100"),
    })
    base = os.getenv(
        "PURE_OFFERWALL_URL",
        "https://offerwall.spectrumsurveys.com/publisher_offers",
    )
    return f"{base}?{query}"


def timewall_reward_amount(
    revenue_raw: str, *, conversion_raw: str | None = None,
    allow_decimals: bool | None = None,
) -> Decimal:
    """Validate the same Decimal conversion in preflight and live receipt handling."""
    try:
        revenue = Decimal(str(revenue_raw))
        conversion = Decimal(
            conversion_raw if conversion_raw is not None
            else os.getenv("TIMEWALL_THC_CONVERSION", "670")
        )
        if allow_decimals is None:
            allow_decimals = os.getenv("TIMEWALL_ALLOW_DECIMALS", "0") == "1"
        amount_scale = _THC_SCALE if allow_decimals else Decimal("1")
        rounding = ROUND_DOWN if allow_decimals else ROUND_HALF_UP
        amount = (revenue * conversion).quantize(amount_scale, rounding=rounding)
        if revenue <= 0 or conversion <= 0 or amount <= 0:
            raise ValueError
        # Keep the durable ledger representation at the same six-decimal
        # scale used by balance/history APIs, even when the provider
        # placement itself disallows fractional THC.
        ledger_amount = amount.quantize(_THC_SCALE)
    except (TypeError, ValueError, InvalidOperation):
        raise EarnError("invalid_timewall_revenue")
    return ledger_amount


def build_timewall_offerwall_url(provider_user_id: str) -> str:
    """Build the server-configured TimeWall placement URL.

    Placement parameter names differ by TimeWall account. The Railway-only
    template must therefore contain {userId}; we never guess a URL.
    """
    template = os.getenv("TIMEWALL_PLACEMENT_URL", "").strip()
    if not template:
        raise EarnError("timewall_not_configured")
    if not provider_user_id or len(provider_user_id) > 32:
        raise EarnError("invalid_timewall_user")
    placeholders = ("{UNIQUE_USER_ID}", "{userId}", "{userID}", "{user_ID}", "{user_id}")
    if not template.startswith("https://") or not any(
        placeholder in template for placeholder in placeholders
    ):
        raise EarnError("invalid_timewall_placement")
    encoded_user_id = urlencode({"v": provider_user_id})[2:]
    for placeholder in placeholders:
        template = template.replace(placeholder, encoded_user_id)
    return template


def verify_pure_postback_signature(
    trans_id: str, respondent_id: str, signature: str,
) -> bool:
    """Verify PureSpectrum S2S postback: sha256(transId + respondentId + secret)."""
    secret = os.getenv("PURE_SECRET_KEY", "").strip()
    if not secret or not trans_id or not respondent_id or not signature:
        return False
    expected = hashlib.sha256(
        f"{trans_id}{respondent_id}{secret}".encode("utf-8"),
    ).hexdigest()
    return hmac.compare_digest(expected, str(signature).strip().lower())


def timewall_postback_hash(user_id: str, revenue: str, secret: str) -> str:
    """TimeWall callback formula: sha256(user_ID + revenue + SecretKey)."""
    return hashlib.sha256(
        f"{user_id}{revenue}{secret}".encode("utf-8"),
    ).hexdigest()


def verify_timewall_postback_signature(
    user_id: str, revenue: str, signature: str,
) -> bool:
    secret = os.getenv("TIMEWALL_SECRET_KEY", "").strip()
    if not secret or not user_id or not revenue or not signature:
        return False
    expected = timewall_postback_hash(user_id, revenue, secret)
    return hmac.compare_digest(expected, str(signature).strip().lower())


def timewall_allowed_ips() -> set[str]:
    configured = os.getenv(
        "TIMEWALL_POSTBACK_IPS",
        "18.156.132.55,51.81.120.73,142.111.248.18",
    )
    return {item.strip() for item in configured.split(",") if item.strip()}


def timewall_enforce_ip_allowlist() -> bool:
    """Require the configured provider IP list in addition to the signature.

    TimeWall may deliver callbacks through changing proxy/worker addresses. The
    signed callback is the stable authentication mechanism; IP enforcement is
    available as an explicit extra restriction for deployments that need it.
    """
    return os.getenv("TIMEWALL_POSTBACK_IP_ENFORCE", "0").strip() == "1"


def cpx_postback_hash(trans_id: str, secret: str) -> str:
    """Documented CPX callback formula: md5(trans_id + "-" + CPX_APP_SECURE_HASH)."""
    return hashlib.md5(
        f"{trans_id}-{secret}".encode("utf-8"),
    ).hexdigest()


def verify_cpx_postback_signature(trans_id: str, received_hash: str) -> bool:
    secret = os.getenv("CPX_APP_SECURE_HASH", "").strip()
    if not trans_id or not received_hash or not secret:
        return False
    expected = cpx_postback_hash(trans_id, secret)
    return hmac.compare_digest(expected, received_hash.lower())


_CPX_POSTBACK_IPS = frozenset(ipaddress.ip_address(value) for value in (
    "157.90.97.92", "188.40.3.73", "2a01:4f8:d0a:30ff::2",
))


def cpx_postback_ip_allowed(
    remote_addr: str | None, railway_real_ip: str | None = None,
) -> bool:
    """Match CPX's source address supplied by Railway's ingress.

    ProxyFix(x_for=1) intentionally exposes an offer participant's address
    as request.remote_addr when CPX forwards that address. Railway's own
    X-Real-IP preserves the direct caller to the public endpoint, so it is
    authoritative for this callback. Direct deployments can safely fall back
    to remote_addr.
    """
    candidate = railway_real_ip or remote_addr
    try:
        return ipaddress.ip_address(str(candidate or "")) in _CPX_POSTBACK_IPS
    except ValueError:
        return False


def verify_earn_wallet_proof(
    challenge: dict[str, str], *, wallet_address: str,
    public_key: str, signature: str,
) -> bool:
    """Verify compact secp256k1 proof and bind its public key to THR address.

    The signed payload contains only an expiring server-issued nonce and the
    requested action.  It is never a transferable payment approval.
    """
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec, utils
        from wallet_v1_address_derivation import derive_thronos_address

        public_key = str(public_key or "").strip().lower()
        signature = str(signature or "").strip().lower()
        wallet_address = EarnAccountStore._wallet_address(wallet_address)
        if len(public_key) != 66 or len(signature) != 128:
            return False
        if derive_thronos_address(public_key).upper() != wallet_address:
            return False
        pub_bytes = bytes.fromhex(public_key)
        if pub_bytes[0] not in (2, 3):
            return False
        verifier = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256K1(), pub_bytes)
        signed = {
            "action": str(challenge["action"]),
            "challenge_id": str(challenge["challenge_id"]),
            "expires_at": str(challenge["expires_at"]),
            "nonce": str(challenge["nonce"]),
            "wallet_address": wallet_address,
        }
        # Wallet-link proofs are deliberately distinct from wallet-session
        # proofs.  The PWA/APK only produces this proof after its local
        # WebAuthn/passkey approval gate succeeds.
        if challenge.get("approval"):
            signed["approval"] = str(challenge["approval"])
        message = json.dumps(signed, sort_keys=True, separators=(",", ":")).encode()
        digest = hashlib.sha256(message).digest()
        sig_bytes = bytes.fromhex(signature)
        der_signature = utils.encode_dss_signature(
            int.from_bytes(sig_bytes[:32], "big"), int.from_bytes(sig_bytes[32:], "big"),
        )
        verifier.verify(
            der_signature, digest, ec.ECDSA(utils.Prehashed(hashes.SHA256())),
        )
        return True
    except Exception:
        return False


def _wallet_link_requires_mobile_approval(wallet_address: str) -> bool:
    """Return whether this wallet opted into the existing 3FA device flow.

    3FA is an *additional* approval signal and never replaces the expiring,
    wallet-signed challenge.  Import lazily so Earn can remain available on
    deployments where the optional 3FA blueprint is not installed.
    """
    try:
        from three_factor_auth import check_3fa_required
        return bool(check_3fa_required(wallet_address, action="earn_wallet_link"))
    except Exception:
        return False


def _verified_mobile_wallet_approval(approval_id: str, wallet_address: str) -> bool:
    """Verify a live 3FA approval for a wallet-link request when required."""
    if not approval_id:
        return False
    try:
        from three_factor_auth import verify_3fa_approval
        result = verify_3fa_approval(approval_id, wallet_address)
        return bool(result.get("ok"))
    except Exception:
        return False


# ── Flask route registration ─────────────────────────────────────────────


def register_earn_account_routes(
    app: Any,
    store: EarnAccountStore,
) -> None:
    from flask import jsonify, request

    def _current_user():
        # An explicitly supplied Authorization header is authoritative.  Never
        # fall back to a browser cookie when that Bearer token is invalid or
        # revoked, otherwise a stale API token could silently authenticate as
        # whichever account happens to be open in the browser.
        auth_header = request.headers.get("Authorization", "").strip()
        if auth_header:
            if not auth_header.startswith("Bearer "):
                return None, ""
            token = auth_header.removeprefix("Bearer ").strip()
            return store.user_for_session(token), token

        # Browser pages without an Authorization header use the HttpOnly,
        # same-origin cookie. API consumers use only their Bearer token.
        token = request.cookies.get(_SESSION_COOKIE, "").strip()
        return store.user_for_session(token), token

    def _set_session_cookie(response, token: str):
        response.set_cookie(
            _SESSION_COOKIE,
            token,
            max_age=_SESSION_TTL,
            secure=True,
            httponly=True,
            samesite="Lax",
            path="/",
        )
        return response

    @app.post("/api/earn/register")
    def earn_register():
        data = request.get_json(silent=True) or {}
        ref_code = str(data.get("ref", "")).strip() or None
        try:
            user = store.register(
                str(data.get("email", "")),
                str(data.get("password", "")),
                ref_code=ref_code,
            )
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, **user), 201

    @app.post("/api/earn/login")
    def earn_login():
        data = request.get_json(silent=True) or {}
        try:
            user, token = store.login(
                str(data.get("email", "")),
                str(data.get("password", "")),
            )
        except EarnError as exc:
            code = 429 if "locked" in str(exc) else 401
            return jsonify(ok=False, error=str(exc)), code
        response = jsonify(
            ok=True,
            earn_user_id=user["earn_user_id"],
            email=user["email"],
            access_token=token,
            expires_in=_SESSION_TTL,
        )
        return _set_session_cookie(response, token)

    @app.post("/api/earn/logout")
    def earn_logout():
        user, token = _current_user()
        if user and token:
            store.logout(token)
        response = jsonify(ok=True)
        response.delete_cookie(_SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="Lax")
        return response

    @app.get("/api/earn/me")
    def earn_me():
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        link = store.wallet_link_for_user(user["earn_user_id"])
        return jsonify(
            ok=True,
            earn_user_id=user["earn_user_id"],
            email=user["email"],
            email_verified=bool(user["email_verified"]),
            wallet_address=link["wallet_address"] if link else None,
            loyalty=store.loyalty_status(user["earn_user_id"]),
        )

    @app.post("/api/earn/wallet-link/challenge")
    def earn_wallet_link_challenge():
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        data = request.get_json(silent=True) or {}
        try:
            challenge = store.wallet_link_challenge(
                user["earn_user_id"], str(data.get("wallet_address", "")),
            )
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, **challenge)

    @app.post("/api/earn/wallet-link/complete")
    def earn_wallet_link_complete():
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        data = request.get_json(silent=True) or {}
        challenge_id = str(data.get("challenge_id", ""))
        wallet_address = str(data.get("wallet_address", ""))
        try:
            challenge = store.wallet_challenge_for_proof(
                challenge_id=challenge_id, purpose="link", wallet_address=wallet_address,
                earn_user_id=user["earn_user_id"],
            )
            if not verify_earn_wallet_proof(
                challenge, wallet_address=wallet_address,
                public_key=str(data.get("public_key", "")),
                signature=str(data.get("signature", "")),
            ):
                return jsonify(ok=False, error="invalid_wallet_proof"), 403
            # A registered mobile 3FA device is an extra confirmation channel
            # for desktop/QR pairing.  It supplements, but never replaces,
            # the signed, single-use Earn challenge verified above.
            if _wallet_link_requires_mobile_approval(wallet_address) and not _verified_mobile_wallet_approval(
                str(data.get("mobile_approval_id", "")), wallet_address,
            ):
                return jsonify(ok=False, error="mobile_wallet_approval_required"), 403
            link = store.complete_wallet_link(
                challenge_id=challenge_id, earn_user_id=user["earn_user_id"],
                wallet_address=wallet_address, public_key=str(data.get("public_key", "")),
            )
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, **link)

    @app.post("/api/earn/wallet-session/challenge")
    def earn_wallet_session_challenge():
        data = request.get_json(silent=True) or {}
        try:
            challenge = store.wallet_login_challenge(str(data.get("wallet_address", "")))
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, **challenge)

    @app.post("/api/earn/wallet-session/complete")
    def earn_wallet_session_complete():
        data = request.get_json(silent=True) or {}
        challenge_id = str(data.get("challenge_id", ""))
        wallet_address = str(data.get("wallet_address", ""))
        try:
            challenge = store.wallet_challenge_for_proof(
                challenge_id=challenge_id, purpose="login", wallet_address=wallet_address,
            )
            if not verify_earn_wallet_proof(
                challenge, wallet_address=wallet_address,
                public_key=str(data.get("public_key", "")),
                signature=str(data.get("signature", "")),
            ):
                return jsonify(ok=False, error="invalid_wallet_proof"), 403
            user, token = store.complete_wallet_login(
                challenge_id=challenge_id, wallet_address=wallet_address,
            )
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 401
        # The wallet-proof flow needs no JavaScript-visible bearer token.
        # Keep the session confined to the Secure, HttpOnly cookie.
        response = jsonify(ok=True, earn_user_id=user["earn_user_id"], email=user["email"])
        return _set_session_cookie(response, token)

    @app.get("/api/earn/balance")
    def earn_balance():
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        balance = store.thc_balance(user["earn_user_id"])
        return jsonify(ok=True, currency="THC", **balance)

    @app.get("/api/earn/history")
    def earn_history():
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        entries = store.thc_history(user["earn_user_id"])
        return jsonify(ok=True, entries=entries)

    @app.get("/api/earn/goblins-wood/progress")
    def earn_goblins_wood_progress():
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        response = jsonify(ok=True, **store.goblins_wood_progress(user["earn_user_id"]))
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/earn/history/<entry_id>")
    def earn_receipt_details(entry_id):
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        try:
            details = store.thc_receipt_details(user["earn_user_id"], entry_id)
        except EarnError:
            return jsonify(ok=False, error="receipt_not_found"), 404
        response = jsonify(ok=True, server_now=int(time.time()), **details)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/earn/leaderboard")
    def earn_leaderboard():
        user, _ = _current_user()
        period = request.args.get("period", "monthly")
        data = store.leaderboard(
            caller_user_id=user["earn_user_id"] if user else None,
            period=period,
        )
        response = jsonify(ok=True, **data)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/earn/staking/pools")
    def earn_staking_pools():
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        pools = store.staking_pools()
        return jsonify(ok=True, pools=pools)

    @app.get("/api/earn/staking/positions")
    def earn_staking_positions():
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        positions = store.staking_positions(user["earn_user_id"])
        return jsonify(ok=True, positions=positions)

    @app.get("/api/earn/staking/fee-quote")
    def earn_staking_fee_quote():
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        try:
            quote = store.staking_fee_quote(
                str(request.args.get("pool_id", "")), str(request.args.get("amount", "")),
                term=str(request.args.get("term", "flex")),
            )
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        response = jsonify(ok=True, **quote)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/api/earn/staking/stake")
    def earn_staking_stake():
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        data = request.get_json(silent=True) or {}
        # Earn session authentication does not prove wallet authorization for a
        # specific THR debit. Pause new THR stakes until a signed, expiring
        # wallet intent is verified by the server. Existing unstake remains open.
        requested_pool = str(data.get("pool_id", ""))
        if any(p["pool_id"] == requested_pool and p["token"] == "THR"
               for p in store.staking_pools()):
            return jsonify(ok=False, error="thr_stake_requires_signed_wallet_intent"), 409
        try:
            position = store.create_stake(
                user["earn_user_id"],
                str(data.get("pool_id", "")),
                str(data.get("amount", "")),
                idempotency_key=str(data.get("idempotency_key", "")),
                accepted_fee=data.get("accepted_fee"),
                term=str(data.get("term", "flex")),
            )
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, **position)

    @app.post("/api/earn/staking/unstake")
    def earn_staking_unstake():
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        data = request.get_json(silent=True) or {}
        try:
            result = store.request_unstake(
                user["earn_user_id"],
                str(data.get("position_id", "")),
                accepted_fee=data.get("accepted_fee"),
            )
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, **result)

    @app.get("/api/earn/pools/public")
    def earn_pools_public():
        pools = store.staking_pools()
        public_pools = []
        for p in pools:
            public_pools.append({
                "pool_id": p["pool_id"],
                "token": p["token"],
                "label": p["label"],
                "base_apy": p["base_apy"],
                "boosted_apy": p["boosted_apy"],
                "min_stake": p["min_stake"],
                "total_staked": p["total_staked"],
                "stakers": p["stakers"],
            })
        return jsonify(ok=True, pools=public_pools, last_updated=int(time.time()))

    @app.get("/api/earn/ads")
    def earn_ads():
        placement = request.args.get("placement", "earn")
        if placement not in ("earn", "basketball", "general"):
            return jsonify(ok=False, error="invalid_placement"), 400
        ads = store.list_ads(placement)
        return jsonify(ok=True, ads=ads)

    @app.post("/api/earn/ads/impression")
    def earn_ad_impression():
        data = request.get_json(silent=True) or {}
        ad_id = str(data.get("ad_id", "")).strip()
        if ad_id:
            store.record_ad_impression(ad_id)
        return jsonify(ok=True)

    @app.post("/api/earn/ads/click")
    def earn_ad_click():
        data = request.get_json(silent=True) or {}
        ad_id = str(data.get("ad_id", "")).strip()
        if ad_id:
            store.record_ad_click(ad_id)
        return jsonify(ok=True)

    @app.post("/api/earn/ads/create")
    def earn_ad_create():
        mgmt_token = request.headers.get("X-Admin-Key", "").strip()
        if not mgmt_token or mgmt_token != os.getenv("EARN_MGMT_TOKEN", "").strip():
            return jsonify(ok=False, error="unauthorized"), 403
        data = request.get_json(silent=True) or {}
        title = str(data.get("title", "")).strip()
        image_url = str(data.get("image_url", "")).strip()
        target_url = str(data.get("target_url", "")).strip()
        if not title or not image_url or not target_url:
            return jsonify(ok=False, error="missing_fields"), 400
        placement = str(data.get("placement", "earn")).strip()
        priority = int(data.get("priority", 0))
        expires_at = data.get("expires_at")
        result = store.create_ad(
            title=title,
            image_url=image_url,
            target_url=target_url,
            placement=placement,
            priority=priority,
            expires_at=int(expires_at) if expires_at else None,
        )
        return jsonify(ok=True, **result)

    @app.post("/api/earn/ads/delete")
    def earn_ad_delete():
        mgmt_token = request.headers.get("X-Admin-Key", "").strip()
        if not mgmt_token or mgmt_token != os.getenv("EARN_MGMT_TOKEN", "").strip():
            return jsonify(ok=False, error="unauthorized"), 403
        data = request.get_json(silent=True) or {}
        ad_id = str(data.get("ad_id", "")).strip()
        if not ad_id:
            return jsonify(ok=False, error="missing_ad_id"), 400
        deleted = store.delete_ad(ad_id)
        return jsonify(ok=True, deleted=deleted)

    # ── Ad Marketplace API Routes ─────────────────────────────────────

    @app.post("/api/earn/ads/campaign/create")
    def earn_campaign_create():
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        data = request.get_json(silent=True) or {}
        name = str(data.get("name", "")).strip()
        if not name:
            return jsonify(ok=False, error="missing_name"), 400
        try:
            result = store.create_campaign(
                advertiser_id=user["earn_user_id"],
                name=name,
                campaign_type=str(data.get("campaign_type", "cpm")).strip(),
                bid_amount=str(data.get("bid_amount", "1.000000")).strip(),
                daily_budget=str(data.get("daily_budget", "0")).strip(),
                total_budget=str(data.get("total_budget", "0")).strip(),
                country_targets=str(data.get("country_targets", "")).strip(),
                placement=str(data.get("placement", "earn")).strip(),
                starts_at=int(data["starts_at"]) if data.get("starts_at") else None,
                ends_at=int(data["ends_at"]) if data.get("ends_at") else None,
            )
        except (EarnError, InvalidOperation, ValueError) as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, **result)

    @app.get("/api/earn/ads/campaign/list")
    def earn_campaign_list():
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        campaigns = store.list_advertiser_campaigns(user["earn_user_id"])
        return jsonify(ok=True, campaigns=campaigns)

    @app.get("/api/earn/ads/campaign/<campaign_id>")
    def earn_campaign_get(campaign_id):
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        camp = store.get_campaign(campaign_id)
        if not camp or camp["advertiser_id"] != user["earn_user_id"]:
            return jsonify(ok=False, error="campaign_not_found"), 404
        return jsonify(ok=True, campaign=camp)

    @app.post("/api/earn/ads/campaign/<campaign_id>/update")
    def earn_campaign_update(campaign_id):
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        data = request.get_json(silent=True) or {}
        try:
            result = store.update_campaign(
                campaign_id, user["earn_user_id"], **data,
            )
        except (EarnError, InvalidOperation, ValueError) as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, **result)

    @app.post("/api/earn/ads/campaign/<campaign_id>/pause")
    def earn_campaign_pause(campaign_id):
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        try:
            result = store.pause_campaign(campaign_id, user["earn_user_id"])
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, **result)

    @app.post("/api/earn/ads/campaign/<campaign_id>/resume")
    def earn_campaign_resume(campaign_id):
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        try:
            result = store.resume_campaign(campaign_id, user["earn_user_id"])
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, **result)

    @app.post("/api/earn/ads/campaign/<campaign_id>/creative/add")
    def earn_creative_add(campaign_id):
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        data = request.get_json(silent=True) or {}
        title = str(data.get("title", "")).strip()
        image_url = str(data.get("image_url", "")).strip()
        target_url = str(data.get("target_url", "")).strip()
        if not title or not image_url or not target_url:
            return jsonify(ok=False, error="missing_fields"), 400
        try:
            result = store.add_creative(
                campaign_id, user["earn_user_id"],
                title, image_url, target_url,
            )
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, **result)

    @app.get("/api/earn/ads/campaign/<campaign_id>/creative/list")
    def earn_creative_list(campaign_id):
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        try:
            creatives = store.list_creatives(
                campaign_id, user["earn_user_id"],
            )
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, creatives=creatives)

    @app.post("/api/earn/ads/moderate/campaign")
    def earn_moderate_campaign():
        mgmt_token = request.headers.get("X-Admin-Key", "").strip()
        if not mgmt_token or mgmt_token != os.getenv("EARN_MGMT_TOKEN", "").strip():
            return jsonify(ok=False, error="unauthorized"), 403
        data = request.get_json(silent=True) or {}
        campaign_id = str(data.get("campaign_id", "")).strip()
        action = str(data.get("action", "")).strip()
        reason = str(data.get("reason", "")).strip()
        if not campaign_id or not action:
            return jsonify(ok=False, error="missing_fields"), 400
        try:
            result = store.moderate_campaign(campaign_id, action, reason)
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, **result)

    @app.post("/api/earn/ads/moderate/creative")
    def earn_moderate_creative():
        mgmt_token = request.headers.get("X-Admin-Key", "").strip()
        if not mgmt_token or mgmt_token != os.getenv("EARN_MGMT_TOKEN", "").strip():
            return jsonify(ok=False, error="unauthorized"), 403
        data = request.get_json(silent=True) or {}
        creative_id = str(data.get("creative_id", "")).strip()
        action = str(data.get("action", "")).strip()
        reason = str(data.get("reason", "")).strip()
        if not creative_id or not action:
            return jsonify(ok=False, error="missing_fields"), 400
        try:
            result = store.moderate_creative(creative_id, action, reason)
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, **result)

    @app.post("/api/earn/ads/escrow/intent")
    def earn_escrow_intent():
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        data = request.get_json(silent=True) or {}
        campaign_id = str(data.get("campaign_id", "")).strip()
        action = str(data.get("action", "")).strip()
        amount = str(data.get("amount", "")).strip()
        if not campaign_id or not action or not amount:
            return jsonify(ok=False, error="missing_fields"), 400
        try:
            result = store.escrow_create_intent(
                user["earn_user_id"], campaign_id, action, amount,
            )
        except (EarnError, InvalidOperation, ValueError) as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, **result)

    @app.post("/api/earn/ads/escrow/execute")
    def earn_escrow_execute():
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        data = request.get_json(silent=True) or {}
        intent_id = str(data.get("intent_id", "")).strip()
        nonce = str(data.get("nonce", "")).strip()
        wallet_signature = str(
            data.get("wallet_signature", ""),
        ).strip() or None
        if not intent_id or not nonce:
            return jsonify(ok=False, error="missing_fields"), 400
        try:
            result = store.escrow_execute(
                intent_id, user["earn_user_id"],
                nonce, wallet_signature,
            )
        except (EarnError, InvalidOperation, ValueError) as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, **result)

    @app.get("/api/earn/ads/escrow/balance/<campaign_id>")
    def earn_escrow_balance(campaign_id):
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        camp = store.get_campaign(campaign_id)
        if not camp or camp["advertiser_id"] != user["earn_user_id"]:
            return jsonify(ok=False, error="campaign_not_found"), 404
        balance = store.escrow_balance(campaign_id)
        return jsonify(ok=True, balance=balance)

    @app.get("/api/earn/ads/serve")
    def earn_ads_serve():
        # Paid campaigns cannot be delivered while their public event path is
        # disabled: that would serve advertiser inventory with no verifiable
        # view/click accounting. Legacy house banners use /api/earn/ads.
        return jsonify(ok=False, error="verified_ad_delivery_required"), 503

    @app.post("/api/earn/ads/serve/event")
    def earn_ads_serve_event():
        # This endpoint previously accepted arbitrary client-supplied IDs and
        # could debit a funded THC escrow without a verified view or click.
        # Keep paid delivery closed until a server-issued, single-use proof
        # binds creative, placement, trusted geo and a unique viewer.
        return jsonify(ok=False, error="verified_ad_event_required"), 503

    @app.get("/api/earn/ads/campaign/<campaign_id>/report")
    def earn_campaign_report(campaign_id):
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        try:
            report = store.campaign_report(
                campaign_id, user["earn_user_id"],
            )
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, **report)

    @app.get("/api/earn/ads/campaign/<campaign_id>/report/daily")
    def earn_campaign_report_daily(campaign_id):
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        days = min(int(request.args.get("days", "30")), 90)
        try:
            daily = store.campaign_report_daily(
                campaign_id, user["earn_user_id"], days=days,
            )
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, daily=daily)

    @app.get("/api/earn/referral/code")
    def earn_referral_code():
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="not_authenticated"), 401
        code = store.referral_code(user["earn_user_id"])
        return jsonify(ok=True, ref_code=code)

    @app.get("/api/earn/referral/stats")
    def earn_referral_stats():
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="not_authenticated"), 401
        uid = user["earn_user_id"]
        stats = store.referral_stats(uid)
        refs = store.referral_list(uid)
        return jsonify(ok=True, **stats, referrals=refs)

    @app.get("/api/earn/providers")
    def earn_providers():
        """Return public availability only; provider credentials stay server-side."""
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        return jsonify(
            ok=True,
            providers=[
                {"id": "cpx", "label": "CPX Research", "kind": "surveys",
                 "enabled": os.getenv("CPX_SURVEYS_BETA_ENABLED", "0") == "1"},
                {"id": "bitcotasks", "label": "BitcoTasks", "kind": "offers",
                 "enabled": os.getenv("BITCOTASKS_ENABLED", "0") == "1"},
                {"id": "pure", "label": "PureSpectrum", "kind": "surveys",
                 "enabled": os.getenv("PURE_ENABLED", "0") == "1"},
                {"id": "timewall", "label": "TimeWall", "kind": "tasks",
                 "enabled": os.getenv("TIMEWALL_ENABLED", "0") == "1"
                 and bool(os.getenv("TIMEWALL_PLACEMENT_URL", "").strip())},
            ],
        )

    @app.get("/api/earn/cpx/offerwall")
    def earn_cpx_offerwall():
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        if os.getenv("CPX_SURVEYS_BETA_ENABLED", "0") != "1":
            return jsonify(ok=False, error="cpx_surveys_not_enabled"), 503
        try:
            url = build_cpx_offerwall_url(user["cpx_ext_user_id"])
            return jsonify(ok=True, url=url)
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 503

    @app.get("/api/earn/bitcotasks/offerwall")
    def earn_bitcotasks_offerwall():
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        if os.getenv("BITCOTASKS_ENABLED", "0") != "1":
            return jsonify(ok=False, error="bitcotasks_not_enabled"), 503
        try:
            provider_user_id = store.provider_user_id(
                user["earn_user_id"], "bitcotasks",
            )
            return jsonify(
                ok=True,
                provider="bitcotasks",
                url=build_bitcotasks_offerwall_url(provider_user_id),
            )
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 503

    @app.route("/api/earn/cpx/postback", methods=["GET", "POST"])
    def earn_cpx_postback():
        params = (
            request.values.to_dict()
            if request.values
            else (request.get_json(silent=True) or {})
        )
        trans_id = str(params.get("trans_id") or "").strip()
        user_id = str(params.get("user_id") or "").strip()
        received_hash = str(
            params.get("secure_hash") or params.get("hash") or "",
        ).strip()
        if os.getenv("CPX_POSTBACK_LIVE", "0") != "1":
            return "0", 503
        if not cpx_postback_ip_allowed(
            request.remote_addr, request.headers.get("X-Real-IP"),
        ):
            return "0", 403
        if not verify_cpx_postback_signature(trans_id, received_hash):
            return "0", 403
        try:
            store.record_cpx_receipt(
                trans_id=trans_id,
                cpx_ext_user_id=user_id,
                status=int(params.get("status") or 0),
                amount_local=str(params.get("amount_local") or "0"),
                amount_usd=str(params.get("amount_usd") or ""),
                offer_id=str(
                    params.get("offer_id") or params.get("offer_ID") or "",
                ),
                payload=params,
            )
        except (EarnError, ValueError):
            return "0", 400
        return "1", 200

    @app.route("/api/earn/bitcotasks/postback", methods=["GET", "POST"])
    def earn_bitcotasks_postback():
        """BitcoTasks S2S receiver; never exposed to browser reward claims."""
        params = (
            request.values.to_dict()
            if request.values
            else (request.get_json(silent=True) or {})
        )
        if os.getenv("BITCOTASKS_POSTBACK_LIVE", "0") != "1":
            return "ERROR", 503
        # BitcoTasks requires an exact sub_id match to the opaque ID sent
        # when the offerwall was opened.  Do not strip, truncate, prefix, or
        # otherwise normalize it: a changed ID must fail safely rather than
        # credit a different Earn account.  Accept both documented spellings
        # of the *parameter name*, never an altered parameter value.
        raw_sub_id = params["sub_id"] if "sub_id" in params else params.get("subId", "")
        raw_trans_id = params["trans_id"] if "trans_id" in params else params.get("transId", "")
        sub_id = raw_sub_id if isinstance(raw_sub_id, str) else str(raw_sub_id or "")
        trans_id = raw_trans_id if isinstance(raw_trans_id, str) else str(raw_trans_id or "")
        raw_reward = params.get("reward", "")
        reward = raw_reward if isinstance(raw_reward, str) else str(raw_reward or "")
        raw_signature = params.get("signature", "")
        signature = raw_signature if isinstance(raw_signature, str) else str(raw_signature or "")
        if not verify_bitcotasks_postback_signature(
            sub_id, trans_id, reward, signature,
        ):
            return "ERROR", 403
        # Dashboard connectivity tests must not fabricate a user reward.
        if str(params.get("debug") or "0") == "1":
            return "ok", 200
        try:
            store.record_bitcotasks_receipt(
                trans_id=trans_id,
                provider_user_id=sub_id,
                status=int(params.get("status") or 0),
                reward_thc=reward,
                payout_usd=str(params.get("payout") or ""),
                offer_name=str(params.get("offer_name") or ""),
                offer_type=str(params.get("offer_type") or ""),
                payload=params,
            )
        except (EarnError, ValueError):
            return "ERROR", 400
        return "ok", 200

    @app.get("/api/earn/pure/offerwall")
    def earn_pure_offerwall():
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        if os.getenv("PURE_ENABLED", "0") != "1":
            return jsonify(ok=False, error="pure_not_enabled"), 503
        try:
            provider_user_id = store.provider_user_id(
                user["earn_user_id"], "pure",
            )
            return jsonify(
                ok=True,
                provider="pure",
                url=build_pure_offerwall_url(provider_user_id),
            )
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 503

    @app.get("/api/earn/timewall/offerwall")
    def earn_timewall_offerwall():
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        if os.getenv("TIMEWALL_ENABLED", "0") != "1":
            return jsonify(ok=False, error="timewall_not_enabled"), 503
        try:
            provider_user_id = store.provider_user_id(
                user["earn_user_id"], "timewall",
            )
            return jsonify(
                ok=True,
                provider="timewall",
                url=build_timewall_offerwall_url(provider_user_id),
            )
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 503

    @app.route("/api/earn/timewall/postback", methods=["GET", "POST"])
    def earn_timewall_postback():
        """Receive a signed TimeWall event; disabled until explicitly enabled."""
        live = os.getenv("TIMEWALL_POSTBACK_LIVE", "0") == "1"
        params = (
            request.values.to_dict()
            if request.values
            else (request.get_json(silent=True) or {})
        )
        user_id = str(
            params.get("userId") or params.get("userID")
            or params.get("user_ID") or params.get("user_id") or "",
        ).strip()
        # Preserve the provider's exact revenue string for signature validation.
        revenue_value = params.get("revenue")
        revenue = revenue_value if isinstance(revenue_value, str) else str(revenue_value or "")
        received_hash = str(params.get("hash") or "").strip()
        event_id = str(
            params.get("transactionId") or params.get("transactionID")
            or params.get("txid") or params.get("transaction_id")
            or params.get("withdrawid") or "",
        ).strip()
        if not event_id or not verify_timewall_postback_signature(
            user_id, revenue, received_hash,
        ):
            return "ERROR", 403 if live else 503
        # Keep the disabled/preflight path conservative; once explicitly live,
        # signature validation remains sufficient unless strict IP mode is set.
        if (not live or timewall_enforce_ip_allowlist()) and request.remote_addr not in timewall_allowed_ips():
            return "ERROR", 403 if live else 503
        if not live:
            # Verify genuine callbacks while credits remain disabled. Keep the
            # non-200 response so the provider does not consider a reward paid.
            # Only a fingerprint is logged; no signature/user/IP/raw payload.
            try:
                store.validate_timewall_identity(user_id)
                if len(event_id) > 200:
                    raise EarnError("invalid_timewall_event")
                timewall_reward_amount(revenue)
            except (EarnError, InvalidOperation, ValueError):
                return "ERROR", 503
            event_ref = hashlib.sha256(event_id.encode("utf-8")).hexdigest()[:16]
            logger.info(
                "[TimeWall preflight] verified_callback event_ref=%s "
                "credit_enabled=false ledger_write=false retry_required=true", event_ref,
            )
            return "ERROR", 503
        try:
            store.record_timewall_receipt(
                event_id=event_id,
                provider_user_id=user_id,
                revenue_raw=revenue,
                event_type=str(params.get("type") or ""),
                reason=str(params.get("reason") or ""),
                offer_name=str(params.get("offername") or ""),
                offer_detail=str(params.get("offerdetail") or ""),
                payload=params,
            )
        except (EarnError, ValueError):
            return "ERROR", 400
        return "OK", 200

    @app.route("/api/earn/pure/postback", methods=["GET", "POST"])
    def earn_pure_postback():
        """PureSpectrum S2S completion receiver."""
        params = (
            request.values.to_dict()
            if request.values
            else (request.get_json(silent=True) or {})
        )
        if os.getenv("PURE_POSTBACK_LIVE", "0") != "1":
            return "ERROR", 503
        respondent_id = str(params.get("respondentId") or params.get("memberId") or "").strip()
        trans_id = str(params.get("transId") or params.get("surveyId") or "").strip()
        reward = str(params.get("reward") or params.get("cpi") or "").strip()
        signature = str(params.get("signature") or params.get("hash") or "").strip()
        if not verify_pure_postback_signature(trans_id, respondent_id, signature):
            return "ERROR", 403
        if str(params.get("debug") or "0") == "1":
            return "ok", 200
        status = 2 if str(params.get("status") or "1") == "2" else 1
        try:
            store.record_pure_receipt(
                trans_id=trans_id,
                provider_user_id=respondent_id,
                status=status,
                reward_thc=reward,
                payout_usd=str(params.get("payout") or params.get("cpi") or ""),
                survey_id=str(params.get("surveyId") or ""),
                payload=params,
            )
        except (EarnError, ValueError):
            return "ERROR", 400
        return "ok", 200

    @app.post("/api/earn/session/rotate")
    def earn_session_rotate():
        _, token = _current_user()
        result = store.rotate_session(token)
        if not result:
            return jsonify(ok=False, error="earn_auth_required"), 401
        new_token, expires = result
        response = jsonify(
            ok=True, access_token=new_token, expires_in=_SESSION_TTL,
        )
        return _set_session_cookie(response, new_token)

    # ── Publisher routes (isolated from advertiser and Earn identity) ────

    @app.post("/api/earn/publisher/register")
    def earn_publisher_register():
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        data = request.get_json(silent=True) or {}
        provider = str(data.get("provider", "")).strip()
        label = str(data.get("label", "")).strip()
        provider_pub_id = str(data.get("provider_pub_id", "")).strip() or None
        if not provider:
            return jsonify(ok=False, error="missing_provider"), 400
        try:
            result = store.publisher_register(
                user["earn_user_id"], provider, label, provider_pub_id,
            )
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, **result), 201

    @app.get("/api/earn/publisher/list")
    def earn_publisher_list():
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        publishers = store.publisher_get(user["earn_user_id"])
        return jsonify(ok=True, publishers=publishers)

    @app.post("/api/earn/publisher/<publisher_id>/postback")
    def earn_publisher_postback_config(publisher_id):
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        data = request.get_json(silent=True) or {}
        postback_url = str(data.get("postback_url", "")).strip()
        postback_secret = str(data.get("postback_secret", "")).strip() or None
        if not postback_url:
            return jsonify(ok=False, error="missing_postback_url"), 400
        try:
            result = store.publisher_update_postback(
                publisher_id, user["earn_user_id"], postback_url, postback_secret,
            )
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, **result)

    @app.post("/api/earn/publisher/moderate")
    def earn_publisher_moderate():
        data = request.get_json(silent=True) or {}
        publisher_id = str(data.get("publisher_id", "")).strip()
        action = str(data.get("action", "")).strip()
        reason = str(data.get("reason", "")).strip() or None
        if not publisher_id or not action:
            return jsonify(ok=False, error="missing_fields"), 400
        try:
            result = store.publisher_moderate(publisher_id, action, reason)
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, **result)

    @app.post("/api/earn/publisher/<publisher_id>/placement/add")
    def earn_publisher_placement_add(publisher_id):
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        data = request.get_json(silent=True) or {}
        placement_type = str(data.get("placement_type", "survey")).strip()
        site_url = str(data.get("site_url", "")).strip() or None
        try:
            result = store.publisher_add_placement(
                publisher_id, user["earn_user_id"], placement_type, site_url,
            )
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, **result), 201

    @app.get("/api/earn/publisher/<publisher_id>/placements")
    def earn_publisher_placements(publisher_id):
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        try:
            placements = store.publisher_get_placements(
                publisher_id, user["earn_user_id"],
            )
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, placements=placements)

    @app.get("/api/earn/publisher/<publisher_id>/report")
    def earn_publisher_report(publisher_id):
        user, _ = _current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        try:
            report = store.publisher_report(publisher_id, user["earn_user_id"])
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, **report)

