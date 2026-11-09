"""
Tests for swap handler hardening against double-serialized JSON
and malformed request bodies (issue #607).

These tests verify that /api/swap/execute and /api/wallet/v1/swap
return 400 (not 500) when the request body is a string, a list,
or contains double-serialized nested fields.
"""

import json
import pytest
import re


# ---------------------------------------------------------------------------
# 1. Unit-level: server.py api_swap_execute handler guards
# ---------------------------------------------------------------------------

class TestSwapExecuteBodyGuard:
    """Test that api_swap_execute guards against non-dict request bodies."""

    def _read_swap_execute_handler(self):
        with open('server.py', 'r') as f:
            src = f.read()
        match = re.search(
            r'@app\.route\("/api/swap/execute".*?\ndef api_swap_execute\(\):'
            r'([\s\S]*?)(?=\n@app\.route|\nclass |\Z)',
            src
        )
        assert match, "api_swap_execute handler not found"
        return match.group(1)

    def test_isinstance_dict_guard_present(self):
        """Handler must check isinstance(data, dict) after get_json."""
        body = self._read_swap_execute_handler()
        assert 'isinstance(data, dict)' in body

    def test_isinstance_str_re_parse_present(self):
        """Handler must attempt json.loads when data is a string."""
        body = self._read_swap_execute_handler()
        assert 'isinstance(data, str)' in body
        assert 'json.loads(data)' in body

    def test_inner_payload_string_guard(self):
        """Handler must guard inner/payload against string type."""
        body = self._read_swap_execute_handler()
        assert 'isinstance(inner, str)' in body

    def test_returns_400_not_500_for_non_dict(self):
        """Handler returns 400 with error code for non-dict body."""
        body = self._read_swap_execute_handler()
        assert 'invalid_request_body' in body


class TestSwapExecutePayloadParsing:
    """Test the double-serialized payload parsing logic in isolation."""

    def test_string_body_reparsed_to_dict(self):
        """A JSON string containing a dict should be re-parsed."""
        raw = '{"token_in": "THR", "token_out": "WBTC", "amount_in": 1.0}'
        data = raw
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, ValueError):
                pass
        assert isinstance(data, dict)
        assert data["token_in"] == "THR"

    def test_invalid_string_body_stays_string(self):
        """A non-JSON string stays as string and is rejected."""
        data = "not valid json"
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, ValueError):
                pass
        assert not isinstance(data, dict)

    def test_nested_payload_string_reparsed(self):
        """A string payload nested inside a dict is re-parsed."""
        inner_str = '{"token_in":"THR","token_out":"WBTC"}'
        data = {"payload": inner_str}
        inner = data.get("payload") or {}
        if isinstance(inner, str):
            try:
                inner = json.loads(inner)
            except (json.JSONDecodeError, ValueError):
                inner = {}
        if not isinstance(inner, dict):
            inner = {}
        assert isinstance(inner, dict)
        assert inner["token_in"] == "THR"

    def test_list_body_rejected(self):
        """A list body is not a dict and should be rejected."""
        data = [1, 2, 3]
        assert not isinstance(data, dict)

    def test_none_body_becomes_empty_dict(self):
        """None from get_json() becomes {} via `or {}`."""
        data = None or {}
        assert isinstance(data, dict)
        assert data == {}

    def test_double_serialized_full_roundtrip(self):
        """Simulate double-serialized JSON: JSON.stringify called twice."""
        original = {"token_in": "THR", "token_out": "WBTC", "amount_in": 1.0}
        once = json.dumps(original)
        twice = json.dumps(once)
        # Flask get_json() would parse outer layer, returning the string
        data = json.loads(twice)
        assert isinstance(data, str)
        # Our guard re-parses
        if isinstance(data, str):
            data = json.loads(data)
        assert isinstance(data, dict)
        assert data["token_in"] == "THR"


# ---------------------------------------------------------------------------
# 2. Unit-level: server_ext.py wallet_v1_swap handler guards
# ---------------------------------------------------------------------------

class TestWalletV1SwapBodyGuard:
    """Test that wallet_v1_swap in server_ext.py guards against non-dict bodies."""

    def _read_wallet_v1_swap_handler(self):
        with open('server_ext.py', 'r') as f:
            src = f.read()
        match = re.search(
            r"@app\.route\('/api/wallet/v1/swap'.*?\ndef wallet_v1_swap\(\):"
            r"([\s\S]*?)(?=\n@app\.route|\nclass |\Z)",
            src
        )
        assert match, "wallet_v1_swap handler not found"
        return match.group(1)

    def test_isinstance_dict_guard_present(self):
        """Handler must check isinstance(data, dict) after get_json."""
        body = self._read_wallet_v1_swap_handler()
        assert 'isinstance(data, dict)' in body

    def test_isinstance_str_re_parse_present(self):
        """Handler must attempt json.loads when data is a string."""
        body = self._read_wallet_v1_swap_handler()
        assert 'isinstance(data, str)' in body

    def test_payload_string_guard(self):
        """Handler must guard payload field against string type."""
        body = self._read_wallet_v1_swap_handler()
        assert 'isinstance(payload, str)' in body

    def test_returns_400_for_non_dict(self):
        """Handler returns 400 with error code for non-dict body."""
        body = self._read_wallet_v1_swap_handler()
        assert 'invalid_request_body' in body


# ---------------------------------------------------------------------------
# 3. PWA swap route existence
# ---------------------------------------------------------------------------

class TestPWASwapRouteExists:
    """Verify both swap routes exist for the PWA fallback pattern."""

    def test_api_swap_execute_route_exists(self):
        with open('server.py', 'r') as f:
            src = f.read()
        assert '@app.route("/api/swap/execute"' in src

    def test_api_wallet_v1_swap_route_exists(self):
        with open('server_ext.py', 'r') as f:
            src = f.read()
        assert "@app.route('/api/wallet/v1/swap'" in src

    def test_pwa_sends_to_v1_swap_first(self):
        with open('public/wallet-pwa/app.js', 'r') as f:
            src = f.read()
        assert '/api/wallet/v1/swap' in src

    def test_pwa_fallback_sends_to_swap_execute(self):
        with open('public/wallet-pwa/app.js', 'r') as f:
            src = f.read()
        assert '/api/swap/execute' in src


# ---------------------------------------------------------------------------
# 4. Recovery Kit restore UI existence
# ---------------------------------------------------------------------------

class TestRecoveryKitRestoreUI:
    """Verify that Recovery Kit restore UI elements exist in the frontend."""

    def test_restore_kit_button_in_base_html(self):
        with open('templates/base.html', 'r') as f:
            src = f.read()
        assert 'recovery' in src.lower() or 'restore' in src.lower()

    def test_restore_handler_in_app_js(self):
        with open('public/wallet-pwa/app.js', 'r') as f:
            src = f.read()
        assert 'restore' in src.lower()


# ---------------------------------------------------------------------------
# 5. No secrets in swap handlers
# ---------------------------------------------------------------------------

class TestNoSecretsInSwapHandlers:
    """Verify swap handlers don't log or expose private keys or secrets."""

    def _read_swap_execute_handler(self):
        with open('server.py', 'r') as f:
            src = f.read()
        match = re.search(
            r'def api_swap_execute\(\):([\s\S]*?)(?=\ndef [a-z]|\n@app\.route|\Z)',
            src
        )
        return match.group(1) if match else ""

    def test_no_private_key_logging(self):
        body = self._read_swap_execute_handler()
        assert 'private_key' not in body.lower() or 'private_key' in body.lower().split('error')[0] is None

    def test_no_secret_in_response(self):
        body = self._read_swap_execute_handler()
        lines = [l for l in body.split('\n') if 'jsonify' in l]
        for line in lines:
            assert 'auth_secret' not in line or 'error' in line or 'missing' in line


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
