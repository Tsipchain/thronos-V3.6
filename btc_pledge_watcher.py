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
    """Get all transactions received by the pledge vault address"""
    if not BTC_PLEDGE_VAULT:
        logger.warning("BTC_PLEDGE_VAULT not configured")
        return []

    # Get transactions for the vault address
    # Note: This assumes the vault address is being watched by the Bitcoin node
    # Use listtransactions or similar method depending on your node setup

    # For now, return empty list as this requires specific RPC setup
    # In production, you would use methods like:
    # - listreceivedbyaddress
    # - listtransactions
    # - listsinceblock
    # depending on your Bitcoin node configuration

    logger.debug(f"Checking vault address: {BTC_PLEDGE_VAULT}")
    return []


def resolve_user_from_tx(tx: Dict) -> Optional[Dict]:
    """
    Resolve user information from a transaction

    Returns dict with:
    - thr_address: THR wallet address
    - btc_address: BTC source address
    - kyc_verified: bool
    - whitelisted_admin: bool
    """
    # Get source BTC address from the transaction
    # This is simplified - in production you'd parse the tx inputs
    btc_address = tx.get("address", "")

    if not btc_address:
        logger.warning(f"No source address found in tx: {tx.get('txid')}")
        return None

    # Look up user in registry
    registry = load_user_registry()
    user_info = registry.get(btc_address)

    if not user_info:
        logger.warning(f"No user found for BTC address: {btc_address}")
        return None

    return {
        "thr_address": user_info.get("thr_address"),
        "btc_address": btc_address,
        "kyc_verified": user_info.get("kyc_verified", False),
        "whitelisted_admin": user_info.get("whitelisted_admin", False),
    }


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
