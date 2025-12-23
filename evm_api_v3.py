# evm_api.py
# Flask API endpoints for Thronos EVM functionality

import os
import json
import time
import hashlib
from flask import request, jsonify
from typing import Dict, Any

from evm_core import ThronosEVM, estimate_gas, compile_solidity_stub


def register_evm_routes(app, data_dir: str, ledger_file: str, chain_file: str, pledge_chain: str):
    """
    Register EVM-related routes to the Flask app.
    
    Args:
        app: Flask application instance
        data_dir: Data directory path
        ledger_file: Path to ledger.json
        chain_file: Path to chain.json
        pledge_chain: Path to pledge_chain.json
    """
    
    # Initialize EVM
    evm = ThronosEVM(data_dir)
    
    def load_json(path, default):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except:
            return default
    
    def save_json(path, data):
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def verify_auth(thr_address: str, auth_secret: str, passphrase: str = "") -> bool:
        """Verify authentication for a THR address."""
        pledges = load_json(pledge_chain, [])
        pledge = next((p for p in pledges if p.get("thr_address") == thr_address), None)
        if not pledge:
            return False
        
        stored_hash = pledge.get("send_auth_hash")
        if not stored_hash:
            return False
        
        if pledge.get("has_passphrase"):
            auth_string = f"{auth_secret}:{passphrase}:auth"
        else:
            auth_string = f"{auth_secret}:auth"
        
        computed_hash = hashlib.sha256(auth_string.encode()).hexdigest()
        return computed_hash == stored_hash
    
    # ─── EVM CONTRACT DEPLOYMENT ────────────────────────────────────────
    
    @app.route("/api/evm/deploy", methods=["POST"])
    def api_evm_deploy():
        """
        Deploy a smart contract to Thronos EVM.
        
        Request body:
        {
            "deployer": "THR address",
            "auth_secret": "authentication secret",
            "passphrase": "optional passphrase",
            "bytecode": "0x... contract bytecode",
            "value": 0.0,  // THR to send with deployment
            "gas_limit": 1000000
        }
        
        Response:
        {
            "status": "success",
            "contract_address": "CONTRACT_...",
            "tx_id": "DEPLOY-...",
            "gas_used": 123456
        }
        """
        data = request.get_json() or {}
        
        deployer = (data.get("deployer") or "").strip()
        auth_secret = (data.get("auth_secret") or "").strip()
        passphrase = (data.get("passphrase") or "").strip()
        bytecode = (data.get("bytecode") or "").strip()
        value = float(data.get("value", 0.0))
        gas_limit = int(data.get("gas_limit", 1000000))
        
        # Validate inputs
        if not deployer or not auth_secret or not bytecode:
            return jsonify(error="Missing required fields"), 400
        
        # Verify authentication
        if not verify_auth(deployer, auth_secret, passphrase):
            return jsonify(error="Invalid authentication"), 403
        
        # Check balance
        ledger = load_json(ledger_file, {})
        balance = float(ledger.get(deployer, 0.0))
        
        # Estimate gas cost (simplified: 1 gas = 0.00001 THR)
        estimated_gas_cost = gas_limit * 0.00001
        total_cost = value + estimated_gas_cost
        
        if balance < total_cost:
            return jsonify(
                error="Insufficient balance",
                balance=balance,
                required=total_cost
            ), 400
        
        # Deploy contract
        success, contract_addr, message = evm.deploy_contract(
            bytecode=bytecode,
            deployer=deployer,
            value=value,
            gas_limit=gas_limit
        )
        
        if not success:
            return jsonify(error=message), 400
        
        # Deduct costs from deployer
        gas_used = gas_limit  # Simplified: assume full gas used
        actual_gas_cost = gas_used * 0.00001
        ledger[deployer] = round(balance - value - actual_gas_cost, 6)
        save_json(ledger_file, ledger)
        
        # Record transaction
        chain = load_json(chain_file, [])
        tx_id = f"DEPLOY-{int(time.time())}-{contract_addr[:8]}"
        tx = {
            "type": "contract_deploy",
            "from": deployer,
            "to": contract_addr,
            "contract_address": contract_addr,
            "value": value,
            "gas_limit": gas_limit,
            "gas_used": gas_used,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "tx_id": tx_id,
            "status": "confirmed"
        }
        chain.append(tx)
        save_json(chain_file, chain)
        
        return jsonify(
            status="success",
            contract_address=contract_addr,
            tx_id=tx_id,
            gas_used=gas_used,
            message=message
        ), 200
    
    # ─── EVM CONTRACT CALL ──────────────────────────────────────────────
    
    @app.route("/api/evm/call", methods=["POST"])
    def api_evm_call():
        """
        Call a deployed smart contract.
        
        Request body:
        {
            "caller": "THR address",
            "auth_secret": "authentication secret",
            "passphrase": "optional passphrase",
            "contract_address": "CONTRACT_...",
            "data": "0x... call data (function selector + args)",
            "value": 0.0,  // THR to send with call
            "gas_limit": 100000
        }
        
        Response:
        {
            "status": "success",
            "return_data": "0x...",
            "gas_used": 12345,
            "tx_id": "CALL-..."
        }
        """
        data = request.get_json() or {}
        
        caller = (data.get("caller") or "").strip()
        auth_secret = (data.get("auth_secret") or "").strip()
        passphrase = (data.get("passphrase") or "").strip()
        contract_address = (data.get("contract_address") or "").strip()
        call_data = (data.get("data") or "0x").strip()
        value = float(data.get("value", 0.0))
        gas_limit = int(data.get("gas_limit", 100000))
        
        # Validate inputs
        if not caller or not auth_secret or not contract_address:
            return jsonify(error="Missing required fields"), 400
        
        # Verify authentication
        if not verify_auth(caller, auth_secret, passphrase):
            return jsonify(error="Invalid authentication"), 403
        
        # Check balance
        ledger = load_json(ledger_file, {})
        balance = float(ledger.get(caller, 0.0))
        
        estimated_gas_cost = gas_limit * 0.00001
        total_cost = value + estimated_gas_cost
        
        if balance < total_cost:
            return jsonify(
                error="Insufficient balance",
                balance=balance,
                required=total_cost
            ), 400
        
        # Convert call data to bytes
        if call_data.startswith("0x"):
            call_data = call_data[2:]
        call_data_bytes = bytes.fromhex(call_data) if call_data else b""
        
        # Execute contract call
        success, result, gas_used = evm.call_contract(
            contract_address=contract_address,
            caller=caller,
            data=call_data_bytes,
            value=value,
            gas_limit=gas_limit
        )
        
        # Deduct costs
        actual_gas_cost = gas_used * 0.00001
        ledger[caller] = round(balance - value - actual_gas_cost, 6)
        save_json(ledger_file, ledger)
        
        # Record transaction
        chain = load_json(chain_file, [])
        tx_id = f"CALL-{int(time.time())}-{contract_address[:8]}"
        tx = {
            "type": "contract_call",
            "from": caller,
            "to": contract_address,
            "contract_address": contract_address,
            "value": value,
            "gas_limit": gas_limit,
            "gas_used": gas_used,
            "success": success,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "tx_id": tx_id,
            "status": "confirmed"
        }
        chain.append(tx)
        save_json(chain_file, chain)
        
        # Format response
        if success:
            return_data_hex = "0x" + (result.hex() if isinstance(result, bytes) else "")
            return jsonify(
                status="success",
                return_data=return_data_hex,
                gas_used=gas_used,
                tx_id=tx_id
            ), 200
        else:
            return jsonify(
                status="error",
                error=str(result),
                gas_used=gas_used,
                tx_id=tx_id
            ), 400
    
    # ─── EVM CONTRACT INFO ──────────────────────────────────────────────
    
    @app.route("/api/evm/contract/<contract_address>", methods=["GET"])
    def api_evm_get_contract(contract_address: str):
        """Get information about a deployed contract."""
        contract = evm.get_contract(contract_address)
        if not contract:
            return jsonify(error="Contract not found"), 404
        
        return jsonify(contract=contract), 200
    
    @app.route("/api/evm/contracts", methods=["GET"])
    def api_evm_list_contracts():
        """List all deployed contracts."""
        contracts = evm.list_contracts()
        return jsonify(contracts=contracts), 200
    
    @app.route("/api/evm/storage/<contract_address>/<int:key>", methods=["GET"])
    def api_evm_get_storage(contract_address: str, key: int):
        """Get storage value for a contract at a specific key."""
        value = evm.get_storage(contract_address, key)
        return jsonify(
            contract_address=contract_address,
            key=key,
            value=value
        ), 200
    
    # ─── EVM UTILITIES ──────────────────────────────────────────────────
    
    @app.route("/api/evm/estimate_gas", methods=["POST"])
    def api_evm_estimate_gas():
        """
        Estimate gas cost for a transaction.
        
        Request body:
        {
            "bytecode": "0x...",  // For deployment
            "data": "0x..."       // For call
        }
        """
        data = request.get_json() or {}
        bytecode = (data.get("bytecode") or "").strip()
        call_data = (data.get("data") or "").strip()
        
        if bytecode:
            if bytecode.startswith("0x"):
                bytecode = bytecode[2:]
            estimated = estimate_gas(bytecode)
        elif call_data:
            if call_data.startswith("0x"):
                call_data = call_data[2:]
            estimated = estimate_gas("", bytes.fromhex(call_data))
        else:
            estimated = 21000  # Base transaction cost
        
        return jsonify(estimated_gas=estimated), 200
    
    @app.route("/api/evm/compile", methods=["POST"])
    def api_evm_compile():
        """
        Compile Solidity source code to bytecode.
        
        This is a stub endpoint. In production, this would:
        - Use py-solc-x to compile Solidity
        - Or integrate with Remix API
        - Or use a separate compiler service
        
        Request body:
        {
            "source": "contract MyContract { ... }"
        }
        """
        data = request.get_json() or {}
        source = data.get("source", "")
        
        if not source:
            return jsonify(error="No source code provided"), 400
        
        # Stub compilation
        bytecode = compile_solidity_stub(source)
        
        return jsonify(
            status="success",
            bytecode=bytecode,
            note="This is a stub compiler. Integrate real Solidity compiler for production."
        ), 200
    
    print("[EVM] Routes registered successfully")