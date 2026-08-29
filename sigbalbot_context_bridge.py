"""
SigBalBot Context Bridge — Polls the SigBalBot bidirectional context endpoint
for watchlist symbols and Sentinel-confirmed signals, and routes actionable
intelligence into ThronosChain's autonomous trading and Pytheia governance.

Polling contract v1.0:
  GET /api/v1/context/trader-sentinel?since=<cursor>&limit=25
  Authorization: Bearer <SIGBALBOT_API_KEY>

Response:
  { ok, contract_version, generated_at, watchlist[], native_signals[] }

Integration points:
  - autonomous_trading.AutonomousTrading — signal-driven trade execution
  - Pytheia governance — market intelligence advisories
  - Persistent cursor state on disk
"""
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

_STATE_DIR = Path(os.getenv("SIGBALBOT_BRIDGE_STATE_DIR", "/app/data/sigbalbot_bridge"))
_STATE_FILE = _STATE_DIR / "bridge_state.json"

_MAX_PROCESSED_IDS = 500
_SENTINEL_ID_PREFIX = "sentinel-"


def _strip_env_quotes(val: str) -> str:
    return val.strip().strip("'\"")


SIGBALBOT_BASE_URL = _strip_env_quotes(os.getenv("SIGBALBOT_WEBHOOK_URL", ""))
SIGBALBOT_API_KEY = _strip_env_quotes(os.getenv("SIGBALBOT_API_KEY", ""))
SIGBALBOT_POLL_INTERVAL = int(_strip_env_quotes(os.getenv("SIGBALBOT_BRIDGE_POLL_INTERVAL", "120")))
CONTEXT_LIMIT = 25


def _derive_context_url(webhook_url: str) -> str:
    if "/signals/" in webhook_url:
        root = webhook_url.rsplit("/signals/", 1)[0]
    else:
        root = webhook_url.rstrip("/")
    return f"{root}/context/trader-sentinel"


def _derive_status_url(webhook_url: str) -> str:
    if not webhook_url:
        return ""
    return webhook_url.rstrip("/") + "/status"


class SigBalBotContextBridge:
    """Polls SigBalBot context endpoint and bridges signals into ThronosChain."""

    def __init__(self):
        self.context_url = _derive_context_url(SIGBALBOT_BASE_URL) if SIGBALBOT_BASE_URL else ""
        self.status_url = _derive_status_url(SIGBALBOT_BASE_URL) if SIGBALBOT_BASE_URL else ""
        self.api_key = SIGBALBOT_API_KEY
        self.context_capability_confirmed = False
        self.state = self._load_state()
        self.last_cursor: Optional[str] = self.state.get("last_cursor")
        self.processed_ids: List[str] = self.state.get("processed_signal_ids", [])
        self.last_poll_at: Optional[str] = self.state.get("last_poll_at")
        self.cycle_count = 0
        self.total_signals_routed = self.state.get("total_signals_routed", 0)
        self._autonomous_trader = None
        self._milestone_airdrop = None

    def is_configured(self) -> bool:
        return bool(self.context_url and self.api_key)

    def check_context_capability(self) -> bool:
        """Verify SigBalBot exposes the context_feed capability via status endpoint."""
        if not self.status_url or not self.api_key:
            return False
        try:
            resp = requests.get(
                self.status_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )
            if resp.status_code != 200:
                logger.warning("[sigbalbot-bridge] status endpoint HTTP %d — context feed not yet available", resp.status_code)
                return False
            body = resp.json()
            capabilities = body.get("capabilities", {})
            context_feed = capabilities.get("context_feed", "")
            if "/context/trader-sentinel" in context_feed:
                self.context_capability_confirmed = True
                logger.info("[sigbalbot-bridge] context_feed capability confirmed: %s", context_feed)
                return True
            logger.info("[sigbalbot-bridge] context_feed capability not present yet (capabilities=%s)", capabilities)
            return False
        except Exception as exc:
            logger.warning("[sigbalbot-bridge] could not check status endpoint: %s", str(exc)[:120])
            return False

    def _load_state(self) -> Dict[str, Any]:
        if not _STATE_FILE.exists():
            return {"last_cursor": None, "processed_signal_ids": [], "total_signals_routed": 0}
        try:
            with open(_STATE_FILE) as f:
                data = json.load(f)
            if "processed_signal_ids" not in data:
                data["processed_signal_ids"] = []
            return data
        except Exception as exc:
            logger.warning("[sigbalbot-bridge] could not load state: %s", exc)
            return {"last_cursor": None, "processed_signal_ids": [], "total_signals_routed": 0}

    def _save_state(self) -> None:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(_STATE_FILE, "w") as f:
                json.dump({
                    "last_cursor": self.last_cursor,
                    "processed_signal_ids": self.processed_ids,
                    "last_poll_at": self.last_poll_at,
                    "total_signals_routed": self.total_signals_routed,
                    "last_summary": getattr(self, "_last_summary", None),
                }, f)
        except Exception as exc:
            logger.warning("[sigbalbot-bridge] could not save state: %s", exc)

    def _get_milestone_airdrop(self):
        if self._milestone_airdrop is None:
            try:
                from sigbalbot_milestone_airdrop import SigBalBotMilestoneAirdrop
                self._milestone_airdrop = SigBalBotMilestoneAirdrop()
                logger.info("[sigbalbot-bridge] milestone airdrop module loaded")
            except Exception as exc:
                logger.debug("[sigbalbot-bridge] milestone airdrop not available: %s", exc)
        return self._milestone_airdrop

    def _get_autonomous_trader(self):
        if self._autonomous_trader is None:
            try:
                from autonomous_trading import AutonomousTrading
                self._autonomous_trader = AutonomousTrading()
                logger.info("[sigbalbot-bridge] autonomous trading module loaded")
            except Exception as exc:
                logger.debug("[sigbalbot-bridge] autonomous trading not available: %s", exc)
        return self._autonomous_trader

    def fetch_context(self) -> Optional[Dict[str, Any]]:
        """Poll the SigBalBot context endpoint. Returns parsed response or None."""
        if not self.is_configured():
            return None

        params: Dict[str, Any] = {"limit": CONTEXT_LIMIT}
        if self.last_cursor:
            params["since"] = self.last_cursor

        headers = {"Authorization": f"Bearer {self.api_key}"}

        for attempt in range(3):
            try:
                resp = requests.get(
                    self.context_url,
                    params=params,
                    headers=headers,
                    timeout=15,
                )

                if resp.status_code in (401, 403):
                    logger.error(
                        "[sigbalbot-bridge] AUTH ERROR HTTP %d — check SIGBALBOT_API_KEY",
                        resp.status_code,
                    )
                    return None

                if resp.status_code == 200:
                    body = resp.json()
                    if body.get("ok"):
                        return body
                    logger.warning("[sigbalbot-bridge] ok=false: %s", str(body)[:200])
                    return None

                if resp.status_code >= 500 and attempt < 2:
                    logger.warning(
                        "[sigbalbot-bridge] HTTP %d (attempt %d/3), retrying",
                        resp.status_code, attempt + 1,
                    )
                    time.sleep(2 ** (attempt + 1))
                    continue

                logger.warning("[sigbalbot-bridge] HTTP %d: %s", resp.status_code, resp.text[:200])
                return None

            except Exception as exc:
                logger.warning(
                    "[sigbalbot-bridge] network error (attempt %d/3): %s",
                    attempt + 1, str(exc)[:120],
                )
                if attempt < 2:
                    time.sleep(2 ** (attempt + 1))

        return None

    def _is_sentinel_signal(self, signal_id: str) -> bool:
        return str(signal_id).startswith(_SENTINEL_ID_PREFIX)

    def _classify_signal(self, signal: Dict[str, Any]) -> str:
        """Classify a native signal for routing. Returns: sentinel_confirmed, external, skip."""
        sig_id = str(signal.get("id", ""))
        if self._is_sentinel_signal(sig_id):
            return "sentinel_confirmed"
        sig_type = signal.get("signal", "")
        if sig_type in ("AGG_LONG", "AGG_SHORT", "LONG", "SHORT", "BUY", "SELL"):
            return "external"
        return "skip"

    def _route_signal_to_trading(self, signal: Dict[str, Any], classification: str) -> bool:
        """Route an actionable signal to the autonomous trading system."""
        trader = self._get_autonomous_trader()
        if trader is None or not getattr(trader, "auto_trade_enabled", False):
            return False

        symbol = signal.get("symbol", "")
        direction = signal.get("signal", "")
        confidence = int(signal.get("confidence", 0))

        if confidence < 70:
            logger.debug(
                "[sigbalbot-bridge] signal %s confidence %d < 70, skipping trade route",
                signal.get("id"), confidence,
            )
            return False

        base_asset = symbol.split("/")[0] if "/" in symbol else symbol

        if direction in ("LONG", "BUY", "AGG_LONG"):
            from_asset = "USD"
            to_asset = base_asset
        elif direction in ("SHORT", "SELL", "AGG_SHORT"):
            from_asset = base_asset
            to_asset = "USD"
        else:
            return False

        trade_amount = 100.0
        reason = (
            f"SigBalBot {classification} signal: {direction} {symbol} "
            f"(conf={confidence}%, id={signal.get('id')})"
        )

        try:
            success, msg, trade_id = trader.execute_swap(
                from_asset=from_asset,
                to_asset=to_asset,
                amount=trade_amount,
                reason=reason,
                strategy_id=f"sigbalbot-{classification}",
            )
            if success:
                logger.info("[sigbalbot-bridge] trade executed: %s — %s", trade_id, reason)
                return True
            else:
                logger.info("[sigbalbot-bridge] trade not executed: %s", msg)
                return False
        except Exception as exc:
            logger.warning("[sigbalbot-bridge] trade execution error: %s", str(exc)[:120])
            return False

    def _build_governance_advisory(self, signals: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Build a Pytheia governance advisory from accumulated signals."""
        if not signals:
            return None

        long_count = sum(1 for s in signals if s.get("signal") in ("LONG", "BUY", "AGG_LONG"))
        short_count = sum(1 for s in signals if s.get("signal") in ("SHORT", "SELL", "AGG_SHORT"))
        avg_confidence = sum(int(s.get("confidence", 0)) for s in signals) / len(signals)

        sentiment = "BULLISH" if long_count > short_count else "BEARISH" if short_count > long_count else "MIXED"
        symbols_mentioned = list({s.get("symbol", "?") for s in signals})

        return {
            "source": "sigbalbot_context_bridge",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "signal_count": len(signals),
            "sentiment": sentiment,
            "avg_confidence": round(avg_confidence, 1),
            "long_signals": long_count,
            "short_signals": short_count,
            "symbols": symbols_mentioned[:10],
            "summary": (
                f"SigBalBot context: {len(signals)} signals ({long_count}L/{short_count}S), "
                f"sentiment={sentiment}, avg_conf={avg_confidence:.0f}%"
            ),
        }

    def run_cycle(self) -> Dict[str, Any]:
        """One polling cycle — fetch, classify, route. Called by APScheduler."""
        self.cycle_count += 1
        summary: Dict[str, Any] = {
            "ts": time.time(),
            "cycle": self.cycle_count,
            "context_items": 0,
            "watchlist_count": 0,
            "native_signals_count": 0,
            "sentinel_confirmed": 0,
            "external_signals": 0,
            "signals_routed": 0,
            "skipped_duplicates": 0,
            "skipped_feedback": 0,
        }

        if not self.is_configured():
            summary["error"] = "not_configured"
            logger.debug("[sigbalbot-bridge] not configured, skipping cycle")
            return summary

        if not self.context_capability_confirmed:
            available = self.check_context_capability()
            if not available:
                summary["error"] = "capability_not_available"
                logger.info("[sigbalbot-bridge] context_feed not available yet, skipping cycle")
                return summary

        context = self.fetch_context()
        if context is None:
            summary["error"] = "fetch_failed"
            return summary

        watchlist = context.get("watchlist", [])
        native_signals = context.get("native_signals", [])
        generated_at = context.get("generated_at")

        summary["watchlist_count"] = len(watchlist)
        summary["native_signals_count"] = len(native_signals)
        summary["context_items"] = len(watchlist) + len(native_signals)

        logger.info(
            "[sigbalbot-bridge] cycle %d: %d watchlist + %d native signals (cursor=%s)",
            self.cycle_count, len(watchlist), len(native_signals),
            self.last_cursor or "INITIAL",
        )

        processed_set = set(str(i) for i in self.processed_ids)
        new_cursor = generated_at or self.last_cursor
        actionable_signals: List[Dict[str, Any]] = []

        for item in watchlist:
            symbol = item.get("symbol", "?")
            wl_key = f"wl:{symbol}:{item.get('last_scan_at', '')}"
            if wl_key in processed_set:
                summary["skipped_duplicates"] += 1
                continue
            self.processed_ids.append(wl_key)

        for signal in native_signals:
            sig_id = str(signal.get("id", ""))

            if sig_id in processed_set:
                summary["skipped_duplicates"] += 1
                continue

            classification = self._classify_signal(signal)

            if classification == "sentinel_confirmed":
                summary["sentinel_confirmed"] += 1
                actionable_signals.append(signal)
                logger.info(
                    "[sigbalbot-bridge] Sentinel-confirmed signal: id=%s symbol=%s %s conf=%s",
                    sig_id, signal.get("symbol"), signal.get("signal"), signal.get("confidence"),
                )
            elif classification == "external":
                summary["external_signals"] += 1
                actionable_signals.append(signal)
            else:
                summary["skipped_feedback"] += 1

            sig_created = signal.get("created_at")
            if sig_created and (not new_cursor or sig_created > new_cursor):
                new_cursor = sig_created

            self.processed_ids.append(sig_id)

        for signal in actionable_signals:
            routed = self._route_signal_to_trading(signal, self._classify_signal(signal))
            if routed:
                summary["signals_routed"] += 1
                self.total_signals_routed += 1

        # Record qualifying wins for milestone airdrop tracking
        milestone_airdrop = self._get_milestone_airdrop()
        if milestone_airdrop and actionable_signals:
            for signal in actionable_signals:
                airdrop_result = milestone_airdrop.record_win(
                    signal_id=str(signal.get("id", "")),
                    symbol=signal.get("symbol", ""),
                )
                if airdrop_result:
                    summary["milestone_airdrop"] = airdrop_result
                    logger.info(
                        "[sigbalbot-bridge] MILESTONE %d reached — pending allocation %s "
                        "created for %d subscribers (%.6f THR, requires admin approval)",
                        airdrop_result["milestone_number"],
                        airdrop_result.get("batch_id", "?"),
                        airdrop_result["active_subscribers"],
                        airdrop_result.get("total_required_thr", 0.0),
                    )

        advisory = self._build_governance_advisory(actionable_signals)
        if advisory:
            summary["governance_advisory"] = advisory

        if len(self.processed_ids) > _MAX_PROCESSED_IDS:
            self.processed_ids = self.processed_ids[-_MAX_PROCESSED_IDS:]

        self.last_cursor = new_cursor
        self.last_poll_at = datetime.now(timezone.utc).isoformat()
        self._last_summary = summary
        self._save_state()

        logger.info(
            "[sigbalbot-bridge] cycle %d done — %d sentinel-confirmed, %d external, "
            "%d routed, %d dupes skipped",
            self.cycle_count,
            summary["sentinel_confirmed"],
            summary["external_signals"],
            summary["signals_routed"],
            summary["skipped_duplicates"],
        )

        return summary

    def get_status(self) -> Dict[str, Any]:
        """Return bridge status for health/status endpoints."""
        milestone_airdrop = self._get_milestone_airdrop()
        milestone_status = milestone_airdrop.get_status() if milestone_airdrop else None

        return {
            "configured": self.is_configured(),
            "context_capability_confirmed": self.context_capability_confirmed,
            "context_url": self.context_url if self.is_configured() else None,
            "poll_interval_s": SIGBALBOT_POLL_INTERVAL,
            "last_cursor": self.last_cursor,
            "last_poll_at": self.last_poll_at,
            "cycle_count": self.cycle_count,
            "total_signals_routed": self.total_signals_routed,
            "processed_ids_count": len(self.processed_ids),
            "last_summary": getattr(self, "_last_summary", None),
            "milestone_airdrop": milestone_status,
        }
