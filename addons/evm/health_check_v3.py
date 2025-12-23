"""
Health Check Blueprint for Thronos EVM
Provides monitoring endpoints for EVM health status
"""

from flask import Blueprint, jsonify
import os
import json
from datetime import datetime

health_bp = Blueprint('health', __name__, url_prefix='/api/health')

@health_bp.route('/evm', methods=['GET'])
def evm_health():
    """Check EVM module health status"""
    try:
        # Check if EVM core files exist
        evm_dir = os.path.join(os.path.dirname(__file__))
        core_exists = os.path.exists(os.path.join(evm_dir, 'evm_core.py'))
        api_exists = os.path.exists(os.path.join(evm_dir, 'evm_api_v3.py'))
        
        # Check if contracts directory exists
        data_dir = os.path.join(os.path.dirname(os.path.dirname(evm_dir)), 'data')
        contracts_dir = os.path.join(data_dir, 'evm_contracts')
        contracts_exist = os.path.exists(contracts_dir)
        
        # Count deployed contracts
        contract_count = 0
        if contracts_exist:
            contract_count = len([f for f in os.listdir(contracts_dir) if f.endswith('.json')])
        
        status = {
            "status": "healthy" if (core_exists and api_exists) else "degraded",
            "timestamp": datetime.utcnow().isoformat(),
            "components": {
                "evm_core": "ok" if core_exists else "missing",
                "evm_api": "ok" if api_exists else "missing",
                "storage": "ok" if contracts_exist else "not_initialized"
            },
            "metrics": {
                "deployed_contracts": contract_count,
                "version": "3.0.0"
            }
        }
        
        return jsonify(status), 200 if status["status"] == "healthy" else 503
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }), 500

@health_bp.route('/node', methods=['GET'])
def node_health():
    """Check overall node health"""
    try:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
        
        # Check critical files
        ledger_exists = os.path.exists(os.path.join(data_dir, 'ledger.json'))
        chain_exists = os.path.exists(os.path.join(data_dir, 'chain.json'))
        
        status = {
            "status": "healthy" if (ledger_exists and chain_exists) else "degraded",
            "timestamp": datetime.utcnow().isoformat(),
            "components": {
                "ledger": "ok" if ledger_exists else "missing",
                "blockchain": "ok" if chain_exists else "missing",
                "evm": "enabled"
            }
        }
        
        return jsonify(status), 200 if status["status"] == "healthy" else 503
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }), 500