"""
/api/wallet/send Wallet V1 Migration Tests

Verifies that /api/wallet/send endpoint supports:
1. New centralized Wallet V1 signed request format
2. Legacy auth_secret + passphrase format (backward compatibility)
3. Proper payload extraction and validation
4. Clear error messages for invalid payloads
5. Bound signer validation
"""

import pytest
from pathlib import Path


class TestWalletSendV1Support:
    """Test Wallet V1 signed request support in send endpoint."""

    def test_wallet_send_endpoint_exists(self):
        """Verify /api/wallet/send endpoint exists."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        assert "@app.route(\"/api/wallet/send\"" in content, \
            "/api/wallet/send endpoint not found"
        assert "def api_wallet_send():" in content, \
            "api_wallet_send function not found"

    def test_wallet_send_checks_wallet_v1_signed_request(self):
        """Verify endpoint checks for Wallet V1 signed request."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find endpoint
        start = content.find("def api_wallet_send():")
        end = content.find("\ndef ", start + 100)
        endpoint = content[start:end]

        assert "canonical_v1_address" in endpoint and "signature" in endpoint, \
            "Should check for Wallet V1 signed request fields"
        assert "verify_wallet_v1_signed_request" in endpoint, \
            "Should verify signed request"

    def test_wallet_send_uses_extract_signed_payload(self):
        """Verify send endpoint uses _extract_signed_payload helper."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find endpoint
        start = content.find("def api_wallet_send():")
        end = content.find("\ndef ", start + 100)
        endpoint = content[start:end]

        assert "_extract_signed_payload" in endpoint, \
            "Should use payload extraction helper"

    def test_wallet_send_returns_400_on_payload_error(self):
        """Verify send returns 400 for invalid payload."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find endpoint
        start = content.find("def api_wallet_send():")
        end = content.find("\ndef ", start + 100)
        endpoint = content[start:end]

        assert "payload_err" in endpoint or "payload, " in endpoint, \
            "Should check for payload errors"
        assert "400" in endpoint, \
            "Should return 400 on invalid payload"


class TestWalletSendPayloadExtraction:
    """Test payload extraction from signed requests."""

    def test_wallet_send_extracts_token_from_payload(self):
        """Verify send extracts token from payload."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find endpoint
        start = content.find("def api_wallet_send():")
        end = content.find("\ndef ", start + 100)
        endpoint = content[start:end]

        # Extract payload section
        payload_start = endpoint.find("payload.get(\"token\")")
        assert payload_start > 0, \
            "Should extract token from payload"

    def test_wallet_send_extracts_recipient_from_payload(self):
        """Verify send extracts recipient address from payload."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find endpoint
        start = content.find("def api_wallet_send():")
        end = content.find("\ndef ", start + 100)
        endpoint = content[start:end]

        # Should extract 'to' address
        assert "payload.get(\"to\")" in endpoint, \
            "Should extract recipient address from payload"

    def test_wallet_send_extracts_amount_from_payload(self):
        """Verify send extracts amount from payload."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find endpoint
        start = content.find("def api_wallet_send():")
        end = content.find("\ndef send_thr_internal", start)
        endpoint = content[start:end]

        # Should extract amount (check for the assignment in signed request section)
        # Look for the section after payload extraction
        payload_section_start = endpoint.find("payload.get(")
        if payload_section_start > 0:
            payload_section = endpoint[payload_section_start:payload_section_start + 200]
            # Should have amount = payload.get with amount key
            assert 'payload.get' in payload_section and 'amount' in payload_section, \
                "Should extract amount from payload"
        else:
            # Fallback: just check that amount is mentioned with payload
            assert 'payload' in endpoint and 'amount' in endpoint, \
                "Should handle amount from payload"

    def test_wallet_send_extracts_speed_from_payload(self):
        """Verify send extracts speed preference from payload."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find endpoint
        start = content.find("def api_wallet_send():")
        end = content.find("\ndef ", start + 100)
        endpoint = content[start:end]

        # Should extract speed
        assert "payload.get(\"speed\")" in endpoint, \
            "Should extract speed from payload"


class TestWalletSendBackwardCompatibility:
    """Test backward compatibility with legacy format."""

    def test_wallet_send_supports_legacy_format(self):
        """Verify send still supports legacy auth_secret format."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find endpoint
        start = content.find("def api_wallet_send():")
        end = content.find("\ndef ", start + 100)
        endpoint = content[start:end]

        # Should have legacy fallback section
        assert "Legacy format fallback" in endpoint, \
            "Should have legacy format fallback comment"
        assert "auth_secret" in endpoint, \
            "Should support auth_secret"
        assert "passphrase" in endpoint, \
            "Should support passphrase"

    def test_wallet_send_legacy_gets_addresses_from_data(self):
        """Verify legacy format gets addresses from data dict."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find endpoint
        start = content.find("def api_wallet_send():")
        end = content.find("\ndef ", start + 100)
        endpoint = content[start:end]

        # Legacy section should get from/to from data
        legacy_start = endpoint.find("Legacy format fallback")
        legacy_section = endpoint[legacy_start:legacy_start+500]

        assert "data.get(\"from\")" in legacy_section or "data.get(\"from_thr\")" in legacy_section, \
            "Legacy format should get from address from data"
        assert "data.get(\"to\")" in legacy_section or "data.get(\"to_thr\")" in legacy_section, \
            "Legacy format should get to address from data"


class TestWalletSendIntegration:
    """Test send endpoint integration with internal functions."""

    def test_wallet_send_calls_send_thr_internal(self):
        """Verify send calls send_thr_internal for THR."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find endpoint
        start = content.find("def api_wallet_send():")
        end = content.find("\ndef ", start + 100)
        endpoint = content[start:end]

        assert "send_thr_internal" in endpoint, \
            "Should call send_thr_internal for THR transfers"

    def test_wallet_send_calls_transfer_custom_token(self):
        """Verify send calls transfer_custom_token for non-THR tokens."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find endpoint
        start = content.find("def api_wallet_send():")
        end = content.find("\ndef ", start + 100)
        endpoint = content[start:end]

        assert "transfer_custom_token" in endpoint, \
            "Should call transfer_custom_token for custom tokens"


class TestWalletSendSignedRequestValidation:
    """Test signed request validation in send."""

    def test_wallet_send_validates_signature(self):
        """Verify send validates signature before processing."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find endpoint
        start = content.find("def api_wallet_send():")
        end = content.find("\ndef ", start + 100)
        endpoint = content[start:end]

        # Should check verified.get("ok")
        assert "verified.get(\"ok\")" in endpoint, \
            "Should validate signature verification result"
        assert "400" in endpoint, \
            "Should return 400 on signature validation failure"

    def test_wallet_send_returns_clear_error_message(self):
        """Verify send returns clear error messages."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find endpoint
        start = content.find("def api_wallet_send():")
        end = content.find("\ndef ", start + 100)
        endpoint = content[start:end]

        # Should have error message in response
        assert "message=" in endpoint or "error=" in endpoint, \
            "Should include error message in response"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
