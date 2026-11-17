"""Local Bitcoin Core node agent for the canonical Thronos BTC Observer.

Runs beside bitcoind. RPC and ZMQ remain loopback-only. The only network
egress is authenticated HTTPS to the public Thronos BTC adapter.

This process is read-only with respect to Bitcoin Core: no wallet unlock,
signing, private-key access, transaction creation, or broadcast RPC exists.
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import os
from pathlib import Path
import socket
import time
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from services.btc_observer import BtcObserver, BtcObserverError, BtcObserverStore

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
        try:
            with urlopen(req, timeout=10) as response:
                raw = response.read(16 * 1024 * 1024 + 1)
        except Exception as exc:
            raise NodeAgentError("bitcoin_rpc_unreachable") from exc
        if len(raw) > 16 * 1024 * 1024:
            raise NodeAgentError("bitcoin_rpc_response_too_large")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise NodeAgentError("invalid_bitcoin_rpc_response") from exc
        if body.get("error"):
            raise NodeAgentError(f"bitcoin_rpc_error:{body['error']}")
        return body.get("result")


class AdapterClient:
    def __init__(self) -> None:
        self.base_url = _https_adapter_url(
            os.getenv("BTC_ADAPTER_URL", "https://btc-api.thronoschain.org")
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
        result[address] = owner_ref
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
        self.store = BtcObserverStore(db_path)
        self.observer = (
            BtcObserver(
                self.rpc,
                self.store,
                watch_registry,
                minimum_confirmations=minimum_confirmations,
            )
            if watch_registry
            else None
        )

    def preflight(self) -> dict[str, Any]:
        info = self.rpc.call("getblockchaininfo", [])
        if not isinstance(info, dict):
            raise NodeAgentError("invalid_getblockchaininfo")
        if info.get("chain") != "main":
            raise NodeAgentError("bitcoin_node_not_mainnet")
        if bool(info.get("initialblockdownload")):
            raise NodeAgentError("bitcoin_node_still_syncing")
        blocks = int(info.get("blocks", -1))
        headers = int(info.get("headers", -2))
        if blocks < 0 or headers < 0 or blocks != headers:
            raise NodeAgentError("bitcoin_node_tip_not_synced")
        return {
            "chain": "main",
            "blocks": blocks,
            "pruned": bool(info.get("pruned")),
            "synced": True,
        }

    def current_tip(self) -> tuple[int, str]:
        height = int(self.rpc.call("getblockcount", []))
        block_hash = str(self.rpc.call("getblockhash", [height])).lower()
        if len(block_hash) != 64 or any(ch not in "0123456789abcdef" for ch in block_hash):
            raise NodeAgentError("invalid_bitcoin_tip_hash")
        return height, block_hash

    def publish_tip(self) -> tuple[int, str, int]:
        height, block_hash = self.current_tip()
        self.store.save_checkpoint(height, block_hash, observed_at=int(time.time()))
        sequence = self.store.next_sequence()
        self.adapter.push_tip(height=height, block_hash=block_hash, sequence=sequence)
        return height, block_hash, sequence

    def handle_rawtx(self, raw_tx: bytes) -> int:
        if self.observer is None:
            return 0
        decoded = self.rpc.call("decoderawtransaction", [raw_tx.hex()])
        if not isinstance(decoded, dict):
            raise NodeAgentError("decoderawtransaction_failed")
        return len(self.observer.observe_decoded_transaction(decoded))

    def handle_new_block(self) -> tuple[int, int, str, int]:
        height, block_hash = self.current_tip()
        matched = 0
        if self.observer is not None:
            block = self.rpc.call("getblock", [block_hash, 2])
            if not isinstance(block, dict):
                raise NodeAgentError("getblock_failed")
            matched = len(self.observer.observe_block(block))
            self.observer.reconcile_tip()
        self.store.save_checkpoint(height, block_hash, observed_at=int(time.time()))
        sequence = self.store.next_sequence()
        self.adapter.push_tip(height=height, block_hash=block_hash, sequence=sequence)
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

        context = zmq.Context.instance()
        sock = context.socket(zmq.SUB)
        sock.setsockopt(zmq.RCVHWM, 10000)
        for endpoint in endpoints.values():
            sock.connect(endpoint)
        for topic in (b"hashblock", b"rawtx", b"sequence"):
            sock.setsockopt(zmq.SUBSCRIBE, topic)

        logger.info("BTC node agent listening on local Bitcoin Core ZMQ")
        while True:
            frames = sock.recv_multipart()
            if len(frames) < 2:
                continue
            topic, body = frames[0], frames[1]
            try:
                if topic == b"rawtx":
                    count = self.handle_rawtx(body)
                    if count:
                        logger.info("Observed %d watched BTC output(s)", count)
                elif topic == b"hashblock":
                    matched, height, _hash, _seq = self.handle_new_block()
                    logger.info(
                        "Reconciled Bitcoin block %d; watched outputs=%d", height, matched
                    )
                elif topic == b"sequence":
                    # Sequence notifications are intentionally not used to mutate
                    # balances yet. They are reserved for explicit RBF/mempool
                    # eviction handling in a later reviewed phase.
                    continue
            except (NodeAgentError, BtcObserverError) as exc:
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
    args = parser.parse_args()

    logging.basicConfig(
        level=os.getenv("BTC_NODE_AGENT_LOG_LEVEL", "INFO"),
        format="[BTC_NODE_AGENT] %(asctime)s %(levelname)s %(message)s",
    )
    watch = load_watch_registry(args.watch_registry or None)
    agent = LocalBitcoinNodeAgent(db_path=args.db, watch_registry=watch)
    info = agent.preflight()
    height, _block_hash, sequence = agent.publish_tip()
    logger.info(
        "Bitcoin node ready: chain=%s height=%d pruned=%s sequence=%d watched=%d",
        info["chain"], height, info["pruned"], sequence, len(watch),
    )
    if args.once:
        return 0
    agent.run_zmq()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
