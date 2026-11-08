"""Exact, accounting-only allocation of verified provider revenue.

Amounts here are USD claims, not funded THC transfers or BTC settlement.
"""

from decimal import Decimal, InvalidOperation


def allocate_timewall_revenue(revenue_raw: str) -> dict[str, str]:
    try:
        gross = Decimal(str(revenue_raw))
        if not gross.is_finite() or gross <= 0:
            raise ValueError("invalid revenue")
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("invalid TimeWall revenue") from exc

    player = gross * Decimal("0.65")
    referral_cap = gross * Decimal("0.05")
    platform_before_referrals = gross - player
    platform_after_full_referrals = platform_before_referrals - referral_cap
    return {
        "provider_revenue_usd": str(gross),
        "player_share_usd": str(player),
        "referral_cap_usd": str(referral_cap),
        "platform_before_referrals_usd": str(platform_before_referrals),
        "platform_after_full_referrals_usd": str(platform_after_full_referrals),
    }
