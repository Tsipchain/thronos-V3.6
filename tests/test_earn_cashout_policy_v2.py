from dataclasses import replace
from decimal import Decimal

import pytest

from services.earn_cashout_policy_v2 import (
    CashoutPolicyError,
    PythiaLiquidityEvidence,
    SponsoredInternalBtcGrant,
    ThcUsdValuation,
    evaluate_cashout_policy_v2,
)
from services.pythia_wallet_settlement_quote import PythiaWalletSettlementQuote


NOW = 1_800_000_000
USER = "earn-user-1"
WALLET = "THR" + "a" * 40
RESERVE = "THR" + "b" * 40


class Store:
    def __init__(self, *, linked=False, available="100000.000000"):
        self.linked = linked
        self.available = available
        self.calls = []

    def wallet_link_for_user(self, earn_user_id):
        self.calls.append(("wallet_link", earn_user_id))
        return {"wallet_address": WALLET} if self.linked else None

    def thc_balance(self, earn_user_id):
        self.calls.append(("balance", earn_user_id))
        return {"available": self.available, "reserved": "0.000000"}


class ValuationAuthority:
    def __init__(self, usd="100.000000", quote=None):
        self.usd = usd
        self.quote = quote
        self.calls = []

    def quote_thc_usd(self, *, earn_user_id, thc_amount):
        self.calls.append((earn_user_id, thc_amount))
        return self.quote or ThcUsdValuation(
            quote_id="usd-quote-1",
            earn_user_id=earn_user_id,
            thc_amount=thc_amount,
            usd_equivalent=Decimal(self.usd),
            expires_at=NOW + 120,
            pricing_version="trusted-usd-v1",
            attestation="server-side-attestation",
        )


class Sponsor:
    def authorize(self, *, earn_user_id, thc_amount):
        return SponsoredInternalBtcGrant(
            grant_id="sponsor-grant-1",
            earn_user_id=earn_user_id,
            thc_amount=thc_amount,
            expires_at=NOW + 120,
            policy_version="internal-btc-sponsor-v1",
            attestation="server-side-sponsor-attestation",
        )


def pythia_quote(**changes):
    quote = PythiaWalletSettlementQuote(
        quote_id="pythia-quote-1",
        earn_user_id=USER,
        wallet_address=WALLET,
        thc_amount=Decimal("25000.000000"),
        gross_thr=Decimal("100.000000"),
        fee_thr=Decimal("0.090000"),
        net_thr=Decimal("99.910000"),
        speed="slow",
        reserve_address=RESERVE,
        expires_at=NOW + 120,
        policy_version="pythia-wallet-v1",
        attestation="trusted-pythia-quote",
    )
    return replace(quote, **changes)


class Liquidity:
    def __init__(self, **changes):
        self.changes = changes

    def verify_quote_liquidity(self, quote):
        evidence = PythiaLiquidityEvidence(
            evidence_id="liquidity-1",
            quote_id=quote.quote_id,
            reserve_address=quote.reserve_address,
            available_thr=Decimal("100.000000"),
            expires_at=NOW + 60,
            attestation="verified-reserve-liquidity",
        )
        return replace(evidence, **self.changes)


def decide(store, authority, **kwargs):
    defaults = dict(
        earn_user_id=USER,
        requested_thc="25000.000000",
        route="external_btc",
        external_btc_fee_bps=800,
        now_fn=lambda: NOW,
    )
    defaults.update(kwargs)
    return evaluate_cashout_policy_v2(store, authority, **defaults)


def test_unlinked_account_requires_one_hundred_usd_equivalent():
    with pytest.raises(CashoutPolicyError, match="cashout_minimum_not_met"):
        decide(Store(), ValuationAuthority("99.999999"))
    out = decide(Store(), ValuationAuthority("100.000000"))
    assert out.minimum_usd == Decimal("100.000000")
    assert out.user_fee_bps == 800
    assert out.payout_enabled is False


def test_verified_persisted_wallet_link_reduces_minimum_to_twenty_five_usd():
    out = decide(Store(linked=True), ValuationAuthority("25.000000"))
    assert out.verified_wallet_link is True
    assert out.minimum_usd == Decimal("25.000000")
    with pytest.raises(CashoutPolicyError, match="cashout_minimum_not_met"):
        decide(Store(linked=True), ValuationAuthority("24.999999"))


def test_caller_cannot_claim_wallet_link_or_supply_its_own_usd_rate():
    store = Store(linked=False)
    authority = ValuationAuthority("100.000000")
    out = decide(store, authority)
    assert out.verified_wallet_link is False
    assert authority.calls == [(USER, Decimal("25000.000000"))]
    assert store.calls == [("balance", USER), ("wallet_link", USER)]


@pytest.mark.parametrize("fee", [799, 1801, None, True])
def test_external_btc_preserves_existing_fee_bounds(fee):
    with pytest.raises(CashoutPolicyError, match="external_btc_fee_out_of_bounds"):
        decide(Store(), ValuationAuthority(), external_btc_fee_bps=fee)


def test_only_attested_sponsored_internal_btc_has_zero_user_fee():
    out = decide(
        Store(), ValuationAuthority(), route="sponsored_internal_btc",
        external_btc_fee_bps=None, sponsored_authority=Sponsor(),
    )
    assert out.user_fee_bps == 0
    assert out.evidence_reference == "sponsor-grant-1"
    with pytest.raises(CashoutPolicyError, match="sponsorship_authority_required"):
        decide(
            Store(), ValuationAuthority(), route="sponsored_internal_btc",
            external_btc_fee_bps=None,
        )


def test_linked_thr_fails_closed_without_verified_pythia_liquidity():
    with pytest.raises(CashoutPolicyError, match="verified_pythia_liquidity_required"):
        decide(
            Store(linked=True), ValuationAuthority("25.000000"),
            route="linked_thr", external_btc_fee_bps=None,
            pythia_quote=pythia_quote(),
        )
    with pytest.raises(CashoutPolicyError, match="verified_pythia_liquidity_required"):
        decide(
            Store(linked=True), ValuationAuthority("25.000000"),
            route="linked_thr", external_btc_fee_bps=None,
            pythia_quote=pythia_quote(),
            liquidity_verifier=Liquidity(available_thr=Decimal("99.999999")),
        )


def test_linked_thr_accepts_exact_identity_and_liquidity_as_preflight_only():
    out = decide(
        Store(linked=True), ValuationAuthority("25.000000"),
        route="linked_thr", external_btc_fee_bps=None,
        pythia_quote=pythia_quote(), liquidity_verifier=Liquidity(),
    )
    assert out.eligible is True
    assert out.payout_enabled is False
    assert out.evidence_reference == "liquidity-1"


@pytest.mark.parametrize("change,error", [
    ({"earn_user_id": "other"}, "valuation_identity_mismatch"),
    ({"thc_amount": Decimal("25000.000001")}, "valuation_amount_mismatch"),
    ({"attestation": ""}, "unattested_usd_valuation"),
    ({"expires_at": NOW + 301}, "expired_or_unbounded_valuation"),
])
def test_usd_valuation_is_identity_amount_and_time_bound(change, error):
    quote = ThcUsdValuation(
        quote_id="usd-quote-1", earn_user_id=USER,
        thc_amount=Decimal("25000.000000"),
        usd_equivalent=Decimal("100.000000"), expires_at=NOW + 120,
        pricing_version="trusted-usd-v1", attestation="attested",
    )
    with pytest.raises(CashoutPolicyError, match=error):
        decide(Store(), ValuationAuthority(quote=replace(quote, **change)))


def test_preflight_has_no_reservation_signer_broadcast_or_balance_mutation():
    store = Store(linked=True)
    before = store.available
    out = decide(store, ValuationAuthority("25.000000"))
    assert store.available == before
    assert out.status == "eligible_preflight_only_operator_activation_required"
    assert not hasattr(out, "txid")
    assert not hasattr(store, "reserve")
