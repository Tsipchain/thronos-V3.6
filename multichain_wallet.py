"""
Multi-Chain Non-Custodial Wallet Backend (PR-184)

This module provides RPC-based wallet functionality for multiple chains:
- Bitcoin (BTC)
- Ethereum (ETH) and EVM-compatible chains (BSC, Polygon, Arbitrum, Optimism)
- Solana (SOL)
- XRP Ledger (XRP)

The backend:
- Stores only addresses (non-custodial - no private keys)
- Reads native balances from external RPCs
- Reads Thronos balances from the main chain
- Exposes REST APIs for wallet UI/extension/mobile
"""

import os
import json
import requests
from typing import Dict, List, Optional
from decimal import Decimal

# Environment configuration
DATA_DIR = os.getenv("DATA_DIR", "./data")
USER_PROFILES_FILE = os.path.join(DATA_DIR, "user_profiles.json")

# RPC URLs
ETH_RPC_URL = os.getenv("ETH_RPC_URL", "https://eth.llamarpc.com")
BSC_RPC_URL = os.getenv("BSC_RPC_URL", "https://bsc-dataseed.binance.org")
POLYGON_RPC_URL = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")
ARBITRUM_RPC_URL = os.getenv("ARBITRUM_RPC_URL", "https://arb1.arbitrum.io/rpc")
OPTIMISM_RPC_URL = os.getenv("OPTIMISM_RPC_URL", "https://mainnet.optimism.io")
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
XRP_RPC_URL = os.getenv("XRP_RPC_URL", "https://xrplcluster.com")
BTC_RPC_URL = os.getenv("BTC_RPC_URL", "")


def load_user_profiles() -> Dict:
    """Load user profiles from storage"""
    try:
        if os.path.exists(USER_PROFILES_FILE):
            with open(USER_PROFILES_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"Error loading user profiles: {e}")
        return {}


def save_user_profiles(profiles: Dict):
    """Save user profiles to storage"""
    try:
        os.makedirs(os.path.dirname(USER_PROFILES_FILE), exist_ok=True)
        with open(USER_PROFILES_FILE, 'w') as f:
            json.dump(profiles, f, indent=2)
    except Exception as e:
        print(f"Error saving user profiles: {e}")


def get_user_profile(user_id: str) -> Optional[Dict]:
    """
    Get user profile by ID

    Returns:
    {
        "user_id": "user123",
        "kyc_id": "KYC123",
        "is_kyc_verified": true/false,
        "is_whitelisted_admin": true/false,
        "thr_address": "THR...",
        "btc_address": "1...",
        "btc_pledge_address": "1...",
        "evm_address": "0x...",
        "sol_address": "...",
        "xrp_address": "r...",
        "created_at": timestamp,
        "updated_at": timestamp
    }
    """
    profiles = load_user_profiles()
    return profiles.get(user_id)


def save_user_profile(user_id: str, profile: Dict) -> Dict:
    """Save or update user profile"""
    import time

    profiles = load_user_profiles()

    if user_id not in profiles:
        profile["created_at"] = int(time.time())

    profile["updated_at"] = int(time.time())
    profiles[user_id] = profile

    save_user_profiles(profiles)
    return profile


def evm_rpc_call(rpc_url: str, method: str, params: list) -> Optional[Dict]:
    """Make a JSON-RPC call to an EVM-compatible chain"""
    try:
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1
        }

        response = requests.post(rpc_url, json=payload, timeout=10)

        if response.status_code == 200:
            result = response.json()
            if "error" in result:
                print(f"RPC error: {result['error']}")
                return None
            return result.get("result")
        else:
            print(f"RPC call failed: {response.status_code}")
            return None

    except Exception as e:
        print(f"RPC call exception: {e}")
        return None


def get_eth_balance(address: str, rpc_url: str = ETH_RPC_URL) -> float:
    """Get ETH balance for an address"""
    try:
        result = evm_rpc_call(rpc_url, "eth_getBalance", [address, "latest"])
        if result:
            # Convert from wei to ETH
            balance_wei = int(result, 16)
            balance_eth = balance_wei / 1e18
            return balance_eth
        return 0.0
    except Exception as e:
        print(f"Error getting ETH balance: {e}")
        return 0.0


def get_erc20_balance(
    address: str,
    token_address: str,
    rpc_url: str = ETH_RPC_URL
) -> float:
    """Get ERC20 token balance for an address"""
    try:
        # ERC20 balanceOf function signature: 0x70a08231
        data = "0x70a08231" + address[2:].zfill(64)

        result = evm_rpc_call(
            rpc_url,
            "eth_call",
            [{"to": token_address, "data": data}, "latest"]
        )

        if result:
            balance = int(result, 16)
            # Note: This assumes 18 decimals - adjust based on token
            return balance / 1e18
        return 0.0
    except Exception as e:
        print(f"Error getting ERC20 balance: {e}")
        return 0.0


def get_solana_balance(address: str) -> float:
    """Get SOL balance for an address"""
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getBalance",
            "params": [address]
        }

        response = requests.post(SOLANA_RPC_URL, json=payload, timeout=10)

        if response.status_code == 200:
            result = response.json()
            if "result" in result and "value" in result["result"]:
                # Convert from lamports to SOL
                lamports = result["result"]["value"]
                return lamports / 1e9
        return 0.0
    except Exception as e:
        print(f"Error getting Solana balance: {e}")
        return 0.0


def get_xrp_balance(address: str) -> float:
    """Get XRP balance for an address"""
    try:
        payload = {
            "method": "account_info",
            "params": [{
                "account": address,
                "ledger_index": "validated"
            }]
        }

        response = requests.post(XRP_RPC_URL, json=payload, timeout=10)

        if response.status_code == 200:
            result = response.json()
            if "result" in result and "account_data" in result["result"]:
                # Convert from drops to XRP
                drops = int(result["result"]["account_data"].get("Balance", 0))
                return drops / 1e6
        return 0.0
    except Exception as e:
        print(f"Error getting XRP balance: {e}")
        return 0.0


def get_btc_balance(address: str) -> float:
    """Get BTC balance for an address"""
    # This would require Bitcoin RPC access or a block explorer API
    # For now, return 0 as a placeholder
    # In production, integrate with Bitcoin RPC or Blockchair/Blockchain.com API
    return 0.0


def aggregate_user_balances(user_id: str, ledger: Dict, wbtc_ledger: Dict) -> Dict:
    """
    Aggregate all balances for a user across all chains

    Args:
        user_id: User identifier
        ledger: THR ledger
        wbtc_ledger: wBTC ledger

    Returns:
        Dict with all balances
    """
    profile = get_user_profile(user_id)

    if not profile:
        return {
            "error": "User profile not found",
            "balances": {}
        }

    balances = {
        "thronos": {},
        "native": {},
        "total_usd_value": 0.0  # Would need price oracle integration
    }

    # Thronos chain balances
    thr_addr = profile.get("thr_address", "")
    if thr_addr:
        balances["thronos"]["thr"] = float(ledger.get(thr_addr, 0.0))
        balances["thronos"]["wbtc"] = float(wbtc_ledger.get(thr_addr, 0.0))
        # Add other Thronos tokens here (wUSDC, wETH, etc.)

    # Native chain balances
    evm_addr = profile.get("evm_address", "")
    if evm_addr:
        balances["native"]["eth"] = get_eth_balance(evm_addr, ETH_RPC_URL)
        balances["native"]["bnb"] = get_eth_balance(evm_addr, BSC_RPC_URL)
        balances["native"]["matic"] = get_eth_balance(evm_addr, POLYGON_RPC_URL)
        balances["native"]["arb"] = get_eth_balance(evm_addr, ARBITRUM_RPC_URL)
        balances["native"]["op"] = get_eth_balance(evm_addr, OPTIMISM_RPC_URL)

    sol_addr = profile.get("sol_address", "")
    if sol_addr:
        balances["native"]["sol"] = get_solana_balance(sol_addr)

    xrp_addr = profile.get("xrp_address", "")
    if xrp_addr:
        balances["native"]["xrp"] = get_xrp_balance(xrp_addr)

    btc_addr = profile.get("btc_address", "")
    if btc_addr:
        balances["native"]["btc"] = get_btc_balance(btc_addr)

    return {
        "user_id": user_id,
        "balances": balances,
        "timestamp": int(os.times().elapsed)
    }


def preview_native_tx(
    chain: str,
    from_address: str,
    to_address: str,
    amount: float
) -> Dict:
    """
    Preview a native transaction (unsigned) for any supported chain

    Returns transaction preview with estimated gas/fees
    """
    result = {
        "chain": chain,
        "from": from_address,
        "to": to_address,
        "amount": amount,
        "unsigned_tx": None,
        "estimated_fee": 0.0,
        "is_valid": True,
        "error": None
    }

    try:
        if chain.lower() in ["eth", "bsc", "polygon", "arbitrum", "optimism"]:
            # EVM chains
            rpc_url = {
                "eth": ETH_RPC_URL,
                "bsc": BSC_RPC_URL,
                "polygon": POLYGON_RPC_URL,
                "arbitrum": ARBITRUM_RPC_URL,
                "optimism": OPTIMISM_RPC_URL
            }.get(chain.lower(), ETH_RPC_URL)

            # Get nonce
            nonce_result = evm_rpc_call(rpc_url, "eth_getTransactionCount", [from_address, "latest"])
            nonce = int(nonce_result, 16) if nonce_result else 0

            # Get gas price
            gas_price_result = evm_rpc_call(rpc_url, "eth_gasPrice", [])
            gas_price = int(gas_price_result, 16) if gas_price_result else 20000000000  # 20 gwei

            # Estimate gas limit
            gas_limit = 21000  # Standard transfer

            # Calculate fee
            fee_wei = gas_limit * gas_price
            result["estimated_fee"] = fee_wei / 1e18

            # Build unsigned transaction (simplified)
            result["unsigned_tx"] = {
                "nonce": nonce,
                "gasPrice": hex(gas_price),
                "gas": hex(gas_limit),
                "to": to_address,
                "value": hex(int(amount * 1e18)),
                "data": "0x",
                "chainId": 1  # Would need to be chain-specific
            }

        elif chain.lower() == "btc":
            # Bitcoin transaction preview
            result["estimated_fee"] = float(os.getenv("BTC_NETWORK_FEE", "0.0002"))
            result["unsigned_tx"] = {
                "note": "BTC transaction requires UTXO selection - use prepare_btc_withdrawal"
            }

        elif chain.lower() == "sol":
            # Solana transaction preview
            result["estimated_fee"] = 0.000005  # ~5000 lamports
            result["unsigned_tx"] = {
                "note": "Solana transaction - requires blockhash and signing"
            }

        elif chain.lower() == "xrp":
            # XRP transaction preview
            result["estimated_fee"] = 0.00001  # 10 drops
            result["unsigned_tx"] = {
                "TransactionType": "Payment",
                "Account": from_address,
                "Destination": to_address,
                "Amount": str(int(amount * 1e6)),  # Convert to drops
                "Fee": "12"  # 12 drops
            }

        else:
            result["is_valid"] = False
            result["error"] = f"Unsupported chain: {chain}"

    except Exception as e:
        result["is_valid"] = False
        result["error"] = str(e)

    return result


def broadcast_native_tx(chain: str, signed_tx_hex: str) -> Dict:
    """
    Broadcast a signed transaction to the specified chain

    Args:
        chain: Chain identifier (eth, bsc, btc, sol, xrp, etc.)
        signed_tx_hex: Signed transaction in hex/base64 format

    Returns:
        Dict with broadcast result and transaction hash
    """
    result = {
        "chain": chain,
        "success": False,
        "txid": None,
        "error": None
    }

    try:
        if chain.lower() in ["eth", "bsc", "polygon", "arbitrum", "optimism"]:
            # EVM chains
            rpc_url = {
                "eth": ETH_RPC_URL,
                "bsc": BSC_RPC_URL,
                "polygon": POLYGON_RPC_URL,
                "arbitrum": ARBITRUM_RPC_URL,
                "optimism": OPTIMISM_RPC_URL
            }.get(chain.lower(), ETH_RPC_URL)

            tx_hash = evm_rpc_call(rpc_url, "eth_sendRawTransaction", [signed_tx_hex])

            if tx_hash:
                result["success"] = True
                result["txid"] = tx_hash
            else:
                result["error"] = "Failed to broadcast transaction"

        elif chain.lower() == "btc":
            # Bitcoin - use BTC RPC if available
            result["error"] = "BTC broadcast not implemented - use btc_bridge_out module"

        elif chain.lower() == "sol":
            # Solana
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sendTransaction",
                "params": [signed_tx_hex, {"encoding": "base64"}]
            }

            response = requests.post(SOLANA_RPC_URL, json=payload, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if "result" in data:
                    result["success"] = True
                    result["txid"] = data["result"]
                else:
                    result["error"] = data.get("error", {}).get("message", "Unknown error")

        elif chain.lower() == "xrp":
            # XRP
            payload = {
                "method": "submit",
                "params": [{
                    "tx_blob": signed_tx_hex
                }]
            }

            response = requests.post(XRP_RPC_URL, json=payload, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if "result" in data and data["result"].get("engine_result") == "tesSUCCESS":
                    result["success"] = True
                    result["txid"] = data["result"].get("tx_json", {}).get("hash")
                else:
                    result["error"] = data.get("result", {}).get("engine_result_message", "Unknown error")

        else:
            result["error"] = f"Unsupported chain: {chain}"

    except Exception as e:
        result["error"] = str(e)

    return result
