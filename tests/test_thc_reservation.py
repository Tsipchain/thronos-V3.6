"""
Tests for ThcReservationLedger interface contract.

These tests validate the interface definition and error types.
Implementation tests will be added when the methods are built.
"""
from decimal import Decimal

import pytest

from services.thc_reservation import (
    InsufficientThcError,
    ThcReservationLedger,
)


class TestInterfaceContract:
    """Verify the interface is importable and has the right shape."""

    def test_lock_type_constants(self):
        assert ThcReservationLedger.LOCK_STAKING == "staking"
        assert ThcReservationLedger.LOCK_CASHOUT == "cashout"
        assert ThcReservationLedger.LOCK_AD_ESCROW == "ad_escrow"

    def test_active_states(self):
        assert "reserved" in ThcReservationLedger.ACTIVE_STATES
        assert "settling" in ThcReservationLedger.ACTIVE_STATES

    def test_schema_creates_table(self):
        assert "thc_reservations" in ThcReservationLedger.SCHEMA
        assert "reservation_id" in ThcReservationLedger.SCHEMA
        assert "earn_user_id" in ThcReservationLedger.SCHEMA
        assert "lock_type" in ThcReservationLedger.SCHEMA

    def test_schema_creates_index(self):
        assert "idx_res_user_state" in ThcReservationLedger.SCHEMA

    def test_try_reserve_not_implemented(self):
        ledger = ThcReservationLedger()
        with pytest.raises(NotImplementedError, match="interface definition"):
            ledger.try_reserve(
                earn_user_id="u1",
                lock_type="cashout",
                thc_amount=Decimal("100"),
            )

    def test_confirm_not_implemented(self):
        ledger = ThcReservationLedger()
        with pytest.raises(NotImplementedError, match="interface definition"):
            ledger.confirm("res_123")

    def test_release_not_implemented(self):
        ledger = ThcReservationLedger()
        with pytest.raises(NotImplementedError, match="interface definition"):
            ledger.release("res_123")

    def test_total_reserved_not_implemented(self):
        ledger = ThcReservationLedger()
        with pytest.raises(NotImplementedError, match="interface definition"):
            ledger.total_reserved("u1")

    def test_reservations_by_type_not_implemented(self):
        ledger = ThcReservationLedger()
        with pytest.raises(NotImplementedError, match="interface definition"):
            ledger.reservations_by_type("u1", "cashout")


class TestInsufficientThcError:
    def test_error_message(self):
        err = InsufficientThcError(
            available=Decimal("50"), requested=Decimal("100"),
        )
        assert "insufficient_thc" in str(err)
        assert "50" in str(err)
        assert "100" in str(err)

    def test_error_attributes(self):
        err = InsufficientThcError(
            available=Decimal("200.5"), requested=Decimal("300"),
        )
        assert err.available == Decimal("200.5")
        assert err.requested == Decimal("300")

    def test_is_exception(self):
        err = InsufficientThcError(
            available=Decimal("0"), requested=Decimal("1"),
        )
        assert isinstance(err, Exception)


class TestCrossServiceScenarios:
    """Document the double-spend scenarios this interface prevents."""

    def test_scenario_stake_then_cashout_same_thc(self):
        """Without the reservation ledger:
        - User has 1000 THC
        - Staking service locks 800 THC (checks its own DB: 1000 available)
        - Cashout service locks 500 THC (checks its own DB: 1000 available)
        - Total committed: 1300 THC > 1000 THC balance → double-spend

        With the reservation ledger:
        - try_reserve("staking", 800) → succeeds (1000 - 0 = 1000 available)
        - try_reserve("cashout", 500) → raises InsufficientThcError
          (1000 - 800 = 200 available < 500 requested)
        """
        pass  # Documented scenario; implementation test follows

    def test_scenario_cashout_then_ad_escrow(self):
        """Without the reservation ledger:
        - User has 500 THC
        - Cashout locks 400 THC
        - Ad package activation locks 200 THC
        - Total: 600 > 500 → double-spend

        With the reservation ledger:
        - try_reserve("cashout", 400) → succeeds
        - try_reserve("ad_escrow", 200) → raises InsufficientThcError
        """
        pass

    def test_scenario_release_frees_balance(self):
        """When a cashout fails:
        - try_reserve("cashout", 400) → succeeds, 100 available
        - Cashout fails → release(reservation_id)
        - try_reserve("staking", 300) → succeeds (500 - 0 = 500 available)
        """
        pass
