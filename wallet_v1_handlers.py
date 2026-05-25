from flask import jsonify
import os
import wallet_v1_production_final as wallet_v1_prod
from wallet_v1_activation import require_active_thr_address, AdmissionError
from wallet_v1_migration import migrate_legacy_address, repair_migration, resolve_migration
from wallet_v1_address_derivation import derive_thronos_address, validate_thronos_address

_WALLET_V1_LOADED = False
_WALLET_V1_INIT_ERROR = None


def _require_repair_token(request):
    token = request.headers.get('X-Repair-Token') or request.headers.get('X-Admin-Token')
    required = os.getenv('WALLET_V1_REPAIR_TOKEN', '')
    return bool(required and token == required)


def init_wallet_v1_handler(app, redis_client, node_role="master", read_only=False, sqlite_path=None):
    global _WALLET_V1_LOADED, _WALLET_V1_INIT_ERROR
    try:
        wallet_v1_prod.init_wallet_v1(redis_client, node_role, read_only, sqlite_path)
        _WALLET_V1_LOADED = True
        _WALLET_V1_INIT_ERROR = None
    except Exception as e:
        _WALLET_V1_LOADED = False
        _WALLET_V1_INIT_ERROR = str(e)
        raise


def execute_verified_signed_transfer(signed_tx):
    from server import send_thr_internal
    return send_thr_internal(
        from_thr=signed_tx.get('from'), to_thr=signed_tx.get('to'), amount_raw=signed_tx.get('amount'),
        auth_secret='', passphrase='', speed=signed_tx.get('speed', 'fast'), tx_id=signed_tx.get('nonce')
    )


def handle_tx_send(request):
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


def handle_wallet_health():
    return jsonify({'ok': True, 'wallet_v1_loaded': bool(_WALLET_V1_LOADED), 'node_role': getattr(wallet_v1_prod, 'NODE_ROLE', 'master'), 'read_only': bool(getattr(wallet_v1_prod, 'READ_ONLY', False)), 'init_error': _WALLET_V1_INIT_ERROR}), 200


def handle_address_derivation(request):
    data = request.get_json() or {}
    public_key = data.get('public_key')
    if not public_key:
        return jsonify({'ok': False, 'error': 'missing_public_key'}), 400
    try:
        address = derive_thronos_address(public_key)
        if not validate_thronos_address(address):
            return jsonify({'ok': False, 'error': 'address_derivation_failed'}), 500
        return jsonify({'ok': True, 'public_key': public_key, 'address': address}), 200
    except ValueError as ve:
        return jsonify({'ok': False, 'error': 'invalid_public_key', 'detail': str(ve)}), 400


def handle_wallet_migrate(request):
    data = request.get_json() or {}
    try:
        rec = migrate_legacy_address(data.get('old_thr_address'), data.get('legacy_secret'), data.get('new_compressed_public_key'))
        return jsonify({'ok': True, 'migration': rec}), 200
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


def handle_wallet_migration_repair(request):
    if not _require_repair_token(request):
        return jsonify({'ok': False, 'error': 'unauthorized_repair'}), 403
    data = request.get_json() or {}
    try:
        return jsonify(repair_migration(data.get('old_address'), data.get('new_v1_address'))), 200
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


def handle_wallet_migration_status(request):
    if not _require_repair_token(request):
        return jsonify({'ok': False, 'error': 'unauthorized_repair'}), 403
    data = request.get_json() or {}
    old = data.get('old_address')
    if not old:
        return jsonify({'ok': False, 'error': 'missing_old_address'}), 400
    rec = resolve_migration(old)
    if not rec:
        return jsonify({'ok': False, 'error': 'migration_record_not_found'}), 404
    tx = rec.get('migration_tx')
    migration_tx = tx.get('tx_id') if isinstance(tx, dict) else tx
    return jsonify({
        'ok': True,
        'old_address': rec.get('old_address') or old,
        'new_v1_address': rec.get('new_v1_address'),
        'status': rec.get('status'),
        'migration_tx': migration_tx,
        'admission_only': bool(rec.get('admission_only', False)),
        'assets_migrated': bool(rec.get('assets_migrated', False)),
    }), 200
