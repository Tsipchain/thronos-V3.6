"""
server_ext.py — thin wrapper over server.py
Registers additional blueprints without touching the 1.2MB monolith.
Gunicorn entry point: server_ext:app
"""
from server import app  # noqa: F401  — imports the Flask app + all routes

# Wallet V1 — ECDSA/secp256k1 transaction signing
try:
    from wallet_v1_blueprint import register_wallet_v1_routes

    # Try to get Redis client and SQLite path from server.py's globals
    # If not available, wallet init will fail gracefully
    import server as server_module
    redis_client = (
        getattr(server_module, 'REDIS_CLIENT', None)
        or getattr(server_module, 'redis_client', None)
    )
    node_role = getattr(server_module, 'NODE_ROLE', 'master')
    read_only = getattr(server_module, 'READ_ONLY', False)
    sqlite_path = (
        getattr(server_module, 'MASTER_SQLITE_PATH', None)
        or getattr(server_module, 'LEDGER_DB_FILE', None)
    )

    register_wallet_v1_routes(
        app,
        redis_client=redis_client,
        node_role=node_role,
        read_only=read_only,
        sqlite_path=sqlite_path
    )
    app.logger.info("[WalletV1] routes registered")
except Exception as exc:  # pragma: no cover
    app.logger.warning("[WalletV1] routes NOT loaded: %s", exc)

# L2E EDU Bridge — receives attendance events from thronos-edupresence
try:
    from services.l2e_edu import l2e_edu_bp
    app.register_blueprint(l2e_edu_bp)
    app.logger.info("[L2E-EDU] Blueprint registered at /api/l2e/edu")
except Exception as exc:  # pragma: no cover
    app.logger.warning("[L2E-EDU] Blueprint NOT loaded: %s", exc)

# ── Pledge-based v0 wallet migration ──────────────────────────────────────────
# Lets pledge/HMAC users find their old THR address via send_secret only,
# then migrate to a V1 wallet and set up PIN + passkey.
import hashlib as _hashlib
from flask import jsonify as _jsonify, request as _request

import server as _srv

@app.route('/api/wallet/v1/pledge-lookup', methods=['POST'])
def pledge_wallet_lookup():
    """
    Find a pledge record by send_secret (the HMAC token the user received when pledging).
    SHA256(send_secret) is matched against stored send_seed_hash / send_auth_hash.
    Also tries double-SHA256 for v0 wallets that used SHA256d derivation.

    Input:  { "send_secret": "..." }
    Output: { "ok": true, "thr_address": "THR...", "btc_address": "3...", "pledge_hash": "..." }
    """
    try:
        data = _request.get_json() or {}
        send_secret = (data.get('send_secret') or '').strip()
        if not send_secret:
            return _jsonify(ok=False, error='send_secret_required'), 400

        # Compute SHA256 and SHA256d of the secret
        h1 = _hashlib.sha256(send_secret.encode()).hexdigest()          # standard
        h2 = _hashlib.sha256(h1.encode()).hexdigest()                   # SHA256d (v0 wallets)
        h3 = _hashlib.sha256(f'{send_secret}:auth'.encode()).hexdigest()  # pledge_submit variant

        load_json = getattr(_srv, 'load_json', None)
        pledge_chain_path = getattr(_srv, 'PLEDGE_CHAIN', None)
        if not callable(load_json) or not pledge_chain_path:
            return _jsonify(ok=False, error='pledge_system_unavailable'), 503

        pledges = load_json(pledge_chain_path, []) or []
        match = None
        for p in pledges:
            stored = (p.get('send_seed_hash') or p.get('send_auth_hash') or '').lower()
            if stored and stored in (h1, h2, h3):
                match = p
                break

        if not match:
            return _jsonify(ok=False, error='pledge_not_found'), 404

        return _jsonify(
            ok=True,
            thr_address=match.get('thr_address', ''),
            btc_address=match.get('btc_address', ''),
            pledge_hash=match.get('pledge_hash', ''),
        ), 200

    except Exception as exc:
        app.logger.error('[PledgeLookup] %s', exc)
        return _jsonify(ok=False, error='internal_error'), 500


@app.route('/api/wallet/v1/pledge-migrate', methods=['POST'])
def pledge_wallet_migrate():
    """
    Full pledge→V1 migration:
    1. Verify send_secret ownership
    2. Generate secp256k1 keypair server-side (pure Python — no external deps)
    3. Derive canonical V1 address from compressed pubkey
    4. Call migrate_legacy_address
    5. Encrypt private key with PIN (PBKDF2-SHA256-250k + AES-256-GCM) → Recovery Kit
    6. Generate PDF with LSB-embedded send_seed
    7. Return { canonical_v1_address, recovery_kit (JSON string), pdf_url }

    Input:  { "send_secret": "...", "pin": "1234" }
    Output: { "ok": true, "canonical_v1_address": "THR...",
              "recovery_kit": "{...}", "pdf_url": "/contracts/...", "legacy_address": "THR..." }
    """
    try:
        data = _request.get_json() or {}
        send_secret = (data.get('send_secret') or '').strip()
        pin = (data.get('pin') or '').strip()

        if not send_secret:
            return _jsonify(ok=False, error='send_secret_required'), 400
        if not pin or len(pin) < 4:
            return _jsonify(ok=False, error='pin_required_min_4_digits'), 400

        # ── Find pledge record ────────────────────────────────────────────────
        h1 = _hashlib.sha256(send_secret.encode()).hexdigest()
        h2 = _hashlib.sha256(h1.encode()).hexdigest()
        h3 = _hashlib.sha256(f'{send_secret}:auth'.encode()).hexdigest()

        load_json = getattr(_srv, 'load_json', None)
        pledge_chain_path = getattr(_srv, 'PLEDGE_CHAIN', None)
        if not callable(load_json) or not pledge_chain_path:
            return _jsonify(ok=False, error='pledge_system_unavailable'), 503

        pledges = load_json(pledge_chain_path, []) or []
        match = None
        for p in pledges:
            stored = (p.get('send_seed_hash') or p.get('send_auth_hash') or '').lower()
            if stored and stored in (h1, h2, h3):
                match = p
                break

        if not match:
            return _jsonify(ok=False, error='pledge_not_found'), 404

        old_address = match.get('thr_address', '')
        if not old_address:
            return _jsonify(ok=False, error='pledge_missing_address'), 500

        # ── Already migrated? Return existing canonical ───────────────────────
        try:
            from wallet_v1_migration import search_all_migration_sources
            existing = search_all_migration_sources(legacy_address=old_address)
            if existing and existing.get('canonical_v1_address'):
                return _jsonify(
                    ok=True,
                    canonical_v1_address=existing['canonical_v1_address'],
                    legacy_address=old_address,
                    already_migrated=True,
                    recovery_kit=None,
                    pdf_url=None,
                ), 200
        except ImportError:
            pass

        # ── Generate secp256k1 keypair (pure Python, no external deps) ────────
        import os as _os2, json as _json2, struct as _struct2
        _P  = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
        _N  = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
        _Gx = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
        _Gy = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8

        def _pt_add(P1, P2):
            if P1 is None: return P2
            if P2 is None: return P1
            x1,y1=P1; x2,y2=P2
            if x1==x2:
                if y1!=y2: return None
                m=(3*x1*x1*pow(2*y1,_P-2,_P))%_P
            else:
                m=((y2-y1)*pow(x2-x1,_P-2,_P))%_P
            x3=(m*m-x1-x2)%_P; y3=(m*(x1-x3)-y1)%_P
            return x3,y3

        def _pt_mul(k, G):
            R=None; A=G
            while k:
                if k&1: R=_pt_add(R,A)
                A=_pt_add(A,A); k>>=1
            return R

        priv_int = int.from_bytes(_os2.urandom(32), 'big') % (_N - 1) + 1
        priv_hex = priv_int.to_bytes(32, 'big').hex()
        x, y = _pt_mul(priv_int, (_Gx, _Gy))
        compressed_pub = ('02' if y%2==0 else '03') + hex(x)[2:].zfill(64)

        # ── Derive V1 address ─────────────────────────────────────────────────
        from wallet_v1_address_derivation import derive_thronos_address
        canonical = derive_thronos_address(compressed_pub)

        # ── Execute migration ─────────────────────────────────────────────────
        try:
            from wallet_v1_migration import migrate_legacy_address
            migrate_legacy_address(
                old_address=old_address,
                legacy_secret=send_secret,
                new_compressed_public_key=compressed_pub,
            )
        except ValueError as ve:
            if 'already_migrated' in str(ve):
                pass  # Race condition — still generate Recovery Kit below
            else:
                raise

        # ── Encrypt private key with PIN (PBKDF2-SHA256-250k + AES-GCM) ──────
        # Matches JS encryptBlob() in app.js / wallet_session.js exactly.
        recovery_kit_str = None
        try:
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            from cryptography.hazmat.primitives import hashes
            import base64 as _b64

            _salt = _os2.urandom(16)
            _iv   = _os2.urandom(12)
            kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=_salt, iterations=250000)
            key = kdf.derive(pin.encode())
            ct = AESGCM(key).encrypt(_iv, bytes.fromhex(priv_hex), None)

            enc_blob = _json2.dumps({
                'v': 1, 'alg': 'aes256gcm', 'kdf': 'pbkdf2-sha256-250k',
                'salt': _salt.hex(), 'iv': _iv.hex(), 'ct': ct.hex()
            })
            recovery_kit_str = _json2.dumps({
                'canonical_v1_address': canonical,
                'address': canonical,
                'legacy_address': old_address,
                'encrypted_private_key_backup': enc_blob,
                'wallet_v1_encrypted_priv': enc_blob,
                'migration_source': 'pledge_hmac_v0',
                'created_at': _import_datetime().utcnow().isoformat() + 'Z',
                'version': 2,
            }, indent=2)
        except Exception as enc_err:
            app.logger.warning('[PledgeMigrate] Recovery Kit encryption unavailable: %s', enc_err)

        # ── Generate PDF with LSB-embedded send_seed ──────────────────────────
        pdf_url = None
        try:
            from secure_pledge_embed import create_secure_pdf_contract
            contracts_dir = getattr(_srv, 'CONTRACTS_DIR', '/tmp/contracts')
            chain_file = getattr(_srv, 'CHAIN_FILE', None)
            load_json2 = getattr(_srv, 'load_json', None)
            height = len(load_json2(chain_file, [])) if load_json2 and chain_file else 0

            pdf_fn = create_secure_pdf_contract(
                btc_address=match.get('btc_address', ''),
                pledge_text=match.get('pledge_text', ''),
                thr_address=canonical,
                pledge_hash=match.get('pledge_hash', ''),
                height=height,
                send_seed=send_secret,
                output_dir=contracts_dir,
                passphrase=pin,
            )
            if pdf_fn:
                pdf_url = f'/contracts/{pdf_fn}'
        except Exception as pdf_err:
            app.logger.warning('[PledgeMigrate] PDF generation failed: %s', pdf_err)

        return _jsonify(
            ok=True,
            canonical_v1_address=canonical,
            legacy_address=old_address,
            already_migrated=False,
            recovery_kit=recovery_kit_str,
            pdf_url=pdf_url,
        ), 200

    except Exception as exc:
        app.logger.error('[PledgeMigrate] %s', exc, exc_info=True)
        return _jsonify(ok=False, error='internal_error', detail=str(exc)), 500


@app.route('/api/wallet/v1/migration-status', methods=['GET'])
def wallet_migration_status():
    """
    Check migration status for an address (diagnostic).
    Works with both old and new address.
    GET /api/wallet/v1/migration-status?address=THR...
    Returns: { ok, old_address, new_address, balances, source }
    """
    address = (_request.args.get('address') or '').strip().upper()
    if not address or not address.startswith('THR'):
        return _jsonify(ok=False, error='address_required'), 400
    try:
        from wallet_v1_migration import resolve_migration
        result = resolve_migration(address)
        # Also fetch current balances for both addresses
        load_json = getattr(_srv, 'load_json', None)
        ledger_path = getattr(_srv, 'LEDGER_FILE', None) or getattr(_srv, 'LEDGER_JSON', None)
        old_bal = new_bal = None
        if load_json and ledger_path:
            try:
                ledger = load_json(ledger_path, {})
                old_addr = (result or {}).get('legacy_address', address)
                new_addr = (result or {}).get('canonical_v1_address', address)
                old_bal = ledger.get(old_addr, {})
                new_bal = ledger.get(new_addr, {})
            except Exception:
                pass
        return _jsonify(
            ok=True,
            address_queried=address,
            migration=result,
            old_address_balance=old_bal,
            new_address_balance=new_bal,
        ), 200
    except ImportError:
        return _jsonify(ok=False, error='migration_module_unavailable'), 503
    except Exception as exc:
        return _jsonify(ok=False, error=str(exc)), 500


def _import_datetime():
    from datetime import datetime
    return datetime


# ── Universal wallet action intent verification ─────────────────────────────────

import json as _json_wa
import time as _time_wa

_WALLET_ACTION_ALLOWED_ACTIONS = frozenset({
    'internal_transfer', 'external_send_record',
    'pool_deposit_intent', 'pool_withdraw_intent',
    'swap', 'bridge', 'pledge', 'token_create',
    'nft_mint', 'nft_buy',
})

_WALLET_ACTION_NONCES_FILE_CACHED = None


def _get_action_nonces_file():
    global _WALLET_ACTION_NONCES_FILE_CACHED
    if _WALLET_ACTION_NONCES_FILE_CACHED is None:
        import os as _os_wa
        data_dir = getattr(_srv, 'DATA_DIR', '/tmp/thronos_data')
        _WALLET_ACTION_NONCES_FILE_CACHED = _os_wa.path.join(data_dir, 'wallet_action_nonces.json')
    return _WALLET_ACTION_NONCES_FILE_CACHED


def _canonical_wallet_action_intent(intent: dict) -> str:
    """Deterministic canonical JSON for intent signing — all values str, keys alphabetical.

    Must match the JS _canonicalWalletActionIntentMsg() in wallet_session.js exactly.
    """
    fields = ('action', 'amount', 'asset', 'chain', 'created_at', 'from_thr',
              'nonce', 'payload_hash', 'recipient', 'type', 'version', 'wallet_id')
    parts = [f'"{k}":{_json_wa.dumps(str(intent.get(k, "")))}' for k in fields]
    return '{' + ','.join(parts) + '}'


def _verify_action_payload_hash(expected_hash: str, payload: dict) -> bool:
    """Verify SHA-256 of canonical payload JSON equals the hash committed inside the intent."""
    canonical = _json_wa.dumps(payload, sort_keys=True, separators=(',', ':'))
    actual = _hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    return actual == expected_hash


def _verify_wallet_action_intent(intent: dict, signature_hex: str, public_key_hex: str) -> tuple:
    """Verify a signed universal wallet action intent.

    Returns (ok: bool, error_code: str, error_detail: str).

    Check order:
      1. Required fields present and non-empty.
      2. type == 'thronos_wallet_action'.
      3. version == '1'.
      4. action is in allowed set.
      5. created_at (unix timestamp) within 5-minute window.
      6. Nonce not previously seen.
      7. Signature valid over canonical intent (SHA-256 + ECDSA secp256k1 DER).
      8. public_key maps to from_thr address.
      9. Consume nonce (only after all checks pass).
    """
    # 1. Required fields
    required = ('type', 'version', 'action', 'wallet_id', 'from_thr',
                'nonce', 'created_at', 'payload_hash')
    for field in required:
        if not intent.get(field):
            return False, 'missing_field', f'missing field: {field}'

    # 2. Type
    if intent.get('type') != 'thronos_wallet_action':
        return False, 'invalid_type', f'expected thronos_wallet_action, got {intent.get("type")!r}'

    # 3. Version
    if str(intent.get('version', '')) != '1':
        return False, 'invalid_version', f'expected version 1, got {intent.get("version")!r}'

    # 4. Action allowed
    action = str(intent.get('action', ''))
    if action not in _WALLET_ACTION_ALLOWED_ACTIONS:
        return False, 'invalid_action', f'action {action!r} not permitted'

    # 5. Age check — created_at is a unix epoch integer (seconds)
    try:
        created_ts = int(str(intent.get('created_at', '0')))
        age = _time_wa.time() - created_ts
        if age < -30 or age > 300:
            return False, 'intent_expired', f'intent age {int(age)}s exceeds 5-minute window'
    except (ValueError, TypeError) as exc:
        return False, 'invalid_created_at', f'cannot parse created_at: {exc}'

    # 6. Nonce replay check
    nonce = str(intent['nonce'])
    from_thr = str(intent['from_thr']).upper()
    load_json = getattr(_srv, 'load_json', None)
    save_json = getattr(_srv, 'save_json', None)
    if not callable(load_json) or not callable(save_json):
        return False, 'system_error', 'state helpers unavailable'

    nonces_file = _get_action_nonces_file()
    nonces_store = load_json(nonces_file, {})
    wallet_nonces = nonces_store.get(from_thr, [])
    if nonce in wallet_nonces:
        return False, 'nonce_reused', 'intent nonce has already been consumed'

    # 7. Signature verification (SHA-256 over canonical intent + secp256k1 ECDSA DER)
    canonical_msg = _canonical_wallet_action_intent(intent).encode('utf-8')
    try:
        from cryptography.hazmat.primitives import hashes as _hashes_wa
        from cryptography.hazmat.primitives.asymmetric import ec as _ec_wa
        from cryptography.exceptions import InvalidSignature as _InvalidSig
        pub_bytes = bytes.fromhex(public_key_hex)
        sig_bytes = bytes.fromhex(signature_hex)
        pub_obj = _ec_wa.EllipticCurvePublicKey.from_encoded_point(_ec_wa.SECP256K1(), pub_bytes)
        pub_obj.verify(sig_bytes, canonical_msg, _ec_wa.ECDSA(_hashes_wa.SHA256()))
    except _InvalidSig:
        return False, 'invalid_signature', 'signature does not match intent'
    except Exception as exc:
        return False, 'invalid_signature', f'signature verification failed: {exc}'

    # 8. Key-address binding
    try:
        import wallet_v1_production_final as _wv1pf_wa
        binding_ok, binding_error = _wv1pf_wa.verify_publickey_matches_address(
            {'from': from_thr, 'publicKey': public_key_hex}
        )
        if not binding_ok:
            return False, 'key_address_mismatch', binding_error
    except Exception as exc:
        return False, 'key_address_mismatch', f'address binding failed: {exc}'

    # 9. Consume nonce — written only after all checks pass
    wallet_nonces.append(nonce)
    if len(wallet_nonces) > 500:
        wallet_nonces = wallet_nonces[-500:]
    nonces_store[from_thr] = wallet_nonces
    save_json(nonces_file, nonces_store)

    return True, '', ''


# ── WalletConnect lightweight relay ────────────────────────────────────────────
# Stores pending sign requests in-memory (Redis if available, else dict).
# ThronosBuilder POSTs requests here; PWA polls and approves with Face ID.
import threading as _threading
from urllib.parse import quote as _quote
_wc_store_lock = _threading.Lock()
_wc_store: dict = {}  # { address: [ {id, action, payload, dapp, ts} ] }
_wc_sessions: dict = {}  # { session_id: address }
_wc_pairing_sessions: dict = {}  # { session_id: { status, address, dapp, created_at, paired_at } }
_wc_approval_results: dict = {}  # { request_id: { approved, signature, address, rejected, ts } }


def _wc_store_for(address: str) -> list:
    with _wc_store_lock:
        return list(_wc_store.get(address.upper(), []))


def _wc_add_request(address: str, req: dict):
    address = address.upper()
    with _wc_store_lock:
        _wc_store.setdefault(address, [])
        _wc_store[address].append(req)


def _wc_remove_request(address: str, request_id: str):
    address = address.upper()
    with _wc_store_lock:
        _wc_store[address] = [r for r in _wc_store.get(address, []) if r.get('id') != request_id]


@app.route('/api/wallet/wc/pair', methods=['POST'])
def wc_pair():
    """Register a WalletConnect pairing from the PWA — returns a session_id for polling."""
    import uuid as _uuid
    data = _request.get_json() or {}
    address = (data.get('address') or '').strip().upper()
    if not address:
        return _jsonify(ok=False, error='address_required'), 400
    session_id = str(_uuid.uuid4())
    with _wc_store_lock:
        _wc_sessions[session_id] = address
        session_id_from_uri = (data.get('session_id') or '').strip()
        if session_id_from_uri and session_id_from_uri in _wc_pairing_sessions:
            import time as _time
            _wc_pairing_sessions[session_id_from_uri].update({
                'status': 'connected',
                'address': address,
                'paired_at': _time.time(),
            })
    app.logger.info('[WC] Paired address=%s session=%s', address[:10], session_id[:8])
    return _jsonify(ok=True, session_id=session_id, address=address), 200


@app.route('/api/wallet/wc/request', methods=['POST'])
def wc_post_request():
    """
    ThronosBuilder (or any dApp) posts a sign request for a connected address.
    Input: { "address": "THR...", "action": "sign_tx", "payload": {...}, "dapp": "ThronosBuilder" }
    """
    import uuid as _uuid, time as _time
    data = _request.get_json() or {}
    address = (data.get('address') or '').strip().upper()
    if not address:
        return _jsonify(ok=False, error='address_required'), 400
    req = {
        'id': str(_uuid.uuid4()),
        'action': data.get('action', 'sign'),
        'payload': data.get('payload', {}),
        'payload_preview': str(data.get('payload', {}))[:200],
        'dapp': data.get('dapp', 'Unknown dApp'),
        'ts': _time.time(),
    }
    _wc_add_request(address, req)
    app.logger.info('[WC] Request queued id=%s for address=%s', req['id'][:8], address[:10])
    return _jsonify(ok=True, request_id=req['id']), 200


@app.route('/api/wallet/wc/requests', methods=['GET'])
def wc_get_requests():
    """PWA polls this to get pending sign requests for its address."""
    address = (_request.args.get('address') or '').strip().upper()
    if not address:
        return _jsonify(ok=False, error='address_required'), 400
    requests = _wc_store_for(address)
    return _jsonify(ok=True, requests=requests, count=len(requests)), 200


@app.route('/api/wallet/wc/approve', methods=['POST'])
def wc_approve():
    """
    PWA approves a pending request (after Face ID / PIN).
    Signs the payload with the session key if provided, else just records approval.
    Input: { "request_id": "...", "address": "THR...", "session_key": "hex" }
    """
    import time as _time
    data = _request.get_json() or {}
    address = (data.get('address') or '').strip().upper()
    request_id = (data.get('request_id') or '').strip()
    session_key = (data.get('session_key') or '').strip()

    if not address or not request_id:
        return _jsonify(ok=False, error='address_and_request_id_required'), 400

    # Find the request
    pending = _wc_store_for(address)
    req = next((r for r in pending if r.get('id') == request_id), None)
    if not req:
        return _jsonify(ok=False, error='request_not_found'), 404

    # Sign the payload if session key is provided
    signature = None
    if session_key:
        try:
            import hmac as _hmac
            sig_input = _hashlib.sha256(
                (session_key + ':' + str(req.get('payload', ''))).encode()
            ).hexdigest()
            signature = sig_input
        except Exception:
            pass

    _wc_remove_request(address, request_id)

    with _wc_store_lock:
        _wc_approval_results[request_id] = {
            'status': 'approved',
            'approved': True,
            'signature': signature,
            'address': address,
            'ts': _time.time(),
        }

    app.logger.info('[WC] Approved request_id=%s address=%s', request_id[:8], address[:10])
    return _jsonify(
        ok=True,
        request_id=request_id,
        address=address,
        signature=signature,
        approved_at=_time.time(),
    ), 200


@app.route('/api/wallet/wc/reject', methods=['POST'])
def wc_reject():
    """PWA rejects a pending request."""
    data = _request.get_json() or {}
    address = (data.get('address') or '').strip().upper()
    request_id = (data.get('request_id') or '').strip()
    if address and request_id:
        _wc_remove_request(address, request_id)
    import time as _time
    if address and request_id:
        with _wc_store_lock:
            _wc_approval_results[request_id] = {
                'status': 'rejected',
                'approved': False,
                'address': address,
                'ts': _time.time(),
            }
    return _jsonify(ok=True), 200


@app.route('/api/wallet/wc/session/create', methods=['POST'])
def wc_session_create():
    """
    ThronosBuilder calls this to start a pairing session.
    Returns a thrconnect:// URI + QR-ready URL.
    """
    import uuid as _uuid, time as _time
    data = _request.get_json() or {}
    dapp = str(data.get('dapp') or 'ThronosBuilder')[:64]
    session_id = str(_uuid.uuid4())
    relay_base = _request.host_url.rstrip('/')
    # thrconnect://SESSION_ID?relay=URL&dapp=NAME
    uri = f"thrconnect://{session_id}?relay={relay_base}&dapp={dapp}"
    with _wc_store_lock:
        _wc_pairing_sessions[session_id] = {
            'status': 'waiting',
            'address': None,
            'dapp': dapp,
            'created_at': _time.time(),
            'paired_at': None,
        }
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?data={_quote(uri)}&size=220x220&color=ffffff&bgcolor=0d0a1a&margin=8"
    app.logger.info('[WC] Session created id=%s dapp=%s', session_id[:8], dapp)
    return _jsonify(ok=True, session_id=session_id, uri=uri, qr_url=qr_url), 200


@app.route('/api/wallet/wc/session/<session_id>', methods=['GET'])
def wc_session_poll(session_id):
    """Builder polls this to check if mobile wallet has connected."""
    with _wc_store_lock:
        session = dict(_wc_pairing_sessions.get(session_id) or {})
    if not session:
        return _jsonify(ok=False, error='session_not_found'), 404
    return _jsonify(ok=True, **session), 200


@app.route('/api/wallet/wc/result/<request_id>', methods=['GET'])
def wc_get_result(request_id):
    """Builder polls this for mobile approval/rejection of a sign request."""
    with _wc_store_lock:
        result = dict(_wc_approval_results.get(request_id) or {})
    if not result:
        return _jsonify(ok=True, status='pending'), 200
    return _jsonify(ok=True, **result), 200


@app.route('/api/wallet/v1/transfer', methods=['POST'])
def wallet_v1_transfer():
    """
    PWA send — primary path requires signed action intent; legacy private_key_hex is fallback.

    Signed path (preferred):
      intent      – signed action intent object
      signature   – DER hex secp256k1 signature over SHA-256(canonical_intent)
      public_key  – compressed secp256k1 public key hex (33 bytes)
      payload     – { to, token, amount } (hash committed in intent.payload_hash)

    Legacy path (deprecated — logs warning):
      from, to, amount, token, private_key_hex
    """
    data = _request.get_json() or {}
    intent_raw = data.get('intent')
    signature  = (data.get('signature')  or '').strip()
    public_key = (data.get('public_key') or '').strip()
    use_signed = bool(intent_raw and signature and public_key)

    if use_signed:
        intent = intent_raw if isinstance(intent_raw, dict) else {}
        ok, err_code, err_detail = _verify_wallet_action_intent(intent, signature, public_key)
        if not ok:
            return _jsonify(ok=False, error=err_code, detail=err_detail), 400
        payload = data.get('payload') or {}
        if not _verify_action_payload_hash(intent.get('payload_hash', ''), payload):
            return _jsonify(ok=False, error='payload_hash_mismatch',
                            detail='payload does not match signed intent'), 400
        from_addr  = str(intent.get('from_thr', '')).strip().upper()
        to_addr    = str(payload.get('to') or intent.get('recipient') or '').strip()
        amount_raw = payload.get('amount') or intent.get('amount') or 0
        token      = str(payload.get('token') or intent.get('asset') or 'THR').upper()
    else:
        priv_hex   = (data.get('private_key_hex') or '').strip()
        from_addr  = (data.get('from')            or '').strip().upper()
        to_addr    = (data.get('to')              or '').strip()
        amount_raw = data.get('amount', 0)
        token      = (data.get('token')           or 'THR').upper()
        if not from_addr or not to_addr or not priv_hex:
            return _jsonify(ok=False, error='missing_required_fields'), 400
        try:
            from cryptography.hazmat.primitives.asymmetric import ec as _ec
            from cryptography.hazmat.primitives.serialization import Encoding as _Enc, PublicFormat as _PF
            from cryptography.hazmat.backends import default_backend as _backend
            from wallet_v1_address_derivation import derive_thronos_address as _derive
            _priv_key = _ec.derive_private_key(int(priv_hex, 16), _ec.SECP256K1(), _backend())
            _pub_bytes = _priv_key.public_key().public_bytes(_Enc.X962, _PF.CompressedPoint)
            if _derive(_pub_bytes.hex()).upper() != from_addr.upper():
                return _jsonify(ok=False, error='address_mismatch'), 403
        except Exception as _e:
            return _jsonify(ok=False, error='invalid_private_key', detail=str(_e)), 400
        app.logger.warning('[V1Transfer] private_key_hex auth deprecated — upgrade to signed intent')

    if not from_addr or not to_addr:
        return _jsonify(ok=False, error='missing_required_fields'), 400

    # ── Execute transfer via adapter ───────────────────────────────────────────
    try:
        import wallet_v1_execution_adapter as _adapter
        signed_tx = {'from': from_addr, 'to': to_addr, 'amount': amount_raw, 'speed': 'fast', 'nonce': None}
        if token == 'THR':
            _ok, result, status_code = _adapter.execute_verified_signed_transfer(signed_tx)
        else:
            _ok, result, status_code = _adapter.execute_verified_signed_token_transfer(token, signed_tx)
        return _jsonify(**result), status_code
    except Exception as _e:
        app.logger.error('[V1Transfer] transfer_error: %s', _e)
        return _jsonify(ok=False, error='transfer_failed', detail=str(_e)), 500


@app.route('/api/wallet/v1/swap', methods=['POST'])
def wallet_v1_swap():
    """
    PWA swap — primary path requires signed action intent; legacy private_key_hex is fallback.

    Signed path (preferred):
      intent      – action='swap', asset=token_in, amount=amount_in, recipient=token_out
      signature, public_key
      payload     – { token_in, token_out, amount_in, min_amount_out }

    Legacy path (deprecated):
      from, token_in, token_out, amount_in, min_amount_out, private_key_hex
    """
    import server as _srv
    import secrets as _secrets_mod
    import time as _time_mod

    data = _request.get_json() or {}
    intent_raw = data.get('intent')
    signature  = (data.get('signature')  or '').strip()
    public_key = (data.get('public_key') or '').strip()
    use_signed = bool(intent_raw and signature and public_key)

    if use_signed:
        intent = intent_raw if isinstance(intent_raw, dict) else {}
        ok, err_code, err_detail = _verify_wallet_action_intent(intent, signature, public_key)
        if not ok:
            return _jsonify(ok=False, error=err_code, detail=err_detail), 400
        payload = data.get('payload') or {}
        if not _verify_action_payload_hash(intent.get('payload_hash', ''), payload):
            return _jsonify(ok=False, error='payload_hash_mismatch',
                            detail='payload does not match signed intent'), 400
        from_addr      = str(intent.get('from_thr', '')).strip().upper()
        token_in_raw   = str(payload.get('token_in') or intent.get('asset') or '').strip()
        token_out_raw  = str(payload.get('token_out') or intent.get('recipient') or '').strip()
        amount_in_raw  = payload.get('amount_in') or intent.get('amount') or 0
        min_amount_out = float(payload.get('min_amount_out', 0) or 0)
    else:
        priv_hex       = (data.get('private_key_hex') or '').strip()
        from_addr      = (data.get('from')            or '').strip().upper()
        token_in_raw   = (data.get('token_in')        or '').strip()
        token_out_raw  = (data.get('token_out')       or '').strip()
        amount_in_raw  = data.get('amount_in', 0)
        min_amount_out = float(data.get('min_amount_out', 0) or 0)
        if not from_addr or not token_in_raw or not token_out_raw or not priv_hex:
            return _jsonify(ok=False, error='missing_required_fields'), 400
        try:
            from cryptography.hazmat.primitives.asymmetric import ec as _ec
            from cryptography.hazmat.primitives.serialization import Encoding as _Enc, PublicFormat as _PF
            from cryptography.hazmat.backends import default_backend as _backend
            from wallet_v1_address_derivation import derive_thronos_address as _derive
            _priv_key = _ec.derive_private_key(int(priv_hex, 16), _ec.SECP256K1(), _backend())
            _pub_bytes = _priv_key.public_key().public_bytes(_Enc.X962, _PF.CompressedPoint)
            if _derive(_pub_bytes.hex()).upper() != from_addr.upper():
                return _jsonify(ok=False, error='address_mismatch'), 403
        except Exception as _e:
            return _jsonify(ok=False, error='invalid_private_key', detail=str(_e)), 400
        app.logger.warning('[V1Swap] private_key_hex auth deprecated — upgrade to signed intent')

    if not from_addr or not token_in_raw or not token_out_raw:
        return _jsonify(ok=False, error='missing_required_fields'), 400

    try:
        amount_in = float(amount_in_raw)
        if amount_in <= 0:
            raise ValueError('non_positive')
    except (TypeError, ValueError):
        return _jsonify(ok=False, error='invalid_amount'), 400

    trader = from_addr.upper()

    # ── Sanitize token symbols ────────────────────────────────────────────────
    try:
        token_in  = _srv._sanitize_asset_symbol(token_in_raw)
        token_out = _srv._sanitize_asset_symbol(token_out_raw)
    except Exception as _e:
        return _jsonify(ok=False, error='invalid_token_symbol', detail=str(_e)), 400

    if token_in == token_out:
        return _jsonify(ok=False, error='same_token'), 400

    # ── Get quote / route ─────────────────────────────────────────────────────
    try:
        quote, err = _srv.quote_swap_route(token_in, token_out, amount_in)
    except Exception as _e:
        app.logger.error('[V1Swap] quote_error: %s', _e)
        return _jsonify(ok=False, error='quote_failed', detail=str(_e)), 500

    if err or not quote:
        return _jsonify(ok=False, error=err or 'no_route_found'), 400

    # ── Load ledgers / balances / pools ──────────────────────────────────────
    try:
        thr_ledger     = _srv.load_json(_srv.LEDGER_FILE, {})
        wbtc_ledger    = _srv.load_json(_srv.WBTC_LEDGER_FILE, {})
        token_balances = _srv.load_token_balances()
        pools          = _srv.load_pools()
    except Exception as _e:
        app.logger.error('[V1Swap] load_error: %s', _e)
        return _jsonify(ok=False, error='state_load_failed', detail=str(_e)), 500

    def get_balance(sym):
        if sym == 'THR':  return float(thr_ledger.get(trader, 0.0))
        if sym == 'WBTC': return float(wbtc_ledger.get(trader, 0.0))
        return float(token_balances.get(sym, {}).get(trader, 0.0))

    if get_balance(token_in) < amount_in:
        return _jsonify(ok=False, error='insufficient_balance',
                        balance=get_balance(token_in), required=amount_in), 400

    def deduct(sym, amt):
        if sym == 'THR':
            thr_ledger[trader] = round(float(thr_ledger.get(trader, 0.0)) - amt, 8)
        elif sym == 'WBTC':
            wbtc_ledger[trader] = round(float(wbtc_ledger.get(trader, 0.0)) - amt, 8)
        else:
            bucket = token_balances.setdefault(sym, {})
            bucket[trader] = round(float(bucket.get(trader, 0.0)) - amt, 8)

    def credit(sym, amt):
        if sym == 'THR':
            thr_ledger[trader] = round(float(thr_ledger.get(trader, 0.0)) + amt, 8)
        elif sym == 'WBTC':
            wbtc_ledger[trader] = round(float(wbtc_ledger.get(trader, 0.0)) + amt, 8)
        else:
            bucket = token_balances.setdefault(sym, {})
            bucket[trader] = round(float(bucket.get(trader, 0.0)) + amt, 8)

    # ── Execute swap legs ─────────────────────────────────────────────────────
    swap_trace        = []
    running_in        = amount_in
    total_fee         = 0.0
    total_price_impact = 0.0

    try:
        for leg in quote.get('legs', []):
            leg_token_in  = leg['token_in']
            leg_token_out = leg['token_out']
            pool = next((p for p in pools if p.get('id') == leg['pool_id']), None)
            if pool is None:
                return _jsonify(ok=False, error='pool_not_found', pool_id=leg.get('pool_id')), 400

            a = _srv._sanitize_asset_symbol(pool.get('token_a', ''))
            b = _srv._sanitize_asset_symbol(pool.get('token_b', ''))
            reserves_a = float(pool.get('reserves_a', 0))
            reserves_b = float(pool.get('reserves_b', 0))
            fee_bps    = _srv.pool_fee_bps(pool)

            if leg_token_in == a and leg_token_out == b:
                reserve_in, reserve_out = reserves_a, reserves_b
                is_a_to_b = True
            else:
                reserve_in, reserve_out = reserves_b, reserves_a
                is_a_to_b = False

            out_amount, fee_amount, price_impact = _srv.compute_swap_out(
                running_in, reserve_in, reserve_out, fee_bps)

            if out_amount <= 0:
                return _jsonify(ok=False, error='zero_output_amount',
                                leg=leg.get('pool_id')), 400

            if is_a_to_b:
                pool['reserves_a'] = round(reserves_a + running_in, 6)
                pool['reserves_b'] = round(reserves_b - out_amount, 6)
            else:
                pool['reserves_b'] = round(reserves_b + running_in, 6)
                pool['reserves_a'] = round(reserves_a - out_amount, 6)

            pool['volume_24h']      = float(pool.get('volume_24h',      0.0)) + running_in
            pool['fees_collected']  = float(pool.get('fees_collected',  0.0)) + fee_amount

            swap_trace.append({
                'pool_id':    leg['pool_id'],
                'in_token':   leg_token_in,
                'in_amount':  running_in,
                'out_token':  leg_token_out,
                'out_amount': out_amount,
                'fee':        fee_amount,
            })
            total_fee          += fee_amount
            total_price_impact += price_impact
            running_in          = out_amount
    except Exception as _e:
        app.logger.error('[V1Swap] execution_error: %s', _e)
        return _jsonify(ok=False, error='swap_execution_failed', detail=str(_e)), 500

    amount_out = running_in

    # ── Slippage check ────────────────────────────────────────────────────────
    if min_amount_out > 0 and amount_out < min_amount_out:
        return _jsonify(ok=False, error='slippage_exceeded',
                        amount_out=amount_out, min_amount_out=min_amount_out), 400

    # ── Apply balance changes ─────────────────────────────────────────────────
    try:
        deduct(token_in, amount_in)
        credit(token_out, amount_out)
        _srv.save_json(_srv.LEDGER_FILE,      thr_ledger)
        _srv.save_json(_srv.WBTC_LEDGER_FILE, wbtc_ledger)
        _srv.save_token_balances(token_balances)
        _srv.save_pools(pools)
    except Exception as _e:
        app.logger.error('[V1Swap] save_error: %s', _e)
        return _jsonify(ok=False, error='state_save_failed', detail=str(_e)), 500

    # ── Build transaction record ──────────────────────────────────────────────
    try:
        tx_id        = 'swap_' + _secrets_mod.token_hex(16)
        now_ts       = int(_time_mod.time())
        chain_data   = _srv.load_json(_srv.CHAIN_FILE, {'blocks': [], 'height': 0})
        block_height = int(chain_data.get('height', 0)) + 1

        tx = {
            'id':            tx_id,
            'type':          'swap',
            'from':          trader,
            'token_in':      token_in,
            'token_out':     token_out,
            'amount_in':     amount_in,
            'amount_out':    amount_out,
            'fee':           round(total_fee, 8),
            'price_impact':  round(total_price_impact, 6),
            'legs':          swap_trace,
            'timestamp':     now_ts,
            'block':         block_height,
            'source':        'wallet_pwa_v1',
        }

        _srv.update_last_block(tx)
        _srv.persist_normalized_tx(tx)
    except Exception as _e:
        app.logger.warning('[V1Swap] tx_record_error (swap already applied): %s', _e)
        tx_id = 'swap_unrecorded'

    app.logger.info('[V1Swap] success trader=%s %s->%s in=%.6f out=%.6f fee=%.6f',
                    trader, token_in, token_out, amount_in, amount_out, total_fee)

    return _jsonify(
        status       = 'success',
        ok           = True,
        tx_id        = tx_id,
        from_addr    = trader,
        token_in     = token_in,
        token_out    = token_out,
        amount_in    = amount_in,
        amount_out   = amount_out,
        fee          = round(total_fee, 8),
        price_impact = round(total_price_impact, 6),
        legs         = swap_trace,
    ), 200


@app.route('/api/wallet/v1/add_liquidity', methods=['POST'])
def wallet_v1_add_liquidity():
    """
    PWA add liquidity — primary path requires signed action intent; legacy private_key_hex is fallback.

    Signed path (preferred):
      intent      – action='pool_deposit_intent', asset=pool_id, amount=amount_a
      signature, public_key
      payload     – { pool_id, amount_a, amount_b }

    Legacy path (deprecated):
      from, pool_id, amount_a, amount_b, private_key_hex
    """
    import server as _srv2
    import secrets as _sec2
    import time as _t2

    data = _request.get_json() or {}
    intent_raw = data.get('intent')
    signature  = (data.get('signature')  or '').strip()
    public_key = (data.get('public_key') or '').strip()
    use_signed = bool(intent_raw and signature and public_key)

    if use_signed:
        intent = intent_raw if isinstance(intent_raw, dict) else {}
        ok, err_code, err_detail = _verify_wallet_action_intent(intent, signature, public_key)
        if not ok:
            return _jsonify(ok=False, error=err_code, detail=err_detail), 400
        payload = data.get('payload') or {}
        if not _verify_action_payload_hash(intent.get('payload_hash', ''), payload):
            return _jsonify(ok=False, error='payload_hash_mismatch',
                            detail='payload does not match signed intent'), 400
        from_addr = str(intent.get('from_thr', '')).strip().upper()
        pool_id   = str(payload.get('pool_id') or intent.get('asset') or '').strip()
        amt_a_raw = payload.get('amount_a') or intent.get('amount') or 0
        amt_b_raw = payload.get('amount_b', 0)
    else:
        priv_hex  = (data.get('private_key_hex') or '').strip()
        from_addr = (data.get('from')            or '').strip().upper()
        pool_id   = (data.get('pool_id')         or '').strip()
        amt_a_raw = data.get('amount_a', 0)
        amt_b_raw = data.get('amount_b', 0)
        if not from_addr or not pool_id or not priv_hex:
            return _jsonify(ok=False, error='missing_required_fields'), 400
        try:
            from cryptography.hazmat.primitives.asymmetric import ec as _ec2
            from cryptography.hazmat.primitives.serialization import Encoding as _Enc2, PublicFormat as _PF2
            from cryptography.hazmat.backends import default_backend as _backend2
            from wallet_v1_address_derivation import derive_thronos_address as _derive2
            _priv_key2 = _ec2.derive_private_key(int(priv_hex, 16), _ec2.SECP256K1(), _backend2())
            _pub_bytes2 = _priv_key2.public_key().public_bytes(_Enc2.X962, _PF2.CompressedPoint)
            if _derive2(_pub_bytes2.hex()).upper() != from_addr:
                return _jsonify(ok=False, error='address_mismatch'), 403
        except Exception as _e2:
            return _jsonify(ok=False, error='invalid_private_key', detail=str(_e2)), 400
        app.logger.warning('[V1AddLiquidity] private_key_hex auth deprecated — upgrade to signed intent')

    if not from_addr or not pool_id:
        return _jsonify(ok=False, error='missing_required_fields'), 400

    provider = from_addr

    # ── Validate amounts ──────────────────────────────────────────────────────
    try:
        amt_a = float(amt_a_raw)
        amt_b = float(amt_b_raw)
    except (TypeError, ValueError):
        return _jsonify(ok=False, error='invalid_amounts'), 400
    if amt_a <= 0 or amt_b <= 0:
        return _jsonify(ok=False, error='amounts_must_be_positive'), 400

    # ── Load pool ─────────────────────────────────────────────────────────────
    pools = _srv2.load_pools()
    pool = next((p for p in pools if p.get('id') == pool_id), None)
    if not pool:
        return _jsonify(ok=False, error='pool_not_found'), 404

    token_a    = pool['token_a']
    token_b    = pool['token_b']
    reserves_a = float(pool['reserves_a'])
    reserves_b = float(pool['reserves_b'])
    total_shares = float(pool['total_shares'])

    # Ratio check (2% tolerance)
    if reserves_b > 0:
        expected = reserves_a / reserves_b
        provided = amt_a / amt_b if amt_b > 0 else 0
        if abs(expected - provided) / max(expected, 1e-9) > 0.02:
            return _jsonify(ok=False, error='ratio_mismatch',
                            expected_ratio=expected, provided_ratio=provided), 400

    # ── Balance check ─────────────────────────────────────────────────────────
    thr_ledger   = _srv2.load_json(_srv2.LEDGER_FILE, {})
    wbtc_ledger  = _srv2.load_json(_srv2.WBTC_LEDGER_FILE, {})
    token_bals   = _srv2.load_token_balances()

    def _avail(sym):
        if sym == 'THR': return float(thr_ledger.get(provider, 0.0))
        if sym == 'WBTC': return float(wbtc_ledger.get(provider, 0.0))
        return float(token_bals.get(sym, {}).get(provider, 0.0))

    if _avail(token_a) < amt_a or _avail(token_b) < amt_b:
        return _jsonify(ok=False, error='insufficient_balance'), 400

    # ── Deduct balances ───────────────────────────────────────────────────────
    def _deduct(sym, amt):
        if sym == 'THR':
            thr_ledger[provider] = round(float(thr_ledger.get(provider, 0.0)) - amt, 6)
        elif sym == 'WBTC':
            wbtc_ledger[provider] = round(float(wbtc_ledger.get(provider, 0.0)) - amt, 6)
        else:
            token_bals.setdefault(sym, {})
            token_bals[sym][provider] = round(float(token_bals[sym].get(provider, 0.0)) - amt, 6)

    _deduct(token_a, amt_a)
    _deduct(token_b, amt_b)
    _srv2.save_json(_srv2.LEDGER_FILE, thr_ledger)
    _srv2.save_json(_srv2.WBTC_LEDGER_FILE, wbtc_ledger)
    _srv2.save_token_balances(token_bals)

    # ── Mint shares ───────────────────────────────────────────────────────────
    shares_minted = (amt_a / reserves_a) * total_shares if reserves_a > 0 else (amt_a * amt_b) ** 0.5
    pool['reserves_a']  = round(reserves_a + amt_a, 6)
    pool['reserves_b']  = round(reserves_b + amt_b, 6)
    pool['total_shares'] = round(total_shares + shares_minted, 6)
    pool.setdefault('providers', {})[provider] = round(
        float(pool['providers'].get(provider, 0.0)) + shares_minted, 6)
    _srv2.save_pools(pools)

    # ── Record tx ─────────────────────────────────────────────────────────────
    ts    = _t2.strftime('%Y-%m-%d %H:%M:%S UTC', _t2.gmtime())
    tx_id = f"POOL-ADD-{int(_t2.time())}-{_sec2.token_hex(4)}"
    tx = {
        'kind': 'liquidity_add', 'type': 'liquidity_add',
        'pool_id': pool_id, 'token_a': token_a, 'token_b': token_b,
        'added_a': amt_a, 'added_b': amt_b,
        'shares_minted': shares_minted,
        'from': provider, 'provider': provider,
        'timestamp': ts, 'tx_id': tx_id, 'status': 'confirmed',
        'event_type': 'ADD_LIQ', 'subtype': 'add_liq',
        'pool_event': {'tokenA': token_a, 'amountA': amt_a, 'tokenB': token_b,
                       'amountB': amt_b, 'lp_minted': shares_minted},
    }
    chain = _srv2.load_json(_srv2.CHAIN_FILE, [])
    chain.append(tx)
    _srv2.save_json(_srv2.CHAIN_FILE, chain)
    try: _srv2.update_last_block(tx, is_block=False)
    except Exception: pass
    try: _srv2.persist_normalized_tx(tx)
    except Exception: pass

    return _jsonify(ok=True, status='success', tx_id=tx_id,
                    shares_minted=round(shares_minted, 6),
                    pool_id=pool_id, token_a=token_a, token_b=token_b,
                    added_a=amt_a, added_b=amt_b), 200


def _wallet_v1_verify_owner(from_addr, priv_hex):
    """Shared helper: derive THR address from private_key_hex, confirm it matches from_addr."""
    try:
        from cryptography.hazmat.primitives.asymmetric import ec as _ec
        from cryptography.hazmat.primitives.serialization import Encoding as _Enc, PublicFormat as _PF
        from cryptography.hazmat.backends import default_backend as _backend
        from wallet_v1_address_derivation import derive_thronos_address as _derive
        priv_key = _ec.derive_private_key(int(priv_hex, 16), _ec.SECP256K1(), _backend())
        pub_bytes = priv_key.public_key().public_bytes(_Enc.X962, _PF.CompressedPoint)
        derived = _derive(pub_bytes.hex())
        if derived.upper() != from_addr.upper():
            return False, None
        return True, derived
    except Exception:
        return False, None


@app.route('/api/wallet/v1/create_token', methods=['POST'])
def wallet_v1_create_token():
    """
    PWA/mobile create-token — primary path requires signed action intent; legacy private_key_hex is fallback.

    Signed path (preferred):
      intent      – action='token_create', asset=symbol, amount=total_supply
      signature, public_key
      payload     – { name, symbol, total_supply, decimals }

    Legacy path (deprecated):
      from, name, symbol, total_supply, decimals, private_key_hex
    """
    import server as _srv3
    import time as _t3
    import uuid as _uuid3

    data = _request.get_json() or {}
    intent_raw = data.get('intent')
    signature  = (data.get('signature')  or '').strip()
    public_key = (data.get('public_key') or '').strip()
    use_signed = bool(intent_raw and signature and public_key)

    if use_signed:
        intent = intent_raw if isinstance(intent_raw, dict) else {}
        ok, err_code, err_detail = _verify_wallet_action_intent(intent, signature, public_key)
        if not ok:
            return _jsonify(ok=False, error=err_code, detail=err_detail), 400
        payload = data.get('payload') or {}
        if not _verify_action_payload_hash(intent.get('payload_hash', ''), payload):
            return _jsonify(ok=False, error='payload_hash_mismatch',
                            detail='payload does not match signed intent'), 400
        from_addr    = str(intent.get('from_thr', '')).strip().upper()
        name         = str(payload.get('name') or '').strip()
        symbol       = str(payload.get('symbol') or intent.get('asset') or '').strip().upper()
        total_raw    = payload.get('total_supply') or intent.get('amount') or 0
        decimals_raw = payload.get('decimals', 0)
    else:
        priv_hex     = (data.get('private_key_hex') or '').strip()
        from_addr    = (data.get('from')            or '').strip().upper()
        name         = (data.get('name')            or '').strip()
        symbol       = (data.get('symbol')          or '').strip().upper()
        total_raw    = data.get('total_supply', 0)
        decimals_raw = data.get('decimals', 0)
        if not from_addr or not name or not symbol or not priv_hex:
            return _jsonify(ok=False, error='missing_required_fields'), 400
        owner_ok, _ = _wallet_v1_verify_owner(from_addr, priv_hex)
        if not owner_ok:
            return _jsonify(ok=False, error='invalid_private_key_or_address_mismatch'), 403
        app.logger.warning('[V1CreateToken] private_key_hex auth deprecated — upgrade to signed intent')

    if not from_addr or not name or not symbol:
        return _jsonify(ok=False, error='missing_required_fields'), 400

    try:
        total_supply = float(total_raw)
    except (TypeError, ValueError):
        return _jsonify(ok=False, error='invalid_total_supply'), 400
    if total_supply <= 0:
        return _jsonify(ok=False, error='invalid_total_supply'), 400
    if not symbol or len(symbol) > 8 or not symbol.isalnum():
        return _jsonify(ok=False, error='invalid_symbol'), 400
    if symbol in ('THR', 'WBTC'):
        return _jsonify(ok=False, error='symbol_reserved'), 400
    try:
        decimals = int(decimals_raw)
    except (TypeError, ValueError):
        return _jsonify(ok=False, error='invalid_decimals'), 400
    if decimals < 0 or decimals > 18:
        return _jsonify(ok=False, error='decimals_out_of_range'), 400

    tokens = _srv3.load_tokens()
    if any(t.get('symbol') == symbol for t in tokens):
        return _jsonify(ok=False, error='symbol_already_exists'), 400

    token_id = str(_uuid3.uuid4())
    new_token = {
        'id': token_id, 'name': name, 'symbol': symbol,
        'total_supply': round(total_supply, decimals), 'decimals': decimals,
        'owner': from_addr,
    }
    tokens.append(new_token)
    _srv3.save_tokens(tokens)

    balances = _srv3.load_token_balances()
    balances.setdefault(symbol, {})
    balances[symbol][from_addr] = round(total_supply, decimals)
    _srv3.save_token_balances(balances)

    ts = _t3.strftime('%Y-%m-%d %H:%M:%S UTC', _t3.gmtime())
    tx_id = f"TOKEN-CREATE-{int(_t3.time())}-{_uuid3.uuid4().hex[:8]}"
    tx = {
        'type': 'token_create', 'symbol': symbol, 'name': name,
        'decimals': decimals, 'owner': from_addr,
        'total_supply': round(total_supply, decimals),
        'timestamp': ts, 'tx_id': tx_id, 'status': 'confirmed',
    }
    chain = _srv3.load_json(_srv3.CHAIN_FILE, [])
    chain.append(tx)
    _srv3.save_json(_srv3.CHAIN_FILE, chain)
    try: _srv3.update_last_block(tx, is_block=False)
    except Exception: pass
    try: _srv3.broadcast_tx(tx)
    except Exception: pass

    return _jsonify(ok=True, status='success', token=new_token), 201


@app.route('/api/wallet/v1/nfts/mint', methods=['POST'])
def wallet_v1_nfts_mint():
    """
    PWA/mobile NFT mint — primary path requires signed action intent; legacy private_key_hex is fallback.

    Signed path (preferred):
      intent      – action='nft_mint', asset='NFT', amount=price_thr
      signature, public_key
      payload     – { name, description, category, price, royalties }
      image_data_url may be sent alongside (not hashed — too large for canonical)

    Legacy path (deprecated):
      from, name, description, category, price, royalties, image_data_url, private_key_hex
    """
    import server as _srv4
    import time as _t4
    import base64 as _b64
    import re as _re4

    data = _request.get_json() or {}
    intent_raw = data.get('intent')
    signature  = (data.get('signature')  or '').strip()
    public_key = (data.get('public_key') or '').strip()
    use_signed = bool(intent_raw and signature and public_key)

    if use_signed:
        intent = intent_raw if isinstance(intent_raw, dict) else {}
        ok, err_code, err_detail = _verify_wallet_action_intent(intent, signature, public_key)
        if not ok:
            return _jsonify(ok=False, error=err_code, detail=err_detail), 400
        payload = data.get('payload') or {}
        if not _verify_action_payload_hash(intent.get('payload_hash', ''), payload):
            return _jsonify(ok=False, error='payload_hash_mismatch',
                            detail='payload does not match signed intent'), 400
        from_addr      = str(intent.get('from_thr', '')).strip().upper()
        name           = str(payload.get('name') or '').strip()
        description    = str(payload.get('description') or '').strip()
        category       = str(payload.get('category') or 'art').strip()
        price_raw      = payload.get('price', 0)
        royalties_raw  = payload.get('royalties', 10)
        image_data_url = (data.get('image_data_url') or '').strip()  # not hashed — too large
    else:
        priv_hex       = (data.get('private_key_hex') or '').strip()
        from_addr      = (data.get('from')            or '').strip().upper()
        name           = (data.get('name')            or '').strip()
        description    = (data.get('description')     or '').strip()
        category       = (data.get('category')        or 'art').strip()
        price_raw      = data.get('price', 0)
        royalties_raw  = data.get('royalties', 10)
        image_data_url = (data.get('image_data_url')  or '').strip()
        if not from_addr or not name or not priv_hex:
            return _jsonify(ok=False, error='missing_required_fields'), 400
        owner_ok, _ = _wallet_v1_verify_owner(from_addr, priv_hex)
        if not owner_ok:
            return _jsonify(ok=False, error='invalid_private_key_or_address_mismatch'), 403
        app.logger.warning('[V1NFTMint] private_key_hex auth deprecated — upgrade to signed intent')

    if not from_addr or not name:
        return _jsonify(ok=False, error='missing_required_fields'), 400

    try:
        price = float(price_raw)
    except (TypeError, ValueError):
        return _jsonify(ok=False, error='invalid_price'), 400
    try:
        royalties = max(0, min(50, int(royalties_raw)))
    except (TypeError, ValueError):
        return _jsonify(ok=False, error='invalid_royalties'), 400

    mint_fee = _srv4.NFT_MINT_FEE
    ledger = _srv4.load_json(_srv4.LEDGER_FILE, {})
    balance = float(ledger.get(from_addr, 0.0))
    if balance < mint_fee:
        return _jsonify(ok=False, error='insufficient_balance',
                        mint_fee=mint_fee, balance=balance), 402

    nft_id = f"NFT{int(_t4.time() * 1000)}"
    image_url = None
    if image_data_url:
        match = _re4.match(r'^data:image/(png|jpe?g|gif|webp);base64,(.+)$', image_data_url, _re4.IGNORECASE)
        if match:
            ext = match.group(1).lower().replace('jpeg', 'jpg')
            try:
                raw = _b64.b64decode(match.group(2))
                _srv4.os.makedirs(_srv4.NFT_IMAGES_DIR, exist_ok=True)
                filename = f"{nft_id}.{ext}"
                with open(_srv4.os.path.join(_srv4.NFT_IMAGES_DIR, filename), 'wb') as f:
                    f.write(raw)
                image_url = f"/media/nft_images/{filename}"
            except Exception:
                image_url = None

    ledger[from_addr] = round(balance - mint_fee, 6)
    network_wallet = _srv4.os.getenv('NETWORK_FEE_WALLET', 'THR_NETWORK_FEES_00001')
    ledger[network_wallet] = round(float(ledger.get(network_wallet, 0.0)) + mint_fee, 6)
    _srv4.save_json(_srv4.LEDGER_FILE, ledger)

    timestamp = _t4.strftime('%Y-%m-%d %H:%M:%S UTC', _t4.gmtime())
    nft = {
        'id': nft_id, 'name': name, 'description': description, 'category': category,
        'price': price, 'royalties': royalties, 'creator': from_addr, 'owner': from_addr,
        'image_url': image_url, 'created_at': timestamp, 'for_sale': True, 'mint_fee': mint_fee,
    }
    registry = _srv4.load_nft_registry()
    registry.setdefault('nfts', []).append(nft)
    _srv4.save_nft_registry(registry)

    chain = _srv4.load_json(_srv4.CHAIN_FILE, [])
    tx = {
        'type': 'nft_mint', 'category': 'nft_mint', 'from': from_addr, 'to': network_wallet,
        'amount': mint_fee, 'fee': mint_fee, 'fee_burned': mint_fee,
        'symbol': 'THR', 'token_symbol': 'THR', 'asset_symbol': 'THR',
        'nft_id': nft_id, 'nft_name': name, 'timestamp': timestamp, 'status': 'confirmed',
    }
    chain.append(tx)
    _srv4.save_json(_srv4.CHAIN_FILE, chain)
    try: _srv4.update_last_block(tx, is_block=False)
    except Exception: pass

    nft['image_url'] = _srv4.normalize_media_url(nft.get('image_url') or nft.get('image'))
    return _jsonify(ok=True, status='success', nft=nft, mint_fee=mint_fee,
                    new_balance=ledger.get(from_addr, 0.0)), 201


@app.route('/api/wallet/v1/nfts/buy', methods=['POST'])
def wallet_v1_nfts_buy():
    """
    PWA/mobile NFT buy — primary path requires signed action intent; legacy private_key_hex is fallback.

    Signed path (preferred):
      intent     – action='nft_buy', asset=nft_id, amount=price_thr
      signature, public_key
      payload    – { nft_id }

    Legacy path (deprecated):
      from, nft_id, private_key_hex
    """
    import server as _srv5
    import time as _t5

    data = _request.get_json() or {}
    intent_raw = data.get('intent')
    signature  = (data.get('signature')  or '').strip()
    public_key = (data.get('public_key') or '').strip()
    use_signed = bool(intent_raw and signature and public_key)

    if use_signed:
        intent = intent_raw if isinstance(intent_raw, dict) else {}
        ok, err_code, err_detail = _verify_wallet_action_intent(intent, signature, public_key)
        if not ok:
            return _jsonify(ok=False, error=err_code, detail=err_detail), 400
        payload = data.get('payload') or {}
        if not _verify_action_payload_hash(intent.get('payload_hash', ''), payload):
            return _jsonify(ok=False, error='payload_hash_mismatch',
                            detail='payload does not match signed intent'), 400
        from_addr = str(intent.get('from_thr', '')).strip().upper()
        nft_id    = str(payload.get('nft_id') or intent.get('asset') or '').strip()
    else:
        priv_hex  = (data.get('private_key_hex') or '').strip()
        from_addr = (data.get('from')   or '').strip().upper()
        nft_id    = (data.get('nft_id') or '').strip()
        if not from_addr or not nft_id or not priv_hex:
            return _jsonify(ok=False, error='missing_required_fields'), 400
        owner_ok, _ = _wallet_v1_verify_owner(from_addr, priv_hex)
        if not owner_ok:
            return _jsonify(ok=False, error='invalid_private_key_or_address_mismatch'), 403
        app.logger.warning('[V1NFTBuy] private_key_hex auth deprecated — upgrade to signed intent')

    if not from_addr or not nft_id:
        return _jsonify(ok=False, error='missing_required_fields'), 400

    buyer = from_addr
    registry = _srv5.load_nft_registry()
    nft = next((n for n in registry.get('nfts', []) if n.get('id') == nft_id), None)
    if not nft:
        return _jsonify(ok=False, error='nft_not_found'), 404
    if not nft.get('for_sale'):
        return _jsonify(ok=False, error='nft_not_for_sale'), 400
    if nft.get('owner') == buyer:
        return _jsonify(ok=False, error='already_owned'), 400

    price = float(nft.get('price', 0))
    if price <= 0:
        return _jsonify(ok=False, error='nft_has_no_price'), 400

    ledger = _srv5.load_json(_srv5.LEDGER_FILE, {})
    buyer_balance = float(ledger.get(buyer, 0.0))
    if buyer_balance < price:
        return _jsonify(ok=False, error='insufficient_balance', price=price, balance=buyer_balance), 402

    royalty_pct = min(50, max(0, int(nft.get('royalties', 10)))) / 100.0
    royalty_amount = round(price * royalty_pct, 6)
    seller_amount = round(price - royalty_amount, 6)
    old_owner = nft['owner']
    creator_addr = nft.get('creator', old_owner)

    ledger[buyer] = round(buyer_balance - price, 6)
    ledger[old_owner] = round(float(ledger.get(old_owner, 0.0)) + seller_amount, 6)
    if creator_addr != old_owner and royalty_amount > 0:
        ledger[creator_addr] = round(float(ledger.get(creator_addr, 0.0)) + royalty_amount, 6)
    elif royalty_amount > 0:
        ledger[old_owner] = round(float(ledger.get(old_owner, 0.0)) + royalty_amount, 6)
    _srv5.save_json(_srv5.LEDGER_FILE, ledger)

    nft['owner'] = buyer
    nft['for_sale'] = False
    _srv5.save_nft_registry(registry)

    timestamp = _t5.strftime('%Y-%m-%d %H:%M:%S UTC', _t5.gmtime())
    chain = _srv5.load_json(_srv5.CHAIN_FILE, [])
    tx = {
        'type': 'nft_buy', 'category': 'nft_buy', 'from': buyer, 'to': old_owner,
        'amount': price, 'fee': 0.0, 'symbol': 'THR', 'token_symbol': 'THR', 'asset_symbol': 'THR',
        'nft_id': nft_id, 'nft_name': nft.get('name', ''),
        'royalty_amount': royalty_amount, 'royalty_to': creator_addr,
        'timestamp': timestamp, 'status': 'confirmed',
    }
    chain.append(tx)
    _srv5.save_json(_srv5.CHAIN_FILE, chain)
    try: _srv5.update_last_block(tx, is_block=False)
    except Exception: pass

    return _jsonify(ok=True, status='success', nft=nft, price=price,
                    royalty=royalty_amount, new_balance=ledger.get(buyer, 0.0)), 200


# ── THR Wallet PWA — served from public/wallet-pwa/ ───────────────────────────
import os as _os
from flask import send_from_directory as _send

_PUBLIC_DIR = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'public')

@app.route('/wallet-pwa/')
@app.route('/wallet-pwa/<path:filename>')
def wallet_pwa(filename='index.html'):
    """Serve the THR Wallet PWA static files."""
    pwa_dir = _os.path.join(_PUBLIC_DIR, 'wallet-pwa')
    # Default to index.html for directory requests
    if not filename or filename.endswith('/'):
        filename = 'index.html'
    return _send(pwa_dir, filename)



# ── Security: block PHP probe / scanner bots ──────────────────────────────────
import time as _time
import threading as _threading
from collections import defaultdict as _defaultdict
from flask import request as _req, abort as _abort

_probe_counts = _defaultdict(list)  # ip -> [timestamps]
_blocked_ips: set = set()
_probe_lock = _threading.Lock()

# Paths that signal automated scanner/webshell probe activity
_PHP_PROBE_SUFFIXES = (
    '.php', '.asp', '.aspx', '.jsp', '.cgi', '.sh',
)
_PHP_PROBE_KEYWORDS = (
    'wp-admin', 'wp-content', 'wp-includes', 'wp-login', 'wp-config',
    'phpMyAdmin', 'phpmyadmin', 'adminer', 'xmlrpc', '.env', 'shell',
    'webshell', 'c99', 'r57',
)

def _is_probe_path(path: str) -> bool:
    p = path.lower()
    if any(p.endswith(s) for s in _PHP_PROBE_SUFFIXES):
        return True
    if any(k in p for k in _PHP_PROBE_KEYWORDS):
        return True
    return False

@app.before_request
def _block_scanners():
    ip = (_req.headers.get('X-Forwarded-For') or _req.remote_addr or '').split(',')[0].strip()
    path = _req.path

    with _probe_lock:
        if ip in _blocked_ips:
            _abort(403)

        if _is_probe_path(path):
            now = _time.time()
            window = [t for t in _probe_counts[ip] if now - t < 60]
            window.append(now)
            _probe_counts[ip] = window
            # Block IP after 8 probe requests in 60 seconds
            if len(window) >= 8:
                _blocked_ips.add(ip)
                app.logger.warning('[Security] Blocked scanner IP %s after %d PHP probes', ip, len(window))
                _abort(403)

# Prune old probe records every 5 minutes
def _prune_probe_counts():
    while True:
        _time.sleep(300)
        now = _time.time()
        with _probe_lock:
            for ip in list(_probe_counts):
                _probe_counts[ip] = [t for t in _probe_counts[ip] if now - t < 60]
                if not _probe_counts[ip]:
                    del _probe_counts[ip]

_threading.Thread(target=_prune_probe_counts, daemon=True).start()
