#!/usr/bin/env python3
"""
Phase 7: Post-Mining Economy Transition (Year 30+)
===================================================

Hybrid PoW+PoS network security with perpetual incentives from:
- Transaction fees (50% validators, 30% miners, 10% nodes, 10% ecosystem)
- AI pool micro-rewards (0.1% annual of accumulated pool)
- Heat recovery mining bonuses
- Digital Legacy sustainable distribution

Author: Thronos Phase 7 Team
Status: DESIGN PHASE (Implementation Year ~27-30)
"""

import os
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DATA_DIR.mkdir(exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# PHASE 7: POST-MINING ECONOMY PARAMETERS
# ═══════════════════════════════════════════════════════════════

# Year 30 (approximately block 4.6M at 2-min blocks, 3.3-year halvings)
PHASE_7_ACTIVATION_YEAR = 30
PHASE_7_ACTIVATION_ESTIMATED_BLOCK = 4_600_000

# AI Pool accumulated (approximately 10% of 21M THR)
ACCUMULATED_AI_POOL = 2_100_000.0

# Transaction fee distribution (post-mining)
TRANSACTION_FEE_DISTRIBUTION = {
    "pos_validators": 0.50,      # 50% to PoS validators
    "pow_miners": 0.30,          # 30% to PoW miners (no block reward)
    "full_nodes": 0.10,          # 10% to full node runners
    "ecosystem": 0.10            # 10% to Digital Legacy pool
}

# AI Pool micro-reward (0.1% annual of accumulated pool)
AI_POOL_MICRO_REWARD_ANNUAL_PERCENT = 0.001
AI_POOL_ANNUAL_DISTRIBUTION = ACCUMULATED_AI_POOL * AI_POOL_MICRO_REWARD_ANNUAL_PERCENT

AI_POOL_DISTRIBUTION = {
    "pos_validators": 0.50,      # 50% to PoS validators
    "pow_miners": 0.30,          # 30% to PoW miners
    "full_nodes": 0.15,          # 15% to full node runners
    "ecosystem": 0.05            # 5% to Digital Legacy
}

# Minimum stake for PoS validator
MINIMUM_VALIDATOR_STAKE = 100.0  # 100 THR


# ═══════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════

class ValidatorStatus(Enum):
    """Validator operational status"""
    REGISTERED = "registered"
    ACTIVE = "active"
    INACTIVE = "inactive"
    SLASHED = "slashed"
    UNBONDING = "unbonding"


@dataclass
class PoSValidator:
    """Proof-of-Stake validator registration"""
    address: str
    staked_amount: float                    # Minimum 100 THR
    reputation_score: float = 0.0           # 0.0-1.0 from Digital Legacy
    uptime_percentage: float = 100.0        # Validator uptime tracking
    heat_recovery_participation: bool = False
    blocks_proposed: int = 0
    blocks_slashed: int = 0
    registration_block: int = 0
    registration_timestamp: str = ""
    status: ValidatorStatus = ValidatorStatus.REGISTERED
    metadata: Dict = field(default_factory=dict)

    def is_eligible(self) -> bool:
        """Check if validator can participate in consensus"""
        return (
            self.status in [ValidatorStatus.ACTIVE, ValidatorStatus.REGISTERED]
            and self.staked_amount >= MINIMUM_VALIDATOR_STAKE
            and self.reputation_score >= 0.5
        )

    def voting_power(self, total_stake: float) -> float:
        """Calculate validator's voting power (stake-weighted)"""
        if total_stake <= 0:
            return 0.0
        return self.staked_amount / total_stake


@dataclass
class TransactionFeePool:
    """Daily transaction fee accumulation"""
    date: str
    total_fees_collected: float = 0.0
    block_count: int = 0
    average_fee_per_block: float = 0.0

    distribution_plan: Dict[str, float] = field(default_factory=dict)
    timestamp: str = ""


@dataclass
class HeatRecoveryBonus:
    """Heat recovery mining incentive"""
    miner_address: str
    energy_recovered_kwh: float              # Joules → kWh
    bonus_tier: int                          # 1-3 based on efficiency
    bonus_percentage: float                  # 5-20% depending on tier
    bonus_amount_thr: float                  # Calculated reward
    timestamp: str = ""
    verified: bool = False


@dataclass
class ValidatorReward:
    """Per-epoch validator reward calculation"""
    validator_address: str
    epoch: int
    stake_proportion: float                  # (validator_stake / total_stake)
    transaction_fee_share: float
    ai_pool_share: float
    heat_recovery_bonus: float = 0.0
    total_reward: float = 0.0
    timestamp: str = ""


# ═══════════════════════════════════════════════════════════════
# PHASE 7 MANAGER
# ═══════════════════════════════════════════════════════════════

class Phase7PostMiningEconomyManager:
    """Manage post-mining economy with PoS validators and perpetual incentives"""

    def __init__(self):
        self.validators_file = DATA_DIR / "pos_validators.json"
        self.fee_pool_file = DATA_DIR / "transaction_fee_pool.json"
        self.validator_rewards_file = DATA_DIR / "validator_rewards.json"
        self.heat_recovery_file = DATA_DIR / "heat_recovery_bonuses.json"

        logger.info("⚙️ Phase 7 Post-Mining Economy Manager initialized")

    def register_validator(self, address: str, stake: float,
                          heat_recovery: bool = False) -> Dict:
        """Register a new PoS validator"""
        if stake < MINIMUM_VALIDATOR_STAKE:
            return {"error": f"Minimum stake is {MINIMUM_VALIDATOR_STAKE} THR"}

        validator = PoSValidator(
            address=address,
            staked_amount=stake,
            heat_recovery_participation=heat_recovery,
            registration_timestamp=datetime.utcnow().isoformat(),
            registration_block=0  # Would be set by server
        )

        validators = self._load_validators()
        if address in validators:
            return {"error": "Validator already registered"}

        validators[address] = asdict(validator)
        self._save_validators(validators)

        logger.info(f"✅ Validator {address} registered with {stake} THR")
        return {
            "status": "registered",
            "address": address,
            "stake": stake,
            "heat_recovery": heat_recovery
        }

    def calculate_transaction_fee_distribution(self, total_fees: float) -> Dict:
        """Calculate distribution of transaction fees"""
        distribution = {}
        for role, percentage in TRANSACTION_FEE_DISTRIBUTION.items():
            distribution[role] = round(total_fees * percentage, 6)

        distribution["total_allocated"] = sum(distribution.values())
        return distribution

    def calculate_ai_pool_micro_reward(self) -> Dict:
        """Calculate annual AI pool micro-reward distribution"""
        annual_reward = AI_POOL_ANNUAL_DISTRIBUTION
        distribution = {}

        for role, percentage in AI_POOL_DISTRIBUTION.items():
            distribution[role] = round(annual_reward * percentage, 6)

        distribution["total_annual"] = annual_reward
        distribution["daily_average"] = round(annual_reward / 365.25, 6)
        return distribution

    def calculate_validator_reward(self, validator: Dict, total_stake: float,
                                   daily_fees: float) -> ValidatorReward:
        """Calculate reward for a single validator"""
        stake_prop = validator["staked_amount"] / total_stake if total_stake > 0 else 0.0

        # Transaction fee share
        fee_share = (
            daily_fees *
            TRANSACTION_FEE_DISTRIBUTION["pos_validators"] *
            stake_prop
        )

        # AI pool micro-reward share
        daily_ai_reward = AI_POOL_ANNUAL_DISTRIBUTION / 365.25
        ai_share = (
            daily_ai_reward *
            AI_POOL_DISTRIBUTION["pos_validators"] *
            stake_prop
        )

        total = round(fee_share + ai_share, 6)

        reward = ValidatorReward(
            validator_address=validator["address"],
            epoch=0,  # Would be actual epoch
            stake_proportion=stake_prop,
            transaction_fee_share=round(fee_share, 6),
            ai_pool_share=round(ai_share, 6),
            total_reward=total,
            timestamp=datetime.utcnow().isoformat()
        )

        return reward

    def apply_heat_recovery_bonus(self, miner_address: str,
                                  energy_kwh: float) -> Dict:
        """Apply heat recovery bonus to miner rewards"""
        # Efficiency tiers (example)
        if energy_kwh >= 50:
            tier = 3
            bonus_pct = 0.20  # 20% bonus
        elif energy_kwh >= 25:
            tier = 2
            bonus_pct = 0.15  # 15% bonus
        else:
            tier = 1
            bonus_pct = 0.05  # 5% bonus

        bonus = HeatRecoveryBonus(
            miner_address=miner_address,
            energy_recovered_kwh=energy_kwh,
            bonus_tier=tier,
            bonus_percentage=bonus_pct,
            bonus_amount_thr=0.0,  # Would be calculated from base reward
            timestamp=datetime.utcnow().isoformat(),
            verified=False
        )

        return asdict(bonus)

    def get_network_stats(self) -> Dict:
        """Get Phase 7 network statistics"""
        validators = self._load_validators()
        active_validators = [
            v for v in validators.values()
            if v["status"] in ["registered", "active"]
        ]

        total_stake = sum(v["staked_amount"] for v in active_validators)

        return {
            "active_validators": len(active_validators),
            "total_stake": round(total_stake, 6),
            "average_stake": round(total_stake / len(active_validators), 6) if active_validators else 0,
            "ai_pool_accumulated": ACCUMULATED_AI_POOL,
            "ai_pool_annual_micro_reward": AI_POOL_ANNUAL_DISTRIBUTION,
            "transaction_fee_distribution": TRANSACTION_FEE_DISTRIBUTION,
            "timestamp": datetime.utcnow().isoformat()
        }

    def _load_validators(self) -> Dict:
        """Load validators from file"""
        if self.validators_file.exists():
            return json.loads(self.validators_file.read_text())
        return {}

    def _save_validators(self, validators: Dict):
        """Save validators to file"""
        self.validators_file.write_text(json.dumps(validators, indent=2))


# Global instance
_phase_7_manager: Optional[Phase7PostMiningEconomyManager] = None


def initialize_phase_7() -> Phase7PostMiningEconomyManager:
    """Initialize Phase 7 manager"""
    global _phase_7_manager
    _phase_7_manager = Phase7PostMiningEconomyManager()
    return _phase_7_manager


def get_phase_7_manager() -> Optional[Phase7PostMiningEconomyManager]:
    """Get Phase 7 manager instance"""
    return _phase_7_manager


# ═══════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def estimate_phase_7_activation_date() -> Dict:
    """Estimate when Phase 7 will activate based on block time"""
    from datetime import datetime, timedelta

    # 877,800 blocks per halving at 2 minutes each
    # ~3.3333 years per epoch
    # After ~8.3 epochs = 30 years

    genesis = datetime(2023, 1, 1, 0, 0, 0)
    phase_7_date = genesis + timedelta(days=365.25 * PHASE_7_ACTIVATION_YEAR)

    return {
        "estimated_activation_date": phase_7_date.isoformat(),
        "estimated_block_height": PHASE_7_ACTIVATION_ESTIMATED_BLOCK,
        "years_from_genesis": PHASE_7_ACTIVATION_YEAR,
        "timestamp": datetime.utcnow().isoformat()
    }
