"""
BTC Pledge Watcher Service (PR-183)

This service runs on Node 2 (replica) and:
1. Polls BTC_RPC_URL for incoming transactions to BTC_PLEDGE_VAULT
2. Resolves which user (and THR address) each tx belongs to
3. Calls Node 1 (MASTER_NODE_URL) to create on-chain "btc_pledge" transactions

Environment variables:
- BTC_RPC_URL: Bitcoin node RPC endpoint
- BTC_RPC_USER: RPC username
- BTC_RPC_PASSWORD: RPC password
- BTC_PLEDGE_VAULT: Vault address to watch
- THR_BTC_RATE: THR per 1 BTC exchange rate
- MASTER_NODE_URL: Master node API URL
- ADMIN_SECRET: Shared admin token for API calls
- NODE_ROLE: Should be "replica" for this service
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
    format='[BTC_WATCHER] %(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment configuration
BTC_RPC_URL = os.getenv("BTC_RPC_URL", "")
BTC_RPC_USER = os.getenv("BTC_RPC_USER", "")
BTC_RPC_PASSWORD = os.getenv("BTC_RPC_PASSWORD", "")
BTC_PLEDGE_VAULT = os.getenv("BTC_PLEDGE_VAULT", "")
THR_BTC_RATE = float(os.getenv("THR_BTC_RATE", "33333.33"))
MASTER_NODE_URL = os.getenv("MASTER_NODE_URL", "http://localhost:5000")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "CHANGE_ME_NOW")
DATA_DIR = os.getenv("DATA_DIR", "./data")

# State file to track processed transactions
PROCESSED_TXS_FILE = os.path.join(DATA_DIR, "btc_pledge_processed.json")

# User registry file (maps BTC addresses to THR addresses and KYC status)
# Format: {"btc_address": {"thr_address": "THR...", "kyc_verified": bool, "whitelisted_admin": bool}}
USER_REGISTRY_FILE = os.path.join(DATA_DIR, "btc_user_registry.json")


def load_processed_txs() -> List[str]:
    """Load list of already processed transaction IDs"""
    try:
        if os.path.exists(PROCESSED_TXS_FILE):
            with open(PROCESSED_TXS_FILE, 'r') as f:
                return json.load(f)
        return []
    except Exception as e:
        logger.error(f"Failed to load processed txs: {e}")
        return []


def save_processed_txs(txs: List[str]):
    """Save list of processed transaction IDs"""
    try:
        os.makedirs(os.path.dirname(PROCESSED_TXS_FILE), exist_ok=True)
        with open(PROCESSED_TXS_FILE, 'w') as f:
            json.dump(txs, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save processed txs: {e}")


def load_user_registry() -> Dict:
    """Load user registry mapping BTC addresses to user info"""
    try:
        if os.path.exists(USER_REGISTRY_FILE):
            with open(USER_REGISTRY_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Failed to load user registry: {e}")
        return {}


def save_user_registry(registry: Dict):
    """Save user registry"""
    try:
        os.makedirs(os.path.dirname(USER_REGISTRY_FILE), exist_ok=True)
        with open(USER_REGISTRY_FILE, 'w') as f:
            json.dump(registry, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save user registry: {e}")


def btc_rpc_call(method: str, params: List = None) -> Optional[Dict]:
    """Make a JSON-RPC call to Bitcoin node"""
    if not BTC_RPC_URL:
        logger.warning("BTC_RPC_URL not configured, skipping RPC call")
        return None

    try:
        payload = {
            "jsonrpc": "1.0",
            "id": "btc_watcher",
            "method": method,
            "params": params or []
        }

        auth = None
        if BTC_RPC_USER and BTC_RPC_PASSWORD:
            auth = (BTC_RPC_USER, BTC_RPC_PASSWORD)

        response = requests.post(
            BTC_RPC_URL,
            json=payload,
            auth=auth,
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


def get_vault_transactions() -> List[Dict]:
    """
    Get transactions received by the pledge vault address.
    Uses blockstream.info public API (no Bitcoin node needed).
    Falls back to BTC RPC if configured.
    """
    if not BTC_PLEDGE_VAULT:
        logger.warning("BTC_PLEDGE_VAULT not configured")
        return []

    logger.info(f"Checking vault address: {BTC_PLEDGE_VAULT}")

    # Strategy 1: Use blockstream.info API (public, no config needed)
    try:
        txs = _fetch_vault_txs_blockstream(BTC_PLEDGE_VAULT)
        if txs:
            return txs
    except Exception as e:
        logger.warning(f"Blockstream API failed: {e}")

    # Strategy 2: Fall back to BTC RPC if configured
    if BTC_RPC_URL:
        try:
            result = btc_rpc_call("listtransactions", ["*", 100])
            if result:
                vault_txs = []
                for tx in result:
                    if tx.get("address") == BTC_PLEDGE_VAULT and tx.get("category") == "receive":
                        vault_txs.append({
                            "txid": tx.get("txid"),
                            "address": tx.get("address"),
                            "amount": abs(float(tx.get("amount", 0))),
                            "confirmations": tx.get("confirmations", 0),
                            "timestamp": tx.get("time", int(time.time())),
                        })
                return vault_txs
        except Exception as e:
            logger.warning(f"BTC RPC fallback failed: {e}")

    return []


def _fetch_vault_txs_blockstream(vault_address: str) -> List[Dict]:
    """Fetch incoming transactions to vault using blockstream.info API."""
    BLOCKSTREAM_URL = "https://blockstream.info/api"
    all_txs = []

    # Fetch confirmed transactions (paginated)
    last_seen = None
    for _page in range(10):  # Max 10 pages = 250 txs
        url = f"{BLOCKSTREAM_URL}/address/{vault_address}/txs/chain"
        if last_seen:
            url += f"/{last_seen}"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        page = resp.json()
        if not page:
            break
        all_txs.extend(page)
        last_seen = page[-1]["txid"]
        if len(page) < 25:
            break

    # Also check mempool (unconfirmed)
    try:
        resp = requests.get(
            f"{BLOCKSTREAM_URL}/address/{vault_address}/txs/mempool",
            timeout=10
        )
        resp.raise_for_status()
        all_txs.extend(resp.json())
    except Exception:
        pass

    # Parse into normalized format
    result = []
    seen_txids = set()
    user_registry = load_user_registry()

    for raw_tx in all_txs:
        txid = raw_tx.get("txid")
        if not txid or txid in seen_txids:
            continue
        seen_txids.add(txid)

        status = raw_tx.get("status", {})
        confirmed = status.get("confirmed", False)
        block_time = status.get("block_time", 0)
        confirmations = 0
        if confirmed and block_time:
            # Estimate confirmations from block time
            confirmations = max(1, int((time.time() - block_time) / 600))

        # Find vouts that pay to the vault address
        for vout in raw_tx.get("vout", []):
            addr = vout.get("scriptpubkey_address", "")
            if addr == vault_address:
                amount_btc = vout.get("value", 0) / 1e8
                if amount_btc <= 0:
                    continue

                # Try to find the sender address from vin
                sender_addr = ""
                for vin in raw_tx.get("vin", []):
                    prevout = vin.get("prevout", {})
                    sa = prevout.get("scriptpubkey_address", "")
                    if sa and sa != vault_address:
                        sender_addr = sa
                        break

                result.append({
                    "txid": txid,
                    "address": sender_addr,
                    "to": vault_address,
                    "amount": amount_btc,
                    "confirmations": confirmations,
                    "timestamp": block_time or int(time.time()),
                    "confirmed": confirmed,
                })
                break  # Only count first vout to vault per tx

    logger.info(f"Found {len(result)} transactions to vault via blockstream.info")
    return result


def resolve_user_from_tx(tx: Dict) -> Optional[Dict]:
    """
    Resolve user information from a transaction.

    Lookup order:
    1. User registry (btc_user_registry.json)
    2. Pledge chain (pledge_chain.json) - for addresses submitted via /pledge_submit

    Returns dict with:
    - thr_address: THR wallet address
    - btc_address: BTC source address
    - kyc_verified: bool
    - whitelisted_admin: bool
    """
    # Get source BTC address from the transaction
    btc_address = tx.get("address", "")

    if not btc_address:
        logger.warning(f"No source address found in tx: {tx.get('txid')}")
        return None

    # Strategy 1: Look up user in registry
    registry = load_user_registry()
    user_info = registry.get(btc_address)

    if user_info and user_info.get("thr_address"):
        return {
            "thr_address": user_info.get("thr_address"),
            "btc_address": btc_address,
            "kyc_verified": user_info.get("kyc_verified", False),
            "whitelisted_admin": user_info.get("whitelisted_admin", False),
        }

    # Strategy 2: Look up in pledge_chain.json (from /pledge_submit)
    pledge_chain_file = os.path.join(DATA_DIR, "pledge_chain.json")
    try:
        if os.path.exists(pledge_chain_file):
            with open(pledge_chain_file, 'r') as f:
                pledges = json.load(f)
            for pledge in pledges:
                if pledge.get("btc_address") == btc_address and pledge.get("thr_address"):
                    logger.info(f"Resolved BTC {btc_address} -> THR {pledge['thr_address']} from pledge chain")
                    # Auto-populate registry for future lookups
                    registry[btc_address] = {
                        "thr_address": pledge["thr_address"],
                        "kyc_verified": False,
                        "whitelisted_admin": False,
                        "source": "pledge_chain"
                    }
                    save_user_registry(registry)
                    return {
                        "thr_address": pledge["thr_address"],
                        "btc_address": btc_address,
                        "kyc_verified": False,
                        "whitelisted_admin": False,
                    }
    except Exception as e:
        logger.error(f"Error reading pledge chain: {e}")

    logger.warning(f"No user found for BTC address: {btc_address}")
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


def create_pledge_transaction(
    user_info: Dict,
    btc_amount: float,
    txid: str
) -> bool:
    """
    Create a btc_pledge transaction on the master node

    Args:
        user_info: User information dict
        btc_amount: Amount of BTC pledged
        txid: Bitcoin transaction ID

    Returns:
        True if successful, False otherwise
    """
    thr_amount = btc_amount * THR_BTC_RATE

    pledge_data = {
        "type": "btc_pledge",
        "thr_address": user_info["thr_address"],
        "btc_address": user_info["btc_address"],
        "btc_amount": btc_amount,
        "thr_amount": thr_amount,
        "btc_txid": txid,
        "kyc_verified": user_info.get("kyc_verified", False),
        "whitelisted_admin": user_info.get("whitelisted_admin", False),
        "timestamp": int(time.time()),
    }

    logger.info(f"Creating pledge tx: {btc_amount} BTC -> {thr_amount} THR for {user_info['thr_address']}")

    # Call master node to create the transaction
    result = call_master_node_api("/api/btc/pledge", pledge_data)

    if result and result.get("ok"):
        logger.info(f"Pledge transaction created successfully: {result}")

        # Also activate wallet for KYC-verified users
        if user_info.get("kyc_verified"):
            activate_result = call_master_node_api(
                "/api/wallet/activate",
                {
                    "thr_address": user_info["thr_address"],
                    "btc_address": user_info["btc_address"],
                }
            )
            if activate_result:
                logger.info(f"Wallet activated for {user_info['thr_address']}")

        return True
    else:
        logger.error(f"Failed to create pledge transaction: {result}")
        return False


def watch_btc_pledges():
    """Main watcher loop - poll for new BTC transactions and process them"""
    logger.info("Starting BTC pledge watcher...")
    logger.info(f"Watching vault: {BTC_PLEDGE_VAULT}")
    logger.info(f"THR/BTC rate: {THR_BTC_RATE}")
    logger.info(f"Master node: {MASTER_NODE_URL}")

    processed_txs = load_processed_txs()

    # Get new transactions from the vault
    vault_txs = get_vault_transactions()

    for tx in vault_txs:
        txid = tx.get("txid")

        # Skip if already processed
        if txid in processed_txs:
            continue

        # Skip unconfirmed transactions (require at least 1 confirmation)
        confirmations = tx.get("confirmations", 0)
        if confirmations < 1:
            logger.debug(f"Skipping unconfirmed tx: {txid}")
            continue

        # Get BTC amount
        btc_amount = float(tx.get("amount", 0))
        if btc_amount <= 0:
            logger.warning(f"Invalid amount in tx {txid}: {btc_amount}")
            processed_txs.append(txid)
            continue

        # Resolve user from transaction
        user_info = resolve_user_from_tx(tx)
        if not user_info:
            logger.warning(f"Could not resolve user for tx {txid}")
            processed_txs.append(txid)
            continue

        # Create pledge transaction on master node
        if create_pledge_transaction(user_info, btc_amount, txid):
            logger.info(f"Successfully processed pledge tx: {txid}")
            processed_txs.append(txid)
        else:
            logger.error(f"Failed to process pledge tx: {txid}")
            # Don't mark as processed so we can retry later

    # Save processed txs
    save_processed_txs(processed_txs)

    logger.info(f"Watcher cycle complete. Processed {len(vault_txs)} transactions.")


# Export the watcher function to be called by the scheduler
__all__ = ["watch_btc_pledges"]
