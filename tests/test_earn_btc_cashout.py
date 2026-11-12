"""Tests for Earn BTC Cash-Out Settlement Pipeline.

Covers: request creation, state machine, fee bounds, BTC address validation,
idempotency, Decimal precision, settlement orchestration (reserve → sign →
broadcast → txid → paid), insufficient reserve, broadcast failure, double
request in settlement, and crash recovery.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
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
    def __init__(self, *, succeed: bool = True, txid: str = VALID_TXID):
        self._succeed = succeed
        self._txid = txid
        self.calls: list[dict] = []

    def sign_and_broadcast(self, *, to_address: str, amount_sat: int, request_id: str) -> BroadcastResult:
        self.calls.append({"to_address": to_address, "amount_sat": amount_sat, "request_id": request_id})
        if self._succeed:
            return BroadcastResult(success=True, txid=self._txid, raw_hex="deadbeef" * 8)
        return BroadcastResult(success=False, error="node_unreachable")


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "cashout_test.db")


@pytest.fixture
def store(db_path):
    return EarnBtcCashoutStore(
        db_path,
        quote_provider=FakeQuote(),
        fee_schedule=FakeFee(),
        reserve_provider=FakeReserve(),
        broadcaster=FakeBroadcaster(),
    )


@pytest.fixture
def store_no_infra(db_path):
    return EarnBtcCashoutStore(
        db_path,
        quote_provider=FakeQuote(),
        fee_schedule=FakeFee(),
    )


def _make_request(store, *, thc="100.000000", available="500.000000", addr=VALID_BTC_ADDR, user=USER_ID):
    return store.create_cashout_request(
        earn_user_id=user,
        btc_address=addr,
        thc_amount=thc,
        available_thc=available,
    )


# ══════════════════════════════════════════════════════════════════════════
# 1. Request creation
# ══════════════════════════════════════════════════════════════════════════

class TestCreateRequest:
    def test_basic_creation(self, store):
        rec = _make_request(store)
        assert rec["state"] == "cashout_requested"
        assert rec["earn_user_id"] == USER_ID
        assert rec["btc_address"] == VALID_BTC_ADDR
        assert Decimal(rec["thc_amount"]) == Decimal("100.000000")
        assert rec["request_id"].startswith("co_")

    def test_fee_deducted(self, store):
        rec = _make_request(store, thc="100.000000")
        fee = Decimal(rec["fee_thc"])
        net = Decimal(rec["net_thc"])
        assert fee == Decimal("12.000000")
        assert net == Decimal("88.000000")

    def test_btc_amount_sat_calculated(self, store):
        rec = _make_request(store, thc="100.000000")
        sat = int(rec["btc_amount_sat"])
        assert sat > 0

    def test_usd_equivalent_below_minimum_rejected(self, store):
        with pytest.raises(CashoutError, match="below_minimum_usd"):
            _make_request(store, thc="20.000000", available="500.000000")

    def test_insufficient_balance(self, store):
        with pytest.raises(CashoutError, match="insufficient_thc_balance"):
            _make_request(store, thc="600.000000", available="500.000000")

    def test_zero_amount(self, store):
        with pytest.raises(CashoutError, match="invalid_thc_amount"):
            _make_request(store, thc="0")

    def test_negative_amount(self, store):
        with pytest.raises(CashoutError, match="invalid_thc_amount"):
            _make_request(store, thc="-50")


# ══════════════════════════════════════════════════════════════════════════
# 2. Idempotency
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
        r1 = _make_request(store, thc="100.000000")
        r2 = _make_request(store, thc="200.000000")
        assert r1["request_id"] != r2["request_id"]


# ══════════════════════════════════════════════════════════════════════════
# 3. BTC address validation
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
# 4. Fee bounds (8–18%)
# ══════════════════════════════════════════════════════════════════════════

class TestFeeBounds:
    def test_env_fee_in_bounds(self):
        with patch.dict(os.environ, {"EARN_CASHOUT_FEE_PERCENT": "12"}):
            fs = EnvFeeSchedule()
            assert fs.cashout_fee_percent() == Decimal("12.0000")

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
# 5. State machine transitions
# ══════════════════════════════════════════════════════════════════════════

class TestStateMachine:
    def test_valid_forward_transitions(self, store):
        rec = _make_request(store)
        rid = rec["request_id"]
        rec = store.transition(rid, "reserve_locked")
        assert rec["state"] == "reserve_locked"
        rec = store.transition(rid, "signing")
        assert rec["state"] == "signing"
        rec = store.transition(rid, "broadcasted", btc_txid=VALID_TXID)
        assert rec["state"] == "broadcasted"
        rec = store.transition(rid, "paid", btc_txid=VALID_TXID)
        assert rec["state"] == "paid"

    def test_cannot_skip_states(self, store):
        rec = _make_request(store)
        with pytest.raises(CashoutError, match="invalid_cashout_transition"):
            store.transition(rec["request_id"], "paid", btc_txid=VALID_TXID)

    def test_paid_requires_valid_txid(self, store):
        rec = _make_request(store)
        rid = rec["request_id"]
        store.transition(rid, "reserve_locked")
        store.transition(rid, "signing")
        store.transition(rid, "broadcasted", btc_txid=VALID_TXID)
        with pytest.raises(CashoutError, match="valid_btc_txid_required"):
            store.transition(rid, "paid", btc_txid="short")

    def test_paid_rejects_no_txid(self, store):
        rec = _make_request(store)
        rid = rec["request_id"]
        store.transition(rid, "reserve_locked")
        store.transition(rid, "signing")
        store.transition(rid, "broadcasted", btc_txid=VALID_TXID)
        with pytest.raises(CashoutError, match="valid_btc_txid_required"):
            store.transition(rid, "paid")

    def test_failed_requires_reason(self, store):
        rec = _make_request(store)
        with pytest.raises(CashoutError, match="failure_reason_required"):
            store.transition(rec["request_id"], "failed")

    def test_failed_with_reason(self, store):
        rec = _make_request(store)
        result = store.transition(rec["request_id"], "failed", failure_reason="test_error")
        assert result["state"] == "failed"
        assert result["failure_reason"] == "test_error"

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

    def test_idempotent_same_state_transition(self, store):
        rec = _make_request(store)
        rid = rec["request_id"]
        store.transition(rid, "reserve_locked")
        result = store.transition(rid, "reserve_locked")
        assert result["state"] == "reserve_locked"


# ══════════════════════════════════════════════════════════════════════════
# 6. Decimal precision — no float contamination
# ══════════════════════════════════════════════════════════════════════════

class TestDecimalPrecision:
    def test_thc_amount_precision(self, store):
        rec = _make_request(store, thc="100.123456")
        assert "." in rec["thc_amount"]
        amt = Decimal(rec["thc_amount"])
        assert amt == Decimal("100.123456")

    def test_fee_precision(self, store):
        rec = _make_request(store, thc="100.000000")
        fee = Decimal(rec["fee_thc"])
        net = Decimal(rec["net_thc"])
        assert fee + net == Decimal(rec["thc_amount"])

    def test_no_float_in_record(self, store):
        rec = _make_request(store)
        for key in ("thc_amount", "fee_percent", "fee_thc", "net_thc",
                     "btc_usd_quote", "btc_amount_sat", "usd_equivalent"):
            val = rec[key]
            assert isinstance(val, str), f"{key} should be stored as string, got {type(val)}"
            Decimal(val)


# ══════════════════════════════════════════════════════════════════════════
# 7. Txid validation
# ══════════════════════════════════════════════════════════════════════════

class TestTxidValidation:
    @pytest.mark.parametrize("txid,expected", [
        ("a" * 64, True),
        ("0123456789abcdef" * 4, True),
        ("A" * 64, True),
        ("", False),
        ("short", False),
        ("g" * 64, False),
        ("a" * 63, False),
        ("a" * 65, False),
        (None, False),
    ])
    def test_txid_validation(self, txid, expected):
        assert _validate_txid(txid or "") == expected


# ══════════════════════════════════════════════════════════════════════════
# 8. Queries
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
        _make_request(store, thc="100.000000")
        _make_request(store, thc="200.000000")
        results = store.list_requests(USER_ID)
        assert len(results) == 2

    def test_list_pending(self, store):
        r1 = _make_request(store, thc="100.000000")
        r2 = _make_request(store, thc="200.000000")
        store.transition(r2["request_id"], "failed", failure_reason="test")
        pending = store.list_pending()
        assert len(pending) == 1
        assert pending[0]["request_id"] == r1["request_id"]


# ══════════════════════════════════════════════════════════════════════════
# 9. Payout capability
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

    def test_empty_reserve(self, db_path):
        store = EarnBtcCashoutStore(
            db_path,
            quote_provider=FakeQuote(),
            fee_schedule=FakeFee(),
            reserve_provider=FakeReserve(balance_sat=0),
            broadcaster=FakeBroadcaster(),
        )
        cap = store.payout_capability()
        assert cap["cashout_enabled"] is False
        assert any("empty" in i for i in cap["issues"])

    def test_fee_bounds_in_capability(self, store):
        cap = store.payout_capability()
        assert cap["fee_bounds"]["floor"] == str(_FEE_FLOOR_PERCENT)
        assert cap["fee_bounds"]["ceiling"] == str(_FEE_CEILING_PERCENT)


# ══════════════════════════════════════════════════════════════════════════
# 10. Settlement orchestrator — happy path
# ══════════════════════════════════════════════════════════════════════════

class TestSettleHappyPath:
    def test_full_settlement(self, store):
        rec = _make_request(store)
        result = store.settle(rec["request_id"])
        assert result["state"] == "paid"
        assert result["btc_txid"] == VALID_TXID
        assert result["paid_at"] is not None

    def test_settle_records_timestamps(self, store):
        rec = _make_request(store)
        result = store.settle(rec["request_id"])
        assert result["reserve_locked_at"] is not None
        assert result["broadcast_at"] is not None
        assert result["paid_at"] is not None
        assert result["reserve_locked_at"] <= result["broadcast_at"] <= result["paid_at"]

    def test_settle_broadcaster_called_correctly(self, db_path):
        bc = FakeBroadcaster()
        store = EarnBtcCashoutStore(
            db_path,
            quote_provider=FakeQuote(),
            fee_schedule=FakeFee(),
            reserve_provider=FakeReserve(),
            broadcaster=bc,
        )
        rec = _make_request(store)
        store.settle(rec["request_id"])
        assert len(bc.calls) == 1
        call = bc.calls[0]
        assert call["to_address"] == VALID_BTC_ADDR
        assert call["amount_sat"] == int(rec["btc_amount_sat"])
        assert call["request_id"] == rec["request_id"]

    def test_settle_already_paid_is_noop(self, store):
        rec = _make_request(store)
        result1 = store.settle(rec["request_id"])
        assert result1["state"] == "paid"
        result2 = store.settle(rec["request_id"])
        assert result2["state"] == "paid"
        assert result2["request_id"] == result1["request_id"]


# ══════════════════════════════════════════════════════════════════════════
# 11. Settlement — insufficient BTC reserve
# ══════════════════════════════════════════════════════════════════════════

class TestInsufficientReserve:
    def test_reserve_balance_too_low(self, db_path):
        store = EarnBtcCashoutStore(
            db_path,
            quote_provider=FakeQuote(),
            fee_schedule=FakeFee(),
            reserve_provider=FakeReserve(balance_sat=1),
            broadcaster=FakeBroadcaster(),
        )
        rec = _make_request(store)
        result = store.settle(rec["request_id"])
        assert result["state"] == "failed"
        assert "insufficient_btc_reserve" in result["failure_reason"]

    def test_reserve_query_raises(self, db_path):
        reserve = FakeReserve()
        reserve.confirmed_balance_sat = MagicMock(side_effect=ConnectionError("rpc down"))
        store = EarnBtcCashoutStore(
            db_path,
            quote_provider=FakeQuote(),
            fee_schedule=FakeFee(),
            reserve_provider=reserve,
            broadcaster=FakeBroadcaster(),
        )
        rec = _make_request(store)
        result = store.settle(rec["request_id"])
        assert result["state"] == "failed"
        assert "reserve_query_failed" in result["failure_reason"]

    def test_reserve_lock_fails(self, db_path):
        reserve = FakeReserve(balance_sat=10_000_000_000)
        reserve.lock = MagicMock(return_value=False)
        store = EarnBtcCashoutStore(
            db_path,
            quote_provider=FakeQuote(),
            fee_schedule=FakeFee(),
            reserve_provider=reserve,
            broadcaster=FakeBroadcaster(),
        )
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
# 12. Settlement — broadcast failure
# ══════════════════════════════════════════════════════════════════════════

class TestBroadcastFailure:
    def test_broadcast_returns_failure(self, db_path):
        store = EarnBtcCashoutStore(
            db_path,
            quote_provider=FakeQuote(),
            fee_schedule=FakeFee(),
            reserve_provider=FakeReserve(),
            broadcaster=FakeBroadcaster(succeed=False),
        )
        rec = _make_request(store)
        result = store.settle(rec["request_id"])
        assert result["state"] == "failed"
        assert "broadcast_failed" in result["failure_reason"]

    def test_broadcast_releases_reserve_on_failure(self, db_path):
        reserve = FakeReserve()
        store = EarnBtcCashoutStore(
            db_path,
            quote_provider=FakeQuote(),
            fee_schedule=FakeFee(),
            reserve_provider=reserve,
            broadcaster=FakeBroadcaster(succeed=False),
        )
        rec = _make_request(store)
        store.settle(rec["request_id"])
        assert rec["request_id"] in [c for c in reserve.release_calls]

    def test_broadcast_exception_releases_reserve(self, db_path):
        reserve = FakeReserve()
        bc = FakeBroadcaster()
        bc.sign_and_broadcast = MagicMock(side_effect=RuntimeError("signing_hsm_timeout"))
        store = EarnBtcCashoutStore(
            db_path,
            quote_provider=FakeQuote(),
            fee_schedule=FakeFee(),
            reserve_provider=reserve,
            broadcaster=bc,
        )
        rec = _make_request(store)
        result = store.settle(rec["request_id"])
        assert result["state"] == "failed"
        assert "broadcast_exception" in result["failure_reason"]
        assert rec["request_id"] in reserve.release_calls

    def test_broadcast_returns_invalid_txid(self, db_path):
        store = EarnBtcCashoutStore(
            db_path,
            quote_provider=FakeQuote(),
            fee_schedule=FakeFee(),
            reserve_provider=FakeReserve(),
            broadcaster=FakeBroadcaster(succeed=True, txid="not-a-txid"),
        )
        rec = _make_request(store)
        result = store.settle(rec["request_id"])
        assert result["state"] == "failed"
        assert "invalid_txid" in result["failure_reason"]

    def test_no_broadcaster_configured(self, db_path):
        store = EarnBtcCashoutStore(
            db_path,
            quote_provider=FakeQuote(),
            fee_schedule=FakeFee(),
            reserve_provider=FakeReserve(),
        )
        rec = _make_request(store)
        result = store.settle(rec["request_id"])
        assert result["state"] == "failed"
        assert "broadcaster_not_configured" in result["failure_reason"]


# ══════════════════════════════════════════════════════════════════════════
# 13. Settlement — double request (concurrent settlement)
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

    def test_settle_cancelled_is_safe(self, store):
        rec = _make_request(store)
        store.transition(rec["request_id"], "cancelled")
        result = store.settle(rec["request_id"])
        assert result["state"] == "cancelled"

    def test_two_different_requests_settle_independently(self, store):
        r1 = _make_request(store, thc="100.000000")
        r2 = _make_request(store, thc="200.000000")
        res1 = store.settle(r1["request_id"])
        res2 = store.settle(r2["request_id"])
        assert res1["state"] == "paid"
        assert res2["state"] == "paid"
        assert res1["btc_txid"] == VALID_TXID
        assert res2["btc_txid"] == VALID_TXID


# ══════════════════════════════════════════════════════════════════════════
# 14. Crash recovery
# ══════════════════════════════════════════════════════════════════════════

class TestCrashRecovery:
    def test_recover_reserve_locked_fails_safely(self, store):
        rec = _make_request(store)
        store.transition(rec["request_id"], "reserve_locked")
        recovered = store.recover_inflight()
        assert len(recovered) == 1
        assert recovered[0]["state"] == "failed"
        assert "crash_recovery:stuck_in_reserve_locked" in recovered[0]["failure_reason"]

    def test_recover_signing_fails_safely(self, store):
        rec = _make_request(store)
        store.transition(rec["request_id"], "reserve_locked")
        store.transition(rec["request_id"], "signing")
        recovered = store.recover_inflight()
        assert len(recovered) == 1
        assert recovered[0]["state"] == "failed"
        assert "stuck_in_signing" in recovered[0]["failure_reason"]

    def test_recover_broadcasted_with_txid_promotes_to_paid(self, store):
        rec = _make_request(store)
        store.transition(rec["request_id"], "reserve_locked")
        store.transition(rec["request_id"], "signing")
        store.transition(rec["request_id"], "broadcasted", btc_txid=VALID_TXID)
        recovered = store.recover_inflight()
        assert len(recovered) == 1
        assert recovered[0]["state"] == "paid"
        assert recovered[0]["btc_txid"] == VALID_TXID

    def test_recover_broadcasted_without_txid_fails(self, db_path):
        store = EarnBtcCashoutStore(
            db_path,
            quote_provider=FakeQuote(),
            fee_schedule=FakeFee(),
            reserve_provider=FakeReserve(),
            broadcaster=FakeBroadcaster(),
        )
        rec = _make_request(store)
        store.transition(rec["request_id"], "reserve_locked")
        store.transition(rec["request_id"], "signing")
        # Manually insert broadcasted state without txid via raw SQL
        con = sqlite3.connect(db_path)
        con.execute(
            "UPDATE cashout_requests SET state='broadcasted', btc_txid=NULL WHERE request_id=?",
            (rec["request_id"],),
        )
        con.commit()
        con.close()
        recovered = store.recover_inflight()
        assert len(recovered) == 1
        assert recovered[0]["state"] == "failed"
        assert "without_valid_txid" in recovered[0]["failure_reason"]

    def test_recover_releases_reserve_for_stuck(self, db_path):
        reserve = FakeReserve()
        store = EarnBtcCashoutStore(
            db_path,
            quote_provider=FakeQuote(),
            fee_schedule=FakeFee(),
            reserve_provider=reserve,
            broadcaster=FakeBroadcaster(),
        )
        rec = _make_request(store)
        store.transition(rec["request_id"], "reserve_locked")
        recovered = store.recover_inflight()
        assert rec["request_id"] in reserve.release_calls
        assert recovered[0]["state"] == "failed"

    def test_recover_no_inflight_returns_empty(self, store):
        rec = _make_request(store)
        store.settle(rec["request_id"])
        recovered = store.recover_inflight()
        assert recovered == []

    def test_recover_multiple_inflight(self, store):
        r1 = _make_request(store, thc="100.000000")
        r2 = _make_request(store, thc="200.000000")
        store.transition(r1["request_id"], "reserve_locked")
        store.transition(r2["request_id"], "reserve_locked")
        store.transition(r2["request_id"], "signing")
        store.transition(r2["request_id"], "broadcasted", btc_txid=VALID_TXID)
        recovered = store.recover_inflight()
        assert len(recovered) == 2
        states = {r["request_id"]: r["state"] for r in recovered}
        assert states[r1["request_id"]] == "failed"
        assert states[r2["request_id"]] == "paid"

    def test_recover_without_reserve_provider(self, store_no_infra):
        rec = _make_request(store_no_infra)
        store_no_infra.transition(rec["request_id"], "failed", failure_reason="test_setup")
        rec2 = _make_request(store_no_infra, thc="200.000000")
        # Force into reserve_locked via raw SQL for recovery test
        con = sqlite3.connect(store_no_infra.db_path)
        con.execute(
            "UPDATE cashout_requests SET state='reserve_locked' WHERE request_id=?",
            (rec2["request_id"],),
        )
        con.commit()
        con.close()
        recovered = store_no_infra.recover_inflight()
        assert len(recovered) == 1
        assert recovered[0]["state"] == "failed"


# ══════════════════════════════════════════════════════════════════════════
# 15. No-debit-before-txid invariant
# ══════════════════════════════════════════════════════════════════════════

class TestNoDebitBeforeTxid:
    def test_paid_state_always_has_txid(self, store):
        rec = _make_request(store)
        result = store.settle(rec["request_id"])
        assert result["state"] == "paid"
        assert _validate_txid(result["btc_txid"])

    def test_cannot_reach_paid_without_txid(self, store):
        rec = _make_request(store)
        store.transition(rec["request_id"], "reserve_locked")
        store.transition(rec["request_id"], "signing")
        store.transition(rec["request_id"], "broadcasted", btc_txid=VALID_TXID)
        with pytest.raises(CashoutError, match="valid_btc_txid_required"):
            store.transition(rec["request_id"], "paid", btc_txid=None)


# ══════════════════════════════════════════════════════════════════════════
# 16. Source safety — no secrets, no floats, no simulated success
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
        # Strip module docstring before checking
        import re as _re
        code = _re.sub(r'""".*?"""', '', source, flags=_re.DOTALL)
        for keyword in ("api_key", "secret_key", "private_key", "stripe"):
            assert keyword not in code.lower(), f"Potential secret keyword '{keyword}' in source"

    def test_no_hardcoded_txid_in_source(self):
        source = Path("services/earn_btc_cashout.py").read_text()
        import re
        hex_64 = re.findall(r'["\'][0-9a-fA-F]{64}["\']', source)
        assert len(hex_64) == 0, f"Hardcoded 64-char hex found: {hex_64}"


# ══════════════════════════════════════════════════════════════════════════
# 17. $25 minimum enforcement
# ══════════════════════════════════════════════════════════════════════════

class TestMinimumUsd:
    def test_exactly_25_usd_passes(self, db_path):
        fee_pct = Decimal("8.0000")
        net_needed = Decimal("25.00") / (1 - fee_pct / 100)
        thc = str(net_needed.quantize(Decimal("0.000001"), rounding=ROUND_DOWN) + Decimal("1"))
        store = EarnBtcCashoutStore(
            db_path,
            quote_provider=FakeQuote(Decimal("50000")),
            fee_schedule=FakeFee(fee_pct),
            reserve_provider=FakeReserve(),
            broadcaster=FakeBroadcaster(),
        )
        rec = store.create_cashout_request(
            earn_user_id=USER_ID,
            btc_address=VALID_BTC_ADDR,
            thc_amount=thc,
            available_thc="10000",
        )
        assert Decimal(rec["usd_equivalent"]) >= _MIN_CASHOUT_USD

    def test_below_25_usd_rejected(self, db_path):
        store = EarnBtcCashoutStore(
            db_path,
            quote_provider=FakeQuote(Decimal("50000")),
            fee_schedule=FakeFee(Decimal("18.0000")),
            reserve_provider=FakeReserve(),
            broadcaster=FakeBroadcaster(),
        )
        with pytest.raises(CashoutError, match="below_minimum_usd"):
            store.create_cashout_request(
                earn_user_id=USER_ID,
                btc_address=VALID_BTC_ADDR,
                thc_amount="25.000000",
                available_thc="10000",
            )


# ══════════════════════════════════════════════════════════════════════════
# 18. Quote provider edge cases
# ══════════════════════════════════════════════════════════════════════════

class TestQuoteProvider:
    def test_zero_quote_rejected(self, db_path):
        store = EarnBtcCashoutStore(
            db_path,
            quote_provider=FakeQuote(Decimal("0")),
            fee_schedule=FakeFee(),
        )
        with pytest.raises(CashoutError, match="btc_quote_invalid"):
            _make_request(store)

    def test_negative_quote_rejected(self, db_path):
        store = EarnBtcCashoutStore(
            db_path,
            quote_provider=FakeQuote(Decimal("-100")),
            fee_schedule=FakeFee(),
        )
        with pytest.raises(CashoutError, match="btc_quote_invalid"):
            _make_request(store)

    def test_quote_exception_caught(self, db_path):
        q = FakeQuote()
        q.btc_usd_quote = MagicMock(side_effect=ConnectionError("api down"))
        store = EarnBtcCashoutStore(db_path, quote_provider=q, fee_schedule=FakeFee())
        with pytest.raises(CashoutError, match="btc_quote_unavailable"):
            _make_request(store)
