"""Transactional, wallet-bound Earn Center ledger.

This module deliberately does *not* settle rewards.  It records provider
events and their state transitions; a separately authorised settlement worker
must create the real THR/BTC transaction before an event may become ``paid``.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from urllib.parse import urlencode
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable


class EarnError(ValueError):
    pass


_TRANSITIONS = {
    "pending": {"confirmed", "reversed"},
    "confirmed": {"payable", "reversed"},
    "payable": {"paid", "reversed"},
    "paid": {"reversed"},
    "reversed": set(),
}


class EarnStore:
    """SQLite-backed reward ledger with one atomic writer transaction per call."""

    def __init__(self, db_path: str, cpx_id_key: str):
        if not cpx_id_key or cpx_id_key == "CHANGE_ME":
            raise EarnError("earn_identity_key_not_configured")
        self.db_path = db_path
        self._cpx_id_key = cpx_id_key.encode("utf-8")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _tx(self):
        con = sqlite3.connect(self.db_path, timeout=15, isolation_level=None)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA foreign_keys = ON")
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def _init_db(self) -> None:
        # sqlite3.executescript manages its own DDL transaction, so it must not
        # run inside the explicit BEGIN IMMEDIATE used by ledger mutations.
        con = sqlite3.connect(self.db_path, timeout=15)
        try:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS earn_users (
                    earn_user_id TEXT PRIMARY KEY,
                    wallet_address TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    cpx_external_user_id TEXT NOT NULL UNIQUE,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS earn_sessions (
                    token_hash TEXT PRIMARY KEY,
                    earn_user_id TEXT NOT NULL REFERENCES earn_users(earn_user_id),
                    expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS earn_auth_nonces (
                    wallet_address TEXT NOT NULL COLLATE NOCASE,
                    nonce TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    PRIMARY KEY(wallet_address, nonce)
                );
                CREATE TABLE IF NOT EXISTS earn_rewards (
                    reward_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    provider_event_id TEXT NOT NULL,
                    earn_user_id TEXT NOT NULL REFERENCES earn_users(earn_user_id),
                    asset TEXT NOT NULL,
                    amount TEXT NOT NULL,
                    state TEXT NOT NULL,
                    provider_payload TEXT NOT NULL,
                    settlement_txid TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    UNIQUE(provider, provider_event_id)
                );
                CREATE INDEX IF NOT EXISTS earn_rewards_user_created
                    ON earn_rewards(earn_user_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS cpx_receipts (
                    trans_id TEXT PRIMARY KEY,
                    earn_user_id TEXT NOT NULL REFERENCES earn_users(earn_user_id),
                    status INTEGER NOT NULL,
                    amount_local TEXT NOT NULL,
                    amount_usd TEXT,
                    offer_id TEXT,
                    received_at INTEGER NOT NULL,
                    payload TEXT NOT NULL
                );
            """)
        finally:
            con.close()

    @staticmethod
    def _wallet(wallet: str) -> str:
        wallet = (wallet or "").strip().upper()
        if not wallet.startswith("THR") or len(wallet) < 12:
            raise EarnError("invalid_wallet")
        return wallet

    def _cpx_id(self, earn_user_id: str) -> str:
        # Opaque, deterministic and generated only on the server.  It is not a
        # wallet address and cannot be selected by a browser client.
        digest = hmac.new(self._cpx_id_key, earn_user_id.encode(), hashlib.sha256).hexdigest()
        return "thr_" + digest[:40]

    def user_for_wallet(self, wallet: str) -> dict[str, Any]:
        wallet = self._wallet(wallet)
        with self._tx() as con:
            row = con.execute("SELECT * FROM earn_users WHERE wallet_address = ?", (wallet,)).fetchone()
            if not row:
                now = int(time.time())
                uid = "earn_" + secrets.token_urlsafe(18)
                cpx_id = self._cpx_id(uid)
                con.execute(
                    "INSERT INTO earn_users VALUES (?, ?, ?, ?)", (uid, wallet, cpx_id, now)
                )
                row = con.execute("SELECT * FROM earn_users WHERE earn_user_id = ?", (uid,)).fetchone()
            return dict(row)

    def issue_session(self, wallet: str, ttl_seconds: int = 900) -> tuple[dict[str, Any], str]:
        user = self.user_for_wallet(wallet)
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        with self._tx() as con:
            con.execute(
                "INSERT INTO earn_sessions VALUES (?, ?, ?, ?)",
                (hashlib.sha256(token.encode()).hexdigest(), user["earn_user_id"], now + ttl_seconds, now),
            )
        return user, token

    def consume_wallet_nonce(self, wallet: str, nonce: str, expires_at: int) -> bool:
        """Atomically consume a signed wallet-auth nonce exactly once."""
        wallet = self._wallet(wallet)
        if not nonce or len(nonce) > 256:
            return False
        now = int(time.time())
        with self._tx() as con:
            con.execute("DELETE FROM earn_auth_nonces WHERE expires_at < ?", (now,))
            try:
                con.execute("INSERT INTO earn_auth_nonces VALUES (?, ?, ?)", (wallet, nonce, expires_at))
            except sqlite3.IntegrityError:
                return False
        return True

    def user_for_session(self, token: str) -> dict[str, Any] | None:
        if not token:
            return None
        key = hashlib.sha256(token.encode()).hexdigest()
        with self._tx() as con:
            row = con.execute("""
                SELECT u.* FROM earn_sessions s JOIN earn_users u ON u.earn_user_id=s.earn_user_id
                WHERE s.token_hash=? AND s.expires_at>=?
            """, (key, int(time.time()))).fetchone()
            return dict(row) if row else None

    def record_provider_reward(self, provider: str, provider_event_id: str, cpx_external_user_id: str,
                               asset: str, amount: str | float, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Idempotently record a verified callback.  New rewards start pending."""
        if provider != "cpx":
            raise EarnError("unsupported_provider")
        if not provider_event_id or len(provider_event_id) > 200:
            raise EarnError("invalid_provider_event_id")
        if asset.upper() not in {"THR", "BTC"}:
            raise EarnError("unsupported_reward_asset")
        try:
            normalized_amount = str(amount)
            if float(normalized_amount) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise EarnError("invalid_reward_amount")
        with self._tx() as con:
            user = con.execute("SELECT * FROM earn_users WHERE cpx_external_user_id=?", (cpx_external_user_id,)).fetchone()
            if not user:
                raise EarnError("unknown_external_user")
            existing = con.execute(
                "SELECT * FROM earn_rewards WHERE provider=? AND provider_event_id=?",
                (provider, provider_event_id),
            ).fetchone()
            if existing:
                # A provider must not reuse an id for a different user or asset.
                if existing["earn_user_id"] != user["earn_user_id"] or existing["asset"] != asset.upper() or existing["amount"] != normalized_amount:
                    raise EarnError("provider_event_conflict")
                return self._reward_dict(existing), False
            now = int(time.time())
            reward_id = "rwd_" + secrets.token_urlsafe(18)
            con.execute("""
                INSERT INTO earn_rewards
                (reward_id, provider, provider_event_id, earn_user_id, asset, amount, state, provider_payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
            """, (reward_id, provider, provider_event_id, user["earn_user_id"], asset.upper(), normalized_amount,
                  json.dumps(payload, sort_keys=True, separators=(",", ":")), now, now))
            row = con.execute("SELECT * FROM earn_rewards WHERE reward_id=?", (reward_id,)).fetchone()
            return self._reward_dict(row), True

    @staticmethod
    def _reward_dict(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["amount"] = float(result["amount"])
        result.pop("provider_payload", None)
        return result

    def transition(self, reward_id: str, state: str, settlement_txid: str | None = None) -> dict[str, Any]:
        if state not in _TRANSITIONS:
            raise EarnError("invalid_reward_state")
        with self._tx() as con:
            row = con.execute("SELECT * FROM earn_rewards WHERE reward_id=?", (reward_id,)).fetchone()
            if not row:
                raise EarnError("reward_not_found")
            if row["state"] == state:
                return self._reward_dict(row)
            if state not in _TRANSITIONS[row["state"]]:
                raise EarnError("invalid_reward_transition")
            if state == "paid" and not settlement_txid:
                raise EarnError("settlement_txid_required")
            con.execute("UPDATE earn_rewards SET state=?, settlement_txid=?, updated_at=? WHERE reward_id=?",
                        (state, settlement_txid or row["settlement_txid"], int(time.time()), reward_id))
            return self._reward_dict(con.execute("SELECT * FROM earn_rewards WHERE reward_id=?", (reward_id,)).fetchone())

    def history(self, earn_user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._tx() as con:
            rows = con.execute("SELECT * FROM earn_rewards WHERE earn_user_id=? ORDER BY created_at DESC LIMIT ?",
                               (earn_user_id, min(max(limit, 1), 200))).fetchall()
            return [self._reward_dict(row) for row in rows]

    def record_cpx_receipt(self, *, trans_id: str, cpx_external_user_id: str, status: int,
                           amount_local: str, amount_usd: str = "", offer_id: str = "",
                           payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Atomically retain a verified CPX callback without assigning a token value.

        CPX's publisher amount is revenue/currency data, not a THR/BTC exchange
        rate.  Conversion must be a separately approved reward policy.
        """
        if status not in (1, 2) or not trans_id or len(trans_id) > 200:
            raise EarnError("invalid_cpx_receipt")
        try:
            if float(amount_local) < 0:
                raise ValueError
        except (TypeError, ValueError):
            raise EarnError("invalid_cpx_amount")
        with self._tx() as con:
            user = con.execute("SELECT earn_user_id FROM earn_users WHERE cpx_external_user_id=?", (cpx_external_user_id,)).fetchone()
            if not user:
                raise EarnError("unknown_external_user")
            prior = con.execute("SELECT * FROM cpx_receipts WHERE trans_id=?", (trans_id,)).fetchone()
            if prior:
                if prior["earn_user_id"] != user["earn_user_id"]:
                    raise EarnError("provider_event_conflict")
                if prior["status"] == status:
                    return dict(prior), False
                if status != 2:
                    raise EarnError("invalid_cpx_receipt_transition")
                con.execute("UPDATE cpx_receipts SET status=?, received_at=?, payload=? WHERE trans_id=?",
                            (2, int(time.time()), json.dumps(payload, sort_keys=True, separators=(",", ":")), trans_id))
                return dict(con.execute("SELECT * FROM cpx_receipts WHERE trans_id=?", (trans_id,)).fetchone()), True
            now = int(time.time())
            con.execute("INSERT INTO cpx_receipts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (trans_id, user["earn_user_id"], status, str(amount_local), str(amount_usd), offer_id, now,
                         json.dumps(payload, sort_keys=True, separators=(",", ":"))))
            return dict(con.execute("SELECT * FROM cpx_receipts WHERE trans_id=?", (trans_id,)).fetchone()), True


def build_cpx_offerwall_url(cpx_external_user_id: str) -> str:
    """Create CPX's documented iframe URL; the app secret never leaves server."""
    app_id = os.getenv("CPX_APP_ID", "").strip()
    app_secret = os.getenv("CPX_APP_SECURE_HASH", "").strip()
    if not app_id or not app_secret:
        raise EarnError("cpx_not_configured")
    secure_hash = hashlib.md5(f"{cpx_external_user_id}-{app_secret}".encode("utf-8")).hexdigest()
    query = urlencode({"app_id": app_id, "ext_user_id": cpx_external_user_id, "secure_hash": secure_hash})
    return f"{os.getenv('CPX_OFFERWALL_URL', 'https://offers.cpx-research.com/index.php')}?{query}"


def verify_cpx_postback_signature(trans_id: str, received_hash: str) -> bool:
    """Validate only the formula explicitly selected after dashboard confirmation."""
    if os.getenv("CPX_POSTBACK_SIGNATURE_MODE", "") != "md5_trans_id_dash_secret_v1":
        return False
    secret = os.getenv("CPX_APP_SECURE_HASH", "").strip()
    if not trans_id or not received_hash or not secret:
        return False
    expected = hashlib.md5(f"{trans_id}-{secret}".encode("utf-8")).hexdigest()
    return hmac.compare_digest(expected, received_hash.lower())


def register_earn_routes(app: Any, store: EarnStore,
                         verify_wallet_proof: Callable[[dict[str, Any]], tuple[bool, str, str]]) -> None:
    """Install the public Earn API. ``verify_wallet_proof`` owns wallet crypto."""
    from flask import jsonify, request

    def current_user():
        token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        return store.user_for_session(token)

    @app.post("/api/earn/authenticate")
    def earn_authenticate():
        proof = request.get_json(silent=True) or {}
        ok, wallet, error = verify_wallet_proof(proof)
        if not ok:
            return jsonify(ok=False, error=error), 403
        if not store.consume_wallet_nonce(wallet, str(proof.get("nonce") or ""), int(proof.get("issued_at", 0)) + 300):
            return jsonify(ok=False, error="earn_auth_nonce_reused"), 403
        user, token = store.issue_session(wallet)
        return jsonify(ok=True, earn_user_id=user["earn_user_id"], expires_in=900, access_token=token)

    @app.get("/api/earn/me")
    def earn_me():
        user = current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        return jsonify(ok=True, earn_user_id=user["earn_user_id"], wallet_address=user["wallet_address"])

    @app.get("/api/earn/history")
    def earn_history():
        user = current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        return jsonify(ok=True, rewards=store.history(user["earn_user_id"]))

    @app.get("/api/earn/cpx/offerwall")
    def earn_cpx_offerwall():
        user = current_user()
        if not user:
            return jsonify(ok=False, error="earn_auth_required"), 401
        if os.getenv("CPX_SURVEYS_BETA_ENABLED", "0") != "1":
            return jsonify(ok=False, error="cpx_surveys_not_enabled"), 503
        try:
            return jsonify(ok=True, url=build_cpx_offerwall_url(user["cpx_external_user_id"]))
        except EarnError as exc:
            return jsonify(ok=False, error=str(exc)), 503

    @app.route("/api/earn/cpx/postback", methods=["GET", "POST"])
    def earn_cpx_postback():
        params = request.values.to_dict() if request.values else (request.get_json(silent=True) or {})
        trans_id = str(params.get("trans_id") or "").strip()
        user_id = str(params.get("user_id") or "").strip()
        received_hash = str(params.get("secure_hash") or params.get("hash") or "").strip()
        if os.getenv("CPX_POSTBACK_LIVE", "0") != "1":
            return "0", 503
        if not verify_cpx_postback_signature(trans_id, received_hash):
            return "0", 403
        try:
            store.record_cpx_receipt(
                trans_id=trans_id, cpx_external_user_id=user_id, status=int(params.get("status") or 0),
                amount_local=str(params.get("amount_local") or "0"), amount_usd=str(params.get("amount_usd") or ""),
                offer_id=str(params.get("offer_id") or params.get("offer_ID") or ""), payload=params,
            )
        except (EarnError, ValueError):
            return "0", 400
        # CPX acknowledgement only: no THR/BTC value is minted or paid here.
        return "1", 200
