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
    for forbidden in ('private_key', 'secret_key', 'secret'):
        if data.get(forbidden):
            return None, None, (
                jsonify(ok=False, error='raw_secret_in_request',
                        detail=f'{forbidden} must never be sent in requests'), 400
            )

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


# ── Production endpoints (Stage 2) ────────────────────────────────────────

@physical_assets_bp.route('/creators/approve', methods=['POST'])
def approve_creator():
    guard = _write_guard()
    if guard:
        return guard

    data = request.get_json() or {}
    from_thr, payload, err_resp = _require_signed_intent(data, 'physical_asset_register')
    if err_resp:
        return err_resp

    tenant_id = str(payload.get('tenant_id', '')).strip()
    creator_address = str(payload.get('creator_address', '')).strip()
    if not tenant_id:
        return jsonify(ok=False, error='tenant_id_required'), 400
    if not creator_address:
        return jsonify(ok=False, error='creator_address_required'), 400

    roles = payload.get('roles')
    allowed_product_ids = payload.get('allowed_product_ids')

    ok, result = _pa_service.approve_creator(
        tenant_id=tenant_id,
        creator_address=creator_address,
        roles=roles,
        allowed_product_ids=allowed_product_ids,
    )
    if not ok:
        return jsonify(ok=False, **result), 400
    return jsonify(ok=True, creator=result), 201


@physical_assets_bp.route('/batches', methods=['POST'])
def create_batch():
    guard = _write_guard()
    if guard:
        return guard

    data = request.get_json() or {}
    from_thr, payload, err_resp = _require_signed_intent(data, 'physical_asset_produce')
    if err_resp:
        return err_resp

    batch_id = str(payload.get('batch_id', '')).strip()
    if not batch_id:
        return jsonify(ok=False, error='batch_id_required'), 400

    try:
        quantity = int(payload.get('quantity', 0))
        edition_start = int(payload.get('edition_start', 0))
        edition_size = int(payload.get('edition_size', 0))
        creation_fee = float(payload.get('creation_fee', 0))
    except (ValueError, TypeError):
        return jsonify(ok=False, error='invalid_numeric_field'), 400

    ok, result = _pa_service.create_production_batch(
        batch_id=batch_id,
        tenant_id=str(payload.get('tenant_id', '')).strip(),
        product_id=str(payload.get('product_id', '')).strip(),
        sku=str(payload.get('sku', '')).strip().upper(),
        creator_address=from_thr,
        quantity=quantity,
        edition_start=edition_start,
        edition_size=edition_size,
        design_hash=str(payload.get('design_hash', '')).strip(),
        design_format=str(payload.get('design_format', '3mf')).strip().lower(),
        creation_fee=creation_fee,
    )

    if not ok:
        return jsonify(ok=False, **result), 400
    return jsonify(ok=True, **result), 201


@physical_assets_bp.route('/batches/<batch_id>', methods=['GET'])
def get_batch(batch_id):
    batch = _pa_service.get_batch(batch_id)
    if not batch:
        return jsonify(ok=False, error='batch_not_found'), 404
    return jsonify(ok=True, batch=batch), 200


@physical_assets_bp.route('/jobs', methods=['GET'])
def list_jobs():
    batch_id = request.args.get('batch_id')
    status = request.args.get('status')
    jobs = _pa_service.list_jobs(batch_id=batch_id, status=status)
    return jsonify(ok=True, jobs=jobs, count=len(jobs)), 200


@physical_assets_bp.route('/jobs/<job_id>', methods=['GET'])
def get_job(job_id):
    job = _pa_service.get_job(job_id)
    if not job:
        return jsonify(ok=False, error='job_not_found'), 404
    return jsonify(ok=True, job=job), 200


@physical_assets_bp.route('/jobs/<job_id>/status', methods=['GET'])
def get_job_status(job_id):
    status = _pa_service.get_production_status(job_id)
    if not status:
        return jsonify(ok=False, error='job_not_found'), 404
    return jsonify(ok=True, **status), 200


@physical_assets_bp.route('/jobs/<job_id>/gcode', methods=['POST'])
def upload_gcode(job_id):
    guard = _write_guard()
    if guard:
        return guard

    data = request.get_json() or {}
    from_thr, payload, err_resp = _require_signed_intent(data, 'physical_asset_produce')
    if err_resp:
        return err_resp

    gcode_hash = str(payload.get('gcode_hash', '')).strip()
    if not gcode_hash:
        return jsonify(ok=False, error='gcode_hash_required'), 400

    ok, result = _pa_service.upload_job_gcode(
        job_id=job_id,
        gcode_hash=gcode_hash,
        creator_address=from_thr,
    )

    if not ok:
        status = 404 if result.get('error') == 'job_not_found' else 400
        return jsonify(ok=False, **result), status
    return jsonify(ok=True, job=result), 200


@physical_assets_bp.route('/jobs/<job_id>/start', methods=['POST'])
def start_job(job_id):
    guard = _write_guard()
    if guard:
        return guard

    data = request.get_json() or {}
    from_thr, payload, err_resp = _require_signed_intent(data, 'physical_asset_produce')
    if err_resp:
        return err_resp

    printer_id = str(payload.get('printer_id', '')).strip()
    if not printer_id:
        return jsonify(ok=False, error='printer_id_required'), 400

    ok, result = _pa_service.start_print_job(
        job_id=job_id,
        printer_id=printer_id,
        creator_address=from_thr,
    )

    if not ok:
        status = 404 if result.get('error') == 'job_not_found' else 400
        return jsonify(ok=False, **result), status
    return jsonify(ok=True, job=result), 200


@physical_assets_bp.route('/jobs/<job_id>/fail', methods=['POST'])
def fail_job(job_id):
    guard = _write_guard()
    if guard:
        return guard

    data = request.get_json() or {}
    from_thr, payload, err_resp = _require_signed_intent(data, 'physical_asset_produce')
    if err_resp:
        return err_resp

    reason = str(payload.get('reason', '')).strip()

    ok, result = _pa_service.fail_print_job(
        job_id=job_id,
        creator_address=from_thr,
        reason=reason,
    )

    if not ok:
        status = 404 if result.get('error') == 'job_not_found' else 400
        return jsonify(ok=False, **result), status
    return jsonify(ok=True, job=result), 200


@physical_assets_bp.route('/jobs/<job_id>/complete', methods=['POST'])
def complete_job(job_id):
    guard = _write_guard()
    if guard:
        return guard

    data = request.get_json() or {}
    from_thr, payload, err_resp = _require_signed_intent(data, 'physical_asset_produce')
    if err_resp:
        return err_resp

    ok, result = _pa_service.complete_print_job(
        job_id=job_id,
        creator_address=from_thr,
    )

    if not ok:
        status = 404 if result.get('error') == 'job_not_found' else 400
        return jsonify(ok=False, **result), status
    return jsonify(ok=True, job=result), 200


@physical_assets_bp.route('/jobs/<job_id>/sign', methods=['POST'])
def sign_job(job_id):
    guard = _write_guard()
    if guard:
        return guard

    data = request.get_json() or {}
    from_thr, payload, err_resp = _require_signed_intent(data, 'physical_asset_produce')
    if err_resp:
        return err_resp

    signature_data = payload.get('signature_data') or {}
    if not signature_data:
        return jsonify(ok=False, error='signature_data_required'), 400

    ok, result = _pa_service.sign_production(
        job_id=job_id,
        creator_address=from_thr,
        signature_data=signature_data,
    )

    if not ok:
        status = 404 if result.get('error') in ('job_not_found', 'asset_not_found') else 400
        return jsonify(ok=False, **result), status
    return jsonify(ok=True, **result), 200


@physical_assets_bp.route('/jobs/<job_id>/certify', methods=['POST'])
def certify_job(job_id):
    guard = _write_guard()
    if guard:
        return guard

    data = request.get_json() or {}
    from_thr, payload, err_resp = _require_signed_intent(data, 'physical_asset_produce')
    if err_resp:
        return err_resp

    ok, result = _pa_service.certify_production(
        job_id=job_id,
        creator_address=from_thr,
    )

    if not ok:
        status = 404 if result.get('error') in ('job_not_found', 'asset_not_found') else 400
        return jsonify(ok=False, **result), status
    return jsonify(ok=True, **result), 200
