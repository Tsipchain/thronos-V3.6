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
import tempfile
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

# Thronos BTC API adapter (primary) – falls back to blockstream.info if unavailable
BTC_API_URL = os.getenv("BTC_API_URL", "https://btc-api.thronoschain.org")

# State file to track processed transactions
PROCESSED_TXS_FILE = os.path.join(DATA_DIR, "btc_pledge_processed.json")
# Confirmed deposits that could not yet be attributed or credited are retained here.
# This allows retries after a deposit leaves the adapter's recent transaction window.
UNRESOLVED_TXS_FILE = os.path.join(DATA_DIR, "btc_pledge_unresolved.json")

# User registry file (maps BTC addresses to THR addresses and KYC status)
# Format: {"btc_address": {"thr_address": "THR...", "kyc_verified": bool, "whitelisted_admin": bool}}
USER_REGISTRY_FILE = os.path.join(DATA_DIR, "btc_user_registry.json")

# Pledge chain file - maps BTC addresses to THR addresses (submitted via /pledge_submit)
# Primary location: /data/pledge_chain.json (working directory)
# Fallback: ./static/pledge_chain.json (for historical data)
PLEDGE_CHAIN_FILE = os.path.join(DATA_DIR, "pledge_chain.json")
PLEDGE_CHAIN_FALLBACK = "./static/pledge_chain.json"


def sync_pledge_chain_from_fallback():
    """
    Auto-sync pledge_chain.json from fallback location if primary doesn't exist.
    This ensures we don't lose historical pledge data.
    """
    try:
        if not os.path.exists(PLEDGE_CHAIN_FILE) and os.path.exists(PLEDGE_CHAIN_FALLBACK):
            os.makedirs(os.path.dirname(PLEDGE_CHAIN_FILE), exist_ok=True)
            with open(PLEDGE_CHAIN_FALLBACK, 'r') as f:
                fallback_data = json.load(f)
            with open(PLEDGE_CHAIN_FILE, 'w') as f:
                json.dump(fallback_data, f, indent=2)
            logger.info(f"Synced pledge chain from fallback: {len(fallback_data) if isinstance(fallback_data, list) else 1} entries")
    except Exception as e:
        logger.warning(f"Could not sync pledge chain from fallback: {e}")


def load_processed_txs() -> Optional[List[str]]:
    """Load processed transaction IDs; fail closed if persisted state is corrupt."""
    if not os.path.exists(PROCESSED_TXS_FILE):
        return []
    try:
        with open(PROCESSED_TXS_FILE, "r") as handle:
            value = json.load(handle)
        if not isinstance(value, list) or any(not isinstance(txid, str) for txid in value):
            logger.critical("BTC processed transaction state is invalid; refusing to continue")
            return None
        return value
    except Exception as e:
        logger.critical("Could not read BTC processed transaction state; refusing to continue: %s", e)
        return None


def _save_json_atomic(path: str, value) -> bool:
    """Atomically replace a JSON state file so a crash cannot leave truncated JSON."""
    directory = os.path.dirname(path) or "."
    tmp_path = None
    try:
        os.makedirs(directory, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", delete=False, dir=directory, prefix=".btc-watcher-", suffix=".tmp"
        ) as handle:
            json.dump(value, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
            tmp_path = handle.name
        os.replace(tmp_path, path)
        return True
    except Exception as e:
        logger.error("Failed atomic JSON write for %s: %s", os.path.basename(path), e)
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return False


def save_processed_txs(txs: List[str]) -> bool:
    """Atomically persist transaction IDs successfully processed by the master."""
    unique = list(dict.fromkeys(tx for tx in txs if tx))
    return _save_json_atomic(PROCESSED_TXS_FILE, unique)


def load_unresolved_txs() -> Optional[List[Dict]]:
    """Load confirmed BTC deposits waiting for registration or successful credit."""
    if not os.path.exists(UNRESOLVED_TXS_FILE):
        return []
    try:
        with open(UNRESOLVED_TXS_FILE, "r") as handle:
            value = json.load(handle)
        if not isinstance(value, list):
            logger.critical("BTC unresolved state is invalid; refusing to overwrite it")
            return None
        valid = []
        for item in value:
            if not isinstance(item, dict) or not item.get("txid") or not isinstance(item.get("transaction"), dict):
                logger.critical("BTC unresolved state contains an invalid entry; refusing to overwrite it")
                return None
            valid.append(item)
        return valid
    except Exception as e:
        logger.critical("Could not read BTC unresolved transaction state; refusing to continue: %s", e)
        return None


def save_unresolved_txs(entries: List[Dict]) -> bool:
    """Atomically persist all deposits that still require processing."""
    ordered = sorted(entries, key=lambda item: str(item.get("txid", "")))
    return _save_json_atomic(UNRESOLVED_TXS_FILE, ordered)


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
    Strategy order:
      1. Thronos BTC API adapter (btc-api.thronoschain.org)
      2. Blockstream.info public API
      3. BTC RPC (if configured)
    """
    if not BTC_PLEDGE_VAULT:
        logger.warning("BTC_PLEDGE_VAULT not configured")
        return []

    logger.info(f"Checking vault address: {BTC_PLEDGE_VAULT}")

    # Strategy 1: Thronos BTC API adapter (our own service)
    if BTC_API_URL:
        try:
            txs = _fetch_vault_txs_adapter(BTC_PLEDGE_VAULT)
            if txs:
                logger.info(f"Got {len(txs)} txs from Thronos BTC API")
                return txs
        except Exception as e:
            logger.warning(f"Thronos BTC API failed: {e}, falling back to blockstream")

    # Strategy 2: Blockstream.info public API (fallback)
    try:
        txs = _fetch_vault_txs_blockstream(BTC_PLEDGE_VAULT)
        if txs:
            return txs
    except Exception as e:
        logger.warning(f"Blockstream API failed: {e}")

    # Strategy 3: BTC RPC (if configured)
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


def _fetch_vault_txs_adapter(vault_address: str) -> List[Dict]:
    """Fetch incoming transactions to vault using the Thronos BTC API adapter."""
    base_url = BTC_API_URL.rstrip("/")
    result = []
    seen_txids = set()
    user_registry = load_user_registry()

    # The adapter mirrors blockstream.info API format
    # Try confirmed transactions
    resp = requests.get(
        f"{base_url}/api/address/{vault_address}/txs",
        timeout=15
    )
    resp.raise_for_status()
    txs_data = resp.json()
    all_txs = txs_data if isinstance(txs_data, list) else []

    # Also check mempool
    try:
        mem_resp = requests.get(
            f"{base_url}/api/address/{vault_address}/txs/mempool",
            timeout=10
        )
        mem_resp.raise_for_status()
        mem_txs_data = mem_resp.json()
        mem_txs = mem_txs_data if isinstance(mem_txs_data, list) else []
        all_txs.extend(mem_txs)
    except Exception as e:
        logger.warning(f"Failed to fetch mempool txs for {vault_address}: {e}")

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
            confirmations = max(1, int((time.time() - block_time) / 600))

        for vout in raw_tx.get("vout", []):
            addr = vout.get("scriptpubkey_address", "")
            if addr == vault_address:
                amount_btc = vout.get("value", 0) / 1e8
                if amount_btc <= 0:
                    continue

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
                break

    logger.info(f"Found {len(result)} transactions to vault via Thronos BTC API")
    return result


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
    try:
        if os.path.exists(PLEDGE_CHAIN_FILE):
            with open(PLEDGE_CHAIN_FILE, 'r') as f:
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


def clear_pending_confirmation(btc_address: str):
    """Clear the pending_confirmation flag from pledge_chain when BTC is confirmed"""
    try:
        if os.path.exists(PLEDGE_CHAIN_FILE):
            with open(PLEDGE_CHAIN_FILE, 'r') as f:
                pledges = json.load(f)
            for pledge in pledges:
                if pledge.get("btc_address") == btc_address and pledge.get("pending_confirmation"):
                    pledge["pending_confirmation"] = False
                    logger.info(f"Cleared pending_confirmation flag for {btc_address}")
            with open(PLEDGE_CHAIN_FILE, 'w') as f:
                json.dump(pledges, f, indent=2)
    except Exception as e:
        logger.error(f"Error clearing pending confirmation: {e}")


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

        # Clear pending_confirmation flag now that BTC is confirmed
        clear_pending_confirmation(user_info["btc_address"])

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
    """Poll BTC deposits and persist confirmed transactions until safely credited.

    A transaction is marked processed only after the master confirms success.
    Unknown users and temporary master/API failures remain in a durable retry
    queue even after they leave the explorer/adapter's recent transaction list.
    """
    logger.info("Starting BTC pledge watcher...")
    logger.info(f"Watching vault: {BTC_PLEDGE_VAULT}")
    logger.info(f"THR/BTC rate: {THR_BTC_RATE}")
    logger.info(f"Master node: {MASTER_NODE_URL}")

    sync_pledge_chain_from_fallback()

    processed_txs = load_processed_txs()
    if processed_txs is None:
        logger.critical("BTC watcher stopped because processed state could not be trusted")
        return
    processed_txs = list(dict.fromkeys(txid for txid in processed_txs if txid))
    processed_set = set(processed_txs)

    # Load confirmed transactions that previously could not be resolved/credited.
    stored_unresolved = load_unresolved_txs()
    if stored_unresolved is None:
        logger.critical("BTC watcher stopped because unresolved state could not be trusted")
        return
    pending_by_txid = {}
    for item in stored_unresolved:
        txid = str(item.get("txid") or "").strip()
        transaction = item.get("transaction")
        if not txid or txid in processed_set or not isinstance(transaction, dict):
            continue
        pending_by_txid[txid] = {
            "txid": txid,
            "transaction": transaction,
            "first_seen": item.get("first_seen", time.time()),
            "attempts": int(item.get("attempts", 0) or 0),
            "last_reason": item.get("last_reason", "previous_retry"),
        }

    # Merge fresh observations by txid. Keep the higher confirmation count if
    # an explorer temporarily returns stale/incomplete data.
    vault_txs = get_vault_transactions() or []
    for tx in vault_txs:
        if not isinstance(tx, dict):
            continue
        txid = str(tx.get("txid") or "").strip()
        if not txid or txid in processed_set:
            continue
        try:
            confirmations = int(tx.get("confirmations", 0) or 0)
        except (TypeError, ValueError):
            confirmations = 0
        # Unconfirmed transactions are seen again through the mempool/chain
        # adapter on subsequent cycles; do not credit or mark them processed.
        if confirmations < 1 and txid not in pending_by_txid:
            logger.debug("Skipping unconfirmed BTC tx: %s", txid)
            continue

        current = pending_by_txid.get(txid)
        if current:
            previous_tx = current["transaction"]
            merged_tx = {**previous_tx, **tx}
            try:
                merged_tx["confirmations"] = max(
                    int(previous_tx.get("confirmations", 0) or 0),
                    int(tx.get("confirmations", 0) or 0),
                )
            except (TypeError, ValueError):
                merged_tx["confirmations"] = int(tx.get("confirmations", 0) or 0)
            current["transaction"] = merged_tx
        else:
            pending_by_txid[txid] = {
                "txid": txid,
                "transaction": tx,
                "first_seen": time.time(),
                "attempts": 0,
                "last_reason": "",
            }

    newly_processed = []
    newly_processed_entries = {}
    for txid, item in list(pending_by_txid.items()):
        if txid in processed_set:
            pending_by_txid.pop(txid, None)
            continue

        tx = item["transaction"]
        try:
            confirmations = int(tx.get("confirmations", 0) or 0)
        except (TypeError, ValueError):
            confirmations = 0
        if confirmations < 1:
            # A persisted transaction was previously confirmed, but the latest
            # provider response may have been stale. Preserve it for the next cycle.
            item["last_reason"] = "awaiting_confirmations"
            continue

        try:
            btc_amount = float(tx.get("amount", 0))
        except (TypeError, ValueError):
            btc_amount = 0.0
        if btc_amount <= 0:
            reason = "invalid_amount"
            item["attempts"] += 1
            if item.get("last_reason") != reason or item["attempts"] == 1:
                logger.error("BTC tx %s has invalid amount; retaining for review", txid)
            item["last_reason"] = reason
            continue

        try:
            user_info = resolve_user_from_tx(tx)
        except Exception as exc:
            logger.error("BTC user resolution failed for tx %s: %s", txid, exc)
            user_info = None

        if not user_info:
            reason = "user_unresolved"
            item["attempts"] += 1
            if item.get("last_reason") != reason or item["attempts"] == 1:
                logger.warning(
                    "BTC tx %s cannot yet be attributed; keeping it for retry (amount %.8f BTC)",
                    txid, btc_amount
                )
            item["last_reason"] = reason
            continue

        try:
            credited = create_pledge_transaction(user_info, btc_amount, txid)
        except Exception as exc:
            logger.error("BTC pledge creation raised for tx %s: %s", txid, exc)
            credited = False

        if credited:
            logger.info("Successfully processed BTC pledge tx: %s", txid)
            newly_processed.append(txid)
            processed_set.add(txid)
            newly_processed_entries[txid] = {
                **item,
                "transaction": dict(tx),
                "last_reason": "processed_checkpoint_pending",
            }
            pending_by_txid.pop(txid, None)
        else:
            reason = "master_node_failed"
            item["attempts"] += 1
            if item.get("last_reason") != reason or item["attempts"] == 1:
                logger.warning("Master did not confirm BTC pledge tx %s; retaining for retry", txid)
            item["last_reason"] = reason

    processed_txs.extend(txid for txid in newly_processed if txid not in processed_txs)
    processed_saved = save_processed_txs(processed_txs)
    if not processed_saved:
        # The server may already have accepted a transaction, so keep it queued
        # until the processed checkpoint can be durably saved. The master endpoint
        # must remain idempotent by btc_txid to make this retry safe.
        for txid in newly_processed:
            pending = dict(newly_processed_entries[txid])
            pending["attempts"] = int(pending.get("attempts", 0) or 0) + 1
            pending["last_reason"] = "processed_checkpoint_write_failed"
            pending_by_txid[txid] = pending
        logger.critical("BTC processed checkpoint write failed; retained successful txs for reconciliation")

    unresolved_saved = save_unresolved_txs(list(pending_by_txid.values()))
    if not unresolved_saved:
        logger.critical("Could not persist unresolved BTC transactions; manual reconciliation is required")

    logger.info(
        "BTC watcher cycle complete. observed=%d processed_now=%d unresolved=%d",
        len(vault_txs), len(newly_processed), len(pending_by_txid)
    )


# Export the watcher function to be called by the scheduler
__all__ = ["watch_btc_pledges"]
