"""
Physical Assets API Blueprint — REST endpoints for the Thronos Physical Asset Registry.

Routes are prefixed at /api/assets.
All state-changing endpoints require signed wallet action intents.
"""

from flask import Blueprint, jsonify, request

physical_assets_bp = Blueprint('physical_assets', __name__, url_prefix='/api/assets')

# Injected at registration time
_verify_wallet_action_intent = None
_verify_action_payload_hash = None
_pa_service = None
_node_role = 'master'
_read_only = False


def init_physical_assets_blueprint(
    verify_intent_fn,
    verify_payload_hash_fn,
    pa_service_module,
    node_role='master',
    read_only=False,
):
    global _verify_wallet_action_intent, _verify_action_payload_hash
    global _pa_service, _node_role, _read_only
    _verify_wallet_action_intent = verify_intent_fn
    _verify_action_payload_hash = verify_payload_hash_fn
    _pa_service = pa_service_module
    _node_role = node_role
    _read_only = read_only


def _write_guard():
    if _read_only or _node_role != 'master':
        return jsonify(ok=False, error='read_only_replica'), 503
    return None


def _require_signed_intent(data, allowed_action='physical_asset_register'):
    intent_raw = data.get('intent')
    signature = (data.get('signature') or '').strip()
    public_key = (data.get('public_key') or '').strip()

    if not (intent_raw and signature and public_key):
        return None, None, (
            jsonify(ok=False, error='signed_wallet_action_required',
                    detail='intent, signature, and public_key are required'), 401
        )

    intent = intent_raw if isinstance(intent_raw, dict) else {}
    ok, err_code, err_detail = _verify_wallet_action_intent(intent, signature, public_key)
    if not ok:
        return None, None, (jsonify(ok=False, error=err_code, detail=err_detail), 400)

    payload = data.get('payload') or {}
    if not _verify_action_payload_hash(intent.get('payload_hash', ''), payload):
        return None, None, (
            jsonify(ok=False, error='payload_hash_mismatch',
                    detail='payload does not match signed intent'), 400
        )

    from_thr = str(intent.get('from_thr', '')).strip().upper()
    return from_thr, payload, None


# ── Public read endpoints ────────────────────────────────────────────────────

@physical_assets_bp.route('/<asset_id>', methods=['GET'])
def get_asset(asset_id):
    asset = _pa_service.get_asset(asset_id)
    if not asset:
        return jsonify(ok=False, error='asset_not_found'), 404
    return jsonify(ok=True, asset=asset), 200


@physical_assets_bp.route('/serial/<serial>', methods=['GET'])
def get_asset_by_serial(serial):
    asset = _pa_service.get_asset_by_serial(serial)
    if not asset:
        return jsonify(ok=False, error='asset_not_found'), 404
    return jsonify(ok=True, asset=asset), 200


@physical_assets_bp.route('/<asset_id>/proof', methods=['GET'])
def get_asset_proof(asset_id):
    proof = _pa_service.get_asset_proof(asset_id)
    if not proof:
        return jsonify(ok=False, error='asset_not_found'), 404
    return jsonify(ok=True, proof=proof), 200


@physical_assets_bp.route('/', methods=['GET'])
def list_assets():
    tenant_id = request.args.get('tenant_id')
    product_id = request.args.get('product_id')
    state = request.args.get('state')
    creator = request.args.get('creator')
    try:
        limit = min(100, max(1, int(request.args.get('limit', 50))))
        offset = max(0, int(request.args.get('offset', 0)))
    except (ValueError, TypeError):
        limit, offset = 50, 0

    assets = _pa_service.list_assets(
        tenant_id=tenant_id,
        product_id=product_id,
        state=state,
        creator_address=creator,
        limit=limit,
        offset=offset,
    )
    return jsonify(ok=True, assets=assets, count=len(assets)), 200


# ── Authenticated state-changing endpoints ───────────────────────────────────

@physical_assets_bp.route('/register', methods=['POST'])
def register_asset():
    guard = _write_guard()
    if guard:
        return guard

    data = request.get_json() or {}
    from_thr, payload, err_resp = _require_signed_intent(data, 'physical_asset_register')
    if err_resp:
        return err_resp

    ok, result = _pa_service.register_asset(
        tenant_id=str(payload.get('tenant_id', '')).strip(),
        product_id=str(payload.get('product_id', '')).strip(),
        sku=str(payload.get('sku', '')).strip().upper(),
        serial=str(payload.get('serial', '')).strip().upper(),
        edition_number=payload.get('edition_number'),
        edition_size=payload.get('edition_size'),
        creator_address=from_thr,
        design_hash=str(payload.get('design_hash', '')).strip(),
        asset_type=str(payload.get('asset_type', 'COLLECTIBLE')).strip().upper(),
        idempotency_key=str(payload.get('idempotency_key', '')).strip() or None,
        metadata=payload.get('metadata'),
    )

    if not ok:
        return jsonify(ok=False, **result), 400
    return jsonify(ok=True, asset=result), 201


@physical_assets_bp.route('/<asset_id>/mint', methods=['POST'])
def mint_asset(asset_id):
    guard = _write_guard()
    if guard:
        return guard

    data = request.get_json() or {}
    from_thr, payload, err_resp = _require_signed_intent(data, 'nft_mint')
    if err_resp:
        return err_resp

    ok, result = _pa_service.mint_asset_nft(
        asset_id=asset_id,
        from_address=from_thr,
    )

    if not ok:
        status = 404 if result.get('error') == 'asset_not_found' else 400
        return jsonify(ok=False, **result), status
    return jsonify(ok=True, **result), 201


@physical_assets_bp.route('/<asset_id>/claim', methods=['POST'])
def claim_asset(asset_id):
    guard = _write_guard()
    if guard:
        return guard

    data = request.get_json() or {}

    claim_secret = str(data.get('claim_secret', '')).strip()
    new_owner = str(data.get('new_owner_address', '')).strip()

    if not claim_secret:
        return jsonify(ok=False, error='claim_secret_required'), 400
    if not new_owner:
        return jsonify(ok=False, error='new_owner_address_required'), 400

    ok, result = _pa_service.claim_asset(
        asset_id=asset_id,
        claim_secret=claim_secret,
        new_owner_address=new_owner,
    )

    if not ok:
        status = 404 if result.get('error') == 'asset_not_found' else 400
        return jsonify(ok=False, **result), status
    return jsonify(ok=True, **result), 200


@physical_assets_bp.route('/<asset_id>/transfer', methods=['POST'])
def transfer_asset(asset_id):
    guard = _write_guard()
    if guard:
        return guard

    data = request.get_json() or {}
    from_thr, payload, err_resp = _require_signed_intent(data, 'physical_asset_transfer')
    if err_resp:
        return err_resp

    to_address = str(payload.get('to_address', '')).strip()
    if not to_address:
        return jsonify(ok=False, error='to_address_required'), 400

    ok, result = _pa_service.transfer_asset(
        asset_id=asset_id,
        from_address=from_thr,
        to_address=to_address,
    )

    if not ok:
        status = 404 if result.get('error') == 'asset_not_found' else 400
        return jsonify(ok=False, **result), status
    return jsonify(ok=True, **result), 200


# ── Admin / internal endpoints ───────────────────────────────────────────────

@physical_assets_bp.route('/<asset_id>/claim-secret', methods=['POST'])
def set_claim_secret(asset_id):
    guard = _write_guard()
    if guard:
        return guard

    data = request.get_json() or {}
    from_thr, payload, err_resp = _require_signed_intent(data, 'physical_asset_register')
    if err_resp:
        return err_resp

    asset = _pa_service.get_asset(asset_id)
    if not asset:
        return jsonify(ok=False, error='asset_not_found'), 404
    if from_thr != asset['creator_address']:
        return jsonify(ok=False, error='unauthorized'), 403

    claim_secret = str(payload.get('claim_secret', '')).strip()
    if not claim_secret:
        return jsonify(ok=False, error='claim_secret_required'), 400

    ok, result = _pa_service.set_claim_secret(asset_id, claim_secret)
    if not ok:
        return jsonify(ok=False, **result), 400
    return jsonify(ok=True, **result), 200


@physical_assets_bp.route('/<asset_id>/state', methods=['POST'])
def update_state(asset_id):
    guard = _write_guard()
    if guard:
        return guard

    data = request.get_json() or {}
    from_thr, payload, err_resp = _require_signed_intent(data, 'physical_asset_register')
    if err_resp:
        return err_resp

    asset = _pa_service.get_asset(asset_id)
    if not asset:
        return jsonify(ok=False, error='asset_not_found'), 404
    if from_thr != asset['creator_address']:
        return jsonify(ok=False, error='unauthorized'), 403

    new_state = str(payload.get('state', '')).strip().upper()
    ok, result = _pa_service.update_asset_state(asset_id, new_state, from_thr)
    if not ok:
        return jsonify(ok=False, **result), 400
    return jsonify(ok=True, asset=result), 200
