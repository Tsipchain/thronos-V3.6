"""Deploy FeverHistory.sol to the Thronos chain.

Usage:
    export THRONOS_RPC_URL=http://your-node:8545
    export DEPLOYER_PRIVATE_KEY=0x...
    python deploy.py
"""
import os
import json
from pathlib import Path
from web3 import Web3
from web3.middleware import geth_poa_middleware

RPC_URL     = os.environ["THRONOS_RPC_URL"]
PRIVATE_KEY = os.environ["DEPLOYER_PRIVATE_KEY"]

# Expects contract already compiled; provide ABI + bytecode paths
# or run: solc --abi --bin FeverHistory.sol -o build/
BUILD_DIR = Path(__file__).parent / "build"


def deploy():
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    assert w3.is_connected(), "Cannot connect to node"

    acct = w3.eth.account.from_key(PRIVATE_KEY)
    print(f"Deploying from: {acct.address}")
    print(f"Balance: {w3.eth.get_balance(acct.address)} wei")

    abi      = json.loads((BUILD_DIR / "FeverHistory.abi").read_text())
    bytecode = (BUILD_DIR / "FeverHistory.bin").read_text().strip()

    Contract = w3.eth.contract(abi=abi, bytecode=bytecode)

    tx = Contract.constructor().build_transaction({
        "from":     acct.address,
        "nonce":    w3.eth.get_transaction_count(acct.address),
        "gas":      2_000_000,
        "gasPrice": w3.eth.gas_price,
    })

    signed  = acct.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    print(f"Tx sent: {tx_hash.hex()}")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    print(f"Contract deployed at: {receipt.contractAddress}")
    print(f"Set FEVER_CONTRACT_ADDRESS={receipt.contractAddress} in your .env")
    return receipt.contractAddress


if __name__ == "__main__":
    deploy()
