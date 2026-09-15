"""
Cross-chain incoming transfer detection and history reconciliation.

Scans EVM chains for incoming ERC-20/BEP-20 Transfer events to user
deposit addresses, creates wallet_history events for discovered transfers,
correlates bridge operations, and reconciles expected vs on-chain state.

Configuration (env vars):
    CROSSCHAIN_HISTORY_ENABLED                 – "true" to enable (default "false")
    CROSSCHAIN_HISTORY_RECONCILIATION_ENABLED  – "true" for reconciliation (default "false")
    CROSSCHAIN_HISTORY_SCAN_BLOCKS             – lookback window per chain (default 5000)
    CROSSCHAIN_HISTORY_BATCH_SIZE              – max addresses per RPC batch (default 20)
    CROSSCHAIN_HISTORY_SCAN_INTERVAL_SEC       – min seconds between scans (default 120)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger("crosschain_history")

DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))

ENABLED = os.getenv("CROSSCHAIN_HISTORY_ENABLED", "false").lower() == "true"
RECONCILIATION_ENABLED = os.getenv("CROSSCHAIN_HISTORY_RECONCILIATION_ENABLED", "false").lower() == "true"
SCAN_BLOCKS = int(os.getenv("CROSSCHAIN_HISTORY_SCAN_BLOCKS", "5000"))
BATCH_SIZE = int(os.getenv("CROSSCHAIN_HISTORY_BATCH_SIZE", "20"))
SCAN_INTERVAL_SEC = int(os.getenv("CROSSCHAIN_HISTORY_SCAN_INTERVAL_SEC", "120"))

ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

CHAIN_CONFIG: dict[str, dict[str, Any]] = {
    "bsc": {
        "chain_id": 56,
        "rpc": "https://bsc-dataseed.binance.org",
        "label": "BNB Smart Chain",
        "explorer_tx": "https://bscscan.com/tx/{txid}",
        "tokens": {
            "0x55d398326f99059ff775485246999027b3197955": {
                "symbol": "USDT",
                "decimals": 18,
                "standard": "BEP20",
            },
        },
    },
    "base": {
        "chain_id": 8453,
        "rpc": "https://mainnet.base.org",
        "label": "Base",
        "explorer_tx": "https://basescan.org/tx/{txid}",
        "tokens": {
            "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": {
                "symbol": "USDC",
                "decimals": 6,
                "standard": "ERC20",
            },
        },
    },
    "arbitrum": {
        "chain_id": 42161,
        "rpc": "https://arb1.arbitrum.io/rpc",
        "label": "Arbitrum One",
        "explorer_tx": "https://arbiscan.io/tx/{txid}",
        "tokens": {
            "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9": {
                "symbol": "USDT",
                "decimals": 6,
                "standard": "ERC20",
            },
        },
    },
    "eth": {
        "chain_id": 1,
        "rpc": "https://eth.llamarpc.com",
        "label": "Ethereum",
        "explorer_tx": "https://etherscan.io/tx/{txid}",
        "tokens": {},
    },
}

CROSSCHAIN_HISTORY_FILE = os.path.join(DATA_DIR, "crosschain_history_state.json")


def _load_json(path: str, default: Any = None) -> Any:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


def _save_json(path: str, data: Any) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def make_chain_aware_event_id(
    chain: str,
    tx_hash: str,
    log_index: int | str,
    thr_address: str,
) -> str:
    raw = f"{chain}:{tx_hash}:{log_index}:{thr_address}"
    return f"xc_{hashlib.sha256(raw.encode()).hexdigest()[:24]}"


def make_chain_aware_dedup_key(
    event_type: str,
    chain: str,
    timestamp: float | str,
    amount: float | str,
    external_txid: str = "",
) -> str:
    if external_txid:
        return f"{chain}:{external_txid}"
    return "{chain}:{et}:{ts:.4f}:{amt:.4f}".format(
        chain=chain or "unknown",
        et=event_type,
        ts=float(timestamp) if timestamp else 0.0,
        amt=float(amount) if amount else 0.0,
    )


def get_explorer_url(chain: str, tx_hash: str) -> str | None:
    cfg = CHAIN_CONFIG.get(chain)
    if not cfg or not tx_hash:
        return None
    tpl = cfg.get("explorer_tx", "")
    return tpl.format(txid=tx_hash) if tpl else None


def parse_erc20_transfer_log(log: dict, chain: str) -> dict | None:
    topics = log.get("topics", [])
    if len(topics) < 3:
        return None
    if topics[0].lower() != ERC20_TRANSFER_TOPIC:
        return None
    from_addr = "0x" + topics[1][-40:]
    to_addr = "0x" + topics[2][-40:]
    raw_amount = int(log.get("data", "0x0"), 16)
    contract = (log.get("address") or "").lower()
    tx_hash = log.get("transactionHash", "")
    log_index = log.get("logIndex", "0x0")
    if isinstance(log_index, str):
        log_index = int(log_index, 16)
    block_hex = log.get("blockNumber", "0x0")
    block_number = int(block_hex, 16) if isinstance(block_hex, str) else block_hex

    chain_cfg = CHAIN_CONFIG.get(chain, {})
    token_info = chain_cfg.get("tokens", {}).get(contract)
    if not token_info:
        return None

    decimals = token_info["decimals"]
    amount = raw_amount / (10 ** decimals)
    if amount <= 0:
        return None

    return {
        "chain": chain,
        "from_addr": from_addr.lower(),
        "to_addr": to_addr.lower(),
        "contract": contract,
        "symbol": token_info["symbol"],
        "decimals": decimals,
        "standard": token_info["standard"],
        "amount": amount,
        "tx_hash": tx_hash,
        "log_index": log_index,
        "block_number": block_number,
    }


def build_transfer_event(
    parsed: dict,
    thr_address: str,
) -> dict:
    chain = parsed["chain"]
    event_id = make_chain_aware_event_id(
        chain, parsed["tx_hash"], parsed["log_index"], thr_address
    )
    ts = time.time()
    chain_cfg = CHAIN_CONFIG.get(chain, {})
    explorer_url = get_explorer_url(chain, parsed["tx_hash"])

    return {
        "id": event_id,
        "thr_address": thr_address,
        "event_type": "crosschain_transfer_received",
        "chain": chain,
        "network_label": chain_cfg.get("label", chain.upper()),
        "asset": parsed["symbol"],
        "token_standard": parsed["standard"],
        "token_contract": parsed["contract"],
        "amount": parsed["amount"],
        "status": "confirmed",
        "direction": "in",
        "internal_txid": "",
        "external_txid": parsed["tx_hash"],
        "external_from": parsed["from_addr"],
        "external_to": parsed["to_addr"],
        "explorer_url": explorer_url,
        "pool_id": "",
        "lp_shares": 0.0,
        "pair": "",
        "note": f"Incoming {parsed['symbol']} on {chain_cfg.get('label', chain)}",
        "timestamp": ts,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(ts)),
        "block_number": parsed["block_number"],
        "transfer_scope": "cross_chain",
        "asset_origin_chain": chain,
    }


def correlate_bridge_events(events: list[dict]) -> list[dict]:
    bridge_in_by_id: dict[str, dict] = {}
    bridge_out_by_id: dict[str, dict] = {}

    for ev in events:
        et = ev.get("event_type", "")
        bid = ev.get("bridge_id") or ev.get("correlation_id") or ""
        if not bid:
            continue
        if et in ("bridge_in", "bridge_deposit_detected", "crosschain_transfer_received"):
            bridge_in_by_id[bid] = ev
        elif et in ("bridge_out", "bridge_withdraw", "wbtc_burn"):
            bridge_out_by_id[bid] = ev

    correlated = []
    all_ids = set(bridge_in_by_id.keys()) | set(bridge_out_by_id.keys())
    for bid in all_ids:
        in_ev = bridge_in_by_id.get(bid)
        out_ev = bridge_out_by_id.get(bid)
        correlated.append({
            "bridge_id": bid,
            "bridge_in": in_ev,
            "bridge_out": out_ev,
            "status": _bridge_pair_status(in_ev, out_ev),
        })
    return correlated


def _bridge_pair_status(in_ev: dict | None, out_ev: dict | None) -> str:
    if in_ev and out_ev:
        return "completed"
    if in_ev and not out_ev:
        return "pending_out"
    if out_ev and not in_ev:
        return "pending_in"
    return "unknown"


def reconcile_transfers(
    wallet_events: list[dict],
    onchain_transfers: list[dict],
) -> dict:
    wallet_keys: set[str] = set()
    for ev in wallet_events:
        chain = (ev.get("chain") or "").lower()
        txid = (ev.get("external_txid") or "").lower()
        if chain and txid:
            wallet_keys.add(f"{chain}:{txid}")

    onchain_keys: set[str] = set()
    for tr in onchain_transfers:
        chain = (tr.get("chain") or "").lower()
        txid = (tr.get("tx_hash") or "").lower()
        if chain and txid:
            onchain_keys.add(f"{chain}:{txid}")

    missing_from_history = onchain_keys - wallet_keys
    orphaned_in_history = wallet_keys - onchain_keys

    return {
        "wallet_event_count": len(wallet_events),
        "onchain_transfer_count": len(onchain_transfers),
        "matched": len(wallet_keys & onchain_keys),
        "missing_from_history": sorted(missing_from_history),
        "orphaned_in_history": sorted(orphaned_in_history),
        "is_reconciled": len(missing_from_history) == 0,
    }


def load_scan_state() -> dict:
    return _load_json(CROSSCHAIN_HISTORY_FILE, {
        "last_scan_ts": 0,
        "chain_cursors": {},
        "discovered_count": 0,
    })


def save_scan_state(state: dict) -> None:
    _save_json(CROSSCHAIN_HISTORY_FILE, state)


def should_scan(state: dict | None = None) -> bool:
    if not ENABLED:
        return False
    if state is None:
        state = load_scan_state()
    return (time.time() - state.get("last_scan_ts", 0)) >= SCAN_INTERVAL_SEC


def filter_new_transfers(
    parsed_transfers: list[dict],
    existing_event_ids: set[str],
    thr_address: str,
) -> list[dict]:
    new = []
    for p in parsed_transfers:
        eid = make_chain_aware_event_id(
            p["chain"], p["tx_hash"], p["log_index"], thr_address
        )
        if eid not in existing_event_ids:
            new.append(p)
    return new
