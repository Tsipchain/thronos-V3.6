"""
Wallet V1 - Simplified Endpoint Handlers

These handlers are called by wallet_v1_blueprint.py and work with the
production verification logic in wallet_v1_production_final.py.

Initialization:
    call_wallet_v1_init_handler(app, redis_client, node_role, read_only, sqlite_path)
"""

from flask import jsonify
import wallet_v1_production_final as wallet_v1_prod
from wallet_v1_activation import require_active_thr_address, AdmissionError
from wallet_v1_migration import migrate_legacy_address
from wallet_v1_address_derivation import (
    derive_thronos_address,
    validate_thronos_address,
)


_WALLET_V1_LOADED = False
_WALLET_V1_INIT_ERROR = None


def init_wallet_v1_handler(app, redis_client, node_role="master", read_only=False, sqlite_path=None):
    """
    Initialize Wallet V1 with Flask app dependencies.

    Called from wallet_v1_blueprint.register_wallet_v1_routes().
    """
    global _WALLET_V1_LOADED, _WALLET_V1_INIT_ERROR
    try:
        wallet_v1_prod.init_wallet_v1(redis_client, node_role, read_only, sqlite_path)
        _WALLET_V1_LOADED = True
        _WALLET_V1_INIT_ERROR = None
        app.logger.info("[WalletV1] Handlers initialized: node_role=%s, read_only=%s", node_role, read_only)
    except Exception as e:
        _WALLET_V1_LOADED = False
        _WALLET_V1_INIT_ERROR = str(e)
        app.logger.error("[WalletV1] Initialization failed: %s", e)
        raise


def handle_tx_send(request):
    """
    Handle POST /api/v1/tx/send - ECDSA/secp256k1 signed transaction submission.

    Expected request JSON:
    {
        "tx": {
            "from": "THR...",
            "to": "THR...",
            "amount": 100,
            "token": "THR",
            "nonce": "tx_...",
            "timestamp": 1710000000,
            "signature": "304402...",
            "publicKey": "0279be667ef..."
        }
    }
    """
    try:
        if not _WALLET_V1_LOADED:
            return jsonify({
                "ok": False,
                "error": "wallet_v1_not_initialized",
                "detail": _WALLET_V1_INIT_ERROR or "wallet_v1 init not completed"
            }), 503

        data = request.get_json() or {}
        signed_tx = data.get('tx')

        if not signed_tx:
            return jsonify({
                "ok": False,
                "error": "missing_tx_envelope"
            }), 400

        # Replica check first (fail-closed)
        if wallet_v1_prod.NODE_ROLE == "replica" or wallet_v1_prod.READ_ONLY:
            return jsonify({
                "ok": False,
                "error": "read_only_replica",
                "message": "This node is read-only. Submit transactions to the master node."
            }), 503

        # Verify signature, address derivation, timestamp, nonce
        is_valid, error_msg = wallet_v1_prod.verify_signed_transaction_core(signed_tx)
        if not is_valid:
            return jsonify({
                "ok": False,
                "error": error_msg.split(':')[0],
                "detail": error_msg
            }), 400

        # Admission check: cryptographic ownership is not enough.
        # Address must also be network-admitted (BTC pledge / whitelist / legacy policy).
        try:
            require_active_thr_address(signed_tx.get("from"))
        except AdmissionError as admission_err:
            return jsonify({
                "ok": False,
                "error": str(admission_err),
                "detail": "Address has no active network admission (pledge/whitelist).",
            }), 403

        return jsonify({
            "ok": True,
            "message": "Signed transaction verified and accepted",
            "tx_id": signed_tx.get('nonce'),
            "from": signed_tx.get('from'),
            "to": signed_tx.get('to'),
            "amount": signed_tx.get('amount'),
            "token": signed_tx.get('token', 'THR'),
            "timestamp": signed_tx.get('timestamp')
        }), 200

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": "transaction_processing_failed",
            "detail": str(e)
        }), 500


def handle_wallet_health():
    """Return Wallet V1 runtime diagnostics."""
    return jsonify({
        "ok": True,
        "wallet_v1_loaded": _WALLET_V1_LOADED,
        "node_role": wallet_v1_prod.NODE_ROLE,
        "read_only": bool(wallet_v1_prod.READ_ONLY),
        "redis_present": wallet_v1_prod.REDIS_CLIENT is not None,
        "sqlite_path_present": bool(wallet_v1_prod.MASTER_SQLITE_PATH),
        "init_error": _WALLET_V1_INIT_ERROR,
    }), 200


def handle_address_derivation(request):
    """
    Handle POST /api/v1/address/derive - Derive Thronos address from public key.

    Expected request JSON:
    {
        "public_key": "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
    }
    """
    try:
        data = request.get_json() or {}
        public_key = data.get('public_key')

        if not public_key:
            return jsonify({
                "ok": False,
                "error": "missing_public_key"
            }), 400

        # Derive address
        address = derive_thronos_address(public_key)

        # Validate format
        if not validate_thronos_address(address):
            return jsonify({
                "ok": False,
                "error": "address_derivation_failed",
                "detail": "Derived address failed validation"
            }), 500

        return jsonify({
            "ok": True,
            "public_key": public_key,
            "address": address
        }), 200

    except ValueError as ve:
        return jsonify({
            "ok": False,
            "error": "invalid_public_key",
            "detail": str(ve)
        }), 400
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": "address_derivation_failed",
            "detail": str(e)
        }), 500


def handle_wallet_migrate(request):
    """Handle POST /api/v1/wallet/migrate."""
    try:
        data = request.get_json() or {}
        old_thr_address = data.get("old_thr_address")
        legacy_secret = data.get("legacy_secret")
        new_compressed_public_key = data.get("new_compressed_public_key")
        rec = migrate_legacy_address(old_thr_address, legacy_secret, new_compressed_public_key)
        return jsonify({
            "ok": True,
            "migration": {
                "old_address": rec["old_address"],
                "new_v1_address": rec["new_v1_address"],
                "migrated_at": rec["migrated_at"],
                "old_read_only": rec["old_read_only"],
            }
        }), 200
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": "migration_failed", "detail": str(e)}), 500
