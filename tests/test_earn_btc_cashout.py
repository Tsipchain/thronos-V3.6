"""
Tests for Earn BTC Cash-Out Settlement Ledger.

Covers:
  - Duplicate request idempotency
  - No debit before real txid
  - Reserve/signer/rate absence leaves request pending
  - Minimum $25 enforcement using injected authoritative quote
  - Exact Decimal/satoshi precision, no floats
  - 8–18% fee bounds
  - Full state machine transitions
  - BTC address validation
  - Capability endpoint honesty
"""
from __future__ import annotations

import hashlib
import os
import re
import time
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from services.earn_btc_cashout import (
    CashoutError,
    EarnBtcCashoutStore,
    EnvFeeSchedule,
    FeeSchedule,
    QuoteProvider,
    _CASHOUT_TRANSITIONS,
    _FEE_CEILING_PERCENT,
    _FEE_FLOOR_PERCENT,
    _MIN_CASHOUT_USD,
    _SAT_SCALE,
    _THC_SCALE,
    validate_btc_address,
)


# ── Test doubles ──────────────────────────────────────────────────────────

class FixedQuote:
    """Returns a fixed BTC/USD quote for deterministic testing."""
    def __init__(self, price: str = "100000.00"):
        self.price = Decimal(price)

    def btc_usd_quote(self) -> Decimal:
        return self.price


class FailingQuote:
    def btc_usd_quote(self) -> Decimal:
        raise RuntimeError("quote_service_down")


class FixedFee:
    def __init__(self, pct: str = "10.0000"):
        self.pct = Decimal(pct)

    def cashout_fee_percent(self) -> Decimal:
        return self.pct


class FailingFee:
    def cashout_fee_percent(self) -> Decimal:
        raise RuntimeError("fee_service_down")


# ── Helpers ───────────────────────────────────────────────────────────────

_VALID_BTC_ADDR = "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"
_VALID_LEGACY_ADDR = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
_VALID_P2SH_ADDR = "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy"
_VALID_TXID = "a" * 64  # 64 hex chars


def _make_store(tmp_path, *, quote=None, fee=None):
    return EarnBtcCashoutStore(
        str(tmp_path / "cashout.db"),
        quote_provider=quote or FixedQuote(),
        fee_schedule=fee or FixedFee(),
    )


def _create_request(store, *, thc="100", available="200", addr=_VALID_BTC_ADDR, user="earn_u1"):
    return store.create_cashout_request(
        earn_user_id=user,
        btc_address=addr,
        thc_amount=thc,
        available_thc=available,
    )


# ══════════════════════════════════════════════════════════════════════════
# 1. DUPLICATE REQUEST IDEMPOTENCY
# ══════════════════════════════════════════════════════════════════════════

class TestIdempotency:
    def test_same_request_returns_same_record(self, tmp_path):
        store = _make_store(tmp_path)
        r1 = _create_request(store)
        r2 = _create_request(store)
        assert r1["request_id"] == r2["request_id"]
        assert r1["state"] == "cashout_requested"

    def test_different_amount_creates_new_request(self, tmp_path):
        store = _make_store(tmp_path)
        r1 = _create_request(store, thc="100")
        r2 = _create_request(store, thc="50", available="200")
        assert r1["request_id"] != r2["request_id"]

    def test_different_address_creates_new_request(self, tmp_path):
        store = _make_store(tmp_path)
        r1 = _create_request(store, addr=_VALID_BTC_ADDR)
        r2 = _create_request(store, addr=_VALID_LEGACY_ADDR)
        assert r1["request_id"] != r2["request_id"]

    def test_different_user_creates_new_request(self, tmp_path):
        store = _make_store(tmp_path)
        r1 = _create_request(store, user="earn_alice")
        r2 = _create_request(store, user="earn_bob")
        assert r1["request_id"] != r2["request_id"]

    def test_idempotency_key_is_day_scoped(self, tmp_path):
        """Same user+address+amount on different days → different keys."""
        store = _make_store(tmp_path)
        r1 = _create_request(store)
        day_str = time.strftime("%Y-%m-%d", time.gmtime())
        idem_raw = f"earn_u1:{_VALID_BTC_ADDR}:{Decimal('100').quantize(_THC_SCALE)}:{day_str}"
        expected_key = hashlib.sha256(idem_raw.encode()).hexdigest()
        assert r1["idempotency_key"] == expected_key


# ══════════════════════════════════════════════════════════════════════════
# 2. NO DEBIT BEFORE REAL TXID
# ══════════════════════════════════════════════════════════════════════════

class TestNoDebitBeforeRealTxid:
    def test_paid_requires_valid_btc_txid(self, tmp_path):
        store = _make_store(tmp_path)
        req = _create_request(store)
        rid = req["request_id"]
        store.transition(rid, "reserve_verified")
        store.transition(rid, "signing")
        store.transition(rid, "broadcasted", btc_txid=_VALID_TXID)
        with pytest.raises(CashoutError, match="valid_btc_txid_required"):
            store.transition(rid, "paid")
        with pytest.raises(CashoutError, match="valid_btc_txid_required"):
            store.transition(rid, "paid", btc_txid="not_a_hex_hash")
        with pytest.raises(CashoutError, match="valid_btc_txid_required"):
            store.transition(rid, "paid", btc_txid="abc123")

    def test_paid_with_valid_txid_succeeds(self, tmp_path):
        store = _make_store(tmp_path)
        req = _create_request(store)
        rid = req["request_id"]
        store.transition(rid, "reserve_verified")
        store.transition(rid, "signing")
        store.transition(rid, "broadcasted", btc_txid=_VALID_TXID)
        result = store.transition(rid, "paid", btc_txid=_VALID_TXID)
        assert result["state"] == "paid"
        assert result["btc_txid"] == _VALID_TXID

    def test_new_request_has_no_txid(self, tmp_path):
        store = _make_store(tmp_path)
        req = _create_request(store)
        assert req["btc_txid"] is None
        assert req["state"] == "cashout_requested"

    def test_txid_must_be_64_hex_chars(self, tmp_path):
        store = _make_store(tmp_path)
        req = _create_request(store)
        rid = req["request_id"]
        store.transition(rid, "reserve_verified")
        store.transition(rid, "signing")
        store.transition(rid, "broadcasted", btc_txid=_VALID_TXID)
        # 63 chars
        with pytest.raises(CashoutError, match="valid_btc_txid_required"):
            store.transition(rid, "paid", btc_txid="a" * 63)
        # 65 chars
        with pytest.raises(CashoutError, match="valid_btc_txid_required"):
            store.transition(rid, "paid", btc_txid="a" * 65)
        # Non-hex
        with pytest.raises(CashoutError, match="valid_btc_txid_required"):
            store.transition(rid, "paid", btc_txid="g" * 64)


# ══════════════════════════════════════════════════════════════════════════
# 3. RESERVE/SIGNER/RATE ABSENCE LEAVES REQUEST PENDING
# ══════════════════════════════════════════════════════════════════════════

class TestReserveSignerRateAbsence:
    def test_quote_unavailable_prevents_creation(self, tmp_path):
        store = _make_store(tmp_path, quote=FailingQuote())
        with pytest.raises(CashoutError, match="btc_quote_unavailable"):
            _create_request(store)

    def test_zero_quote_prevents_creation(self, tmp_path):
        store = _make_store(tmp_path, quote=FixedQuote("0"))
        with pytest.raises(CashoutError, match="btc_quote_invalid"):
            _create_request(store)

    def test_fee_unavailable_prevents_creation(self, tmp_path):
        store = _make_store(tmp_path, fee=FailingFee())
        with pytest.raises(CashoutError, match="cashout_fee_unavailable"):
            _create_request(store)

    def test_request_stays_pending_without_progression(self, tmp_path):
        store = _make_store(tmp_path)
        req = _create_request(store)
        assert req["state"] == "cashout_requested"
        # Without external systems progressing it, it stays here
        fetched = store.get_request(req["request_id"])
        assert fetched["state"] == "cashout_requested"

    def test_capability_reports_reserve_and_signer_missing(self, tmp_path):
        store = _make_store(tmp_path)
        cap = store.payout_capability()
        assert cap["cashout_enabled"] is False
        assert "btc_reserve_not_verified" in cap["issues"]
        assert "btc_signer_not_available" in cap["issues"]

    def test_capability_reports_fee_failure(self, tmp_path):
        store = _make_store(tmp_path, fee=FailingFee())
        cap = store.payout_capability()
        assert cap["cashout_enabled"] is False
        assert any("fee" in i.lower() for i in cap["issues"])

    def test_capability_reports_quote_failure(self, tmp_path):
        store = _make_store(tmp_path, quote=FailingQuote())
        cap = store.payout_capability()
        assert cap["cashout_enabled"] is False
        assert any("quote" in i.lower() for i in cap["issues"])


# ══════════════════════════════════════════════════════════════════════════
# 4. MINIMUM $25 ENFORCEMENT
# ══════════════════════════════════════════════════════════════════════════

class TestMinimumUSD:
    def test_below_25_usd_rejected(self, tmp_path):
        """With 10% fee, 26 THC → net 23.40 USD < $25."""
        store = _make_store(tmp_path, fee=FixedFee("10.0000"))
        with pytest.raises(CashoutError, match="below_minimum_usd"):
            _create_request(store, thc="26", available="200")

    def test_exactly_25_net_usd_accepted(self, tmp_path):
        """With 10% fee, 28 THC → net 25.20 → $25.20 ≥ $25."""
        store = _make_store(tmp_path, fee=FixedFee("10.0000"))
        req = _create_request(store, thc="28", available="200")
        assert req["state"] == "cashout_requested"
        assert Decimal(req["usd_equivalent"]) >= _MIN_CASHOUT_USD

    def test_high_fee_rate_reduces_net_below_minimum(self, tmp_path):
        """With 18% fee, 30 THC → net 24.60 → $24.60 < $25."""
        store = _make_store(tmp_path, fee=FixedFee("18.0000"))
        with pytest.raises(CashoutError, match="below_minimum_usd"):
            _create_request(store, thc="30", available="200")

    def test_capability_reports_min_usd(self, tmp_path):
        store = _make_store(tmp_path)
        cap = store.payout_capability()
        assert cap["min_usd"] == "25.00"


# ══════════════════════════════════════════════════════════════════════════
# 5. EXACT DECIMAL/SATOSHI PRECISION — NO FLOATS
# ══════════════════════════════════════════════════════════════════════════

class TestDecimalPrecision:
    def test_no_float_in_source(self):
        """The cashout service must not use float() anywhere in executable code."""
        source = (Path(__file__).parent.parent / "services" / "earn_btc_cashout.py").read_text()
        lines = source.split("\n")
        in_docstring = False
        for i, line in enumerate(lines, 1):
            stripped = line.lstrip()
            if '"""' in stripped:
                count = stripped.count('"""')
                if count == 1:
                    in_docstring = not in_docstring
                continue
            if in_docstring:
                continue
            if stripped.startswith("#"):
                continue
            code = line.split("#")[0]
            if "float(" in code:
                pytest.fail(f"float() found at line {i}: {line.strip()}")

    def test_thc_amount_stored_as_decimal_string(self, tmp_path):
        store = _make_store(tmp_path)
        req = _create_request(store, thc="123.456789")
        assert req["thc_amount"] == "123.456789"
        assert "." in req["thc_amount"]

    def test_btc_amount_has_satoshi_precision(self, tmp_path):
        # BTC at $100,000, net THC ~90 (10% fee from 100), USD ~$90
        # BTC = $90 / $100,000 = 0.00090000
        store = _make_store(tmp_path, quote=FixedQuote("100000"))
        req = _create_request(store, thc="100", available="200")
        btc_sat = Decimal(req["btc_amount_sat"])
        assert btc_sat == btc_sat.quantize(_SAT_SCALE)

    def test_fee_calculation_exact(self, tmp_path):
        """10% of 100 THC = 10 THC fee, 90 THC net."""
        store = _make_store(tmp_path, fee=FixedFee("10.0000"))
        req = _create_request(store, thc="100", available="200")
        assert Decimal(req["fee_thc"]) == Decimal("10.000000")
        assert Decimal(req["net_thc"]) == Decimal("90.000000")
        assert Decimal(req["fee_percent"]) == Decimal("10.0000")

    def test_repeated_small_amounts_precision(self, tmp_path):
        """Create multiple small cashouts; amounts must stay exact."""
        store = _make_store(tmp_path, fee=FixedFee("10.0000"))
        amounts = []
        for i in range(10):
            req = store.create_cashout_request(
                earn_user_id=f"user_{i}",
                btc_address=_VALID_BTC_ADDR,
                thc_amount="28",
                available_thc="1000",
            )
            amounts.append(Decimal(req["thc_amount"]))
        assert all(a == Decimal("28.000000") for a in amounts)

    def test_large_amount_precision(self, tmp_path):
        store = _make_store(tmp_path, fee=FixedFee("8.0000"))
        req = _create_request(store, thc="999999.999999", available="1000000")
        assert Decimal(req["thc_amount"]) == Decimal("999999.999999")
        fee = Decimal(req["fee_thc"])
        expected_fee = (Decimal("999999.999999") * Decimal("8") / Decimal("100")).quantize(
            _THC_SCALE,
        )
        assert fee == expected_fee


# ══════════════════════════════════════════════════════════════════════════
# 6. FEE BOUNDS (8–18%)
# ══════════════════════════════════════════════════════════════════════════

class TestFeeBounds:
    def test_fee_below_8_rejected(self, tmp_path):
        store = _make_store(tmp_path, fee=FixedFee("7.9999"))
        with pytest.raises(CashoutError, match="cashout_fee_out_of_bounds"):
            _create_request(store)

    def test_fee_exactly_8_accepted(self, tmp_path):
        store = _make_store(tmp_path, fee=FixedFee("8.0000"))
        req = _create_request(store)
        assert Decimal(req["fee_percent"]) == Decimal("8.0000")

    def test_fee_exactly_18_accepted(self, tmp_path):
        store = _make_store(tmp_path, fee=FixedFee("18.0000"))
        # Need enough THC for $25 minimum after 18% fee
        req = _create_request(store, thc="200", available="500")
        assert Decimal(req["fee_percent"]) == Decimal("18.0000")

    def test_fee_above_18_rejected(self, tmp_path):
        store = _make_store(tmp_path, fee=FixedFee("18.0001"))
        with pytest.raises(CashoutError, match="cashout_fee_out_of_bounds"):
            _create_request(store)

    def test_env_fee_schedule_validates_bounds(self):
        sched = EnvFeeSchedule()
        with patch.dict(os.environ, {"EARN_CASHOUT_FEE_PERCENT": "7.5"}):
            with pytest.raises(CashoutError, match="cashout_fee_out_of_bounds"):
                sched.cashout_fee_percent()
        with patch.dict(os.environ, {"EARN_CASHOUT_FEE_PERCENT": "19"}):
            with pytest.raises(CashoutError, match="cashout_fee_out_of_bounds"):
                sched.cashout_fee_percent()

    def test_env_fee_schedule_reads_valid_value(self):
        sched = EnvFeeSchedule()
        with patch.dict(os.environ, {"EARN_CASHOUT_FEE_PERCENT": "12.5"}):
            assert sched.cashout_fee_percent() == Decimal("12.5000")

    def test_env_fee_schedule_missing_raises(self):
        sched = EnvFeeSchedule()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EARN_CASHOUT_FEE_PERCENT", None)
            with pytest.raises(CashoutError, match="cashout_fee_not_configured"):
                sched.cashout_fee_percent()


# ══════════════════════════════════════════════════════════════════════════
# 7. STATE MACHINE TRANSITIONS
# ══════════════════════════════════════════════════════════════════════════

class TestStateMachine:
    def test_full_happy_path(self, tmp_path):
        store = _make_store(tmp_path)
        req = _create_request(store)
        rid = req["request_id"]
        assert req["state"] == "cashout_requested"

        r2 = store.transition(rid, "reserve_verified")
        assert r2["state"] == "reserve_verified"

        r3 = store.transition(rid, "signing")
        assert r3["state"] == "signing"

        r4 = store.transition(rid, "broadcasted", btc_txid=_VALID_TXID)
        assert r4["state"] == "broadcasted"

        r5 = store.transition(rid, "paid", btc_txid=_VALID_TXID)
        assert r5["state"] == "paid"
        assert r5["btc_txid"] == _VALID_TXID

    def test_cannot_skip_states(self, tmp_path):
        store = _make_store(tmp_path)
        req = _create_request(store)
        rid = req["request_id"]
        with pytest.raises(CashoutError, match="invalid_cashout_transition"):
            store.transition(rid, "signing")
        with pytest.raises(CashoutError, match="invalid_cashout_transition"):
            store.transition(rid, "paid", btc_txid=_VALID_TXID)

    def test_failure_from_any_non_terminal_state(self, tmp_path):
        store = _make_store(tmp_path)
        for starting_state in ["cashout_requested", "reserve_verified", "signing", "broadcasted"]:
            req = store.create_cashout_request(
                earn_user_id=f"user_{starting_state}",
                btc_address=_VALID_BTC_ADDR,
                thc_amount="100",
                available_thc="500",
            )
            rid = req["request_id"]
            # Advance to starting state
            if starting_state in ("reserve_verified", "signing", "broadcasted"):
                store.transition(rid, "reserve_verified")
            if starting_state in ("signing", "broadcasted"):
                store.transition(rid, "signing")
            if starting_state == "broadcasted":
                store.transition(rid, "broadcasted", btc_txid=_VALID_TXID)

            result = store.transition(rid, "failed", failure_reason="test failure")
            assert result["state"] == "failed"
            assert result["failure_reason"] == "test failure"

    def test_failed_requires_reason(self, tmp_path):
        store = _make_store(tmp_path)
        req = _create_request(store)
        with pytest.raises(CashoutError, match="failure_reason_required"):
            store.transition(req["request_id"], "failed")

    def test_cancelled_from_requested(self, tmp_path):
        store = _make_store(tmp_path)
        req = _create_request(store)
        result = store.transition(req["request_id"], "cancelled")
        assert result["state"] == "cancelled"

    def test_cannot_cancel_after_reserve_verified(self, tmp_path):
        store = _make_store(tmp_path)
        req = _create_request(store)
        store.transition(req["request_id"], "reserve_verified")
        with pytest.raises(CashoutError, match="invalid_cashout_transition"):
            store.transition(req["request_id"], "cancelled")

    def test_terminal_states_are_final(self, tmp_path):
        store = _make_store(tmp_path)
        # paid is terminal
        req = _create_request(store, user="u_paid")
        rid = req["request_id"]
        store.transition(rid, "reserve_verified")
        store.transition(rid, "signing")
        store.transition(rid, "broadcasted", btc_txid=_VALID_TXID)
        store.transition(rid, "paid", btc_txid=_VALID_TXID)
        with pytest.raises(CashoutError, match="invalid_cashout_transition"):
            store.transition(rid, "failed", failure_reason="too late")

    def test_idempotent_same_state(self, tmp_path):
        store = _make_store(tmp_path)
        req = _create_request(store)
        rid = req["request_id"]
        r1 = store.transition(rid, "reserve_verified")
        r2 = store.transition(rid, "reserve_verified")
        assert r1["state"] == r2["state"] == "reserve_verified"


# ══════════════════════════════════════════════════════════════════════════
# 8. BTC ADDRESS VALIDATION
# ══════════════════════════════════════════════════════════════════════════

class TestBtcAddressValidation:
    def test_valid_bech32(self):
        assert validate_btc_address(_VALID_BTC_ADDR) == _VALID_BTC_ADDR

    def test_valid_legacy(self):
        assert validate_btc_address(_VALID_LEGACY_ADDR) == _VALID_LEGACY_ADDR

    def test_valid_p2sh(self):
        assert validate_btc_address(_VALID_P2SH_ADDR) == _VALID_P2SH_ADDR

    def test_empty_rejected(self):
        with pytest.raises(CashoutError, match="invalid_btc_address"):
            validate_btc_address("")

    def test_none_rejected(self):
        with pytest.raises(CashoutError, match="invalid_btc_address"):
            validate_btc_address(None)

    def test_too_short_rejected(self):
        with pytest.raises(CashoutError, match="invalid_btc_address"):
            validate_btc_address("1abc")

    def test_testnet_rejected(self):
        with pytest.raises(CashoutError, match="invalid_btc_address"):
            validate_btc_address("tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx")

    def test_whitespace_stripped(self):
        result = validate_btc_address(f"  {_VALID_BTC_ADDR}  ")
        assert result == _VALID_BTC_ADDR


# ══════════════════════════════════════════════════════════════════════════
# 9. BALANCE AND CREATION VALIDATION
# ══════════════════════════════════════════════════════════════════════════

class TestCreationValidation:
    def test_insufficient_balance_rejected(self, tmp_path):
        store = _make_store(tmp_path)
        with pytest.raises(CashoutError, match="insufficient_thc_balance"):
            _create_request(store, thc="100", available="50")

    def test_zero_amount_rejected(self, tmp_path):
        store = _make_store(tmp_path)
        with pytest.raises(CashoutError, match="invalid_thc_amount"):
            _create_request(store, thc="0", available="100")

    def test_negative_amount_rejected(self, tmp_path):
        store = _make_store(tmp_path)
        with pytest.raises(CashoutError, match="invalid_thc_amount"):
            _create_request(store, thc="-50", available="100")

    def test_invalid_amount_rejected(self, tmp_path):
        store = _make_store(tmp_path)
        with pytest.raises(CashoutError, match="invalid_thc_amount"):
            _create_request(store, thc="not_a_number", available="100")


# ══════════════════════════════════════════════════════════════════════════
# 10. QUERIES
# ══════════════════════════════════════════════════════════════════════════

class TestQueries:
    def test_get_request(self, tmp_path):
        store = _make_store(tmp_path)
        req = _create_request(store)
        fetched = store.get_request(req["request_id"])
        assert fetched["request_id"] == req["request_id"]

    def test_get_missing_request_returns_none(self, tmp_path):
        store = _make_store(tmp_path)
        assert store.get_request("nonexistent") is None

    def test_list_requests_scoped_to_user(self, tmp_path):
        store = _make_store(tmp_path)
        _create_request(store, user="alice")
        _create_request(store, user="bob")
        alice_reqs = store.list_requests("alice")
        assert len(alice_reqs) == 1
        assert alice_reqs[0]["earn_user_id"] == "alice"

    def test_list_pending(self, tmp_path):
        store = _make_store(tmp_path)
        r1 = _create_request(store, user="u1")
        r2 = _create_request(store, user="u2")
        store.transition(r1["request_id"], "failed", failure_reason="test")
        pending = store.list_pending()
        assert len(pending) == 1
        assert pending[0]["earn_user_id"] == "u2"


# ══════════════════════════════════════════════════════════════════════════
# 11. SOURCE SAFETY
# ══════════════════════════════════════════════════════════════════════════

class TestSourceSafety:
    def test_no_private_key_references(self):
        source = (Path(__file__).parent.parent / "services" / "earn_btc_cashout.py").read_text()
        for term in ["private_key", "privkey", "priv_key", "secret_key", "wif"]:
            assert term not in source.lower(), f"'{term}' found in cashout source"

    def test_no_simulated_success(self):
        """Executable code must not contain simulation/fabrication patterns."""
        source = (Path(__file__).parent.parent / "services" / "earn_btc_cashout.py").read_text()
        # Strip module and class docstrings before checking
        import ast
        tree = ast.parse(source)
        code_lines = set(range(1, len(source.split("\n")) + 1))
        for node in ast.walk(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                for ln in range(node.lineno, node.end_lineno + 1):
                    code_lines.discard(ln)
        lines = source.split("\n")
        for i in sorted(code_lines):
            line = lines[i - 1] if i <= len(lines) else ""
            low = line.lower()
            for term in ["fake_txid", "mock_txid"]:
                assert term not in low, f"'{term}' found at line {i}"

    def test_no_hardcoded_secrets(self):
        source = (Path(__file__).parent.parent / "services" / "earn_btc_cashout.py").read_text()
        # No hex strings that look like private keys (>= 64 chars hex literal)
        hex_pattern = re.compile(r'"[0-9a-fA-F]{64,}"')
        matches = hex_pattern.findall(source)
        assert len(matches) == 0, f"Suspicious hex literals: {matches}"

    def test_transition_map_matches_docstring(self):
        """Every declared state appears in transitions, and terminals have empty sets."""
        for state, targets in _CASHOUT_TRANSITIONS.items():
            assert isinstance(targets, set)
        assert _CASHOUT_TRANSITIONS["paid"] == set()
        assert _CASHOUT_TRANSITIONS["failed"] == set()
        assert _CASHOUT_TRANSITIONS["cancelled"] == set()
