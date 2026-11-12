"""Tests for Earn BTC Cash-Out Settlement Pipeline.

Covers: THC→USD conversion (not 1:1), request creation, state machine, fee bounds,
BTC address validation, idempotency, Decimal precision, settlement orchestration
(reserve → sign → broadcast → node verify → confirm → paid), insufficient reserve,
broadcast failure, uncertain broadcast → needs_reconciliation, double request,
crash recovery, concurrent settlement with threading, and source safety.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.earn_btc_cashout import (
    BroadcastResult,
    CashoutError,
    EarnBtcCashoutStore,
    EnvFeeSchedule,
    EnvThcUsdRate,
    VerifyResult,
    _FEE_CEILING_PERCENT,
    _FEE_FLOOR_PERCENT,
    _MIN_CASHOUT_USD,
    _SAT_SCALE,
    _THC_SCALE,
    _validate_txid,
    validate_btc_address,
)

VALID_BTC_ADDR = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
VALID_BECH32_ADDR = "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"
VALID_P2SH_ADDR = "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy"
VALID_TXID = "a" * 64
USER_ID = "earn_user_test_001"
GOOD_QUOTE = Decimal("50000.00")
GOOD_FEE_PCT = Decimal("12.0000")
GOOD_THC_RATE = Decimal("670")  # 670 THC = $1 USD (TimeWall default)


class FakeQuote:
    def __init__(self, price: Decimal = GOOD_QUOTE):
        self._price = price

    def btc_usd_quote(self) -> Decimal:
        return self._price


class FakeFee:
    def __init__(self, pct: Decimal = GOOD_FEE_PCT):
        self._pct = pct

    def cashout_fee_percent(self) -> Decimal:
        return self._pct


class FakeThcRate:
    def __init__(self, rate: Decimal = GOOD_THC_RATE):
        self._rate = rate

    def thc_per_usd(self) -> Decimal:
        return self._rate


class FakeReserve:
    def __init__(self, balance_sat: int = 10_000_000_000):
        self._balance = balance_sat
        self._locks: dict[str, int] = {}
        self.lock_calls: list[tuple[str, int]] = []
        self.release_calls: list[str] = []

    def confirmed_balance_sat(self) -> int:
        return self._balance

    def lock(self, request_id: str, amount_sat: int) -> bool:
        self.lock_calls.append((request_id, amount_sat))
        if amount_sat > self._balance:
            return False
        self._locks[request_id] = amount_sat
        self._balance -= amount_sat
        return True

    def release(self, request_id: str) -> None:
        self.release_calls.append(request_id)
        if request_id in self._locks:
            self._balance += self._locks.pop(request_id)


class FakeBroadcaster:
    def __init__(self, *, succeed: bool = True, txid: str = VALID_TXID, uncertain: bool = False):
        self._succeed = succeed
        self._txid = txid
        self._uncertain = uncertain
        self.calls: list[dict] = []

    def sign_and_broadcast(self, *, to_address: str, amount_sat: int, request_id: str) -> BroadcastResult:
        self.calls.append({"to_address": to_address, "amount_sat": amount_sat, "request_id": request_id})
        if self._uncertain:
            return BroadcastResult(success=False, txid=self._txid, uncertain=True, error="timeout")
        if self._succeed:
            return BroadcastResult(success=True, txid=self._txid, raw_hex="deadbeef" * 8)
        return BroadcastResult(success=False, error="node_unreachable")


class FakeVerifier:
    def __init__(self, *, confirmed: bool = True, amount_sat: int = 0):
        self._confirmed = confirmed
        self._amount_sat = amount_sat
        self.verify_calls: list[dict] = []
        self.lookup_calls: list[str] = []

    def verify_tx(self, *, txid: str, expected_address: str, expected_amount_sat: int) -> VerifyResult:
        self.verify_calls.append({"txid": txid, "address": expected_address, "amount": expected_amount_sat})
        sat = self._amount_sat if self._amount_sat else expected_amount_sat
        if self._confirmed:
            return VerifyResult(confirmed=True, txid=txid, amount_sat=sat)
        return VerifyResult(confirmed=False, error="tx_not_found")

    def lookup_by_fingerprint(self, *, request_id: str) -> VerifyResult:
        self.lookup_calls.append(request_id)
        if self._confirmed:
            return VerifyResult(confirmed=True, txid=VALID_TXID, amount_sat=self._amount_sat or 1000)
        return VerifyResult(confirmed=False, error="no_matching_tx")


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "cashout_test.db")


def _full_store(db_path, **overrides):
    defaults = dict(
        quote_provider=FakeQuote(),
        fee_schedule=FakeFee(),
        thc_rate_provider=FakeThcRate(),
        reserve_provider=FakeReserve(),
        broadcaster=FakeBroadcaster(),
        node_verifier=FakeVerifier(),
    )
    defaults.update(overrides)
    return EarnBtcCashoutStore(db_path, **defaults)


@pytest.fixture
def store(db_path):
    return _full_store(db_path)


@pytest.fixture
def store_no_infra(db_path):
    return EarnBtcCashoutStore(
        db_path,
        quote_provider=FakeQuote(),
        fee_schedule=FakeFee(),
        thc_rate_provider=FakeThcRate(),
    )


# At rate 670 THC/$1, with 12% fee:
# 25000 THC → net 22000 → $32.84 USD → passes $25 minimum
# 100 THC → net 88 → $0.13 USD → below minimum
def _make_request(store, *, thc="25000.000000", available="100000.000000", addr=VALID_BTC_ADDR, user=USER_ID):
    return store.create_cashout_request(
        earn_user_id=user,
        btc_address=addr,
        thc_amount=thc,
        available_thc=available,
    )


# ══════════════════════════════════════════════════════════════════════════
# 1. THC→USD conversion (NOT 1:1)
# ══════════════════════════════════════════════════════════════════════════

class TestThcUsdConversion:
    def test_thc_not_one_to_one_usd(self, store):
        rec = _make_request(store, thc="25000.000000")
        usd = Decimal(rec["usd_equivalent"])
        thc_rate = Decimal(rec["thc_per_usd"])
        assert thc_rate == GOOD_THC_RATE
        net = Decimal(rec["net_thc"])
        expected_usd = (net / GOOD_THC_RATE).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        assert usd == expected_usd
        assert usd < Decimal(rec["net_thc"])

    def test_thc_rate_stored_in_record(self, store):
        rec = _make_request(store)
        assert "thc_per_usd" in rec
        assert Decimal(rec["thc_per_usd"]) == GOOD_THC_RATE

    def test_different_thc_rate_changes_usd(self, db_path):
        s1 = _full_store(db_path, thc_rate_provider=FakeThcRate(Decimal("670")))
        r1 = _make_request(s1)
        db2 = db_path + ".2"
        s2 = _full_store(db2, thc_rate_provider=FakeThcRate(Decimal("100")))
        r2 = _make_request(s2)
        assert Decimal(r2["usd_equivalent"]) > Decimal(r1["usd_equivalent"])

    def test_thc_rate_not_configured_rejects(self, db_path):
        rate = FakeThcRate()
        rate.thc_per_usd = MagicMock(side_effect=CashoutError("thc_cashout_rate_not_configured"))
        store = _full_store(db_path, thc_rate_provider=rate)
        with pytest.raises(CashoutError, match="thc_cashout_rate_not_configured"):
            _make_request(store)

    def test_env_thc_rate_configured(self):
        with patch.dict(os.environ, {"EARN_THC_CASHOUT_RATE": "670"}):
            rate = EnvThcUsdRate()
            assert rate.thc_per_usd() == Decimal("670")

    def test_env_thc_rate_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("EARN_THC_CASHOUT_RATE", None)
            with pytest.raises(CashoutError, match="thc_cashout_rate_not_configured"):
                EnvThcUsdRate().thc_per_usd()

    def test_env_thc_rate_zero(self):
        with patch.dict(os.environ, {"EARN_THC_CASHOUT_RATE": "0"}):
            with pytest.raises(CashoutError, match="thc_cashout_rate_invalid"):
                EnvThcUsdRate().thc_per_usd()

    def test_below_25_usd_at_real_rate(self, db_path):
        store = _full_store(db_path, thc_rate_provider=FakeThcRate(Decimal("670")))
        with pytest.raises(CashoutError, match="below_minimum_usd"):
            _make_request(store, thc="100.000000")


# ══════════════════════════════════════════════════════════════════════════
# 2. Request creation
# ══════════════════════════════════════════════════════════════════════════

class TestCreateRequest:
    def test_basic_creation(self, store):
        rec = _make_request(store)
        assert rec["state"] == "cashout_requested"
        assert rec["earn_user_id"] == USER_ID
        assert rec["btc_address"] == VALID_BTC_ADDR
        assert rec["request_id"].startswith("co_")

    def test_fee_deducted(self, store):
        rec = _make_request(store, thc="25000.000000")
        fee = Decimal(rec["fee_thc"])
        net = Decimal(rec["net_thc"])
        assert fee == Decimal("3000.000000")
        assert net == Decimal("22000.000000")

    def test_btc_amount_sat_calculated(self, store):
        rec = _make_request(store)
        sat = int(rec["btc_amount_sat"])
        assert sat > 0

    def test_insufficient_balance(self, store):
        with pytest.raises(CashoutError, match="insufficient_thc_balance"):
            _make_request(store, thc="200000.000000", available="100000.000000")

    def test_zero_amount(self, store):
        with pytest.raises(CashoutError, match="invalid_thc_amount"):
            _make_request(store, thc="0")

    def test_negative_amount(self, store):
        with pytest.raises(CashoutError, match="invalid_thc_amount"):
            _make_request(store, thc="-50")


# ══════════════════════════════════════════════════════════════════════════
# 3. Idempotency
# ══════════════════════════════════════════════════════════════════════════

class TestIdempotency:
    def test_same_params_same_day_returns_existing(self, store):
        r1 = _make_request(store)
        r2 = _make_request(store)
        assert r1["request_id"] == r2["request_id"]

    def test_different_address_creates_new(self, store):
        r1 = _make_request(store, addr=VALID_BTC_ADDR)
        r2 = _make_request(store, addr=VALID_BECH32_ADDR)
        assert r1["request_id"] != r2["request_id"]

    def test_different_amount_creates_new(self, store):
        r1 = _make_request(store, thc="25000.000000")
        r2 = _make_request(store, thc="50000.000000")
        assert r1["request_id"] != r2["request_id"]


# ══════════════════════════════════════════════════════════════════════════
# 4. BTC address validation
# ══════════════════════════════════════════════════════════════════════════

class TestBtcAddressValidation:
    @pytest.mark.parametrize("addr", [VALID_BTC_ADDR, VALID_BECH32_ADDR, VALID_P2SH_ADDR])
    def test_valid_mainnet_addresses(self, addr):
        assert validate_btc_address(addr) == addr

    @pytest.mark.parametrize("addr", ["", "   ", "not-an-address", "tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx"])
    def test_invalid_addresses(self, addr):
        with pytest.raises(CashoutError, match="invalid_btc_address"):
            validate_btc_address(addr)

    def test_whitespace_stripped(self):
        result = validate_btc_address(f"  {VALID_BTC_ADDR}  ")
        assert result == VALID_BTC_ADDR


# ══════════════════════════════════════════════════════════════════════════
# 5. Fee bounds (8–18%)
# ══════════════════════════════════════════════════════════════════════════

class TestFeeBounds:
    def test_env_fee_in_bounds(self):
        with patch.dict(os.environ, {"EARN_CASHOUT_FEE_PERCENT": "12"}):
            assert EnvFeeSchedule().cashout_fee_percent() == Decimal("12.0000")

    def test_env_fee_at_floor(self):
        with patch.dict(os.environ, {"EARN_CASHOUT_FEE_PERCENT": "8"}):
            assert EnvFeeSchedule().cashout_fee_percent() == Decimal("8.0000")

    def test_env_fee_at_ceiling(self):
        with patch.dict(os.environ, {"EARN_CASHOUT_FEE_PERCENT": "18"}):
            assert EnvFeeSchedule().cashout_fee_percent() == Decimal("18.0000")

    def test_env_fee_below_floor(self):
        with patch.dict(os.environ, {"EARN_CASHOUT_FEE_PERCENT": "7.9"}):
            with pytest.raises(CashoutError, match="cashout_fee_out_of_bounds"):
                EnvFeeSchedule().cashout_fee_percent()

    def test_env_fee_above_ceiling(self):
        with patch.dict(os.environ, {"EARN_CASHOUT_FEE_PERCENT": "18.1"}):
            with pytest.raises(CashoutError, match="cashout_fee_out_of_bounds"):
                EnvFeeSchedule().cashout_fee_percent()

    def test_env_fee_not_configured(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("EARN_CASHOUT_FEE_PERCENT", None)
            with pytest.raises(CashoutError, match="cashout_fee_not_configured"):
                EnvFeeSchedule().cashout_fee_percent()

    def test_env_fee_garbage(self):
        with patch.dict(os.environ, {"EARN_CASHOUT_FEE_PERCENT": "abc"}):
            with pytest.raises(CashoutError, match="cashout_fee_invalid"):
                EnvFeeSchedule().cashout_fee_percent()


# ══════════════════════════════════════════════════════════════════════════
# 6. State machine transitions
# ══════════════════════════════════════════════════════════════════════════

class TestStateMachine:
    def test_valid_forward_transitions(self, store):
        rec = _make_request(store)
        rid = rec["request_id"]
        sat = rec["btc_amount_sat"]
        rec = store.transition(rid, "reserve_locked")
        assert rec["state"] == "reserve_locked"
        rec = store.transition(rid, "signing")
        assert rec["state"] == "signing"
        rec = store.transition(rid, "broadcasted", btc_txid=VALID_TXID)
        assert rec["state"] == "broadcasted"
        rec = store.transition(rid, "confirmed", btc_txid=VALID_TXID, verified_amount_sat=sat)
        assert rec["state"] == "confirmed"
        rec = store.transition(rid, "paid")
        assert rec["state"] == "paid"

    def test_cannot_skip_states(self, store):
        rec = _make_request(store)
        with pytest.raises(CashoutError, match="invalid_cashout_transition"):
            store.transition(rec["request_id"], "paid")

    def test_confirmed_requires_txid_and_amount(self, store):
        rec = _make_request(store)
        rid = rec["request_id"]
        store.transition(rid, "reserve_locked")
        store.transition(rid, "signing")
        store.transition(rid, "broadcasted", btc_txid=VALID_TXID)
        with pytest.raises(CashoutError, match="valid_btc_txid_required"):
            store.transition(rid, "confirmed", btc_txid="short", verified_amount_sat="1000")
        with pytest.raises(CashoutError, match="verified_amount_required"):
            store.transition(rid, "confirmed", btc_txid=VALID_TXID)

    def test_paid_requires_prior_confirmed_fields(self, store):
        rec = _make_request(store)
        rid = rec["request_id"]
        sat = rec["btc_amount_sat"]
        store.transition(rid, "reserve_locked")
        store.transition(rid, "signing")
        store.transition(rid, "broadcasted", btc_txid=VALID_TXID)
        store.transition(rid, "confirmed", btc_txid=VALID_TXID, verified_amount_sat=sat)
        result = store.transition(rid, "paid")
        assert result["state"] == "paid"

    def test_needs_reconciliation_from_signing(self, store):
        rec = _make_request(store)
        rid = rec["request_id"]
        store.transition(rid, "reserve_locked")
        store.transition(rid, "signing")
        result = store.transition(rid, "needs_reconciliation", failure_reason="uncertain")
        assert result["state"] == "needs_reconciliation"

    def test_needs_reconciliation_from_broadcasted(self, store):
        rec = _make_request(store)
        rid = rec["request_id"]
        store.transition(rid, "reserve_locked")
        store.transition(rid, "signing")
        store.transition(rid, "broadcasted", btc_txid=VALID_TXID)
        result = store.transition(rid, "needs_reconciliation", failure_reason="verify_failed")
        assert result["state"] == "needs_reconciliation"

    def test_failed_requires_reason(self, store):
        rec = _make_request(store)
        with pytest.raises(CashoutError, match="failure_reason_required"):
            store.transition(rec["request_id"], "failed")

    def test_cancelled_from_requested(self, store):
        rec = _make_request(store)
        result = store.transition(rec["request_id"], "cancelled")
        assert result["state"] == "cancelled"

    def test_cannot_cancel_after_reserve_locked(self, store):
        rec = _make_request(store)
        store.transition(rec["request_id"], "reserve_locked")
        with pytest.raises(CashoutError, match="invalid_cashout_transition"):
            store.transition(rec["request_id"], "cancelled")

    def test_terminal_states_have_no_transitions(self, store):
        rec = _make_request(store)
        store.transition(rec["request_id"], "failed", failure_reason="done")
        with pytest.raises(CashoutError, match="invalid_cashout_transition"):
            store.transition(rec["request_id"], "reserve_locked")


# ══════════════════════════════════════════════════════════════════════════
# 7. Decimal precision — no float contamination
# ══════════════════════════════════════════════════════════════════════════

class TestDecimalPrecision:
    def test_no_float_in_record(self, store):
        rec = _make_request(store)
        for key in ("thc_amount", "fee_percent", "fee_thc", "net_thc",
                     "thc_per_usd", "usd_equivalent", "btc_usd_quote", "btc_amount_sat"):
            val = rec[key]
            assert isinstance(val, str), f"{key} should be stored as string, got {type(val)}"
            Decimal(val)


# ══════════════════════════════════════════════════════════════════════════
# 8. Txid validation
# ══════════════════════════════════════════════════════════════════════════

class TestTxidValidation:
    @pytest.mark.parametrize("txid,expected", [
        ("a" * 64, True), ("0123456789abcdef" * 4, True), ("A" * 64, True),
        ("", False), ("short", False), ("g" * 64, False), ("a" * 63, False),
    ])
    def test_txid_validation(self, txid, expected):
        assert _validate_txid(txid) == expected


# ══════════════════════════════════════════════════════════════════════════
# 9. Queries
# ══════════════════════════════════════════════════════════════════════════

class TestQueries:
    def test_get_request(self, store):
        rec = _make_request(store)
        fetched = store.get_request(rec["request_id"])
        assert fetched is not None
        assert fetched["request_id"] == rec["request_id"]

    def test_get_request_not_found(self, store):
        assert store.get_request("co_nonexistent") is None

    def test_list_requests_for_user(self, store):
        _make_request(store, thc="25000.000000")
        _make_request(store, thc="50000.000000")
        results = store.list_requests(USER_ID)
        assert len(results) == 2

    def test_list_pending(self, store):
        r1 = _make_request(store, thc="25000.000000")
        r2 = _make_request(store, thc="50000.000000")
        store.transition(r2["request_id"], "failed", failure_reason="test")
        pending = store.list_pending()
        assert len(pending) == 1
        assert pending[0]["request_id"] == r1["request_id"]


# ══════════════════════════════════════════════════════════════════════════
# 10. Payout capability
# ══════════════════════════════════════════════════════════════════════════

class TestPayoutCapability:
    def test_all_configured(self, store):
        cap = store.payout_capability()
        assert cap["cashout_enabled"] is True
        assert cap["issues"] == []

    def test_missing_reserve(self, store_no_infra):
        cap = store_no_infra.payout_capability()
        assert cap["cashout_enabled"] is False
        assert any("reserve" in i for i in cap["issues"])

    def test_missing_broadcaster(self, store_no_infra):
        cap = store_no_infra.payout_capability()
        assert any("broadcaster" in i for i in cap["issues"])

    def test_missing_verifier(self, store_no_infra):
        cap = store_no_infra.payout_capability()
        assert any("verifier" in i for i in cap["issues"])

    def test_empty_reserve(self, db_path):
        store = _full_store(db_path, reserve_provider=FakeReserve(balance_sat=0))
        cap = store.payout_capability()
        assert cap["cashout_enabled"] is False
        assert any("empty" in i for i in cap["issues"])


# ══════════════════════════════════════════════════════════════════════════
# 11. Settlement — happy path (with node verification)
# ══════════════════════════════════════════════════════════════════════════

class TestSettleHappyPath:
    def test_full_settlement(self, store):
        rec = _make_request(store)
        result = store.settle(rec["request_id"])
        assert result["state"] == "paid"
        assert result["btc_txid"] == VALID_TXID
        assert result["verified_amount_sat"] is not None
        assert result["confirmed_at"] is not None
        assert result["paid_at"] is not None

    def test_settle_records_timestamps(self, store):
        rec = _make_request(store)
        result = store.settle(rec["request_id"])
        assert result["reserve_locked_at"] is not None
        assert result["broadcast_at"] is not None
        assert result["confirmed_at"] is not None
        assert result["paid_at"] is not None
        assert result["reserve_locked_at"] <= result["broadcast_at"]
        assert result["broadcast_at"] <= result["confirmed_at"] <= result["paid_at"]

    def test_verifier_called_with_correct_args(self, db_path):
        verifier = FakeVerifier()
        store = _full_store(db_path, node_verifier=verifier)
        rec = _make_request(store)
        store.settle(rec["request_id"])
        assert len(verifier.verify_calls) == 1
        call = verifier.verify_calls[0]
        assert call["txid"] == VALID_TXID
        assert call["address"] == VALID_BTC_ADDR
        assert call["amount"] == int(rec["btc_amount_sat"])

    def test_settle_already_paid_is_noop(self, store):
        rec = _make_request(store)
        store.settle(rec["request_id"])
        result = store.settle(rec["request_id"])
        assert result["state"] == "paid"


# ══════════════════════════════════════════════════════════════════════════
# 12. Settlement — insufficient BTC reserve
# ══════════════════════════════════════════════════════════════════════════

class TestInsufficientReserve:
    def test_reserve_balance_too_low(self, db_path):
        store = _full_store(db_path, reserve_provider=FakeReserve(balance_sat=1))
        rec = _make_request(store)
        result = store.settle(rec["request_id"])
        assert result["state"] == "failed"
        assert "insufficient_btc_reserve" in result["failure_reason"]

    def test_reserve_query_raises(self, db_path):
        reserve = FakeReserve()
        reserve.confirmed_balance_sat = MagicMock(side_effect=ConnectionError("rpc down"))
        store = _full_store(db_path, reserve_provider=reserve)
        rec = _make_request(store)
        result = store.settle(rec["request_id"])
        assert result["state"] == "failed"
        assert "reserve_query_failed" in result["failure_reason"]

    def test_reserve_lock_fails(self, db_path):
        reserve = FakeReserve(balance_sat=10_000_000_000)
        reserve.lock = MagicMock(return_value=False)
        store = _full_store(db_path, reserve_provider=reserve)
        rec = _make_request(store)
        result = store.settle(rec["request_id"])
        assert result["state"] == "failed"
        assert "reserve_lock_failed" in result["failure_reason"]

    def test_no_reserve_provider_fails_settle(self, store_no_infra):
        rec = _make_request(store_no_infra)
        result = store_no_infra.settle(rec["request_id"])
        assert result["state"] == "failed"
        assert "reserve_provider_not_configured" in result["failure_reason"]


# ══════════════════════════════════════════════════════════════════════════
# 13. Settlement — broadcast failure
# ══════════════════════════════════════════════════════════════════════════

class TestBroadcastFailure:
    def test_broadcast_returns_failure(self, db_path):
        store = _full_store(db_path, broadcaster=FakeBroadcaster(succeed=False))
        rec = _make_request(store)
        result = store.settle(rec["request_id"])
        assert result["state"] == "failed"
        assert "broadcast_failed" in result["failure_reason"]

    def test_broadcast_releases_reserve_on_definite_failure(self, db_path):
        reserve = FakeReserve()
        store = _full_store(db_path, reserve_provider=reserve, broadcaster=FakeBroadcaster(succeed=False))
        rec = _make_request(store)
        store.settle(rec["request_id"])
        assert rec["request_id"] in reserve.release_calls

    def test_broadcast_returns_invalid_txid(self, db_path):
        store = _full_store(db_path, broadcaster=FakeBroadcaster(succeed=True, txid="not-a-txid"))
        rec = _make_request(store)
        result = store.settle(rec["request_id"])
        assert result["state"] == "failed"
        assert "invalid_txid" in result["failure_reason"]

    def test_no_broadcaster_configured(self, db_path):
        store = _full_store(db_path, broadcaster=None)
        rec = _make_request(store)
        result = store.settle(rec["request_id"])
        assert result["state"] == "failed"
        assert "broadcaster_not_configured" in result["failure_reason"]

    def test_no_verifier_configured(self, db_path):
        store = _full_store(db_path, node_verifier=None)
        rec = _make_request(store)
        result = store.settle(rec["request_id"])
        assert result["state"] == "failed"
        assert "node_verifier_not_configured" in result["failure_reason"]


# ══════════════════════════════════════════════════════════════════════════
# 14. Uncertain broadcast → needs_reconciliation
# ══════════════════════════════════════════════════════════════════════════

class TestUncertainBroadcast:
    def test_uncertain_broadcast_enters_reconciliation(self, db_path):
        verifier = FakeVerifier(confirmed=False)
        store = _full_store(db_path,
                            broadcaster=FakeBroadcaster(uncertain=True),
                            node_verifier=verifier)
        rec = _make_request(store)
        result = store.settle(rec["request_id"])
        assert result["state"] == "needs_reconciliation"

    def test_uncertain_broadcast_no_reserve_release(self, db_path):
        reserve = FakeReserve()
        verifier = FakeVerifier(confirmed=False)
        store = _full_store(db_path,
                            reserve_provider=reserve,
                            broadcaster=FakeBroadcaster(uncertain=True),
                            node_verifier=verifier)
        rec = _make_request(store)
        store.settle(rec["request_id"])
        assert rec["request_id"] not in reserve.release_calls

    def test_uncertain_broadcast_reconciled_by_node(self, db_path):
        verifier = FakeVerifier(confirmed=True)
        store = _full_store(db_path,
                            broadcaster=FakeBroadcaster(uncertain=True, txid=VALID_TXID),
                            node_verifier=verifier)
        rec = _make_request(store)
        result = store.settle(rec["request_id"])
        assert result["state"] == "paid"
        assert result["verified_amount_sat"] is not None

    def test_broadcast_exception_enters_reconciliation(self, db_path):
        bc = FakeBroadcaster()
        bc.sign_and_broadcast = MagicMock(side_effect=RuntimeError("signing_hsm_timeout"))
        verifier = FakeVerifier(confirmed=False)
        store = _full_store(db_path, broadcaster=bc, node_verifier=verifier)
        rec = _make_request(store)
        result = store.settle(rec["request_id"])
        assert result["state"] == "needs_reconciliation"
        assert "broadcast_exception" in result["failure_reason"]

    def test_broadcast_exception_no_reserve_release(self, db_path):
        reserve = FakeReserve()
        bc = FakeBroadcaster()
        bc.sign_and_broadcast = MagicMock(side_effect=RuntimeError("timeout"))
        verifier = FakeVerifier(confirmed=False)
        store = _full_store(db_path, reserve_provider=reserve, broadcaster=bc, node_verifier=verifier)
        rec = _make_request(store)
        store.settle(rec["request_id"])
        assert rec["request_id"] not in reserve.release_calls

    def test_node_verification_failure_enters_reconciliation(self, db_path):
        verifier = FakeVerifier(confirmed=False)
        store = _full_store(db_path, node_verifier=verifier)
        rec = _make_request(store)
        result = store.settle(rec["request_id"])
        assert result["state"] == "needs_reconciliation"

    def test_node_verification_exception_enters_reconciliation(self, db_path):
        verifier = FakeVerifier()
        verifier.verify_tx = MagicMock(side_effect=ConnectionError("node down"))
        verifier.lookup_by_fingerprint = MagicMock(side_effect=ConnectionError("node down"))
        store = _full_store(db_path, node_verifier=verifier)
        rec = _make_request(store)
        result = store.settle(rec["request_id"])
        assert result["state"] == "needs_reconciliation"


# ══════════════════════════════════════════════════════════════════════════
# 15. Double request (concurrent settlement)
# ══════════════════════════════════════════════════════════════════════════

class TestDoubleRequest:
    def test_idempotent_same_day_same_params(self, store):
        r1 = _make_request(store)
        r2 = _make_request(store)
        assert r1["request_id"] == r2["request_id"]
        result = store.settle(r1["request_id"])
        assert result["state"] == "paid"

    def test_settle_already_settled_is_safe(self, store):
        rec = _make_request(store)
        store.settle(rec["request_id"])
        result = store.settle(rec["request_id"])
        assert result["state"] == "paid"

    def test_settle_already_failed_is_safe(self, store):
        rec = _make_request(store)
        store.transition(rec["request_id"], "failed", failure_reason="manual_fail")
        result = store.settle(rec["request_id"])
        assert result["state"] == "failed"

    def test_two_different_requests_settle_independently(self, store):
        r1 = _make_request(store, thc="25000.000000")
        r2 = _make_request(store, thc="50000.000000")
        res1 = store.settle(r1["request_id"])
        res2 = store.settle(r2["request_id"])
        assert res1["state"] == "paid"
        assert res2["state"] == "paid"


# ══════════════════════════════════════════════════════════════════════════
# 16. Crash recovery
# ══════════════════════════════════════════════════════════════════════════

class TestCrashRecovery:
    def test_recover_reserve_locked_releases_and_fails(self, db_path):
        reserve = FakeReserve()
        store = _full_store(db_path, reserve_provider=reserve)
        rec = _make_request(store)
        store.transition(rec["request_id"], "reserve_locked")
        recovered = store.recover_inflight()
        assert len(recovered) == 1
        assert recovered[0]["state"] == "failed"
        assert rec["request_id"] in reserve.release_calls

    def test_recover_signing_goes_to_reconciliation(self, db_path):
        verifier = FakeVerifier(confirmed=False)
        store = _full_store(db_path, node_verifier=verifier)
        rec = _make_request(store)
        store.transition(rec["request_id"], "reserve_locked")
        store.transition(rec["request_id"], "signing")
        recovered = store.recover_inflight()
        assert len(recovered) == 1
        assert recovered[0]["state"] == "needs_reconciliation"

    def test_recover_signing_found_on_node_confirms(self, db_path):
        verifier = FakeVerifier(confirmed=True, amount_sat=5000)
        store = _full_store(db_path, node_verifier=verifier)
        rec = _make_request(store)
        store.transition(rec["request_id"], "reserve_locked")
        store.transition(rec["request_id"], "signing")
        recovered = store.recover_inflight()
        assert len(recovered) == 1
        assert recovered[0]["state"] == "confirmed"

    def test_recover_broadcasted_with_txid_verifies(self, db_path):
        verifier = FakeVerifier(confirmed=True)
        store = _full_store(db_path, node_verifier=verifier)
        rec = _make_request(store)
        store.transition(rec["request_id"], "reserve_locked")
        store.transition(rec["request_id"], "signing")
        store.transition(rec["request_id"], "broadcasted", btc_txid=VALID_TXID)
        recovered = store.recover_inflight()
        assert len(recovered) == 1
        assert recovered[0]["state"] == "confirmed"

    def test_recover_broadcasted_node_down_stays_reconciliation(self, db_path):
        verifier = FakeVerifier(confirmed=False)
        store = _full_store(db_path, node_verifier=verifier)
        rec = _make_request(store)
        store.transition(rec["request_id"], "reserve_locked")
        store.transition(rec["request_id"], "signing")
        store.transition(rec["request_id"], "broadcasted", btc_txid=VALID_TXID)
        recovered = store.recover_inflight()
        assert len(recovered) == 1
        assert recovered[0]["state"] == "needs_reconciliation"

    def test_recover_confirmed_promotes_to_paid(self, store):
        rec = _make_request(store)
        sat = rec["btc_amount_sat"]
        store.transition(rec["request_id"], "reserve_locked")
        store.transition(rec["request_id"], "signing")
        store.transition(rec["request_id"], "broadcasted", btc_txid=VALID_TXID)
        store.transition(rec["request_id"], "confirmed", btc_txid=VALID_TXID, verified_amount_sat=sat)
        recovered = store.recover_inflight()
        assert len(recovered) == 1
        assert recovered[0]["state"] == "paid"

    def test_recover_no_inflight_returns_empty(self, store):
        rec = _make_request(store)
        store.settle(rec["request_id"])
        recovered = store.recover_inflight()
        assert recovered == []

    def test_recover_multiple_inflight(self, db_path):
        verifier = FakeVerifier(confirmed=True)
        store = _full_store(db_path, node_verifier=verifier)
        r1 = _make_request(store, thc="25000.000000")
        r2 = _make_request(store, thc="50000.000000")
        store.transition(r1["request_id"], "reserve_locked")
        store.transition(r2["request_id"], "reserve_locked")
        store.transition(r2["request_id"], "signing")
        store.transition(r2["request_id"], "broadcasted", btc_txid=VALID_TXID)
        recovered = store.recover_inflight()
        assert len(recovered) == 2
        states = {r["request_id"]: r["state"] for r in recovered}
        assert states[r1["request_id"]] == "failed"
        assert states[r2["request_id"]] == "confirmed"


# ══════════════════════════════════════════════════════════════════════════
# 17. Concurrent settlement (threading)
# ══════════════════════════════════════════════════════════════════════════

class TestConcurrentSettlement:
    def test_concurrent_settle_same_request(self, db_path):
        store = _full_store(db_path)
        rec = _make_request(store)
        rid = rec["request_id"]
        results: list[dict] = []
        transition_races: list[Exception] = []
        real_errors: list[Exception] = []

        def settle_thread():
            try:
                results.append(store.settle(rid))
            except CashoutError as e:
                if "invalid_cashout_transition" in str(e):
                    transition_races.append(e)
                else:
                    real_errors.append(e)
            except Exception as e:
                real_errors.append(e)

        threads = [threading.Thread(target=settle_thread) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not real_errors, f"Unexpected errors: {real_errors}"
        final = store.get_request(rid)
        assert final["state"] == "paid"

    def test_concurrent_create_idempotent(self, db_path):
        store = _full_store(db_path)
        ids: list[str] = []
        errors: list[Exception] = []

        def create_thread():
            try:
                rec = _make_request(store)
                ids.append(rec["request_id"])
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=create_thread) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Unexpected errors: {errors}"
        assert len(set(ids)) == 1


# ══════════════════════════════════════════════════════════════════════════
# 18. No-debit-before-confirmed-txid invariant
# ══════════════════════════════════════════════════════════════════════════

class TestNoDebitBeforeConfirmedTxid:
    def test_paid_state_has_verified_amount(self, store):
        rec = _make_request(store)
        result = store.settle(rec["request_id"])
        assert result["state"] == "paid"
        assert result["verified_amount_sat"] is not None
        assert int(result["verified_amount_sat"]) > 0

    def test_paid_not_from_hex_string_alone(self, db_path):
        verifier = FakeVerifier(confirmed=False)
        store = _full_store(db_path, node_verifier=verifier)
        rec = _make_request(store)
        result = store.settle(rec["request_id"])
        assert result["state"] != "paid"


# ══════════════════════════════════════════════════════════════════════════
# 19. Source safety — no secrets, no floats, no simulated success
# ══════════════════════════════════════════════════════════════════════════

class TestSourceSafety:
    def test_no_float_usage_in_source(self):
        source = Path("services/earn_btc_cashout.py").read_text()
        lines = source.split("\n")
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'"):
                continue
            assert "float(" not in line, f"float() found at line {i}: {line.strip()}"

    def test_no_secrets_in_source(self):
        source = Path("services/earn_btc_cashout.py").read_text()
        import re as _re
        code = _re.sub(r'""".*?"""', '', source, flags=_re.DOTALL)
        for keyword in ("api_key", "secret_key", "private_key", "stripe"):
            assert keyword not in code.lower(), f"Potential secret keyword '{keyword}' in source"

    def test_no_hardcoded_txid_in_source(self):
        source = Path("services/earn_btc_cashout.py").read_text()
        import re
        hex_64 = re.findall(r'["\'][0-9a-fA-F]{64}["\']', source)
        assert len(hex_64) == 0, f"Hardcoded 64-char hex found: {hex_64}"

    def test_no_one_to_one_thc_usd(self):
        source = Path("services/earn_btc_cashout.py").read_text()
        assert 'net_thc * Decimal("1")' not in source, "1 THC = $1 assumption found"


# ══════════════════════════════════════════════════════════════════════════
# 20. Quote provider edge cases
# ══════════════════════════════════════════════════════════════════════════

class TestQuoteProvider:
    def test_zero_quote_rejected(self, db_path):
        store = _full_store(db_path, quote_provider=FakeQuote(Decimal("0")))
        with pytest.raises(CashoutError, match="btc_quote_invalid"):
            _make_request(store)

    def test_negative_quote_rejected(self, db_path):
        store = _full_store(db_path, quote_provider=FakeQuote(Decimal("-100")))
        with pytest.raises(CashoutError, match="btc_quote_invalid"):
            _make_request(store)

    def test_quote_exception_caught(self, db_path):
        q = FakeQuote()
        q.btc_usd_quote = MagicMock(side_effect=ConnectionError("api down"))
        store = EarnBtcCashoutStore(
            db_path, quote_provider=q, fee_schedule=FakeFee(), thc_rate_provider=FakeThcRate())
        with pytest.raises(CashoutError, match="btc_quote_unavailable"):
            _make_request(store)
