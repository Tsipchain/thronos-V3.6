"""Local Bitcoin Core node agent for the canonical Thronos BTC Observer.

Runs beside bitcoind. RPC and ZMQ remain loopback-only. The only network
egress is authenticated HTTPS to the public Thronos BTC adapter.

This process is read-only with respect to Bitcoin Core: no wallet unlock,
signing, private-key access, transaction creation, or broadcast RPC exists.
"""
from __future__ import annotations

import argparse
import base64
from decimal import Decimal
import json
import logging
import os
from pathlib import Path
import socket
import struct
import threading
import time
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from services.btc_observer import BtcObserver, BtcObserverError, BtcObserverStore
from services.btc_deposit_outbox import BtcDepositOutbox, BtcDepositOutboxError
from services.btc_provider_revenue import (
    MAINNET_GENESIS_HASH,
    PURPOSE as PROVIDER_REVENUE_PURPOSE,
    REVENUE_ADDRESS,
    ProviderRevenueStore,
)

logger = logging.getLogger("btc_node_agent")

RPC_METHODS = frozenset(
    {
        "getblockchaininfo",
        "getblockcount",
        "getblockhash",
        "getblock",
        "getblockheader",
        "getbestblockhash",
        "decoderawtransaction",
        "getmempoolentry",
        "getrawmempool",
        "getrawtransaction",
        "getzmqnotifications",
        "validateaddress",
    }
)


class NodeAgentError(RuntimeError):
    pass


def _loopback_rpc_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "http":
        raise NodeAgentError("bitcoin_rpc_must_use_local_http")
    host = (parsed.hostname or "").lower()
    allowed = {"127.0.0.1", "::1", "localhost"}
    if host not in allowed:
        raise NodeAgentError("bitcoin_rpc_must_be_loopback")
    return value.rstrip("/")


def _https_adapter_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise NodeAgentError("adapter_url_must_use_https")
    return value.rstrip("/")


def _default_cookie_file() -> Path | None:
    explicit = os.getenv("BITCOIN_RPC_COOKIE_FILE", "").strip()
    if explicit:
        return Path(explicit)

    # Bitcoin Core 28+ defaults to LOCALAPPDATA on Windows, but it keeps
    # using the legacy APPDATA/Roaming directory when that old directory
    # already exists. Check both for compatibility with upgraded nodes.
    roaming = os.getenv("APPDATA", "").strip()
    if roaming:
        candidate = Path(roaming) / "Bitcoin" / ".cookie"
        if candidate.exists():
            return candidate

    local = os.getenv("LOCALAPPDATA", "").strip()
    if local:
        candidate = Path(local) / "Bitcoin" / ".cookie"
        if candidate.exists():
            return candidate

    candidate = Path.home() / ".bitcoin" / ".cookie"
    return candidate if candidate.exists() else None


class BitcoinCoreRpc:
    def __init__(self) -> None:
        self.url = _loopback_rpc_url(
            os.getenv("BITCOIN_RPC_URL", "http://127.0.0.1:8332")
        )
        self.user = os.getenv("BITCOIN_RPC_USER", "")
        self.password = os.getenv("BITCOIN_RPC_PASSWORD", "")
        self.cookie_file = _default_cookie_file()
        self._counter = 0

    def _credentials(self) -> str:
        if self.user or self.password:
            if not self.user or not self.password:
                raise NodeAgentError("incomplete_bitcoin_rpc_credentials")
            return f"{self.user}:{self.password}"
        if not self.cookie_file or not self.cookie_file.exists():
            raise NodeAgentError("bitcoin_rpc_cookie_not_found")
        value = self.cookie_file.read_text(encoding="utf-8").strip()
        if ":" not in value:
            raise NodeAgentError("invalid_bitcoin_rpc_cookie")
        return value

    def call(self, method: str, params: list[Any]) -> Any:
        if method not in RPC_METHODS:
            raise NodeAgentError("bitcoin_rpc_method_not_allowed")
        self._counter += 1
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": self._counter, "method": method, "params": params}
        ).encode("utf-8")
        auth = base64.b64encode(self._credentials().encode("utf-8")).decode("ascii")
        req = Request(
            self.url,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Basic {auth}",
            },
        )
        max_response = 64 * 1024 * 1024 if method == "getblock" else 16 * 1024 * 1024
        try:
            with urlopen(req, timeout=30 if method == "getblock" else 10) as response:
                raw = response.read(max_response + 1)
        except Exception as exc:
            raise NodeAgentError("bitcoin_rpc_unreachable") from exc
        if len(raw) > max_response:
            raise NodeAgentError("bitcoin_rpc_response_too_large")
        try:
            body = json.loads(raw, parse_float=Decimal)
        except json.JSONDecodeError as exc:
            raise NodeAgentError("invalid_bitcoin_rpc_response") from exc
        if body.get("error"):
            raise NodeAgentError(f"bitcoin_rpc_error:{body['error']}")
        return body.get("result")


class AdapterClient:
    def __init__(self) -> None:
        self.base_url = _https_adapter_url(
            os.getenv(
                "BTC_ADAPTER_URL",
                "https://thronos-btc-api-adapter-production.up.railway.app",
            )
        )
        self.token = os.getenv("BTC_ADAPTER_NODE_AGENT_TOKEN", "").strip()

    def push_tip(self, *, height: int, block_hash: str, sequence: int) -> None:
        if not self.token:
            raise NodeAgentError("btc_adapter_node_agent_token_missing")
        payload = json.dumps(
            {"height": height, "hash": block_hash, "sequence": sequence},
            separators=(",", ":"),
        ).encode("utf-8")
        req = Request(
            f"{self.base_url}/api/node-agent/tip",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Node-Agent-Token": self.token,
            },
        )
        try:
            with urlopen(req, timeout=10) as response:
                raw = response.read(1024 * 1024 + 1)
                status = getattr(response, "status", 200)
        except Exception as exc:
            raise NodeAgentError("btc_adapter_push_failed") from exc
        if status < 200 or status >= 300 or len(raw) > 1024 * 1024:
            raise NodeAgentError("btc_adapter_rejected_tip")


    def push_deposit(self, payload: dict[str, Any]) -> str:
        if not self.token:
            raise NodeAgentError("btc_adapter_node_agent_token_missing")
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        req = Request(
            f"{self.base_url}/api/node-agent/deposits",
            data=encoded,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Node-Agent-Token": self.token,
            },
        )
        try:
            with urlopen(req, timeout=10) as response:
                raw = response.read(1024 * 1024 + 1)
                status = getattr(response, "status", 200)
        except Exception as exc:
            raise NodeAgentError("btc_adapter_deposit_push_failed") from exc
        if status < 200 or status >= 300 or len(raw) > 1024 * 1024:
            raise NodeAgentError("btc_adapter_rejected_deposit")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise NodeAgentError("btc_adapter_invalid_deposit_ack") from exc
        if not isinstance(body, dict) or body.get("accepted") is not True:
            raise NodeAgentError("btc_adapter_invalid_deposit_ack")
        if body.get("credit_applied") is not False:
            raise NodeAgentError("btc_adapter_unexpected_credit_side_effect")
        result = str(body.get("status") or "")
        if result not in {"accepted", "duplicate"}:
            raise NodeAgentError("btc_adapter_invalid_deposit_ack")
        return result


def load_watch_registry(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        raise NodeAgentError("btc_watch_registry_not_found")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        raise NodeAgentError("invalid_btc_watch_registry") from exc
    if not isinstance(data, dict):
        raise NodeAgentError("invalid_btc_watch_registry")
    result: dict[str, str] = {}
    for address, owner_ref in data.items():
        address = str(address).strip()
        owner_ref = str(owner_ref).strip()
        if not address or not owner_ref or len(address) > 128 or len(owner_ref) > 200:
            raise NodeAgentError("invalid_btc_watch_registry_entry")
        if address == REVENUE_ADDRESS and owner_ref != PROVIDER_REVENUE_PURPOSE:
            raise NodeAgentError("btc_provider_revenue_purpose_mismatch")
        if owner_ref == PROVIDER_REVENUE_PURPOSE and address != REVENUE_ADDRESS:
            raise NodeAgentError("btc_provider_revenue_address_mismatch")
        result[address] = owner_ref
    if PROVIDER_REVENUE_PURPOSE in result.values() and os.getenv(
        "BTC_PROVIDER_REVENUE_PAYOUT_CONFIG_VERIFIED", ""
    ).strip().lower() not in {"1", "true", "yes", "on"}:
        raise NodeAgentError("btc_provider_revenue_payout_config_not_verified")
    return result


class LocalBitcoinNodeAgent:
    def __init__(
        self,
        *,
        db_path: str,
        watch_registry: dict[str, str],
        rpc: BitcoinCoreRpc | None = None,
        adapter: AdapterClient | None = None,
        minimum_confirmations: int = 6,
    ) -> None:
        self.rpc = rpc or BitcoinCoreRpc()
        self.adapter = adapter or AdapterClient()
        self.db_path = db_path
        self.watch_registry = dict(watch_registry)
        self.minimum_confirmations = int(minimum_confirmations)
        if self.minimum_confirmations < 1:
            raise NodeAgentError("invalid_btc_minimum_confirmations")
        self.store = BtcObserverStore(db_path)
        self.provider_revenue_store = (
            ProviderRevenueStore(db_path)
            if PROVIDER_REVENUE_PURPOSE in self.watch_registry.values()
            else None
        )
        self.observer = (
            BtcObserver(
                self.rpc,
                self.store,
                watch_registry,
                minimum_confirmations=self.minimum_confirmations,
            )
            if watch_registry
            else None
        )
        self.outbox: BtcDepositOutbox | None = None
        self.network = ""
        self.genesis_hash = ""
        self.delivery_enabled = os.getenv(
            "BTC_DEPOSIT_DELIVERY_ENABLED", "0"
        ).strip().lower() in {"1", "true", "yes", "on"}
        self._zmq_sequences: dict[bytes, int] = {}
        self._event_lock = threading.RLock()

    def preflight(self) -> dict[str, Any]:
        info = self.rpc.call("getblockchaininfo", [])
        if not isinstance(info, dict):
            raise NodeAgentError("invalid_getblockchaininfo")
        if info.get("chain") != "main":
            raise NodeAgentError("bitcoin_node_not_mainnet")
        if bool(info.get("initialblockdownload")):
            raise NodeAgentError("bitcoin_node_still_syncing")

        blocks = info.get("blocks")
        headers = info.get("headers")
        if (
            isinstance(blocks, bool) or not isinstance(blocks, int)
            or isinstance(headers, bool) or not isinstance(headers, int)
            or blocks < 0 or headers < 0 or blocks != headers
        ):
            raise NodeAgentError("bitcoin_node_tip_not_synced")

        genesis_hash = str(self.rpc.call("getblockhash", [0]) or "").lower()
        if len(genesis_hash) != 64 or any(
            ch not in "0123456789abcdef" for ch in genesis_hash
        ):
            raise NodeAgentError("invalid_bitcoin_genesis_hash")
        if self.provider_revenue_store is not None and genesis_hash != MAINNET_GENESIS_HASH:
            raise NodeAgentError("bitcoin_mainnet_genesis_mismatch")

        for address in self.watch_registry:
            result = self.rpc.call("validateaddress", [address])
            if not isinstance(result, dict) or result.get("isvalid") is not True:
                raise NodeAgentError("invalid_or_wrong_network_watch_address")

        self.network = "main"
        self.genesis_hash = genesis_hash
        self.outbox = BtcDepositOutbox(
            self.db_path,
            network=self.network,
            genesis_hash=self.genesis_hash,
        )

        return {
            "chain": "main",
            "genesis_hash": genesis_hash,
            "blocks": blocks,
            "pruned": bool(info.get("pruned")),
            "synced": True,
        }

    def current_tip(self) -> tuple[int, str]:
        raw_height = self.rpc.call("getblockcount", [])
        if isinstance(raw_height, bool) or not isinstance(raw_height, int) or raw_height < 0:
            raise NodeAgentError("invalid_bitcoin_tip_height")
        height = raw_height
        block_hash = str(self.rpc.call("getblockhash", [height])).lower()
        if len(block_hash) != 64 or any(ch not in "0123456789abcdef" for ch in block_hash):
            raise NodeAgentError("invalid_bitcoin_tip_hash")
        return height, block_hash

    def recovery_status(self) -> dict[str, Any]:
        """Return only non-secret observer recovery state for operators."""
        return BtcObserverStore.read_recovery_status(self.db_path)

    def acknowledge_unverified_history_before(self, height: int) -> dict[str, Any]:
        """Scan one explicit boundary while permanently labelling earlier history.

        This enables observation to continue on a pruned node; it never enables
        enqueue/delivery and never describes the missing interval as reconciled.
        """
        if self.observer is None:
            raise NodeAgentError("btc_watch_registry_required")
        if isinstance(height, bool) or not isinstance(height, int) or height < 1:
            raise NodeAgentError("invalid_btc_history_boundary")
        if self.store.checkpoint() is not None:
            raise NodeAgentError("btc_scan_checkpoint_already_exists")
        tip_height, _ = self.current_tip()
        if height > tip_height:
            raise NodeAgentError("btc_history_boundary_ahead_of_chain")

        # Persist the fail-closed classification before attempting any scan.
        self.store.set_meta_int("observer_unverified_history", 1)
        self.store.set_meta_int("observer_reconciliation_required", 1)
        self.store.record_diagnostic(
            "operator_unverified_history_boundary",
            range_start=0,
            range_end=height - 1,
            detail="Operator acknowledged that history before this boundary is unverified",
        )
        block_hash = str(self.rpc.call("getblockhash", [height]) or "").lower()
        try:
            block = self.rpc.call("getblock", [block_hash, 2])
        except Exception as exc:
            raise NodeAgentError(
                f"btc_block_history_unavailable:{height}:{height}"
            ) from exc
        if (
            not isinstance(block, dict)
            or str(block.get("hash") or "").lower() != block_hash
            or block.get("height") != height
        ):
            raise NodeAgentError("btc_block_identity_mismatch")
        self.observer.observe_block(block)
        self.store.save_checkpoint(height, block_hash, observed_at=int(time.time()))
        return {"boundary_height": height, "unverified_through_height": height - 1}

    def publish_tip(self) -> tuple[int, str, int]:
        """Publish adapter liveness state, never the block-scan checkpoint."""
        with self._event_lock:
            height, block_hash = self.current_tip()
            sequence = self.store.next_sequence()
            self.adapter.push_tip(height=height, block_hash=block_hash, sequence=sequence)
            self.store.save_published_tip(
                height, block_hash, sequence, published_at=int(time.time())
            )
            return height, block_hash, sequence

    def publish_heartbeat(self) -> tuple[int, str, int]:
        """Refresh adapter liveness without advancing the observer checkpoint."""
        return self.publish_tip()

    def _record_reconciliation_failure(
        self,
        category: str,
        detail: str,
        *,
        topic: str | None = None,
        expected_sequence: int | None = None,
        observed_sequence: int | None = None,
        range_start: int | None = None,
        range_end: int | None = None,
        zmq_gap: bool = False,
    ) -> int:
        self.store.set_meta_int("observer_reconciliation_required", 1)
        if zmq_gap:
            self.store.set_meta_int("zmq_gap_detected", 1)
        return self.store.record_diagnostic(
            category,
            topic=topic,
            expected_sequence=expected_sequence,
            observed_sequence=observed_sequence,
            range_start=range_start,
            range_end=range_end,
            detail=detail,
        )

    def enqueue_confirmed_deposits(self) -> int:
        if self.observer is None or self.outbox is None:
            return 0
        if any(
            self.store.get_meta_int(key)
            for key in (
                "observer_reconciliation_required",
                "zmq_gap_detected",
                "observer_unverified_history",
            )
        ):
            logger.warning(
                "BTC deposit enqueue remains disabled by durable reconciliation state"
            )
            return 0
        return self.outbox.enqueue_confirmed(
            minimum_confirmations=self.minimum_confirmations
        )

    def reconcile_provider_revenue(self) -> int:
        """Refresh statement matches; never enqueue, deliver, or credit them."""
        if self.provider_revenue_store is None:
            return 0
        return len(self.provider_revenue_store.reconcile_all())

    def deliver_outbox(self, *, limit: int = 10) -> int:
        if not self.delivery_enabled or self.outbox is None:
            return 0
        if any(
            self.store.get_meta_int(key)
            for key in (
                "observer_reconciliation_required",
                "zmq_gap_detected",
                "observer_unverified_history",
            )
        ):
            logger.warning(
                "BTC deposit delivery remains disabled by durable reconciliation state"
            )
            return 0
        delivered = 0
        for _ in range(max(1, int(limit))):
            item = self.outbox.claim_next()
            if item is None:
                break
            try:
                self.adapter.push_deposit(item.payload)
                self.outbox.acknowledge(item.idempotency_key)
                delivered += 1
            except (NodeAgentError, BtcDepositOutboxError) as exc:
                self.outbox.fail(item.idempotency_key, str(exc))
                logger.error(
                    "BTC deposit outbox delivery failed closed key=%s",
                    item.idempotency_key,
                )
                break
        return delivered


    def _recover_from_checkpoint(self) -> tuple[int, int]:
        """Backfill blocks missed while the local agent was offline.

        Only a bounded recent gap is replayed. A checkpoint reorg or excessive
        gap fails closed instead of guessing across a pruned boundary.
        """
        if self.observer is None:
            return (0, 0)

        checkpoint = self.store.checkpoint()
        if not checkpoint:
            current_height, _ = self.current_tip()
            self._record_reconciliation_failure(
                "missing_scan_checkpoint",
                "No fully scanned block boundary is recorded",
                range_start=0,
                range_end=current_height,
            )
            raise NodeAgentError("btc_scan_checkpoint_missing")

        current_height, _current_hash = self.current_tip()
        previous_height = int(checkpoint["block_height"])
        previous_hash = str(checkpoint["block_hash"]).lower()
        max_blocks = max(1, int(os.getenv("BTC_BACKFILL_MAX_BLOCKS", "144")))

        if previous_height > current_height:
            self._record_reconciliation_failure(
                "checkpoint_ahead_of_chain",
                "The fully scanned checkpoint is above the canonical tip",
                range_start=current_height,
                range_end=previous_height,
            )
            raise NodeAgentError("btc_checkpoint_ahead_of_chain")

        canonical_previous = str(
            self.rpc.call("getblockhash", [previous_height])
        ).lower()
        if canonical_previous != previous_hash:
            self._record_reconciliation_failure(
                "checkpoint_reorg",
                "The recorded fully scanned block is no longer canonical",
                range_start=previous_height,
                range_end=current_height,
            )
            self.observer.reconcile_tip()
            raise NodeAgentError("btc_checkpoint_reorg_requires_manual_reconciliation")

        gap = current_height - previous_height
        if gap > max_blocks:
            self._record_reconciliation_failure(
                "scan_range_exceeds_bound",
                "Required block recovery exceeds BTC_BACKFILL_MAX_BLOCKS",
                range_start=previous_height + 1,
                range_end=current_height,
            )
            raise NodeAgentError("btc_checkpoint_gap_exceeds_backfill_limit")

        blocks_scanned = 0
        matched_outputs = 0
        if gap:
            self.store.begin_reconciliation(
                range_start=previous_height + 1,
                target_height=current_height,
                previous_height=previous_height,
            )
        for height in range(previous_height + 1, current_height + 1):
            block_hash = str(self.rpc.call("getblockhash", [height])).lower()
            try:
                block = self.rpc.call("getblock", [block_hash, 2])
            except Exception as exc:
                self._record_reconciliation_failure(
                    "block_history_unavailable",
                    "A required canonical block could not be read; pruning may be the cause",
                    range_start=height,
                    range_end=current_height,
                )
                raise NodeAgentError(
                    f"btc_block_history_unavailable:{height}:{current_height}"
                ) from exc
            if not isinstance(block, dict):
                self._record_reconciliation_failure(
                    "block_history_unavailable",
                    "A required canonical block response was incomplete",
                    range_start=height,
                    range_end=current_height,
                )
                raise NodeAgentError("getblock_failed")
            if str(block.get("hash") or "").lower() != block_hash or block.get("height") != height:
                self._record_reconciliation_failure(
                    "conflicting_block_observation",
                    "Canonical hash/height did not match the decoded block",
                    range_start=height,
                    range_end=height,
                )
                raise NodeAgentError("btc_block_identity_mismatch")
            matched_outputs += len(self.observer.observe_block(block))
            self.store.advance_checkpoint(
                height,
                block_hash,
                observed_at=int(time.time()),
                expected_previous_height=height - 1,
            )
            blocks_scanned += 1

        self.observer.reconcile_tip()
        self.reconcile_provider_revenue()
        self.enqueue_confirmed_deposits()
        return blocks_scanned, matched_outputs

    def recover_from_checkpoint(self) -> tuple[int, int]:
        with self._event_lock:
            return self._recover_from_checkpoint()

    def reconcile_mempool(self) -> tuple[int, int]:
        """Observe a bounded startup snapshot; never silently truncate it."""
        if self.observer is None:
            return (0, 0)
        txids = self.rpc.call("getrawmempool", [])
        if not isinstance(txids, list):
            self._record_reconciliation_failure(
                "mempool_snapshot_invalid", "getrawmempool did not return a list"
            )
            raise NodeAgentError("invalid_btc_mempool_snapshot")
        limit = max(1, int(os.getenv("BTC_MEMPOOL_RECONCILE_MAX_TXS", "10000")))
        if len(txids) > limit:
            self._record_reconciliation_failure(
                "mempool_snapshot_exceeds_bound",
                "Startup mempool exceeds BTC_MEMPOOL_RECONCILE_MAX_TXS",
                range_start=0,
                range_end=len(txids),
            )
            raise NodeAgentError("btc_mempool_snapshot_exceeds_limit")
        matched = 0
        for txid in txids:
            value = str(txid or "").lower()
            if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                self._record_reconciliation_failure(
                    "mempool_snapshot_invalid", "A mempool txid was invalid"
                )
                raise NodeAgentError("invalid_btc_mempool_txid")
            raw = self.rpc.call("getrawtransaction", [value, True])
            if not isinstance(raw, dict) or str(raw.get("txid") or "").lower() != value:
                self._record_reconciliation_failure(
                    "mempool_transaction_unavailable",
                    "A transaction disappeared or conflicted during the bounded snapshot",
                )
                raise NodeAgentError("btc_mempool_transaction_unavailable")
            matched += len(self.observer.observe_decoded_transaction(raw))
        return len(txids), matched

    def _check_zmq_message_sequence(self, topic: bytes, raw_seq: bytes) -> bool:
        """Return True when Bitcoin Core's per-topic ZMQ sequence has a gap."""
        if len(raw_seq) != 4:
            self._record_reconciliation_failure(
                "zmq_invalid_sequence_frame",
                "Bitcoin Core ZMQ sequence frame was not four bytes",
                topic=topic.decode("ascii", errors="replace")[:100],
                zmq_gap=True,
            )
            raise NodeAgentError("invalid_zmq_message_sequence")
        current = struct.unpack("<I", raw_seq)[0]
        previous = self._zmq_sequences.get(topic)
        self._zmq_sequences[topic] = current
        if previous is None:
            return False
        expected = (previous + 1) & 0xFFFFFFFF
        if current == expected:
            return False
        topic_name = topic.decode("ascii", errors="replace")[:100]
        self._record_reconciliation_failure(
            "zmq_sequence_gap",
            "Bitcoin Core per-topic ZMQ sequence was not contiguous",
            topic=topic_name,
            expected_sequence=expected,
            observed_sequence=current,
            zmq_gap=True,
        )
        return True

    def _handle_sequence(self, body: bytes) -> dict[str, Any]:
        """Handle Bitcoin Core sequence A/R/C/D notifications.

        A/R include a mempool sequence number; C/D are block connect/disconnect.
        """
        if len(body) not in (33, 41):
            raise NodeAgentError("invalid_zmq_sequence_body")

        object_hash = body[:32].hex()
        label = chr(body[32])
        mempool_sequence = (
            struct.unpack("<Q", body[33:41])[0] if len(body) == 41 else None
        )

        if label in ("A", "R") and len(body) != 41:
            raise NodeAgentError("invalid_zmq_mempool_sequence_body")
        if label in ("C", "D") and len(body) != 33:
            raise NodeAgentError("invalid_zmq_block_sequence_body")
        if label not in ("A", "R", "C", "D"):
            raise NodeAgentError("unsupported_zmq_sequence_label")

        changed = 0
        if self.observer is not None and label == "A":
            # getrawtransaction without txindex is sufficient for mempool txs.
            raw = self.rpc.call("getrawtransaction", [object_hash, True])
            if isinstance(raw, dict):
                changed = len(self.observer.observe_decoded_transaction(raw))
        elif self.observer is not None and label == "R":
            rows = self.store.mark_mempool_removed(
                object_hash, observed_at=int(time.time())
            )
            changed = len([row for row in rows if row.block_hash is None])
        elif self.observer is not None and label == "D":
            self._record_reconciliation_failure(
                "zmq_block_disconnect",
                "Bitcoin Core reported a block disconnect; canonical review is required",
                topic="sequence",
                zmq_gap=True,
            )
            self.observer.reconcile_tip()

        if self.provider_revenue_store is not None and label in ("A", "R", "C", "D"):
            self.reconcile_provider_revenue()

        return {
            "label": label,
            "hash": object_hash,
            "mempool_sequence": mempool_sequence,
            "changed": changed,
        }

    def handle_sequence(self, body: bytes) -> dict[str, Any]:
        with self._event_lock:
            return self._handle_sequence(body)

    def record_malformed_zmq_frames(self, frames: list[bytes]) -> None:
        topic = (
            frames[0].decode("ascii", errors="replace")[:100]
            if frames else "unknown"
        )
        self._record_reconciliation_failure(
            "zmq_malformed_frames",
            "ZMQ multipart message had fewer than three frames",
            topic=topic,
            zmq_gap=True,
        )

    def probe_zmq(self, timeout_seconds: int = 10) -> dict[str, Any]:
        """Verify local ZMQ configuration and observe traffic without BTC actions."""
        try:
            import zmq
        except ImportError as exc:
            raise NodeAgentError("pyzmq_not_installed") from exc

        configured = self.rpc.call("getzmqnotifications", [])
        if not isinstance(configured, list):
            raise NodeAgentError("invalid_getzmqnotifications")

        configured_types = {
            str(item.get("type"))
            for item in configured
            if isinstance(item, dict) and item.get("type")
        }
        required = {"pubhashblock", "pubrawtx", "pubsequence"}
        missing = sorted(required - configured_types)
        if missing:
            raise NodeAgentError("missing_required_zmq_notifications:" + ",".join(missing))

        endpoints = {
            "hashblock": os.getenv("BTC_ZMQ_HASHBLOCK", "tcp://127.0.0.1:28332"),
            "rawtx": os.getenv("BTC_ZMQ_RAWTX", "tcp://127.0.0.1:28333"),
            "sequence": os.getenv("BTC_ZMQ_SEQUENCE", "tcp://127.0.0.1:28334"),
        }
        context = zmq.Context.instance()
        sock = context.socket(zmq.SUB)
        try:
            sock.setsockopt(zmq.RCVHWM, 10000)
            for endpoint in endpoints.values():
                parsed = urlparse(endpoint)
                if parsed.scheme != "tcp" or parsed.hostname not in {
                    "127.0.0.1", "::1", "localhost"
                }:
                    raise NodeAgentError("bitcoin_zmq_must_be_loopback")
                sock.connect(endpoint)
            for topic in (b"hashblock", b"rawtx", b"sequence"):
                sock.setsockopt(zmq.SUBSCRIBE, topic)

            poller = zmq.Poller()
            poller.register(sock, zmq.POLLIN)
            deadline = time.time() + max(1, int(timeout_seconds))
            observed: set[str] = set()
            while time.time() < deadline:
                remaining_ms = max(1, int((deadline - time.time()) * 1000))
                events = dict(poller.poll(min(remaining_ms, 1000)))
                if sock not in events:
                    continue
                frames = sock.recv_multipart()
                if len(frames) >= 2:
                    observed.add(frames[0].decode("ascii", errors="replace"))
            return {
                "configured": sorted(configured_types),
                "observed": sorted(observed),
                "timeout_seconds": int(timeout_seconds),
            }
        finally:
            sock.close(0)

    def handle_rawtx(self, raw_tx: bytes) -> int:
        with self._event_lock:
            if self.observer is None:
                return 0
            decoded = self.rpc.call("decoderawtransaction", [raw_tx.hex()])
            if not isinstance(decoded, dict):
                raise NodeAgentError("decoderawtransaction_failed")
            changed = len(self.observer.observe_decoded_transaction(decoded))
            self.reconcile_provider_revenue()
            return changed

    def handle_new_block(self) -> tuple[int, int, str, int]:
        with self._event_lock:
            _blocks, matched = self.recover_from_checkpoint()
            height, block_hash, sequence = self.publish_heartbeat()
            return matched, height, block_hash, sequence

    def run_zmq(self) -> None:
        try:
            import zmq
        except ImportError as exc:
            raise NodeAgentError("pyzmq_not_installed") from exc

        endpoints = {
            "hashblock": os.getenv("BTC_ZMQ_HASHBLOCK", "tcp://127.0.0.1:28332"),
            "rawtx": os.getenv("BTC_ZMQ_RAWTX", "tcp://127.0.0.1:28333"),
            "sequence": os.getenv("BTC_ZMQ_SEQUENCE", "tcp://127.0.0.1:28334"),
        }
        for endpoint in endpoints.values():
            parsed = urlparse(endpoint)
            if parsed.scheme != "tcp" or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
                raise NodeAgentError("bitcoin_zmq_must_be_loopback")

        heartbeat_seconds = max(
            10, int(os.getenv("BTC_ADAPTER_HEARTBEAT_SECONDS", "30"))
        )
        context = zmq.Context.instance()
        sock = context.socket(zmq.SUB)
        sock.setsockopt(zmq.RCVHWM, 10000)
        for endpoint in endpoints.values():
            sock.connect(endpoint)
        for topic in (b"hashblock", b"rawtx", b"sequence"):
            sock.setsockopt(zmq.SUBSCRIBE, topic)

        poller = zmq.Poller()
        poller.register(sock, zmq.POLLIN)
        next_heartbeat = time.time() + heartbeat_seconds

        logger.info("BTC node agent listening on local Bitcoin Core ZMQ")
        while True:
            try:
                events = dict(poller.poll(1000))
                if sock in events:
                    frames = sock.recv_multipart()
                    if len(frames) < 3:
                        self.record_malformed_zmq_frames(frames)
                        logger.error("Malformed Bitcoin Core ZMQ frame set; reconciliation required")
                    else:
                        topic, body, raw_seq = frames[0], frames[1], frames[2]
                        if self._check_zmq_message_sequence(topic, raw_seq):
                            self.store.set_meta_int("zmq_gap_detected", 1)
                            self.store.set_meta_int("observer_reconciliation_required", 1)
                            logger.error(
                                "Detected lost Bitcoin Core ZMQ message(s) on topic=%s",
                                topic.decode("ascii", errors="replace"),
                            )

                        if topic == b"rawtx":
                            count = self.handle_rawtx(body)
                            if count:
                                logger.info("Observed %d watched BTC output(s)", count)
                        elif topic == b"hashblock":
                            matched, height, _hash, _seq = self.handle_new_block()
                            logger.info(
                                "Reconciled Bitcoin block %d; watched outputs=%d",
                                height, matched,
                            )
                        elif topic == b"sequence":
                            event = self.handle_sequence(body)
                            if event["label"] in ("R", "D") or event["changed"]:
                                logger.info(
                                    "Bitcoin sequence event label=%s changed=%s",
                                    event["label"], event["changed"],
                                )

                if time.time() >= next_heartbeat:
                    height, _hash, sequence = self.publish_heartbeat()
                    delivered = self.deliver_outbox()
                    logger.info(
                        "Bitcoin heartbeat height=%d sequence=%d deposit_acks=%d",
                        height, sequence, delivered,
                    )
                    next_heartbeat = time.time() + heartbeat_seconds
            except (NodeAgentError, BtcObserverError, BtcDepositOutboxError) as exc:
                logger.error("BTC node-agent event failed closed: %s", exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Thronos local Bitcoin node observer")
    parser.add_argument("--once", action="store_true", help="preflight + publish one tip")
    parser.add_argument(
        "--db",
        default=os.getenv("BTC_OBSERVER_DB", "./data/btc_observer.db"),
        help="durable observer SQLite path",
    )
    parser.add_argument(
        "--watch-registry",
        default=os.getenv("BTC_WATCH_REGISTRY", ""),
        help="JSON mapping of watched BTC address -> owner/intention ref",
    )
    parser.add_argument(
        "--probe-zmq",
        nargs="?",
        const=10,
        type=int,
        help="verify configured local ZMQ and observe topics for N seconds (default 10)",
    )
    parser.add_argument(
        "--recovery-status",
        action="store_true",
        help="print non-secret durable checkpoint/gap status and exit",
    )
    parser.add_argument(
        "--provider-revenue-report",
        action="store_true",
        help="print the existing CPX/TimeWall reconciliation report read-only and exit",
    )
    parser.add_argument(
        "--acknowledge-unverified-history-before-height",
        type=int,
        metavar="HEIGHT",
        help=(
            "scan HEIGHT as the initial boundary and permanently mark all earlier "
            "history unverified; never enables deposit delivery"
        ),
    )
    parser.add_argument(
        "--min-confirmations",
        type=int,
        default=int(os.getenv("BTC_MIN_CONFIRMATIONS", "6")),
        help="minimum Bitcoin confirmations before a deposit is eligible for outbox delivery",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=os.getenv("BTC_NODE_AGENT_LOG_LEVEL", "INFO"),
        format="[BTC_NODE_AGENT] %(asctime)s %(levelname)s %(message)s",
    )
    if args.recovery_status:
        print(json.dumps(BtcObserverStore.read_recovery_status(args.db), sort_keys=True))
        return 0
    if args.provider_revenue_report:
        store = ProviderRevenueStore.open_existing_readonly(args.db)
        print(json.dumps(store.read_only_report(), sort_keys=True))
        return 0
    watch = load_watch_registry(args.watch_registry or None)
    agent = LocalBitcoinNodeAgent(
        db_path=args.db,
        watch_registry=watch,
        minimum_confirmations=args.min_confirmations,
    )
    info = agent.preflight()

    if args.acknowledge_unverified_history_before_height is not None:
        result = agent.acknowledge_unverified_history_before(
            args.acknowledge_unverified_history_before_height
        )
        logger.warning(
            "Recorded unverified BTC history through height=%d; delivery remains blocked",
            result["unverified_through_height"],
        )
        return 0

    if args.probe_zmq is not None:
        probe = agent.probe_zmq(args.probe_zmq)
        logger.info(
            "ZMQ probe configured=%s observed=%s timeout=%ss",
            ",".join(probe["configured"]),
            ",".join(probe["observed"]) or "none",
            probe["timeout_seconds"],
        )
        return 0

    if args.once:
        height, _block_hash, sequence = agent.publish_heartbeat()
        logger.info(
            "Bitcoin node ready: chain=%s height=%d pruned=%s sequence=%d watched=%d",
            info["chain"], height, info["pruned"], sequence, len(watch),
        )
        return 0

    blocks_scanned, recovered_matches = agent.recover_from_checkpoint()
    mempool_scanned, mempool_matches = agent.reconcile_mempool()
    queued = agent.enqueue_confirmed_deposits()
    height, _block_hash, sequence = agent.publish_heartbeat()
    logger.info(
        "Bitcoin node ready: chain=%s height=%d pruned=%s sequence=%d watched=%d backfill_blocks=%d backfill_matches=%d outbox_queued=%d delivery_enabled=%s",
        info["chain"], height, info["pruned"], sequence, len(watch),
        blocks_scanned, recovered_matches, queued, agent.delivery_enabled,
    )
    logger.info(
        "Bitcoin startup mempool snapshot transactions=%d watched_outputs=%d",
        mempool_scanned, mempool_matches,
    )
    agent.run_zmq()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
