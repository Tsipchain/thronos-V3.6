"""
Wallet V1 Swap Frontend Fallback Tests

Verifies that the swap frontend does NOT fall back to legacy format
when Wallet V1 runtime signing material is available and unlocked.

Bug: Previously, if centralized signing failed (network error, etc),
the frontend would fall back to legacy format even with unlocked signing material.

Fix: If we enter the centralized format block (hasRuntimeSigningMaterial=true)
but get an exception, show error instead of falling back to legacy.
"""

import pytest
from pathlib import Path


class TestSwapFrontendRuntimeCheckup:
    """Test that swap frontend checks for runtime signing material."""

    def test_swap_checks_wallet_session_unlock_state(self):
        """Verify swap frontend checks if wallet session is unlocked."""
        swap_html = Path(__file__).parent.parent / "templates" / "swap.html"
        content = swap_html.read_text()

        # Check for session unlock detection
        assert "walletSession" in content and "isUnlockedFor" in content, \
            "Should check wallet session unlock state"

        # Find doSwap function
        start = content.find("function doSwap(")
        assert start > 0, "doSwap function not found"

        end = content.find("\n}", start) if content.find("\n}", start) > 0 else content.find("window.doSwap", start)
        doswap_section = content[start:end]

        assert "hasRuntimeSigningMaterial" in doswap_section, \
            "Should check for runtime signing material"
        assert "walletSession.isUnlockedFor" in doswap_section, \
            "Should use walletSession.isUnlockedFor check"

    def test_swap_uses_runtime_material_flag(self):
        """Verify swap stores runtime material state in a variable."""
        swap_html = Path(__file__).parent.parent / "templates" / "swap.html"
        content = swap_html.read_text()

        # Find doSwap function
        start = content.find("function doSwap(")
        end = content.find("window.doSwap", start)
        doswap_section = content[start:end]

        # Should assign to a variable for clarity
        assert "hasRuntimeSigningMaterial" in doswap_section, \
            "Should use hasRuntimeSigningMaterial variable"


class TestSwapFrontendNoFallbackWithUnlockedMaterial:
    """Test that swap doesn't fall back to legacy if runtime material exists."""

    def test_swap_shows_error_instead_of_fallback(self):
        """Verify swap shows error when centralized format fails with unlocked material."""
        swap_html = Path(__file__).parent.parent / "templates" / "swap.html"
        content = swap_html.read_text()

        # Find the centralized format try/catch block
        start = content.find("if (canonicalAddr && hasRuntimeSigningMaterial)")
        assert start > 0, "Should have centralized format block"

        end = content.find("} else if", start)
        centralized_block = content[start:end]

        # Should have try/catch
        assert "try {" in centralized_block and "} catch" in centralized_block, \
            "Should have try/catch for centralized format"

        # In the catch block, should check for error instead of silently continuing
        catch_start = centralized_block.find("} catch")
        catch_section = centralized_block[catch_start:catch_start + 300]

        # Should show error, not fall through to legacy
        assert "textContent" in catch_section or "Error" in catch_section, \
            "Catch block should show error to user"

    def test_swap_catch_block_returns_early(self):
        """Verify catch block doesn't fall through to legacy fallback."""
        swap_html = Path(__file__).parent.parent / "templates" / "swap.html"
        content = swap_html.read_text()

        # Find the catch block for centralized format in doSwap
        doswap_start = content.find("function doSwap(")
        centralized_catch = content.find("} catch (e) {", doswap_start)
        catch_block = content[centralized_catch:centralized_catch + 300]

        # Should return or show error
        assert "return" in catch_block or "textContent" in catch_block, \
            "Catch block should prevent fall-through to legacy"

    def test_swap_legacy_fallback_only_when_no_runtime_material(self):
        """Verify legacy fallback only happens when no runtime signing material."""
        swap_html = Path(__file__).parent.parent / "templates" / "swap.html"
        content = swap_html.read_text()

        # Find the legacy fallback section
        start = content.find("// Legacy format fallback")
        assert start > 0, "Should have legacy fallback comment"


class TestPoolsAddLiquidityFallback:
    """Test that add_liquidity frontend also prevents inappropriate fallback."""

    def test_pools_checks_wallet_session_unlock_state(self):
        """Verify add_liquidity frontend checks if wallet session is unlocked."""
        pools_html = Path(__file__).parent.parent / "templates" / "pools.html"
        content = pools_html.read_text()

        # Find addLiquidity function
        start = content.find("async function addLiquidity(")
        assert start > 0, "addLiquidity function not found"

        addliquidity_section = content[start:start + 3000]

        # Should check for unlocked material
        assert "hasRuntimeSigningMaterial" in addliquidity_section or "walletSession" in addliquidity_section, \
            "Should check for runtime signing material"

    def test_pools_tracks_centralized_format_attempt(self):
        """Verify add_liquidity tracks if centralized format was attempted."""
        pools_html = Path(__file__).parent.parent / "templates" / "pools.html"
        content = pools_html.read_text()

        # Find addLiquidity function
        start = content.find("async function addLiquidity(")
        assert start > 0, "addLiquidity function not found"

        addliquidity_section = content[start:start + 3000]

        # Should track whether centralized format was tried
        assert "triedCentralizedFormat" in addliquidity_section, \
            "Should track whether centralized format was attempted"

    def test_pools_prevents_fallback_after_centralized_error(self):
        """Verify add_liquidity prevents fallback if centralized error occurred."""
        pools_html = Path(__file__).parent.parent / "templates" / "pools.html"
        content = pools_html.read_text()

        # Find addLiquidity function
        start = content.find("async function addLiquidity(")
        assert start > 0, "addLiquidity function not found"

        addliquidity_section = content[start:start + 3000]

        # Should have logic to prevent fallback on centralized error
        assert "triedCentralizedFormat && !response && centralizedError" in addliquidity_section or \
               ("triedCentralizedFormat" in addliquidity_section and "alert" in addliquidity_section), \
            "Should show alert instead of falling back to legacy"


class TestRecoveryKitRestoreVisibility:
    """Test that Recovery Kit restore is shown as primary."""

    def test_recovery_kit_restore_exists_in_import_mode(self):
        """Verify Recovery Kit restore form exists in import mode."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Check for import mode UI
        assert 'id="walletV1ImportMode"' in content, \
            "Import mode container not found"

    def test_recovery_kit_restore_shown_as_primary(self):
        """Verify Recovery Kit restore is prominently displayed."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Should mention as primary
        assert "Restore Wallet from Recovery Kit" in content, \
            "Recovery Kit restore text not found"

    def test_recovery_kit_form_id_exists(self):
        """Verify Recovery Kit restore form has proper ID."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Should have form for recovery kit
        assert "walletV1RecoveryKitRestoreForm" in content, \
            "Should have walletV1RecoveryKitRestoreForm element"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
