"""
Tests for the SigBalBot Context Bridge (thronos-v3.6 integration).

Covers:
  1. Configuration detection
  2. Context URL derivation
  3. Authentication (Bearer header)
  4. Cursor persistence
  5. Signal classification (sentinel_confirmed, external, skip)
  6. Duplicate detection
  7. Governance advisory generation
  8. Status reporting
  9. Retry on 5xx
  10. Processed IDs bounding
"""
import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

os.environ["SIGBALBOT_WEBHOOK_URL"] = "https://sigbalbot.up.railway.app/api/v1/signals/trader-sentinel"
os.environ["SIGBALBOT_API_KEY"] = "test-bridge-key-789"

from sigbalbot_context_bridge import (
    SigBalBotContextBridge,
    _derive_context_url,
    _MAX_PROCESSED_IDS,
)


SAMPLE_CONTEXT = {
    "ok": True,
    "contract_version": "1.0",
    "generated_at": "2025-01-15T12:00:00Z",
    "watchlist": [
        {
            "symbol": "BSB/USDT",
            "label": "BSB",
            "mode": "sniper",
            "market_cap_usd": 9000000,
            "volume_24h": 1250000,
            "liquidity_usd": 340000,
            "last_scan_at": "2025-01-15T11:55:00Z",
            "last_scan_signal": "HOLD",
        }
    ],
    "native_signals": [
        {
            "id": "sentinel-ctx-BTC-USDT-LONG-1700000000",
            "symbol": "BTC/USDT",
            "signal": "LONG",
            "timeframe": "1h",
            "price": 65000,
            "confidence": 78,
            "risk": "STANDARD",
            "reason": "Sentinel TA confirmed",
            "created_at": "2025-01-15T11:58:00Z",
        },
        {
            "id": 456,
            "symbol": "ETH/USDT",
            "signal": "AGG_LONG",
            "timeframe": "15m",
            "price": 3200,
            "confidence": 85,
            "risk": "ELEVATED",
            "reason": "Bullish divergence",
            "created_at": "2025-01-15T11:59:00Z",
        },
        {
            "id": 789,
            "symbol": "XYZ/USDT",
            "signal": "HOLD",
            "timeframe": "1h",
            "price": 1.0,
            "confidence": 50,
            "risk": "STANDARD",
            "reason": "Flat market",
            "created_at": "2025-01-15T11:59:30Z",
        },
    ],
}


def _mock_response(status_code, body=None):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.text = json.dumps(body or {})
    resp.json.return_value = body or {}
    return resp


# ── 1. Configuration ──────────────────────────────────────────────────────

def test_is_configured():
    bridge = SigBalBotContextBridge()
    assert bridge.is_configured() is True


def test_not_configured_without_url():
    bridge = SigBalBotContextBridge()
    bridge.context_url = ""
    assert bridge.is_configured() is False


def test_not_configured_without_key():
    bridge = SigBalBotContextBridge()
    bridge.api_key = ""
    assert bridge.is_configured() is False


# ── 2. Context URL derivation ─────────────────────────────────────────────

def test_context_url_derivation():
    url = _derive_context_url("https://sigbalbot.up.railway.app/api/v1/signals/trader-sentinel")
    assert url == "https://sigbalbot.up.railway.app/api/v1/context/trader-sentinel"


def test_context_url_derivation_no_signals_path():
    url = _derive_context_url("https://sigbalbot.up.railway.app/api/v1")
    assert url == "https://sigbalbot.up.railway.app/api/v1/context/trader-sentinel"


def test_context_url_derivation_trailing_slash():
    url = _derive_context_url("https://sigbalbot.up.railway.app/api/v1/")
    assert url == "https://sigbalbot.up.railway.app/api/v1/context/trader-sentinel"


# ── 3. Authentication ─────────────────────────────────────────────────────

def test_fetch_sends_bearer_auth():
    bridge = SigBalBotContextBridge()
    with patch("sigbalbot_context_bridge.requests.get") as mock_get:
        mock_get.return_value = _mock_response(200, SAMPLE_CONTEXT)
        bridge.fetch_context()

    call_kwargs = mock_get.call_args
    headers = call_kwargs.kwargs.get("headers", {})
    assert headers["Authorization"] == "Bearer test-bridge-key-789"


def test_fetch_401_returns_none():
    bridge = SigBalBotContextBridge()
    with patch("sigbalbot_context_bridge.requests.get") as mock_get:
        mock_get.return_value = _mock_response(401, {"error": "unauthorized"})
        result = bridge.fetch_context()

    assert result is None
    mock_get.assert_called_once()


def test_fetch_403_returns_none():
    bridge = SigBalBotContextBridge()
    with patch("sigbalbot_context_bridge.requests.get") as mock_get:
        mock_get.return_value = _mock_response(403, {"error": "forbidden"})
        result = bridge.fetch_context()

    assert result is None


# ── 4. Cursor persistence ─────────────────────────────────────────────────

def test_cursor_persisted_after_cycle(tmp_path):
    state_file = tmp_path / "bridge_state.json"
    bridge = SigBalBotContextBridge()
    bridge.processed_ids = []

    with (
        patch("sigbalbot_context_bridge.requests.get") as mock_get,
        patch("sigbalbot_context_bridge._STATE_FILE", state_file),
        patch("sigbalbot_context_bridge._STATE_DIR", tmp_path),
    ):
        mock_get.return_value = _mock_response(200, SAMPLE_CONTEXT)
        bridge.run_cycle()

    assert state_file.exists()
    saved = json.loads(state_file.read_text())
    assert saved["last_cursor"] is not None
    assert "last_poll_at" in saved


def test_cursor_sent_as_since_param():
    bridge = SigBalBotContextBridge()
    bridge.last_cursor = "2025-01-15T10:00:00Z"

    with patch("sigbalbot_context_bridge.requests.get") as mock_get:
        mock_get.return_value = _mock_response(200, {**SAMPLE_CONTEXT, "watchlist": [], "native_signals": []})
        bridge.fetch_context()

    params = mock_get.call_args.kwargs.get("params", {})
    assert params["since"] == "2025-01-15T10:00:00Z"


# ── 5. Signal classification ──────────────────────────────────────────────

def test_classify_sentinel_confirmed():
    bridge = SigBalBotContextBridge()
    signal = {"id": "sentinel-ctx-BTC-USDT-LONG-1700000000", "signal": "LONG"}
    assert bridge._classify_signal(signal) == "sentinel_confirmed"


def test_classify_external():
    bridge = SigBalBotContextBridge()
    signal = {"id": 456, "signal": "AGG_LONG"}
    assert bridge._classify_signal(signal) == "external"


def test_classify_skip_non_directional():
    bridge = SigBalBotContextBridge()
    signal = {"id": 789, "signal": "HOLD"}
    assert bridge._classify_signal(signal) == "skip"


def test_classify_short_signals():
    bridge = SigBalBotContextBridge()
    for sig_type in ("AGG_SHORT", "SHORT", "SELL"):
        signal = {"id": 100, "signal": sig_type}
        assert bridge._classify_signal(signal) == "external"


# ── 6. Duplicate detection ────────────────────────────────────────────────

def test_duplicate_watchlist_skipped(tmp_path):
    bridge = SigBalBotContextBridge()
    wl_key = "wl:BSB/USDT:2025-01-15T11:55:00Z"
    bridge.processed_ids = [wl_key]

    with (
        patch("sigbalbot_context_bridge.requests.get") as mock_get,
        patch("sigbalbot_context_bridge._STATE_FILE", tmp_path / "state.json"),
        patch("sigbalbot_context_bridge._STATE_DIR", tmp_path),
    ):
        ctx = {**SAMPLE_CONTEXT, "native_signals": []}
        mock_get.return_value = _mock_response(200, ctx)
        summary = bridge.run_cycle()

    assert summary["skipped_duplicates"] == 1


def test_duplicate_native_signal_skipped(tmp_path):
    bridge = SigBalBotContextBridge()
    bridge.processed_ids = ["sentinel-ctx-BTC-USDT-LONG-1700000000"]

    with (
        patch("sigbalbot_context_bridge.requests.get") as mock_get,
        patch("sigbalbot_context_bridge._STATE_FILE", tmp_path / "state.json"),
        patch("sigbalbot_context_bridge._STATE_DIR", tmp_path),
    ):
        ctx = {**SAMPLE_CONTEXT, "watchlist": []}
        mock_get.return_value = _mock_response(200, ctx)
        summary = bridge.run_cycle()

    assert summary["skipped_duplicates"] >= 1


# ── 7. Governance advisory ────────────────────────────────────────────────

def test_governance_advisory_generated(tmp_path):
    bridge = SigBalBotContextBridge()
    bridge.processed_ids = []

    with (
        patch("sigbalbot_context_bridge.requests.get") as mock_get,
        patch("sigbalbot_context_bridge._STATE_FILE", tmp_path / "state.json"),
        patch("sigbalbot_context_bridge._STATE_DIR", tmp_path),
    ):
        mock_get.return_value = _mock_response(200, SAMPLE_CONTEXT)
        summary = bridge.run_cycle()

    assert "governance_advisory" in summary
    advisory = summary["governance_advisory"]
    assert advisory["signal_count"] >= 1
    assert advisory["sentiment"] in ("BULLISH", "BEARISH", "MIXED")
    assert "symbols" in advisory


def test_governance_advisory_none_when_no_signals():
    bridge = SigBalBotContextBridge()
    result = bridge._build_governance_advisory([])
    assert result is None


def test_governance_advisory_sentiment_bullish():
    bridge = SigBalBotContextBridge()
    signals = [
        {"signal": "LONG", "confidence": 80, "symbol": "BTC/USDT"},
        {"signal": "BUY", "confidence": 75, "symbol": "ETH/USDT"},
    ]
    advisory = bridge._build_governance_advisory(signals)
    assert advisory["sentiment"] == "BULLISH"
    assert advisory["long_signals"] == 2
    assert advisory["short_signals"] == 0


def test_governance_advisory_sentiment_bearish():
    bridge = SigBalBotContextBridge()
    signals = [
        {"signal": "SHORT", "confidence": 80, "symbol": "BTC/USDT"},
        {"signal": "SELL", "confidence": 75, "symbol": "ETH/USDT"},
    ]
    advisory = bridge._build_governance_advisory(signals)
    assert advisory["sentiment"] == "BEARISH"


# ── 8. Status reporting ───────────────────────────────────────────────────

def test_get_status():
    bridge = SigBalBotContextBridge()
    status = bridge.get_status()

    assert status["configured"] is True
    assert status["poll_interval_s"] == 120
    assert "last_cursor" in status
    assert "processed_ids_count" in status
    assert "cycle_count" in status


# ── 9. Retry on 5xx ───────────────────────────────────────────────────────

def test_503_retries(tmp_path):
    bridge = SigBalBotContextBridge()

    with (
        patch("sigbalbot_context_bridge.requests.get") as mock_get,
        patch("sigbalbot_context_bridge.time.sleep"),
    ):
        mock_get.return_value = _mock_response(503, {"error": "service unavailable"})
        result = bridge.fetch_context()

    assert result is None
    assert mock_get.call_count == 3


# ── 10. Processed IDs bounding ────────────────────────────────────────────

def test_processed_ids_bounded(tmp_path):
    bridge = SigBalBotContextBridge()
    bridge.processed_ids = [str(i) for i in range(600)]

    with (
        patch("sigbalbot_context_bridge.requests.get") as mock_get,
        patch("sigbalbot_context_bridge._STATE_FILE", tmp_path / "state.json"),
        patch("sigbalbot_context_bridge._STATE_DIR", tmp_path),
    ):
        mock_get.return_value = _mock_response(200, {
            "ok": True, "contract_version": "1.0",
            "generated_at": "2025-01-15T12:00:00Z",
            "watchlist": [], "native_signals": [],
        })
        bridge.run_cycle()

    assert len(bridge.processed_ids) <= _MAX_PROCESSED_IDS


# ── 11. Full cycle signal counts ──────────────────────────────────────────

def test_full_cycle_counts(tmp_path):
    bridge = SigBalBotContextBridge()
    bridge.processed_ids = []

    with (
        patch("sigbalbot_context_bridge.requests.get") as mock_get,
        patch("sigbalbot_context_bridge._STATE_FILE", tmp_path / "state.json"),
        patch("sigbalbot_context_bridge._STATE_DIR", tmp_path),
    ):
        mock_get.return_value = _mock_response(200, SAMPLE_CONTEXT)
        summary = bridge.run_cycle()

    assert summary["watchlist_count"] == 1
    assert summary["native_signals_count"] == 3
    assert summary["sentinel_confirmed"] == 1
    assert summary["external_signals"] == 1
    assert summary["skipped_feedback"] == 1


# ── 12. Fetch failure in cycle ────────────────────────────────────────────

def test_fetch_failure_returns_error(tmp_path):
    bridge = SigBalBotContextBridge()

    with (
        patch("sigbalbot_context_bridge.requests.get") as mock_get,
        patch("sigbalbot_context_bridge.time.sleep"),
    ):
        mock_get.side_effect = Exception("connection refused")
        summary = bridge.run_cycle()

    assert summary["error"] == "fetch_failed"
