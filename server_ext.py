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
