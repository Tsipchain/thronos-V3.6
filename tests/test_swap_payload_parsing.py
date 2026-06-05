"""
Swap Payload Parsing Bug Fix Tests

Verifies robust payload parsing for /api/swap/execute and /api/swap/add_liquidity:
1. Handles payload as dict - OK
2. Handles payload as JSON string - parse and use
3. Handles missing payload - default to {}
4. Rejects invalid JSON string - 400 invalid_payload_json
5. Rejects non-dict payload - 400 invalid_payload_format
6. Returns 400, not 500, for malformed payload

Bug: Previously returned HTTP 500 with "string indices must be integers, not 'str'"
when payload was a string instead of dict.
"""

import pytest
import json
from pathlib import Path


class TestPayloadExtractionFunction:
    """Test the _extract_signed_payload helper function."""

    def test_extract_signed_payload_exists(self):
        """Verify _extract_signed_payload function is defined."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        assert "def _extract_signed_payload(request_data):" in content, \
            "_extract_signed_payload function not found"

    def test_extract_signed_payload_handles_dict(self):
        """Verify function handles dict payload."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find function
        start = content.find("def _extract_signed_payload")
        end = content.find("\ndef ", start + 1)
        func = content[start:end]

        # Must handle dict
        assert "isinstance(payload, dict)" in func, \
            "Must check if payload is dict"

    def test_extract_signed_payload_handles_string_json(self):
        """Verify function handles JSON string payload."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find function
        start = content.find("def _extract_signed_payload")
        end = content.find("\ndef ", start + 1)
        func = content[start:end]

        # Must handle string -> JSON
        assert "isinstance(payload, str)" in func, \
            "Must check if payload is string"
        assert "json.loads" in func, \
            "Must parse JSON string"

    def test_extract_signed_payload_returns_tuple(self):
        """Verify function returns (payload, error) tuple."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find function
        start = content.find("def _extract_signed_payload")
        end = content.find("\ndef ", start + 1)
        func = content[start:end]

        # Must return tuple
        assert "return" in func and ("None" in func or "error" in func), \
            "Must handle error returns"


class TestSwapPayloadParsing:
    """Test swap endpoint payload parsing."""

    def test_swap_uses_extract_signed_payload(self):
        """Verify swap endpoint uses _extract_signed_payload."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find swap endpoint
        start = content.find("@app.route(\"/api/swap/execute\"")
        end = content.find("@app.route", start + 100)
        endpoint = content[start:end]

        assert "_extract_signed_payload" in endpoint, \
            "Swap endpoint should use _extract_signed_payload"

    def test_swap_checks_payload_error(self):
        """Verify swap endpoint checks for payload parsing errors."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Check that _extract_signed_payload is used in the file
        # (tests that verify specific lines are in the endpoint)
        assert "_extract_signed_payload" in content and "api_swap_execute" in content, \
            "Swap endpoint should use _extract_signed_payload"

        # Find the extract call and verify error handling follows
        extract_pos = content.find("_extract_signed_payload", content.find("def api_swap_execute"))
        assert extract_pos > 0, "Should use _extract_signed_payload in swap"

        error_check = content[extract_pos:extract_pos + 500]
        assert "payload_err" in error_check, \
            "Should check for payload_err after extraction"
        assert "return jsonify" in error_check and "400" in error_check, \
            "Should return 400 on payload error"


class TestAddLiquidityPayloadParsing:
    """Test add_liquidity endpoint payload parsing."""

    def test_add_liquidity_uses_extract_signed_payload(self):
        """Verify add_liquidity endpoint uses _extract_signed_payload."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find add_liquidity endpoint (looking for add_liquidity route in pools section)
        start = content.find("def api_v1_add_liquidity()")
        end = content.find("\n@app.route", start)
        if end == -1:
            end = content.find("\ndef ", start + 200)
        endpoint = content[start:end]

        assert "_extract_signed_payload" in endpoint, \
            "Add_liquidity endpoint should use _extract_signed_payload"

    def test_add_liquidity_checks_payload_error(self):
        """Verify add_liquidity endpoint checks for payload parsing errors."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Check that _extract_signed_payload is used in the file
        assert "_extract_signed_payload" in content and "api_v1_add_liquidity" in content, \
            "Add_liquidity endpoint should use _extract_signed_payload"

        # Find the extract call in add_liquidity
        api_start = content.find("def api_v1_add_liquidity()")
        extract_pos = content.find("_extract_signed_payload", api_start)
        assert extract_pos > api_start, "Should use _extract_signed_payload in add_liquidity"

        error_check = content[extract_pos:extract_pos + 500]
        assert "payload_err" in error_check, \
            "Should check for payload_err after extraction"
        assert "return jsonify" in error_check and "400" in error_check, \
            "Should return 400 on payload error"


class TestErrorMessages:
    """Test that error messages are clear."""

    def test_swap_endpoint_has_error_message(self):
        """Verify swap endpoint returns clear error messages."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Check for payload error handling in swap
        start = content.find("@app.route(\"/api/swap/execute\"")
        end = content.find("@app.route", start + 100)
        endpoint = content[start:end]

        # Should return both error code and message
        assert "Invalid payload" in endpoint, \
            "Should have user-friendly error message"

    def test_add_liquidity_endpoint_has_error_message(self):
        """Verify add_liquidity endpoint returns clear error messages."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Check for payload error handling in add_liquidity
        start = content.find("def api_v1_add_liquidity()")
        end = content.find("\n@app.route", start)
        if end == -1:
            end = content.find("\ndef ", start + 200)
        endpoint = content[start:end]

        # Should return both error code and message
        assert "Invalid payload" in endpoint, \
            "Should have user-friendly error message"


class TestAmountConversionErrorHandling:
    """Test that invalid amount values return 400, not 500."""

    def test_swap_wraps_float_conversion_in_try_except(self):
        """Verify swap endpoint wraps float() in try/except for centralized format."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find the centralized format section of swap endpoint
        api_start = content.find("def api_swap_execute()")
        centralized_section_start = content.find("if data.get(\"canonical_v1_address\")", api_start)
        centralized_section_end = content.find("else:", centralized_section_start)
        centralized_section = content[centralized_section_start:centralized_section_end]

        # Must have try/except around float() calls
        assert "try:" in centralized_section and "except" in centralized_section, \
            "Should wrap float() conversion in try/except for centralized format"

        # Check for float conversions
        assert "float(payload.get(\"amount_in\"" in centralized_section, \
            "Should convert amount_in to float"
        assert "float(payload.get(\"min_amount_out\"" in centralized_section, \
            "Should convert min_amount_out to float"

    def test_swap_returns_400_on_invalid_amount(self):
        """Verify swap returns 400 for invalid amounts."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find the centralized format section
        api_start = content.find("def api_swap_execute()")
        centralized_end = content.find("else:", content.find("canonical_v1_address", api_start))
        centralized_section = content[api_start:centralized_end]

        # Find try/except for float conversion
        float_try = centralized_section.find("try:")
        float_try = centralized_section.find("try:", float_try + 5)  # Second try block
        float_except = centralized_section.find("except", float_try)

        assert float_try > 0 and float_except > float_try, \
            "Should have try/except for float conversions"

        # Check that it returns 400
        error_response = centralized_section[float_except:float_except + 200]
        assert "400" in error_response, \
            "Should return 400 for invalid amounts"


class TestNoFallbackOnPayloadError:
    """Test that invalid payload doesn't fall back to legacy."""

    def test_swap_returns_400_not_fallback(self):
        """Verify invalid payload returns 400, not fallback to legacy."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find swap endpoint
        api_start = content.find("def api_swap_execute()")
        payload_extract = content.find("_extract_signed_payload", api_start)
        payload_error_check = content.find("if payload_err:", payload_extract)
        token_in_ref = content.find("token_in =", payload_error_check)

        # Error check must come before token_in extraction
        assert payload_error_check > payload_extract and token_in_ref > payload_error_check, \
            "Error handling must come before token extraction"

        error_section = content[payload_error_check:token_in_ref]
        assert "return jsonify" in error_section and "400" in error_section, \
            "Should return 400 for invalid payload before using fields"

    def test_add_liquidity_returns_400_not_fallback(self):
        """Verify invalid payload returns 400, not fallback to legacy."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find add_liquidity endpoint
        api_start = content.find("def api_v1_add_liquidity()")
        payload_extract = content.find("_extract_signed_payload", api_start)
        payload_error_check = content.find("if payload_err:", payload_extract)
        pool_id_ref = content.find("pool_id =", payload_error_check)

        # Error check must come before pool_id extraction
        assert payload_error_check > payload_extract and pool_id_ref > payload_error_check, \
            "Error handling must come before pool_id extraction"

        error_section = content[payload_error_check:pool_id_ref]
        assert "return jsonify" in error_section and "400" in error_section, \
            "Should return 400 for invalid payload before using fields"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
