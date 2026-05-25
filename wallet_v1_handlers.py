"""Wallet V1 handlers."""

import os
from flask import jsonify
import wallet_v1_production_final as wallet_v1_prod
from wallet_v1_activation import require_active_thr_address, AdmissionError
from wallet_v1_migration import migrate_legacy_address, repair_migration
from wallet_v1_address_derivation import derive_thronos_address, validate_thronos_address


_WALLET_V1_LOADED = False
_WALLET_V1_INIT_ERROR = None


def init_wallet_v1_handler(app, redis_client, node_role="master", read_only=False, sqlite_path=None):
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


def execute_verified_signed_transfer(signed_tx):
    from server import send_thr_internal
    return send_thr_internal(
        from_thr=signed_tx.get('from'),
        to_thr=signed_tx.get('to'),
        amount_raw=signed_tx.get('amount'),
        auth_secret="",
        passphrase="",
        speed=signed_tx.get('speed', 'fast'),
        tx_id=signed_tx.get('nonce'),
    )


def handle_tx_send(request):
    try:
        if not _WALLET_V1_LOADED:
            return jsonify({'ok': False, 'error': 'wallet_v1_not_initialized', 'detail': _WALLET_V1_INIT_ERROR}), 503

        data = request.get_json() or {}
        signed_tx = data.get('tx')
        if not signed_tx:
            return jsonify({'ok': False, 'error': 'missing_tx_envelope'}), 400

        if wallet_v1_prod.NODE_ROLE == 'replica' or wallet_v1_prod.READ_ONLY:
            return jsonify({'ok': False, 'error': 'read_only_replica'}), 503

        is_valid, error_msg = wallet_v1_prod.verify_signed_transaction_core(signed_tx)
        if not is_valid:
            return jsonify({'ok': False, 'error': error_msg.split(':')[0], 'detail': error_msg}), 400

        try:
            require_active_thr_address(signed_tx.get('from'))
        except AdmissionError as ae:
            return jsonify({'ok': False, 'error': str(ae)}), 403

        if (signed_tx.get('token') or 'THR').upper() != 'THR':
            return jsonify({'ok': False, 'error': 'unsupported_token'}), 400

        return execute_verified_signed_transfer(signed_tx)
    except Exception as e:
        return jsonify({'ok': False, 'error': 'transaction_processing_failed', 'detail': str(e)}), 500


def handle_wallet_health():
    return jsonify({
        'ok': True,
        'wallet_v1_loaded': bool(_WALLET_V1_LOADED),
        'node_role': getattr(wallet_v1_prod, 'NODE_ROLE', 'master'),
        'read_only': bool(getattr(wallet_v1_prod, 'READ_ONLY', False)),
        'init_error': _WALLET_V1_INIT_ERROR,
    }), 200


def handle_address_derivation(request):
    try:
        data = request.get_json() or {}
        public_key = data.get('public_key')
        if not public_key:
            return jsonify({'ok': False, 'error': 'missing_public_key'}), 400
        address = derive_thronos_address(public_key)
        if not validate_thronos_address(address):
            return jsonify({'ok': False, 'error': 'address_derivation_failed'}), 500
        return jsonify({'ok': True, 'public_key': public_key, 'address': address}), 200
    except ValueError as ve:
        return jsonify({'ok': False, 'error': 'invalid_public_key', 'detail': str(ve)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': 'address_derivation_failed', 'detail': str(e)}), 500


def handle_wallet_migrate(request):
    data = request.get_json() or {}
    try:
        rec = migrate_legacy_address(
            data.get('old_thr_address'),
            data.get('legacy_secret'),
            data.get('new_compressed_public_key'),
        )
        return jsonify({'ok': True, 'migration': rec}), 200
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


def handle_wallet_migration_repair(request):
    token = request.headers.get('X-Repair-Token') or request.headers.get('X-Admin-Token')
    required = os.getenv('WALLET_V1_REPAIR_TOKEN', '')
    if not required or token != required:
        return jsonify({'ok': False, 'error': 'unauthorized_repair'}), 403
    data = request.get_json() or {}
    try:
        out = repair_migration(data.get('old_address'), data.get('new_v1_address'))
        return jsonify(out), 200
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


