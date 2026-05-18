"""
Bitcoin Heat Recovery Mining - Dual-Chain Farming System
Enables large farm operators to mine Bitcoin AND earn Thronos heat bonuses simultaneously.

Architecture:
- Miners run Bitcoin mining + Thronos heat sensors in parallel
- Heat from BTC ASICs → measured via IoT sensors → Thronos heat proofs
- BTC mining yields Bitcoin, heat recovery yields THR bonuses
- Bridge settles value between chains for large-scale operations
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path

class MiningHardware(Enum):
    """Bitcoin mining hardware supported for heat recovery"""
    ANTMINER_S19_PRO = {"power_w": 3250, "hashrate_th": 110, "efficiency": 29.5, "heat_factor": 0.95}
    ANTMINER_S19_PRO_MAX = {"power_w": 3500, "hashrate_th": 140, "efficiency": 25.0, "heat_factor": 0.97}
    ANTMINER_S21 = {"power_w": 3360, "hashrate_th": 200, "efficiency": 16.8, "heat_factor": 0.98}
    ANTMINER_T21 = {"power_w": 3610, "hashrate_th": 252, "efficiency": 14.3, "heat_factor": 0.98}
    WHATSMINER_M30S = {"power_w": 3400, "hashrate_th": 112, "efficiency": 30.4, "heat_factor": 0.94}
    WHATSMINER_M32 = {"power_w": 3472, "hashrate_th": 136, "efficiency": 25.5, "heat_factor": 0.96}
    WHATSMINER_M50 = {"power_w": 3245, "hashrate_th": 135, "efficiency": 24.0, "heat_factor": 0.95}
    AVALON_A1066 = {"power_w": 3254, "hashrate_th": 50, "efficiency": 65.1, "heat_factor": 0.92}
    AVALON_A1246 = {"power_w": 3420, "hashrate_th": 120, "efficiency": 28.5, "heat_factor": 0.96}
    CGMINER_CUSTOM = {"power_w": 3500, "hashrate_th": 100, "efficiency": 35.0, "heat_factor": 0.90}

    @property
    def specs(self) -> Dict:
        return self.value

class BtcHeatTier(Enum):
    """Heat recovery tiers based on farm efficiency"""
    TIER_BASIC = {"recovery_min": 0.05, "recovery_max": 0.10, "bonus": 0.05}
    TIER_STANDARD = {"recovery_min": 0.10, "recovery_max": 0.15, "bonus": 0.15}
    TIER_ADVANCED = {"recovery_min": 0.15, "recovery_max": 0.25, "bonus": 0.25}
    TIER_ENTERPRISE = {"recovery_min": 0.25, "recovery_max": 0.50, "bonus": 0.40}

    @property
    def specs(self) -> Dict:
        return self.value

class BtcMiningStatus(Enum):
    """Status of BTC heat mining operation"""
    REGISTERED = "registered"
    MINING = "mining"
    VALIDATING = "validating"
    ACTIVE = "active"
    PAUSED = "paused"
    SUSPENDED = "suspended"
    BANNED = "banned"

@dataclass
class BtcMiner:
    """BTC miner with heat recovery capability"""
    address: str
    farm_name: str
    hardware_type: MiningHardware
    unit_count: int
    installation_date: str
    location_latitude: float
    location_longitude: float
    ambient_temp_c: float
    facility_photos: List[str] = field(default_factory=list)

    @property
    def total_power_w(self) -> float:
        return self.hardware_type.specs["power_w"] * self.unit_count

    @property
    def total_hashrate_th(self) -> float:
        return self.hardware_type.specs["hashrate_th"] * self.unit_count

    @property
    def theoretical_heat_kw(self) -> float:
        """Heat output in kW (95% of power becomes heat)"""
        return (self.total_power_w * self.hardware_type.specs["heat_factor"]) / 1000.0

@dataclass
class BtcHeatProof:
    """Bitcoin mining heat recovery proof"""
    proof_id: str
    btc_address: str
    thronos_address: str
    miner: BtcMiner
    mining_duration_minutes: int
    btc_block_height: int
    btc_transaction_hash: str

    sensor_data: Dict = field(default_factory=dict)  # inlet_temp, outlet_temp, humidity, airflow, etc
    measured_heat_kwh: float = 0.0
    recovery_percentage: float = 0.0
    heat_to_energy_kwh: float = 0.0

    submitted_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    validation_level: int = 0  # 0-4
    is_valid: bool = False

    @property
    def expected_heat_kwh(self) -> float:
        """Expected heat based on power consumption"""
        return (self.miner.total_power_w * (self.mining_duration_minutes / 60.0)) / 1000.0

@dataclass
class BtcFarmComplianceRecord:
    """Compliance tracking for BTC heat mining farm"""
    btc_address: str
    status: BtcMiningStatus = BtcMiningStatus.REGISTERED
    current_tier: BtcHeatTier = BtcHeatTier.TIER_BASIC

    first_proof_date: Optional[str] = None
    last_proof_date: Optional[str] = None
    proof_submission_count: int = 0
    fraud_violations: int = 0

    reputation_score: float = 75.0  # 0-100
    total_heat_bonus_thr: float = 0.0
    average_recovery_percent: float = 0.0

    btc_mined_total: float = 0.0  # Satoshis
    thronos_earned_total: float = 0.0

    equipment_verified: bool = False
    equipment_verification_date: Optional[str] = None
    monitoring_flags: List[str] = field(default_factory=list)

class BtcHeatMiningValidator:
    """Validates Bitcoin mining heat proofs"""

    # Validation thresholds
    MIN_RECOVERY_PERCENT = 0.05
    MAX_RECOVERY_PERCENT = 0.50
    MIN_TEMP_DIFF = 5.0  # Celsius
    MAX_TEMP_DIFF = 80.0
    HUMIDITY_DROP_MIN = 5.0  # Percentage points
    SENSOR_UPTIME_MIN = 0.90

    def validate_heat_proof(self, proof: BtcHeatProof) -> Tuple[bool, int, List[str], float]:
        """
        Validate BTC mining heat proof
        Returns: (is_valid, validation_level, anomalies, bonus_multiplier)
        """
        anomalies = []
        validation_level = 0
        bonus_multiplier = 0.0

        # Level 1: Temperature differential validation
        level1_valid = self._check_level1_temperature(proof, anomalies)
        if level1_valid:
            validation_level = 1
            bonus_multiplier = 0.5
        else:
            return False, 0, anomalies, 0.0

        # Level 2: Energy balance validation
        level2_valid = self._check_level2_energy_balance(proof, anomalies)
        if level2_valid:
            validation_level = 2
            bonus_multiplier = 0.85

        # Level 3: Facility proof validation
        level3_valid = self._check_level3_facility_proof(proof, anomalies)
        if level3_valid:
            validation_level = 3
            bonus_multiplier = 0.95

        # Level 4: Energy generation validation
        level4_valid = self._check_level4_energy_generation(proof, anomalies)
        if level4_valid:
            validation_level = 4
            bonus_multiplier = 1.0

        # Fraud detection
        fraud_detected = self._detect_fraud(proof, anomalies)
        if fraud_detected:
            return False, 0, anomalies, 0.0

        is_valid = validation_level >= 1
        return is_valid, validation_level, anomalies, bonus_multiplier

    def _check_level1_temperature(self, proof: BtcHeatProof, anomalies: List[str]) -> bool:
        """Level 1: Temperature differential validation"""
        inlet_temp = proof.sensor_data.get("inlet_temp_c", 0)
        outlet_temp = proof.sensor_data.get("outlet_temp_c", 0)

        temp_diff = outlet_temp - inlet_temp
        if temp_diff < self.MIN_TEMP_DIFF:
            anomalies.append(f"Temperature differential too low: {temp_diff}°C (min {self.MIN_TEMP_DIFF})")
            return False

        if temp_diff > self.MAX_TEMP_DIFF:
            anomalies.append(f"Impossible temperature differential: {temp_diff}°C (max {self.MAX_TEMP_DIFF})")
            return False

        # Calculate measured heat
        airflow_m3_per_min = proof.sensor_data.get("airflow_m3_per_min", 0)
        air_density = 1.2  # kg/m³
        air_specific_heat = 1005  # J/(kg·K)

        measured_heat_kw = (airflow_m3_per_min * air_density * air_specific_heat * temp_diff) / 60000
        proof.measured_heat_kwh = measured_heat_kw * (proof.mining_duration_minutes / 60.0)

        return True

    def _check_level2_energy_balance(self, proof: BtcHeatProof, anomalies: List[str]) -> bool:
        """Level 2: Energy balance validation"""
        expected_heat = proof.expected_heat_kwh
        measured_heat = proof.measured_heat_kwh

        if expected_heat == 0:
            return False

        recovery = measured_heat / expected_heat
        proof.recovery_percentage = recovery

        if recovery < self.MIN_RECOVERY_PERCENT:
            anomalies.append(f"Heat recovery too low: {recovery:.1%} (min {self.MIN_RECOVERY_PERCENT:.1%})")
            return False

        if recovery > self.MAX_RECOVERY_PERCENT:
            anomalies.append(f"Heat recovery unrealistic: {recovery:.1%} (max {self.MAX_RECOVERY_PERCENT:.1%})")
            return False

        return True

    def _check_level3_facility_proof(self, proof: BtcHeatProof, anomalies: List[str]) -> bool:
        """Level 3: Facility receives and retains heat"""
        ambient_temp = proof.miner.ambient_temp_c
        facility_inlet = proof.sensor_data.get("facility_inlet_temp_c")
        facility_outlet = proof.sensor_data.get("facility_outlet_temp_c")

        if facility_inlet is None or facility_outlet is None:
            anomalies.append("Missing facility temperature readings")
            return False

        # Facility should be warmer than ambient
        if facility_inlet < ambient_temp + 5:
            anomalies.append(f"Facility temp too close to ambient: {facility_inlet}°C vs {ambient_temp}°C")
            return False

        # Outlet should be cooler than inlet (heat recovery happening)
        if facility_outlet >= facility_inlet:
            anomalies.append("Facility outlet not cooler than inlet (no heat recovery)")
            return False

        return True

    def _check_level4_energy_generation(self, proof: BtcHeatProof, anomalies: List[str]) -> bool:
        """Level 4: Actual energy being generated/captured"""
        energy_generated = proof.sensor_data.get("energy_generated_kwh", 0)
        measured_heat = proof.measured_heat_kwh

        if energy_generated <= 0:
            anomalies.append("No energy generation detected from heat recovery system")
            return False

        # Energy should be proportional to heat recovery (not more than 50% of heat)
        if energy_generated > measured_heat * 0.50:
            anomalies.append(f"Energy generation unrealistic: {energy_generated}kWh from {measured_heat}kWh heat")
            return False

        proof.heat_to_energy_kwh = energy_generated
        return True

    def _detect_fraud(self, proof: BtcHeatProof, anomalies: List[str]) -> bool:
        """7-point fraud detection"""
        violation_count = 0

        # Check 1: Impossible physics
        inlet = proof.sensor_data.get("inlet_temp_c", 0)
        outlet = proof.sensor_data.get("outlet_temp_c", 0)
        if outlet - inlet > 100:
            anomalies.append("Fraud: Impossible temperature differential detected")
            violation_count += 1

        # Check 2: Sensor tampering (inconsistent readings)
        humidity_in = proof.sensor_data.get("humidity_inlet_percent", 0)
        humidity_out = proof.sensor_data.get("humidity_outlet_percent", 0)
        if humidity_in < humidity_out + 5:
            anomalies.append("Fraud: Humidity inversion detected (sensor tampering)")
            violation_count += 1

        # Check 3: GPS accuracy (should be within expected farm location)
        gps_lat = proof.sensor_data.get("gps_latitude", 0)
        gps_lon = proof.sensor_data.get("gps_longitude", 0)
        distance = self._gps_distance(proof.miner.location_latitude, proof.miner.location_longitude, gps_lat, gps_lon)
        if distance > 1.0:  # More than 1km away
            anomalies.append(f"Fraud: GPS location mismatch ({distance:.2f}km from farm)")
            violation_count += 1

        # Check 4: Sensor uptime verification
        uptime = proof.sensor_data.get("sensor_uptime_percent", 100)
        if uptime < 90:
            anomalies.append(f"Fraud: Sensor uptime too low ({uptime}%)")
            violation_count += 1

        # Check 5: Energy generation sanity
        energy_gen = proof.sensor_data.get("energy_generated_kwh", 0)
        if energy_gen > proof.miner.theoretical_heat_kw * 0.30:  # More than 30% of theoretical max
            anomalies.append("Fraud: Energy generation exceeds theoretical maximum")
            violation_count += 1

        # Check 6: Mining duration sanity
        if proof.mining_duration_minutes < 5 or proof.mining_duration_minutes > 1440:
            anomalies.append(f"Fraud: Suspicious mining duration ({proof.mining_duration_minutes} minutes)")
            violation_count += 1

        # Check 7: Recovery percentage sanity
        if proof.recovery_percentage < 0.05 or proof.recovery_percentage > 0.50:
            anomalies.append(f"Fraud: Recovery percentage out of range ({proof.recovery_percentage:.1%})")
            violation_count += 1

        return violation_count >= 2  # 2+ violations = fraud

    @staticmethod
    def _gps_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between GPS coordinates in km (approximate)"""
        from math import sin, cos, sqrt, atan2, radians
        R = 6371  # Earth radius in km
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        return R * c

class BtcHeatMiningTracker:
    """Tracks BTC heat mining farms and compliance"""

    def __init__(self, data_dir: str = "/data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)

        self.miners_file = self.data_dir / "btc_miners.json"
        self.compliance_file = self.data_dir / "btc_compliance.json"
        self.proofs_file = self.data_dir / "btc_heat_proofs.json"
        self.fraud_log_file = self.data_dir / "btc_fraud_log.json"

        self.miners: Dict[str, BtcMiner] = self._load_json(self.miners_file, {})
        self.compliance: Dict[str, BtcFarmComplianceRecord] = {}
        self.proofs: Dict[str, BtcHeatProof] = self._load_json(self.proofs_file, {})
        self.fraud_log: List[Dict] = self._load_json(self.fraud_log_file, [])
        self.validator = BtcHeatMiningValidator()

        self._load_compliance()

    def _load_json(self, filepath: Path, default=None) -> dict:
        """Load JSON file or return default"""
        try:
            if filepath.exists():
                with open(filepath) as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
        return default or {}

    def _save_json(self, filepath: Path, data):
        """Save data to JSON file"""
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    def _load_compliance(self):
        """Load compliance records"""
        try:
            with open(self.compliance_file) as f:
                data = json.load(f)
                for addr, record in data.items():
                    self.compliance[addr] = BtcFarmComplianceRecord(
                        btc_address=addr,
                        status=BtcMiningStatus(record.get("status", "registered")),
                        current_tier=BtcHeatTier[record.get("current_tier", "TIER_BASIC")],
                        first_proof_date=record.get("first_proof_date"),
                        last_proof_date=record.get("last_proof_date"),
                        proof_submission_count=record.get("proof_submission_count", 0),
                        fraud_violations=record.get("fraud_violations", 0),
                        reputation_score=record.get("reputation_score", 75.0),
                        total_heat_bonus_thr=record.get("total_heat_bonus_thr", 0.0),
                        average_recovery_percent=record.get("average_recovery_percent", 0.0),
                        btc_mined_total=record.get("btc_mined_total", 0.0),
                        thronos_earned_total=record.get("thronos_earned_total", 0.0),
                        equipment_verified=record.get("equipment_verified", False),
                        equipment_verification_date=record.get("equipment_verification_date"),
                        monitoring_flags=record.get("monitoring_flags", [])
                    )
        except (json.JSONDecodeError, IOError, FileNotFoundError):
            pass

    def register_btc_miner(self, btc_address: str, farm_name: str, hardware_type: str,
                          unit_count: int, location_lat: float, location_lon: float,
                          ambient_temp: float) -> bool:
        """Register a BTC mining farm for heat recovery"""
        if btc_address in self.miners:
            return False  # Already registered

        try:
            hw = MiningHardware[hardware_type.upper()]
        except KeyError:
            return False

        miner = BtcMiner(
            address=btc_address,
            farm_name=farm_name,
            hardware_type=hw,
            unit_count=unit_count,
            installation_date=datetime.utcnow().isoformat(),
            location_latitude=location_lat,
            location_longitude=location_lon,
            ambient_temp_c=ambient_temp
        )

        self.miners[btc_address] = miner
        self.compliance[btc_address] = BtcFarmComplianceRecord(btc_address=btc_address)

        self._save_json(self.miners_file, {addr: vars(m) for addr, m in self.miners.items()})
        self._save_compliance()

        return True

    def submit_heat_proof(self, btc_address: str, thronos_address: str,
                         mining_duration_minutes: int, btc_block_height: int,
                         btc_tx_hash: str, sensor_data: Dict) -> Tuple[bool, str, int, float]:
        """
        Submit BTC mining heat recovery proof
        Returns: (is_valid, proof_id, validation_level, bonus_multiplier)
        """
        if btc_address not in self.miners:
            return False, "", 0, 0.0

        proof_id = self._generate_proof_id(btc_address, btc_block_height)
        miner = self.miners[btc_address]

        proof = BtcHeatProof(
            proof_id=proof_id,
            btc_address=btc_address,
            thronos_address=thronos_address,
            miner=miner,
            mining_duration_minutes=mining_duration_minutes,
            btc_block_height=btc_block_height,
            btc_transaction_hash=btc_tx_hash,
            sensor_data=sensor_data
        )

        # Validate proof
        is_valid, level, anomalies, bonus_mult = self.validator.validate_heat_proof(proof)
        proof.is_valid = is_valid
        proof.validation_level = level

        # Store proof
        self.proofs[proof_id] = proof
        self._save_proofs()

        # Update compliance
        compliance = self.compliance[btc_address]
        compliance.last_proof_date = datetime.utcnow().isoformat()
        if not compliance.first_proof_date:
            compliance.first_proof_date = compliance.last_proof_date

        compliance.proof_submission_count += 1

        if is_valid:
            compliance.equipment_verified = True
            compliance.equipment_verification_date = datetime.utcnow().isoformat()
            self._update_tier(btc_address, proof.recovery_percentage)
            compliance.status = BtcMiningStatus.ACTIVE
        else:
            compliance.fraud_violations += 1
            if compliance.fraud_violations >= 3:
                compliance.status = BtcMiningStatus.BANNED
            elif compliance.fraud_violations >= 2:
                compliance.status = BtcMiningStatus.SUSPENDED
            else:
                compliance.status = BtcMiningStatus.MONITORING

            self.fraud_log.append({
                "timestamp": datetime.utcnow().isoformat(),
                "btc_address": btc_address,
                "proof_id": proof_id,
                "anomalies": anomalies,
                "violation_count": compliance.fraud_violations
            })
            self._save_json(self.fraud_log_file, self.fraud_log)

        self._save_compliance()

        return is_valid, proof_id, level, bonus_mult

    def _update_tier(self, btc_address: str, recovery_percent: float):
        """Auto-upgrade tier based on recovery percentage"""
        compliance = self.compliance[btc_address]

        if recovery_percent >= BtcHeatTier.TIER_ENTERPRISE.specs["recovery_min"]:
            compliance.current_tier = BtcHeatTier.TIER_ENTERPRISE
        elif recovery_percent >= BtcHeatTier.TIER_ADVANCED.specs["recovery_min"]:
            compliance.current_tier = BtcHeatTier.TIER_ADVANCED
        elif recovery_percent >= BtcHeatTier.TIER_STANDARD.specs["recovery_min"]:
            compliance.current_tier = BtcHeatTier.TIER_STANDARD
        else:
            compliance.current_tier = BtcHeatTier.TIER_BASIC

    def get_farm_status(self, btc_address: str) -> Optional[Dict]:
        """Get complete farm status and compliance"""
        if btc_address not in self.miners:
            return None

        miner = self.miners[btc_address]
        compliance = self.compliance.get(btc_address)

        return {
            "btc_address": btc_address,
            "farm_name": miner.farm_name,
            "hardware": miner.hardware_type.name,
            "unit_count": miner.unit_count,
            "total_power_kw": miner.total_power_w / 1000,
            "total_hashrate_th": miner.total_hashrate_th,
            "theoretical_heat_kw": miner.theoretical_heat_kw,
            "location": {"latitude": miner.location_latitude, "longitude": miner.location_longitude},
            "status": compliance.status.value if compliance else "unknown",
            "tier": compliance.current_tier.name if compliance else "TIER_BASIC",
            "equipment_verified": compliance.equipment_verified if compliance else False,
            "reputation_score": compliance.reputation_score if compliance else 75.0,
            "proofs_submitted": compliance.proof_submission_count if compliance else 0,
            "btc_mined": compliance.btc_mined_total if compliance else 0.0,
            "thronos_earned": compliance.thronos_earned_total if compliance else 0.0,
            "average_recovery_percent": compliance.average_recovery_percent if compliance else 0.0
        }

    def calculate_heat_bonus(self, btc_address: str, btc_mined_satoshis: float) -> float:
        """Calculate THR bonus based on heat recovery tier and BTC mined"""
        if btc_address not in self.compliance:
            return 0.0

        compliance = self.compliance[btc_address]
        tier_bonus = compliance.current_tier.specs["bonus"]

        # Base reward: 8 THR per block, plus tier bonus
        # For heat mining: bonus is calculated per satoshi mined
        base_reward_thr_per_btc = 8.0 * 100000000  # THR per satoshi (simplified)
        bonus = (btc_mined_satoshis / 100000000) * 8 * tier_bonus

        return bonus

    def _generate_proof_id(self, btc_address: str, block_height: int) -> str:
        """Generate unique proof ID"""
        data = f"{btc_address}{block_height}{datetime.utcnow().isoformat()}".encode()
        return hashlib.sha256(data).hexdigest()[:16]

    def _save_proofs(self):
        """Save proofs to file"""
        self._save_json(self.proofs_file, {pid: vars(p) for pid, p in self.proofs.items()})

    def _save_compliance(self):
        """Save compliance records to file"""
        data = {}
        for addr, record in self.compliance.items():
            data[addr] = {
                "status": record.status.value,
                "current_tier": record.current_tier.name,
                "first_proof_date": record.first_proof_date,
                "last_proof_date": record.last_proof_date,
                "proof_submission_count": record.proof_submission_count,
                "fraud_violations": record.fraud_violations,
                "reputation_score": record.reputation_score,
                "total_heat_bonus_thr": record.total_heat_bonus_thr,
                "average_recovery_percent": record.average_recovery_percent,
                "btc_mined_total": record.btc_mined_total,
                "thronos_earned_total": record.thronos_earned_total,
                "equipment_verified": record.equipment_verified,
                "equipment_verification_date": record.equipment_verification_date,
                "monitoring_flags": record.monitoring_flags
            }
        self._save_json(self.compliance_file, data)
