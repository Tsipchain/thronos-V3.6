"""
Thronos Earn — BTC Cash-Out Settlement

Independent path: reserve → signed BTC tx → broadcast → txid → node-confirmed → paid.

State machine:
  cashout_requested → reserve_locked → signing → broadcasted
    → needs_reconciliation (uncertain broadcast)
    → confirmed → paid
  Any non-terminal state → failed
  cashout_requested → cancelled (user-initiated)

THC-to-USD conversion:
  THC is an internal reward token, NOT pegged 1:1 to USD. The conversion
  rate is injected via ThcUsdRateProvider, which the operator sets from
  the actual provider conversion used when THC was minted. For reference:
    - TimeWall mints at TIMEWALL_THC_CONVERSION THC per $1 (default 670)
    - PureSpectrum mints at PURE_THC_CONVERSION THC per $1 (default 100)
  The cashout rate MUST reflect the operator's redemption policy, not the
  minting rate — they may differ.

Design constraints:
  - Earn Account is email-and-credential first; Thronos Wallet is optional.
  - THC is the CPX/Earn reward currency; never mixed with THR, L2E, pledge, AMM.
  - BTC minimum is USD 25 equivalent; rate comes from injected quote + THC rate.
  - External BTC cashout fee is 8–18%; exact rate from authoritative env config.
  - No float anywhere — Decimal with satoshi precision (8 decimal places).
  - No fake BTC success, no made-up txid.
  - A payout may become paid ONLY after BTC node confirmation of the txid
    with correct output address and amount. A 64-char hex string alone is NOT proof.
  - Reserve must be verified against ACTUAL BTC hot wallet balance (UTXO query),
    NOT a ledger entry or accounting assumption.
  - If reserve, signer, rate, or broadcast confirmation is unavailable, status
    must remain pending/reviewable — never paid.
  - On uncertain broadcast (exception, timeout), enter needs_reconciliation:
    look up the tx by fingerprint from the BTC node before releasing anything.
  - On crash recovery, in-flight requests go to needs_reconciliation (not failed)
    when a broadcast may have occurred.
  - No keys, no secret values in code/logs/tests.
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
    "cashout_requested":      {"reserve_locked", "failed", "cancelled"},
    "reserve_locked":         {"signing", "failed"},
    "signing":                {"broadcasted", "needs_reconciliation", "failed"},
    "broadcasted":            {"confirmed", "needs_reconciliation", "failed"},
    "needs_reconciliation":   {"confirmed", "failed"},
    "confirmed":              {"paid", "failed"},
    "paid":                   set(),      # terminal
    "failed":                 set(),      # terminal
    "cancelled":              set(),      # terminal
}

_INFLIGHT_STATES = {"reserve_locked", "signing", "broadcasted", "needs_reconciliation", "confirmed"}


class CashoutError(ValueError):
    pass


# ── Protocol interfaces (dependency injection) ───────────────────────────

class QuoteProvider(Protocol):
    def btc_usd_quote(self) -> Decimal: ...


class FeeSchedule(Protocol):
    def cashout_fee_percent(self) -> Decimal: ...


class ThcUsdRateProvider(Protocol):
    """Returns how many THC equal $1 USD for cashout purposes.

    This is the operator's redemption rate, not necessarily the minting rate.
    E.g. if THC is minted at 670 per $1 but the cashout policy redeems at
    700 per $1, this returns Decimal("700").
    """
    def thc_per_usd(self) -> Decimal: ...


class ReserveProvider(Protocol):
    """Checks actual BTC reserve (UTXO-based, not a ledger entry).

    confirmed_balance_sat() must query the real hot wallet and return
    the confirmed balance in satoshis as int. Raise on RPC failure.
    lock()/release() manage a per-request hold so concurrent settlements
    don't overspend the same UTXOs.
    """
    def confirmed_balance_sat(self) -> int: ...
    def lock(self, request_id: str, amount_sat: int) -> bool: ...
    def release(self, request_id: str) -> None: ...


class BtcBroadcaster(Protocol):
    """Signs and broadcasts a BTC transaction.

    sign_and_broadcast() returns a BroadcastResult. The implementation
    holds the signing key (HSM/KMS) — this module never sees it.
    """
    def sign_and_broadcast(
        self, *, to_address: str, amount_sat: int, request_id: str,
    ) -> "BroadcastResult": ...


class BtcNodeVerifier(Protocol):
    """Confirms a transaction on-chain from the BTC node.

    verify_tx() queries the node for the txid. Returns a VerifyResult
    with confirmed=True only when the tx exists, has the expected
    output address, and the output amount in satoshis matches.
    lookup_by_fingerprint() searches for a tx matching a request_id-based
    fingerprint (e.g. OP_RETURN, unique UTXO pattern) — used for
    reconciliation after uncertain broadcast.
    """
    def verify_tx(
        self, *, txid: str, expected_address: str, expected_amount_sat: int,
    ) -> "VerifyResult": ...

    def lookup_by_fingerprint(self, *, request_id: str) -> "VerifyResult": ...


class BroadcastResult:
    __slots__ = ("success", "txid", "raw_hex", "error", "uncertain")

    def __init__(
        self, *, success: bool, txid: str = "",
        raw_hex: str = "", error: str = "",
        uncertain: bool = False,
    ):
        self.success = success
        self.txid = txid
        self.raw_hex = raw_hex
        self.error = error
        self.uncertain = uncertain


class VerifyResult:
    __slots__ = ("confirmed", "txid", "amount_sat", "error")

    def __init__(
        self, *, confirmed: bool, txid: str = "",
        amount_sat: int = 0, error: str = "",
    ):
        self.confirmed = confirmed
        self.txid = txid
        self.amount_sat = amount_sat
        self.error = error


# ── Fee / rate implementations ───────────────────────────────────────────

class EnvFeeSchedule:
    """Read fee from EARN_CASHOUT_FEE_PERCENT env var."""

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


class EnvThcUsdRate:
    """Read THC-per-USD redemption rate from EARN_THC_CASHOUT_RATE env var.

    Defaults to 670 (the TimeWall minting default) if not set.
    Must be positive. Operator should set this to match their cashout policy.
    """

    def thc_per_usd(self) -> Decimal:
        raw = os.getenv("EARN_THC_CASHOUT_RATE", "").strip()
        if not raw:
            raise CashoutError("thc_cashout_rate_not_configured")
        try:
            rate = Decimal(raw)
        except (InvalidOperation, TypeError):
            raise CashoutError("thc_cashout_rate_invalid")
        if rate <= 0:
            raise CashoutError("thc_cashout_rate_invalid")
        return rate


def validate_btc_address(address: str) -> str:
    address = (address or "").strip()
    if not address or not _BTC_ADDR_RE.match(address):
        raise CashoutError("invalid_btc_address")
    return address


def _validate_txid(txid: str) -> bool:
    if not txid or len(txid) != 64:
        return False
    try:
        bytes.fromhex(txid)
        return True
    except ValueError:
        return False


# ── Main store ───────────────────────────────────────────────────────────

class EarnBtcCashoutStore:
    """SQLite-backed BTC cashout request ledger with settlement orchestration.

    Isolated from wallet core, THR ledger, pledge, AMM, and mining.
    """

    def __init__(
        self,
        db_path: str,
        *,
        quote_provider: QuoteProvider,
        fee_schedule: FeeSchedule,
        thc_rate_provider: ThcUsdRateProvider,
        reserve_provider: ReserveProvider | None = None,
        broadcaster: BtcBroadcaster | None = None,
        node_verifier: BtcNodeVerifier | None = None,
    ):
        self.db_path = db_path
        self._quote = quote_provider
        self._fees = fee_schedule
        self._thc_rate = thc_rate_provider
        self._reserve = reserve_provider
        self._broadcaster = broadcaster
        self._verifier = node_verifier
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
                    thc_per_usd         TEXT NOT NULL,
                    usd_equivalent      TEXT NOT NULL,
                    btc_usd_quote       TEXT NOT NULL,
                    btc_amount_sat      TEXT NOT NULL,
                    state               TEXT NOT NULL DEFAULT 'cashout_requested',
                    btc_txid            TEXT,
                    raw_tx_hex          TEXT,
                    verified_amount_sat TEXT,
                    failure_reason      TEXT,
                    idempotency_key     TEXT NOT NULL UNIQUE,
                    reserve_locked_at   INTEGER,
                    broadcast_at        INTEGER,
                    confirmed_at        INTEGER,
                    paid_at             INTEGER,
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

        # Convert THC → USD using the operator's redemption rate
        try:
            thc_per_usd = self._thc_rate.thc_per_usd()
        except CashoutError:
            raise
        except Exception as exc:
            raise CashoutError("thc_rate_unavailable") from exc
        if thc_per_usd <= 0:
            raise CashoutError("thc_rate_invalid")

        usd_equiv = (net_thc / thc_per_usd).quantize(_USD_SCALE, rounding=ROUND_DOWN)
        if usd_equiv < _MIN_CASHOUT_USD:
            raise CashoutError("below_minimum_usd")

        try:
            btc_usd = self._quote.btc_usd_quote()
        except Exception:
            raise CashoutError("btc_quote_unavailable")
        if btc_usd <= 0:
            raise CashoutError("btc_quote_invalid")

        btc_amount = (usd_equiv / btc_usd).quantize(_SAT_SCALE, rounding=ROUND_DOWN)
        if btc_amount <= 0:
            raise CashoutError("btc_amount_zero")

        btc_amount_sat = int(btc_amount / _SAT_SCALE)

        day_str = time.strftime("%Y-%m-%d", time.gmtime())
        idem_raw = f"{earn_user_id}:{btc_address}:{thc_amt}:{day_str}"
        idem_key = hashlib.sha256(idem_raw.encode()).hexdigest()

        request_id = "co_" + secrets.token_urlsafe(18)
        now = int(time.time())

        with self._tx() as con:
            existing = con.execute(
                "SELECT * FROM cashout_requests WHERE idempotency_key = ?",
                (idem_key,),
            ).fetchone()
            if existing:
                return self._row_dict(existing)

            con.execute(
                """INSERT INTO cashout_requests
                   (request_id, earn_user_id, btc_address, thc_amount,
                    fee_percent, fee_thc, net_thc, thc_per_usd,
                    usd_equivalent, btc_usd_quote, btc_amount_sat,
                    state, idempotency_key, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,'cashout_requested',?,?,?)""",
                (
                    request_id, earn_user_id, btc_address,
                    str(thc_amt), str(fee_pct), str(fee_thc), str(net_thc),
                    str(thc_per_usd), str(usd_equiv), str(btc_usd),
                    str(btc_amount_sat), idem_key, now, now,
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
        raw_tx_hex: str | None = None,
        verified_amount_sat: str | None = None,
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

            if new_state == "confirmed":
                if not btc_txid or not _validate_txid(btc_txid):
                    raise CashoutError("valid_btc_txid_required")
                if not verified_amount_sat:
                    raise CashoutError("verified_amount_required")

            if new_state == "paid":
                if not row["btc_txid"] or not _validate_txid(row["btc_txid"]):
                    raise CashoutError("valid_btc_txid_required")
                if not row["verified_amount_sat"]:
                    raise CashoutError("verified_amount_required")

            if new_state == "failed" and not failure_reason:
                raise CashoutError("failure_reason_required")

            now = int(time.time())
            extra_cols = ""
            extra_vals: list[Any] = []
            if new_state == "reserve_locked":
                extra_cols += ", reserve_locked_at = ?"
                extra_vals.append(now)
            elif new_state == "broadcasted":
                extra_cols += ", broadcast_at = ?"
                extra_vals.append(now)
            elif new_state == "confirmed":
                extra_cols += ", confirmed_at = ?, verified_amount_sat = ?"
                extra_vals.extend([now, verified_amount_sat])
            elif new_state == "paid":
                extra_cols += ", paid_at = ?"
                extra_vals.append(now)

            con.execute(
                f"""UPDATE cashout_requests
                   SET state = ?, btc_txid = ?, raw_tx_hex = ?,
                       failure_reason = ?, updated_at = ?{extra_cols}
                   WHERE request_id = ?""",
                (
                    new_state,
                    btc_txid or row["btc_txid"],
                    raw_tx_hex or row["raw_tx_hex"],
                    failure_reason or row["failure_reason"],
                    now,
                    *extra_vals,
                    request_id,
                ),
            )
            return self._row_dict(
                con.execute(
                    "SELECT * FROM cashout_requests WHERE request_id = ?",
                    (request_id,),
                ).fetchone(),
            )

    # ── Settlement orchestrator ──────────────────────────────────────────

    def settle(self, request_id: str) -> dict[str, Any]:
        """Drive a request through reserve → sign → broadcast → confirm → paid.

        Each step is persisted to the DB before the next begins, so a crash
        at any point leaves the record in a recoverable state.

        After broadcast, the txid is verified against the BTC node (correct
        output address and amount) before marking confirmed. On uncertain
        broadcast (exception/timeout), the request enters needs_reconciliation
        instead of failing — nothing is released until we know the outcome.
        """
        rec = self.get_request(request_id)
        if not rec:
            raise CashoutError("cashout_request_not_found")

        if rec["state"] in ("paid", "failed", "cancelled"):
            return rec

        if not self._reserve:
            return self.transition(request_id, "failed",
                                   failure_reason="reserve_provider_not_configured")
        if not self._broadcaster:
            return self.transition(request_id, "failed",
                                   failure_reason="broadcaster_not_configured")
        if not self._verifier:
            return self.transition(request_id, "failed",
                                   failure_reason="node_verifier_not_configured")

        amount_sat = int(rec["btc_amount_sat"])

        # Step 1: verify and lock reserve
        if rec["state"] == "cashout_requested":
            try:
                balance_sat = self._reserve.confirmed_balance_sat()
            except Exception as e:
                return self.transition(request_id, "failed",
                                       failure_reason=f"reserve_query_failed:{e}")
            if balance_sat < amount_sat:
                return self.transition(request_id, "failed",
                                       failure_reason="insufficient_btc_reserve")
            locked = self._reserve.lock(request_id, amount_sat)
            if not locked:
                return self.transition(request_id, "failed",
                                       failure_reason="reserve_lock_failed")
            rec = self.transition(request_id, "reserve_locked")

        # Step 2: signing phase
        if rec["state"] == "reserve_locked":
            rec = self.transition(request_id, "signing")

        # Step 3: broadcast
        if rec["state"] == "signing":
            try:
                result = self._broadcaster.sign_and_broadcast(
                    to_address=rec["btc_address"],
                    amount_sat=amount_sat,
                    request_id=request_id,
                )
            except Exception as e:
                rec = self.transition(request_id, "needs_reconciliation",
                                      failure_reason=f"broadcast_exception:{e}")
            else:
                if result.uncertain:
                    rec = self.transition(request_id, "needs_reconciliation",
                                          btc_txid=result.txid if _validate_txid(result.txid or "") else None,
                                          failure_reason="broadcast_uncertain")
                elif not result.success:
                    self._reserve.release(request_id)
                    return self.transition(request_id, "failed",
                                           failure_reason=f"broadcast_failed:{result.error}")
                elif not _validate_txid(result.txid):
                    self._reserve.release(request_id)
                    return self.transition(request_id, "failed",
                                           failure_reason="broadcast_returned_invalid_txid")
                else:
                    rec = self.transition(request_id, "broadcasted",
                                          btc_txid=result.txid,
                                          raw_tx_hex=result.raw_hex)

        # Step 4: verify tx on node
        if rec["state"] == "broadcasted":
            rec = self._verify_and_confirm(rec)

        # Step 5: reconcile uncertain broadcasts
        if rec["state"] == "needs_reconciliation":
            rec = self._try_reconcile(rec)

        # Step 6: mark paid (confirmed = node-verified output)
        if rec["state"] == "confirmed":
            rec = self.transition(request_id, "paid")

        return rec

    def _verify_and_confirm(self, rec: dict[str, Any]) -> dict[str, Any]:
        rid = rec["request_id"]
        txid = rec.get("btc_txid", "")
        amount_sat = int(rec["btc_amount_sat"])

        if not txid or not _validate_txid(txid):
            return self.transition(rid, "needs_reconciliation",
                                   failure_reason="broadcasted_without_valid_txid")

        try:
            vr = self._verifier.verify_tx(
                txid=txid,
                expected_address=rec["btc_address"],
                expected_amount_sat=amount_sat,
            )
        except Exception as e:
            return self.transition(rid, "needs_reconciliation",
                                   failure_reason=f"verify_exception:{e}")

        if not vr.confirmed:
            return self.transition(rid, "needs_reconciliation",
                                   failure_reason=f"verify_failed:{vr.error}")

        return self.transition(rid, "confirmed",
                               btc_txid=vr.txid or txid,
                               verified_amount_sat=str(vr.amount_sat))

    def _try_reconcile(self, rec: dict[str, Any]) -> dict[str, Any]:
        rid = rec["request_id"]
        if not self._verifier:
            return rec

        amount_sat = int(rec["btc_amount_sat"])

        # Try by txid first if we have one
        txid = rec.get("btc_txid", "")
        if txid and _validate_txid(txid):
            try:
                vr = self._verifier.verify_tx(
                    txid=txid,
                    expected_address=rec["btc_address"],
                    expected_amount_sat=amount_sat,
                )
                if vr.confirmed:
                    return self.transition(rid, "confirmed",
                                           btc_txid=vr.txid or txid,
                                           verified_amount_sat=str(vr.amount_sat))
            except Exception:
                pass

        # Fall back to fingerprint lookup
        try:
            vr = self._verifier.lookup_by_fingerprint(request_id=rid)
            if vr.confirmed:
                return self.transition(rid, "confirmed",
                                       btc_txid=vr.txid,
                                       verified_amount_sat=str(vr.amount_sat))
        except Exception:
            pass

        # Still uncertain — stay in needs_reconciliation, don't release anything
        return rec

    # ── Crash recovery ───────────────────────────────────────────────────

    def recover_inflight(self) -> list[dict[str, Any]]:
        """On startup, find requests stuck in non-terminal states and handle them.

        - reserve_locked (no broadcast attempted) → release reserve, fail
        - signing / broadcasted / needs_reconciliation → try reconciliation
          from node; if unconfirmed, stay needs_reconciliation (NOT failed,
          because we don't know if the tx was broadcast)
        - confirmed → promote to paid
        """
        recovered: list[dict[str, Any]] = []
        pending = self._list_by_states(list(_INFLIGHT_STATES))

        for rec in pending:
            rid = rec["request_id"]
            state = rec["state"]

            if state == "reserve_locked":
                if self._reserve:
                    try:
                        self._reserve.release(rid)
                    except Exception:
                        pass
                result = self.transition(
                    rid, "failed",
                    failure_reason=f"crash_recovery:stuck_in_{state}",
                )
                recovered.append(result)

            elif state == "confirmed":
                result = self.transition(rid, "paid")
                recovered.append(result)

            elif state in ("signing", "broadcasted", "needs_reconciliation"):
                # A broadcast may have occurred — must check the node
                recon_rec = rec
                if state in ("signing", "broadcasted"):
                    recon_rec = self.transition(
                        rid, "needs_reconciliation",
                        failure_reason=f"crash_recovery:stuck_in_{state}",
                    )
                result = self._try_reconcile(recon_rec)
                recovered.append(result)

        return recovered

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

    def _list_by_states(self, states: list[str]) -> list[dict[str, Any]]:
        if not states:
            return []
        placeholders = ",".join("?" for _ in states)
        with self._tx() as con:
            rows = con.execute(
                f"""SELECT * FROM cashout_requests
                    WHERE state IN ({placeholders})
                    ORDER BY created_at ASC""",
                states,
            ).fetchall()
            return [self._row_dict(r) for r in rows]

    # ── Capability check ─────────────────────────────────────────────────

    def payout_capability(self) -> dict[str, Any]:
        issues: list[str] = []

        try:
            fee = self._fees.cashout_fee_percent()
            if fee < _FEE_FLOOR_PERCENT or fee > _FEE_CEILING_PERCENT:
                issues.append(f"fee {fee}% outside 8-18% bounds")
        except Exception as e:
            issues.append(f"fee_schedule: {e}")

        try:
            rate = self._thc_rate.thc_per_usd()
            if rate <= 0:
                issues.append("thc_rate_zero_or_negative")
        except Exception as e:
            issues.append(f"thc_rate: {e}")

        try:
            quote = self._quote.btc_usd_quote()
            if quote <= 0:
                issues.append("btc_quote_zero_or_negative")
        except Exception as e:
            issues.append(f"quote_provider: {e}")

        if not self._reserve:
            issues.append("btc_reserve_provider_not_configured")
        else:
            try:
                bal = self._reserve.confirmed_balance_sat()
                if bal <= 0:
                    issues.append("btc_reserve_empty")
            except Exception as e:
                issues.append(f"btc_reserve_query_failed: {e}")

        if not self._broadcaster:
            issues.append("btc_broadcaster_not_configured")

        if not self._verifier:
            issues.append("btc_node_verifier_not_configured")

        return {
            "cashout_enabled": len(issues) == 0,
            "min_usd": str(_MIN_CASHOUT_USD),
            "fee_bounds": {"floor": str(_FEE_FLOOR_PERCENT), "ceiling": str(_FEE_CEILING_PERCENT)},
            "issues": issues,
        }

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)
