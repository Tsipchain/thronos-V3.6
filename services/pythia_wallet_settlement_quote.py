"""Pythia quote gate for linked-wallet Earn settlement.

This module deliberately does not price THC, move THR, or broadcast a
transaction.  It validates an authoritative, short-lived Pythia quote before
a later settlement executor may reserve THC and transfer THR from the system
reserve to the linked wallet.

A quote is rejected unless it names the exact wallet, carries a non-empty
attestation, has a bounded lifetime, and produces a positive net THR amount.
No fallback rate and no float arithmetic exist here.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import time
from typing import Protocol

THC_SCALE = Decimal("0.000001")
THR_SCALE = Decimal("0.000001")
MIN_LINKED_WALLET_SETTLEMENT_THC = Decimal("25000.000000")
MAX_QUOTE_TTL_SECONDS = 300


class PythiaQuoteError(ValueError):
    pass


@dataclass(frozen=True)
class PythiaWalletSettlementQuote:
    quote_id: str
    earn_user_id: str
    wallet_address: str
    thc_amount: Decimal
    gross_thr: Decimal
    fee_thr: Decimal
    net_thr: Decimal
    speed: str
    reserve_address: str
    expires_at: int
    policy_version: str
    attestation: str

    def public_dict(self) -> dict[str, str | int]:
        return {
            "quote_id": self.quote_id,
            "earn_user_id": self.earn_user_id,
            "wallet_address": self.wallet_address,
            "thc_amount": str(self.thc_amount.quantize(THC_SCALE)),
            "gross_thr": str(self.gross_thr.quantize(THR_SCALE)),
            "fee_thr": str(self.fee_thr.quantize(THR_SCALE)),
            "net_thr": str(self.net_thr.quantize(THR_SCALE)),
            "speed": self.speed,
            "reserve_address": self.reserve_address,
            "expires_at": self.expires_at,
            "policy_version": self.policy_version,
        }


class PythiaQuoteAuthority(Protocol):
    """Trusted Pythia component, not an HTTP request supplied by a browser."""

    def quote_linked_wallet_settlement(
        self,
        *,
        earn_user_id: str,
        wallet_address: str,
        thc_amount: Decimal,
        speed: str,
    ) -> PythiaWalletSettlementQuote:
        ...


def _amount(value: Decimal | str, scale: Decimal) -> Decimal:
    try:
        parsed = Decimal(str(value))
        if not parsed.is_finite() or parsed <= 0:
            raise ValueError
        return parsed.quantize(scale)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PythiaQuoteError("invalid_quote_amount") from exc


class LinkedWalletSettlementQuoteGate:
    """Validation boundary between Earn and the authoritative Pythia quote."""

    def __init__(
        self,
        authority: PythiaQuoteAuthority,
        *,
        now_fn=time.time,
        min_thc: Decimal = MIN_LINKED_WALLET_SETTLEMENT_THC,
    ) -> None:
        self._authority = authority
        self._now_fn = now_fn
        self._min_thc = _amount(min_thc, THC_SCALE)

    def issue(
        self,
        *,
        earn_user_id: str,
        wallet_address: str,
        cleared_available_thc: Decimal | str,
        requested_thc: Decimal | str,
        speed: str,
    ) -> PythiaWalletSettlementQuote:
        if not earn_user_id or not wallet_address:
            raise PythiaQuoteError("wallet_link_required")
        if speed not in ("slow", "fast"):
            raise PythiaQuoteError("invalid_settlement_speed")
        available = _amount(cleared_available_thc, THC_SCALE)
        requested = _amount(requested_thc, THC_SCALE)
        if requested < self._min_thc:
            raise PythiaQuoteError("linked_wallet_minimum_not_met")
        if requested > available:
            raise PythiaQuoteError("insufficient_cleared_thc")

        quote = self._authority.quote_linked_wallet_settlement(
            earn_user_id=earn_user_id,
            wallet_address=wallet_address,
            thc_amount=requested,
            speed=speed,
        )
        self._validate(
            quote=quote,
            earn_user_id=earn_user_id,
            wallet_address=wallet_address,
            requested_thc=requested,
            speed=speed,
        )
        return quote

    def _validate(
        self,
        *,
        quote: PythiaWalletSettlementQuote,
        earn_user_id: str,
        wallet_address: str,
        requested_thc: Decimal,
        speed: str,
    ) -> None:
        now = int(self._now_fn())
        if (not quote.quote_id or not quote.attestation or not quote.policy_version
                or not quote.reserve_address):
            raise PythiaQuoteError("unattested_pythia_quote")
        if quote.earn_user_id != earn_user_id or quote.wallet_address != wallet_address:
            raise PythiaQuoteError("quote_identity_mismatch")
        if quote.speed != speed:
            raise PythiaQuoteError("quote_speed_mismatch")
        if _amount(quote.thc_amount, THC_SCALE) != requested_thc:
            raise PythiaQuoteError("quote_thc_amount_mismatch")
        gross = _amount(quote.gross_thr, THR_SCALE)
        try:
            fee = Decimal(str(quote.fee_thr)).quantize(THR_SCALE)
            if not fee.is_finite():
                raise ValueError
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise PythiaQuoteError("invalid_pythia_fee_quote") from exc
        net = _amount(quote.net_thr, THR_SCALE)
        if fee < 0 or gross <= fee or net != gross - fee:
            raise PythiaQuoteError("invalid_pythia_fee_quote")
        if quote.expires_at <= now or quote.expires_at > now + MAX_QUOTE_TTL_SECONDS:
            raise PythiaQuoteError("expired_or_unbounded_quote")
