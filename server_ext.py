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


def _import_datetime():
    from datetime import datetime
    return datetime


# ── WalletConnect lightweight relay ────────────────────────────────────────────
# Stores pending sign requests in-memory (Redis if available, else dict).
# ThronosBuilder POSTs requests here; PWA polls and approves with Face ID.
import threading as _threading
_wc_store_lock = _threading.Lock()
_wc_store: dict = {}  # { address: [ {id, action, payload, dapp, ts} ] }
_wc_sessions: dict = {}  # { session_id: address }


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
    return _jsonify(ok=True), 200


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

