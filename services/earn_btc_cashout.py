"""
Thronos Earn — BTC Cash-Out Settlement Ledger

Fail-closed request ledger for external BTC payouts from THC balances.

State machine:
  payable → cashout_requested → reserve_verified → signing → broadcasted → paid
  Any non-terminal state → failed
  cashout_requested → cancelled (user-initiated)

Design constraints:
  - Earn Account is email/password first; Thronos Wallet is optional.
  - THC is the CPX/Earn reward currency; never mixed with THR, L2E, pledge, AMM.
  - CPX never supplies a BTC address — the user provides one in a cashout request.
  - BTC minimum is USD 25 equivalent; rate comes from an injected quote interface.
  - External BTC cashout fee is 8–18%; exact rate from authoritative config.
  - No float anywhere — Decimal with satoshi precision (8 decimal places).
  - No fake BTC success, no made-up txid.
  - A payout may become paid ONLY after a real broadcast result with a validated txid.
  - If reserve, signer, rate, or broadcast confirmation is unavailable, status
    must remain pending/reviewable — never paid.
  - No private keys, no secret values in code/logs/tests.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)

_SAT_SCALE = Decimal("0.00000001")  # 1 satoshi
_THC_SCALE = Decimal("0.000001")
_USD_SCALE = Decimal("0.01")
_FEE_SCALE = Decimal("0.0001")  # fee percentage precision

_MIN_CASHOUT_USD = Decimal("25.00")
_FEE_FLOOR_PERCENT = Decimal("8.0000")
_FEE_CEILING_PERCENT = Decimal("18.0000")

# BTC address basic validation (mainnet only)
_BTC_ADDR_RE = re.compile(
    r"^(1[a-km-zA-HJ-NP-Z1-9]{25,34}|3[a-km-zA-HJ-NP-Z1-9]{25,34}|bc1[a-zA-HJ-NP-Z0-9]{25,90})$"
)

_CASHOUT_TRANSITIONS = {
    "cashout_requested": {"reserve_verified", "failed", "cancelled"},
    "reserve_verified":  {"signing", "failed"},
    "signing":           {"broadcasted", "failed"},
    "broadcasted":       {"paid", "failed"},
    "paid":              set(),      # terminal
    "failed":            set(),      # terminal
    "cancelled":         set(),      # terminal
}


class CashoutError(ValueError):
    pass


class QuoteProvider(Protocol):
    """Interface for BTC/USD price quotes.

    Implementations must return a Decimal BTC/USD price or raise.
    The cashout service never fetches prices itself — the caller
    injects a provider so the rate source is auditable.
    """

    def btc_usd_quote(self) -> Decimal:
        """Return current BTC price in USD as Decimal. Raise on failure."""
        ...


class FeeSchedule(Protocol):
    """Interface for cashout fee configuration.

    Returns the fee percentage as Decimal (e.g. Decimal("12.5") for 12.5%).
    Must be within 8–18% bounds or the cashout service rejects it.
    """

    def cashout_fee_percent(self) -> Decimal:
        """Return the current cashout fee percentage. Raise on failure."""
        ...


class EnvFeeSchedule:
    """Read fee from EARN_CASHOUT_FEE_PERCENT env var (default: not set → error)."""

    def cashout_fee_percent(self) -> Decimal:
        raw = os.getenv("EARN_CASHOUT_FEE_PERCENT", "").strip()
        if not raw:
            raise CashoutError("cashout_fee_not_configured")
        try:
            pct = Decimal(raw).quantize(_FEE_SCALE)
        except (InvalidOperation, TypeError):
            raise CashoutError("cashout_fee_invalid")
        if pct < _FEE_FLOOR_PERCENT or pct > _FEE_CEILING_PERCENT:
            raise CashoutError("cashout_fee_out_of_bounds")
        return pct


def validate_btc_address(address: str) -> str:
    address = (address or "").strip()
    if not address or not _BTC_ADDR_RE.match(address):
        raise CashoutError("invalid_btc_address")
    return address


class EarnBtcCashoutStore:
    """SQLite-backed BTC cashout request ledger.

    This store is deliberately isolated from the wallet core, THR ledger,
    pledge, AMM, and mining systems. It operates only on the Earn THC
    ledger's payable balance.
    """

    def __init__(
        self,
        db_path: str,
        *,
        quote_provider: QuoteProvider,
        fee_schedule: FeeSchedule,
    ):
        self.db_path = db_path
        self._quote = quote_provider
        self._fees = fee_schedule
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

                CREATE TABLE IF NOT EXISTS cashout_requests (
                    request_id          TEXT PRIMARY KEY,
                    earn_user_id        TEXT NOT NULL,
                    btc_address         TEXT NOT NULL,
                    thc_amount          TEXT NOT NULL,
                    fee_percent         TEXT NOT NULL,
                    fee_thc             TEXT NOT NULL,
                    net_thc             TEXT NOT NULL,
                    btc_usd_quote       TEXT NOT NULL,
                    btc_amount_sat      TEXT NOT NULL,
                    usd_equivalent      TEXT NOT NULL,
                    state               TEXT NOT NULL DEFAULT 'cashout_requested',
                    btc_txid            TEXT,
                    failure_reason      TEXT,
                    idempotency_key     TEXT NOT NULL UNIQUE,
                    created_at          INTEGER NOT NULL,
                    updated_at          INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_cashout_user
                    ON cashout_requests(earn_user_id, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_cashout_state
                    ON cashout_requests(state);
            """)
        finally:
            con.close()

    # ── Request creation ─────────────────────────────────────────────────

    def create_cashout_request(
        self,
        *,
        earn_user_id: str,
        btc_address: str,
        thc_amount: str | Decimal,
        available_thc: str | Decimal,
    ) -> dict[str, Any]:
        """Create a new BTC cashout request.

        Args:
            earn_user_id: The Earn account user ID.
            btc_address: User-supplied BTC destination address.
            thc_amount: THC amount to cash out (from payable balance).
            available_thc: Current available (confirmed + payable) THC balance.

        Returns:
            The created request record as dict.

        Raises:
            CashoutError on validation failure or insufficient balance.
        """
        btc_address = validate_btc_address(btc_address)

        try:
            thc_amt = Decimal(str(thc_amount)).quantize(_THC_SCALE, rounding=ROUND_DOWN)
        except (InvalidOperation, TypeError):
            raise CashoutError("invalid_thc_amount")
        if thc_amt <= 0:
            raise CashoutError("invalid_thc_amount")

        try:
            avail = Decimal(str(available_thc)).quantize(_THC_SCALE)
        except (InvalidOperation, TypeError):
            raise CashoutError("invalid_balance")
        if thc_amt > avail:
            raise CashoutError("insufficient_thc_balance")

        # Get fee
        try:
            fee_pct = self._fees.cashout_fee_percent()
        except CashoutError:
            raise
        except Exception as exc:
            raise CashoutError("cashout_fee_unavailable") from exc
        if fee_pct < _FEE_FLOOR_PERCENT or fee_pct > _FEE_CEILING_PERCENT:
            raise CashoutError("cashout_fee_out_of_bounds")

        fee_thc = (thc_amt * fee_pct / Decimal("100")).quantize(
            _THC_SCALE, rounding=ROUND_HALF_UP,
        )
        net_thc = thc_amt - fee_thc
        if net_thc <= 0:
            raise CashoutError("net_amount_zero_after_fee")

        # Get BTC/USD quote
        try:
            btc_usd = self._quote.btc_usd_quote()
        except Exception:
            raise CashoutError("btc_quote_unavailable")
        if btc_usd <= 0:
            raise CashoutError("btc_quote_invalid")

        # Check USD minimum
        usd_equiv = (net_thc * Decimal("1")).quantize(_USD_SCALE, rounding=ROUND_DOWN)
        if usd_equiv < _MIN_CASHOUT_USD:
            raise CashoutError("below_minimum_usd")

        # Convert net THC (treated as USD equivalent) to BTC satoshis
        btc_amount = (usd_equiv / btc_usd).quantize(_SAT_SCALE, rounding=ROUND_DOWN)
        if btc_amount <= 0:
            raise CashoutError("btc_amount_zero")

        # Idempotency key: hash of (user + address + amount + date)
        day_str = time.strftime("%Y-%m-%d", time.gmtime())
        idem_raw = f"{earn_user_id}:{btc_address}:{thc_amt}:{day_str}"
        idem_key = hashlib.sha256(idem_raw.encode()).hexdigest()

        request_id = "co_" + secrets.token_urlsafe(18)
        now = int(time.time())

        with self._tx() as con:
            # Check idempotency
            existing = con.execute(
                "SELECT * FROM cashout_requests WHERE idempotency_key = ?",
                (idem_key,),
            ).fetchone()
            if existing:
                return self._row_dict(existing)

            con.execute(
                """INSERT INTO cashout_requests
                   (request_id, earn_user_id, btc_address, thc_amount,
                    fee_percent, fee_thc, net_thc, btc_usd_quote,
                    btc_amount_sat, usd_equivalent, state,
                    idempotency_key, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,'cashout_requested',?,?,?)""",
                (
                    request_id, earn_user_id, btc_address,
                    str(thc_amt), str(fee_pct), str(fee_thc), str(net_thc),
                    str(btc_usd), str(btc_amount), str(usd_equiv),
                    idem_key, now, now,
                ),
            )
            row = con.execute(
                "SELECT * FROM cashout_requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            return self._row_dict(row)

    # ── State transitions ────────────────────────────────────────────────

    def transition(
        self,
        request_id: str,
        new_state: str,
        *,
        btc_txid: str | None = None,
        failure_reason: str | None = None,
    ) -> dict[str, Any]:
        if new_state not in _CASHOUT_TRANSITIONS:
            raise CashoutError("invalid_cashout_state")

        with self._tx() as con:
            row = con.execute(
                "SELECT * FROM cashout_requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if not row:
                raise CashoutError("cashout_request_not_found")

            current = row["state"]
            if current == new_state:
                return self._row_dict(row)
            if new_state not in _CASHOUT_TRANSITIONS.get(current, set()):
                raise CashoutError("invalid_cashout_transition")

            # paid requires a real btc_txid
            if new_state == "paid":
                if not btc_txid or not self._validate_txid(btc_txid):
                    raise CashoutError("valid_btc_txid_required")

            # failed requires a reason
            if new_state == "failed" and not failure_reason:
                raise CashoutError("failure_reason_required")

            con.execute(
                """UPDATE cashout_requests
                   SET state = ?, btc_txid = ?, failure_reason = ?,
                       updated_at = ?
                   WHERE request_id = ?""",
                (
                    new_state,
                    btc_txid or row["btc_txid"],
                    failure_reason or row["failure_reason"],
                    int(time.time()),
                    request_id,
                ),
            )
            return self._row_dict(
                con.execute(
                    "SELECT * FROM cashout_requests WHERE request_id = ?",
                    (request_id,),
                ).fetchone(),
            )

    # ── Queries ──────────────────────────────────────────────────────────

    def get_request(self, request_id: str) -> dict[str, Any] | None:
        with self._tx() as con:
            row = con.execute(
                "SELECT * FROM cashout_requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            return self._row_dict(row) if row else None

    def list_requests(
        self, earn_user_id: str, *, limit: int = 50,
    ) -> list[dict[str, Any]]:
        with self._tx() as con:
            rows = con.execute(
                """SELECT * FROM cashout_requests
                   WHERE earn_user_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (earn_user_id, min(max(limit, 1), 200)),
            ).fetchall()
            return [self._row_dict(r) for r in rows]

    def list_pending(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._tx() as con:
            rows = con.execute(
                """SELECT * FROM cashout_requests
                   WHERE state NOT IN ('paid', 'failed', 'cancelled')
                   ORDER BY created_at ASC LIMIT ?""",
                (min(max(limit, 1), 500),),
            ).fetchall()
            return [self._row_dict(r) for r in rows]

    # ── Capability check ─────────────────────────────────────────────────

    def payout_capability(self) -> dict[str, Any]:
        """Return current payout readiness — always reports honestly."""
        issues: list[str] = []

        # Fee schedule
        try:
            fee = self._fees.cashout_fee_percent()
            if fee < _FEE_FLOOR_PERCENT or fee > _FEE_CEILING_PERCENT:
                issues.append(f"fee {fee}% outside 8-18% bounds")
        except Exception as e:
            issues.append(f"fee_schedule: {e}")

        # Quote provider
        try:
            quote = self._quote.btc_usd_quote()
            if quote <= 0:
                issues.append("btc_quote_zero_or_negative")
        except Exception as e:
            issues.append(f"quote_provider: {e}")

        # Reserve / signer — we have no live adapter, so always report missing
        issues.append("btc_reserve_not_verified")
        issues.append("btc_signer_not_available")

        return {
            "cashout_enabled": len(issues) == 0,
            "min_usd": str(_MIN_CASHOUT_USD),
            "fee_bounds": {"floor": str(_FEE_FLOOR_PERCENT), "ceiling": str(_FEE_CEILING_PERCENT)},
            "issues": issues,
        }

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _validate_txid(txid: str) -> bool:
        """Validate that txid looks like a real Bitcoin transaction hash."""
        if not txid or len(txid) != 64:
            return False
        try:
            bytes.fromhex(txid)
            return True
        except ValueError:
            return False

    @staticmethod
    def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)
