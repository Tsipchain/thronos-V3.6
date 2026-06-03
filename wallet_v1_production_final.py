"""
Production Wallet V1 - Master/Replica Safe Transaction Backend

Architecture:
- Master node: SQLite + Redis (persistent state + distributed nonce coordination)
- Replica node: Redis only (no local writes, check nonce from shared Redis)
- Fail-closed: Reject transaction if SQLite unavailable (master) or Redis unavailable (any)

SQLite: Master-local persistent storage for chain/wallet state
Redis: Distributed nonce/replay coordination (key prefix: thronos:wallet:*)

ADDRESS DERIVATION (CANONICAL):
  Input: Compressed secp256k1 public key (66 chars, starts with 02 or 03)
  1. SHA256(publicKey)
  2. RIPEMD160(SHA256 result)
  3. Take first 40 hex chars
  4. Uppercase
  5. Prepend "THR"
  Result: "THR" + 40 uppercase hex = 43-char address
"""

import json
import time
import sqlite3
import hashlib
from typing import Dict, Any, Tuple, Optional
from datetime import datetime, timedelta

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.exceptions import InvalidSignature
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

# Configuration
MAX_TIMESTAMP_DRIFT = 300  # ±5 minutes
NONCE_EXPIRY_SECONDS = 300  # 5 minutes
REDIS_KEY_PREFIX = "thronos:wallet"  # Isolated from road-assistant

# Server dependencies (injected)
REDIS_CLIENT = None
NODE_ROLE = "master"  # "master" or "replica"
READ_ONLY = False
MASTER_SQLITE_PATH = None  # Only used on master node


def init_wallet_v1(redis_client, node_role="master", read_only=False, sqlite_path=None):
    """
    Initialize wallet V1 with server dependencies.

    Args:
        redis_client: Redis client for distributed nonce tracking
        node_role: "master" or "replica"
        read_only: True if node is read-only replica
        sqlite_path: Path to SQLite database (master only, fail-closed if unavailable)
    """
    global REDIS_CLIENT, NODE_ROLE, READ_ONLY, MASTER_SQLITE_PATH
    REDIS_CLIENT = redis_client
    NODE_ROLE = node_role
    READ_ONLY = read_only
    MASTER_SQLITE_PATH = sqlite_path if node_role == "master" else None

    # Fail-closed: Verify critical dependencies
    if REDIS_CLIENT is None:
        raise RuntimeError("[WALLET] Redis client required for wallet V1 (fail-closed)")

    # Master must have SQLite available
    if NODE_ROLE == "master":
        if MASTER_SQLITE_PATH is None:
            raise RuntimeError("[WALLET] SQLite path required on master node (fail-closed)")
        try:
            _init_master_sqlite(MASTER_SQLITE_PATH)
        except Exception as e:
            raise RuntimeError(f"[WALLET] Failed to initialize master SQLite: {e} (fail-closed)")


def _init_master_sqlite(db_path: str):
    """
    Initialize master SQLite database for wallet state.
    Only called on master node. Fails closed if unavailable.
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS wallet_nonces (
                address TEXT NOT NULL,
                nonce TEXT NOT NULL,
                txhash TEXT,
                timestamp INTEGER,
                created_at REAL,
                PRIMARY KEY (address, nonce)
            )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        raise RuntimeError(f"SQLite initialization failed: {e}")


def derive_thronos_address(public_key_hex: str) -> str:
    """
    CANONICAL address derivation (Bitcoin-style: SHA256 → RIPEMD160).
    
    MUST match exactly what all clients use.
    
    Input: Compressed secp256k1 public key (66 chars, starts with 02 or 03)
    1. SHA256(publicKey)
    2. RIPEMD160(SHA256)
    3. Take first 40 hex chars (20 bytes)
    4. Uppercase
    5. Prepend "THR"
    Result: "THR" + 40 uppercase hex chars = 43-char address
    """
    try:
        # Validate input format
        if not isinstance(public_key_hex, str) or len(public_key_hex) != 66:
            raise ValueError(f"Expected 66-char compressed pubkey, got {len(public_key_hex) if isinstance(public_key_hex, str) else 'non-string'}")
        
        if not public_key_hex.startswith(('02', '03')):
            raise ValueError(f"Compressed pubkey must start with 02 or 03, got {public_key_hex[:2]}")
        
        # Step 1: SHA256
        pub_key_bytes = bytes.fromhex(public_key_hex)
        sha256_hash = hashlib.sha256(pub_key_bytes).digest()
        
        # Step 2: RIPEMD160
        try:
            ripemd160 = hashlib.new('ripemd160')
            ripemd160.update(sha256_hash)
            ripemd160_hash = ripemd160.digest()
        except ValueError:
            raise ValueError("RIPEMD160 not available (requires OpenSSL support)")
        
        # Step 3: Take first 40 chars (20 bytes in hex)
        ripemd160_hex = ripemd160_hash.hex().upper()
        address_hash = ripemd160_hex[:40]
        
        # Step 4 & 5: Prepend THR
        address = f"THR{address_hash}"
        
        return address
    
    except Exception as e:
        raise ValueError(f"Address derivation failed: {e}")


def check_nonce_redis(address: str, nonce: str) -> Tuple[bool, str]:
    """
    Check nonce via Redis (distributed, all nodes).

    Redis key format: thronos:wallet:nonce:{address}:{nonce}
    Prevents replay attacks across master/replica nodes.

    Returns: (is_valid, error_message)
    """
    if REDIS_CLIENT is None:
        return False, "redis_unavailable"

    try:
        nonce_key = f"{REDIS_KEY_PREFIX}:nonce:{address}:{nonce}"

        # Check if nonce already used
        if REDIS_CLIENT.exists(nonce_key):
            return False, "nonce_replay_detected"

        # Mark nonce as used (5-min TTL)
        REDIS_CLIENT.setex(nonce_key, NONCE_EXPIRY_SECONDS, "1")
        return True, ""

    except Exception as e:
        return False, f"redis_error:{str(e)}"


def store_master_txhash(txhash: str, tx_data: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Store transaction hash in master SQLite + Redis (dual write for safety).
    Only called on master node.

    Redis key: thronos:wallet:txhash:{txhash}
    SQLite: wallet_state table with full transaction

    Fail-closed: If either storage fails, return error.
    """
    if NODE_ROLE != "master":
        return False, "not_master_node"

    if REDIS_CLIENT is None or MASTER_SQLITE_PATH is None:
        return False, "storage_unavailable"

    try:
        # Redis: Quick duplicate check
        txhash_key = f"{REDIS_KEY_PREFIX}:txhash:{txhash}"
        if REDIS_CLIENT.exists(txhash_key):
            return False, "duplicate_txhash"

        # SQLite: Persistent master state
        conn = sqlite3.connect(MASTER_SQLITE_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO wallet_transactions (txhash, data, created_at)
            VALUES (?, ?, ?)
        ''', (txhash, json.dumps(tx_data), time.time()))
        conn.commit()
        conn.close()

        # Mark in Redis (1-hour TTL for quick lookup)
        REDIS_CLIENT.setex(txhash_key, 3600, "1")
        return True, ""

    except Exception as e:
        return False, f"storage_error:{str(e)}"


def verify_timestamp(timestamp: int) -> Tuple[bool, str]:
    """Verify timestamp is within tolerance (±5 minutes)."""
    current_time = int(time.time())
    time_diff = abs(current_time - timestamp)

    if time_diff > MAX_TIMESTAMP_DRIFT:
        return False, f"timestamp_outside_tolerance:drift_{time_diff}s"

    return True, ""


def verify_ecdsa_signature(signed_tx: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Verify ECDSA/secp256k1 signature using public key.
    Real public-key cryptography.
    """
    if not CRYPTO_AVAILABLE:
        return False, "cryptography_unavailable"

    signature_hex = signed_tx.get('signature')
    public_key_hex = signed_tx.get('publicKey')

    if not signature_hex or not public_key_hex:
        return False, "missing_signature_or_publickey"

    try:
        # Canonical message (matches client signing)
        tx_for_signing = {
            'from': signed_tx.get('from'),
            'to': signed_tx.get('to'),
            'amount': signed_tx.get('amount'),
            'token': signed_tx.get('token', 'THR'),
            'nonce': signed_tx.get('nonce'),
            'timestamp': signed_tx.get('timestamp')
        }
        message = json.dumps(tx_for_signing, sort_keys=True, separators=(',', ':')).encode('utf-8')

        # Reconstruct public key
        public_key_bytes = bytes.fromhex(public_key_hex)
        public_key = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256K1(),
            public_key_bytes
        )

        # Verify signature
        signature_bytes = bytes.fromhex(signature_hex)
        public_key.verify(
            signature_bytes,
            message,
            ec.ECDSA(hashes.SHA256())
        )

        return True, ""

    except InvalidSignature:
        return False, "invalid_signature"
    except Exception as e:
        return False, f"signature_verification_failed:{str(e)}"


def verify_publickey_matches_address(signed_tx: Dict[str, Any]) -> Tuple[bool, str]:
    """
    CRITICAL: Verify that publicKey can sign for the address in tx.from

    Using CANONICAL address derivation (Bitcoin-style: SHA256→RIPEMD160).

    Rules:
    1. If publicKey derives to from_address directly → allow (standard case)
    2. If not, check for active key binding (re-key ceremony case):
       - from_address must have active key binding
       - publicKey hash must match binding
       - binding must be status='active'
    3. Otherwise reject

    Prevents attacker from using valid signature + mismatched address,
    while allowing re-keyed wallets to sign with bound keys.
    """
    try:
        public_key_hex = signed_tx.get('publicKey')
        from_address = signed_tx.get('from')

        if not public_key_hex or not from_address:
            return False, "missing_publickey_or_from_address"

        # Derive address from public key using CANONICAL algorithm
        derived_address = derive_thronos_address(public_key_hex)

        # RULE 1: Check if key derives to the claimed address (standard case)
        if derived_address == from_address:
            return True, ""

        # RULE 2: Check for active key binding (re-key ceremony case)
        try:
            import hashlib
            public_key_hash = hashlib.sha256(public_key_hex.encode()).hexdigest()[:32]

            # Load key bindings from server state
            import os
            import json
            bindings_file = os.path.join(os.environ.get('DATA_DIR', 'data'), 'wallet_v1_key_bindings.json')

            if os.path.exists(bindings_file):
                with open(bindings_file, 'r') as f:
                    bindings = json.load(f)

                # Find active binding for this address
                for binding in bindings:
                    if (binding.get('canonical_v1_address') == from_address and
                        binding.get('status') == 'active'):
                        # Check if public key hash matches
                        if binding.get('active_public_key_hash') == public_key_hash:
                            # Key binding is valid
                            bound_key_address = binding.get('bound_key_address', '')
                            if derived_address == bound_key_address:
                                # Hash matches and derived address matches binding
                                return True, ""
                            else:
                                return (
                                    False,
                                    f"binding_address_mismatch:expected_{bound_key_address}_got_{derived_address}",
                                )
                        else:
                            return (
                                False,
                                f"binding_key_hash_mismatch:no_matching_binding",
                            )
        except Exception as binding_check_err:
            # Binding check failed, fall through to final error
            pass

        # No matching binding found
        return (
            False,
            f"address_binding_invalid:derived_{derived_address}_vs_claimed_{from_address}_no_binding",
        )

    except Exception as e:
        return False, f"address_binding_failed:{str(e)}"


def verify_no_forbidden_fields(signed_tx: Dict[str, Any]) -> Tuple[bool, str]:
    """Reject requests containing secrets or sensitive fields."""
    forbidden = ['secret', 'mnemonic', 'seed', 'privateKey', 'auth_secret', 'passphrase']

    for field in forbidden:
        if field in signed_tx:
            return False, f"forbidden_field:{field}_present"

    return True, ""


def verify_required_fields(signed_tx: Dict[str, Any]) -> Tuple[bool, str]:
    """Verify all required fields are present."""
    required = ['from', 'to', 'amount', 'signature', 'publicKey', 'nonce', 'timestamp']

    for field in required:
        if field not in signed_tx:
            return False, f"missing_field:{field}"

    return True, ""


def verify_signed_transaction_core(signed_tx: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Core transaction verification (works on master + replica):
    1. Required fields present
    2. No forbidden fields
    3. ECDSA signature valid
    4. PublicKey matches tx.from address (CANONICAL derivation)
    5. Timestamp valid (±5 minutes)
    6. Nonce not replayed (Redis check)

    Returns: (is_valid, error_message)
    """
    # Step 1: Required fields
    is_valid, error = verify_required_fields(signed_tx)
    if not is_valid:
        return False, f"validation_failed:{error}"

    # Step 2: No forbidden fields (CRITICAL)
    is_valid, error = verify_no_forbidden_fields(signed_tx)
    if not is_valid:
        return False, f"security_violation:{error}"

    # Step 3: Valid ECDSA signature
    is_valid, error = verify_ecdsa_signature(signed_tx)
    if not is_valid:
        return False, f"signature_invalid:{error}"

    # Step 4: PublicKey derives to from address (CRITICAL - prevents address spoofing)
    is_valid, error = verify_publickey_matches_address(signed_tx)
    if not is_valid:
        return False, f"address_binding_invalid:{error}"

    # Step 5: Valid timestamp
    timestamp = signed_tx.get('timestamp')
    is_valid, error = verify_timestamp(timestamp)
    if not is_valid:
        return False, f"timestamp_invalid:{error}"

    # Step 6: Nonce not replayed (Redis-backed, works on all nodes)
    from_addr = signed_tx.get('from')
    nonce = signed_tx.get('nonce')
    is_valid, error = check_nonce_redis(from_addr, nonce)
    if not is_valid:
        return False, f"replay_detected:{error}"

    return True, ""


def verify_master_mode_required(signed_tx: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Verify that transaction is being processed on master node.
    Replica nodes must not write state locally.

    Returns: (is_master_safe, error_message)
    """
    if NODE_ROLE != "master":
        return False, "not_master_node"

    if READ_ONLY:
        return False, "read_only_mode"

    if MASTER_SQLITE_PATH is None:
        return False, "sqlite_path_unavailable"

    # Verify SQLite is accessible (fail-closed)
    try:
        conn = sqlite3.connect(MASTER_SQLITE_PATH)
        conn.execute("SELECT 1 FROM sqlite_master LIMIT 1")
        conn.close()
    except Exception as e:
        return False, f"sqlite_unavailable:{str(e)}"

    return True, ""


def verify_redis_available() -> Tuple[bool, str]:
    """
    Verify Redis is available for nonce coordination.
    Fail-closed: Reject transaction if Redis unavailable.

    Returns: (is_available, error_message)
    """
    if REDIS_CLIENT is None:
        return False, "redis_unavailable"

    try:
        REDIS_CLIENT.ping()
        return True, ""
    except Exception as e:
        return False, f"redis_unavailable:{str(e)}"
