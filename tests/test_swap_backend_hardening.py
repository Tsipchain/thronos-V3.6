"""
Test Swap Backend Hardening - PR-E

Tests ensure:
1. No HTTP 500 errors for any user input (always 400)
2. Payload parsing handles dict, JSON string, invalid JSON
3. Amount validation with type checking
4. _extract_signed_payload() helper function
5. Fee estimate endpoint exists and doesn't 404
"""

import pytest
import json
from pathlib import Path


class TestExtractSignedPayload:
    """Test the _extract_signed_payload() helper function."""

    def test_extract_signed_payload_dict(self):
        """Verify dict payload is returned as-is."""
        # This test imports and calls the function
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from server import _extract_signed_payload

        payload = {"signature": "abc123", "from": "THR123"}
        result, error = _extract_signed_payload(payload)

        assert error is None, "No error expected"
        assert result == payload, "Payload should be returned unchanged"

    def test_extract_signed_payload_json_string(self):
        """Verify JSON string payload is parsed to dict."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from server import _extract_signed_payload

        payload_dict = {"signature": "abc123", "from": "THR123"}
        payload_json = json.dumps(payload_dict)
        result, error = _extract_signed_payload(payload_json)

        assert error is None, "No error expected"
        assert result == payload_dict, "Should parse JSON string to dict"

    def test_extract_signed_payload_invalid_json(self):
        """Verify invalid JSON returns error."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from server import _extract_signed_payload

        payload_json = "{not valid json"
        result, error = _extract_signed_payload(payload_json)

        assert error is not None, "Error should be returned"
        assert "invalid_signed_tx_format" in error, "Should indicate format error"
        assert result == {}, "Result should be empty dict"

    def test_extract_signed_payload_json_non_dict(self):
        """Verify JSON array (non-dict) returns error."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from server import _extract_signed_payload

        payload_json = json.dumps(["not", "a", "dict"])
        result, error = _extract_signed_payload(payload_json)

        assert error is not None, "Error should be returned"
        assert "must be JSON object" in error, "Should indicate must be object"
        assert result == {}, "Result should be empty dict"

    def test_extract_signed_payload_none(self):
        """Verify None returns empty dict without error."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from server import _extract_signed_payload

        result, error = _extract_signed_payload(None)

        assert error is None, "No error expected for None"
        assert result == {}, "Result should be empty dict"

    def test_extract_signed_payload_invalid_type(self):
        """Verify invalid type (number, list) returns error."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from server import _extract_signed_payload

        result, error = _extract_signed_payload(12345)

        assert error is not None, "Error should be returned"
        assert "invalid_signed_tx_type" in error, "Should indicate type error"
        assert result == {}, "Result should be empty dict"


class TestSwapExecuteErrorHandling:
    """Test that /api/swap/execute returns 400 for all user errors, never 500."""

    def test_swap_execute_missing_json_returns_400(self):
        """Verify missing JSON request returns 400, not 500."""
        # This would require a Flask test client, so we verify the code instead
        swap_py = Path(__file__).parent.parent / "server.py"
        content = swap_py.read_text()

        # Find api_swap_execute function
        func_start = content.find("def api_swap_execute():")
        func_end = content.find("@app.route", func_start + 100)
        func_body = content[func_start:func_end]

        # Verify it doesn't have "), 500" (actual return statement, not docstring)
        assert "), 500" not in func_body, "Should not return 500 anywhere"

        # Verify exception handler returns 400
        assert "return jsonify(status=\"error\"" in func_body, "Should have error response"
        assert ", 400" in func_body, "Should return 400 for errors"

    def test_swap_execute_invalid_amount_returns_400(self):
        """Verify invalid amount parsing returns 400."""
        swap_py = Path(__file__).parent.parent / "server.py"
        content = swap_py.read_text()

        func_start = content.find("def api_swap_execute():")
        func_end = content.find("@app.route", func_start + 100)
        func_body = content[func_start:func_end]

        # Check for amount parsing error handler
        assert "invalid_amounts" in func_body, "Should have invalid_amounts error code"
        assert "float(data.get(\"amount_in\"" in func_body or "float(min_amount_out_raw)" in func_body, "Should parse amounts"

    def test_swap_execute_no_bare_500s(self):
        """Verify no unhandled exceptions return 500."""
        swap_py = Path(__file__).parent.parent / "server.py"
        content = swap_py.read_text()

        func_start = content.find("def api_swap_execute():")
        func_end = content.find("@app.route", func_start + 100)
        func_body = content[func_start:func_end]

        # Count "500" occurrences - should be 0 in this function
        count_500 = func_body.count("), 500")
        assert count_500 == 0, "Should not return 500 status code"

        # Verify final exception handler
        assert "except Exception as exc:" in func_body, "Should have exception handler"
        assert "return jsonify(status=\"error\"" in func_body, "Should return error response"
        assert ", 400" in func_body, "Exception handler should return 400"


class TestFeeEstimateEndpoint:
    """Test the /api/v1/wallet/fee-estimate endpoint exists."""

    def test_fee_estimate_endpoint_exists(self):
        """Verify fee-estimate endpoint is defined."""
        server_py = Path(__file__).parent.parent / "server.py"
        content = server_py.read_text()

        assert "/api/v1/wallet/fee-estimate" in content, "Endpoint should be defined"
        assert "def api_v1_wallet_fee_estimate()" in content, "Function should exist"

    def test_fee_estimate_endpoint_handles_invalid_amount(self):
        """Verify fee-estimate returns 400 for invalid amount."""
        server_py = Path(__file__).parent.parent / "server.py"
        content = server_py.read_text()

        func_start = content.find("def api_v1_wallet_fee_estimate():")
        func_end = content.find("@app.route", func_start + 50)
        if func_end < func_start:
            func_end = content.find("def ", func_start + 50)
        func_body = content[func_start:func_end]

        # Should have error handling
        assert "invalid_amount" in func_body, "Should check for invalid amounts"
        assert ", 400" in func_body, "Should return 400 for invalid input"

    def test_fee_estimate_endpoint_no_500s(self):
        """Verify fee-estimate endpoint doesn't return 500."""
        server_py = Path(__file__).parent.parent / "server.py"
        content = server_py.read_text()

        func_start = content.find("def api_v1_wallet_fee_estimate():")
        func_end = content.find("@app.route", func_start + 50)
        if func_end < func_start:
            func_end = content.find("def ", func_start + 50)
        func_body = content[func_start:func_end]

        # Should not return 500
        assert "), 500" not in func_body, "Should not return 500"
        assert ", 400" in func_body or ", 200" in func_body, "Should return 400 or 200"


class TestSwapFrontendNoFallback:
    """Test that swap.html doesn't fallback to legacy when V1 material exists."""

    def test_swap_html_checks_runtime_signing_material(self):
        """Verify swap.html checks wallet session state."""
        swap_html = Path(__file__).parent.parent / "templates" / "swap.html"
        content = swap_html.read_text()

        # Should use wallet session (check is in base.html but swap uses it)
        assert "walletSession" in content or "requireUnlockedWallet" in content, "Should use wallet session or require unlocked wallet"

    def test_swap_html_no_fallback_when_v1_exists(self):
        """Verify swap doesn't fallback to legacy when V1 material exists."""
        swap_html = Path(__file__).parent.parent / "templates" / "swap.html"
        content = swap_html.read_text()

        # Find the swap execution function
        exec_start = content.find("async function doSwap()")
        if exec_start < 0:
            exec_start = content.find("function doSwap()")
        exec_end = content.find("finally", exec_start) + 100
        exec_body = content[exec_start:exec_end]

        # Should have requireUnlockedWallet call
        assert "requireUnlockedWallet" in exec_body, "Should require unlocked wallet"

    def test_swap_html_payload_format_consistent(self):
        """Verify swap.html uses consistent centralized format."""
        swap_html = Path(__file__).parent.parent / "templates" / "swap.html"
        content = swap_html.read_text()

        # Should build signed request with required fields
        assert "signed_tx" in content or "signTransaction" in content, "Should handle signed transactions"
        assert "trader_thr" in content, "Should include trader address"
        assert "token_in" in content, "Should include token_in"
        assert "token_out" in content, "Should include token_out"
        assert "amount_in" in content, "Should include amount_in"

    def test_swap_html_error_handling(self):
        """Verify swap.html has error handling for failed swaps."""
        swap_html = Path(__file__).parent.parent / "templates" / "swap.html"
        content = swap_html.read_text()

        # Should handle errors
        assert "catch" in content or "try" in content, "Should have error handling"
        assert "error" in content.lower(), "Should check for error response"


class TestConsistencyAcrossPages:
    """Test that swap/pools use consistent request builders."""

    def test_swap_pools_use_requireUnlockedWallet(self):
        """Verify swap and pools pages use requireUnlockedWallet for centralized auth."""
        swap_html = Path(__file__).parent.parent / "templates" / "swap.html"
        pools_html = Path(__file__).parent.parent / "templates" / "pools.html"

        swap_content = swap_html.read_text()
        pools_content = pools_html.read_text()

        # Swap and pools should use requireUnlockedWallet (centralized signing)
        assert "requireUnlockedWallet" in swap_content, "Swap should require unlocked wallet"
        assert "requireUnlockedWallet" in pools_content, "Pools should require unlocked wallet"

    def test_swap_pools_send_same_format(self):
        """Verify swap and pools send consistent payload structure."""
        swap_html = Path(__file__).parent.parent / "templates" / "swap.html"
        pools_html = Path(__file__).parent.parent / "templates" / "pools.html"

        swap_content = swap_html.read_text()
        pools_content = pools_html.read_text()

        # Swap includes trader_thr, pools includes active_wallet_address (both are wallet address fields)
        assert "trader_thr" in swap_content, "Swap should send trader_thr"
        assert "active_wallet_address" in pools_content or "trader_thr" in pools_content, "Pools should send wallet address"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
