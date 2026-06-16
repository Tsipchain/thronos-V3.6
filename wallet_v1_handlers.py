from flask import jsonify
import json
import os
from datetime import datetime, UTC
from pathlib import Path
import wallet_v1_production_final as wallet_v1_prod
from wallet_v1_activation import require_active_thr_address, AdmissionError
from wallet_v1_migration import migrate_legacy_address, repair_migration, resolve_migration, _remaining_old_token_count
from wallet_v1_address_derivation import derive_thronos_address, validate_thronos_address

_WALLET_V1_LOADED = False
_WALLET_V1_INIT_ERROR = None

WALLET_V1_PUBLIC_KEY_BINDINGS_FILE = Path('data/wallet_v1_public_key_bindings.json')


def _now_iso():
    return datetime.now(UTC).isoformat().replace('+00:00', 'Z')


def _load_public_key_bindings():
    if not WALLET_V1_PUBLIC_KEY_BINDINGS_FILE.exists():
        return {'bindings': {}}
    try:
        data = json.loads(WALLET_V1_PUBLIC_KEY_BINDINGS_FILE.read_text())
        if isinstance(data, dict) and isinstance(data.get('bindings'), dict):
            return data
    except Exception:
        pass
    return {'bindings': {}}


def _save_public_key_bindings(data):
    WALLET_V1_PUBLIC_KEY_BINDINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    WALLET_V1_PUBLIC_KEY_BINDINGS_FILE.write_text(json.dumps(data, indent=2, sort_keys=True))


def _binding_addresses_related(address, credential_lookup_address):
    if address == credential_lookup_address:
        return True
    rec = resolve_migration(credential_lookup_address)
    return bool(rec and rec.get('new_v1_address') == address)


def _require_repair_token(request):
    token = request.headers.get('X-Repair-Token') or request.headers.get('X-Admin-Token')
    required = os.getenv('WALLET_V1_REPAIR_TOKEN', '')
    return bool(required and token == required)

_WALLET_V1_LOADED = False
_WALLET_V1_INIT_ERROR = None

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
    """Persist an already-verified V1 signed transfer (THR or custom token).

    Ownership of `from` is already proven via ECDSA signature verification
    (verify_signed_transaction_core), so this intentionally bypasses the
    legacy auth_secret/BTC-pledge gate (validate_effective_auth) used by
    send_thr_internal/transfer_custom_token — re-imposing that gate here
    would defeat the purpose of the V1 signed-envelope flow and incorrectly
    block V1 wallets that never made a BTC pledge.
    """
    import wallet_v1_execution_adapter as _adapter
    token = (signed_tx.get('token') or 'THR').upper()
    if token == 'THR':
        ok, result, status = _adapter.execute_verified_signed_transfer(signed_tx)
    else:
        ok, result, status = _adapter.execute_verified_signed_token_transfer(token, signed_tx)
    return jsonify(result), status


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
    remaining_old_token_count = rec.get('remaining_old_token_count')
    if remaining_old_token_count is None:
        try:
            remaining_old_token_count = _remaining_old_token_count(old)
        except Exception:
            remaining_old_token_count = 0
    assets_migrated = bool(rec.get('assets_migrated', False)) and int(remaining_old_token_count) == 0
    return jsonify({
        'ok': True,
        'old_address': rec.get('old_address') or old,
        'new_v1_address': rec.get('new_v1_address'),
        'status': rec.get('status'),
        'migration_tx': migration_tx,
        'admission_only': bool(rec.get('admission_only', False)),
        'assets_migrated': assets_migrated,
        'repair_tx_id': rec.get('repair_tx_id', ''),
        'moved_token_count': int(rec.get('moved_token_count', 0) or 0),
        'remaining_old_token_count': int(remaining_old_token_count or 0),
        'ecosystem_bindings_repaired': bool(rec.get('ecosystem_bindings_repaired', False)),
        'music_bindings_repaired': bool(rec.get('music_bindings_repaired', False)),
    }), 200


def handle_wallet_bind_public_key(request):
    data = request.get_json() or {}
    address = (data.get('address') or '').strip()
    credential_lookup_address = (data.get('credential_lookup_address') or address).strip()
    public_key = (data.get('public_key') or '').strip()
    auth_secret = (data.get('auth_secret') or '').strip()
    passphrase = (data.get('passphrase') or '').strip()

    if not address or not credential_lookup_address or not public_key:
        return jsonify({'ok': False, 'error': 'missing_binding_fields'}), 400
    if not validate_thronos_address(address) or not validate_thronos_address(credential_lookup_address):
        return jsonify({'ok': False, 'error': 'invalid_address'}), 400
    if not _binding_addresses_related(address, credential_lookup_address):
        return jsonify({'ok': False, 'error': 'credential_lookup_address_mismatch'}), 403
    try:
        public_key_address = derive_thronos_address(public_key)
    except ValueError as ve:
        return jsonify({'ok': False, 'error': 'invalid_public_key', 'detail': str(ve)}), 400

    from server import validate_effective_auth
    ok, _state, error_key = validate_effective_auth(credential_lookup_address, auth_secret, passphrase)
    if not ok:
        status = 400 if error_key in ('missing_auth_secret', 'passphrase_required') else 403
        return jsonify({'ok': False, 'error': error_key or 'invalid_auth'}), status

    store = _load_public_key_bindings()
    binding = {
        'address': address,
        'credential_lookup_address': credential_lookup_address,
        'public_key': public_key,
        'public_key_address': public_key_address,
        'bound_at': _now_iso(),
        'proof': 'legacy_auth_secret',
    }
    store.setdefault('bindings', {})[address] = binding
    _save_public_key_bindings(store)
    return jsonify({'ok': True, 'binding': binding}), 200
