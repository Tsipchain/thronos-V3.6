"""
Time-Lock & Pool Redistribution System - Phase C4
==================================================

Manages unclaimed assets and fair redistribution to charitable causes.

Philosophy:
When an heir doesn't claim their inherited assets within 15-30 years,
those assets return to the network pool and are redistributed fairly
to reduce human suffering: schools, housing, homeless support, healthcare.

Features:
- Time-lock tracking (15-30 years)
- Unclaimed asset collection and aggregation
- Fair redistribution algorithm
- Charitable cause allocation
- Real-world asset → charity pipeline
- Blockchain-verified transfers

Asset Lifecycle:
1. Estate created (0 years)
2. Will locked (30 years by default)
3. Will can be opened (year 30)
4. Distribution window opens (years 30-33)
5. Unclaimed assets collected (year 33)
6. Redistributed to pool causes (year 33+)
7. Real-world execution (ongoing)

Distribution Causes (fair allocation):
- 25% → Schools & Education (reduce illiteracy, enable futures)
- 25% → Housing & Shelter (end homelessness)
- 25% → Healthcare & Medical (save lives, reduce suffering)
- 15% → Food Security & Nutrition (prevent starvation)
- 10% → Community Development (empower local economies)

Author: Thronos Digital Redistribution
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
POOL_FILE = DATA_DIR / "charity_pool.json"
REDISTRIBUTION_FILE = DATA_DIR / "redistributions.json"


class CharityCause(Enum):
    """Charitable causes for redistribution"""
    SCHOOLS = "schools"              # Education & schools (25%)
    HOUSING = "housing"              # Housing & shelter (25%)
    HEALTHCARE = "healthcare"        # Medical & healthcare (25%)
    FOOD_SECURITY = "food"           # Food & nutrition (15%)
    COMMUNITY = "community"          # Community development (10%)


class PoolStatus(Enum):
    """Status of assets in the pool"""
    COLLECTING = "collecting"        # Collecting unclaimed assets
    COLLECTED = "collected"          # All unclaimed assets collected
    ALLOCATING = "allocating"        # Allocating to causes
    ALLOCATED = "allocated"          # Allocated but not yet transferred
    EXECUTED = "executed"            # Real-world execution complete


@dataclass
class CharityAllocation:
    """Allocation to a specific charitable cause"""
    cause: CharityCause                 # Charity type
    allocation_percentage: float        # % of pool for this cause
    allocated_amount_usd: float = 0.0   # Amount allocated
    transferred_amount_usd: float = 0.0 # Amount transferred
    execution_status: str = "pending"   # pending, executing, completed

    allocated_at: Optional[str] = None
    transferred_at: Optional[str] = None
    execution_details: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "cause": self.cause.value,
            "allocation_percentage": self.allocation_percentage,
            "allocated_amount_usd": self.allocated_amount_usd,
            "transferred_amount_usd": self.transferred_amount_usd,
            "execution_status": self.execution_status,
            "allocated_at": self.allocated_at,
            "transferred_at": self.transferred_at,
            "execution_details": self.execution_details,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "CharityAllocation":
        if "cause" in data and isinstance(data["cause"], str):
            data["cause"] = CharityCause(data["cause"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class PoolAsset:
    """Asset in the charity pool"""
    asset_id: str                       # From original estate
    original_owner: str                 # Original owner address
    asset_type: str                     # Type: crypto, real_estate, etc
    value_usd: float                    # Current value

    claim_deadline: str                 # When claim period expired
    collected_at: Optional[str] = None  # When added to pool

    # Allocation
    allocated_to_cause: Optional[str] = None  # Which cause it was allocated to
    allocation_percentage: float = 0.0

    # Transfer
    transfer_status: str = "pending"    # pending, transferred, executing
    transferred_at: Optional[str] = None
    transfer_hash: Optional[str] = None # Blockchain tx or execution record

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "PoolAsset":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class CharityPool:
    """The charity pool for redistributing unclaimed assets"""
    pool_id: str                        # Unique pool identifier
    created_at: str                     # When pool was created

    # Assets in pool
    assets: List[PoolAsset] = field(default_factory=list)
    total_assets_count: int = 0
    total_value_usd: float = 0.0

    # Allocations to causes
    allocations: Dict[str, CharityAllocation] = field(default_factory=dict)

    # Status
    status: PoolStatus = PoolStatus.COLLECTING
    collected_at: Optional[str] = None
    allocated_at: Optional[str] = None

    # Execution tracking
    execution_start: Optional[str] = None
    execution_complete: Optional[str] = None

    # Metadata
    notes: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "pool_id": self.pool_id,
            "created_at": self.created_at,
            "assets": [a.to_dict() for a in self.assets],
            "total_assets_count": self.total_assets_count,
            "total_value_usd": self.total_value_usd,
            "allocations": {k: v.to_dict() for k, v in self.allocations.items()},
            "status": self.status.value,
            "collected_at": self.collected_at,
            "allocated_at": self.allocated_at,
            "execution_start": self.execution_start,
            "execution_complete": self.execution_complete,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "CharityPool":
        if "assets" in data:
            data["assets"] = [PoolAsset.from_dict(a) for a in data["assets"]]
        if "allocations" in data:
            data["allocations"] = {
                k: CharityAllocation.from_dict(v)
                for k, v in data["allocations"].items()
            }
        if "status" in data and isinstance(data["status"], str):
            data["status"] = PoolStatus(data["status"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class CharityPoolManager:
    """Manages unclaimed assets and charitable redistribution"""

    # Default allocations (fair redistribution)
    DEFAULT_ALLOCATIONS = {
        CharityCause.SCHOOLS: 25.0,      # Education
        CharityCause.HOUSING: 25.0,      # Housing
        CharityCause.HEALTHCARE: 25.0,   # Healthcare
        CharityCause.FOOD_SECURITY: 15.0, # Food
        CharityCause.COMMUNITY: 10.0,    # Community
    }

    def __init__(self):
        self.pools: Dict[str, CharityPool] = {}
        self._load_pools()
        logger.info("🌍 Charity Pool Manager initialized")

    def _load_pools(self):
        """Load charity pools from storage"""
        try:
            if POOL_FILE.exists():
                with open(POOL_FILE, 'r') as f:
                    data = json.load(f)
                    for pool_id, pool_data in data.items():
                        self.pools[pool_id] = CharityPool.from_dict(pool_data)
                logger.info(f"✅ Loaded {len(self.pools)} charity pools")
        except Exception as e:
            logger.error(f"Error loading pools: {e}")

    def _save_pools(self):
        """Save charity pools to storage"""
        try:
            DATA_DIR.mkdir(exist_ok=True)
            with open(POOL_FILE, 'w') as f:
                data = {pid: pool.to_dict() for pid, pool in self.pools.items()}
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving pools: {e}")

    def create_pool(self) -> CharityPool:
        """Create a new charity pool for redistribution"""
        try:
            pool_id = f"pool_{int(time.time())}"

            # Create allocations with default percentages
            allocations = {}
            for cause, percentage in self.DEFAULT_ALLOCATIONS.items():
                allocations[cause.value] = CharityAllocation(
                    cause=cause,
                    allocation_percentage=percentage
                )

            pool = CharityPool(
                pool_id=pool_id,
                created_at=datetime.utcnow().isoformat() + "Z",
                allocations=allocations
            )

            self.pools[pool_id] = pool
            self._save_pools()
            logger.info(f"✅ Created charity pool {pool_id}")
            return pool

        except Exception as e:
            logger.error(f"Error creating pool: {e}")
            raise

    def add_unclaimed_asset(
        self,
        pool_id: str,
        asset_id: str,
        original_owner: str,
        asset_type: str,
        value_usd: float,
        claim_deadline: str
    ) -> Tuple[bool, str]:
        """Add unclaimed asset to pool"""
        try:
            pool = self.pools.get(pool_id)
            if not pool:
                return False, "Pool not found"

            asset = PoolAsset(
                asset_id=asset_id,
                original_owner=original_owner,
                asset_type=asset_type,
                value_usd=value_usd,
                claim_deadline=claim_deadline,
                collected_at=datetime.utcnow().isoformat() + "Z"
            )

            pool.assets.append(asset)
            pool.total_assets_count = len(pool.assets)
            pool.total_value_usd += value_usd

            self._save_pools()
            logger.info(f"✅ Added unclaimed asset {asset_id} to pool {pool_id} (${value_usd:,.2f})")
            return True, f"Asset added. Pool total: ${pool.total_value_usd:,.2f}"

        except Exception as e:
            logger.error(f"Error adding unclaimed asset: {e}")
            return False, str(e)

    def allocate_pool_to_causes(self, pool_id: str) -> Tuple[bool, str]:
        """
        Allocate pool assets to charitable causes

        Distribution based on default percentages:
        - 25% Schools (education)
        - 25% Housing (shelter & homelessness)
        - 25% Healthcare (medical & wellness)
        - 15% Food Security (nutrition)
        - 10% Community (development)
        """
        try:
            pool = self.pools.get(pool_id)
            if not pool:
                return False, "Pool not found"

            if pool.status != PoolStatus.COLLECTED:
                return False, f"Pool status is {pool.status.value}, not collected"

            # Allocate assets to causes
            for cause_str, allocation in pool.allocations.items():
                cause_amount = (allocation.allocation_percentage / 100.0) * pool.total_value_usd
                allocation.allocated_amount_usd = cause_amount
                allocation.allocated_at = datetime.utcnow().isoformat() + "Z"

            pool.status = PoolStatus.ALLOCATED
            pool.allocated_at = datetime.utcnow().isoformat() + "Z"

            self._save_pools()
            logger.info(f"✅ Allocated pool {pool_id} to causes (Total: ${pool.total_value_usd:,.2f})")
            return True, "Pool allocated to all causes"

        except Exception as e:
            logger.error(f"Error allocating pool: {e}")
            return False, str(e)

    def get_pool_stats(self, pool_id: Optional[str] = None) -> Dict:
        """Get statistics for pool(s)"""
        try:
            if pool_id:
                pool = self.pools.get(pool_id)
                if not pool:
                    return {}

                return {
                    "pool_id": pool_id,
                    "status": pool.status.value,
                    "total_assets": pool.total_assets_count,
                    "total_value_usd": pool.total_value_usd,
                    "allocations": {
                        cause: {
                            "percentage": alloc.allocation_percentage,
                            "amount_usd": alloc.allocated_amount_usd
                        }
                        for cause, alloc in pool.allocations.items()
                    }
                }
            else:
                # All pools
                total_value = sum(p.total_value_usd for p in self.pools.values())
                return {
                    "total_pools": len(self.pools),
                    "total_value_usd": total_value,
                    "pools": {
                        pid: {
                            "assets": p.total_assets_count,
                            "value_usd": p.total_value_usd,
                            "status": p.status.value
                        }
                        for pid, p in self.pools.items()
                    }
                }

        except Exception as e:
            logger.error(f"Error getting pool stats: {e}")
            return {}

    def collect_pool(self, pool_id: str) -> Tuple[bool, str]:
        """Mark pool as fully collected (ready for allocation)"""
        try:
            pool = self.pools.get(pool_id)
            if not pool:
                return False, "Pool not found"

            pool.status = PoolStatus.COLLECTED
            pool.collected_at = datetime.utcnow().isoformat() + "Z"
            self._save_pools()

            logger.info(f"✅ Pool {pool_id} fully collected (${pool.total_value_usd:,.2f})")
            return True, f"Pool collected with {pool.total_assets_count} assets"

        except Exception as e:
            logger.error(f"Error collecting pool: {e}")
            return False, str(e)


# Global instance
_pool_manager: Optional[CharityPoolManager] = None


def initialize_pool_manager() -> CharityPoolManager:
    """Initialize global pool manager"""
    global _pool_manager
    _pool_manager = CharityPoolManager()
    return _pool_manager


def get_pool_manager() -> Optional[CharityPoolManager]:
    """Get global manager instance"""
    return _pool_manager
