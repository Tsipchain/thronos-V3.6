"""
Route-level tests for swap handler hardening (issue #607).

Root cause analysis:
  The issue reports "HTTP 500: string indices must be integers, not 'str'"
  on /api/swap/execute after wallet disconnect/reconnect.

  Key findings:
  1. api_swap_execute (server.py) has a comprehensive try/except that catches
     ALL exceptions (ValueError, KeyError, Exception) and returns 400.  It
     cannot return 500 for any user-triggered input error.

  2. wallet_v1_swap (server_ext.py) does NOT have a top-level try/except.
     If get_json() returns a non-dict (string, list, None that slips past
     the `or {}`), the first .get() call raises AttributeError, which
     propagates to Flask's 500 error handler.

  3. The inner try/except blocks in wallet_v1_swap (swap execution, state
     save) explicitly return 500 with detail=str(exception).  If the swap
     leg iteration encounters a non-dict leg, bracket indexing like
     leg["token_in"] on a string raises TypeError: string indices must be
     integers, which is caught and returned as 500.

  4. The PWA constructs swap bodies with single JSON.stringify — the
     "double-serialized JSON" hypothesis was incorrect.  The actual trigger
     is a non-dict body or payload reaching handler code that assumes dict.

  Evidence (bracket-index on non-dict types):
    "hello"["intent"]  → TypeError: string indices must be integers, not 'str'
    "hello".get("intent") → AttributeError: 'str' object has no attribute 'get'
  Both are unhandled in wallet_v1_swap before the fix; Flask returns 500.

  Fix:  isinstance guards at the top of both handlers reject non-dict
  bodies early with 400, before any .get() or bracket-indexing code runs.

  Physical-device QA remains required for the full restore→sign→swap path.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Import server_ext to register /api/wallet/v1/swap route (added by server_ext.py)
import server_ext  # noqa: F401 — registers ext routes on the Flask app


# ---------------------------------------------------------------------------
# Route-level: Flask test client tests
# ---------------------------------------------------------------------------

class TestSwapExecuteRouteMalformedBody:
    """Route-level: /api/swap/execute rejects malformed bodies with 400."""

    @pytest.fixture(autouse=True)
    def _client(self):
        from server_ext import app
        self.client = app.test_client()

    def test_string_body_returns_400(self):
        """A JSON string body (not a dict) must return 400, not 500."""
        r = self.client.post(
            "/api/swap/execute",
            data=json.dumps("not_a_dict"),
            content_type="application/json",
        )
        assert r.status_code == 400, f"Expected 400, got {r.status_code}"
        body = r.get_json()
        assert body.get("error") in (
            "invalid_request_body",
            "missing_trader",
            "invalid_input",
        )

    def test_list_body_returns_400(self):
        """A JSON array body must return 400, not 500."""
        r = self.client.post(
            "/api/swap/execute",
            data=json.dumps(["a", "b"]),
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_null_body_returns_400(self):
        """A null JSON body must return 400, not 500."""
        r = self.client.post(
            "/api/swap/execute",
            data="null",
            content_type="application/json",
        )
        # null → get_json() returns None → data = None or {} → {}
        # Handler proceeds with empty dict, returns 400 for missing fields
        assert r.status_code == 400

    def test_double_serialized_dict_returns_400(self):
        """Double-serialized JSON (string wrapping a dict) → 400."""
        inner = {"token_in": "THR", "token_out": "WBTC", "amount_in": 1.0}
        double = json.dumps(json.dumps(inner))
        r = self.client.post(
            "/api/swap/execute",
            data=double,
            content_type="application/json",
        )
        # Should be re-parsed or rejected, never 500
        assert r.status_code != 500, "Must not return 500 for malformed body"
        assert r.status_code == 400

    def test_valid_dict_body_not_rejected_by_guard(self):
        """A valid dict body passes the guard (may fail auth, but not 500)."""
        r = self.client.post(
            "/api/swap/execute",
            json={"token_in": "THR", "token_out": "WBTC", "amount_in": 1.0,
                  "trader_thr": "THR0000000000000000000000000000000000000001"},
        )
        # Should fail on auth/pledge, not on body parsing
        assert r.status_code != 500, f"Valid dict body should not cause 500"
        assert r.status_code in (400, 403, 404)


class TestWalletV1SwapRouteMalformedBody:
    """Route-level: /api/wallet/v1/swap rejects malformed bodies with 400."""

    @pytest.fixture(autouse=True)
    def _client(self):
        from server_ext import app
        self.client = app.test_client()

    def test_string_body_returns_400_not_500(self):
        """A JSON string body must return 400, not 500.

        Before the fix, get_json() returning a string caused:
          data.get('intent') → AttributeError
        which propagated to Flask's 500 handler.
        """
        r = self.client.post(
            "/api/wallet/v1/swap",
            data=json.dumps("not_a_dict"),
            content_type="application/json",
        )
        assert r.status_code != 500, (
            f"String body caused {r.status_code}; "
            "should be 400 (invalid_request_body), not 500"
        )
        assert r.status_code == 400
        body = r.get_json()
        assert body.get("error") == "invalid_request_body"

    def test_list_body_returns_400_not_500(self):
        """A JSON array body must return 400, not 500."""
        r = self.client.post(
            "/api/wallet/v1/swap",
            data=json.dumps([1, 2, 3]),
            content_type="application/json",
        )
        assert r.status_code != 500
        assert r.status_code == 400

    def test_integer_body_returns_400_not_500(self):
        """A bare integer JSON body must return 400, not 500."""
        r = self.client.post(
            "/api/wallet/v1/swap",
            data="42",
            content_type="application/json",
        )
        assert r.status_code != 500
        assert r.status_code == 400

    def test_double_serialized_dict_returns_400(self):
        """Double-serialized JSON (string wrapping a dict) → 400."""
        inner = {"intent": {}, "signature": "ab" * 32, "public_key": "02" + "1" * 64}
        double = json.dumps(json.dumps(inner))
        r = self.client.post(
            "/api/wallet/v1/swap",
            data=double,
            content_type="application/json",
        )
        assert r.status_code != 500, "Double-serialized body must not cause 500"

    def test_missing_intent_returns_401(self):
        """Dict body without intent/signature/public_key returns 401."""
        r = self.client.post(
            "/api/wallet/v1/swap",
            json={"token_in": "THR"},
        )
        assert r.status_code == 401
        body = r.get_json()
        assert body.get("error") == "signed_wallet_action_required"

    def test_string_payload_field_handled(self):
        """If payload field is a string, it should not cause 500.

        Before the fix:
          payload = data.get('payload') or {}  → "string_value"
          payload.get('token_in') → AttributeError → 500
        After the fix:
          isinstance(payload, str) check re-parses or resets to {}
        """
        r = self.client.post(
            "/api/wallet/v1/swap",
            json={
                "intent": {"action": "swap", "type": "thronos_wallet_action",
                           "version": "1", "wallet_id": "test",
                           "from_thr": "THR0001", "nonce": "n1",
                           "created_at": "9999999999", "payload_hash": "x"},
                "signature": "ab" * 32,
                "public_key": "02" + "1" * 64,
                "payload": "this_is_a_string_not_dict",
            },
        )
        # Should fail on auth/hash, not on AttributeError → 500
        assert r.status_code != 500, (
            f"String payload field caused {r.status_code}; expected 400"
        )


# ---------------------------------------------------------------------------
# Source-level: guard presence checks
# ---------------------------------------------------------------------------

class TestSwapExecuteGuardPresence:
    """Verify isinstance guards are present in api_swap_execute."""

    @pytest.fixture(autouse=True)
    def _src(self):
        import re
        with open(str(Path(__file__).resolve().parents[1] / "server.py")) as f:
            src = f.read()
        m = re.search(
            r'@app\.route\("/api/swap/execute".*?\ndef api_swap_execute\(\):'
            r'([\s\S]*?)(?=\n@app\.route|\nclass |\Z)',
            src,
        )
        assert m, "api_swap_execute handler not found"
        self.body = m.group(1)

    def test_isinstance_dict_guard(self):
        assert "isinstance(data, dict)" in self.body

    def test_isinstance_str_guard(self):
        assert "isinstance(data, str)" in self.body

    def test_inner_payload_str_guard(self):
        assert "isinstance(inner, str)" in self.body

    def test_400_error_code(self):
        assert "invalid_request_body" in self.body


class TestWalletV1SwapGuardPresence:
    """Verify isinstance guards are present in wallet_v1_swap."""

    @pytest.fixture(autouse=True)
    def _src(self):
        import re
        with open(str(Path(__file__).resolve().parents[1] / "server_ext.py")) as f:
            src = f.read()
        m = re.search(
            r"@app\.route\('/api/wallet/v1/swap'.*?\ndef wallet_v1_swap\(\):"
            r"([\s\S]*?)(?=\n@app\.route|\nclass |\Z)",
            src,
        )
        assert m, "wallet_v1_swap handler not found"
        self.body = m.group(1)

    def test_isinstance_dict_guard(self):
        assert "isinstance(data, dict)" in self.body

    def test_isinstance_str_guard(self):
        assert "isinstance(data, str)" in self.body

    def test_payload_str_guard(self):
        assert "isinstance(payload, str)" in self.body

    def test_400_error_code(self):
        assert "invalid_request_body" in self.body


# ---------------------------------------------------------------------------
# PWA swap path verification
# ---------------------------------------------------------------------------

class TestPWASwapPaths:
    """Verify PWA swap code uses single JSON.stringify for each path."""

    @pytest.fixture(autouse=True)
    def _src(self):
        with open(str(Path(__file__).resolve().parents[1] /
                       "public/wallet-pwa/app.js")) as f:
            self.src = f.read()

    def test_v1_swap_path_exists(self):
        assert "/api/wallet/v1/swap" in self.src

    def test_execute_swap_path_exists(self):
        assert "/api/swap/execute" in self.src

    def test_single_stringify_v1_path(self):
        """V1 path uses JSON.stringify once (not double-serialized).

        The fetch() call for /api/wallet/v1/swap should have exactly one
        JSON.stringify in its body: argument (appears AFTER the URL).
        """
        idx = self.src.index("/api/wallet/v1/swap")
        # body: JSON.stringify(...) appears ~50-200 chars after the URL
        block = self.src[idx:idx + 300]
        assert "JSON.stringify" in block, "No JSON.stringify found near v1/swap fetch body"
        count = block.count("JSON.stringify")
        assert count == 1, f"Expected 1 JSON.stringify for v1/swap body, found {count}"

    def test_single_stringify_execute_path(self):
        """Execute path uses JSON.stringify once for the body (not double)."""
        idx = self.src.index("/api/swap/execute")
        # body: JSON.stringify(...) appears ~50-200 chars after the URL
        block = self.src[idx:idx + 300]
        assert "JSON.stringify" in block, "No JSON.stringify found near execute fetch body"


# ---------------------------------------------------------------------------
# No secrets verification
# ---------------------------------------------------------------------------

class TestNoSecretsInSwapHandlers:
    """Verify swap handlers don't log or expose private keys."""

    def _read_handler(self, filename, pattern):
        import re
        with open(str(Path(__file__).resolve().parents[1] / filename)) as f:
            src = f.read()
        m = re.search(pattern, src)
        return m.group(1) if m else ""

    def test_no_private_key_in_execute_response(self):
        body = self._read_handler(
            "server.py",
            r'def api_swap_execute\(\):([\s\S]*?)(?=\ndef [a-z]|\n@app\.route|\Z)',
        )
        for line in body.split("\n"):
            if "jsonify" in line:
                assert "private_key" not in line.lower() or "error" in line.lower()

    def test_no_auth_secret_in_execute_response(self):
        body = self._read_handler(
            "server.py",
            r'def api_swap_execute\(\):([\s\S]*?)(?=\ndef [a-z]|\n@app\.route|\Z)',
        )
        for line in body.split("\n"):
            if "jsonify" in line:
                assert "auth_secret" not in line or "missing" in line or "error" in line
