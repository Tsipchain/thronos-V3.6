from flask import Blueprint, request
from wallet_v1_handlers import (
    handle_tx_send, handle_address_derivation, handle_wallet_health,
    handle_wallet_migrate, handle_wallet_migration_repair, handle_wallet_migration_status, handle_wallet_bind_public_key, init_wallet_v1_handler,
)

wallet_v1_bp = Blueprint('wallet_v1', __name__, url_prefix='/api/v1')

@wallet_v1_bp.route('/tx/send', methods=['POST'])
def tx_send(): return handle_tx_send(request)

@wallet_v1_bp.route('/address/derive', methods=['POST'])
def address_derive(): return handle_address_derivation(request)

@wallet_v1_bp.route('/wallet/health', methods=['GET'])
def wallet_health(): return handle_wallet_health()

@wallet_v1_bp.route('/wallet/migrate', methods=['POST'])
def wallet_migrate(): return handle_wallet_migrate(request)

@wallet_v1_bp.route('/wallet/migration/repair', methods=['POST'])
def wallet_migration_repair(): return handle_wallet_migration_repair(request)

@wallet_v1_bp.route('/wallet/migration/status', methods=['POST'])
def wallet_migration_status(): return handle_wallet_migration_status(request)

@wallet_v1_bp.route('/wallet/bind_public_key', methods=['POST'])
def wallet_bind_public_key(): return handle_wallet_bind_public_key(request)


def register_wallet_v1_routes(app, redis_client=None, node_role='master', read_only=False, sqlite_path=None):
    init_wallet_v1_handler(app, redis_client, node_role, read_only, sqlite_path)
    app.register_blueprint(wallet_v1_bp)
