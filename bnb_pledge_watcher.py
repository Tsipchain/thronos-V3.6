"""
BNB/USDT Pledge Watcher Service

This service runs on the master node and:
1. Polls BSC_RPC_URL for USDT (BEP20) Transfer events to BNB_PLEDGE_VAULT
2. Resolves which user (and THR address) each transfer belongs to
3. Calls the master node's /api/usdt/pledge endpoint to credit THR and seed pool

Environment variables:
- BSC_RPC_URL: Binance Smart Chain RPC endpoint
- BNB_PLEDGE_VAULT: EVM vault address to watch (receives USDT)
- USDT_BNB_CONTRACT: USDT BEP20 token contract address (0x55d... by default)
- USDT_THR_RATE: THR credit per 1 USDT (default 100)
- MIN_USDT_PLEDGE: Minimum USDT to process (default 10)
- USDT_PLEDGE_POOL_SPLIT: Fraction of THR to seed into pool (default 0.5)
- MASTER_NODE_URL: Local master node URL
- ADMIN_SECRET: Shared admin token for API calls
- NODE_ROLE: Should be "master" for this service
- SCHEDULER_ENABLED: Should be "1" to enable the watcher
"""

import os
import json
import time
import logging
import requests
from typing import Dict, List, Optional
from decimal import Decimal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[BNB_WATCHER] %(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment configuration
BSC_RPC_URL = os.getenv("BSC_RPC_URL", "https://bsc-dataseed.binance.org")
BNB_PLEDGE_VAULT = os.getenv("BNB_PLEDGE_VAULT", "").lower()
USDT_BNB_CONTRACT = os.getenv("USDT_BNB_CONTRACT", "0x55d398326f99059ff775485246999027b3197955").lower()
USDT_THR_RATE = float(os.getenv("USDT_THR_RATE", "100"))
MIN_USDT_PLEDGE = float(os.getenv("MIN_USDT_PLEDGE", "10"))
USDT_PLEDGE_POOL_SPLIT = float(os.getenv("USDT_PLEDGE_POOL_SPLIT", "0.5"))
MASTER_NODE_URL = os.getenv("MASTER_NODE_URL", "http://localhost:5000")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "CHANGE_ME_NOW")
DATA_DIR = os.getenv("DATA_DIR", "./data")
BSC_CONFIRMATIONS = int(os.getenv("BSC_CONFIRMATIONS", "15"))  # only scan confirmed blocks
BSC_BACKFILL_BLOCKS = int(os.getenv("BSC_BACKFILL_BLOCKS", "5000"))  # max backfill on startup

# State file to track processed transactions
PROCESSED_TXS_FILE = os.path.join(DATA_DIR, "bnb_pledge_processed.json")
LAST_SCANNED_BLOCK_FILE = os.path.join(DATA_DIR, "bnb_last_scanned_block.json")

# User registry file (maps BNB addresses to THR addresses)
# Format: {"bnb_address_lowercase": {"thr_address": "THR...", "registered_at": timestamp}}
BNB_USER_REGISTRY_FILE = os.path.join(DATA_DIR, "bnb_user_registry.json")

# ERC20 Transfer event signature (keccak256 of "Transfer(address,address,uint256)")
TRANSFER_EVENT_SIGNATURE = "0xddf252ad1be2c89b69c2b068fc378dfc33cfd62c0f1eb7ece0cbf6cda9b8a97"


def load_processed_txs() -> List[str]:
    """Load list of already processed transaction hashes"""
    try:
        if os.path.exists(PROCESSED_TXS_FILE):
            with open(PROCESSED_TXS_FILE, 'r') as f:
                return json.load(f)
        return []
    except Exception as e:
        logger.error(f"Failed to load processed txs: {e}")
        return []


def save_processed_txs(txs: List[str]):
    """Save list of processed transaction hashes"""
    try:
        os.makedirs(os.path.dirname(PROCESSED_TXS_FILE), exist_ok=True)
        with open(PROCESSED_TXS_FILE, 'w') as f:
            json.dump(txs, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save processed txs: {e}")


def load_last_scanned_block() -> int:
    """Load the last successfully scanned block number"""
    try:
        if os.path.exists(LAST_SCANNED_BLOCK_FILE):
            with open(LAST_SCANNED_BLOCK_FILE, 'r') as f:
                data = json.load(f)
                return int(data.get('block', 0))
        return 0
    except Exception as e:
        logger.error(f"Failed to load last scanned block: {e}")
        return 0


def save_last_scanned_block(block: int):
    """Save the last successfully scanned block number"""
    try:
        os.makedirs(os.path.dirname(LAST_SCANNED_BLOCK_FILE), exist_ok=True)
        with open(LAST_SCANNED_BLOCK_FILE, 'w') as f:
            json.dump({'block': block, 'timestamp': time.time()}, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save last scanned block: {e}")


def load_user_registry() -> Dict:
    """Load user registry mapping BNB addresses to user info"""
    try:
        if os.path.exists(BNB_USER_REGISTRY_FILE):
            with open(BNB_USER_REGISTRY_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Failed to load user registry: {e}")
        return {}


def bsc_rpc_call(method: str, params: List = None) -> Optional[Dict]:
    """Make a JSON-RPC call to Binance Smart Chain node"""
    if not BSC_RPC_URL:
        logger.warning("BSC_RPC_URL not configured, skipping RPC call")
        return None

    try:
        payload = {
            "jsonrpc": "2.0",
            "id": "bnb_watcher",
            "method": method,
            "params": params or []
        }

        response = requests.post(
            BSC_RPC_URL,
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            if "error" in result and result["error"]:
                logger.error(f"RPC error: {result['error']}")
                return None
            return result.get("result")
        else:
            logger.error(f"RPC call failed: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.error(f"RPC call exception: {e}")
        return None


def get_vault_transfers(from_block: int = None) -> List[Dict]:
    """
    Get USDT Transfer events to the pledge vault address via eth_getLogs.

    Returns list of dicts with:
    - txhash: transaction hash
    - blockNumber: block number (hex)
    - from: sender BNB address (recovered from topic1)
    - to: vault address
    - amount: USDT amount (in wei, needs /1e18 to convert to USDT)
    - confirmed: True if block is final
    """
    if not BNB_PLEDGE_VAULT or not USDT_BNB_CONTRACT:
        logger.warning("BNB_PLEDGE_VAULT or USDT_BNB_CONTRACT not configured")
        return [], 0

    logger.info(f"Polling BSC for USDT transfers to vault: {BNB_PLEDGE_VAULT}")

    try:
        # Get current block number
        latest_block_resp = bsc_rpc_call("eth_blockNumber")
        if not latest_block_resp:
            logger.error("Failed to get latest block number")
            return []

        latest_block = int(latest_block_resp, 16)
        # Only scan confirmed blocks (safe from reorg)
        safe_block = max(0, latest_block - BSC_CONFIRMATIONS)

        # Use provided from_block or load from persistent state (with backfill limit)
        if from_block is None:
            last_scanned = load_last_scanned_block()
            from_block = max(0, last_scanned + 1, safe_block - BSC_BACKFILL_BLOCKS)

        if from_block > safe_block:
            logger.info(f"Already up to date (last_scanned={from_block - 1} >= safe_block={safe_block}), skipping")
            return [], safe_block

        logger.info(f"Querying blocks {from_block} to {safe_block}")

        # eth_getLogs: filter for Transfer events to vault address
        # topic0 = Transfer event signature
        # topic2 = 'to' address (vault)
        logs = bsc_rpc_call("eth_getLogs", [{
            "address": USDT_BNB_CONTRACT,
            "topics": [
                TRANSFER_EVENT_SIGNATURE,  # topic0: Transfer(address,address,uint256)
                None,                       # topic1: 'from' (any sender)
                "0x" + BNB_PLEDGE_VAULT[2:].zfill(64)  # topic2: 'to' (vault)
            ],
            "fromBlock": hex(from_block),
            "toBlock": hex(safe_block),
        }])

        if not logs:
            logger.info("No USDT transfers to vault found")
            return [], safe_block

        if not isinstance(logs, list):
            logger.error(f"Unexpected logs format: {logs}")
            return [], safe_block

        result = []
        for log in logs:
            try:
                txhash = log.get("transactionHash", "")
                if not txhash:
                    continue

                # topic1 contains the 'from' address (padded to 32 bytes)
                topics = log.get("topics", [])
                if len(topics) < 2:
                    logger.warning(f"Invalid topics in log: {log}")
                    continue

                from_hex = topics[1]
                from_addr = "0x" + from_hex[-40:]  # Extract last 40 hex chars (20 bytes)

                # data contains the amount (padded to 32 bytes)
                data_hex = log.get("data", "0x")
                try:
                    amount_wei = int(data_hex, 16) if data_hex.startswith("0x") else int(data_hex, 16)
                except ValueError:
                    logger.warning(f"Could not parse amount from data: {data_hex}")
                    continue

                # USDT has 18 decimals
                amount_usdt = amount_wei / 1e18

                if amount_usdt < MIN_USDT_PLEDGE:
                    logger.debug(f"Skipping small transfer: {amount_usdt} USDT (< {MIN_USDT_PLEDGE})")
                    continue

                result.append({
                    "txhash": txhash,
                    "blockNumber": log.get("blockNumber", ""),
                    "from": from_addr.lower(),
                    "to": BNB_PLEDGE_VAULT,
                    "amount": amount_usdt,
                    "confirmed": True,  # eth_getLogs returns finalized blocks
                })

                logger.info(f"Found USDT transfer: {amount_usdt} from {from_addr} to vault in {txhash}")

            except Exception as e:
                logger.error(f"Error parsing log entry: {e}")
                continue

        logger.info(f"Found {len(result)} valid USDT transfers to vault")
        # Return both transfers and the safe block we scanned up to
        return result, safe_block

    except Exception as e:
        logger.error(f"Failed to get vault transfers: {e}")
        return [], 0


def resolve_user_from_bnb_address(bnb_address: str) -> Optional[Dict]:
    """
    Resolve user information from a BNB sender address.

    Looks up the BNB address in bnb_user_registry.json to get the THR address.

    Returns dict with:
    - thr_address: THR wallet address
    - bnb_address: BNB source address
    """
    if not bnb_address:
        logger.warning("Empty BNB address")
        return None

    registry = load_user_registry()
    bnb_addr_lower = bnb_address.lower()

    if bnb_addr_lower in registry:
        user_info = registry[bnb_addr_lower]
        thr_address = user_info.get("thr_address")
        if thr_address:
            logger.info(f"Resolved BNB {bnb_address} -> THR {thr_address}")
            return {
                "thr_address": thr_address,
                "bnb_address": bnb_address,
            }

    logger.warning(f"No user found for BNB address: {bnb_address}")
    return None


def call_master_node_api(endpoint: str, data: Dict) -> Optional[Dict]:
    """Call master node API with admin authentication"""
    try:
        url = f"{MASTER_NODE_URL}{endpoint}"

        # Add admin secret to the request
        data["secret"] = ADMIN_SECRET

        response = requests.post(
            url,
            json=data,
            timeout=30
        )

        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Master node API call failed: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.error(f"Master node API call exception: {e}")
        return None


def create_usdt_pledge_transaction(
    user_info: Dict,
    usdt_amount: float,
    txhash: str,
    bnb_address: str
) -> bool:
    """
    Create a usdt_pledge transaction on the master node.

    Args:
        user_info: User information dict with thr_address
        usdt_amount: Amount of USDT pledged
        txhash: BSC transaction hash
        bnb_address: BNB sender address

    Returns:
        True if successful, False otherwise
    """
    pledge_data = {
        "type": "usdt_pledge",
        "thr_address": user_info["thr_address"],
        "bnb_address": bnb_address,
        "usdt_amount": usdt_amount,
        "bnb_txid": txhash,
        "timestamp": int(time.time()),
    }

    logger.info(f"Creating USDT pledge: {usdt_amount} USDT -> THR for {user_info['thr_address']}")

    # Call master node to create the transaction
    result = call_master_node_api("/api/usdt/pledge", pledge_data)

    if result and result.get("ok"):
        logger.info(f"USDT pledge transaction created successfully: {result}")
        return True
    else:
        logger.error(f"Failed to create USDT pledge transaction: {result}")
        return False


def watch_bnb_pledges():
    """Main watcher loop - poll for new USDT transfers and process them"""
    logger.info("Starting BNB/USDT pledge watcher...")
    logger.info(f"Watching vault: {BNB_PLEDGE_VAULT}")
    logger.info(f"USDT contract: {USDT_BNB_CONTRACT}")
    logger.info(f"Min pledge: {MIN_USDT_PLEDGE} USDT")
    logger.info(f"THR/USDT rate: {USDT_THR_RATE}")
    logger.info(f"Pool split: {USDT_PLEDGE_POOL_SPLIT}")
    logger.info(f"Master node: {MASTER_NODE_URL}")

    processed_txs = load_processed_txs()

    # Get new USDT transfers to the vault
    vault_transfers, last_safe_block = get_vault_transfers()

    for transfer in vault_transfers:
        txhash = transfer.get("txhash", "")

        # Skip if already processed
        if txhash in processed_txs:
            logger.debug(f"Skipping already-processed tx: {txhash}")
            continue

        # Get USDT amount
        usdt_amount = float(transfer.get("amount", 0))
        if usdt_amount < MIN_USDT_PLEDGE:
            logger.warning(f"Amount below minimum in tx {txhash}: {usdt_amount} USDT")
            processed_txs.append(txhash)
            continue

        # Resolve user from BNB address
        bnb_address = transfer.get("from", "")
        user_info = resolve_user_from_bnb_address(bnb_address)
        if not user_info:
            logger.warning(f"Could not resolve user for BNB address {bnb_address} (tx {txhash})")
            processed_txs.append(txhash)
            continue

        # Create USDT pledge transaction on master node
        if create_usdt_pledge_transaction(user_info, usdt_amount, txhash, bnb_address):
            logger.info(f"Successfully processed USDT pledge: {txhash}")
            processed_txs.append(txhash)
        else:
            logger.error(f"Failed to process USDT pledge: {txhash}")
            # Don't mark as processed so we can retry later

    # Save processed txs and last scanned block (only after successful scan)
    save_processed_txs(processed_txs)
    if last_safe_block > 0:
        save_last_scanned_block(last_safe_block)

    logger.info(f"Watcher cycle complete. Processed {len(vault_transfers)} USDT transfers. Last scanned block: {last_safe_block}")


# Export the watcher function to be called by the scheduler
__all__ = ["watch_bnb_pledges"]
