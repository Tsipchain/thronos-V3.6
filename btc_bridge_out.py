"""
BTC Bridge-Out Utilities (PR-183)

Functions for calculating fees and preparing BTC withdrawals
from the hot wallet to user addresses.
"""

import os
from typing import Dict, Tuple
from decimal import Decimal, ROUND_DOWN

# Import environment variables
BTC_NETWORK_FEE = float(os.getenv("BTC_NETWORK_FEE", "0.0002"))
MIN_BTC_WITHDRAWAL = float(os.getenv("MIN_BTC_WITHDRAWAL", "0.001"))
MAX_BTC_WITHDRAWAL = float(os.getenv("MAX_BTC_WITHDRAWAL", "0.5"))
WITHDRAWAL_FEE_PERCENT = float(os.getenv("WITHDRAWAL_FEE_PERCENT", "0.5"))


def calculate_bridge_out_fees(
    btc_amount: float
) -> Dict[str, float]:
    """
    Calculate all fees for a BTC bridge-out withdrawal.

    Args:
        btc_amount: Amount of BTC user wants to withdraw

    Returns:
        Dict with:
        - gross_amount: Original requested amount
        - protocol_fee: Protocol fee (WITHDRAWAL_FEE_PERCENT)
        - treasury_fee: Additional treasury fee (if any)
        - network_fee: BTC network transaction fee
        - total_fees: Sum of all fees
        - net_amount: Amount user will actually receive
        - is_valid: Whether the withdrawal meets min/max limits
        - error: Error message if not valid
    """
    result = {
        "gross_amount": btc_amount,
        "protocol_fee": 0.0,
        "treasury_fee": 0.0,
        "network_fee": BTC_NETWORK_FEE,
        "total_fees": 0.0,
        "net_amount": 0.0,
        "is_valid": True,
        "error": None
    }

    # Validate limits
    if btc_amount < MIN_BTC_WITHDRAWAL:
        result["is_valid"] = False
        result["error"] = f"Amount below minimum: {MIN_BTC_WITHDRAWAL} BTC"
        return result

    if btc_amount > MAX_BTC_WITHDRAWAL:
        result["is_valid"] = False
        result["error"] = f"Amount exceeds maximum: {MAX_BTC_WITHDRAWAL} BTC"
        return result

    # Calculate protocol fee (percentage)
    protocol_fee_factor = WITHDRAWAL_FEE_PERCENT / 100.0
    result["protocol_fee"] = round(btc_amount * protocol_fee_factor, 8)

    # Treasury fee could be added here if needed
    # For now, treasury gets the protocol fee
    result["treasury_fee"] = 0.0

    # Total fees
    result["total_fees"] = round(
        result["protocol_fee"] + result["treasury_fee"] + result["network_fee"],
        8
    )

    # Net amount to user
    result["net_amount"] = round(btc_amount - result["total_fees"], 8)

    # Ensure net amount is still positive
    if result["net_amount"] <= 0:
        result["is_valid"] = False
        result["error"] = "Fees exceed withdrawal amount"

    return result


def prepare_btc_withdrawal(
    user_btc_address: str,
    btc_amount: float,
    hot_wallet_address: str
) -> Dict:
    """
    Prepare a BTC withdrawal transaction (unsigned).

    This function prepares the transaction data but does NOT sign or broadcast.
    The actual signing and broadcasting should be done by a separate secure service
    that has access to the hot wallet private key.

    Args:
        user_btc_address: Destination BTC address
        btc_amount: Amount to withdraw
        hot_wallet_address: Source hot wallet address

    Returns:
        Dict with transaction details:
        - outputs: List of outputs [(address, amount), ...]
        - fee_breakdown: Fee calculation details
        - total_input_needed: Total BTC needed from hot wallet
        - is_valid: Whether transaction is valid
        - error: Error message if not valid
    """
    # Calculate fees
    fees = calculate_bridge_out_fees(btc_amount)

    if not fees["is_valid"]:
        return {
            "is_valid": False,
            "error": fees["error"],
            "fee_breakdown": fees
        }

    # Prepare transaction outputs
    outputs = []

    # Output 1: Net amount to user
    if fees["net_amount"] > 0:
        outputs.append({
            "address": user_btc_address,
            "amount": fees["net_amount"],
            "type": "user_withdrawal"
        })

    # Output 2: Protocol/treasury fee (if any)
    treasury_address = os.getenv("BTC_TREASURY", "")
    if fees["protocol_fee"] > 0 and treasury_address:
        outputs.append({
            "address": treasury_address,
            "amount": fees["protocol_fee"],
            "type": "treasury_fee"
        })

    # Total input needed from hot wallet
    total_input_needed = btc_amount

    return {
        "is_valid": True,
        "outputs": outputs,
        "fee_breakdown": fees,
        "total_input_needed": total_input_needed,
        "hot_wallet_address": hot_wallet_address,
        "network_fee": fees["network_fee"],
        "estimated_total_cost": total_input_needed,
        "error": None
    }


def build_unsigned_btc_tx(
    inputs: list,
    outputs: list
) -> Dict:
    """
    Build an unsigned Bitcoin transaction.

    This is a stub - in production, you would use a library like
    bitcoin-python or bitcoinlib to construct the actual transaction.

    Args:
        inputs: List of UTXOs to spend
        outputs: List of outputs from prepare_btc_withdrawal

    Returns:
        Dict with unsigned transaction data
    """
    # STUB: In production, construct actual Bitcoin transaction
    # For now, just return a placeholder
    return {
        "version": 1,
        "inputs": inputs,
        "outputs": outputs,
        "locktime": 0,
        "unsigned_hex": None,  # Would contain actual unsigned tx hex
        "ready_to_sign": False,
        "note": "STUB: Implement actual Bitcoin transaction construction"
    }


def broadcast_btc_transaction(
    signed_tx_hex: str,
    btc_rpc_url: str = None
) -> Dict:
    """
    Broadcast a signed Bitcoin transaction to the network.

    This is a stub - in production, you would use Bitcoin RPC
    to broadcast the transaction.

    Args:
        signed_tx_hex: Signed transaction in hex format
        btc_rpc_url: Bitcoin RPC URL (optional, uses env var if not provided)

    Returns:
        Dict with broadcast result
    """
    # STUB: In production, broadcast via Bitcoin RPC
    return {
        "success": False,
        "txid": None,
        "error": "STUB: Implement actual Bitcoin transaction broadcast",
        "note": "Use Bitcoin RPC sendrawtransaction method"
    }


# Example usage
if __name__ == "__main__":
    # Test fee calculation
    print("Testing bridge-out fee calculation:")
    print()

    test_amounts = [0.001, 0.01, 0.1, 0.5, 1.0]

    for amount in test_amounts:
        fees = calculate_bridge_out_fees(amount)
        print(f"Withdrawal: {amount} BTC")
        print(f"  Valid: {fees['is_valid']}")
        if fees["is_valid"]:
            print(f"  Protocol fee: {fees['protocol_fee']} BTC ({WITHDRAWAL_FEE_PERCENT}%)")
            print(f"  Network fee: {fees['network_fee']} BTC")
            print(f"  Total fees: {fees['total_fees']} BTC")
            print(f"  Net to user: {fees['net_amount']} BTC")
        else:
            print(f"  Error: {fees['error']}")
        print()

    # Test withdrawal preparation
    print("Testing withdrawal preparation:")
    withdrawal = prepare_btc_withdrawal(
        user_btc_address="1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
        btc_amount=0.1,
        hot_wallet_address="1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2"
    )
    print(f"Valid: {withdrawal['is_valid']}")
    if withdrawal["is_valid"]:
        print(f"Outputs: {len(withdrawal['outputs'])}")
        for i, out in enumerate(withdrawal['outputs']):
            print(f"  Output {i+1}: {out['amount']} BTC to {out['address']} ({out['type']})")
    print()
