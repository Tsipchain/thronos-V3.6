"""
Regression Tests: Wallet Status Address Parameter

Ensures that:
1. /api/wallet/v1/status is never called without address parameter
2. Frontend gracefully handles missing active address (safe default)
3. Widget shows recovery/pledge options even without active address
"""

import pytest
from pathlib import Path


class TestWalletStatusAddressParameter:
    """Test that /api/wallet/v1/status always receives address parameter."""

    def test_fetch_wallet_status_helper_exists(self):
        """Ensure fetchWalletStatusWithAddress helper function exists."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert "function fetchWalletStatusWithAddress" in content or \
               "const fetchWalletStatusWithAddress" in content or \
               "fetchWalletStatusWithAddress = function" in content, \
            "Helper function fetchWalletStatusWithAddress should exist"

    def test_fetch_helper_includes_address_parameter(self):
        """Verify helper includes address in query string."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Should have address encoding somewhere in the helper
        assert "encodeURIComponent(activeAddr)" in content, \
            "Helper should include address parameter in query string"

        # Verify the pattern is for wallet/v1/status
        assert "/api/wallet/v1/status?address=" in content, \
            "Should call /api/wallet/v1/status with address query parameter"

    def test_fetch_helper_checks_active_address(self):
        """Verify helper checks if active address exists before calling."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find helper function
        func_start = content.find("function fetchWalletStatusWithAddress")
        if func_start < 0:
            func_start = content.find("const fetchWalletStatusWithAddress")
        assert func_start > 0, "Helper function should be defined"

        func_end = content.find("}", func_start) + 1
        func_body = content[func_start:func_end]

        # Should check if address exists
        assert "activeAddr" in func_body or "getAddress()" in func_body, \
            "Helper should check for active address"

        # Should handle missing address gracefully
        assert "!activeAddr" in func_body or "if (!activeAddr)" in func_body, \
            "Helper should handle missing address"

    def test_dom_content_loaded_uses_helper(self):
        """Verify wallet initialization uses the helper function."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Verify the helper function is called somewhere during wallet initialization
        assert "fetchWalletStatusWithAddress" in content, \
            "Helper function should be called for wallet status initialization"

        # Should NOT have direct bare /api/wallet/v1/status calls (without address)
        # Count occurrences - we'll search for the pattern more carefully
        import re
        # Look for fetch to /api/wallet/v1/status NOT followed by ?address=
        bad_pattern = re.compile(r"fetch\(['\"]\/api\/wallet\/v1\/status['\"]\)")
        matches = bad_pattern.findall(content)
        assert len(matches) == 0, \
            "Should not fetch endpoint directly without address parameter"

    def test_modal_open_uses_helper(self):
        """Verify wallet modal open handler uses the helper function."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find openHeaderWalletModal override
        override_start = content.find("window.openHeaderWalletModal = async function")
        assert override_start > 0, "openHeaderWalletModal override should exist"

        # Get function body
        override_end = content.find("};", override_start) + 2
        func_body = content[override_start:override_end]

        # Should use helper
        assert "fetchWalletStatusWithAddress" in func_body, \
            "Modal open handler should use fetchWalletStatusWithAddress helper"

        # Should NOT call endpoint directly
        assert "fetch('/api/wallet/v1/status')" not in func_body, \
            "Modal open should not fetch endpoint directly without address"

    def test_mode_switch_uses_helper(self):
        """Verify wallet mode switch handler uses the helper function."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find switchWalletV1Mode override
        override_start = content.find("window.switchWalletV1Mode = function")
        assert override_start > 0, "switchWalletV1Mode override should exist"

        # Get function body (approximately)
        override_end = content.find("return result;", override_start) + 15
        func_body = content[override_start:override_end]

        # Should use helper
        assert "fetchWalletStatusWithAddress" in func_body, \
            "Mode switch should use fetchWalletStatusWithAddress helper"

        # Should NOT call endpoint directly
        assert "fetch('/api/wallet/v1/status')" not in func_body, \
            "Mode switch should not fetch endpoint directly"

    def test_no_bare_endpoint_calls_without_address(self):
        """Ensure endpoint is never called without address parameter in code."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Search for problematic patterns: direct fetch to endpoint without query
        bad_patterns = [
            "fetch('/api/wallet/v1/status')",
            'fetch("/api/wallet/v1/status")',
        ]

        for pattern in bad_patterns:
            # Count occurrences - should be 0 for bare calls (only in helper is OK)
            count = 0
            for match_idx in range(len(content)):
                if content[match_idx:].startswith(pattern):
                    # Check if it's in the helper function (should have address parameter after)
                    after_pattern = content[match_idx + len(pattern):match_idx + len(pattern) + 50]
                    if "?address=" not in after_pattern:
                        count += 1

            assert count == 0, f"Found {count} direct calls to endpoint without address: {pattern}"


class TestWalletStatusEndpointBackCompat:
    """Test that endpoint handles missing address gracefully."""

    def test_wallet_v1_status_endpoint_exists(self):
        """Ensure /api/wallet/v1/status endpoint is defined."""
        server_py = Path(__file__).parent.parent / "server.py"
        content = server_py.read_text()

        assert "/api/wallet/v1/status" in content, "Should have /api/wallet/v1/status endpoint"
        assert "def api_wallet_v1_status()" in content, "Should have api_wallet_v1_status function"

    def test_endpoint_delegates_to_current(self):
        """Verify v1 endpoint properly delegates to current implementation."""
        server_py = Path(__file__).parent.parent / "server.py"
        content = server_py.read_text()

        # Find v1 endpoint
        v1_start = content.find("def api_wallet_v1_status()")
        assert v1_start > 0, "v1 endpoint should exist"

        # Find next function
        v1_end = content.find("def ", v1_start + 1)
        v1_body = content[v1_start:v1_end]

        # Should delegate to current endpoint
        assert "api_wallet_status()" in v1_body, \
            "v1 endpoint should delegate to api_wallet_status()"

    def test_endpoint_requires_address_parameter(self):
        """Verify endpoint properly validates address parameter."""
        server_py = Path(__file__).parent.parent / "server.py"
        content = server_py.read_text()

        # Find api_wallet_status function
        func_start = content.find("def api_wallet_status()")
        assert func_start > 0, "api_wallet_status should be defined"

        # Find function body
        func_end = content.find("def ", func_start + 1)
        func_body = content[func_start:func_end]

        # Should check for address parameter
        assert "request.args.get" in func_body and "address" in func_body, \
            "Should read address from query parameters"

        # Should return error if missing
        assert "Missing address parameter" in func_body, \
            "Should return clear error when address missing"

        # Should return 400 for missing address
        assert ", 400" in func_body, "Should return HTTP 400 for missing address"


class TestWalletUIRecoveryOptions:
    """Test that wallet UI shows recovery/pledge options even without address."""

    def test_wallet_modal_shows_options_initialization(self):
        """Verify wallet modal initializes even without active address."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Should have safe defaults that work without address
        assert "recovery" in content.lower() or "Recovery" in content, \
            "UI should reference recovery flow"

        assert "pledge" in content.lower() or "Pledge" in content, \
            "UI should reference pledge flow"

    def test_wallet_session_has_address_getter(self):
        """Verify wallet_session.js has getAddress method."""
        wallet_session = Path(__file__).parent.parent / "static" / "wallet_session.js"
        content = wallet_session.read_text()

        assert "getAddress" in content, "wallet_session should have getAddress method"

    def test_safe_default_when_no_address(self):
        """Verify frontend uses safe default when no active address."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Check helper function handles null/undefined address
        helper_start = content.find("function fetchWalletStatusWithAddress")
        if helper_start < 0:
            helper_start = content.find("const fetchWalletStatusWithAddress")
        assert helper_start > 0, "Helper should exist"

        helper_end = content.find("}", helper_start) + 1
        helper_body = content[helper_start:helper_end]

        # Should return safe default
        assert "legacy_repair_ui_enabled: false" in helper_body or \
               "ok: false" in helper_body, \
            "Should return safe default (production mode) when no address"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
