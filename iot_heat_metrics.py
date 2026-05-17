#!/usr/bin/env python3
"""
Phase 6: IoT Heat Metrics Framework
====================================

Decentralized waste heat recovery system for ASIC mining operations.
Miners report heat metrics → earn THR bonuses → incentivize efficiency.

Author: Thronos Phase 6 Team
Status: Implementation Phase
"""

import os
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DATA_DIR.mkdir(exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# PHASE 6: IOT HEAT METRICS FRAMEWORK
# ═══════════════════════════════════════════════════════════════

# Energy reference prices (global market average 2024)
ENERGY_PRICE_USD_PER_KWH = {
    "industrial": 0.08,
    "commercial": 0.12,
    "residential": 0.15,
    "peak": 0.25,
}

# Conversion constants
JOULES_PER_KWH = 3_600_000
BTU_PER_JOULE = 0.000947817


class HeatRewardTier(Enum):
    """Heat recovery efficiency reward tiers"""
    TIER_1 = {
        "name": "Baseline Recovery",
        "recovery_min": 5,
        "recovery_max": 10,
        "bonus_percentage": 0.05,
        "description": "Basic waste heat capture (5% bonus)"
    }
    TIER_2 = {
        "name": "Standard Recovery",
        "recovery_min": 10,
        "recovery_max": 15,
        "bonus_percentage": 0.15,
        "description": "Moderate heat recovery system (15% bonus)"
    }
    TIER_3 = {
        "name": "Advanced Recovery",
        "recovery_min": 15,
        "recovery_max": 25,
        "bonus_percentage": 0.25,
        "description": "High-efficiency heat capture (25% bonus)"
    }
    TIER_4 = {
        "name": "Elite Recovery",
        "recovery_min": 25,
        "recovery_max": 100,
        "bonus_percentage": 0.40,
        "description": "Industrial-grade heat recovery (40% bonus)"
    }


class UseCase(Enum):
    """Heat recovery application types"""
    SPACE_HEATING = {
        "name": "Space Heating",
        "bonus": 0.10,
        "reliability": 0.95,
        "seasonal_factor": 0.5
    }
    GREENHOUSE = {
        "name": "Greenhouse Farming",
        "bonus": 0.15,
        "reliability": 0.98,
        "seasonal_factor": 1.0
    }
    LIVESTOCK = {
        "name": "Livestock Operations",
        "bonus": 0.12,
        "reliability": 0.90,
        "seasonal_factor": 0.7
    }
    AQUACULTURE = {
        "name": "Fish Farming",
        "bonus": 0.18,
        "reliability": 0.99,
        "seasonal_factor": 1.0
    }
    DESALINATION = {
        "name": "Water Treatment",
        "bonus": 0.20,
        "reliability": 0.99,
        "seasonal_factor": 1.0
    }


# ═══════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════

@dataclass
class MinerHeatMetrics:
    """Real-time heat metrics from mining operation"""
    miner_address: str
    timestamp: str  # ISO 8601

    # Hardware
    device_type: str  # "ASIC_S19", "CPU", "GPU"
    device_count: int
    power_consumption_watts: float

    # Temperature
    ambient_temp_celsius: float
    inlet_temp_celsius: float
    outlet_temp_celsius: float

    # Heat recovery
    airflow_cfm: float  # Cubic feet per minute
    heat_recovered_joules: float
    heat_recovered_kwh: float = 0.0

    # Efficiency
    pue_ratio: float  # Power Usage Effectiveness
    recovery_percentage: float  # 0-100

    # Location
    farm_location: str
    use_case: str

    # Verification
    verified: bool = False
    verification_signature: str = ""
    block_height: int = 0

    def __post_init__(self):
        """Calculate derived fields"""
        if self.heat_recovered_joules > 0 and self.heat_recovered_kwh == 0:
            self.heat_recovered_kwh = self.heat_recovered_joules / JOULES_PER_KWH


@dataclass
class HeatRewardPool:
    """Accumulated heat recovery rewards for miner"""
    miner_address: str
    current_block_reward: float  # From Phase C5 (8 THR)
    heat_recovery_kwh_day: float
    heat_bonus_percentage: float
    heat_bonus_amount: float

    # Energy economics
    energy_value_usd_per_kwh: float = 0.08
    heat_value_usd: float = 0.0
    thr_price_usd: float = 0.0001
    heat_equivalent_thr: float = 0.0

    # Total
    base_mining_reward: float = 8.0
    heat_bonus_reward: float = 0.0
    total_reward: float = 0.0

    timestamp: str = ""

    def calculate_total(self) -> float:
        """Total miner reward"""
        return round(self.base_mining_reward + self.heat_bonus_reward, 6)


@dataclass
class FarmHeatStats:
    """Aggregated statistics for a farm"""
    farm_location: str
    total_miners: int = 0
    total_kwh_day: float = 0.0
    average_recovery_pct: float = 0.0
    active_use_case: str = ""
    reputation_score: float = 0.0  # 0.0-1.0
    total_thr_earned: float = 0.0
    total_usd_value: float = 0.0
    last_report_timestamp: str = ""
    uptime_percentage: float = 100.0


# ═══════════════════════════════════════════════════════════════
# ENERGY CONVERTER
# ═══════════════════════════════════════════════════════════════

class EnergyConverter:
    """Convert heat energy to economic value"""

    @staticmethod
    def joules_to_kwh(joules: float) -> float:
        """Convert joules to kWh"""
        return joules / JOULES_PER_KWH

    @staticmethod
    def joules_to_btu(joules: float) -> float:
        """Convert joules to BTU"""
        return joules * BTU_PER_JOULE

    @staticmethod
    def estimate_energy_value(
        kwh_recovered: float,
        market_segment: str = "industrial"
    ) -> float:
        """Estimate USD value of recovered energy"""
        price = ENERGY_PRICE_USD_PER_KWH.get(
            market_segment,
            ENERGY_PRICE_USD_PER_KWH["industrial"]
        )
        return round(kwh_recovered * price, 4)

    @staticmethod
    def energy_value_to_thr(
        energy_value_usd: float,
        thr_price_usd: float = 0.0001
    ) -> float:
        """Convert USD energy value to THR equivalent"""
        if thr_price_usd <= 0:
            return 0.0
        return round(energy_value_usd / thr_price_usd, 6)

    @staticmethod
    def daily_projection(
        kwh_recovered_per_block: float,
        blocks_per_day: int = 720  # 2-minute blocks
    ) -> Dict:
        """Project energy recovery over time periods"""
        kwh_day = kwh_recovered_per_block * blocks_per_day
        usd_day = EnergyConverter.estimate_energy_value(kwh_day)

        return {
            "kwh_daily": round(kwh_day, 2),
            "kwh_monthly": round(kwh_day * 30, 2),
            "kwh_yearly": round(kwh_day * 365, 2),
            "usd_daily": round(usd_day, 2),
            "usd_monthly": round(usd_day * 30, 2),
            "usd_yearly": round(usd_day * 365, 2),
        }


# ═══════════════════════════════════════════════════════════════
# HEAT REWARD ENGINE
# ═══════════════════════════════════════════════════════════════

class HeatRewardEngine:
    """Calculate heat recovery bonuses for miners"""

    def __init__(self):
        self.metrics_file = DATA_DIR / "heat_metrics.json"
        self.rewards_file = DATA_DIR / "heat_rewards.json"
        self.farms_file = DATA_DIR / "heat_farms.json"
        logger.info("🔥 Heat Reward Engine initialized")

    @staticmethod
    def get_tier(recovery_percentage: float) -> HeatRewardTier:
        """Determine reward tier from recovery %"""
        for tier in HeatRewardTier:
            tier_data = tier.value
            if (tier_data["recovery_min"] <= recovery_percentage <=
                tier_data["recovery_max"]):
                return tier
        return HeatRewardTier.TIER_1

    @staticmethod
    def get_use_case_bonus(use_case: str) -> float:
        """Get bonus for specific use case"""
        try:
            uc = UseCase[use_case.upper()]
            return uc.value["bonus"]
        except (KeyError, AttributeError):
            return 0.10  # Default bonus

    def calculate_heat_reward(
        self,
        base_reward: float,  # 8.0 THR from Phase C5
        heat_metrics: MinerHeatMetrics,
        thr_price_usd: float = 0.0001
    ) -> HeatRewardPool:
        """Calculate total reward: base + heat bonus"""

        # Determine tier
        tier = self.get_tier(heat_metrics.recovery_percentage)
        tier_bonus = tier.value["bonus_percentage"]

        # Use case bonus
        use_case_bonus = self.get_use_case_bonus(heat_metrics.use_case)

        # Calculate bonuses
        heat_bonus_thr = base_reward * tier_bonus
        total_bonus_thr = heat_bonus_thr * (1.0 + use_case_bonus)

        # Energy value
        energy_value_usd = EnergyConverter.estimate_energy_value(
            heat_metrics.heat_recovered_kwh,
            "industrial"
        )

        reward = HeatRewardPool(
            miner_address=heat_metrics.miner_address,
            current_block_reward=base_reward,
            heat_recovery_kwh_day=heat_metrics.heat_recovered_kwh,
            heat_bonus_percentage=tier_bonus,
            heat_bonus_amount=total_bonus_thr,
            energy_value_usd_per_kwh=ENERGY_PRICE_USD_PER_KWH["industrial"],
            heat_value_usd=energy_value_usd,
            thr_price_usd=thr_price_usd,
            heat_equivalent_thr=EnergyConverter.energy_value_to_thr(
                energy_value_usd, thr_price_usd
            ),
            base_mining_reward=base_reward,
            heat_bonus_reward=total_bonus_thr,
            total_reward=base_reward + total_bonus_thr,
            timestamp=datetime.utcnow().isoformat()
        )

        return reward

    def submit_heat_metrics(
        self,
        metrics: MinerHeatMetrics
    ) -> Dict:
        """Submit heat metrics to blockchain"""

        tier = self.get_tier(metrics.recovery_percentage)
        reward_multiplier = 1.0 + tier.value["bonus_percentage"]

        return {
            "status": "accepted",
            "metrics_id": f"metric_{metrics.miner_address}_{int(time.time())}",
            "tier": tier.name,
            "recovery_percentage": metrics.recovery_percentage,
            "reward_multiplier": round(reward_multiplier, 3),
            "estimated_bonus_thr": round(8.0 * (reward_multiplier - 1.0), 6),
            "energy_value_usd": EnergyConverter.estimate_energy_value(
                metrics.heat_recovered_kwh
            ),
            "next_report_in_blocks": 300  # 10 hours at 2-min blocks
        }

    def get_farm_stats(self, farm_location: str) -> Optional[FarmHeatStats]:
        """Get aggregated stats for a farm"""
        farms = self._load_farms()
        return farms.get(farm_location)

    def update_farm_reputation(
        self,
        farm_location: str,
        reliability_score: float  # 0.0-1.0
    ) -> float:
        """Update farm reputation based on uptime"""
        farms = self._load_farms()
        if farm_location not in farms:
            farms[farm_location] = asdict(FarmHeatStats(farm_location))

        # Weighted average: 70% recent, 30% historical
        old_score = farms[farm_location].get("reputation_score", 0.5)
        new_score = (0.7 * reliability_score) + (0.3 * old_score)
        farms[farm_location]["reputation_score"] = round(new_score, 3)

        self._save_farms(farms)
        return new_score

    def _load_farms(self) -> Dict:
        """Load farm stats"""
        if self.farms_file.exists():
            return json.loads(self.farms_file.read_text())
        return {}

    def _save_farms(self, farms: Dict):
        """Save farm stats"""
        self.farms_file.write_text(json.dumps(farms, indent=2))


# ═══════════════════════════════════════════════════════════════
# GLOBAL INSTANCE
# ═══════════════════════════════════════════════════════════════

_heat_engine: Optional[HeatRewardEngine] = None


def initialize_heat_engine() -> HeatRewardEngine:
    """Initialize global heat reward engine"""
    global _heat_engine
    _heat_engine = HeatRewardEngine()
    return _heat_engine


def get_heat_engine() -> Optional[HeatRewardEngine]:
    """Get global heat reward engine"""
    return _heat_engine
