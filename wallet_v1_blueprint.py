"""
Wallet V1 Blueprint — Modular ECDSA/secp256k1 transaction signing

Registers all Wallet V1 endpoints without modifying server.py.
Entry point: register_wallet_v1_routes(app, redis_client, node_role, read_only, sqlite_path)
"""

from flask import Blueprint, request, jsonify
from wallet_v1_handlers import (
    handle_tx_send,
    handle_address_derivation,
    init_wallet_v1_handler,
)

wallet_v1_bp = Blueprint(
    'wallet_v1',
    __name__,
    url_prefix='/api/v1',
)


@wallet_v1_bp.route('/tx/send', methods=['POST'])
def tx_send():
    """Sign and send Thronos transaction (ECDSA/secp256k1)."""
    return handle_tx_send(request)


@wallet_v1_bp.route('/address/derive', methods=['POST'])
def address_derive():
    """Derive Thronos address from compressed public key."""
    return handle_address_derivation(request)


def register_wallet_v1_routes(app, redis_client=None, node_role="master", read_only=False, sqlite_path=None):
    """
    Register Wallet V1 blueprint with Flask app.

    Called from server_ext.py to avoid modifying server.py.

    Args:
        app: Flask application instance
        redis_client: Redis client for nonce tracking (required)
        node_role: "master" or "replica" (default: "master")
        read_only: True if this node is read-only (default: False)
        sqlite_path: Path to SQLite database on master node (required on master)
    """
    # Initialize wallet V1 with Flask app dependencies
    init_wallet_v1_handler(app, redis_client, node_role, read_only, sqlite_path)

    # Register blueprint
    app.register_blueprint(wallet_v1_bp)
    app.logger.info("[WalletV1] Blueprint registered at /api/v1/tx/send, /api/v1/address/derive")
