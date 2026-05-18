#!/usr/bin/env python3
"""
Miner Equipment Installation & Tier Upgrade Tracker
====================================================

Tracks:
1. Heat recovery equipment installation
2. Sensor calibration & verification
3. Automatic tier upgrades based on proof improvements
4. Miner reputation & compliance history
5. Penalty system for fraud detection

Author: Thronos Phase 6D
Status: Implementation
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DATA_DIR.mkdir(exist_ok=True)


class EquipmentType(Enum):
    """Heat recovery equipment types"""
    NONE = "none"
    PASSIVE_FANS = "passive_fans"  # Just ventilation
    HEAT_EXCHANGER = "heat_exchanger"  # 90%+ efficiency
    ORC_TURBINE = "orc_turbine"  # Organic Rankine Cycle (12% electrical)
    STIRLING_ENGINE = "stirling_engine"  # 18% electrical
    HEAT_PUMP = "heat_pump"  # 333% COP
    ABSORPTION_SYSTEM = "absorption_system"  # 80%+ for heating/cooling
    HYBRID_SYSTEM = "hybrid_system"  # Multiple methods combined


class ComplianceStatus(Enum):
    """Miner compliance status"""
    NOT_REGISTERED = "not_registered"  # No heat system declared
    PENDING_VERIFICATION = "pending_verification"  # Claimed but not verified
    VERIFIED = "verified"  # Equipment confirmed via proofs
    COMPLIANT = "compliant"  # Meeting all requirements
    MONITORING = "monitoring"  # Under observation for fraud
    SUSPENDED = "suspended"  # Temporarily banned due to violations
    PERMANENTLY_BANNED = "permanently_banned"  # Permanently banned


@dataclass
class EquipmentInfo:
    """Heat recovery equipment installation info"""
    miner_address: str
    equipment_type: str  # From EquipmentType enum
    installation_date: str  # ISO 8601
    location: str  # Farm location

    # Specifications
    capacity_kw: float  # Heat capacity in kW
    efficiency_percent: float  # Expected efficiency

    # Verification
    verification_date: Optional[str] = None
    verified_by: str = ""  # Third-party verifier
    gps_latitude: float = 0.0
    gps_longitude: float = 0.0
    facility_photo_hash: str = ""  # IPFS hash of installation photo

    # Status
    is_operational: bool = False
    last_maintenance: Optional[str] = None
    maintenance_interval_days: int = 30


@dataclass
class MinerComplianceRecord:
    """Miner compliance and tier upgrade history"""
    miner_address: str
    current_tier: str  # TIER_1, TIER_2, TIER_3, TIER_4
    compliance_status: str  # From ComplianceStatus enum

    # Timeline
    first_submission_date: Optional[str] = None
    last_proof_submission: Optional[str] = None
    last_tier_upgrade_date: Optional[str] = None

    # Equipment
    equipment_type: str = "none"
    equipment_verified: bool = False
    equipment_verification_date: Optional[str] = None

    # Proof statistics
    total_proofs_submitted: int = 0
    valid_proofs: int = 0
    failed_proofs: int = 0
    fraud_violations: int = 0

    # Reputation
    reputation_score: float = 100.0  # 0-100, starts at 100
    average_recovery_pct: float = 0.0

    # Penalties
    warnings: int = 0  # Warning count before suspension
    suspensions: int = 0
    is_banned: bool = False
    ban_reason: str = ""
    ban_until: Optional[str] = None

    # Reward tracking
    total_heat_bonus_thr: float = 0.0
    last_bonus_calculation: Optional[str] = None


class MinerEquipmentTracker:
    """Manage miner equipment installation and compliance"""

    def __init__(self):
        self.equipment_file = DATA_DIR / "miner_equipment.json"
        self.compliance_file = DATA_DIR / "miner_compliance.json"
        logger.info("🔧 Miner Equipment Tracker initialized")

    def register_equipment(self, miner_address: str, equipment: EquipmentInfo) -> Dict:
        """Register new heat recovery equipment for miner"""
        equipment_data = self._load_equipment_data()

        if miner_address in equipment_data:
            return {
                "status": "error",
                "message": "Equipment already registered for this miner",
                "existing": equipment_data[miner_address][0] if equipment_data[miner_address] else None
            }

        # Initialize compliance record if not exists
        compliance = self._get_or_create_compliance(miner_address)
        compliance["equipment_type"] = equipment.equipment_type
        compliance["compliance_status"] = ComplianceStatus.PENDING_VERIFICATION.value

        # Store equipment
        if miner_address not in equipment_data:
            equipment_data[miner_address] = []
        equipment_data[miner_address].append(asdict(equipment))
        self._save_equipment_data(equipment_data)
        self._save_compliance_record(miner_address, compliance)

        return {
            "status": "registered",
            "message": "Equipment registration pending verification",
            "equipment_type": equipment.equipment_type,
            "expected_tier": self._estimate_tier_from_equipment(equipment.efficiency_percent),
            "next_step": "Submit heat recovery proofs to verify equipment"
        }

    def verify_equipment(self, miner_address: str, verified_by: str = "ThronosVerifier") -> Dict:
        """Mark equipment as verified (after successful proofs)"""
        equipment_data = self._load_equipment_data()

        if miner_address not in equipment_data or not equipment_data[miner_address]:
            return {
                "status": "error",
                "message": "No equipment found for this miner"
            }

        # Mark as verified
        equipment_data[miner_address][-1]["verified_by"] = verified_by
        equipment_data[miner_address][-1]["verification_date"] = datetime.utcnow().isoformat()
        equipment_data[miner_address][-1]["is_operational"] = True
        self._save_equipment_data(equipment_data)

        # Update compliance
        compliance = self._get_or_create_compliance(miner_address)
        compliance["equipment_verified"] = True
        compliance["equipment_verification_date"] = datetime.utcnow().isoformat()
        compliance["compliance_status"] = ComplianceStatus.VERIFIED.value
        self._save_compliance_record(miner_address, compliance)

        return {
            "status": "verified",
            "message": "Equipment verified successfully",
            "compliance_status": ComplianceStatus.VERIFIED.value
        }

    def auto_upgrade_tier(self, miner_address: str, new_recovery_pct: float, proof_level: str) -> Dict:
        """
        Automatically upgrade miner tier based on proof improvements

        Tier progression:
        - TIER_1: 5-10% recovery (50% bonus)
        - TIER_2: 10-15% recovery (85% bonus)
        - TIER_3: 15-25% recovery (95% bonus)
        - TIER_4: 25%+ recovery (100% bonus)
        """
        compliance = self._get_or_create_compliance(miner_address)
        old_tier = compliance.get("current_tier", "TIER_1")

        # Determine new tier based on recovery percentage
        if new_recovery_pct >= 25:
            new_tier = "TIER_4"
        elif new_recovery_pct >= 15:
            new_tier = "TIER_3"
        elif new_recovery_pct >= 10:
            new_tier = "TIER_2"
        else:
            new_tier = "TIER_1"

        # Update if tier improved
        tier_order = {"TIER_1": 1, "TIER_2": 2, "TIER_3": 3, "TIER_4": 4}
        tier_upgraded = tier_order.get(new_tier, 0) > tier_order.get(old_tier, 0)

        if tier_upgraded:
            compliance["current_tier"] = new_tier
            compliance["last_tier_upgrade_date"] = datetime.utcnow().isoformat()
            compliance["average_recovery_pct"] = new_recovery_pct
            self._save_compliance_record(miner_address, compliance)

            logger.info(f"✅ Tier upgrade: {miner_address} {old_tier} → {new_tier}")

            return {
                "status": "upgraded",
                "message": f"Congratulations! Tier upgraded to {new_tier}",
                "old_tier": old_tier,
                "new_tier": new_tier,
                "recovery_pct": new_recovery_pct,
                "bonus_increase": self._get_tier_bonus(new_tier) - self._get_tier_bonus(old_tier)
            }
        else:
            compliance["average_recovery_pct"] = new_recovery_pct
            self._save_compliance_record(miner_address, compliance)

            return {
                "status": "no_upgrade",
                "message": f"Tier remains {old_tier}. Keep improving to reach {self._get_next_tier(new_tier)}",
                "current_tier": new_tier,
                "recovery_pct": new_recovery_pct,
                "progress": f"{new_recovery_pct:.1f}% of current tier"
            }

    def record_proof_submission(self, miner_address: str, is_valid: bool, proof_level: str, recovery_pct: float) -> Dict:
        """Record proof submission for compliance tracking"""
        compliance = self._get_or_create_compliance(miner_address)

        compliance["total_proofs_submitted"] = compliance.get("total_proofs_submitted", 0) + 1
        compliance["last_proof_submission"] = datetime.utcnow().isoformat()

        if is_valid:
            compliance["valid_proofs"] = compliance.get("valid_proofs", 0) + 1

            # Update first submission date
            if not compliance.get("first_submission_date"):
                compliance["first_submission_date"] = datetime.utcnow().isoformat()

            # Verify equipment if not already done
            if not compliance.get("equipment_verified") and proof_level in ["LEVEL_2", "LEVEL_3", "LEVEL_4"]:
                self.verify_equipment(miner_address)

            # Check for tier upgrade
            self.auto_upgrade_tier(miner_address, recovery_pct, proof_level)
        else:
            compliance["failed_proofs"] = compliance.get("failed_proofs", 0) + 1

        self._save_compliance_record(miner_address, compliance)

        return {
            "status": "recorded",
            "total_submissions": compliance["total_proofs_submitted"],
            "valid": compliance["valid_proofs"],
            "failed": compliance["failed_proofs"],
            "success_rate": round(compliance["valid_proofs"] / max(1, compliance["total_proofs_submitted"]) * 100, 1)
        }

    def record_fraud_violation(self, miner_address: str, violation: str) -> Dict:
        """Record fraud violation and apply penalties"""
        compliance = self._get_or_create_compliance(miner_address)

        compliance["fraud_violations"] = compliance.get("fraud_violations", 0) + 1
        violations = compliance["fraud_violations"]

        # Penalty system
        if violations == 1:
            # First violation: Warning + monitoring
            compliance["warnings"] = 1
            compliance["compliance_status"] = ComplianceStatus.MONITORING.value
            logger.warning(f"⚠️ Fraud Warning: {miner_address} - {violation}")
            action = "Placed under monitoring"

        elif violations == 2:
            # Second violation: Tier downgrade + suspension
            compliance["suspensions"] = 1
            compliance["compliance_status"] = ComplianceStatus.SUSPENDED.value
            compliance["ban_until"] = (datetime.utcnow() + timedelta(days=7)).isoformat()
            # Downgrade tier
            compliance["current_tier"] = self._downgrade_tier(compliance.get("current_tier", "TIER_1"))
            logger.error(f"🚫 Fraud Suspension: {miner_address} - {violation}")
            action = "7-day suspension + tier downgrade"

        else:
            # Third+ violation: Permanent ban
            compliance["is_banned"] = True
            compliance["compliance_status"] = ComplianceStatus.PERMANENTLY_BANNED.value
            compliance["ban_reason"] = violation
            logger.error(f"🔒 Fraud Permanent Ban: {miner_address} - {violation}")
            action = "Permanently banned from heat rewards"

        self._save_compliance_record(miner_address, compliance)

        return {
            "status": "violation_recorded",
            "violation_count": violations,
            "action_taken": action,
            "compliance_status": compliance["compliance_status"],
            "message": f"Violation #{violations}: {action}"
        }

    def get_miner_status(self, miner_address: str) -> Dict:
        """Get complete miner compliance and equipment status"""
        compliance = self._get_or_create_compliance(miner_address)
        equipment_data = self._load_equipment_data()
        equipment = equipment_data.get(miner_address, [{}])[-1] if miner_address in equipment_data else {}

        return {
            "miner_address": miner_address,
            "compliance": {
                "status": compliance.get("compliance_status", ComplianceStatus.NOT_REGISTERED.value),
                "current_tier": compliance.get("current_tier", "TIER_1"),
                "is_banned": compliance.get("is_banned", False),
                "reputation_score": compliance.get("reputation_score", 100.0),
                "average_recovery_pct": compliance.get("average_recovery_pct", 0.0)
            },
            "equipment": {
                "type": equipment.get("equipment_type", "none"),
                "verified": equipment.get("verified_by") is not None,
                "operational": equipment.get("is_operational", False),
                "capacity_kw": equipment.get("capacity_kw", 0),
                "efficiency_percent": equipment.get("efficiency_percent", 0)
            },
            "proof_statistics": {
                "total_submitted": compliance.get("total_proofs_submitted", 0),
                "valid": compliance.get("valid_proofs", 0),
                "failed": compliance.get("failed_proofs", 0),
                "fraud_violations": compliance.get("fraud_violations", 0),
                "success_rate": round(compliance.get("valid_proofs", 0) / max(1, compliance.get("total_proofs_submitted", 1)) * 100, 1)
            },
            "rewards": {
                "total_heat_bonus_thr": compliance.get("total_heat_bonus_thr", 0.0),
                "last_calculation": compliance.get("last_bonus_calculation")
            }
        }

    # ─── PRIVATE HELPERS ───

    def _load_equipment_data(self) -> Dict:
        """Load equipment data from file"""
        if self.equipment_file.exists():
            try:
                return json.loads(self.equipment_file.read_text())
            except:
                return {}
        return {}

    def _save_equipment_data(self, data: Dict):
        """Save equipment data to file"""
        self.equipment_file.write_text(json.dumps(data, indent=2))

    def _get_or_create_compliance(self, miner_address: str) -> Dict:
        """Get or create compliance record"""
        compliance_data = {}
        if self.compliance_file.exists():
            try:
                compliance_data = json.loads(self.compliance_file.read_text())
            except:
                compliance_data = {}

        if miner_address not in compliance_data:
            compliance_data[miner_address] = {
                "miner_address": miner_address,
                "current_tier": "TIER_1",
                "compliance_status": ComplianceStatus.NOT_REGISTERED.value,
                "equipment_type": "none",
                "total_proofs_submitted": 0,
                "valid_proofs": 0,
                "failed_proofs": 0,
                "fraud_violations": 0,
                "reputation_score": 100.0,
                "average_recovery_pct": 0.0,
                "warnings": 0,
                "suspensions": 0,
                "is_banned": False,
                "total_heat_bonus_thr": 0.0
            }

        return compliance_data[miner_address]

    def _save_compliance_record(self, miner_address: str, record: Dict):
        """Save compliance record"""
        compliance_data = {}
        if self.compliance_file.exists():
            try:
                compliance_data = json.loads(self.compliance_file.read_text())
            except:
                compliance_data = {}

        compliance_data[miner_address] = record
        self.compliance_file.write_text(json.dumps(compliance_data, indent=2))

    def _estimate_tier_from_equipment(self, efficiency: float) -> str:
        """Estimate tier based on equipment efficiency"""
        if efficiency >= 25:
            return "TIER_4"
        elif efficiency >= 15:
            return "TIER_3"
        elif efficiency >= 10:
            return "TIER_2"
        else:
            return "TIER_1"

    def _downgrade_tier(self, current_tier: str) -> str:
        """Downgrade tier one level"""
        tier_map = {"TIER_4": "TIER_3", "TIER_3": "TIER_2", "TIER_2": "TIER_1", "TIER_1": "TIER_1"}
        return tier_map.get(current_tier, "TIER_1")

    def _get_next_tier(self, current_tier: str) -> str:
        """Get next tier level"""
        tier_map = {"TIER_1": "TIER_2", "TIER_2": "TIER_3", "TIER_3": "TIER_4", "TIER_4": "TIER_4"}
        return tier_map.get(current_tier, "TIER_2")

    def _get_tier_bonus(self, tier: str) -> float:
        """Get bonus multiplier for tier"""
        bonus_map = {"TIER_1": 0.05, "TIER_2": 0.15, "TIER_3": 0.25, "TIER_4": 0.40}
        return bonus_map.get(tier, 0.05)


# ─── GLOBAL INSTANCE ───

_equipment_tracker: Optional[MinerEquipmentTracker] = None


def initialize_equipment_tracker() -> MinerEquipmentTracker:
    """Initialize global equipment tracker"""
    global _equipment_tracker
    _equipment_tracker = MinerEquipmentTracker()
    return _equipment_tracker


def get_equipment_tracker() -> Optional[MinerEquipmentTracker]:
    """Get global equipment tracker"""
    return _equipment_tracker
