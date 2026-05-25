"""
Wallet V1 Blueprint — Modular ECDSA/secp256k1 transaction signing

Registers all Wallet V1 endpoints without modifying server.py.
Entry point: register_wallet_v1_routes(app, redis_client, node_role, read_only, sqlite_path)
"""

from flask import Blueprint, request
from wallet_v1_handlers import (
    handle_tx_send,
    handle_address_derivation,
    handle_wallet_health,
    handle_wallet_migrate,
    handle_wallet_migration_repair,
    init_wallet_v1_handler,
)

wallet_v1_bp = Blueprint(
    'wallet_v1',
    __name__,
    url_prefix='/api/v1',
)


@wallet_v1_bp.route('/tx/send', methods=['POST'])
def tx_send():
    return handle_tx_send(request)


@wallet_v1_bp.route('/address/derive', methods=['POST'])
def address_derive():
    return handle_address_derivation(request)


@wallet_v1_bp.route('/wallet/health', methods=['GET'])
def wallet_health():
    return handle_wallet_health()


@wallet_v1_bp.route('/wallet/migrate', methods=['POST'])
def wallet_migrate():
    return handle_wallet_migrate(request)


@wallet_v1_bp.route('/wallet/migration/repair', methods=['POST'])
def wallet_migration_repair():
    return handle_wallet_migration_repair(request)


def register_wallet_v1_routes(app, redis_client=None, node_role="master", read_only=False, sqlite_path=None):
    init_wallet_v1_handler(app, redis_client, node_role, read_only, sqlite_path)
    app.register_blueprint(wallet_v1_bp)
    app.logger.info("[WalletV1] Blueprint registered at /api/v1/tx/send, /api/v1/address/derive, /api/v1/wallet/health, /api/v1/wallet/migrate")
