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
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

_THC_SCALE = Decimal("0.000001")
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

    def __init__(self, db_path: str, identity_key: str):
        if not identity_key or identity_key == "CHANGE_ME":
            raise EarnError("earn_identity_key_not_configured")
        self.db_path = db_path
        self._identity_key = identity_key.encode("utf-8")
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
                    created_at      INTEGER NOT NULL,
                    updated_at      INTEGER NOT NULL,
                    UNIQUE(source, source_ref)
                );

                CREATE INDEX IF NOT EXISTS idx_thc_ledger_user
                    ON thc_ledger(earn_user_id, created_at DESC);

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
            """)
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
        if provider != "bitcotasks":
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
            # 31 characters: accepted by BitcoTasks' documented varchar(32).
            provider_user_id = "bt_" + digest[:28]
            con.execute(
                """INSERT INTO earn_provider_identities
                   (provider, provider_user_id, earn_user_id, created_at)
                   VALUES (?,?,?,?)""",
                (provider, provider_user_id, earn_user_id, int(time.time())),
            )
            return provider_user_id

    # ── Registration ─────────────────────────────────────────────────────

    def register(self, email: str, password: str) -> dict[str, Any]:
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
            return {
                "action": "earn_wallet_link" if purpose == "link" else "earn_wallet_login",
                "challenge_id": row["challenge_id"],
                "wallet_address": row["wallet_address"],
                "nonce": row["nonce"],
                "expires_at": str(row["expires_at"]),
            }

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

    def thc_balance(self, earn_user_id: str) -> dict[str, Any]:
        now = int(time.time())
        with self._tx() as con:
            rows = con.execute(
                "SELECT state, amount, created_at FROM thc_ledger WHERE earn_user_id = ?",
                (earn_user_id,),
            ).fetchall()
        by_state: dict[str, Decimal] = {}
        earliest_pending_ts: int | None = None
        latest_pending_ts: int | None = None
        for r in rows:
            s = r["state"]
            by_state[s] = by_state.get(s, Decimal("0")) + Decimal(r["amount"])
            if s == "pending":
                ts = int(r["created_at"] or 0)
                if earliest_pending_ts is None or ts < earliest_pending_ts:
                    earliest_pending_ts = ts
                if latest_pending_ts is None or ts > latest_pending_ts:
                    latest_pending_ts = ts
        confirmed = by_state.get("confirmed", Decimal("0"))
        payable = by_state.get("payable", Decimal("0"))
        paid = by_state.get("paid", Decimal("0"))
        pending = by_state.get("pending", Decimal("0"))
        result: dict[str, Any] = {
            "available": str((confirmed + payable).quantize(_THC_SCALE)),
            "pending": str(pending.quantize(_THC_SCALE)),
            "total_earned": str((confirmed + payable + paid).quantize(_THC_SCALE)),
            "paid_out": str(paid.quantize(_THC_SCALE)),
            "clearance_days": _CLEARANCE_DAYS,
        }
        if earliest_pending_ts:
            clears_at = earliest_pending_ts + _CLEARANCE_DAYS * 86400
            remaining = max(0, clears_at - now)
            result["earliest_clears_at"] = clears_at
            result["days_remaining"] = remaining // 86400 + (1 if remaining % 86400 else 0)
        return result

    def thc_history(
        self, earn_user_id: str, *, limit: int = 100,
    ) -> list[dict[str, Any]]:
        with self._tx() as con:
            rows = con.execute(
                """SELECT entry_id, source, source_ref, amount, state,
                          note, settlement_ref, created_at, updated_at
                   FROM thc_ledger WHERE earn_user_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (earn_user_id, min(max(limit, 1), 200)),
            ).fetchall()
            return [self._ledger_dict(r) for r in rows]

    @staticmethod
    def _ledger_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        if "amount" in d:
            d["amount"] = str(Decimal(d["amount"]).quantize(_THC_SCALE))
        d.pop("password_hash", None)
        if d.get("state") == "pending" and d.get("created_at"):
            d["clears_at"] = int(d["created_at"]) + _CLEARANCE_DAYS * 86400
        return d

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
            return dict(con.execute(
                "SELECT * FROM bitcotasks_receipts WHERE trans_id = ?", (trans_id,),
            ).fetchone()), True

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
                            self._reverse_thc_in_tx(con, prior["thc_entry_id"])
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
                        state, note, created_at, updated_at)
                       VALUES (?,?,?,?,?,'pending',?,?,?)""",
                    (
                        thc_entry_id,
                        uid,
                        "cpx_survey",
                        trans_id,
                        str(amount_local),
                        f"offer:{offer_id}" if offer_id else "",
                        now,
                        now,
                    ),
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
            return dict(
                con.execute(
                    "SELECT * FROM cpx_receipts WHERE trans_id = ?",
                    (trans_id,),
                ).fetchone(),
            ), True

    def _reverse_thc_in_tx(
        self, con: sqlite3.Connection, entry_id: str,
    ) -> None:
        row = con.execute(
            "SELECT state FROM thc_ledger WHERE entry_id = ?", (entry_id,),
        ).fetchone()
        if not row or row["state"] == "reversed":
            return
        if "reversed" not in _THC_TRANSITIONS.get(row["state"], set()):
            raise EarnError("invalid_thc_transition")
        con.execute(
            "UPDATE thc_ledger SET state = 'reversed', updated_at = ? WHERE entry_id = ?",
            (int(time.time()), entry_id),
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


# ── Flask route registration ─────────────────────────────────────────────


def register_earn_account_routes(
    app: Any,
    store: EarnAccountStore,
) -> None:
    from flask import jsonify, request

    def _current_user():
        token = (
            request.headers.get("Authorization", "")
            .removeprefix("Bearer ")
            .strip()
        )
        user = store.user_for_session(token)
        if user:
            return user, token
        # Browser pages use this HttpOnly, same-origin cookie.  API consumers
        # may continue using the Bearer token, so this is additive.
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
        try:
            user = store.register(
                str(data.get("email", "")),
                str(data.get("password", "")),
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
        sub_id = str(params.get("subId") or "").strip()
        trans_id = str(params.get("transId") or "").strip()
        reward = str(params.get("reward") or "").strip()
        signature = str(params.get("signature") or "").strip()
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
