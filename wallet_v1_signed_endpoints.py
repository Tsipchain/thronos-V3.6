"""
Thronos Wallet V1 - Secure Signed Transaction Flask Endpoints

Production endpoints for signed transaction submission:
- /api/v1/tx/send - Primary production endpoint for signed envelopes
- Replica-aware: rejects on read-only replicas with 503 Service Unavailable
- Signature verification: ECDSA/secp256k1 via wallet_v1_production.py
- Nonce tracking: Redis-backed distributed storage
"""

from flask import request, jsonify
from typing import Dict, Any, Tuple
import json
import time


def register_wallet_v1_endpoints(app, wallet_v1_module, node_role: str, read_only: bool, send_thr_internal_fn, transfer_custom_token_fn, validate_address_fn):
    """
    Register wallet V1 signed transaction endpoints on Flask app.

    Args:
        app: Flask application
        wallet_v1_module: wallet_v1_production module with verification functions
        node_role: "master" or "replica"
        read_only: bool - true if node is read-only
        send_thr_internal_fn: reference to send_thr_internal function
        transfer_custom_token_fn: reference to transfer_custom_token function
        validate_address_fn: reference to validate_thr_address function
    """

    @app.route("/api/v1/tx/send", methods=["POST"])
    def api_v1_tx_send():
        """
        Secure transaction submission endpoint (v1).

        Accepts ONLY signed transaction envelopes.
        Rejects all secret-based authentication and legacy endpoints.
        Replica nodes reject with 503 (read-only).

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

        Response (read-only replica):
        {
            "ok": false,
            "error": "read_only_replica",
            "message": "This node is read-only. Submit to master at ...",
            "master_url": "..."
        }

        Response (failure):
        {
            "ok": false,
            "error": "error_code",
            "reason": "human_readable_reason"
        }
        """
        # CRITICAL: Replica check FIRST
        if read_only:
            return jsonify({
                "ok": False,
                "error": "read_only_replica",
                "message": "This node is read-only. Submit transactions to the master node.",
                "node_role": "replica"
            }), 503

        try:
            data = request.get_json() or {}
            signed_tx = data.get('tx')

            if not signed_tx:
                return jsonify({
                    "ok": False,
                    "error": "missing_tx_envelope"
                }), 400

            # Verify signed transaction
            is_valid, error_msg = wallet_v1_module.verify_signed_transaction_complete(signed_tx)
            if not is_valid:
                return jsonify({
                    "ok": False,
                    "error": error_msg.split(':')[0],
                    "detail": error_msg
                }), 400 if 'validation_failed' in error_msg else 401

            # Extract transaction details
            from_addr = signed_tx.get('from')
            to_addr = signed_tx.get('to')
            amount = signed_tx.get('amount')
            token = signed_tx.get('token', 'THR')
            speed = signed_tx.get('speed', 'fast')

            # Validate addresses
            if not validate_address_fn(from_addr):
                return jsonify({
                    "ok": False,
                    "error": "invalid_from_address"
                }), 400

            if not validate_address_fn(to_addr):
                return jsonify({
                    "ok": False,
                    "error": "invalid_to_address"
                }), 400

            # Validate amount
            if amount <= 0:
                return jsonify({
                    "ok": False,
                    "error": "invalid_amount"
                }), 400

            # Route to appropriate handler
            if token.upper() == 'THR':
                # Use send_thr_internal (already authenticated via signature)
                result = send_thr_internal_fn(
                    from_thr=from_addr,
                    to_thr=to_addr,
                    amount_raw=amount,
                    auth_secret="",  # Already authenticated via signature
                    passphrase="",
                    speed=speed,
                    tx_id=signed_tx.get('nonce')  # Use nonce as tx_id
                )
            else:
                # Custom token transfer (fee paid in THR)
                result = transfer_custom_token_fn(
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

    @app.route("/api/v1/tx/batch", methods=["POST"])
    def api_v1_tx_batch():
        """
        Batch transaction submission endpoint (v1).

        Submit multiple signed transactions in one request.
        Respects read-only replica check.
        """
        # CRITICAL: Replica check FIRST
        if read_only:
            return jsonify({
                "ok": False,
                "error": "read_only_replica",
                "message": "This node is read-only. Submit transactions to the master node."
            }), 503

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
                result = api_v1_tx_send_internal(signed_tx)
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

    def api_v1_tx_send_internal(signed_tx):
        """Internal handler for single transaction verification."""
        is_valid, error_msg = wallet_v1_module.verify_signed_transaction_complete(signed_tx)
        if not is_valid:
            return (jsonify({
                "ok": False,
                "error": error_msg.split(':')[0],
                "detail": error_msg
            }), 400)

        from_addr = signed_tx.get('from')
        to_addr = signed_tx.get('to')
        amount = signed_tx.get('amount')
        token = signed_tx.get('token', 'THR')
        speed = signed_tx.get('speed', 'fast')

        if not validate_address_fn(from_addr) or not validate_address_fn(to_addr):
            return (jsonify({"ok": False, "error": "invalid_address"}), 400)

        try:
            if token.upper() == 'THR':
                result = send_thr_internal_fn(
                    from_thr=from_addr,
                    to_thr=to_addr,
                    amount_raw=amount,
                    auth_secret="",
                    passphrase="",
                    speed=speed,
                    tx_id=signed_tx.get('nonce')
                )
            else:
                result = transfer_custom_token_fn(
                    symbol=token,
                    from_thr=from_addr,
                    to_thr=to_addr,
                    amount_raw=amount,
                    auth_secret="",
                    passphrase="",
                    speed=speed
                )
            return (result, 200)
        except Exception as e:
            return (jsonify({"ok": False, "error": str(e)}), 500)


def register_legacy_deprecation_endpoints(app):
    """
    Register deprecation handlers for legacy endpoints.

    These endpoints will be removed in production.
    Clients should migrate to /api/v1/tx/send.
    """

    @app.route("/api/wallet/send", methods=["POST"])
    def api_wallet_send_deprecated():
        """Legacy endpoint - DEPRECATED - use /api/v1/tx/send"""
        return jsonify({
            "ok": False,
            "error": "legacy_endpoint_deprecated",
            "message": "/api/wallet/send is deprecated. Use /api/v1/tx/send with signed envelopes.",
            "upgrade_required": True
        }), 410

    @app.route("/send_thr", methods=["POST"])
    def send_thr_deprecated():
        """Legacy endpoint - DEPRECATED - use /api/v1/tx/send"""
        return jsonify({
            "ok": False,
            "error": "legacy_endpoint_deprecated",
            "message": "/send_thr is deprecated. Use /api/v1/tx/send with signed envelopes.",
            "upgrade_required": True
        }), 410

    @app.route("/api/tokens/transfer", methods=["POST"])
    def api_tokens_transfer_deprecated():
        """Legacy endpoint - DEPRECATED - use /api/v1/tx/send"""
        return jsonify({
            "ok": False,
            "error": "legacy_endpoint_deprecated",
            "message": "/api/tokens/transfer is deprecated. Use /api/v1/tx/send with signed envelopes.",
            "upgrade_required": True
        }), 410
