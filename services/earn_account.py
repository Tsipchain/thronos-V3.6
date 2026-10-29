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
            """)
        finally:
            con.close()

    # ── CPX identity (server-side only) ──────────────────────────────────

    def _cpx_id(self, earn_user_id: str) -> str:
        digest = hmac.new(
            self._identity_key, earn_user_id.encode(), hashlib.sha256,
        ).hexdigest()
        return "thr_" + digest[:40]

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

    def thc_balance(self, earn_user_id: str) -> dict[str, str]:
        with self._tx() as con:
            rows = con.execute(
                "SELECT state, amount FROM thc_ledger WHERE earn_user_id = ?",
                (earn_user_id,),
            ).fetchall()
        by_state: dict[str, Decimal] = {}
        for r in rows:
            s = r["state"]
            by_state[s] = by_state.get(s, Decimal("0")) + Decimal(r["amount"])
        confirmed = by_state.get("confirmed", Decimal("0"))
        payable = by_state.get("payable", Decimal("0"))
        paid = by_state.get("paid", Decimal("0"))
        pending = by_state.get("pending", Decimal("0"))
        return {
            "available": str((confirmed + payable).quantize(_THC_SCALE)),
            "pending": str(pending.quantize(_THC_SCALE)),
            "total_earned": str((confirmed + payable + paid).quantize(_THC_SCALE)),
            "paid_out": str(paid.quantize(_THC_SCALE)),
        }

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
        return d

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
        return jsonify(
            ok=True,
            earn_user_id=user["earn_user_id"],
            email=user["email"],
            email_verified=bool(user["email_verified"]),
        )

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
