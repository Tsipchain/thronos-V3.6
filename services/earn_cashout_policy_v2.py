"""Read-only policy gate for the proposed Earn Cashout Policy V2.

This module deliberately cannot create a reservation, debit THC, convert to
THR, construct a Bitcoin transaction, or invoke a signer.  It only validates
trusted, short-lived evidence and returns an eligibility decision for a later,
separately approved settlement implementation.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import time
from typing import Any, Protocol

from services.pythia_wallet_settlement_quote import (
    PythiaWalletSettlementQuote,
    THR_SCALE,
)


POLICY_VERSION = "earn-cashout-policy-v2"
USD_SCALE = Decimal("0.000001")
THC_SCALE = Decimal("0.000001")
UNLINKED_MINIMUM_USD = Decimal("100.000000")
VERIFIED_LINKED_MINIMUM_USD = Decimal("25.000000")
MAX_EVIDENCE_TTL_SECONDS = 300
EXTERNAL_BTC_FEE_BPS_MIN = 800
EXTERNAL_BTC_FEE_BPS_MAX = 1800


class CashoutPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class ThcUsdValuation:
    quote_id: str
    earn_user_id: str
    thc_amount: Decimal
    usd_equivalent: Decimal
    expires_at: int
    pricing_version: str
    attestation: str


class ThcUsdValuationAuthority(Protocol):
    """Trusted server-side pricing authority; never a browser-supplied rate."""

    def quote_thc_usd(
        self, *, earn_user_id: str, thc_amount: Decimal,
    ) -> ThcUsdValuation:
        ...


@dataclass(frozen=True)
class SponsoredInternalBtcGrant:
    grant_id: str
    earn_user_id: str
    thc_amount: Decimal
    expires_at: int
    policy_version: str
    attestation: str


class SponsoredInternalBtcAuthority(Protocol):
    def authorize(
        self, *, earn_user_id: str, thc_amount: Decimal,
    ) -> SponsoredInternalBtcGrant:
        ...


@dataclass(frozen=True)
class PythiaLiquidityEvidence:
    evidence_id: str
    quote_id: str
    reserve_address: str
    available_thr: Decimal
    expires_at: int
    attestation: str


class PythiaLiquidityVerifier(Protocol):
    """Trusted verifier for quote authenticity and reserve liquidity."""

    def verify_quote_liquidity(
        self, quote: PythiaWalletSettlementQuote,
    ) -> PythiaLiquidityEvidence:
        ...


class CashoutPolicyStore(Protocol):
    def wallet_link_for_user(self, earn_user_id: str) -> dict[str, str] | None:
        ...

    def thc_balance(self, earn_user_id: str) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class CashoutPolicyDecision:
    earn_user_id: str
    route: str
    thc_amount: Decimal
    usd_equivalent: Decimal
    minimum_usd: Decimal
    verified_wallet_link: bool
    user_fee_bps: int
    valuation_quote_id: str
    pricing_version: str
    evidence_reference: str
    eligible: bool = True
    payout_enabled: bool = False
    policy_version: str = POLICY_VERSION
    status: str = "eligible_preflight_only_operator_activation_required"

    def public_dict(self) -> dict[str, str | int | bool]:
        return {
            "earn_user_id": self.earn_user_id,
            "route": self.route,
            "thc_amount": str(self.thc_amount),
            "usd_equivalent": str(self.usd_equivalent),
            "minimum_usd": str(self.minimum_usd),
            "verified_wallet_link": self.verified_wallet_link,
            "user_fee_bps": self.user_fee_bps,
            "valuation_quote_id": self.valuation_quote_id,
            "pricing_version": self.pricing_version,
            "evidence_reference": self.evidence_reference,
            "eligible": self.eligible,
            "payout_enabled": self.payout_enabled,
            "policy_version": self.policy_version,
            "status": self.status,
        }


def _exact_positive(value: Decimal | str, scale: Decimal, error: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
        if not parsed.is_finite() or parsed <= 0 or parsed != parsed.quantize(scale):
            raise ValueError
        return parsed
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise CashoutPolicyError(error) from exc


def _bounded_expiry(expires_at: int, now: int) -> bool:
    return isinstance(expires_at, int) and now < expires_at <= now + MAX_EVIDENCE_TTL_SECONDS


def _validate_valuation(
    quote: ThcUsdValuation, *, earn_user_id: str, thc_amount: Decimal, now: int,
) -> ThcUsdValuation:
    if not quote.quote_id or not quote.pricing_version or not quote.attestation:
        raise CashoutPolicyError("unattested_usd_valuation")
    if quote.earn_user_id != earn_user_id:
        raise CashoutPolicyError("valuation_identity_mismatch")
    if _exact_positive(quote.thc_amount, THC_SCALE, "invalid_valuation_amount") != thc_amount:
        raise CashoutPolicyError("valuation_amount_mismatch")
    _exact_positive(quote.usd_equivalent, USD_SCALE, "invalid_usd_equivalent")
    if not _bounded_expiry(quote.expires_at, now):
        raise CashoutPolicyError("expired_or_unbounded_valuation")
    return quote


def evaluate_cashout_policy_v2(
    store: CashoutPolicyStore,
    valuation_authority: ThcUsdValuationAuthority,
    *,
    earn_user_id: str,
    requested_thc: Decimal | str,
    route: str,
    external_btc_fee_bps: int | None = None,
    sponsored_authority: SponsoredInternalBtcAuthority | None = None,
    pythia_quote: PythiaWalletSettlementQuote | None = None,
    liquidity_verifier: PythiaLiquidityVerifier | None = None,
    now_fn=time.time,
) -> CashoutPolicyDecision:
    """Return a non-executable policy decision based on authoritative evidence."""
    if not earn_user_id or store is None or valuation_authority is None:
        raise CashoutPolicyError("missing_cashout_authority")
    if route not in {"external_btc", "sponsored_internal_btc", "linked_thr"}:
        raise CashoutPolicyError("unsupported_cashout_route")
    amount = _exact_positive(requested_thc, THC_SCALE, "invalid_cashout_amount")
    balance = store.thc_balance(earn_user_id)
    if not isinstance(balance, dict) or "available" not in balance:
        raise CashoutPolicyError("cleared_balance_unavailable")
    try:
        available = Decimal(str(balance["available"]))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise CashoutPolicyError("cleared_balance_unavailable") from exc
    if (not available.is_finite() or available < 0
            or available != available.quantize(THC_SCALE)):
        raise CashoutPolicyError("cleared_balance_unavailable")
    if amount > available:
        raise CashoutPolicyError("insufficient_cleared_thc")

    now = int(now_fn())
    valuation = _validate_valuation(
        valuation_authority.quote_thc_usd(
            earn_user_id=earn_user_id, thc_amount=amount,
        ),
        earn_user_id=earn_user_id,
        thc_amount=amount,
        now=now,
    )
    usd_equivalent = _exact_positive(
        valuation.usd_equivalent, USD_SCALE, "invalid_usd_equivalent",
    )
    link = store.wallet_link_for_user(earn_user_id)
    wallet_address = str((link or {}).get("wallet_address", "")).strip()
    verified_link = bool(wallet_address)
    minimum = VERIFIED_LINKED_MINIMUM_USD if verified_link else UNLINKED_MINIMUM_USD
    if usd_equivalent < minimum:
        raise CashoutPolicyError("cashout_minimum_not_met")

    evidence_reference = valuation.quote_id
    user_fee_bps = 0
    if route == "external_btc":
        if (isinstance(external_btc_fee_bps, bool)
                or not isinstance(external_btc_fee_bps, int)
                or not EXTERNAL_BTC_FEE_BPS_MIN
                <= external_btc_fee_bps
                <= EXTERNAL_BTC_FEE_BPS_MAX):
            raise CashoutPolicyError("external_btc_fee_out_of_bounds")
        user_fee_bps = external_btc_fee_bps
    elif route == "sponsored_internal_btc":
        if sponsored_authority is None:
            raise CashoutPolicyError("sponsorship_authority_required")
        grant = sponsored_authority.authorize(
            earn_user_id=earn_user_id, thc_amount=amount,
        )
        if not grant.grant_id or not grant.attestation or not grant.policy_version:
            raise CashoutPolicyError("unattested_sponsorship")
        if grant.earn_user_id != earn_user_id:
            raise CashoutPolicyError("sponsorship_identity_mismatch")
        if _exact_positive(grant.thc_amount, THC_SCALE, "invalid_sponsorship_amount") != amount:
            raise CashoutPolicyError("sponsorship_amount_mismatch")
        if not _bounded_expiry(grant.expires_at, now):
            raise CashoutPolicyError("expired_or_unbounded_sponsorship")
        evidence_reference = grant.grant_id
    else:
        if not verified_link:
            raise CashoutPolicyError("wallet_link_required")
        if pythia_quote is None or liquidity_verifier is None:
            raise CashoutPolicyError("verified_pythia_liquidity_required")
        if (pythia_quote.earn_user_id != earn_user_id
                or pythia_quote.wallet_address != wallet_address
                or _exact_positive(
                    pythia_quote.thc_amount, THC_SCALE, "invalid_pythia_quote_amount",
                ) != amount
                or not pythia_quote.quote_id
                or not pythia_quote.attestation
                or not pythia_quote.policy_version
                or not pythia_quote.reserve_address
                or not _bounded_expiry(pythia_quote.expires_at, now)):
            raise CashoutPolicyError("invalid_pythia_quote")
        liquidity = liquidity_verifier.verify_quote_liquidity(pythia_quote)
        available_thr = _exact_positive(
            liquidity.available_thr, THR_SCALE, "invalid_pythia_liquidity",
        )
        required_thr = _exact_positive(
            pythia_quote.gross_thr, THR_SCALE, "invalid_pythia_quote_amount",
        )
        if (not liquidity.evidence_id or not liquidity.attestation
                or liquidity.quote_id != pythia_quote.quote_id
                or liquidity.reserve_address != pythia_quote.reserve_address
                or available_thr < required_thr
                or not _bounded_expiry(liquidity.expires_at, now)):
            raise CashoutPolicyError("verified_pythia_liquidity_required")
        evidence_reference = liquidity.evidence_id

    return CashoutPolicyDecision(
        earn_user_id=earn_user_id,
        route=route,
        thc_amount=amount,
        usd_equivalent=usd_equivalent,
        minimum_usd=minimum,
        verified_wallet_link=verified_link,
        user_fee_bps=user_fee_bps,
        valuation_quote_id=valuation.quote_id,
        pricing_version=valuation.pricing_version,
        evidence_reference=evidence_reference,
    )
