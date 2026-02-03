"""VerifyID Service for Thronos V3.6

This service manages device verification and registration for:
- ASICs and mining hardware
- GPS telemetry devices
- AI training nodes
- Driver/Vehicle nodes for autonomous driving rewards

The service uses the main SQLite database (ledger.sqlite3) for persistence
and integrates with the rewards system for Train-to-Earn (T2E) functionality.

Database Tables:
- verified_devices: Registered and verified devices/ASICs
- device_telemetry: GPS/sensor telemetry from devices
- driver_rewards: Rewards tracking for AI-trained drivers
- training_contributions: AI model training contributions
"""

from __future__ import annotations

import os
import json
import time
import hashlib
import secrets
import sqlite3
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)

# Configuration
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
VERIFY_DB_FILE = os.path.join(DATA_DIR, "ledger.sqlite3")


class DeviceType(Enum):
    """Supported device types for verification"""
    ASIC = "asic"
    GPU_MINER = "gpu_miner"
    CPU_MINER = "cpu_miner"
    GPS_NODE = "gps_node"
    VEHICLE_NODE = "vehicle_node"
    AI_TRAINER = "ai_trainer"
    MUSIC_NODE = "music_node"


class VerificationStatus(Enum):
    """Device verification status"""
    PENDING = "pending"
    VERIFIED = "verified"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


@dataclass
class VerifiedDevice:
    """Represents a verified device in the system"""
    device_id: str
    device_type: str
    owner_wallet: str
    hardware_hash: str  # Unique hardware identifier
    registration_time: str
    last_seen: str
    status: str
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DeviceTelemetry:
    """GPS/Sensor telemetry from a device"""
    device_id: str
    timestamp: str
    gps_lat: Optional[float]
    gps_lng: Optional[float]
    speed_kmh: Optional[float]
    battery_percent: Optional[int]
    mode: str  # "AI_AUTOPILOT", "MANUAL", "TRAINING"
    sensor_data: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DriverReward:
    """Reward entry for drivers/AI training"""
    reward_id: str
    device_id: str
    wallet_address: str
    reward_type: str  # "trip_discount", "training_bonus", "music_royalty"
    amount_thr: float
    crosschain_asset: Optional[str]  # For crosschain rewards
    crosschain_amount: Optional[float]
    trip_distance_km: Optional[float]
    training_contribution: Optional[float]
    created_at: str
    claimed: bool
    claimed_at: Optional[str]


class VerifyIDService:
    """
    Main service for device verification and management.

    This service handles:
    1. Device registration and verification
    2. Telemetry collection and GPS tracking
    3. Driver rewards for AI-trained trips
    4. Training contributions tracking
    """

    def __init__(self, db_path: str = None):
        self.db_path = db_path or VERIFY_DB_FILE
        self._init_tables()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with Row factory"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self):
        """Initialize VerifyID tables (idempotent)"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        with self._get_connection() as conn:
            # Verified devices table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS verified_devices (
                    device_id TEXT PRIMARY KEY,
                    device_type TEXT NOT NULL,
                    owner_wallet TEXT NOT NULL,
                    hardware_hash TEXT UNIQUE NOT NULL,
                    registration_time TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    metadata TEXT,
                    hashrate_avg REAL DEFAULT 0.0,
                    total_rewards_earned REAL DEFAULT 0.0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_devices_owner ON verified_devices(owner_wallet)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_devices_type ON verified_devices(device_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_devices_status ON verified_devices(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_devices_hardware ON verified_devices(hardware_hash)")

            # Device telemetry table (GPS, sensors)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS device_telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    gps_lat REAL,
                    gps_lng REAL,
                    speed_kmh REAL,
                    battery_percent INTEGER,
                    mode TEXT,
                    sensor_data TEXT,
                    indexed_at INTEGER NOT NULL,
                    FOREIGN KEY (device_id) REFERENCES verified_devices(device_id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_device ON device_telemetry(device_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp ON device_telemetry(timestamp DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_mode ON device_telemetry(mode)")

            # Driver rewards table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS driver_rewards (
                    reward_id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    wallet_address TEXT NOT NULL,
                    reward_type TEXT NOT NULL,
                    amount_thr REAL NOT NULL DEFAULT 0.0,
                    crosschain_asset TEXT,
                    crosschain_amount REAL,
                    trip_distance_km REAL,
                    training_contribution REAL,
                    created_at TEXT NOT NULL,
                    claimed INTEGER DEFAULT 0,
                    claimed_at TEXT,
                    FOREIGN KEY (device_id) REFERENCES verified_devices(device_id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rewards_wallet ON driver_rewards(wallet_address)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rewards_device ON driver_rewards(device_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rewards_claimed ON driver_rewards(claimed)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rewards_type ON driver_rewards(reward_type)")

            # Training contributions table (for AI model training)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS training_contributions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    wallet_address TEXT NOT NULL,
                    contribution_type TEXT NOT NULL,
                    data_hash TEXT NOT NULL,
                    data_size_bytes INTEGER,
                    quality_score REAL,
                    reward_amount REAL,
                    created_at TEXT NOT NULL,
                    processed INTEGER DEFAULT 0,
                    FOREIGN KEY (device_id) REFERENCES verified_devices(device_id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_contrib_wallet ON training_contributions(wallet_address)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_contrib_device ON training_contributions(device_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_contrib_type ON training_contributions(contribution_type)")

            conn.commit()
            logger.info("[VerifyID] Database tables initialized")

    # ─── Device Registration & Verification ───────────────────────────────

    def generate_device_id(self, device_type: str, hardware_info: Dict[str, Any]) -> str:
        """Generate unique device ID from hardware info"""
        hw_str = json.dumps(hardware_info, sort_keys=True)
        hw_hash = hashlib.sha256(hw_str.encode()).hexdigest()[:16]
        prefix = device_type[:3].upper()
        return f"{prefix}-{hw_hash}-{secrets.token_hex(4)}"

    def generate_hardware_hash(self, hardware_info: Dict[str, Any]) -> str:
        """Generate hardware fingerprint hash"""
        hw_str = json.dumps(hardware_info, sort_keys=True)
        return hashlib.sha256(hw_str.encode()).hexdigest()

    def register_device(
        self,
        device_type: str,
        owner_wallet: str,
        hardware_info: Dict[str, Any],
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Register a new device for verification.

        Args:
            device_type: Type of device (asic, gps_node, vehicle_node, etc.)
            owner_wallet: THR wallet address of the owner
            hardware_info: Hardware identification data
            metadata: Additional device metadata

        Returns:
            Registration result with device_id
        """
        try:
            hardware_hash = self.generate_hardware_hash(hardware_info)

            # Check if device already exists
            with self._get_connection() as conn:
                existing = conn.execute(
                    "SELECT device_id, status FROM verified_devices WHERE hardware_hash = ?",
                    (hardware_hash,)
                ).fetchone()

                if existing:
                    return {
                        "ok": False,
                        "error": "Device already registered",
                        "device_id": existing["device_id"],
                        "status": existing["status"]
                    }

                device_id = self.generate_device_id(device_type, hardware_info)
                now = datetime.utcnow().isoformat() + "Z"

                conn.execute("""
                    INSERT INTO verified_devices
                    (device_id, device_type, owner_wallet, hardware_hash,
                     registration_time, last_seen, status, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    device_id,
                    device_type,
                    owner_wallet,
                    hardware_hash,
                    now,
                    now,
                    VerificationStatus.PENDING.value,
                    json.dumps(metadata or {})
                ))
                conn.commit()

                logger.info(f"[VerifyID] Device registered: {device_id} ({device_type}) for {owner_wallet}")

                return {
                    "ok": True,
                    "device_id": device_id,
                    "status": VerificationStatus.PENDING.value,
                    "message": "Device registered successfully. Awaiting verification."
                }

        except Exception as e:
            logger.exception(f"[VerifyID] Registration error: {e}")
            return {"ok": False, "error": str(e)}

    def verify_device(self, device_id: str, admin_secret: str = None) -> Dict[str, Any]:
        """
        Verify a pending device (admin function).

        For ASICs, this confirms the device is legitimate.
        For GPS nodes, this enables telemetry tracking.
        """
        try:
            with self._get_connection() as conn:
                device = conn.execute(
                    "SELECT * FROM verified_devices WHERE device_id = ?",
                    (device_id,)
                ).fetchone()

                if not device:
                    return {"ok": False, "error": "Device not found"}

                if device["status"] == VerificationStatus.VERIFIED.value:
                    return {"ok": True, "message": "Device already verified"}

                now = datetime.utcnow().isoformat() + "Z"
                conn.execute("""
                    UPDATE verified_devices
                    SET status = ?, last_seen = ?
                    WHERE device_id = ?
                """, (VerificationStatus.VERIFIED.value, now, device_id))
                conn.commit()

                logger.info(f"[VerifyID] Device verified: {device_id}")

                return {
                    "ok": True,
                    "device_id": device_id,
                    "status": VerificationStatus.VERIFIED.value,
                    "message": "Device verified successfully"
                }

        except Exception as e:
            logger.exception(f"[VerifyID] Verification error: {e}")
            return {"ok": False, "error": str(e)}

    def check_device_exists(self, device_id: str = None, hardware_hash: str = None) -> Dict[str, Any]:
        """
        Check if a device exists in the verification database.

        This is the main endpoint for the verification check the user mentioned.
        """
        try:
            with self._get_connection() as conn:
                if device_id:
                    device = conn.execute(
                        "SELECT * FROM verified_devices WHERE device_id = ?",
                        (device_id,)
                    ).fetchone()
                elif hardware_hash:
                    device = conn.execute(
                        "SELECT * FROM verified_devices WHERE hardware_hash = ?",
                        (hardware_hash,)
                    ).fetchone()
                else:
                    return {"ok": False, "error": "device_id or hardware_hash required"}

                if not device:
                    return {
                        "ok": True,
                        "exists": False,
                        "verified": False
                    }

                return {
                    "ok": True,
                    "exists": True,
                    "verified": device["status"] == VerificationStatus.VERIFIED.value,
                    "device_id": device["device_id"],
                    "device_type": device["device_type"],
                    "status": device["status"],
                    "owner_wallet": device["owner_wallet"],
                    "last_seen": device["last_seen"]
                }

        except Exception as e:
            logger.exception(f"[VerifyID] Check error: {e}")
            return {"ok": False, "error": str(e)}

    def get_device(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Get full device details"""
        try:
            with self._get_connection() as conn:
                device = conn.execute(
                    "SELECT * FROM verified_devices WHERE device_id = ?",
                    (device_id,)
                ).fetchone()

                if not device:
                    return None

                return dict(device)
        except Exception as e:
            logger.exception(f"[VerifyID] Get device error: {e}")
            return None

    def list_devices_by_wallet(self, wallet_address: str) -> List[Dict[str, Any]]:
        """List all devices owned by a wallet"""
        try:
            with self._get_connection() as conn:
                devices = conn.execute(
                    """SELECT * FROM verified_devices
                       WHERE owner_wallet = ?
                       ORDER BY registration_time DESC""",
                    (wallet_address,)
                ).fetchall()

                return [dict(d) for d in devices]
        except Exception as e:
            logger.exception(f"[VerifyID] List devices error: {e}")
            return []

    def list_devices_by_type(self, device_type: str, verified_only: bool = True) -> List[Dict[str, Any]]:
        """List all devices of a specific type"""
        try:
            with self._get_connection() as conn:
                if verified_only:
                    devices = conn.execute(
                        """SELECT * FROM verified_devices
                           WHERE device_type = ? AND status = ?
                           ORDER BY last_seen DESC""",
                        (device_type, VerificationStatus.VERIFIED.value)
                    ).fetchall()
                else:
                    devices = conn.execute(
                        """SELECT * FROM verified_devices
                           WHERE device_type = ?
                           ORDER BY last_seen DESC""",
                        (device_type,)
                    ).fetchall()

                return [dict(d) for d in devices]
        except Exception as e:
            logger.exception(f"[VerifyID] List by type error: {e}")
            return []

    # ─── Telemetry Collection ─────────────────────────────────────────────

    def record_telemetry(
        self,
        device_id: str,
        gps_lat: float = None,
        gps_lng: float = None,
        speed_kmh: float = None,
        battery_percent: int = None,
        mode: str = "MANUAL",
        sensor_data: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Record telemetry from a device.

        For GPS/Vehicle nodes, this tracks location and sensor data.
        Used for autonomous driving rewards and AI training.
        """
        try:
            with self._get_connection() as conn:
                # Verify device exists
                device = conn.execute(
                    "SELECT status FROM verified_devices WHERE device_id = ?",
                    (device_id,)
                ).fetchone()

                if not device:
                    return {"ok": False, "error": "Device not registered"}

                if device["status"] != VerificationStatus.VERIFIED.value:
                    return {"ok": False, "error": "Device not verified"}

                now = datetime.utcnow().isoformat() + "Z"
                indexed_at = int(time.time())

                conn.execute("""
                    INSERT INTO device_telemetry
                    (device_id, timestamp, gps_lat, gps_lng, speed_kmh,
                     battery_percent, mode, sensor_data, indexed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    device_id,
                    now,
                    gps_lat,
                    gps_lng,
                    speed_kmh,
                    battery_percent,
                    mode,
                    json.dumps(sensor_data or {}),
                    indexed_at
                ))

                # Update device last_seen
                conn.execute(
                    "UPDATE verified_devices SET last_seen = ? WHERE device_id = ?",
                    (now, device_id)
                )

                conn.commit()

                return {
                    "ok": True,
                    "device_id": device_id,
                    "timestamp": now,
                    "recorded": True
                }

        except Exception as e:
            logger.exception(f"[VerifyID] Telemetry error: {e}")
            return {"ok": False, "error": str(e)}

    def get_device_telemetry(
        self,
        device_id: str,
        limit: int = 100,
        since: str = None
    ) -> List[Dict[str, Any]]:
        """Get telemetry history for a device"""
        try:
            with self._get_connection() as conn:
                if since:
                    rows = conn.execute(
                        """SELECT * FROM device_telemetry
                           WHERE device_id = ? AND timestamp >= ?
                           ORDER BY timestamp DESC
                           LIMIT ?""",
                        (device_id, since, limit)
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """SELECT * FROM device_telemetry
                           WHERE device_id = ?
                           ORDER BY timestamp DESC
                           LIMIT ?""",
                        (device_id, limit)
                    ).fetchall()

                result = []
                for row in rows:
                    entry = dict(row)
                    if entry.get("sensor_data"):
                        try:
                            entry["sensor_data"] = json.loads(entry["sensor_data"])
                        except:
                            pass
                    result.append(entry)

                return result
        except Exception as e:
            logger.exception(f"[VerifyID] Get telemetry error: {e}")
            return []

    # ─── Driver Rewards System ────────────────────────────────────────────

    def calculate_trip_reward(
        self,
        device_id: str,
        wallet_address: str,
        trip_distance_km: float,
        training_mode: bool = False,
        music_streaming: bool = False
    ) -> Dict[str, Any]:
        """
        Calculate and create reward for a completed trip.

        Rewards:
        - Base discount for using Thronos autopilot
        - Bonus for AI training mode (contributes to model training)
        - Extra bonus if streaming music from Thronos Music

        Payment options:
        - THR tokens
        - Crosschain assets (BTC via bridge, etc.)
        """
        try:
            # Base reward: 0.01 THR per km
            base_rate = 0.01
            reward_thr = trip_distance_km * base_rate

            # Training mode bonus: +50%
            training_contrib = 0.0
            if training_mode:
                reward_thr *= 1.5
                training_contrib = trip_distance_km * 0.1  # Training contribution score

            # Music streaming bonus: +20%
            if music_streaming:
                reward_thr *= 1.2

            # Create reward entry
            reward_id = f"RWD-{secrets.token_hex(8)}"
            now = datetime.utcnow().isoformat() + "Z"

            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO driver_rewards
                    (reward_id, device_id, wallet_address, reward_type, amount_thr,
                     trip_distance_km, training_contribution, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    reward_id,
                    device_id,
                    wallet_address,
                    "trip_discount",
                    reward_thr,
                    trip_distance_km,
                    training_contrib,
                    now
                ))

                # Update device total rewards
                conn.execute("""
                    UPDATE verified_devices
                    SET total_rewards_earned = total_rewards_earned + ?
                    WHERE device_id = ?
                """, (reward_thr, device_id))

                conn.commit()

                return {
                    "ok": True,
                    "reward_id": reward_id,
                    "amount_thr": round(reward_thr, 6),
                    "trip_distance_km": trip_distance_km,
                    "training_contribution": training_contrib,
                    "training_bonus_applied": training_mode,
                    "music_bonus_applied": music_streaming,
                    "message": f"Reward of {reward_thr:.4f} THR created for trip"
                }

        except Exception as e:
            logger.exception(f"[VerifyID] Trip reward error: {e}")
            return {"ok": False, "error": str(e)}

    def get_pending_rewards(self, wallet_address: str) -> List[Dict[str, Any]]:
        """Get unclaimed rewards for a wallet"""
        try:
            with self._get_connection() as conn:
                rows = conn.execute(
                    """SELECT * FROM driver_rewards
                       WHERE wallet_address = ? AND claimed = 0
                       ORDER BY created_at DESC""",
                    (wallet_address,)
                ).fetchall()

                return [dict(r) for r in rows]
        except Exception as e:
            logger.exception(f"[VerifyID] Get rewards error: {e}")
            return []

    def claim_reward(self, reward_id: str, wallet_address: str) -> Dict[str, Any]:
        """
        Claim a pending reward.

        This transfers THR (or crosschain asset) to the wallet.
        Integration with main ledger happens here.
        """
        try:
            with self._get_connection() as conn:
                reward = conn.execute(
                    """SELECT * FROM driver_rewards
                       WHERE reward_id = ? AND wallet_address = ?""",
                    (reward_id, wallet_address)
                ).fetchone()

                if not reward:
                    return {"ok": False, "error": "Reward not found"}

                if reward["claimed"]:
                    return {"ok": False, "error": "Reward already claimed"}

                now = datetime.utcnow().isoformat() + "Z"

                conn.execute("""
                    UPDATE driver_rewards
                    SET claimed = 1, claimed_at = ?
                    WHERE reward_id = ?
                """, (now, reward_id))

                conn.commit()

                # Note: Actual THR transfer would be handled by main ledger
                # This returns the claim info for the caller to process

                return {
                    "ok": True,
                    "reward_id": reward_id,
                    "amount_thr": reward["amount_thr"],
                    "wallet_address": wallet_address,
                    "claimed_at": now,
                    "message": f"Reward of {reward['amount_thr']} THR claimed"
                }

        except Exception as e:
            logger.exception(f"[VerifyID] Claim reward error: {e}")
            return {"ok": False, "error": str(e)}

    # ─── AI Training Contributions ────────────────────────────────────────

    def record_training_contribution(
        self,
        device_id: str,
        wallet_address: str,
        contribution_type: str,  # "gps_telemetry", "music_telemetry", "driving_data"
        data_hash: str,
        data_size_bytes: int = 0,
        quality_score: float = 1.0
    ) -> Dict[str, Any]:
        """
        Record a contribution to AI model training.

        Types:
        - gps_telemetry: GPS route data for navigation AI
        - music_telemetry: Music listening patterns for recommendations
        - driving_data: Driving behavior for autopilot training
        """
        try:
            # Calculate reward based on contribution type and quality
            reward_rates = {
                "gps_telemetry": 0.001,  # THR per KB
                "music_telemetry": 0.0005,
                "driving_data": 0.002,
            }

            rate = reward_rates.get(contribution_type, 0.0005)
            reward = (data_size_bytes / 1024) * rate * quality_score

            now = datetime.utcnow().isoformat() + "Z"

            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO training_contributions
                    (device_id, wallet_address, contribution_type, data_hash,
                     data_size_bytes, quality_score, reward_amount, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    device_id,
                    wallet_address,
                    contribution_type,
                    data_hash,
                    data_size_bytes,
                    quality_score,
                    reward,
                    now
                ))

                conn.commit()

                return {
                    "ok": True,
                    "contribution_type": contribution_type,
                    "data_hash": data_hash,
                    "reward_amount": round(reward, 6),
                    "message": "Training contribution recorded"
                }

        except Exception as e:
            logger.exception(f"[VerifyID] Training contribution error: {e}")
            return {"ok": False, "error": str(e)}

    # ─── Statistics ───────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get overall VerifyID statistics"""
        try:
            with self._get_connection() as conn:
                total_devices = conn.execute(
                    "SELECT COUNT(*) as count FROM verified_devices"
                ).fetchone()["count"]

                verified_devices = conn.execute(
                    "SELECT COUNT(*) as count FROM verified_devices WHERE status = ?",
                    (VerificationStatus.VERIFIED.value,)
                ).fetchone()["count"]

                by_type = conn.execute(
                    """SELECT device_type, COUNT(*) as count
                       FROM verified_devices
                       GROUP BY device_type"""
                ).fetchall()

                total_rewards = conn.execute(
                    "SELECT SUM(amount_thr) as total FROM driver_rewards"
                ).fetchone()["total"] or 0.0

                unclaimed_rewards = conn.execute(
                    "SELECT SUM(amount_thr) as total FROM driver_rewards WHERE claimed = 0"
                ).fetchone()["total"] or 0.0

                total_telemetry = conn.execute(
                    "SELECT COUNT(*) as count FROM device_telemetry"
                ).fetchone()["count"]

                return {
                    "total_devices": total_devices,
                    "verified_devices": verified_devices,
                    "devices_by_type": {row["device_type"]: row["count"] for row in by_type},
                    "total_rewards_distributed": round(total_rewards, 4),
                    "unclaimed_rewards": round(unclaimed_rewards, 4),
                    "total_telemetry_records": total_telemetry
                }

        except Exception as e:
            logger.exception(f"[VerifyID] Stats error: {e}")
            return {"error": str(e)}


# ─── Global Service Instance ──────────────────────────────────────────────
_verify_id_service: Optional[VerifyIDService] = None


def get_verify_id_service() -> VerifyIDService:
    """Get or create the global VerifyID service instance"""
    global _verify_id_service
    if _verify_id_service is None:
        _verify_id_service = VerifyIDService()
    return _verify_id_service


# ─── Flask Route Handlers (for integration with server.py) ────────────────

def register_verify_id_routes(app):
    """Register VerifyID API routes with Flask app"""
    from flask import request, jsonify

    service = get_verify_id_service()

    @app.route("/api/verify/register", methods=["POST"])
    def api_verify_register():
        """Register a new device for verification"""
        data = request.get_json() or {}

        device_type = data.get("device_type", "asic")
        owner_wallet = data.get("wallet") or data.get("owner_wallet")
        hardware_info = data.get("hardware_info", {})
        metadata = data.get("metadata", {})

        if not owner_wallet:
            return jsonify({"ok": False, "error": "wallet required"}), 400

        if not hardware_info:
            return jsonify({"ok": False, "error": "hardware_info required"}), 400

        result = service.register_device(device_type, owner_wallet, hardware_info, metadata)
        return jsonify(result), 200 if result.get("ok") else 400

    @app.route("/api/verify/check", methods=["GET", "POST"])
    def api_verify_check():
        """Check if a device exists and is verified"""
        if request.method == "POST":
            data = request.get_json() or {}
        else:
            data = dict(request.args)

        device_id = data.get("device_id")
        hardware_hash = data.get("hardware_hash")

        result = service.check_device_exists(device_id, hardware_hash)
        return jsonify(result), 200

    @app.route("/api/verify/device/<device_id>", methods=["GET"])
    def api_verify_device(device_id):
        """Get device details"""
        device = service.get_device(device_id)
        if not device:
            return jsonify({"ok": False, "error": "Device not found"}), 404
        return jsonify({"ok": True, "device": device}), 200

    @app.route("/api/verify/devices", methods=["GET"])
    def api_verify_devices():
        """List devices by wallet or type"""
        wallet = request.args.get("wallet")
        device_type = request.args.get("type")
        verified_only = request.args.get("verified_only", "true").lower() == "true"

        if wallet:
            devices = service.list_devices_by_wallet(wallet)
        elif device_type:
            devices = service.list_devices_by_type(device_type, verified_only)
        else:
            return jsonify({"ok": False, "error": "wallet or type required"}), 400

        return jsonify({"ok": True, "devices": devices, "count": len(devices)}), 200

    @app.route("/api/verify/telemetry", methods=["POST"])
    def api_verify_telemetry():
        """Record device telemetry"""
        data = request.get_json() or {}

        device_id = data.get("device_id")
        if not device_id:
            return jsonify({"ok": False, "error": "device_id required"}), 400

        result = service.record_telemetry(
            device_id=device_id,
            gps_lat=data.get("gps_lat"),
            gps_lng=data.get("gps_lng"),
            speed_kmh=data.get("speed_kmh"),
            battery_percent=data.get("battery_percent"),
            mode=data.get("mode", "MANUAL"),
            sensor_data=data.get("sensor_data")
        )
        return jsonify(result), 200 if result.get("ok") else 400

    @app.route("/api/verify/telemetry/<device_id>", methods=["GET"])
    def api_verify_telemetry_history(device_id):
        """Get telemetry history for a device"""
        limit = int(request.args.get("limit", 100))
        since = request.args.get("since")

        telemetry = service.get_device_telemetry(device_id, limit, since)
        return jsonify({"ok": True, "telemetry": telemetry, "count": len(telemetry)}), 200

    @app.route("/api/verify/rewards/trip", methods=["POST"])
    def api_verify_trip_reward():
        """Calculate reward for completed trip"""
        data = request.get_json() or {}

        device_id = data.get("device_id")
        wallet = data.get("wallet")
        distance_km = data.get("distance_km", 0)
        training_mode = data.get("training_mode", False)
        music_streaming = data.get("music_streaming", False)

        if not device_id or not wallet:
            return jsonify({"ok": False, "error": "device_id and wallet required"}), 400

        result = service.calculate_trip_reward(
            device_id, wallet, distance_km, training_mode, music_streaming
        )
        return jsonify(result), 200 if result.get("ok") else 400

    @app.route("/api/verify/rewards", methods=["GET"])
    def api_verify_rewards():
        """Get pending rewards for wallet"""
        wallet = request.args.get("wallet")
        if not wallet:
            return jsonify({"ok": False, "error": "wallet required"}), 400

        rewards = service.get_pending_rewards(wallet)
        total = sum(r.get("amount_thr", 0) for r in rewards)
        return jsonify({
            "ok": True,
            "rewards": rewards,
            "count": len(rewards),
            "total_pending_thr": round(total, 6)
        }), 200

    @app.route("/api/verify/rewards/claim", methods=["POST"])
    def api_verify_claim_reward():
        """Claim a pending reward"""
        data = request.get_json() or {}

        reward_id = data.get("reward_id")
        wallet = data.get("wallet")

        if not reward_id or not wallet:
            return jsonify({"ok": False, "error": "reward_id and wallet required"}), 400

        result = service.claim_reward(reward_id, wallet)
        return jsonify(result), 200 if result.get("ok") else 400

    @app.route("/api/verify/stats", methods=["GET"])
    def api_verify_stats():
        """Get VerifyID statistics"""
        stats = service.get_stats()
        return jsonify({"ok": True, "stats": stats}), 200

    @app.route("/api/verify/admin/approve", methods=["POST"])
    def api_verify_admin_approve():
        """Admin: Approve/verify a pending device"""
        data = request.get_json() or {}

        device_id = data.get("device_id")
        admin_secret = data.get("admin_secret")

        if not device_id:
            return jsonify({"ok": False, "error": "device_id required"}), 400

        # Note: Add admin secret validation in production
        result = service.verify_device(device_id, admin_secret)
        return jsonify(result), 200 if result.get("ok") else 400

    logger.info("[VerifyID] API routes registered")


# ─── CLI for testing ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="VerifyID Service CLI")
    parser.add_argument("--stats", action="store_true", help="Show statistics")
    parser.add_argument("--list", metavar="TYPE", help="List devices by type")
    parser.add_argument("--check", metavar="DEVICE_ID", help="Check device status")

    args = parser.parse_args()

    service = VerifyIDService()

    if args.stats:
        stats = service.get_stats()
        print(json.dumps(stats, indent=2))
    elif args.list:
        devices = service.list_devices_by_type(args.list, verified_only=False)
        print(json.dumps(devices, indent=2))
    elif args.check:
        result = service.check_device_exists(device_id=args.check)
        print(json.dumps(result, indent=2))
    else:
        print("VerifyID Service initialized successfully")
        print(f"Database: {service.db_path}")
        stats = service.get_stats()
        print(f"Total devices: {stats.get('total_devices', 0)}")
        print(f"Verified devices: {stats.get('verified_devices', 0)}")
