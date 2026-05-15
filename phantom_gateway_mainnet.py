import requests, time, logging
from typing import List, Dict
import hashlib

# Use Thronos BTC adapter (with caching) instead of external blockstream API
# Falls back to blockstream if adapter is unavailable
BTC_ADAPTER_URL = "https://btc-api.thronoschain.org"  # Our adapter (with caching)
BLOCKSTREAM_URL = "https://blockstream.info/api"      # Fallback
MIN_AMOUNT = 0.00001
PAGE_SIZE = 25
CACHE_TTL = 1800  # 30 minutes

# In-memory cache for BTC address verification
_btc_cache = {}

def _cache_key(address: str, receiver: str = None) -> str:
    """Generate cache key for BTC address verification."""
    key_data = f"{address}:{receiver or 'all'}"
    return hashlib.md5(key_data.encode()).hexdigest()

def _get_cached_txns(address: str, receiver: str = None) -> tuple:
    """Check if txns are cached and not expired."""
    key = _cache_key(address, receiver)
    if key in _btc_cache:
        txns, timestamp = _btc_cache[key]
        if time.time() - timestamp < CACHE_TTL:
            return txns, True  # Return cached, from_cache=True
    return None, False

def _cache_txns(address: str, receiver: str, txns: List[Dict]) -> None:
    """Cache transaction list."""
    key = _cache_key(address, receiver)
    _btc_cache[key] = (txns, time.time())

def fetch_all_confirmed(btc_address: str, use_adapter: bool = True) -> List[dict]:
    """
    Fetch confirmed transactions for address.
    Optimized: Limits to first page only (recent txs) instead of pagination loop.
    Uses Thronos adapter which has built-in caching.
    """
    all_txs = []

    try:
        base_url = BTC_ADAPTER_URL if use_adapter else BLOCKSTREAM_URL
        # Limit to first page only - get recent transactions
        # Pagination loop removed to prevent hangs on addresses with many txs
        url = f"{base_url}/address/{btc_address}/txs"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        all_txs = r.json() if isinstance(r.json(), list) else []
    except Exception as e:
        logging.warning(f"Confirmed txs fetch failed for {btc_address}: {e}")
        # Fall back to blockstream if adapter failed
        if use_adapter:
            try:
                return fetch_all_confirmed(btc_address, use_adapter=False)
            except Exception:
                pass

    return all_txs

def get_btc_txns(
    btc_address: str,
    btc_receiver: str = None,
) -> List[Dict]:
    """
    Get relevant BTC transactions for an address.

    OPTIMIZED:
    - Uses Thronos BTC adapter (built-in caching)
    - Limits transaction history to recent txs (no deep pagination)
    - Caches results for 30 minutes
    - Eliminates N+1 queries by using adapter's aggregated response
    """
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    logger = logging.getLogger("phantom_gateway")

    # Check cache first
    cached_txns, from_cache = _get_cached_txns(btc_address, btc_receiver)
    if from_cache:
        logger.info(f"Returning cached txns for {btc_address}")
        return cached_txns

    try:
        # Fetch current block height for confirmation calculation
        current_block_height = 0
        try:
            # Try adapter first (faster, cached), fall back to blockstream
            try:
                r_blocks = requests.get(f"{BTC_ADAPTER_URL}/blocks/tip/height", timeout=10)
            except:
                r_blocks = requests.get(f"{BLOCKSTREAM_URL}/blocks/tip/height", timeout=10)
            r_blocks.raise_for_status()
            current_block_height = int(r_blocks.text.strip())
            logger.info(f"Current block height: {current_block_height}")
        except Exception as e:
            logger.warning(f"Could not fetch current block height: {e}")

        logger.info(f"Fetching txs for {btc_address} (limited to recent, cached)")
        # Use adapter for confirmed - it handles pagination internally with caching
        confirmed = fetch_all_confirmed(btc_address, use_adapter=True)

        logger.info(f"Fetching mempool txs for {btc_address}")
        try:
            r_memp = requests.get(f"{BTC_ADAPTER_URL}/address/{btc_address}/txs/mempool", timeout=10)
            r_memp.raise_for_status()
            mempool = r_memp.json() if isinstance(r_memp.json(), list) else []
        except:
            # Fallback to blockstream mempool
            try:
                r_memp = requests.get(f"{BLOCKSTREAM_URL}/address/{btc_address}/txs/mempool", timeout=10)
                r_memp.raise_for_status()
                mempool = r_memp.json() if isinstance(r_memp.json(), list) else []
            except Exception as e:
                logger.warning(f"Mempool fetch failed: {e}")
                mempool = []

        raw_txs = confirmed + mempool
        logger.info(f"Total fetched txs: {len(raw_txs)}")

        txs = []
        seen = set()

        # Process transactions - no N+1 queries since adapter returns full data
        for tx in raw_txs:
            txid = tx.get("txid")
            if not txid or txid in seen:
                continue
            seen.add(txid)

            status = tx.get("status", {})
            ts = status.get("block_time", int(time.time()))
            block_height = status.get("block_height")
            confirmed = status.get("confirmed", False)

            confirmations = 0
            if block_height and current_block_height:
                confirmations = max(1, current_block_height - block_height + 1)
            elif confirmed:
                confirmations = 1

            # Extract outputs to the target address
            for vout in tx.get("vout", []):
                addr = vout.get("scriptpubkey_address")
                amount = vout.get("value", 0) / 1e8
                if (btc_receiver is None or addr == btc_receiver) and amount >= MIN_AMOUNT:
                    txs.append({
                        "txid": txid,
                        "to": addr,
                        "from": btc_address,
                        "amount_btc": amount,
                        "timestamp": ts,
                        "confirmations": confirmations,
                        "block_height": block_height,
                    })
                    logger.info(f"→ {txid}: {amount:.8f} BTC to {addr} ({confirmations} confirmations)")
                    break

        # Cache the results
        _cache_txns(btc_address, btc_receiver, txs)
        return txs

    except Exception as e:
        logger.error(f"Error in get_btc_txns: {e}")
        return []


        return txs

    except Exception as e:
        logger.error(f"Error in get_btc_txns: {e}")
        return []
