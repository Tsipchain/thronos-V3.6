"""
Production Wallet V1 - Secure Signed Transaction Backend

Production-grade implementation for Thronos master/replica architecture:
- ECDSA/secp256k1 signature verification (real public-key cryptography)
- Redis-backed durable nonce tracking (distributed, not local)
- Replica-aware transaction handling (rejects on read-only replicas)
- Strict timestamp validation (±5 minute window)
- Forbidden field rejection (secret, mnemonic, seed, privateKey, auth_secret)
"""

import json
import time
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

MAX_TIMESTAMP_DRIFT = 300  # ±5 minutes = 300 seconds
NONCE_VALID_MINUTES = 5
NONCE_EXPIRY_SECONDS = NONCE_VALID_MINUTES * 60

# Will be injected from server.py
REDIS_CLIENT = None
NODE_ROLE = "master"
READ_ONLY = False


def init_wallet_v1(redis_client, node_role="master", read_only=False):
    """Initialize wallet V1 with server dependencies."""
    global REDIS_CLIENT, NODE_ROLE, READ_ONLY
    REDIS_CLIENT = redis_client
    NODE_ROLE = node_role
    READ_ONLY = read_only


def check_nonce_production(nonce: str) -> Tuple[bool, str]:
    """
    Production-grade nonce checking with Redis persistence.
    Prevents replay attacks across server instances and restarts.
    """
    if not REDIS_CLIENT:
        return False, "nonce_storage_unavailable"

    try:
        nonce_key = f"wallet:nonce:{nonce}"

        # Check if nonce already exists (replay)
        if REDIS_CLIENT.exists(nonce_key):
            return False, "nonce_replay_detected"

        # Store nonce with expiration
        REDIS_CLIENT.setex(nonce_key, NONCE_EXPIRY_SECONDS, "1")
        return True, ""

    except Exception as e:
        return False, f"nonce_check_failed:{str(e)}"


def verify_timestamp(timestamp: int) -> Tuple[bool, str]:
    """
    Verify timestamp is within acceptable window (±5 minutes).
    Prevents old/future transaction replays.
    """
    current_time = int(time.time())
    time_diff = abs(current_time - timestamp)

    if time_diff > MAX_TIMESTAMP_DRIFT:
        return False, f"timestamp_outside_tolerance:drift_{time_diff}s"

    return True, ""


def verify_ecdsa_signature(signed_tx: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Verify ECDSA/secp256k1 signature using public key.
    Real public-key cryptography instead of HMAC.
    """
    if not CRYPTO_AVAILABLE:
        return False, "cryptography_library_unavailable"

    signature_hex = signed_tx.get('signature')
    public_key_hex = signed_tx.get('publicKey')

    if not signature_hex or not public_key_hex:
        return False, "missing_signature_or_publickey"

    try:
        # Create canonical message (sorted keys, no spaces)
        tx_for_signing = {
            'from': signed_tx.get('from'),
            'to': signed_tx.get('to'),
            'amount': signed_tx.get('amount'),
            'token': signed_tx.get('token', 'THR'),
            'nonce': signed_tx.get('nonce'),
            'timestamp': signed_tx.get('timestamp')
        }
        message = json.dumps(tx_for_signing, sort_keys=True, separators=(',', ':')).encode('utf-8')

        # Reconstruct public key from hex
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


def verify_no_forbidden_fields(signed_tx: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Reject any request containing secrets or sensitive fields.
    Critical gate that prevents secret transmission.
    """
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


def verify_signed_transaction_complete(signed_tx: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Complete transaction verification with production checks:
    1. Required fields present
    2. No forbidden fields
    3. ECDSA signature valid
    4. Timestamp valid (±5 minutes)
    5. Nonce not replayed (distributed via Redis)

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

    # Step 4: Valid timestamp
    timestamp = signed_tx.get('timestamp')
    is_valid, error = verify_timestamp(timestamp)
    if not is_valid:
        return False, f"timestamp_invalid:{error}"

    # Step 5: Nonce not replayed (production: Redis-backed)
    nonce = signed_tx.get('nonce')
    is_valid, error = check_nonce_production(nonce)
    if not is_valid:
        return False, f"replay_detected:{error}"

    return True, ""


def derive_address_from_public_key(public_key_hex: str) -> Optional[str]:
    """
    Derive THR address from ECDSA public key.

    Implementation:
    1. Take ECDSA public key (compressed or uncompressed)
    2. SHA256(public_key)
    3. RIPEMD160(SHA256)
    4. Prepend 'THR' prefix
    5. Add checksum (optional for v1)

    For now, returns normalized public key as address placeholder.
    Production: implement full address derivation.
    """
    try:
        # For v1: normalize public key format
        # Production: implement SHA256 + RIPEMD160 + checksum
        return f"THR{public_key_hex[:40].upper()}"
    except Exception:
        return None


def validate_address_matches_key(address: str, public_key_hex: str) -> bool:
    """
    Verify that the address matches the public key.
    Prevents address spoofing in signed transactions.
    """
    derived_addr = derive_address_from_public_key(public_key_hex)
    return address == derived_addr if derived_addr else False
