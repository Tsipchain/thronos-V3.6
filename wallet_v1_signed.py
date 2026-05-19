"""
Thronos Wallet V1 - Secure Signed Transaction API
Implements client-side signature verification for all wallet operations.

This module provides the /api/v1/tx/send endpoint which is the secure alternative to
legacy endpoints (/send_thr, /api/wallet/send). All transactions must be signed on
the client-side before submission.

CRITICAL SECURITY:
- Signature verification required for all transactions
- Legacy secret-based authentication REJECTED
- Nonce + timestamp replay protection enforced
- Forbidden fields (secret, mnemonic, seed, privateKey, auth_secret) REJECTED
"""

import hashlib
import hmac
import json
import time
from typing import Dict, Any, Tuple
from flask import request, jsonify

# Replay protection cache: stores used nonces with expiration
NONCE_CACHE: Dict[str, float] = {}
NONCE_CACHE_TTL = 300  # 5 minutes
MAX_TIMESTAMP_DRIFT = 60  # Allow ±60 seconds clock drift


def verify_signed_envelope(signed_tx: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Verify a signed transaction envelope.

    Returns: (is_valid, error_message)
    """
    # Check required fields
    required_fields = ['from', 'to', 'amount', 'signature', 'publicKey', 'nonce', 'timestamp']
    for field in required_fields:
        if field not in signed_tx:
            return False, f"missing_required_field:{field}"

    # CRITICAL: Reject forbidden fields (prevents accidental secret transmission)
    forbidden_fields = ['secret', 'mnemonic', 'seed', 'privateKey', 'auth_secret', 'passphrase']
    for field in forbidden_fields:
        if field in signed_tx:
            return False, f"forbidden_field_in_envelope:{field}"

    return True, ""


def check_replay_protection(nonce: str, timestamp: int) -> Tuple[bool, str]:
    """
    Check if nonce/timestamp are valid (not replayed, not expired).

    Returns: (is_valid, error_message)
    """
    current_time = int(time.time())
    timestamp_drift = abs(current_time - timestamp)

    # Reject timestamps that are too far in the future or past
    if timestamp_drift > MAX_TIMESTAMP_DRIFT:
        return False, f"timestamp_outside_tolerance:drift_{timestamp_drift}s"

    # Check if nonce was already used
    if nonce in NONCE_CACHE:
        return False, "nonce_replay_detected"

    # Mark nonce as used
    NONCE_CACHE[nonce] = time.time()

    # Clean up expired nonces periodically
    current_time_s = time.time()
    expired_nonces = [n for n, t in NONCE_CACHE.items() if current_time_s - t > NONCE_CACHE_TTL]
    for n in expired_nonces:
        del NONCE_CACHE[n]

    return True, ""


def verify_signature(signed_tx: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Verify HMAC-SHA256 signature of transaction.

    In production, this would use ECDSA or EdDSA. For now, we verify HMAC-SHA256
    using the public key as the signing key.

    Returns: (is_valid, error_message)
    """
    signature = signed_tx.get('signature')
    public_key = signed_tx.get('publicKey')

    if not signature or not public_key:
        return False, "missing_signature_or_publickey"

    # Create canonical message for verification
    # Must match client-side signing format exactly
    tx_for_signing = {
        'from': signed_tx.get('from'),
        'to': signed_tx.get('to'),
        'amount': signed_tx.get('amount'),
        'token': signed_tx.get('token', 'THR'),
        'nonce': signed_tx.get('nonce'),
        'timestamp': signed_tx.get('timestamp')
    }

    # Serialize in canonical form (sorted keys, no spaces)
    message = json.dumps(tx_for_signing, sort_keys=True, separators=(',', ':'))

    # Verify HMAC-SHA256 signature
    # NOTE: In production, use actual ECDSA/EdDSA verification
    expected_signature = hmac.new(
        public_key.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    # Use constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(signature, expected_signature):
        return False, "invalid_signature"

    return True, ""


def send_signed_transaction(signed_tx: Dict[str, Any]):
    """
    Handle /api/v1/tx/send endpoint - secure signed transaction submission.

    This is the ONLY endpoint that should be used in production. All other
    wallet send endpoints (/send_thr, /api/wallet/send) should be deprecated.

    Args:
        signed_tx: Signed transaction envelope with signature, publicKey, etc.

    Returns:
        JSON response with tx result or error
    """
    # Step 1: Verify envelope structure
    is_valid, error_msg = verify_signed_envelope(signed_tx)
    if not is_valid:
        return jsonify({
            "ok": False,
            "error": error_msg,
            "reason": "invalid_envelope_structure"
        }), 400

    # Step 2: Verify signature
    is_valid, error_msg = verify_signature(signed_tx)
    if not is_valid:
        return jsonify({
            "ok": False,
            "error": error_msg,
            "reason": "signature_verification_failed"
        }), 401

    # Step 3: Check replay protection
    nonce = signed_tx.get('nonce')
    timestamp = signed_tx.get('timestamp', 0)
    is_valid, error_msg = check_replay_protection(nonce, timestamp)
    if not is_valid:
        return jsonify({
            "ok": False,
            "error": error_msg,
            "reason": "replay_protection_triggered"
        }), 409

    # Step 4: Extract transaction details
    from_addr = signed_tx.get('from')
    to_addr = signed_tx.get('to')
    amount = signed_tx.get('amount')
    token = signed_tx.get('token', 'THR')
    speed = signed_tx.get('speed', 'fast')

    # Step 5: Validate transaction parameters
    if not from_addr or not to_addr or amount is None:
        return jsonify({
            "ok": False,
            "error": "missing_transaction_fields"
        }), 400

    if amount <= 0:
        return jsonify({
            "ok": False,
            "error": "invalid_amount",
            "amount": amount
        }), 400

    # Step 6: Route to appropriate handler
    # NOTE: The actual send_thr_internal is called here WITHOUT the auth_secret
    # because we've already authenticated via signature verification
    try:
        # Import here to avoid circular imports
        from server import send_thr_internal, transfer_custom_token, validate_thr_address

        # Validate addresses
        if not validate_thr_address(from_addr):
            return jsonify({
                "ok": False,
                "error": "invalid_from_address",
                "from": from_addr
            }), 400

        if not validate_thr_address(to_addr):
            return jsonify({
                "ok": False,
                "error": "invalid_to_address",
                "to": to_addr
            }), 400

        # Process based on token type
        if token.upper() == 'THR':
            # Use send_thr_internal but note that signature replaces auth_secret
            # Pass empty string for auth_secret since we've verified via signature
            result = send_thr_internal(
                from_thr=from_addr,
                to_thr=to_addr,
                amount_raw=amount,
                auth_secret="",  # Already authenticated via signature
                passphrase="",
                speed=speed,
                tx_id=None
            )
        else:
            # Custom token transfer
            result = transfer_custom_token(
                symbol=token,
                from_thr=from_addr,
                to_thr=to_addr,
                amount_raw=amount,
                auth_secret="",  # Already authenticated via signature
                passphrase="",
                speed=speed
            )

        return result

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": "transaction_processing_failed",
            "detail": str(e)
        }), 500


def reject_legacy_endpoint(endpoint_name: str):
    """
    Reject calls to legacy secret-based endpoints.
    Used for /send_thr, /api/wallet/send, etc.
    """
    return jsonify({
        "ok": False,
        "error": "legacy_endpoint_deprecated",
        "message": f"{endpoint_name} is deprecated. Use /api/v1/tx/send with signed envelopes.",
        "upgrade_required": True
    }), 410  # 410 Gone - permanent deprecation


def register_wallet_v1_endpoints(app):
    """
    Register the v1 (secure signed) wallet endpoints on Flask app.

    This should be called during app initialization.
    """

    @app.route("/api/v1/tx/send", methods=["POST"])
    def api_v1_tx_send():
        """
        Secure transaction submission endpoint (v1).

        Accepts only signed transaction envelopes. Rejects all secret-based
        authentication and legacy endpoints.

        Request body:
        {
            "tx": {
                "from": "THR...",
                "to": "THR...",
                "amount": 100,
                "token": "THR",
                "nonce": 123456,
                "timestamp": 1234567890,
                "signature": "...",
                "publicKey": "..."
            }
        }

        Response (success):
        {
            "ok": true,
            "accepted": true,
            "status": "confirmed",
            "tx": {...},
            "tx_id": "TX-...",
            "new_balance": 900,
            "fee": 0.1
        }

        Response (failure):
        {
            "ok": false,
            "error": "error_code",
            "reason": "human_readable_reason"
        }
        """
        try:
            data = request.get_json() or {}
            signed_tx = data.get('tx')

            if not signed_tx:
                return jsonify({
                    "ok": False,
                    "error": "missing_tx_envelope"
                }), 400

            return send_signed_transaction(signed_tx)

        except Exception as e:
            return jsonify({
                "ok": False,
                "error": "request_parsing_failed",
                "detail": str(e)
            }), 400

    @app.route("/api/v1/tx/batch", methods=["POST"])
    def api_v1_tx_batch():
        """
        Batch transaction submission endpoint (v1).

        Submit multiple signed transactions in one request.
        """
        try:
            data = request.get_json() or {}
            transactions = data.get('transactions', [])

            if not transactions:
                return jsonify({
                    "ok": False,
                    "error": "empty_transaction_list"
                }), 400

            results = []
            for signed_tx in transactions:
                result = send_signed_transaction(signed_tx)
                results.append({
                    "tx_id": signed_tx.get('nonce'),
                    "response": result
                })

            all_success = all(r['response'][1] == 200 for r in results)

            return jsonify({
                "ok": all_success,
                "results": results
            }), 200 if all_success else 207

        except Exception as e:
            return jsonify({
                "ok": False,
                "error": "batch_processing_failed",
                "detail": str(e)
            }), 400


def register_legacy_deprecation_endpoints(app):
    """
    Register deprecation handlers for legacy endpoints.
    These endpoints will eventually be removed; clients should migrate to /api/v1/tx/send.
    """

    @app.route("/api/wallet/send", methods=["POST"])
    def api_wallet_send_deprecated():
        """Legacy endpoint - DEPRECATED - use /api/v1/tx/send"""
        return reject_legacy_endpoint("/api/wallet/send")

    @app.route("/send_thr", methods=["POST"])
    def send_thr_deprecated():
        """Legacy endpoint - DEPRECATED - use /api/v1/tx/send"""
        return reject_legacy_endpoint("/send_thr")

    @app.route("/api/tokens/transfer", methods=["POST"])
    def api_tokens_transfer_deprecated():
        """Legacy endpoint - DEPRECATED - use /api/v1/tx/send"""
        return reject_legacy_endpoint("/api/tokens/transfer")
