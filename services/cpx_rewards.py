"""
CPX Research Rewards Integration for Thronos V3.6

Provides:
  - Pre-wallet user accounts (email/password → stable ext_user_id)
  - RPT (Reward Points) ledger separate from THR/BTC/USDT
  - CPX Offerwall frame with server-side secure_hash generation
  - Postback handler with MD5 signature verification, idempotency, reversals
  - Per-transaction file locking to prevent concurrent duplicate credits

Environment variables (set in Railway / .env):
  CPX_APP_ID            – from CPX Research publisher dashboard
  CPX_APP_SECURE_HASH   – rotated secret; NEVER expose to client or logs

Data files (all in DATA_DIR):
  cpx_accounts.json     – { email_hash: { ext_user_id, ... } }
  rpt_ledger.json       – { ext_user_id: { balance, ... } }
  cpx_transactions.json – { trans_id: { user_id, amount, status, ... } }
"""

import fcntl
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import tempfile
import time
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# File paths – set by init_cpx_rewards() from server.py's DATA_DIR
# ---------------------------------------------------------------------------
_DATA_DIR = None
CPX_ACCOUNTS_FILE = None
RPT_LEDGER_FILE = None
CPX_TRANSACTIONS_FILE = None
_LOCK_DIR = None

# Config
CPX_APP_ID = None
CPX_APP_SECURE_HASH = None  # never logged
CPX_OFFERWALL_URL = "https://offers.cpx-research.com/index.php"
CPX_CURRENCY_FACTOR = 680
CPX_BONUS_FACTOR = 1000

# Rate limiter for account registration
_reg_rate_buckets = {}
_REG_RATE_LIMIT = 5  # per minute per IP
_REG_RATE_WINDOW = 60


def init_cpx_rewards(data_dir: str):
    """Called once from server.py startup to bind file paths and load config."""
    global _DATA_DIR, CPX_ACCOUNTS_FILE, RPT_LEDGER_FILE, CPX_TRANSACTIONS_FILE
    global _LOCK_DIR, CPX_APP_ID, CPX_APP_SECURE_HASH

    _DATA_DIR = data_dir
    CPX_ACCOUNTS_FILE = os.path.join(data_dir, "cpx_accounts.json")
    RPT_LEDGER_FILE = os.path.join(data_dir, "rpt_ledger.json")
    CPX_TRANSACTIONS_FILE = os.path.join(data_dir, "cpx_transactions.json")
    _LOCK_DIR = os.path.join(data_dir, "locks")
    os.makedirs(_LOCK_DIR, exist_ok=True)

    CPX_APP_ID = os.getenv("CPX_APP_ID", "").strip()
    CPX_APP_SECURE_HASH = os.getenv("CPX_APP_SECURE_HASH", "").strip()

    if not CPX_APP_ID:
        logger.warning("CPX_APP_ID not set — CPX offerwall will be disabled")
    if not CPX_APP_SECURE_HASH:
        logger.warning("CPX_APP_SECURE_HASH not set — CPX postback verification disabled")


# ---------------------------------------------------------------------------
# JSON helpers (atomic write via tmp+rename, same pattern as server.py)
# ---------------------------------------------------------------------------

def _load_json(path, default=None):
    if default is None:
        default = {}
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    dir_name = os.path.dirname(path)
    base_name = os.path.basename(path)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", delete=False, dir=dir_name,
            prefix=f".{base_name}.", suffix=".tmp", encoding="utf-8"
        ) as tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp_path = tmp.name
        os.replace(tmp_path, path)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Pre-wallet accounts
# ---------------------------------------------------------------------------

def _hash_email(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 250_000
    ).hex()


def _generate_ext_user_id(email_hash: str) -> str:
    """Stable internal account ID used as CPX ext_user_id."""
    seed = f"{email_hash}:{secrets.token_hex(8)}:cpx"
    h = hashlib.sha256(seed.encode()).hexdigest()
    return f"CPX{h[:32]}"


def _check_reg_rate_limit(ip: str) -> bool:
    now = time.time()
    bucket = _reg_rate_buckets.get(ip)
    if not bucket or now - bucket["window_start"] > _REG_RATE_WINDOW:
        _reg_rate_buckets[ip] = {"window_start": now, "count": 1}
        return True
    if bucket["count"] >= _REG_RATE_LIMIT:
        return False
    bucket["count"] += 1
    return True


def register_account(email: str, password: str, ip: str = "") -> dict:
    """
    Create a pre-wallet account for CPX survey rewards.

    Returns { ok, ext_user_id } on success or { ok: False, error } on failure.
    Email stored as SHA-256 hash only. Password stored as PBKDF2-SHA256-250k.
    """
    if not email or not password:
        return {"ok": False, "error": "missing_fields"}

    email = email.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return {"ok": False, "error": "invalid_email"}

    if len(password) < 8:
        return {"ok": False, "error": "password_too_short"}

    if ip and not _check_reg_rate_limit(ip):
        return {"ok": False, "error": "rate_limited"}

    email_hash = _hash_email(email)
    accounts = _load_json(CPX_ACCOUNTS_FILE, {})

    if email_hash in accounts:
        return {"ok": False, "error": "account_exists"}

    salt = secrets.token_hex(16)
    ext_user_id = _generate_ext_user_id(email_hash)

    accounts[email_hash] = {
        "ext_user_id": ext_user_id,
        "password_hash": _hash_password(password, salt),
        "salt": salt,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "wallet_linked": False,
        "thr_address": None,
    }
    _save_json(CPX_ACCOUNTS_FILE, accounts)

    # Initialize RPT balance
    ledger = _load_json(RPT_LEDGER_FILE, {})
    if ext_user_id not in ledger:
        ledger[ext_user_id] = {"balance": 0, "total_earned": 0, "total_spent": 0}
        _save_json(RPT_LEDGER_FILE, ledger)

    return {"ok": True, "ext_user_id": ext_user_id}


def authenticate_account(email: str, password: str) -> dict:
    """
    Authenticate a pre-wallet account.
    Returns { ok, ext_user_id } on success.
    """
    if not email or not password:
        return {"ok": False, "error": "missing_fields"}

    email_hash = _hash_email(email.strip().lower())
    accounts = _load_json(CPX_ACCOUNTS_FILE, {})

    account = accounts.get(email_hash)
    if not account:
        return {"ok": False, "error": "invalid_credentials"}

    expected = _hash_password(password, account["salt"])
    if not hmac.compare_digest(expected, account["password_hash"]):
        return {"ok": False, "error": "invalid_credentials"}

    return {"ok": True, "ext_user_id": account["ext_user_id"]}


def link_wallet(email: str, password: str, thr_address: str) -> dict:
    """
    Link a real ThronosWallet to a pre-wallet CPX account.
    Migrates RPT balance to the new address-based identity.
    """
    auth = authenticate_account(email, password)
    if not auth["ok"]:
        return auth

    if not thr_address or not thr_address.startswith("THR"):
        return {"ok": False, "error": "invalid_thr_address"}

    email_hash = _hash_email(email.strip().lower())
    accounts = _load_json(CPX_ACCOUNTS_FILE, {})
    account = accounts.get(email_hash)
    if not account:
        return {"ok": False, "error": "account_not_found"}

    old_id = account["ext_user_id"]
    account["wallet_linked"] = True
    account["thr_address"] = thr_address.strip().upper()
    account["linked_at"] = datetime.now(timezone.utc).isoformat()
    accounts[email_hash] = account
    _save_json(CPX_ACCOUNTS_FILE, accounts)

    return {"ok": True, "ext_user_id": old_id, "thr_address": account["thr_address"]}


# ---------------------------------------------------------------------------
# RPT Ledger
# ---------------------------------------------------------------------------

def get_rpt_balance(ext_user_id: str) -> dict:
    ledger = _load_json(RPT_LEDGER_FILE, {})
    entry = ledger.get(ext_user_id, {"balance": 0, "total_earned": 0, "total_spent": 0})
    return {"ok": True, "ext_user_id": ext_user_id, **entry}


def credit_rpt(ext_user_id: str, amount: int, source: str = "cpx") -> bool:
    if amount <= 0:
        return False
    ledger = _load_json(RPT_LEDGER_FILE, {})
    entry = ledger.get(ext_user_id, {"balance": 0, "total_earned": 0, "total_spent": 0})
    entry["balance"] += amount
    entry["total_earned"] += amount
    entry["last_credit"] = datetime.now(timezone.utc).isoformat()
    entry["last_source"] = source
    ledger[ext_user_id] = entry
    _save_json(RPT_LEDGER_FILE, ledger)
    return True


def debit_rpt(ext_user_id: str, amount: int, reason: str = "reversal") -> bool:
    if amount <= 0:
        return False
    ledger = _load_json(RPT_LEDGER_FILE, {})
    entry = ledger.get(ext_user_id)
    if not entry:
        return False
    entry["balance"] = max(0, entry["balance"] - amount)
    entry["total_spent"] = entry.get("total_spent", 0) + amount
    entry["last_debit"] = datetime.now(timezone.utc).isoformat()
    entry["last_debit_reason"] = reason
    ledger[ext_user_id] = entry
    _save_json(RPT_LEDGER_FILE, ledger)
    return True


# ---------------------------------------------------------------------------
# CPX secure_hash generation (server-side only)
# ---------------------------------------------------------------------------

def generate_cpx_secure_hash(ext_user_id: str) -> str:
    """
    Generate the CPX iframe secure_hash per CPX spec:
      MD5(ext_user_id + "-" + APP_SECURE_HASH)

    NEVER expose CPX_APP_SECURE_HASH itself to the client.
    """
    if not CPX_APP_SECURE_HASH:
        raise ValueError("CPX_APP_SECURE_HASH not configured")
    raw = f"{ext_user_id}-{CPX_APP_SECURE_HASH}"
    return hashlib.md5(raw.encode()).hexdigest()


def build_offerwall_url(ext_user_id: str) -> str:
    """Build the full CPX Offerwall URL with required parameters."""
    secure_hash = generate_cpx_secure_hash(ext_user_id)
    params = (
        f"?app_id={CPX_APP_ID}"
        f"&ext_user_id={ext_user_id}"
        f"&secure_hash={secure_hash}"
    )
    return f"{CPX_OFFERWALL_URL}{params}"


# ---------------------------------------------------------------------------
# CPX Postback verification
# ---------------------------------------------------------------------------

def verify_cpx_signature(trans_id: str, received_hash: str) -> bool:
    """
    Verify CPX postback signature:
      expected = MD5(trans_id + "-" + APP_SECURE_HASH)
    Uses constant-time comparison.
    """
    if not CPX_APP_SECURE_HASH or not trans_id or not received_hash:
        return False
    expected = hashlib.md5(f"{trans_id}-{CPX_APP_SECURE_HASH}".encode()).hexdigest()
    return hmac.compare_digest(expected, received_hash.lower())


# ---------------------------------------------------------------------------
# Idempotent crediting with file locking
# ---------------------------------------------------------------------------

def _acquire_tx_lock(trans_id: str):
    """Acquire per-transaction file lock. Returns (lock_file, fd) or (None, None)."""
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", trans_id)[:128]
    lock_path = os.path.join(_LOCK_DIR, f"cpx_tx_{safe_id}.lock")
    try:
        fd = open(lock_path, "w")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_path, fd
    except (IOError, OSError):
        return None, None


def _release_tx_lock(fd):
    if fd:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
            fd.close()
        except (IOError, OSError):
            pass


def process_cpx_callback(trans_id: str, user_id: str, amount_local: float,
                         status: int, offer_id: str = "",
                         ip_click: str = "") -> dict:
    """
    Process a CPX postback callback.

    - status=1: credit reward
    - status=2: reverse/chargeback
    - Idempotent per trans_id
    - Per-transaction file lock prevents concurrent duplicates

    amount_local is the FINAL reward amount (already multiplied by currency factor).
    Do NOT multiply by 680 again.
    """
    amount = int(round(amount_local))  # RPT is integer
    if amount < 0:
        return {"ok": False, "error": "negative_amount"}

    lock_path, lock_fd = _acquire_tx_lock(trans_id)
    if lock_fd is None:
        return {"ok": False, "error": "concurrent_processing"}

    try:
        txns = _load_json(CPX_TRANSACTIONS_FILE, {})

        if trans_id in txns:
            existing = txns[trans_id]

            if existing["status"] == status:
                return {"ok": True, "duplicate": True}

            # Reversal: status changed from 1 (credited) to 2 (reversed)
            if status == 2 and existing["status"] == 1:
                debit_rpt(existing["user_id"], existing["amount"], reason="cpx_reversal")
                existing["status"] = 2
                existing["reversed_at"] = datetime.now(timezone.utc).isoformat()
                txns[trans_id] = existing
                _save_json(CPX_TRANSACTIONS_FILE, txns)
                logger.info("CPX reversal: trans_id=%s user=%s amount=%d",
                            trans_id, existing["user_id"], existing["amount"])
                return {"ok": True, "reversed": True}

            return {"ok": True, "no_action": True}

        # New transaction
        now_iso = datetime.now(timezone.utc).isoformat()
        if status == 1 and amount > 0:
            # Verify user exists in accounts or RPT ledger
            ledger = _load_json(RPT_LEDGER_FILE, {})
            if user_id not in ledger:
                # Auto-create ledger entry if account exists
                accounts = _load_json(CPX_ACCOUNTS_FILE, {})
                user_exists = any(
                    a.get("ext_user_id") == user_id for a in accounts.values()
                )
                if not user_exists:
                    return {"ok": False, "error": "unknown_user"}

            credit_rpt(user_id, amount, source="cpx")
            logger.info("CPX credit: trans_id=%s user=%s amount=%d",
                        trans_id, user_id, amount)

        # status=2 without prior credit = no-op (can't reverse what wasn't credited)

        txns[trans_id] = {
            "user_id": user_id,
            "amount": amount,
            "status": status,
            "offer_id": offer_id,
            "ip_click": ip_click,
            "processed_at": now_iso,
        }
        _save_json(CPX_TRANSACTIONS_FILE, txns)
        return {"ok": True}

    finally:
        _release_tx_lock(lock_fd)


# ---------------------------------------------------------------------------
# Account lookup helpers
# ---------------------------------------------------------------------------

def get_account_by_ext_user_id(ext_user_id: str) -> dict | None:
    accounts = _load_json(CPX_ACCOUNTS_FILE, {})
    for email_hash, account in accounts.items():
        if account.get("ext_user_id") == ext_user_id:
            return {
                "ext_user_id": account["ext_user_id"],
                "wallet_linked": account.get("wallet_linked", False),
                "thr_address": account.get("thr_address"),
                "created_at": account.get("created_at"),
            }
    return None


def get_transaction_history(ext_user_id: str, limit: int = 50) -> list:
    txns = _load_json(CPX_TRANSACTIONS_FILE, {})
    user_txns = [
        {"trans_id": tid, **data}
        for tid, data in txns.items()
        if data.get("user_id") == ext_user_id
    ]
    user_txns.sort(key=lambda x: x.get("processed_at", ""), reverse=True)
    return user_txns[:limit]
