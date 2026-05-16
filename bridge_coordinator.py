"""
Multi-Chain Bridge Coordinator
Manages cross-chain token swaps and liquidity between Thronos and:
- Bitcoin (BTC)
- Ethereum (ETH)
- Solana (SOL)
- XRP Ledger (XRP)
- Polkadot (DOT)
- Cosmos (ATOM)

Philosophy: One blockchain cannot protect humanity alone.
Bridge technology enables value to flow to where it's needed most.
"""

import json
import time
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum
import uuid


class ChainType(Enum):
    """Supported blockchain networks"""
    BITCOIN = "bitcoin"
    ETHEREUM = "ethereum"
    SOLANA = "solana"
    XRP_LEDGER = "xrp"
    POLKADOT = "polkadot"
    COSMOS = "cosmos"
    THRONOS = "thronos"


class BridgeStatus(Enum):
    """Status of a bridge transaction"""
    INITIATED = "initiated"           # User initiated swap
    SOURCE_CONFIRMED = "source_confirmed"  # Confirmed on source chain
    LOCKED = "locked"                 # Tokens locked/burned on source
    MINTED = "minted"                 # Tokens minted on destination
    CONFIRMED = "confirmed"           # Both sides confirmed
    FAILED = "failed"                 # Transaction failed
    ROLLED_BACK = "rolled_back"       # Reverted on both chains


class SwapDirection(Enum):
    """Direction of token flow"""
    TO_THRONOS = "to_thronos"         # External chain → Thronos
    FROM_THRONOS = "from_thronos"     # Thronos → External chain


class BridgeTransaction:
    """Represents a single cross-chain transaction"""

    def __init__(self, source_chain: ChainType, destination_chain: ChainType,
                 source_address: str, destination_address: str,
                 amount: float):
        self.tx_id = str(uuid.uuid4())
        self.timestamp = int(time.time())
        self.source_chain = source_chain
        self.destination_chain = destination_chain
        self.source_address = source_address
        self.destination_address = destination_address
        self.amount = amount
        self.status = BridgeStatus.INITIATED
        self.source_tx_hash = ""
        self.destination_tx_hash = ""
        self.confirmation_count = 0
        self.source_confirmations_required = self._get_required_confirmations(source_chain)
        self.destination_confirmations_required = self._get_required_confirmations(destination_chain)
        self.required_confirmations = self.source_confirmations_required
        self.fee_amount = 0.0
        self.rate_used = 1.0
        self.received_amount = amount
        self.error_message = ""
        self.created_timestamp = int(time.time())
        self.updated_timestamp = int(time.time())

    def to_dict(self) -> Dict:
        return {
            "tx_id": self.tx_id,
            "timestamp": self.timestamp,
            "source_chain": self.source_chain.value,
            "destination_chain": self.destination_chain.value,
            "source_address": self.source_address,
            "destination_address": self.destination_address,
            "amount": self.amount,
            "status": self.status.value,
            "source_tx_hash": self.source_tx_hash,
            "destination_tx_hash": self.destination_tx_hash,
            "confirmation_count": self.confirmation_count,
            "required_confirmations": self.required_confirmations,
            "fee_amount": self.fee_amount,
            "rate_used": self.rate_used,
            "received_amount": self.received_amount,
            "error_message": self.error_message,
            "created_timestamp": self.created_timestamp,
            "updated_timestamp": self.updated_timestamp
        }

    @staticmethod
    def _get_required_confirmations(chain: ChainType) -> int:
        """Get required confirmations for finality on different chains"""
        confirmations = {
            ChainType.BITCOIN: 12,
            ChainType.ETHEREUM: 30,
            ChainType.SOLANA: 30,
            ChainType.XRP_LEDGER: 1,
            ChainType.POLKADOT: 15,
            ChainType.COSMOS: 1,
            ChainType.THRONOS: 100  # Thronos requires more confirmations for security
        }
        return confirmations.get(chain, 10)


class LiquidityPool:
    """Manages liquidity reserves for bridge operations"""

    def __init__(self, pool_id: str, base_chain: ChainType, paired_chain: ChainType):
        self.pool_id = pool_id
        self.base_chain = base_chain
        self.paired_chain = paired_chain
        self.reserve_base = 0.0
        self.reserve_paired = 0.0
        self.total_liquidity_shares = 0.0
        self.providers: Dict[str, float] = {}  # Address → shares
        self.creation_timestamp = int(time.time())
        self.swap_volume_24h = 0.0
        self.total_swap_volume = 0.0
        self.slippage_fee_bps = 25  # 0.25% fee

    def deposit_liquidity(self, provider_address: str, base_amount: float,
                         paired_amount: float) -> Tuple[float, float]:
        """
        Add liquidity to the pool.

        Args:
            provider_address: Address of liquidity provider
            base_amount: Amount in base chain token
            paired_amount: Amount in paired chain token

        Returns:
            shares: Amount of liquidity shares issued
        """
        if base_amount <= 0 or paired_amount <= 0:
            raise ValueError("Amounts must be positive")

        # Calculate share percentage
        total_reserve_value = self.reserve_base + self.reserve_paired
        deposit_value = base_amount + paired_amount

        if total_reserve_value == 0:
            # First deposit
            shares = (base_amount + paired_amount) / 2
        else:
            # Pro-rata shares
            shares = (deposit_value / total_reserve_value) * self.total_liquidity_shares

        # Update reserves
        self.reserve_base += base_amount
        self.reserve_paired += paired_amount
        self.total_liquidity_shares += shares

        # Track provider
        if provider_address not in self.providers:
            self.providers[provider_address] = 0
        self.providers[provider_address] += shares

        return shares, deposit_value

    def withdraw_liquidity(self, provider_address: str, share_amount: float) -> Tuple[float, float]:
        """
        Withdraw liquidity from the pool.

        Args:
            provider_address: Address of liquidity provider
            share_amount: Amount of shares to burn

        Returns:
            base_amount, paired_amount: Tokens returned to provider
        """
        if provider_address not in self.providers:
            raise ValueError(f"Provider {provider_address} not in pool")

        if self.providers[provider_address] < share_amount:
            raise ValueError("Insufficient shares")

        # Calculate proportional return
        share_ratio = share_amount / self.total_liquidity_shares
        base_amount = self.reserve_base * share_ratio
        paired_amount = self.reserve_paired * share_ratio

        # Update reserves
        self.reserve_base -= base_amount
        self.reserve_paired -= paired_amount
        self.total_liquidity_shares -= share_amount

        # Update provider
        self.providers[provider_address] -= share_amount

        return base_amount, paired_amount

    def get_exchange_rate(self) -> float:
        """Get current exchange rate (paired per base)"""
        if self.reserve_base == 0:
            return 1.0
        return self.reserve_paired / self.reserve_base

    def to_dict(self) -> Dict:
        return {
            "pool_id": self.pool_id,
            "base_chain": self.base_chain.value,
            "paired_chain": self.paired_chain.value,
            "reserve_base": round(self.reserve_base, 8),
            "reserve_paired": round(self.reserve_paired, 8),
            "exchange_rate": round(self.get_exchange_rate(), 8),
            "total_liquidity_shares": round(self.total_liquidity_shares, 8),
            "swap_volume_24h": round(self.swap_volume_24h, 8),
            "total_swap_volume": round(self.total_swap_volume, 8),
            "slippage_fee_bps": self.slippage_fee_bps,
            "provider_count": len([p for p in self.providers.values() if p > 0])
        }


class BridgeCoordinator:
    """Main coordinator for all cross-chain bridge operations"""

    # Fee structure (in basis points, 100 bps = 1%)
    BASE_BRIDGE_FEE = 25  # 0.25%
    EMERGENCY_FEE = 50    # 0.5% during high volatility

    def __init__(self):
        self.transactions: Dict[str, BridgeTransaction] = {}
        self.pools: Dict[str, LiquidityPool] = {}
        self.validators: List[str] = []
        self.paused = False
        self.total_volume_processed = 0.0
        self.total_fees_collected = 0.0

        # Initialize liquidity pools for each pair
        self._initialize_pools()

    def _initialize_pools(self):
        """Create liquidity pools for all supported chain pairs"""
        chain_pairs = [
            (ChainType.BITCOIN, ChainType.THRONOS),
            (ChainType.ETHEREUM, ChainType.THRONOS),
            (ChainType.SOLANA, ChainType.THRONOS),
            (ChainType.XRP_LEDGER, ChainType.THRONOS),
            (ChainType.POLKADOT, ChainType.THRONOS),
            (ChainType.COSMOS, ChainType.THRONOS),
        ]

        for source, dest in chain_pairs:
            pool_id = f"{source.value}_{dest.value}"
            self.pools[pool_id] = LiquidityPool(pool_id, source, dest)

    def initiate_bridge_transaction(self, source_chain: ChainType,
                                   destination_chain: ChainType,
                                   source_address: str,
                                   destination_address: str,
                                   amount: float) -> str:
        """
        Initiate a new bridge transaction.

        Args:
            source_chain: Blockchain where funds originate
            destination_chain: Blockchain where funds arrive
            source_address: Sender's address
            destination_address: Recipient's address
            amount: Amount to transfer

        Returns:
            tx_id: Transaction ID for tracking
        """
        if self.paused:
            raise ValueError("Bridge is temporarily paused")

        if amount <= 0:
            raise ValueError("Amount must be positive")

        # Validate addresses (basic check)
        if not self._validate_address(source_address, source_chain):
            raise ValueError(f"Invalid address for {source_chain.value}")

        if not self._validate_address(destination_address, destination_chain):
            raise ValueError(f"Invalid address for {destination_chain.value}")

        # Create transaction
        tx = BridgeTransaction(
            source_chain=source_chain,
            destination_chain=destination_chain,
            source_address=source_address,
            destination_address=destination_address,
            amount=amount
        )

        # Calculate fee
        tx.fee_amount = self._calculate_bridge_fee(amount)
        tx.received_amount = amount - tx.fee_amount

        # Store transaction
        self.transactions[tx.tx_id] = tx

        return tx.tx_id

    def confirm_source_transaction(self, tx_id: str, source_tx_hash: str,
                                   confirmation_count: int) -> bool:
        """
        Confirm that transaction was received on source chain.

        Args:
            tx_id: Transaction ID
            source_tx_hash: Transaction hash on source chain
            confirmation_count: Current confirmation count

        Returns:
            success: True if confirmed
        """
        if tx_id not in self.transactions:
            raise ValueError(f"Transaction {tx_id} not found")

        tx = self.transactions[tx_id]
        tx.source_tx_hash = source_tx_hash
        tx.confirmation_count = confirmation_count

        if confirmation_count >= tx.required_confirmations:
            tx.status = BridgeStatus.SOURCE_CONFIRMED
            return True

        return False

    def lock_source_tokens(self, tx_id: str) -> bool:
        """
        Lock or burn tokens on source chain.

        Args:
            tx_id: Transaction ID

        Returns:
            success: True if locked
        """
        if tx_id not in self.transactions:
            raise ValueError(f"Transaction {tx_id} not found")

        tx = self.transactions[tx_id]

        if tx.status != BridgeStatus.SOURCE_CONFIRMED:
            raise ValueError("Source not confirmed yet")

        tx.status = BridgeStatus.LOCKED
        return True

    def mint_destination_tokens(self, tx_id: str, destination_tx_hash: str) -> bool:
        """
        Mint tokens on destination chain.

        Args:
            tx_id: Transaction ID
            destination_tx_hash: Transaction hash on destination chain

        Returns:
            success: True if minted
        """
        if tx_id not in self.transactions:
            raise ValueError(f"Transaction {tx_id} not found")

        tx = self.transactions[tx_id]

        if tx.status != BridgeStatus.LOCKED:
            raise ValueError("Source tokens not locked yet")

        tx.destination_tx_hash = destination_tx_hash
        tx.status = BridgeStatus.MINTED
        return True

    def confirm_destination_transaction(self, tx_id: str, confirmation_count: int) -> bool:
        """
        Confirm transaction on destination chain.

        Args:
            tx_id: Transaction ID
            confirmation_count: Current confirmation count

        Returns:
            success: True if confirmed
        """
        if tx_id not in self.transactions:
            raise ValueError(f"Transaction {tx_id} not found")

        tx = self.transactions[tx_id]

        if tx.status != BridgeStatus.MINTED:
            raise ValueError("Tokens not minted yet")

        if confirmation_count >= tx.destination_confirmations_required:
            tx.status = BridgeStatus.CONFIRMED
            self.total_volume_processed += tx.amount
            self.total_fees_collected += tx.fee_amount
            return True

        return False

    def get_transaction_status(self, tx_id: str) -> Optional[Dict]:
        """Get status of a bridge transaction"""
        if tx_id not in self.transactions:
            return None
        return self.transactions[tx_id].to_dict()

    def get_transactions_by_address(self, address: str) -> List[Dict]:
        """Get all transactions for an address"""
        matching = [
            tx.to_dict() for tx in self.transactions.values()
            if tx.source_address == address or tx.destination_address == address
        ]
        return matching

    def get_pool_info(self, base_chain: ChainType, paired_chain: ChainType) -> Optional[Dict]:
        """Get liquidity pool information"""
        pool_id = f"{base_chain.value}_{paired_chain.value}"
        if pool_id not in self.pools:
            return None
        return self.pools[pool_id].to_dict()

    def add_liquidity(self, base_chain: ChainType, paired_chain: ChainType,
                     provider_address: str, base_amount: float,
                     paired_amount: float) -> Dict:
        """
        Add liquidity to a pool.

        Returns:
            result: Dict with shares issued and pool state
        """
        pool_id = f"{base_chain.value}_{paired_chain.value}"
        if pool_id not in self.pools:
            raise ValueError(f"Pool {pool_id} not found")

        pool = self.pools[pool_id]
        shares, deposit_value = pool.deposit_liquidity(provider_address, base_amount, paired_amount)

        return {
            "pool_id": pool_id,
            "shares_issued": round(shares, 8),
            "deposit_value": round(deposit_value, 8),
            "provider_address": provider_address
        }

    def remove_liquidity(self, base_chain: ChainType, paired_chain: ChainType,
                        provider_address: str, share_amount: float) -> Dict:
        """Remove liquidity from a pool"""
        pool_id = f"{base_chain.value}_{paired_chain.value}"
        if pool_id not in self.pools:
            raise ValueError(f"Pool {pool_id} not found")

        pool = self.pools[pool_id]
        base_amt, paired_amt = pool.withdraw_liquidity(provider_address, share_amount)

        return {
            "pool_id": pool_id,
            "base_amount": round(base_amt, 8),
            "paired_amount": round(paired_amt, 8),
            "shares_burned": round(share_amount, 8)
        }

    def get_bridge_stats(self) -> Dict:
        """Get overall bridge statistics"""
        confirmed_txs = len([tx for tx in self.transactions.values()
                            if tx.status == BridgeStatus.CONFIRMED])

        return {
            "total_transactions": len(self.transactions),
            "confirmed_transactions": confirmed_txs,
            "pending_transactions": len([tx for tx in self.transactions.values()
                                        if tx.status not in [BridgeStatus.CONFIRMED, BridgeStatus.FAILED]]),
            "failed_transactions": len([tx for tx in self.transactions.values()
                                       if tx.status == BridgeStatus.FAILED]),
            "total_volume_processed": round(self.total_volume_processed, 8),
            "total_fees_collected": round(self.total_fees_collected, 8),
            "active_pools": len([p for p in self.pools.values() if p.total_liquidity_shares > 0]),
            "bridge_paused": self.paused
        }

    def pause_bridge(self, reason: str = "") -> bool:
        """Emergency pause of bridge operations"""
        self.paused = True
        return True

    def resume_bridge(self) -> bool:
        """Resume bridge operations"""
        self.paused = False
        return True

    def _calculate_bridge_fee(self, amount: float) -> float:
        """Calculate bridge fee"""
        fee_bps = self.EMERGENCY_FEE if self._is_high_volatility() else self.BASE_BRIDGE_FEE
        return (amount * fee_bps) / 10000

    def _is_high_volatility(self) -> bool:
        """Check if market is in high volatility state"""
        # In production: Check against actual price feeds
        return False

    def _validate_address(self, address: str, chain: ChainType) -> bool:
        """Validate address format for specific chain"""
        # Basic validation - in production this would be more thorough
        if not address or len(address) < 5:
            return False
        # For now, accept all addresses that are non-empty and at least 5 chars
        # In production, implement strict validation per chain
        return True


class BridgeValidator:
    """Validates bridge transactions and ensures security"""

    def __init__(self, coordinator: BridgeCoordinator):
        self.coordinator = coordinator
        self.validation_history: List[Dict] = []

    def validate_transaction(self, tx_id: str) -> Tuple[bool, str]:
        """
        Validate a bridge transaction.

        Returns:
            is_valid, reason: Validation result and message
        """
        if tx_id not in self.coordinator.transactions:
            return False, "Transaction not found"

        tx = self.coordinator.transactions[tx_id]

        # Validate amount
        if tx.amount <= 0:
            return False, "Invalid amount"

        # Validate status progression
        if tx.status == BridgeStatus.INITIATED:
            if not tx.source_tx_hash:
                return False, "Source transaction not confirmed"
        elif tx.status == BridgeStatus.SOURCE_CONFIRMED:
            if tx.confirmation_count < tx.required_confirmations:
                return False, f"Insufficient confirmations: {tx.confirmation_count}/{tx.required_confirmations}"
        elif tx.status == BridgeStatus.LOCKED:
            if not tx.destination_tx_hash:
                return False, "Destination transaction not initiated"
        elif tx.status == BridgeStatus.MINTED:
            pass  # Awaiting destination confirmations

        return True, "Valid"

    def log_validation(self, tx_id: str, is_valid: bool, reason: str):
        """Log validation result"""
        self.validation_history.append({
            "tx_id": tx_id,
            "timestamp": int(time.time()),
            "is_valid": is_valid,
            "reason": reason
        })
