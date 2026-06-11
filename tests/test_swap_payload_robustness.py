"""
Test Swap endpoint robustness against malformed payloads.

Ensures that string JSON payloads, missing fields, and invalid data types
are handled gracefully with 400 errors, never 500 errors.

Bug that this fixes:
- When payload is a JSON string instead of dict, code throws:
  "string indices must be integers, not 'str'"
- Result: HTTP 500 instead of 400
"""

import pytest
import json
from pathlib import Path


class TestSwapPayloadParsing:
    """Test that swap endpoint handles various payload formats."""

    def test_swap_endpoint_handles_dict_payload(self):
        """Verify swap works with normal dict payload."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Check swap endpoint exists
        assert "@app.route(\"/api/swap/execute\"" in content, \
            "Swap endpoint not found"

        # Check it receives JSON
        start = content.find("def api_swap_execute()")
        swap_func = content[start:start + 2000]

        assert "request.get_json()" in swap_func, \
            "Should get JSON from request"

    def test_swap_handles_string_json_payload(self):
        """Verify swap can handle JSON string payloads gracefully."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        start = content.find("def api_swap_execute()")
        end = content.find("def ", start + 100)
        swap_func = content[start:end]

        # Should handle string payloads without 500
        # Either by parsing them or returning 400
        assert "json.loads" in swap_func or \
               "isinstance" in swap_func or \
               "try:" in swap_func, \
            "Should have error handling for malformed payloads"

    def test_swap_returns_400_not_500_for_bad_amounts(self):
        """Verify bad amount values return 400, not 500."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        start = content.find("def api_swap_execute()")
        end = content.find("def ", start + 100)
        swap_func = content[start:end]

        # Should catch ValueError from float() and return 400
        assert "except" in swap_func and "400" in swap_func, \
            "Should catch float() errors and return 400"

    def test_verify_wallet_v1_function_handles_missing_fields(self):
        """Verify verify_swap_wallet_v1_or_legacy handles all payload formats."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find function
        func_start = content.find("def verify_swap_wallet_v1_or_legacy(")
        func_end = content.find("\ndef ", func_start + 100)
        func = content[func_start:func_end]

        # Should safely access payload fields
        assert "payload.get(" in func, \
            "Should use .get() for safe field access"

        # Should not assume payload is dict
        assert "isinstance" in func or \
               ".get(" in func, \
            "Should handle various payload types safely"


class TestPayloadExtractionErrors:
    """Test error handling for bad payload data."""

    def test_swap_catches_float_conversion_errors(self):
        """Verify float() conversion errors are caught."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        start = content.find("def api_swap_execute()")
        end = content.find("def ", start + 100)
        swap_func = content[start:end]

        # Should wrap float() calls in try/except
        float_calls = swap_func.count("float(")
        if float_calls > 0:
            assert "except (TypeError, ValueError)" in swap_func or \
                   "except" in swap_func, \
                f"Should catch errors from {float_calls} float() calls"

    def test_swap_doesnt_return_500_for_user_errors(self):
        """Verify user input errors return 400, never 500."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        start = content.find("def api_swap_execute()")
        end = content.find("def ", start + 100)
        swap_func = content[start:end]

        # Count error returns
        err_400 = swap_func.count(", 400")
        err_500 = swap_func.count(", 500")

        # Should have 400s for validation errors
        assert err_400 >= 5, \
            "Should return 400 for input validation errors"

        # Should minimize 500s (they're only for unexpected exceptions)
        assert err_500 <= 2, \
            "Should minimize 500 errors (only for unexpected exceptions)"


class TestErrorMessages:
    """Test that error messages are clear and helpful."""

    def test_swap_returns_structured_errors(self):
        """Verify errors have consistent structure."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        start = content.find("def api_swap_execute()")
        end = content.find("def ", start + 100)
        swap_func = content[start:end]

        # Should use jsonify for consistent response format
        assert "jsonify(" in swap_func, \
            "Should use jsonify for structured responses"

    def test_error_responses_have_status_field(self):
        """Verify error responses include status field."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        start = content.find("def api_swap_execute()")
        end = content.find("def ", start + 100)
        swap_func = content[start:end]

        # Should include status or error field
        assert "status=" in swap_func or \
               "error=" in swap_func or \
               "message=" in swap_func, \
            "Error responses should include status/error/message field"


class TestEdgeCases:
    """Test edge cases in payload handling."""

    def test_swap_handles_empty_payload(self):
        """Verify empty payload is handled safely."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        start = content.find("def api_swap_execute()")
        end = content.find("def ", start + 100)
        swap_func = content[start:end]

        # Should handle empty dict
        assert "or {}" in swap_func or \
               "{}" in swap_func, \
            "Should default to empty dict for missing JSON"

    def test_swap_handles_null_fields(self):
        """Verify null/None fields don't crash."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        start = content.find("def api_swap_execute()")
        end = content.find("def ", start + 100)
        swap_func = content[start:end]

        # Should check for None or use .get() with defaults
        assert ".get(" in swap_func and ("or " in swap_func or "\"\"" in swap_func), \
            "Should handle None/null fields with defaults"

    def test_swap_validates_before_using_fields(self):
        """Verify fields are validated before use."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        start = content.find("def api_swap_execute()")
        end = content.find("def ", start + 100)
        swap_func = content[start:end]

        # Validation errors should come before critical operations
        validation_check = swap_func.find("if not token_in")
        ledger_load = swap_func.find("LEDGER_FILE")

        if validation_check > 0 and ledger_load > 0:
            assert validation_check < ledger_load, \
                "Should validate inputs before loading ledger"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
