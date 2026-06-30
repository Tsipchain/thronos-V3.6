"""
Pool Deposit Watcher Service

Monitors Pythia AMM pool vaults for real external on-chain deposits:
  - BSC:  USDT (BEP20) transfers to the BSC pool vault
  - Base: USDC (ERC20) transfers to the Base pool vault

On a confirmed deposit the watcher calls the master node's internal
POST /api/admin/pools/watcher/credit-external-deposit endpoint to write
the event into pool_liquidity_ledger.json and increase external_reserve.

No signing.  No broadcast.  No private keys.  Read-only RPC.

Environment variables
─────────────────────
POOL_WATCHER_ENABLED           "1" to enable (default: disabled)
POOL_WATCHER_CONFIRMATIONS     blocks to wait for finality (default: 15)
POOL_WATCHER_BACKFILL_BLOCKS   max blocks to scan back on startup (default: 5000)

BSC_RPC_URL                    Binance Smart Chain JSON-RPC endpoint
BASE_RPC_URL                   Base chain JSON-RPC endpoint

BSC_USDT_CONTRACT              BEP20 USDT contract (default: canonical BEP20 USDT)
BASE_USDC_CONTRACT             ERC20 USDC contract on Base (default: canonical Base USDC)

BSC_POOL_VAULT_ADDRESS         BSC vault to watch (preferred)
PYTHIA_SYSTEM_EVM_BSC_ADDRESS  fallback vault if BSC_POOL_VAULT_ADDRESS not set
BASE_POOL_VAULT_ADDRESS        Base vault to watch (preferred)
PYTHIA_SYSTEM_EVM_BASE_ADDRESS fallback vault if BASE_POOL_VAULT_ADDRESS not set

MASTER_NODE_URL                local master node URL for crediting (default: http://localhost:5000)
ADMIN_SECRET                   shared admin token
DATA_DIR                       state file directory (default: ./data)
"""

import os
import json
import time
import logging
import requests
from typing import Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format='[POOL_WATCHER] %(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

POOL_WATCHER_ENABLED       = os.getenv("POOL_WATCHER_ENABLED", "0") == "1"
POOL_WATCHER_CONFIRMATIONS = int(os.getenv("POOL_WATCHER_CONFIRMATIONS", "15"))
POOL_WATCHER_BACKFILL      = int(os.getenv("POOL_WATCHER_BACKFILL_BLOCKS", "5000"))
POOL_LOGS_CHUNK_SIZE       = int(os.getenv("POOL_LOGS_CHUNK_SIZE", "500"))   # max blocks per eth_getLogs call

BSC_RPC_URL  = os.getenv("BSC_RPC_URL", "")
BASE_RPC_URL = os.getenv("BASE_RPC_URL", "")

# Default token contracts (canonical addresses for mainnet)
BSC_USDT_CONTRACT  = (
    os.getenv("BSC_USDT_CONTRACT") or "0x55d398326f99059ff775485246999027b3197955"
).lower()
BASE_USDC_CONTRACT = (
    os.getenv("BASE_USDC_CONTRACT") or "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
).lower()

# Pool vault addresses — prefer explicit var, fall back to Pythia system EVM address,
# then hardcoded MVP fallback.
_BSC_VAULT_DEFAULT  = "0x76b1926f40c596e10c30ae7a359df8a0b21ac4a2"
_BASE_VAULT_DEFAULT = "0x76b1926f40c596e10c30ae7a359df8a0b21ac4a2"
_BSC_VAULT  = (
    os.getenv("BSC_POOL_VAULT_ADDRESS") or
    os.getenv("PYTHIA_SYSTEM_EVM_BSC_ADDRESS") or
    _BSC_VAULT_DEFAULT
).lower()
_BASE_VAULT = (
    os.getenv("BASE_POOL_VAULT_ADDRESS") or
    os.getenv("PYTHIA_SYSTEM_EVM_BASE_ADDRESS") or
    _BASE_VAULT_DEFAULT
).lower()

MASTER_NODE_URL = os.getenv("MASTER_NODE_URL", "http://localhost:5000")
ADMIN_SECRET    = os.getenv("ADMIN_SECRET", "CHANGE_ME_NOW")
DATA_DIR        = os.getenv("DATA_DIR", "./data")

# ERC-20 Transfer(address,address,uint256) topic0
TRANSFER_EVENT_SIG = "0xddf252ad1be2c89b69c2b068fc378dfc33cfd62c0f1eb7ece0cbf6cda9b8a97"

# State files
WATCHER_STATE_FILE     = os.path.join(DATA_DIR, "pool_deposit_watcher_state.json")
EXTERNAL_DEPOSITS_FILE = os.path.join(DATA_DIR, "pool_external_deposits.json")

# Pool targets: each entry describes one vault to watch
POOL_TARGETS: List[Dict] = [
    {
        "pool_id":           "bsc-usdt",
        "chain":             "bsc",
        "asset":             "USDT",
        "decimals":          18,
        "token_contract":    BSC_USDT_CONTRACT,
        "vault_address":     _BSC_VAULT,
        "rpc_url":           BSC_RPC_URL,
        "source_detail":     "bsc_usdt_pool_watcher",
        "rpc_env_var":       "BSC_RPC_URL",
        "vault_env_vars":    "BSC_POOL_VAULT_ADDRESS / PYTHIA_SYSTEM_EVM_BSC_ADDRESS",
        "contract_env_var":  "BSC_USDT_CONTRACT",
    },
    {
        "pool_id":           "base-usdc",
        "chain":             "base",
        "asset":             "USDC",
        "decimals":          6,
        "token_contract":    BASE_USDC_CONTRACT,
        "vault_address":     _BASE_VAULT,
        "rpc_url":           BASE_RPC_URL,
        "source_detail":     "base_usdc_pool_watcher",
        "rpc_env_var":       "BASE_RPC_URL",
        "vault_env_vars":    "BASE_POOL_VAULT_ADDRESS / PYTHIA_SYSTEM_EVM_BASE_ADDRESS",
        "contract_env_var":  "BASE_USDC_CONTRACT",
    },
]


# ── State management ───────────────────────────────────────────────────────────

def _load_watcher_state() -> dict:
    try:
        if os.path.exists(WATCHER_STATE_FILE):
            with open(WATCHER_STATE_FILE, "r") as f:
                return json.load(f)
    except Exception as exc:
        logger.error("Failed to load watcher state: %s", exc)
    return {"last_scanned_block": {}, "credited_event_ids": [], "last_error": ""}


def _save_watcher_state(state: dict) -> None:
    try:
        os.makedirs(os.path.dirname(WATCHER_STATE_FILE), exist_ok=True)
        with open(WATCHER_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as exc:
        logger.error("Failed to save watcher state: %s", exc)


def _load_external_deposits() -> list:
    try:
        if os.path.exists(EXTERNAL_DEPOSITS_FILE):
            with open(EXTERNAL_DEPOSITS_FILE, "r") as f:
                return json.load(f)
    except Exception as exc:
        logger.error("Failed to load external deposits: %s", exc)
    return []


def _save_external_deposits(deposits: list) -> None:
    try:
        os.makedirs(os.path.dirname(EXTERNAL_DEPOSITS_FILE), exist_ok=True)
        with open(EXTERNAL_DEPOSITS_FILE, "w") as f:
            json.dump(deposits, f, indent=2)
    except Exception as exc:
        logger.error("Failed to save external deposits: %s", exc)


def stable_event_id(chain: str, tx_hash: str, log_index) -> str:
    """Deterministic, collision-safe event ID for deduplication."""
    return f"POOL-WATCHER-{chain.lower()}-{tx_hash.lower()}-{log_index}"


# ── EVM JSON-RPC helpers ───────────────────────────────────────────────────────

def evm_rpc_call(rpc_url: str, method: str, params: list = None) -> Optional[object]:
    """Make a single JSON-RPC 2.0 call; return result or None on error."""
    if not rpc_url:
        return None
    try:
        payload = {
            "jsonrpc": "2.0",
            "id":      "pool_watcher",
            "method":  method,
            "params":  params or [],
        }
        resp = requests.post(rpc_url, json=payload, timeout=30)
        if resp.status_code == 200:
            body = resp.json()
            if body.get("error"):
                logger.error("RPC error [%s %s]: %s", rpc_url[:40], method, body["error"])
                return None
            return body.get("result")
        logger.error("RPC HTTP %s from %s (%s)", resp.status_code, rpc_url[:40], method)
        return None
    except Exception as exc:
        logger.error("RPC exception [%s %s]: %s", rpc_url[:40], method, exc)
        return None


def _get_evm_logs_chunked(
    rpc_url: str,
    chain: str,
    filter_params: dict,
    from_block: int,
    to_block: int,
) -> Optional[list]:
    """
    Call eth_getLogs in ≤POOL_LOGS_CHUNK_SIZE block chunks to avoid -32005 limit errors.
    Returns accumulated list of logs, or None on unrecoverable error.
    """
    all_logs: list = []
    chunk_start = from_block
    while chunk_start <= to_block:
        chunk_end = min(chunk_start + POOL_LOGS_CHUNK_SIZE - 1, to_block)
        params = {**filter_params, "fromBlock": hex(chunk_start), "toBlock": hex(chunk_end)}
        result = evm_rpc_call(rpc_url, "eth_getLogs", [params])
        if result is None:
            logger.error("[%s] eth_getLogs failed for chunk %d-%d", chain, chunk_start, chunk_end)
            return None
        if not isinstance(result, list):
            logger.error("[%s] eth_getLogs unexpected result for chunk %d-%d: %s",
                         chain, chunk_start, chunk_end, result)
            return None
        all_logs.extend(result)
        logger.debug("[%s] chunk %d-%d: %d log(s)", chain, chunk_start, chunk_end, len(result))
        chunk_start = chunk_end + 1
    return all_logs


def get_evm_vault_transfers(
    rpc_url: str,
    vault_address: str,
    token_contract: str,
    chain: str,
    decimals: int,
    last_scanned_block: int,
) -> Tuple[List[Dict], int]:
    """
    Fetch ERC-20 Transfer events directed to vault_address since last_scanned_block.

    Returns (transfers, safe_block) where safe_block is the highest confirmed block
    the scan reached (POOL_WATCHER_CONFIRMATIONS behind the chain tip).
    """
    latest_hex = evm_rpc_call(rpc_url, "eth_blockNumber")
    if not latest_hex:
        logger.error("[%s] Cannot get latest block number", chain)
        return [], 0

    latest_block = int(latest_hex, 16)
    safe_block   = max(0, latest_block - POOL_WATCHER_CONFIRMATIONS)
    from_block   = max(0, last_scanned_block + 1, safe_block - POOL_WATCHER_BACKFILL)

    if from_block > safe_block:
        logger.info("[%s] Already at block %d — nothing to scan", chain, safe_block)
        return [], safe_block

    logger.info("[%s] Scanning blocks %d → %d for transfers to %s",
                chain, from_block, safe_block, vault_address)

    # topic2 = vault address padded to 32 bytes (the "to" field of Transfer)
    vault_padded = "0x" + vault_address.lstrip("0x").zfill(64)
    filter_base = {
        "address": token_contract,
        "topics":  [TRANSFER_EVENT_SIG, None, vault_padded],
    }
    logs = _get_evm_logs_chunked(rpc_url, chain, filter_base, from_block, safe_block)

    if logs is None:
        logger.error("[%s] eth_getLogs chunked scan failed — not advancing checkpoint", chain)
        return [], 0

    if not logs:
        logger.info("[%s] No transfers found in block range", chain)
        return [], safe_block

    transfers: List[Dict] = []
    for log in logs:
        try:
            tx_hash = log.get("transactionHash", "")
            if not tx_hash:
                continue
            topics = log.get("topics", [])
            if len(topics) < 3:
                logger.warning("[%s] Log with fewer than 3 topics skipped: %s", chain, log)
                continue

            from_addr    = "0x" + topics[1][-40:]
            log_index    = int(log.get("logIndex", "0x0"), 16)
            block_number = int(log.get("blockNumber", "0x0"), 16)
            data_hex     = log.get("data", "0x")
            amount_raw   = int(data_hex, 16)
            amount       = amount_raw / (10 ** decimals)

            transfers.append({
                "tx_hash":      tx_hash.lower(),
                "log_index":    log_index,
                "block_number": block_number,
                "from_address": from_addr.lower(),
                "to_address":   vault_address.lower(),
                "amount":       amount,
                "confirmations": latest_block - block_number,
            })
            logger.info("[%s] Transfer detected: %.6f from %s tx=%s log=%d",
                        chain, amount, from_addr, tx_hash[:20], log_index)
        except Exception as exc:
            logger.error("[%s] Error parsing log entry: %s | log=%s", chain, exc, log)

    logger.info("[%s] %d transfer(s) detected in block range", chain, len(transfers))
    return transfers, safe_block


# ── Credit via master node API ─────────────────────────────────────────────────

def credit_pool_external_deposit(deposit: dict) -> bool:
    """
    POST deposit to the master node's internal credit endpoint.
    Returns True if credited (or already a duplicate), False on transient failure.
    """
    try:
        url  = f"{MASTER_NODE_URL}/api/admin/pools/watcher/credit-external-deposit"
        data = {**deposit, "secret": ADMIN_SECRET}
        resp = requests.post(url, json=data, timeout=30)
        if resp.status_code in (200, 201, 202):
            result = resp.json()
            if result.get("ok"):
                logger.info("[%s] Credited %.6f %s pool=%s tx=%s log=%d (HTTP %d)",
                            deposit["chain"], deposit["amount"], deposit["asset"],
                            deposit["pool_id"], deposit["tx_hash"][:20], deposit["log_index"],
                            resp.status_code)
                return True
            if result.get("error") == "duplicate":
                logger.info("[%s] Already credited (duplicate): %s",
                            deposit["chain"], deposit["event_id"])
                return True  # idempotent — not a failure
            logger.error("[%s] Credit rejected: %s", deposit["chain"], result)
            return False
        logger.error("[%s] Credit HTTP %s: %s",
                     deposit["chain"], resp.status_code, resp.text[:200])
        return False
    except Exception as exc:
        logger.error("[%s] Credit exception: %s", deposit["chain"], exc)
        return False


# ── Main watcher cycle ─────────────────────────────────────────────────────────

def scan_pool_deposits() -> None:
    """
    Single watcher cycle: scan all configured pool vault addresses for new
    ERC-20 deposits and credit confirmed ones into the pool liquidity ledger.

    Called by APScheduler every 5 minutes via _with_app_context wrapper.
    Separate from the pledge watcher — pledge processing is unchanged.
    """
    if not POOL_WATCHER_ENABLED:
        logger.debug("Pool deposit watcher disabled (POOL_WATCHER_ENABLED != 1)")
        return

    state       = _load_watcher_state()
    credited    = set(state.get("credited_event_ids", []))
    had_failure = False

    for target in POOL_TARGETS:
        pool_id    = target["pool_id"]
        chain      = target["chain"]
        rpc_url    = target["rpc_url"]
        vault      = target["vault_address"]
        contract   = target["token_contract"]
        asset      = target["asset"]
        decimals   = target["decimals"]
        src_detail = target["source_detail"]

        if not rpc_url:
            logger.warning("[%s] Skipping scan — %s not configured",
                           chain, target["rpc_env_var"])
            continue

        if not vault:
            logger.warning("[%s] Skipping scan — %s not configured",
                           chain, target["vault_env_vars"])
            continue

        last_block = int(state.get("last_scanned_block", {}).get(chain, 0))
        transfers, safe_block = get_evm_vault_transfers(
            rpc_url, vault, contract, chain, decimals, last_block
        )

        chain_failed = False
        for t in transfers:
            event_id = stable_event_id(chain, t["tx_hash"], t["log_index"])
            if event_id in credited:
                logger.debug("[%s] Already credited: %s", chain, event_id)
                continue

            deposit = {
                "event_id":      event_id,
                "pool_id":       pool_id,
                "chain":         chain,
                "asset":         asset,
                "amount":        t["amount"],
                "tx_hash":       t["tx_hash"],
                "log_index":     t["log_index"],
                "from_address":  t["from_address"],
                "to_address":    t["to_address"],
                "block_number":  t["block_number"],
                "confirmations": t["confirmations"],
                "source_detail": src_detail,
                "timestamp":     int(time.time()),
            }

            if credit_pool_external_deposit(deposit):
                credited.add(event_id)
                # Persist a local copy for audit / admin review
                deposits = _load_external_deposits()
                if not any(d.get("event_id") == event_id for d in deposits):
                    deposits.append({**deposit, "credited_at": int(time.time())})
                    _save_external_deposits(deposits)
            else:
                chain_failed = True
                had_failure  = True

        # Only advance the checkpoint when all transfers in this chain scan succeeded
        if safe_block > 0 and not chain_failed:
            state.setdefault("last_scanned_block", {})[chain] = safe_block
        elif chain_failed:
            logger.warning("[%s] Not advancing checkpoint — some transfers failed", chain)

    state["credited_event_ids"] = list(credited)
    state["last_scan_ts"]       = int(time.time())
    if had_failure:
        state["last_error"] = f"failures during scan at {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}"
    else:
        state.pop("last_error", None)

    _save_watcher_state(state)
    logger.info("Pool deposit watcher cycle complete.")
