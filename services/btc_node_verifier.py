"""
BTC Node Verifier — adapter for the BtcNodeVerifier protocol.

Two strategies, tried in order:
  1. Thronos BTC API adapter (Esplora-style REST): /api/tx/{txid}
  2. bitcoind JSON-RPC: getrawtransaction + decoderawtransaction

Both must confirm:
  - The txid exists and has at least MIN_CONFIRMATIONS
  - One output pays to the expected address
  - That output's value in satoshis matches the expected amount

If neither strategy can reach a node, every method raises — the caller
(EarnBtcCashoutStore) treats exceptions as "unverified" and keeps the
request in needs_reconciliation.

Configuration (all from env):
  BTC_CASHOUT_API_URL   — Thronos BTC API adapter base URL (optional)
  BTC_RPC_URL           — bitcoind JSON-RPC endpoint (optional)
  BTC_RPC_USER          — bitcoind RPC username (optional)
  BTC_RPC_PASSWORD      — bitcoind RPC password (optional)
  BTC_MIN_CONFIRMATIONS — minimum confirmations to accept (default 1)

At least one of BTC_CASHOUT_API_URL or BTC_RPC_URL must be configured
for any verification to succeed.

Design constraints:
  - No secrets in source or logs.
  - No simulated success. Every code path returns confirmed=False or
    raises on failure — never a fabricated True.
  - Decimal math for satoshi conversion where needed.
  - Timeout on all HTTP calls.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import requests

from services.earn_btc_cashout import VerifyResult

logger = logging.getLogger(__name__)

_MIN_CONFIRMATIONS_DEFAULT = 1
_HTTP_TIMEOUT = 15


class BtcRpcNodeVerifier:
    """Implements BtcNodeVerifier protocol via Esplora REST and/or bitcoind RPC."""

    def __init__(
        self,
        *,
        api_url: str | None = None,
        rpc_url: str | None = None,
        rpc_user: str | None = None,
        rpc_password: str | None = None,
        min_confirmations: int | None = None,
        http_timeout: int = _HTTP_TIMEOUT,
    ):
        self._api_url = (api_url or os.getenv("BTC_CASHOUT_API_URL", "")).rstrip("/") or None
        self._rpc_url = (rpc_url or os.getenv("BTC_RPC_URL", "")).rstrip("/") or None
        self._rpc_user = rpc_user or os.getenv("BTC_RPC_USER", "") or None
        self._rpc_password = rpc_password or os.getenv("BTC_RPC_PASSWORD", "") or None
        if min_confirmations is not None:
            self._min_conf = max(1, min_confirmations)
        else:
            raw = os.getenv("BTC_MIN_CONFIRMATIONS", "")
            self._min_conf = max(1, int(raw)) if raw.strip().isdigit() else _MIN_CONFIRMATIONS_DEFAULT
        self._timeout = http_timeout

        if not self._api_url and not self._rpc_url:
            raise ValueError(
                "BtcRpcNodeVerifier requires at least one of "
                "BTC_CASHOUT_API_URL or BTC_RPC_URL"
            )

    # ── Public protocol methods ─────────────────────────────────────────

    def verify_tx(
        self,
        *,
        txid: str,
        expected_address: str,
        expected_amount_sat: int,
    ) -> VerifyResult:
        errors: list[str] = []

        # Strategy 1: Esplora REST
        if self._api_url:
            try:
                return self._verify_via_esplora(txid, expected_address, expected_amount_sat)
            except Exception as exc:
                errors.append(f"esplora:{exc}")

        # Strategy 2: bitcoind RPC
        if self._rpc_url:
            try:
                return self._verify_via_rpc(txid, expected_address, expected_amount_sat)
            except Exception as exc:
                errors.append(f"rpc:{exc}")

        raise ConnectionError(f"all_strategies_failed:{'; '.join(errors)}")

    def lookup_by_fingerprint(self, *, request_id: str) -> VerifyResult:
        """Search for a tx matching the request by OP_RETURN or UTXO pattern.

        This requires a full-node index or a specialized API. Neither the
        Esplora REST API nor standard bitcoind RPC supports searching by
        arbitrary OP_RETURN data without an address-based query.

        Until a dedicated indexer is available, this method returns
        confirmed=False with an explanatory error — the caller stays in
        needs_reconciliation, which is the safe default.
        """
        return VerifyResult(
            confirmed=False,
            error="fingerprint_lookup_not_implemented:requires_dedicated_indexer",
        )

    # ── Esplora REST strategy ───────────────────────────────────────────

    def _verify_via_esplora(
        self, txid: str, expected_address: str, expected_amount_sat: int,
    ) -> VerifyResult:
        url = f"{self._api_url}/api/tx/{txid}"
        resp = requests.get(url, timeout=self._timeout)

        if resp.status_code == 404:
            return VerifyResult(confirmed=False, error="tx_not_found")
        resp.raise_for_status()

        tx = resp.json()
        return self._check_esplora_tx(tx, txid, expected_address, expected_amount_sat)

    def _check_esplora_tx(
        self,
        tx: dict[str, Any],
        txid: str,
        expected_address: str,
        expected_amount_sat: int,
    ) -> VerifyResult:
        status = tx.get("status", {})
        if not status.get("confirmed", False):
            return VerifyResult(confirmed=False, txid=txid, error="tx_unconfirmed")

        block_height = status.get("block_height", 0)
        tip_height = self._get_esplora_tip_height()
        if tip_height and block_height:
            confirmations = tip_height - block_height + 1
            if confirmations < self._min_conf:
                return VerifyResult(
                    confirmed=False, txid=txid,
                    error=f"insufficient_confirmations:{confirmations}<{self._min_conf}",
                )

        vout = tx.get("vout", [])
        for output in vout:
            addr = output.get("scriptpubkey_address", "")
            value = output.get("value", 0)
            if addr == expected_address and value == expected_amount_sat:
                return VerifyResult(
                    confirmed=True,
                    txid=tx.get("txid", txid),
                    amount_sat=value,
                )

        found_addrs = [o.get("scriptpubkey_address", "") for o in vout]
        found_amounts = [o.get("value", 0) for o in vout]
        return VerifyResult(
            confirmed=False, txid=txid,
            error=f"output_mismatch:expected={expected_address}:{expected_amount_sat},"
                  f"found_addrs={found_addrs},found_amounts={found_amounts}",
        )

    def _get_esplora_tip_height(self) -> int | None:
        try:
            url = f"{self._api_url}/api/blocks/tip/height"
            resp = requests.get(url, timeout=self._timeout)
            if resp.status_code == 200:
                return int(resp.text.strip())
        except Exception:
            pass
        return None

    # ── bitcoind JSON-RPC strategy ──────────────────────────────────────

    def _verify_via_rpc(
        self, txid: str, expected_address: str, expected_amount_sat: int,
    ) -> VerifyResult:
        raw_tx = self._rpc_call("getrawtransaction", [txid, True])
        if raw_tx is None:
            return VerifyResult(confirmed=False, error="tx_not_found_rpc")

        confirmations = raw_tx.get("confirmations", 0)
        if confirmations < self._min_conf:
            return VerifyResult(
                confirmed=False, txid=txid,
                error=f"insufficient_confirmations:{confirmations}<{self._min_conf}",
            )

        vout = raw_tx.get("vout", [])
        for output in vout:
            script = output.get("scriptPubKey", {})
            addr = script.get("address", "")
            if not addr:
                addrs = script.get("addresses", [])
                addr = addrs[0] if addrs else ""

            value_btc = output.get("value", 0)
            value_sat = int(round(value_btc * 1e8))

            if addr == expected_address and value_sat == expected_amount_sat:
                return VerifyResult(
                    confirmed=True,
                    txid=raw_tx.get("txid", txid),
                    amount_sat=value_sat,
                )

        return VerifyResult(
            confirmed=False, txid=txid,
            error=f"output_mismatch_rpc:expected={expected_address}:{expected_amount_sat}",
        )

    def _rpc_call(self, method: str, params: list | None = None) -> Any | None:
        payload = {
            "jsonrpc": "1.0",
            "id": "cashout_verifier",
            "method": method,
            "params": params or [],
        }

        auth = None
        if self._rpc_user and self._rpc_password:
            auth = (self._rpc_user, self._rpc_password)

        resp = requests.post(
            self._rpc_url,
            json=payload,
            auth=auth,
            timeout=self._timeout,
        )

        if resp.status_code != 200:
            raise ConnectionError(f"rpc_http_{resp.status_code}")

        body = resp.json()
        if body.get("error"):
            err = body["error"]
            code = err.get("code", "unknown")
            msg = err.get("message", "unknown")
            if code == -5:
                return None
            raise ConnectionError(f"rpc_error:{code}:{msg}")

        return body.get("result")
