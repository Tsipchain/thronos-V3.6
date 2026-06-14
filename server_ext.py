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

