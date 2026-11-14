from dataclasses import replace
from decimal import Decimal
import pytest
from services.earn_thr_linked_wallet_preflight import prepare_linked_wallet_redemption
from services.pythia_wallet_settlement_quote import (
    PythiaWalletSettlementQuote, PythiaQuoteError,
)

USER = "user-1"
WALLET = "THR" + "A" * 40


class Store:
    def __init__(self, *, link=True, available="26000.000000"):
        self.link = link
        self.available = available

    def wallet_link_for_user(self, user):
        return {"wallet_address": WALLET} if self.link else None

    def thc_balance(self, user):
        return {"available": self.available, "pending": "50000.000000",
                "reserved": "0.000000"}


class Pythia:
    def __init__(self, *, mismatch=False):
        self.calls = []
        self.mismatch = mismatch

    def quote_linked_wallet_settlement(self, *, earn_user_id, wallet_address,
                                       thc_amount, speed):
        self.calls.append((earn_user_id, wallet_address, thc_amount, speed))
        return PythiaWalletSettlementQuote(
            quote_id="pythia-quote-1",
            earn_user_id=earn_user_id,
            wallet_address="THR" + "B" * 40 if self.mismatch else wallet_address,
            thc_amount=thc_amount,
            gross_thr=Decimal("100.000000"),
            fee_thr=Decimal("0.090000"),
            net_thr=Decimal("99.910000"),
            speed=speed,
            reserve_address="THR" + "C" * 40,
            expires_at=1100,
            policy_version="v1",
            attestation="trusted-pythia-reference",
        )


def test_real_link_and_spendable_balance_bound_to_authoritative_quote():
    p = Pythia()
    out = prepare_linked_wallet_redemption(
        Store(), p, earn_user_id=USER,
        requested_thc="25000.000000", speed="slow", now_fn=lambda: 1000,
    )
    assert out.wallet_address == WALLET
    assert p.calls == [(USER, WALLET, Decimal("25000.000000"), "slow")]
    assert out.public_dict()["status"] == "device_approval_and_treasury_verification_required"
    assert "attestation" not in out.public_dict()


@pytest.mark.parametrize("store, requested, error", [
    (Store(link=False), "25000.000000", "wallet_link_required"),
    (Store(available="24999.999999"), "25000.000000", "insufficient_cleared_thc"),
    (Store(), "24999.999999", "linked_wallet_minimum_not_met"),
    (Store(), "25000.0000001", "invalid_quote_amount"),
])
def test_invalid_account_or_amount_never_requests_quote(store, requested, error):
    p = Pythia()
    with pytest.raises(PythiaQuoteError, match=error):
        prepare_linked_wallet_redemption(
            store, p, earn_user_id=USER,
            requested_thc=requested, speed="slow", now_fn=lambda: 1000,
        )
    assert p.calls == []


def test_wrong_wallet_in_quote_rejected():
    with pytest.raises(PythiaQuoteError, match="quote_identity_mismatch"):
        prepare_linked_wallet_redemption(
            Store(), Pythia(mismatch=True),
            earn_user_id=USER, requested_thc="25000.000000",
            speed="slow", now_fn=lambda: 1000,
        )


def test_pending_does_not_make_spendable():
    p = Pythia()
    with pytest.raises(PythiaQuoteError, match="insufficient_cleared_thc"):
        prepare_linked_wallet_redemption(
            Store(available="0.000000"), p,
            earn_user_id=USER, requested_thc="25000.000000",
            speed="slow", now_fn=lambda: 1000,
        )
    assert p.calls == []


def test_read_only_no_reservation_or_settlement_access():
    store = Store()
    out = prepare_linked_wallet_redemption(
        store, Pythia(), earn_user_id=USER,
        requested_thc="25000.000000", speed="slow", now_fn=lambda: 1000,
    )
    assert store.available == "26000.000000"
    assert out.status != "settled"
