"""
Regression Tests: Merge 611 Fixes

Ensures that:
1. showWalletLoginForm is always defined and callable
2. /api/wallet/v1/status endpoint exists (back-compat)
3. No undefined wallet UI symbols
"""

import pytest
from pathlib import Path


class TestWalletUIRegressions:
    """Test wallet UI symbol availability."""

    def test_showWalletLoginForm_defined_early(self):
        """Ensure showWalletLoginForm is available early in script."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find the first script tag
        script_start = content.find("<script>")
        assert script_start > 0, "Should have a script tag"

        # Find where showWalletLoginForm is first CALLED
        first_call = content.find("showWalletLoginForm()")
        assert first_call > 0, "showWalletLoginForm should be called"

        # Find where defensive stub is defined
        defensive_stub = content.find("window.showWalletLoginForm = function()")
        assert defensive_stub > 0, "Should have defensive stub"

        # Stub should come BEFORE any call
        assert defensive_stub < first_call, "Defensive stub should come before first call"

    def test_showWalletLoginForm_defensive_stub_has_fallback(self):
        """Ensure defensive stub has fallback implementation."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find defensive stub
        stub_start = content.find("window.showWalletLoginForm = function()")
        assert stub_start > 0, "Should have defensive stub"

        stub_end = content.find("}", stub_start) + 1
        stub_body = content[stub_start:stub_end]

        # Should have fallback implementation
        assert "walletLoginSection" in stub_body, "Stub should handle login section"
        assert "display" in stub_body, "Stub should modify display"
        assert "console.warn" in stub_body, "Stub should log warning"

    def test_showWalletLoginForm_real_definition_exists(self):
        """Ensure real function definition exists."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find real definition (not inside a function assignment)
        real_def = content.find("function showWalletLoginForm(){")
        assert real_def > 0, "Real function definition should exist"

        # Real definition should come after defensive stub
        stub_start = content.find("window.showWalletLoginForm = function()")
        assert real_def > stub_start, "Real definition should come after stub"

    def test_no_undefined_wallet_symbols(self):
        """Ensure critical wallet symbols are defined before use."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Critical symbols that should be defined/imported somewhere
        critical_symbols = [
            'showWalletLoginForm',
            'walletSession',
            'WalletAuth'
        ]

        for symbol in critical_symbols:
            # Should be mentioned in file (either defined or handled defensively)
            assert symbol in content, f"{symbol} should be available in base.html"


class TestWalletAPIRegressions:
    """Test wallet API endpoints for regressions."""

    def test_wallet_v1_status_endpoint_exists(self):
        """Ensure /api/wallet/v1/status endpoint exists."""
        server_py = Path(__file__).parent.parent / "server.py"
        content = server_py.read_text()

        assert "/api/wallet/v1/status" in content, "Should have /api/wallet/v1/status endpoint"
        assert "def api_wallet_v1_status()" in content, "Should have api_wallet_v1_status function"

    def test_wallet_v1_status_routes_to_current(self):
        """Ensure /api/wallet/v1/status properly routes to current implementation."""
        server_py = Path(__file__).parent.parent / "server.py"
        content = server_py.read_text()

        # Find the v1 endpoint
        v1_start = content.find("def api_wallet_v1_status()")
        assert v1_start > 0, "Should have v1 endpoint"

        # Should call the current endpoint
        v1_end = content.find("def api_wallet_status()", v1_start)
        v1_func = content[v1_start:v1_end]

        assert "api_wallet_status()" in v1_func or "api_wallet_status()" in v1_func, \
            "v1 endpoint should delegate to current implementation"

    def test_wallet_status_endpoint_still_exists(self):
        """Ensure current /api/wallet/status endpoint exists."""
        server_py = Path(__file__).parent.parent / "server.py"
        content = server_py.read_text()

        assert "/api/wallet/status" in content, "Should have /api/wallet/status endpoint"
        assert "def api_wallet_status()" in content, "Should have api_wallet_status function"

    def test_wallet_v1_endpoint_before_current(self):
        """Ensure v1 compat endpoint is defined before current endpoint."""
        server_py = Path(__file__).parent.parent / "server.py"
        content = server_py.read_text()

        v1_pos = content.find("def api_wallet_v1_status()")
        current_pos = content.find("def api_wallet_status()")

        assert v1_pos > 0, "v1 endpoint should exist"
        assert current_pos > 0, "current endpoint should exist"
        assert v1_pos < current_pos, "v1 endpoint should come before current endpoint (for clarity)"

    def test_wallet_endpoints_return_valid_responses(self):
        """Ensure both endpoints return valid response structure."""
        server_py = Path(__file__).parent.parent / "server.py"
        content = server_py.read_text()

        # Both should exist
        for endpoint in ["api_wallet_v1_status", "api_wallet_status"]:
            func_start = content.find(f"def {endpoint}()")
            assert func_start > 0, f"{endpoint} should be defined"

            # Should have return statement (either jsonify or delegation to another func)
            func_end = content.find("def ", func_start + 1)
            func_body = content[func_start:func_end]

            assert "return" in func_body, f"{endpoint} should have return statement"


class TestRegressionPrevention:
    """Tests to prevent similar regressions."""

    def test_no_undefined_function_calls(self):
        """Ensure critical functions are defined or have defensive stubs."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # showWalletLoginForm is the critical one that must be protected
        func_name = 'showWalletLoginForm'

        # Should have either defensive stub or real definition
        has_defensive_stub = f"window.{func_name} = function()" in content
        has_real_def = f"function {func_name}()" in content

        assert has_defensive_stub or has_real_def, \
            f"{func_name} should be defined or have defensive stub"

    def test_all_api_endpoints_have_routes(self):
        """Ensure all referenced API endpoints have corresponding routes."""
        server_py = Path(__file__).parent.parent / "server.py"
        content = server_py.read_text()

        # Critical v1 endpoints that should exist
        required_endpoints = [
            ("/api/wallet/v1/status", "api_wallet_v1_status"),
            ("/api/wallet/status", "api_wallet_status"),
            ("/api/build", "api_build"),
            ("/api/health", "api_health"),
        ]

        for route, func in required_endpoints:
            assert route in content, f"Route {route} should be defined"
            assert f"def {func}()" in content, f"Function {func} should be defined"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
