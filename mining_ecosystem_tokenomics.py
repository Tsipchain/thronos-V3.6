"""
Mining Ecosystem Tokenomics - Phase C5
=======================================

Complete Thronos mining schedule with halving, supply projections, and epoch management.

Parameters:
- Total Supply: 21,000,001 THR (Bitcoin + 1)
- Initial Block Reward: 1 THR
- Block Time: 2 minutes (120 seconds)
- Halving Interval: 210,000 blocks (~9.6 months per halving)
- Reward Distribution: 80% Miner, 5% Full Nodes, 5% Ecosystem

Halving Schedule (matching Bitcoin structure):
Epoch 0: 210,000 blocks × 1.0 THR = 210,000 THR
Epoch 1: 210,000 blocks × 0.5 THR = 105,000 THR
Epoch 2: 210,000 blocks × 0.25 THR = 52,500 THR
... (continues until supply exhausted at block 2,100,000)

Max supply reached: Block 2,100,000 (after ~4 years at 2-min blocks)

Author: Thronos Mining Economics
"""

import os
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DATA_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────────────────────
# THRONOS MINING PARAMETERS
# ─────────────────────────────────────────────────────────────

TOTAL_SUPPLY_THR = 21_000_001  # Bitcoin + 1
INITIAL_BLOCK_REWARD = 1.0     # 1 THR per block
BLOCK_TIME_MINUTES = 2         # 2 minutes per block
HALVING_INTERVAL = 210_000     # Blocks between halvings (like Bitcoin)
GENESIS_BLOCK_TIME = datetime(2024, 1, 1, 0, 0, 0)  # Assumed genesis

# Current reward distribution (to be updated to 80/5/5)
REWARD_DISTRIBUTION_V1 = {
    "miner": 0.80,         # 80% to miner
    "ai_pool": 0.10,       # 10% to AI pool
    "burn": 0.10           # 10% burned
}

REWARD_DISTRIBUTION_V2 = {
    "miner": 0.80,         # 80% to miner (ASIC/CPU/GPU)
    "full_nodes": 0.05,    # 5% to full node runners
    "ecosystem": 0.05      # 5% to ecosystem (Digital Legacy, notaries, IoT)
}


class EpochInfo:
    """Information about a mining epoch"""

    @staticmethod
    def get_epoch_for_block(block_height: int) -> int:
        """Get epoch number for a given block height"""
        return block_height // HALVING_INTERVAL

    @staticmethod
    def get_block_range_for_epoch(epoch: int) -> Tuple[int, int]:
        """Get block range for an epoch"""
        start = epoch * HALVING_INTERVAL
        end = start + HALVING_INTERVAL - 1
        return start, end

    @staticmethod
    def get_reward_for_block(block_height: int) -> float:
        """Get reward amount for a block height"""
        epoch = EpochInfo.get_epoch_for_block(block_height)
        return INITIAL_BLOCK_REWARD / (2 ** epoch)

    @staticmethod
    def get_total_supply_at_block(block_height: int) -> float:
        """Calculate total THR supply up to a block"""
        total = 0.0
        for epoch in range(100):  # Arbitrary large number
            start, end = EpochInfo.get_block_range_for_epoch(epoch)
            if start >= block_height:
                break

            actual_end = min(end, block_height - 1)
            blocks_in_epoch = actual_end - start + 1
            reward = EpochInfo.get_reward_for_block(start)
            total += blocks_in_epoch * reward

            if actual_end < end:
                break

        return total

    @staticmethod
    def get_max_supply_block() -> int:
        """Get block height where max supply (21,000,001 THR) is reached"""
        for block in range(0, 10_000_000, 100_000):
            supply = EpochInfo.get_total_supply_at_block(block)
            if supply >= TOTAL_SUPPLY_THR:
                # Binary search for exact block
                low, high = max(0, block - 100_000), block
                while low < high:
                    mid = (low + high) // 2
                    if EpochInfo.get_total_supply_at_block(mid) < TOTAL_SUPPLY_THR:
                        low = mid + 1
                    else:
                        high = mid
                return low
        return 2_100_000  # Approximate


class TimingCalculator:
    """Calculate timing information for halvings and supply projection"""

    @staticmethod
    def blocks_to_time(blocks: int) -> timedelta:
        """Convert blocks to time duration"""
        minutes = blocks * BLOCK_TIME_MINUTES
        return timedelta(minutes=minutes)

    @staticmethod
    def time_to_blocks(duration: timedelta) -> int:
        """Convert time duration to blocks"""
        minutes = duration.total_seconds() / 60
        return int(minutes / BLOCK_TIME_MINUTES)

    @staticmethod
    def get_halving_times() -> List[Dict]:
        """Get all halving times and details"""
        halvings = []

        for epoch in range(33):  # Up to 33 halvings (very small rewards after)
            start_block, end_block = EpochInfo.get_block_range_for_epoch(epoch)

            if start_block >= EpochInfo.get_max_supply_block():
                break

            reward = EpochInfo.get_reward_for_block(start_block)
            if reward <= 0:
                break

            time_to_halving = TimingCalculator.blocks_to_time(start_block)
            halving_date = GENESIS_BLOCK_TIME + time_to_halving

            supply_at_halving = EpochInfo.get_total_supply_at_block(start_block)

            duration_hours = (HALVING_INTERVAL * BLOCK_TIME_MINUTES) / 60

            halvings.append({
                "epoch": epoch,
                "halving_date": halving_date.isoformat(),
                "block_height": start_block,
                "reward_before": reward if epoch > 0 else INITIAL_BLOCK_REWARD,
                "reward_after": reward,
                "supply_at_halving": round(supply_at_halving, 2),
                "epoch_duration_hours": round(duration_hours, 2),
                "blocks_until_halving": HALVING_INTERVAL if epoch < 32 else 0
            })

        return halvings

    @staticmethod
    def get_supply_projection(num_years: int = 10) -> List[Dict]:
        """Project total supply over time"""
        projection = []

        for year in range(num_years + 1):
            blocks = TimingCalculator.time_to_blocks(timedelta(days=365 * year))
            supply = EpochInfo.get_total_supply_at_block(blocks)
            epoch = EpochInfo.get_epoch_for_block(blocks)

            if supply >= TOTAL_SUPPLY_THR:
                break

            projection.append({
                "year": year,
                "date": (GENESIS_BLOCK_TIME + timedelta(days=365 * year)).isoformat(),
                "block_height": blocks,
                "supply_thr": round(supply, 2),
                "percent_of_max": round((supply / TOTAL_SUPPLY_THR) * 100, 2),
                "current_epoch": epoch,
                "current_reward": round(EpochInfo.get_reward_for_block(blocks), 6)
            })

        return projection


@dataclass
class HalvingEvent:
    """Record of a halving event"""
    epoch: int
    block_height: int
    timestamp: str
    reward_before: float
    reward_after: float
    total_supply_at_event: float
    next_halving_blocks: int
    next_halving_date: str


class MiningEcosystemManager:
    """Manage mining reward distribution and ecosystem tracking"""

    def __init__(self, distribution_version: int = 2):
        """
        Initialize with reward distribution version
        1 = 80/10/10 (miner/AI/burn)
        2 = 80/5/5 (miner/nodes/ecosystem) - NEW
        """
        self.distribution_version = distribution_version
        self.distribution = (
            REWARD_DISTRIBUTION_V2 if distribution_version == 2
            else REWARD_DISTRIBUTION_V1
        )
        logger.info(f"🔨 Mining Ecosystem Manager initialized (v{distribution_version})")

    def get_reward_split(self, total_reward: float) -> Dict[str, float]:
        """Calculate reward split for a given total reward"""
        return {
            key: round(total_reward * pct, 6)
            for key, pct in self.distribution.items()
        }

    def get_current_epoch_info(self, current_block: int) -> Dict:
        """Get information about current epoch"""
        epoch = EpochInfo.get_epoch_for_block(current_block)
        start, end = EpochInfo.get_block_range_for_epoch(epoch)
        reward = EpochInfo.get_reward_for_block(current_block)

        blocks_in_epoch = current_block - start
        blocks_until_halving = HALVING_INTERVAL - blocks_in_epoch

        halving_time = TimingCalculator.blocks_to_time(blocks_until_halving)
        halving_date = datetime.utcnow() + halving_time

        return {
            "epoch": epoch,
            "block_range": f"{start:,} - {end:,}",
            "current_block": current_block,
            "blocks_until_halving": blocks_until_halving,
            "halving_date_estimate": halving_date.isoformat(),
            "current_reward": reward,
            "reward_distribution": self.get_reward_split(reward),
            "supply_circulating": round(EpochInfo.get_total_supply_at_block(current_block), 2),
            "supply_max": TOTAL_SUPPLY_THR
        }

    def get_stats(self) -> Dict:
        """Get mining ecosystem statistics"""
        # Assume we're tracking current chain height from somewhere
        # For now, return template with calculated values

        return {
            "total_supply_max": TOTAL_SUPPLY_THR,
            "initial_reward": INITIAL_BLOCK_REWARD,
            "block_time_minutes": BLOCK_TIME_MINUTES,
            "halving_interval_blocks": HALVING_INTERVAL,
            "halving_interval_months": round((HALVING_INTERVAL * BLOCK_TIME_MINUTES) / (60 * 24 * 30.44), 1),
            "distribution_version": self.distribution_version,
            "distribution": self.distribution,
            "max_supply_block": EpochInfo.get_max_supply_block(),
            "estimated_full_circulation_years": round(
                (EpochInfo.get_max_supply_block() * BLOCK_TIME_MINUTES) / (60 * 24 * 365.25), 2
            )
        }


# Global instance
_mining_manager: Optional[MiningEcosystemManager] = None


def initialize_mining_ecosystem(version: int = 2) -> MiningEcosystemManager:
    """Initialize global mining ecosystem manager"""
    global _mining_manager
    _mining_manager = MiningEcosystemManager(distribution_version=version)
    return _mining_manager


def get_mining_ecosystem() -> Optional[MiningEcosystemManager]:
    """Get global mining ecosystem manager"""
    return _mining_manager


# Utility functions for direct use
def get_halving_schedule() -> List[Dict]:
    """Get complete halving schedule"""
    return TimingCalculator.get_halving_times()


def get_supply_projection(years: int = 10) -> List[Dict]:
    """Get supply projection over years"""
    return TimingCalculator.get_supply_projection(years)


def get_current_epoch_info(block_height: int) -> Dict:
    """Get epoch info for a block height"""
    manager = get_mining_ecosystem()
    if manager:
        return manager.get_current_epoch_info(block_height)
    return {}
