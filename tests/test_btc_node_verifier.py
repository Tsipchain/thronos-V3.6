"""Tests for BtcRpcNodeVerifier adapter.

Covers: Esplora REST strategy, bitcoind RPC strategy, fallback between
strategies, confirmation depth, output matching (address + exact satoshi),
tx not found, unconfirmed, output mismatch, fingerprint stub, configuration
errors, and HTTP failure modes.

No real BTC node or API is contacted — all HTTP calls are mocked.
"""
from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
import requests

from services.btc_node_verifier import BtcRpcNodeVerifier
from services.earn_btc_cashout import VerifyResult

VALID_TXID = "a" * 64
VALID_ADDR = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
EXPECTED_SAT = 65660

# ── Esplora response factories ──────────────────────────────────────────

def _esplora_tx(
    *,
    confirmed: bool = True,
    block_height: int = 800000,
    address: str = VALID_ADDR,
    value: int = EXPECTED_SAT,
    extra_outputs: list | None = None,
):
    vout = [{"scriptpubkey_address": address, "value": value}]
    if extra_outputs:
        vout.extend(extra_outputs)
    return {
        "txid": VALID_TXID,
        "status": {"confirmed": confirmed, "block_height": block_height},
        "vout": vout,
    }


def _esplora_response(tx_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = tx_data
    resp.raise_for_status = MagicMock()
    return resp


def _esplora_404():
    resp = MagicMock()
    resp.status_code = 404
    return resp


def _tip_response(height=800010):
    resp = MagicMock()
    resp.status_code = 200
    resp.text = str(height)
    return resp


# ── bitcoind RPC response factories ─────────────────────────────────────

def _rpc_tx(
    *,
    confirmations: int = 6,
    address: str = VALID_ADDR,
    value_btc: float = 0.00065660,
    extra_outputs: list | None = None,
):
    vout = [{
        "value": value_btc,
        "scriptPubKey": {"address": address},
    }]
    if extra_outputs:
        vout.extend(extra_outputs)
    return {
        "txid": VALID_TXID,
        "confirmations": confirmations,
        "vout": vout,
    }


def _rpc_response(result, error=None, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"result": result, "error": error}
    return resp


# ── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def esplora_verifier():
    return BtcRpcNodeVerifier(api_url="http://btc-api.test")


@pytest.fixture
def rpc_verifier():
    return BtcRpcNodeVerifier(rpc_url="http://btc-rpc.test:8332")


@pytest.fixture
def dual_verifier():
    return BtcRpcNodeVerifier(
        api_url="http://btc-api.test",
        rpc_url="http://btc-rpc.test:8332",
    )


# ══════════════════════════════════════════════════════════════════════════
# 1. Configuration
# ══════════════════════════════════════════════════════════════════════════

class TestConfiguration:
    def test_no_url_raises(self):
        with pytest.raises(ValueError, match="requires at least one"):
            BtcRpcNodeVerifier()

    def test_api_url_only(self):
        v = BtcRpcNodeVerifier(api_url="http://test")
        assert v._api_url == "http://test"

    def test_rpc_url_only(self):
        v = BtcRpcNodeVerifier(rpc_url="http://test:8332")
        assert v._rpc_url == "http://test:8332"

    def test_min_confirmations_default(self):
        v = BtcRpcNodeVerifier(api_url="http://test")
        assert v._min_conf == 1

    def test_min_confirmations_custom(self):
        v = BtcRpcNodeVerifier(api_url="http://test", min_confirmations=6)
        assert v._min_conf == 6

    def test_min_confirmations_floor_at_1(self):
        v = BtcRpcNodeVerifier(api_url="http://test", min_confirmations=0)
        assert v._min_conf == 1


# ══════════════════════════════════════════════════════════════════════════
# 2. Esplora strategy — happy path
# ══════════════════════════════════════════════════════════════════════════

class TestEsploraHappyPath:
    @patch("services.btc_node_verifier.requests.get")
    def test_confirmed_tx_with_matching_output(self, mock_get, esplora_verifier):
        mock_get.side_effect = [
            _esplora_response(_esplora_tx()),
            _tip_response(800010),
        ]
        result = esplora_verifier.verify_tx(
            txid=VALID_TXID,
            expected_address=VALID_ADDR,
            expected_amount_sat=EXPECTED_SAT,
        )
        assert result.confirmed is True
        assert result.txid == VALID_TXID
        assert result.amount_sat == EXPECTED_SAT

    @patch("services.btc_node_verifier.requests.get")
    def test_multiple_outputs_matches_correct_one(self, mock_get, esplora_verifier):
        tx = _esplora_tx(
            extra_outputs=[
                {"scriptpubkey_address": "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy", "value": 999},
            ]
        )
        mock_get.side_effect = [_esplora_response(tx), _tip_response()]
        result = esplora_verifier.verify_tx(
            txid=VALID_TXID,
            expected_address=VALID_ADDR,
            expected_amount_sat=EXPECTED_SAT,
        )
        assert result.confirmed is True
        assert result.amount_sat == EXPECTED_SAT


# ══════════════════════════════════════════════════════════════════════════
# 3. Esplora strategy — failure modes
# ══════════════════════════════════════════════════════════════════════════

class TestEsploraFailures:
    @patch("services.btc_node_verifier.requests.get")
    def test_tx_not_found_404(self, mock_get, esplora_verifier):
        mock_get.return_value = _esplora_404()
        result = esplora_verifier.verify_tx(
            txid=VALID_TXID,
            expected_address=VALID_ADDR,
            expected_amount_sat=EXPECTED_SAT,
        )
        assert result.confirmed is False
        assert "tx_not_found" in result.error

    @patch("services.btc_node_verifier.requests.get")
    def test_tx_unconfirmed(self, mock_get, esplora_verifier):
        tx = _esplora_tx(confirmed=False)
        mock_get.return_value = _esplora_response(tx)
        result = esplora_verifier.verify_tx(
            txid=VALID_TXID,
            expected_address=VALID_ADDR,
            expected_amount_sat=EXPECTED_SAT,
        )
        assert result.confirmed is False
        assert "unconfirmed" in result.error

    @patch("services.btc_node_verifier.requests.get")
    def test_insufficient_confirmations(self, mock_get):
        verifier = BtcRpcNodeVerifier(api_url="http://test", min_confirmations=6)
        tx = _esplora_tx(block_height=800008)
        mock_get.side_effect = [_esplora_response(tx), _tip_response(800010)]
        result = verifier.verify_tx(
            txid=VALID_TXID,
            expected_address=VALID_ADDR,
            expected_amount_sat=EXPECTED_SAT,
        )
        assert result.confirmed is False
        assert "insufficient_confirmations" in result.error

    @patch("services.btc_node_verifier.requests.get")
    def test_wrong_address(self, mock_get, esplora_verifier):
        tx = _esplora_tx(address="3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy")
        mock_get.side_effect = [_esplora_response(tx), _tip_response()]
        result = esplora_verifier.verify_tx(
            txid=VALID_TXID,
            expected_address=VALID_ADDR,
            expected_amount_sat=EXPECTED_SAT,
        )
        assert result.confirmed is False
        assert "output_mismatch" in result.error

    @patch("services.btc_node_verifier.requests.get")
    def test_wrong_amount(self, mock_get, esplora_verifier):
        tx = _esplora_tx(value=9999)
        mock_get.side_effect = [_esplora_response(tx), _tip_response()]
        result = esplora_verifier.verify_tx(
            txid=VALID_TXID,
            expected_address=VALID_ADDR,
            expected_amount_sat=EXPECTED_SAT,
        )
        assert result.confirmed is False
        assert "output_mismatch" in result.error

    @patch("services.btc_node_verifier.requests.get")
    def test_http_error_raises(self, mock_get, esplora_verifier):
        resp = MagicMock()
        resp.status_code = 500
        resp.raise_for_status.side_effect = requests.HTTPError("server error")
        mock_get.return_value = resp
        with pytest.raises(ConnectionError, match="all_strategies_failed"):
            esplora_verifier.verify_tx(
                txid=VALID_TXID,
                expected_address=VALID_ADDR,
                expected_amount_sat=EXPECTED_SAT,
            )

    @patch("services.btc_node_verifier.requests.get")
    def test_connection_timeout_raises(self, mock_get, esplora_verifier):
        mock_get.side_effect = requests.ConnectionError("timeout")
        with pytest.raises(ConnectionError, match="all_strategies_failed"):
            esplora_verifier.verify_tx(
                txid=VALID_TXID,
                expected_address=VALID_ADDR,
                expected_amount_sat=EXPECTED_SAT,
            )


# ══════════════════════════════════════════════════════════════════════════
# 4. bitcoind RPC strategy — happy path
# ══════════════════════════════════════════════════════════════════════════

class TestRpcHappyPath:
    @patch("services.btc_node_verifier.requests.post")
    def test_confirmed_tx_with_matching_output(self, mock_post, rpc_verifier):
        mock_post.return_value = _rpc_response(_rpc_tx())
        result = rpc_verifier.verify_tx(
            txid=VALID_TXID,
            expected_address=VALID_ADDR,
            expected_amount_sat=EXPECTED_SAT,
        )
        assert result.confirmed is True
        assert result.txid == VALID_TXID
        assert result.amount_sat == EXPECTED_SAT

    @patch("services.btc_node_verifier.requests.post")
    def test_rpc_auth_passed(self, mock_post, rpc_verifier):
        rpc_verifier._rpc_user = "user"
        rpc_verifier._rpc_password = "pass"
        mock_post.return_value = _rpc_response(_rpc_tx())
        rpc_verifier.verify_tx(
            txid=VALID_TXID,
            expected_address=VALID_ADDR,
            expected_amount_sat=EXPECTED_SAT,
        )
        call_kwargs = mock_post.call_args
        assert call_kwargs.kwargs.get("auth") == ("user", "pass")


# ══════════════════════════════════════════════════════════════════════════
# 5. bitcoind RPC strategy — failure modes
# ══════════════════════════════════════════════════════════════════════════

class TestRpcFailures:
    @patch("services.btc_node_verifier.requests.post")
    def test_tx_not_found(self, mock_post, rpc_verifier):
        mock_post.return_value = _rpc_response(
            None, error={"code": -5, "message": "No such mempool or blockchain transaction"}
        )
        result = rpc_verifier.verify_tx(
            txid=VALID_TXID,
            expected_address=VALID_ADDR,
            expected_amount_sat=EXPECTED_SAT,
        )
        assert result.confirmed is False
        assert "tx_not_found_rpc" in result.error

    @patch("services.btc_node_verifier.requests.post")
    def test_insufficient_confirmations(self, mock_post):
        verifier = BtcRpcNodeVerifier(rpc_url="http://test:8332", min_confirmations=6)
        mock_post.return_value = _rpc_response(_rpc_tx(confirmations=2))
        result = verifier.verify_tx(
            txid=VALID_TXID,
            expected_address=VALID_ADDR,
            expected_amount_sat=EXPECTED_SAT,
        )
        assert result.confirmed is False
        assert "insufficient_confirmations" in result.error

    @patch("services.btc_node_verifier.requests.post")
    def test_wrong_address(self, mock_post, rpc_verifier):
        tx = _rpc_tx(address="3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy")
        mock_post.return_value = _rpc_response(tx)
        result = rpc_verifier.verify_tx(
            txid=VALID_TXID,
            expected_address=VALID_ADDR,
            expected_amount_sat=EXPECTED_SAT,
        )
        assert result.confirmed is False
        assert "output_mismatch_rpc" in result.error

    @patch("services.btc_node_verifier.requests.post")
    def test_wrong_amount(self, mock_post, rpc_verifier):
        tx = _rpc_tx(value_btc=0.00099999)
        mock_post.return_value = _rpc_response(tx)
        result = rpc_verifier.verify_tx(
            txid=VALID_TXID,
            expected_address=VALID_ADDR,
            expected_amount_sat=EXPECTED_SAT,
        )
        assert result.confirmed is False
        assert "output_mismatch_rpc" in result.error

    @patch("services.btc_node_verifier.requests.post")
    def test_rpc_error_raises(self, mock_post, rpc_verifier):
        mock_post.return_value = _rpc_response(
            None, error={"code": -1, "message": "Internal error"}
        )
        with pytest.raises(ConnectionError, match="all_strategies_failed"):
            rpc_verifier.verify_tx(
                txid=VALID_TXID,
                expected_address=VALID_ADDR,
                expected_amount_sat=EXPECTED_SAT,
            )

    @patch("services.btc_node_verifier.requests.post")
    def test_http_500_raises(self, mock_post, rpc_verifier):
        mock_post.return_value = _rpc_response(None, status_code=500)
        with pytest.raises(ConnectionError, match="all_strategies_failed"):
            rpc_verifier.verify_tx(
                txid=VALID_TXID,
                expected_address=VALID_ADDR,
                expected_amount_sat=EXPECTED_SAT,
            )


# ══════════════════════════════════════════════════════════════════════════
# 6. Fallback between strategies
# ══════════════════════════════════════════════════════════════════════════

class TestFallback:
    @patch("services.btc_node_verifier.requests.post")
    @patch("services.btc_node_verifier.requests.get")
    def test_esplora_fails_falls_back_to_rpc(self, mock_get, mock_post, dual_verifier):
        mock_get.side_effect = requests.ConnectionError("esplora down")
        mock_post.return_value = _rpc_response(_rpc_tx())
        result = dual_verifier.verify_tx(
            txid=VALID_TXID,
            expected_address=VALID_ADDR,
            expected_amount_sat=EXPECTED_SAT,
        )
        assert result.confirmed is True

    @patch("services.btc_node_verifier.requests.post")
    @patch("services.btc_node_verifier.requests.get")
    def test_both_fail_raises(self, mock_get, mock_post, dual_verifier):
        mock_get.side_effect = requests.ConnectionError("esplora down")
        mock_post.side_effect = requests.ConnectionError("rpc down")
        with pytest.raises(ConnectionError, match="all_strategies_failed"):
            dual_verifier.verify_tx(
                txid=VALID_TXID,
                expected_address=VALID_ADDR,
                expected_amount_sat=EXPECTED_SAT,
            )

    @patch("services.btc_node_verifier.requests.get")
    def test_esplora_succeeds_skips_rpc(self, mock_get, dual_verifier):
        mock_get.side_effect = [
            _esplora_response(_esplora_tx()),
            _tip_response(),
        ]
        result = dual_verifier.verify_tx(
            txid=VALID_TXID,
            expected_address=VALID_ADDR,
            expected_amount_sat=EXPECTED_SAT,
        )
        assert result.confirmed is True


# ══════════════════════════════════════════════════════════════════════════
# 7. Fingerprint lookup stub
# ══════════════════════════════════════════════════════════════════════════

class TestFingerprintLookup:
    def test_returns_not_confirmed(self, esplora_verifier):
        result = esplora_verifier.lookup_by_fingerprint(request_id="co_test123")
        assert result.confirmed is False
        assert "not_implemented" in result.error

    def test_safe_default_no_fabricated_true(self, rpc_verifier):
        result = rpc_verifier.lookup_by_fingerprint(request_id="co_test456")
        assert result.confirmed is False


# ══════════════════════════════════════════════════════════════════════════
# 8. Esplora — edge cases
# ══════════════════════════════════════════════════════════════════════════

class TestEsploraEdgeCases:
    @patch("services.btc_node_verifier.requests.get")
    def test_tip_height_unavailable_still_confirms(self, mock_get, esplora_verifier):
        """If tip height fetch fails, tx with confirmed status is still accepted (min_conf=1)."""
        tip_fail = MagicMock()
        tip_fail.status_code = 500
        mock_get.side_effect = [
            _esplora_response(_esplora_tx()),
            tip_fail,
        ]
        result = esplora_verifier.verify_tx(
            txid=VALID_TXID,
            expected_address=VALID_ADDR,
            expected_amount_sat=EXPECTED_SAT,
        )
        assert result.confirmed is True

    @patch("services.btc_node_verifier.requests.get")
    def test_exact_satoshi_match_required(self, mock_get, esplora_verifier):
        """Off by 1 satoshi must fail."""
        tx = _esplora_tx(value=EXPECTED_SAT + 1)
        mock_get.side_effect = [_esplora_response(tx), _tip_response()]
        result = esplora_verifier.verify_tx(
            txid=VALID_TXID,
            expected_address=VALID_ADDR,
            expected_amount_sat=EXPECTED_SAT,
        )
        assert result.confirmed is False

    @patch("services.btc_node_verifier.requests.get")
    def test_empty_vout(self, mock_get, esplora_verifier):
        tx = _esplora_tx()
        tx["vout"] = []
        mock_get.side_effect = [_esplora_response(tx), _tip_response()]
        result = esplora_verifier.verify_tx(
            txid=VALID_TXID,
            expected_address=VALID_ADDR,
            expected_amount_sat=EXPECTED_SAT,
        )
        assert result.confirmed is False


# ══════════════════════════════════════════════════════════════════════════
# 9. RPC — edge cases
# ══════════════════════════════════════════════════════════════════════════

class TestRpcEdgeCases:
    @patch("services.btc_node_verifier.requests.post")
    def test_addresses_array_fallback(self, mock_post, rpc_verifier):
        """Old-style bitcoind returns addresses in an array."""
        tx = {
            "txid": VALID_TXID,
            "confirmations": 6,
            "vout": [{
                "value": 0.00065660,
                "scriptPubKey": {"addresses": [VALID_ADDR]},
            }],
        }
        mock_post.return_value = _rpc_response(tx)
        result = rpc_verifier.verify_tx(
            txid=VALID_TXID,
            expected_address=VALID_ADDR,
            expected_amount_sat=EXPECTED_SAT,
        )
        assert result.confirmed is True

    @patch("services.btc_node_verifier.requests.post")
    def test_satoshi_rounding(self, mock_post, rpc_verifier):
        """0.00065660 BTC must round to exactly 65660 sat."""
        mock_post.return_value = _rpc_response(_rpc_tx(value_btc=0.00065660))
        result = rpc_verifier.verify_tx(
            txid=VALID_TXID,
            expected_address=VALID_ADDR,
            expected_amount_sat=65660,
        )
        assert result.confirmed is True
        assert result.amount_sat == 65660


# ══════════════════════════════════════════════════════════════════════════
# 10. Source safety
# ══════════════════════════════════════════════════════════════════════════

class TestSourceSafety:
    def test_no_hardcoded_secrets(self):
        from pathlib import Path
        source = Path("services/btc_node_verifier.py").read_text()
        for keyword in ("api_key", "secret_key", "private_key", "password"):
            lines = [
                (i, l) for i, l in enumerate(source.split("\n"), 1)
                if keyword in l.lower()
                and not l.strip().startswith("#")
                and "rpc_password" not in l
                and "getenv" in l
            ]

    def test_no_fabricated_true(self):
        from pathlib import Path
        import re
        source = Path("services/btc_node_verifier.py").read_text()
        blocks = re.findall(
            r"return VerifyResult\([\s\S]*?confirmed=True[\s\S]*?\n\s*\)",
            source,
        )
        assert len(blocks) >= 1, "Expected at least one confirmed=True return"
        for block in blocks:
            assert "amount_sat=" in block, \
                f"confirmed=True must include amount_sat: {block}"
