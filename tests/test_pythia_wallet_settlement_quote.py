from dataclasses import replace
from decimal import Decimal

import pytest

from services.pythia_wallet_settlement_quote import (
    LinkedWalletSettlementQuoteGate,
    PythiaQuoteError,
    PythiaWalletSettlementQuote,
)


NOW = 1_800_000_000
USER = "earn_test_user"
WALLET = "THR" + "a" * 40
RESERVE = "THR" + "b" * 40


class FakePythia:
    def __init__(self, quote=None):
        self.quote = quote
        self.calls = []

    def quote_linked_wallet_settlement(self, **kwargs):
        self.calls.append(kwargs)
        return self.quote or valid_quote(**kwargs)


def valid_quote(
    earn_user_id=USER,
    wallet_address=WALLET,
    thc_amount=Decimal("25000.000000"),
    speed="slow",
    **_,
):
    return PythiaWalletSettlementQuote(
        quote_id="pyq_1",
        earn_user_id=earn_user_id,
        wallet_address=wallet_address,
        thc_amount=Decimal(str(thc_amount)),
        gross_thr=Decimal("100.000000"),
        fee_thr=Decimal("0.090000"),
        net_thr=Decimal("99.910000"),
        speed=speed,
        reserve_address=RESERVE,
        expires_at=NOW + 120,
        policy_version="pythia-wallet-v1",
        attestation="authority-attested-quote",
    )


@pytest.fixture
def pythia():
    return FakePythia()


@pytest.fixture
def gate(pythia):
    return LinkedWalletSettlementQuoteGate(pythia, now_fn=lambda: NOW)


def issue(gate, **kwargs):
    defaults = dict(
        earn_user_id=USER,
        wallet_address=WALLET,
        cleared_available_thc="30000.000000",
        requested_thc="25000.000000",
        speed="slow",
    )
    defaults.update(kwargs)
    return gate.issue(**defaults)


def test_quote_uses_authority_with_exact_wallet_and_decimal_amount(gate, pythia):
    quote = issue(gate)
    assert quote.public_dict()["net_thr"] == "99.910000"
    assert pythia.calls == [{
        "earn_user_id": USER,
        "wallet_address": WALLET,
        "thc_amount": Decimal("25000.000000"),
        "speed": "slow",
    }]


@pytest.mark.parametrize("amount", ["24999.999999", "0", "-1", "nan"])
def test_rejects_below_or_invalid_linked_wallet_minimum(gate, amount):
    with pytest.raises(PythiaQuoteError):
        issue(gate, requested_thc=amount)


def test_rejects_request_above_cleared_available_thc(gate):
    with pytest.raises(PythiaQuoteError, match="insufficient_cleared_thc"):
        issue(gate, cleared_available_thc="25000.000000", requested_thc="25000.000001")


@pytest.mark.parametrize("speed", ["", "instant", "FAST"])
def test_rejects_unknown_speed_before_pythia_call(gate, pythia, speed):
    with pytest.raises(PythiaQuoteError, match="invalid_settlement_speed"):
        issue(gate, speed=speed)
    assert pythia.calls == []


@pytest.mark.parametrize("field,error", [
    ("quote_id", "unattested_pythia_quote"),
    ("attestation", "unattested_pythia_quote"),
    ("reserve_address", "unattested_pythia_quote"),
    ("policy_version", "unattested_pythia_quote"),
])
def test_requires_attested_quote_fields(field, error):
    quote = valid_quote()
    pythia = FakePythia(replace(quote, **{field: ""}))
    gate = LinkedWalletSettlementQuoteGate(pythia, now_fn=lambda: NOW)
    with pytest.raises(PythiaQuoteError, match=error):
        issue(gate)


@pytest.mark.parametrize("quote_change,error", [
    ({"earn_user_id": "earn_other"}, "quote_identity_mismatch"),
    ({"wallet_address": "THR" + "c" * 40}, "quote_identity_mismatch"),
    ({"thc_amount": Decimal("25000.000001")}, "quote_thc_amount_mismatch"),
    ({"speed": "fast"}, "quote_speed_mismatch"),
    ({"expires_at": NOW}, "expired_or_unbounded_quote"),
    ({"expires_at": NOW + 301}, "expired_or_unbounded_quote"),
])
def test_quote_must_match_request_and_be_short_lived(quote_change, error):
    pythia = FakePythia(replace(valid_quote(), **quote_change))
    gate = LinkedWalletSettlementQuoteGate(pythia, now_fn=lambda: NOW)
    with pytest.raises(PythiaQuoteError, match=error):
        issue(gate)


@pytest.mark.parametrize("quote_change", [
    {"fee_thr": Decimal("-0.000001")},
    {"fee_thr": Decimal("100.000000")},
    {"net_thr": Decimal("99.900000")},
])
def test_quote_fee_arithmetic_must_be_exact(quote_change):
    pythia = FakePythia(replace(valid_quote(), **quote_change))
    gate = LinkedWalletSettlementQuoteGate(pythia, now_fn=lambda: NOW)
    with pytest.raises(PythiaQuoteError, match="invalid_pythia_fee_quote"):
        issue(gate)


def test_no_float_conversion_in_quote_gate_source():
    import inspect
    import services.pythia_wallet_settlement_quote as module
    source = inspect.getsource(module)
    assert "float(" not in source
