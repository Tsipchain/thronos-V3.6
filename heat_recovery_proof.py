#!/usr/bin/env python3
"""
Phase 6C: Heat Recovery Proof System
Verification & Real-World Energy Validation

Ensures miners provide legitimate proof that:
1. Heat is actually captured from mining equipment
2. Heat is circulated/transported
3. Heat is converted to useful energy
4. Energy generation is measurable
"""

import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path
import os

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DATA_DIR.mkdir(exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# PROOF LEVELS
# ═══════════════════════════════════════════════════════════════

class ProofLevel(Enum):
    """Heat recovery proof levels"""
    LEVEL_1 = {
        "name": "Temperature Differential Proof",
        "requirement": "Outlet temp ≥ Inlet temp + 20°C",
        "confidence": 0.5,
        "bonus_multiplier": 0.5
    }
    LEVEL_2 = {
        "name": "Energy Balance Proof",
        "requirement": "Calculated heat matches physics (±10%)",
        "confidence": 0.75,
        "bonus_multiplier": 0.85
    }
    LEVEL_3 = {
        "name": "Facility Proof",
        "requirement": "End-use facility temperature validates heat arrival",
        "confidence": 0.90,
        "bonus_multiplier": 0.95
    }
    LEVEL_4 = {
        "name": "Energy Generation Proof",
        "requirement": "Smart meter validates measurable energy output",
        "confidence": 1.0,
        "bonus_multiplier": 1.0
    }


# ═══════════════════════════════════════════════════════════════
# SENSOR DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════

@dataclass
class SensorReading:
    """Single sensor reading with metadata"""
    sensor_type: str  # "temperature", "humidity", "airflow", "flow_meter"
    location: str  # "inlet", "outlet", "facility", etc.
    value: float
    unit: str  # "C", "%", "CFM", "GPM", "kWh"
    timestamp: str  # ISO 8601
    accuracy_percent: float = 2.0  # ±X% accuracy
    sensor_brand: str = ""
    calibration_date: str = ""
    is_valid: bool = True
    error_message: str = ""


@dataclass
class HeatRecoveryProof:
    """Complete heat recovery proof for a mining operation"""
    miner_address: str
    timestamp: str  # ISO 8601

    # Sensor readings
    ambient_temp_c: float
    inlet_temp_c: float
    outlet_temp_c: float
    inlet_humidity_pct: float
    outlet_humidity_pct: float
    airflow_cfm: float

    # Heat recovery system
    pre_recovery_temp_c: float
    post_recovery_temp_c: float
    recirculation_flow_gpm: float

    # End use facility
    facility_temp_c: float
    facility_humidity_pct: float

    # Energy measurement
    energy_generated_kwh: float

    # Device info
    device_type: str
    device_count: int
    power_consumption_watts: float

    # Location & use case
    farm_location: str
    use_case: str

    # GPS proof
    gps_latitude: float = 0.0
    gps_longitude: float = 0.0
    gps_accuracy_meters: float = 0.0

    # Photo/video proof (IPFS hashes)
    facility_photo_hash: str = ""
    installation_photo_hash: str = ""
    video_proof_hash: str = ""

    # Proof metadata
    proof_level: ProofLevel = ProofLevel.LEVEL_1
    calculated_recovery_pct: float = 0.0
    calculated_heat_kwh: float = 0.0
    physics_valid: bool = True
    sensors_online: int = 12
    sensors_total: int = 12
    data_integrity_hash: str = ""
    third_party_auditor: str = ""
    audit_signature: str = ""


@dataclass
class HeatProofVerification:
    """Result of proof verification"""
    proof_id: str
    miner_address: str
    timestamp: str

    is_valid: bool
    proof_level: ProofLevel

    # Individual checks
    level_1_passed: bool = False  # Temperature check
    level_2_passed: bool = False  # Energy balance
    level_3_passed: bool = False  # Facility proof
    level_4_passed: bool = False  # Energy generation

    physics_valid: bool = False
    fraud_detected: bool = False

    # Fraud detection results
    anomalies: List[str] = field(default_factory=list)

    # Reward calculation
    calculated_tier: str = ""
    bonus_multiplier: float = 1.0
    bonus_amount_thr: float = 0.0

    details: Dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════
# HEAT RECOVERY PROOF VERIFIER
# ═══════════════════════════════════════════════════════════════

class HeatRecoveryVerifier:
    """Verify heat recovery proof and prevent fraud"""

    def __init__(self):
        self.proofs_file = DATA_DIR / "heat_recovery_proofs.json"
        self.fraud_log_file = DATA_DIR / "fraud_detections.json"
        logger.info("🔥 Heat Recovery Proof Verifier initialized")

    def verify_proof(self, proof: HeatRecoveryProof) -> HeatProofVerification:
        """
        Complete heat recovery proof verification
        Returns verification result with fraud detection
        """
        proof_id = f"proof_{proof.miner_address}_{int(datetime.utcnow().timestamp())}"
        verification = HeatProofVerification(
            proof_id=proof_id,
            miner_address=proof.miner_address,
            timestamp=datetime.utcnow().isoformat(),
            is_valid=False,
            proof_level=ProofLevel.LEVEL_1
        )

        # Check Level 1: Temperature Differential
        level_1_result = self._check_level_1_temperature(proof)
        if level_1_result["passed"]:
            verification.level_1_passed = True
            verification.proof_level = ProofLevel.LEVEL_1
        else:
            verification.anomalies.append(f"Level 1 failed: {level_1_result['reason']}")
            return verification  # Stop if basic check fails

        # Check Level 2: Energy Balance
        level_2_result = self._check_level_2_energy_balance(proof)
        if level_2_result["passed"]:
            verification.level_2_passed = True
            verification.proof_level = ProofLevel.LEVEL_2
        else:
            verification.anomalies.append(f"Level 2 failed: {level_2_result['reason']}")

        # Check Level 3: Facility Proof
        level_3_result = self._check_level_3_facility_proof(proof)
        if level_3_result["passed"]:
            verification.level_3_passed = True
            verification.proof_level = ProofLevel.LEVEL_3
        else:
            verification.anomalies.append(f"Level 3 failed: {level_3_result['reason']}")

        # Check Level 4: Energy Generation
        level_4_result = self._check_level_4_energy_generation(proof)
        if level_4_result["passed"]:
            verification.level_4_passed = True
            verification.proof_level = ProofLevel.LEVEL_4
        else:
            verification.anomalies.append(f"Level 4 failed: {level_4_result['reason']}")

        # Fraud Detection
        fraud_results = self._detect_fraud(proof, verification)
        if fraud_results["fraud_detected"]:
            verification.fraud_detected = True
            verification.anomalies.extend(fraud_results["violations"])
            self._log_fraud_detection(proof, fraud_results)

        # Determine final validity
        verification.is_valid = (
            verification.level_1_passed and
            not verification.fraud_detected and
            verification.physics_valid
        )

        # Calculate bonus based on proof level
        if verification.is_valid:
            verification.bonus_multiplier = verification.proof_level.value["bonus_multiplier"]

        # Store proof
        self._store_proof(proof, verification)

        return verification

    def _check_level_1_temperature(self, proof: HeatRecoveryProof) -> Dict:
        """Check Level 1: Temperature differential proof"""
        delta_t = proof.outlet_temp_c - proof.inlet_temp_c

        # Must have at least 20°C difference
        if delta_t < 20:
            return {
                "passed": False,
                "reason": f"Temperature delta {delta_t}°C < minimum 20°C",
                "delta_t": delta_t
            }

        # Check for physics impossibility
        if delta_t > 100:
            return {
                "passed": False,
                "reason": f"Temperature delta {delta_t}°C exceeds physical possibility",
                "delta_t": delta_t
            }

        return {
            "passed": True,
            "delta_t": delta_t,
            "confidence": 0.5
        }

    def _check_level_2_energy_balance(self, proof: HeatRecoveryProof) -> Dict:
        """Check Level 2: Energy balance (thermodynamic calculation)"""

        # Air density at sea level
        air_density = 1.2  # kg/m³
        air_specific_heat = 1005  # J/kg·°C

        # Convert CFM to kg/s
        cfm_to_m3_s = 0.000471947  # 1 CFM = 0.000471947 m³/s
        m3_per_second = proof.airflow_cfm * cfm_to_m3_s
        kg_per_second = m3_per_second * air_density

        # Calculate heat energy
        delta_t = proof.outlet_temp_c - proof.inlet_temp_c
        heat_joules_per_second = kg_per_second * air_specific_heat * delta_t
        heat_watts = heat_joules_per_second
        heat_kwh_per_day = (heat_watts / 1000) * 24

        # Compare with power consumption
        power_kw = proof.power_consumption_watts / 1000
        recovery_pct = (heat_watts / proof.power_consumption_watts) * 100

        # Store calculated values
        proof.calculated_heat_kwh = heat_kwh_per_day
        proof.calculated_recovery_pct = recovery_pct

        # Recovery must be between 5% and 50% (realistic range)
        if recovery_pct < 5:
            return {
                "passed": False,
                "reason": f"Recovery {recovery_pct:.1f}% below minimum 5%",
                "recovery_pct": recovery_pct
            }

        if recovery_pct > 50:
            return {
                "passed": False,
                "reason": f"Recovery {recovery_pct:.1f}% above maximum 50% (impossible)",
                "recovery_pct": recovery_pct
            }

        return {
            "passed": True,
            "recovery_pct": recovery_pct,
            "heat_kwh_per_day": heat_kwh_per_day,
            "confidence": 0.75
        }

    def _check_level_3_facility_proof(self, proof: HeatRecoveryProof) -> Dict:
        """Check Level 3: Facility receives the heat"""

        # Facility should be significantly above ambient
        facility_above_ambient = proof.facility_temp_c - proof.ambient_temp_c

        # If outdoor is 15°C and facility is 28°C, that's +13°C
        # Should be at least +8°C above ambient from heat recovery
        if facility_above_ambient < 8:
            return {
                "passed": False,
                "reason": f"Facility only {facility_above_ambient}°C above ambient (need ≥8°C)",
                "facility_temp": proof.facility_temp_c,
                "ambient_temp": proof.ambient_temp_c
            }

        # Check humidity consistency (cooled air has lower humidity)
        if proof.outlet_humidity_pct >= proof.inlet_humidity_pct:
            return {
                "passed": False,
                "reason": "Outlet humidity should be lower than inlet (cooling effect)",
                "inlet_humidity": proof.inlet_humidity_pct,
                "outlet_humidity": proof.outlet_humidity_pct
            }

        return {
            "passed": True,
            "facility_above_ambient": facility_above_ambient,
            "confidence": 0.90
        }

    def _check_level_4_energy_generation(self, proof: HeatRecoveryProof) -> Dict:
        """Check Level 4: Smart meter validates energy generation"""

        if proof.energy_generated_kwh <= 0:
            return {
                "passed": False,
                "reason": "No measurable energy generation reported",
                "energy_kwh": proof.energy_generated_kwh
            }

        # Energy should be reasonable given heat calculation
        # Rough estimate: 1 kW heat ≈ 0.7-0.8 kWh/day usable energy (with conversion losses)
        heat_watts = (proof.calculated_heat_kwh / 24) * 1000 if proof.calculated_heat_kwh else 0
        expected_daily_kwh = (heat_watts / 1000) * 24 * 0.75  # 75% efficiency

        if proof.energy_generated_kwh > expected_daily_kwh * 1.5:
            return {
                "passed": False,
                "reason": f"Energy generation {proof.energy_generated_kwh} kWh exceeds calculated {expected_daily_kwh:.1f} kWh",
                "energy_kwh": proof.energy_generated_kwh,
                "expected_kwh": expected_daily_kwh
            }

        return {
            "passed": True,
            "energy_kwh": proof.energy_generated_kwh,
            "confidence": 1.0
        }

    def _detect_fraud(self, proof: HeatRecoveryProof, verification: HeatProofVerification) -> Dict:
        """Fraud detection mechanisms"""
        violations = []
        fraud_detected = False

        # Check 1: Impossible physics
        if proof.outlet_temp_c > proof.inlet_temp_c + 100:
            violations.append("Impossible temperature delta (>100°C)")
            fraud_detected = True

        if proof.calculated_recovery_pct > 100:
            violations.append("Recovery percentage exceeds 100% (impossible)")
            fraud_detected = True

        # Check 2: Sensor tampering
        if proof.outlet_temp_c - proof.inlet_temp_c > 10 and proof.inlet_humidity_pct >= proof.outlet_humidity_pct:
            violations.append("Humidity unchanged despite major temperature change (sensor inconsistency)")
            fraud_detected = True

        # Check 3: Abrupt changes (would indicate data manipulation)
        if proof.timestamp:
            # This would compare with previous readings
            pass

        # Check 4: Consistency violations
        if proof.facility_temp_c > proof.outlet_temp_c + 5:
            violations.append("Facility temperature higher than heat source (impossible)")
            fraud_detected = True

        # Check 5: Energy generation impossibility
        if proof.energy_generated_kwh > 200:  # Per 5-minute interval
            violations.append(f"Energy generation {proof.energy_generated_kwh} kWh in 5 min (exceeds physics)")
            fraud_detected = True

        # Check 6: Missing critical sensors
        if proof.sensors_online < proof.sensors_total * 0.9:
            violations.append(f"Only {proof.sensors_online}/{proof.sensors_total} sensors online (need >90%)")
            fraud_detected = True

        # Check 7: Facility proof with GPS verification
        if proof.gps_accuracy_meters > 100:
            violations.append("GPS accuracy too low for facility verification")
            fraud_detected = True

        return {
            "fraud_detected": fraud_detected,
            "violations": violations
        }

    def _log_fraud_detection(self, proof: HeatRecoveryProof, fraud_results: Dict):
        """Log fraud detection for review"""
        fraud_log = []
        if self.fraud_log_file.exists():
            try:
                fraud_log = json.loads(self.fraud_log_file.read_text())
            except:
                fraud_log = []

        fraud_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "miner_address": proof.miner_address,
            "violations": fraud_results["violations"],
            "proof_data": {
                "recovery_pct": proof.calculated_recovery_pct,
                "delta_t": proof.outlet_temp_c - proof.inlet_temp_c
            }
        })

        self.fraud_log_file.write_text(json.dumps(fraud_log[-1000:], indent=2))

    def _store_proof(self, proof: HeatRecoveryProof, verification: HeatProofVerification):
        """Store proof record"""
        proofs = {}
        if self.proofs_file.exists():
            try:
                proofs = json.loads(self.proofs_file.read_text())
            except:
                proofs = {}

        if proof.miner_address not in proofs:
            proofs[proof.miner_address] = []

        proofs[proof.miner_address].append({
            "proof_id": verification.proof_id,
            "timestamp": proof.timestamp,
            "is_valid": verification.is_valid,
            "proof_level": verification.proof_level.name,
            "recovery_pct": proof.calculated_recovery_pct,
            "bonus_multiplier": verification.bonus_multiplier
        })

        # Keep last 1000 proofs per miner
        if len(proofs[proof.miner_address]) > 1000:
            proofs[proof.miner_address] = proofs[proof.miner_address][-1000:]

        self.proofs_file.write_text(json.dumps(proofs, indent=2))


# ═══════════════════════════════════════════════════════════════
# GLOBAL INSTANCE
# ═══════════════════════════════════════════════════════════════

_heat_verifier: Optional[HeatRecoveryVerifier] = None


def initialize_heat_verifier() -> HeatRecoveryVerifier:
    """Initialize global heat recovery verifier"""
    global _heat_verifier
    _heat_verifier = HeatRecoveryVerifier()
    return _heat_verifier


def get_heat_verifier() -> Optional[HeatRecoveryVerifier]:
    """Get global heat recovery verifier"""
    return _heat_verifier
