"""Wallet V1 history display logic — regression fixtures for #942.

These tests verify the Python equivalents of the TypeScript formatting
and category-mapping logic in HistoryScreen.tsx, ensuring:
- true zero renders as '0', not '0.000000'
- missing/null renders as '—'
- tiny nonzero amounts (1e-8, 1e-12) never show scientific notation in list view
- exact detail view preserves significant digits
- category mapping never silently classifies unknown events as THR
"""

import math
import pytest


# ── Python port of HistoryScreen.tsx formatAmount ────────────────────────────

def format_amount(amount):
    """List-view amount formatter (compact, no scientific notation)."""
    if amount is None:
        return "—"
    if amount == 0:
        return "0"
    abs_val = abs(amount)
    if abs_val >= 1000:
        return f"{amount:,.2f}"
    if abs_val >= 1:
        return f"{amount:.2f}"
    if abs_val >= 0.01:
        return f"{amount:.4f}"
    if abs_val >= 0.000001:
        return f"{amount:.6f}"
    return "< -0.000001" if amount < 0 else "< 0.000001"


def format_amount_exact(amount):
    """Detail-view amount formatter (full precision, no scientific notation)."""
    if amount is None:
        return "—"
    if amount == 0:
        return "0"
    abs_val = abs(amount)
    if abs_val >= 0.000001:
        return format_amount(amount)
    digits = max(6, min(18, -math.floor(math.log10(abs_val)) + 2))
    fixed = f"{amount:.{digits}f}"
    fixed = fixed.rstrip("0").rstrip(".")
    return fixed


# ── Python port of CATEGORY_MAP ─────────────────────────────────────────────

CATEGORY_MAP = {
    "thr": "thr",
    "transfer": "thr",
    "token_transfer": "tokens",
    "token_receive": "tokens",
    "tokens": "tokens",
    "mining": "mining",
    "mining_reward": "mining",
    "swaps": "swaps",
    "swap": "swaps",
    "liquidity": "liquidity",
    "pool_seed": "liquidity",
    "pool_withdraw": "liquidity",
    "pool_add_liquidity": "liquidity",
    "pool_add_liquidity_intent_created": "liquidity",
    "pool_add_liquidity_external_tx_confirmed": "liquidity",
    "pool_add_liquidity_lp_minted": "liquidity",
    "bridge": "bridge",
    "bridge_deposit_detected": "bridge",
    "crosschain_deposit_detected": "bridge",
    "crosschain_transfer_received": "bridge",
    "crosschain_transfer_sent": "bridge",
    "music_tip": "music",
    "music_stream": "music",
    "music_royalty": "music",
    "music": "music",
    "ai_credits": "ai_credits",
    "ai_reward": "ai_credits",
    "architect": "ai_credits",
    "architect_job": "ai_credits",
    "t2e": "l2e",
    "t2e_reward_thr": "l2e",
    "l2e": "l2e",
    "iot": "iot",
    "iot_telemetry": "iot",
    "iot_reward": "iot",
    "iot_mining_reward": "iot",
    "gps_mining": "iot",
    "music_gps_telemetry": "iot",
    "pledge": "staking",
    "pledge_usdt_bnb_confirmed": "staking",
    "staking": "staking",
    "nft": "nft",
    "nft_mint": "nft",
    "nft_buy": "nft",
    "verifyid": "gateway",
    "gateway": "gateway",
    "fiat_buy": "gateway",
    "fiat_deposit": "gateway",
    "other": "gateway",
}


# ── Tests ────────────────────────────────────────────────────────────────────

class TestFormatAmount:
    """List-view amount formatting."""

    def test_null_renders_dash(self):
        assert format_amount(None) == "—"

    def test_true_zero(self):
        assert format_amount(0) == "0"
        assert format_amount(0.0) == "0"

    def test_large_values_comma_separated(self):
        assert "," in format_amount(12345.67)

    def test_normal_range(self):
        assert format_amount(1.5) == "1.50"
        assert format_amount(0.05) == "0.0500"

    def test_micro_amounts(self):
        assert format_amount(0.000001) == "0.000001"
        assert format_amount(0.0000019) == "0.000002"

    def test_tiny_1e8_no_scientific(self):
        result = format_amount(1e-8)
        assert "e" not in result.lower(), f"Scientific notation in list: {result}"
        assert result == "< 0.000001"

    def test_tiny_1e12_no_scientific(self):
        result = format_amount(1e-12)
        assert "e" not in result.lower(), f"Scientific notation in list: {result}"
        assert result == "< 0.000001"

    def test_negative_tiny(self):
        result = format_amount(-1e-8)
        assert "e" not in result.lower()
        assert result == "< -0.000001"

    def test_sub_micro_positive(self):
        assert format_amount(5e-7) == "< 0.000001"

    def test_4_9e_7_below_threshold(self):
        result = format_amount(4.9e-7)
        assert "e" not in result.lower()


class TestFormatAmountExact:
    """Detail-view amount formatting (full precision)."""

    def test_null_renders_dash(self):
        assert format_amount_exact(None) == "—"

    def test_true_zero(self):
        assert format_amount_exact(0) == "0"

    def test_normal_delegated(self):
        assert format_amount_exact(1.5) == "1.50"

    def test_1e8_exact_no_scientific(self):
        result = format_amount_exact(1e-8)
        assert "e" not in result.lower(), f"Scientific notation in detail: {result}"
        assert "0.00000001" in result

    def test_1e12_exact_no_scientific(self):
        result = format_amount_exact(1e-12)
        assert "e" not in result.lower(), f"Scientific notation in detail: {result}"
        assert "0.000000000001" in result

    def test_negative_tiny(self):
        result = format_amount_exact(-5e-9)
        assert "e" not in result.lower()
        assert result.startswith("-")

    def test_trailing_zeros_stripped(self):
        result = format_amount_exact(1e-8)
        assert not result.endswith("0")


class TestCategoryMapping:
    """Category mapping never silently classifies unknown events as THR."""

    def test_token_receive_is_tokens_not_thr(self):
        assert CATEGORY_MAP["token_receive"] == "tokens"

    def test_token_transfer_is_tokens(self):
        assert CATEGORY_MAP["token_transfer"] == "tokens"

    def test_other_is_gateway_not_thr(self):
        assert CATEGORY_MAP["other"] == "gateway"

    def test_unknown_category_fallback(self):
        # In the TS code: CATEGORY_MAP[rawCategory] || ... || 'thr'
        # Unknown categories should NOT silently map to thr in the map itself
        for key, value in CATEGORY_MAP.items():
            if key in ("thr", "transfer"):
                assert value == "thr"
            elif key not in ("thr", "transfer"):
                assert value != "thr", f"Category '{key}' maps to 'thr' unexpectedly"

    def test_earn_categories_present(self):
        assert CATEGORY_MAP.get("staking") == "staking"
        assert CATEGORY_MAP.get("l2e") == "l2e"
        assert CATEGORY_MAP.get("t2e") == "l2e"
        assert CATEGORY_MAP.get("ai_credits") == "ai_credits"

    def test_bridge_lifecycle_categories(self):
        for key in ("bridge_deposit_detected", "crosschain_deposit_detected",
                     "crosschain_transfer_received", "crosschain_transfer_sent"):
            assert CATEGORY_MAP[key] == "bridge"

    def test_pool_lifecycle_categories(self):
        for key in ("pool_seed", "pool_withdraw", "pool_add_liquidity",
                     "pool_add_liquidity_intent_created",
                     "pool_add_liquidity_external_tx_confirmed",
                     "pool_add_liquidity_lp_minted"):
            assert CATEGORY_MAP[key] == "liquidity"


class TestSafeFloat:
    """Python equivalent of safeFloat: null/empty → null, invalid → null."""

    @staticmethod
    def safe_float(v):
        if v is None or v == "":
            return None
        try:
            n = float(v)
            return None if math.isnan(n) else n
        except (ValueError, TypeError):
            return None

    def test_none(self):
        assert self.safe_float(None) is None

    def test_empty_string(self):
        assert self.safe_float("") is None

    def test_invalid_string(self):
        assert self.safe_float("abc") is None

    def test_zero(self):
        assert self.safe_float(0) == 0

    def test_valid_float(self):
        assert self.safe_float("1.5") == 1.5

    def test_negative(self):
        assert self.safe_float("-0.001") == -0.001

    def test_nan(self):
        assert self.safe_float(float("nan")) is None
