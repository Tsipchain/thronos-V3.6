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
    Full pledge→V1 migration in one call:
    1. Verify send_secret ownership (same lookup as pledge-lookup)
    2. Call existing wallet_v1_migration.migrate_legacy_address
    3. Return new canonical V1 address + a fresh recovery session token

    Input:  { "send_secret": "...", "pin": "1234" }
    Output: { "ok": true, "canonical_v1_address": "THR...", "legacy_address": "THR..." }
    """
    try:
        data = _request.get_json() or {}
        send_secret = (data.get('send_secret') or '').strip()
        pin = (data.get('pin') or '').strip()

        if not send_secret:
            return _jsonify(ok=False, error='send_secret_required'), 400

        # Find pledge record
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

        # Check if already migrated
        try:
            from wallet_v1_migration import search_all_migration_sources
            existing = search_all_migration_sources(legacy_address=old_address)
            if existing and existing.get('canonical_v1_address'):
                return _jsonify(
                    ok=True,
                    canonical_v1_address=existing['canonical_v1_address'],
                    legacy_address=old_address,
                    already_migrated=True,
                ), 200
        except ImportError:
            pass

        # Execute migration
        try:
            from wallet_v1_migration import migrate_legacy_address
            result = migrate_legacy_address(
                old_address=old_address,
                legacy_secret=send_secret,
                pin=pin or None,
            )
            canonical = result.get('new_v1_address') or result.get('canonical_v1_address', '')
            return _jsonify(
                ok=True,
                canonical_v1_address=canonical,
                legacy_address=old_address,
                already_migrated=False,
            ), 200
        except Exception as mig_exc:
            app.logger.error('[PledgeMigrate] migration error: %s', mig_exc)
            return _jsonify(ok=False, error='migration_failed', detail=str(mig_exc)), 500

    except Exception as exc:
        app.logger.error('[PledgeMigrate] %s', exc)
        return _jsonify(ok=False, error='internal_error'), 500


# THR Wallet PWA — served from public/wallet-pwa/
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

