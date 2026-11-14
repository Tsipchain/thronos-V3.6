"""Read-only Earn THC→THR readiness check bound to the saved wallet link.

This is NOT payout execution: does not reserve THC, debit any ledger, sign,
broadcast, or claim a treasury balance. A short-lived, attested Pythia quote
is necessary but never sufficient for a real transaction.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, Any

from services.pythia_wallet_settlement_quote import (
    LinkedWalletSettlementQuoteGate, PythiaWalletSettlementQuote,
    PythiaQuoteAuthority, PythiaQuoteError,
)


class EarnWalletPreflightStore(Protocol):
    def wallet_link_for_user(self, earn_user_id: str) -> dict[str, str] | None:
        ...

    def thc_balance(self, earn_user_id: str) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class LinkedWalletPreflight:
    quote: PythiaWalletSettlementQuote
    available_thc: str
    wallet_address: str
    status: str = "device_approval_and_treasury_verification_required"

    def public_dict(self) -> dict[str, str | int]:
        return {
            **self.quote.public_dict(),
            "available_thc": self.available_thc,
            "status": self.status,
        }


def prepare_linked_wallet_redemption(
    store: EarnWalletPreflightStore,
    authority: PythiaQuoteAuthority,
    *,
    earn_user_id: str,
    requested_thc: Decimal | str,
    speed: str,
    now_fn=None,
) -> LinkedWalletPreflight:
    """Require a persisted wallet link and authoritative *available* cleared THC.

    Never accept a browser-selected destination wallet or browser balance.
    The eventual executor still needs device approval, atomic reservation,
    sufficient THR treasury reserve, broadcast proof, and reconciliation.
    """
    if not earn_user_id or store is None or authority is None:
        raise PythiaQuoteError("missing_earn_authority")
    link = store.wallet_link_for_user(earn_user_id)
    wallet = (link or {}).get("wallet_address", "").strip()
    if not wallet:
        raise PythiaQuoteError("wallet_link_required")
    balance = store.thc_balance(earn_user_id)
    if not isinstance(balance, dict) or "available" not in balance:
        raise PythiaQuoteError("cleared_balance_unavailable")
    kwargs = {"now_fn": now_fn} if now_fn is not None else {}
    quote = LinkedWalletSettlementQuoteGate(authority, **kwargs).issue(
        earn_user_id=earn_user_id,
        wallet_address=wallet,
        cleared_available_thc=balance["available"],
        requested_thc=requested_thc,
        speed=speed,
    )
    return LinkedWalletPreflight(
        quote=quote,
        available_thc=str(Decimal(str(balance["available"]))),
        wallet_address=wallet,
    )
