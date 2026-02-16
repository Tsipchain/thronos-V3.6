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
import hmac
import secrets
import sqlite3
import logging
import threading
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)

# Configuration
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
VERIFY_DB_FILE = os.path.join(DATA_DIR, "ledger.sqlite3")

# Blockchain / Chain connection
CHAIN_RPC_URL = os.getenv("CHAIN_RPC_URL", "https://thrchain.up.railway.app/evm")
CHAIN_CONTRACT_ADDRESS = os.getenv("CHAIN_CONTRACT_ADDRESS", "")
CHAIN_PRIVATE_KEY = os.getenv("CHAIN_PRIVATE_KEY", "")

# Admin secret (shared with server.py)
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "CHANGE_ME_NOW")

# IP geolocation
IPINFO_TOKEN = os.getenv("IPINFO_TOKEN", "")

# JWT secret for role-based access control
JWT_SECRET = os.getenv("JWT_SECRET", os.getenv("ADMIN_SECRET", "CHANGE_ME_NOW"))

# Challenge expiry (seconds)
CHALLENGE_EXPIRY_SECONDS = 300  # 5 minutes


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
        """Get database connection with Row factory, WAL mode, and extended timeout."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
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

            # Device challenge-response table (for secure verification)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS device_challenges (
                    challenge_id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    challenge TEXT NOT NULL,
                    expected_response TEXT NOT NULL,
                    public_key TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    resolved INTEGER DEFAULT 0,
                    FOREIGN KEY (device_id) REFERENCES verified_devices(device_id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_challenge_device ON device_challenges(device_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_challenge_expires ON device_challenges(expires_at)")

            # Blockchain verification log
            conn.execute("""
                CREATE TABLE IF NOT EXISTS blockchain_verifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    wallet_address TEXT NOT NULL,
                    tx_hash TEXT,
                    block_height INTEGER,
                    verification_type TEXT NOT NULL,
                    data_hash TEXT NOT NULL,
                    chain_status TEXT DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    confirmed_at TEXT,
                    FOREIGN KEY (device_id) REFERENCES verified_devices(device_id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bc_device ON blockchain_verifications(device_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bc_wallet ON blockchain_verifications(wallet_address)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bc_status ON blockchain_verifications(chain_status)")

            # Risk score cache
            conn.execute("""
                CREATE TABLE IF NOT EXISTS risk_score_cache (
                    wallet_address TEXT PRIMARY KEY,
                    score REAL NOT NULL,
                    account_age_days INTEGER,
                    previous_verifications INTEGER,
                    ip_country TEXT,
                    ip_risk_flag INTEGER DEFAULT 0,
                    computed_at TEXT NOT NULL
                )
            """)

            conn.commit()
            logger.info("[VerifyID] Database tables initialized (with WAL mode)")

    # ─── Blockchain Integration ───────────────────────────────────────────

    def _submit_to_chain(self, verification_type: str, device_id: str,
                         wallet_address: str, data_hash: str) -> Dict[str, Any]:
        """
        Submit a verification record to the Thronos blockchain.
        Uses the main server's /api/chain/hash/submit endpoint.
        """
        try:
            payload = json.dumps({
                "hash": data_hash,
                "hash_type": verification_type,
                "wallet": wallet_address,
                "metadata": {
                    "device_id": device_id,
                    "source": "verify_id_service",
                    "verification_type": verification_type
                }
            }).encode("utf-8")

            chain_url = CHAIN_RPC_URL.rstrip("/")
            # Use the main server's hash submission endpoint
            submit_url = chain_url.replace("/evm", "") + "/api/chain/hash/submit"

            req = urllib.request.Request(
                submit_url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-Admin-Secret": ADMIN_SECRET
                },
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            tx_hash = result.get("tx_id", "")
            block_height = result.get("block_height", 0)

            # Store in local DB
            now = datetime.utcnow().isoformat() + "Z"
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO blockchain_verifications
                    (device_id, wallet_address, tx_hash, block_height,
                     verification_type, data_hash, chain_status, created_at, confirmed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    device_id, wallet_address, tx_hash, block_height,
                    verification_type, data_hash, "confirmed", now, now
                ))
                conn.commit()

            logger.info(f"[VerifyID] Chain submission OK: {tx_hash} for {device_id}")
            return {"ok": True, "tx_hash": tx_hash, "block_height": block_height}

        except Exception as e:
            logger.warning(f"[VerifyID] Chain submission failed: {e}")
            # Store as pending for retry
            now = datetime.utcnow().isoformat() + "Z"
            try:
                with self._get_connection() as conn:
                    conn.execute("""
                        INSERT INTO blockchain_verifications
                        (device_id, wallet_address, tx_hash, block_height,
                         verification_type, data_hash, chain_status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        device_id, wallet_address, "", 0,
                        verification_type, data_hash, "pending", now
                    ))
                    conn.commit()
            except Exception:
                pass
            return {"ok": False, "error": str(e), "chain_status": "pending"}

    def retry_pending_chain_submissions(self) -> Dict[str, Any]:
        """Retry any pending blockchain submissions."""
        retried = 0
        confirmed = 0
        try:
            with self._get_connection() as conn:
                pending = conn.execute(
                    "SELECT * FROM blockchain_verifications WHERE chain_status = 'pending'"
                ).fetchall()

            for row in pending:
                retried += 1
                result = self._submit_to_chain(
                    row["verification_type"], row["device_id"],
                    row["wallet_address"], row["data_hash"]
                )
                if result.get("ok"):
                    confirmed += 1
                    with self._get_connection() as conn:
                        conn.execute("""
                            UPDATE blockchain_verifications
                            SET chain_status = 'confirmed', tx_hash = ?, block_height = ?,
                                confirmed_at = ?
                            WHERE id = ?
                        """, (
                            result["tx_hash"], result["block_height"],
                            datetime.utcnow().isoformat() + "Z", row["id"]
                        ))
                        conn.commit()

        except Exception as e:
            logger.exception(f"[VerifyID] Retry chain error: {e}")

        return {"retried": retried, "confirmed": confirmed}

    def get_blockchain_verifications(self, device_id: str = None,
                                     wallet_address: str = None,
                                     limit: int = 50) -> List[Dict[str, Any]]:
        """Get blockchain verification history."""
        try:
            with self._get_connection() as conn:
                if device_id:
                    rows = conn.execute(
                        "SELECT * FROM blockchain_verifications WHERE device_id = ? ORDER BY created_at DESC LIMIT ?",
                        (device_id, limit)
                    ).fetchall()
                elif wallet_address:
                    rows = conn.execute(
                        "SELECT * FROM blockchain_verifications WHERE wallet_address = ? ORDER BY created_at DESC LIMIT ?",
                        (wallet_address, limit)
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM blockchain_verifications ORDER BY created_at DESC LIMIT ?",
                        (limit,)
                    ).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.exception(f"[VerifyID] Get BC verifications error: {e}")
            return []

    # ─── Challenge-Response Device Verification ───────────────────────────

    def create_device_challenge(self, device_id: str, public_key: str = None) -> Dict[str, Any]:
        """
        Create a challenge for secure device verification.
        The device must respond with HMAC-SHA256(challenge, device_secret).
        """
        try:
            with self._get_connection() as conn:
                device = conn.execute(
                    "SELECT * FROM verified_devices WHERE device_id = ?",
                    (device_id,)
                ).fetchone()
                if not device:
                    return {"ok": False, "error": "Device not found"}

                challenge = secrets.token_hex(32)
                challenge_id = f"CH-{secrets.token_hex(8)}"
                # Expected response is HMAC of challenge using hardware_hash as key
                expected = hmac.new(
                    device["hardware_hash"].encode(),
                    challenge.encode(),
                    hashlib.sha256
                ).hexdigest()

                now = datetime.utcnow()
                expires = now + timedelta(seconds=CHALLENGE_EXPIRY_SECONDS)

                conn.execute("""
                    INSERT INTO device_challenges
                    (challenge_id, device_id, challenge, expected_response, public_key,
                     created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    challenge_id, device_id, challenge, expected, public_key,
                    now.isoformat() + "Z", expires.isoformat() + "Z"
                ))
                conn.commit()

                return {
                    "ok": True,
                    "challenge_id": challenge_id,
                    "challenge": challenge,
                    "expires_at": expires.isoformat() + "Z"
                }
        except Exception as e:
            logger.exception(f"[VerifyID] Create challenge error: {e}")
            return {"ok": False, "error": str(e)}

    def verify_challenge_response(self, challenge_id: str, response: str,
                                   public_key: str = None) -> Dict[str, Any]:
        """
        Verify a device's response to a challenge.
        If valid, the device is marked as verified and the public key is stored.
        """
        try:
            with self._get_connection() as conn:
                ch = conn.execute(
                    "SELECT * FROM device_challenges WHERE challenge_id = ? AND resolved = 0",
                    (challenge_id,)
                ).fetchone()

                if not ch:
                    return {"ok": False, "error": "Challenge not found or already resolved"}

                # Check expiry
                expires = datetime.fromisoformat(ch["expires_at"].replace("Z", "+00:00"))
                now = datetime.utcnow().replace(tzinfo=expires.tzinfo)
                if now > expires:
                    return {"ok": False, "error": "Challenge expired"}

                # Verify response
                if not hmac.compare_digest(response, ch["expected_response"]):
                    return {"ok": False, "error": "Invalid response"}

                # Mark challenge resolved
                conn.execute(
                    "UPDATE device_challenges SET resolved = 1 WHERE challenge_id = ?",
                    (challenge_id,)
                )

                # Store public key if provided
                pk = public_key or ch["public_key"]
                if pk:
                    # Store public key in device metadata
                    device = conn.execute(
                        "SELECT metadata FROM verified_devices WHERE device_id = ?",
                        (ch["device_id"],)
                    ).fetchone()
                    meta = json.loads(device["metadata"]) if device and device["metadata"] else {}
                    meta["public_key"] = pk
                    meta["key_registered_at"] = datetime.utcnow().isoformat() + "Z"
                    conn.execute(
                        "UPDATE verified_devices SET metadata = ? WHERE device_id = ?",
                        (json.dumps(meta), ch["device_id"])
                    )

                # Mark device as verified
                now_str = datetime.utcnow().isoformat() + "Z"
                conn.execute("""
                    UPDATE verified_devices SET status = ?, last_seen = ? WHERE device_id = ?
                """, (VerificationStatus.VERIFIED.value, now_str, ch["device_id"]))

                conn.commit()

                # Submit to blockchain
                data_hash = hashlib.sha256(
                    f"{ch['device_id']}:{ch['challenge']}:{response}".encode()
                ).hexdigest()
                chain_result = self._submit_to_chain(
                    "device_verification", ch["device_id"],
                    "", data_hash
                )

                return {
                    "ok": True,
                    "device_id": ch["device_id"],
                    "status": VerificationStatus.VERIFIED.value,
                    "public_key_stored": bool(pk),
                    "chain_tx": chain_result.get("tx_hash", ""),
                    "message": "Device verified via challenge-response"
                }

        except Exception as e:
            logger.exception(f"[VerifyID] Verify challenge error: {e}")
            return {"ok": False, "error": str(e)}

    # ─── Risk Score Calculation ───────────────────────────────────────────

    def _get_ip_location(self, ip_address: str) -> Dict[str, Any]:
        """Get IP geolocation using ipinfo.io API."""
        try:
            token_param = f"?token={IPINFO_TOKEN}" if IPINFO_TOKEN else ""
            url = f"https://ipinfo.io/{ip_address}/json{token_param}"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.warning(f"[VerifyID] IP geolocation failed for {ip_address}: {e}")
            return {}

    def calculate_risk_score(self, wallet_address: str,
                              ip_address: str = None) -> Dict[str, Any]:
        """
        Calculate a risk score for a wallet address.

        Components (weighted sum):
        - account_age_days: Older accounts are lower risk (weight 0.3)
        - previous_verifications: More verifications = lower risk (weight 0.4)
        - ip_location: Geographic anomalies increase risk (weight 0.3)

        Score: 0.0 (lowest risk) to 1.0 (highest risk)
        """
        try:
            # 1. Account age (from first on-chain activity)
            account_age_days = 0
            try:
                chain_url = CHAIN_RPC_URL.rstrip("/").replace("/evm", "")
                auth_url = f"{chain_url}/api/chain/wallet/authenticate"
                payload = json.dumps({"wallet": wallet_address}).encode("utf-8")
                req = urllib.request.Request(
                    auth_url, data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    wallet_data = json.loads(resp.read().decode("utf-8"))

                last_activity = wallet_data.get("last_activity")
                if last_activity:
                    activity_dt = datetime.fromisoformat(last_activity.replace("Z", "+00:00"))
                    age_delta = datetime.utcnow().replace(
                        tzinfo=activity_dt.tzinfo) - activity_dt
                    account_age_days = max(age_delta.days, 0)
            except Exception:
                pass

            # 2. Previous successful verifications
            previous_verifications = 0
            try:
                with self._get_connection() as conn:
                    row = conn.execute(
                        """SELECT COUNT(*) as cnt FROM blockchain_verifications
                           WHERE wallet_address = ? AND chain_status = 'confirmed'""",
                        (wallet_address,)
                    ).fetchone()
                    previous_verifications = row["cnt"] if row else 0
            except Exception:
                pass

            # 3. IP geolocation risk
            ip_country = ""
            ip_risk_flag = 0
            if ip_address:
                geo = self._get_ip_location(ip_address)
                ip_country = geo.get("country", "")
                # Flag if IP is from a VPN/proxy or unusual location
                if geo.get("privacy", {}).get("vpn") or geo.get("privacy", {}).get("proxy"):
                    ip_risk_flag = 1
                # Also flag bogon IPs
                if geo.get("bogon"):
                    ip_risk_flag = 1

            # Calculate weighted score components
            # Account age: 0 days = 1.0 risk, 365+ days = 0.0 risk
            age_score = max(0.0, 1.0 - (account_age_days / 365.0))

            # Verifications: 0 = 1.0 risk, 10+ = 0.0 risk
            verif_score = max(0.0, 1.0 - (previous_verifications / 10.0))

            # IP: 0 = no risk flag, 1 = flagged
            ip_score = float(ip_risk_flag)

            # Weighted sum
            risk_score = round(
                (age_score * 0.3) + (verif_score * 0.4) + (ip_score * 0.3),
                4
            )

            # Cache the result
            now = datetime.utcnow().isoformat() + "Z"
            try:
                with self._get_connection() as conn:
                    conn.execute("""
                        INSERT OR REPLACE INTO risk_score_cache
                        (wallet_address, score, account_age_days, previous_verifications,
                         ip_country, ip_risk_flag, computed_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (wallet_address, risk_score, account_age_days,
                          previous_verifications, ip_country, ip_risk_flag, now))
                    conn.commit()
            except Exception:
                pass

            return {
                "ok": True,
                "wallet_address": wallet_address,
                "risk_score": risk_score,
                "risk_level": "low" if risk_score < 0.3 else ("medium" if risk_score < 0.7 else "high"),
                "components": {
                    "account_age_days": account_age_days,
                    "account_age_score": round(age_score, 4),
                    "previous_verifications": previous_verifications,
                    "verification_score": round(verif_score, 4),
                    "ip_country": ip_country,
                    "ip_risk_flag": ip_risk_flag,
                    "ip_score": round(ip_score, 4)
                },
                "weights": {"account_age": 0.3, "verifications": 0.4, "ip_location": 0.3},
                "computed_at": now
            }

        except Exception as e:
            logger.exception(f"[VerifyID] Risk score error: {e}")
            return {"ok": False, "error": str(e)}

    # ─── Live Telemetry (Real-time truck tracking) ────────────────────────

    def get_live_position(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Get the most recent GPS position for a device."""
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    """SELECT * FROM device_telemetry
                       WHERE device_id = ? AND gps_lat IS NOT NULL AND gps_lng IS NOT NULL
                       ORDER BY timestamp DESC LIMIT 1""",
                    (device_id,)
                ).fetchone()

                if not row:
                    return None

                entry = dict(row)
                if entry.get("sensor_data"):
                    try:
                        entry["sensor_data"] = json.loads(entry["sensor_data"])
                    except Exception:
                        pass
                return entry
        except Exception as e:
            logger.exception(f"[VerifyID] Get live position error: {e}")
            return None

    def get_fleet_positions(self, wallet_address: str) -> List[Dict[str, Any]]:
        """Get latest positions for all devices owned by a wallet (fleet view)."""
        try:
            devices = self.list_devices_by_wallet(wallet_address)
            positions = []
            for dev in devices:
                pos = self.get_live_position(dev["device_id"])
                if pos:
                    pos["device_type"] = dev.get("device_type", "")
                    pos["device_status"] = dev.get("status", "")
                    positions.append(pos)
            return positions
        except Exception as e:
            logger.exception(f"[VerifyID] Fleet positions error: {e}")
            return []

    # ─── Driver Rewards Scheduler ─────────────────────────────────────────

    def process_pending_trips(self) -> Dict[str, Any]:
        """
        Scheduler: Process recent telemetry to calculate trip distances
        and distribute T2E rewards automatically.
        """
        processed = 0
        rewards_created = 0
        try:
            with self._get_connection() as conn:
                # Get all vehicle nodes with recent telemetry
                vehicles = conn.execute(
                    """SELECT DISTINCT d.device_id, d.owner_wallet
                       FROM verified_devices d
                       JOIN device_telemetry t ON d.device_id = t.device_id
                       WHERE d.device_type IN ('vehicle_node', 'gps_node')
                       AND d.status = 'verified'
                       AND t.timestamp >= ?""",
                    ((datetime.utcnow() - timedelta(hours=24)).isoformat() + "Z",)
                ).fetchall()

                for vehicle in vehicles:
                    dev_id = vehicle["device_id"]
                    wallet = vehicle["owner_wallet"]

                    # Get telemetry points for last 24h
                    points = conn.execute(
                        """SELECT gps_lat, gps_lng, speed_kmh, mode, timestamp
                           FROM device_telemetry
                           WHERE device_id = ? AND gps_lat IS NOT NULL
                           AND timestamp >= ?
                           ORDER BY timestamp ASC""",
                        (dev_id, (datetime.utcnow() - timedelta(hours=24)).isoformat() + "Z")
                    ).fetchall()

                    if len(points) < 2:
                        continue

                    # Calculate approximate distance (haversine simplified)
                    total_km = 0.0
                    training_mode = False
                    for i in range(1, len(points)):
                        lat1, lng1 = points[i-1]["gps_lat"], points[i-1]["gps_lng"]
                        lat2, lng2 = points[i]["gps_lat"], points[i]["gps_lng"]
                        if lat1 and lng1 and lat2 and lng2:
                            # Approximate distance in km
                            import math
                            dlat = math.radians(lat2 - lat1)
                            dlng = math.radians(lng2 - lng1)
                            a = (math.sin(dlat/2)**2 +
                                 math.cos(math.radians(lat1)) *
                                 math.cos(math.radians(lat2)) *
                                 math.sin(dlng/2)**2)
                            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
                            total_km += 6371.0 * c

                        if points[i]["mode"] == "TRAINING":
                            training_mode = True

                    processed += 1

                    if total_km >= 1.0:  # Minimum 1km to earn rewards
                        result = self.calculate_trip_reward(
                            dev_id, wallet, total_km, training_mode=training_mode
                        )
                        if result.get("ok"):
                            rewards_created += 1

        except Exception as e:
            logger.exception(f"[VerifyID] Process trips error: {e}")

        return {
            "vehicles_processed": processed,
            "rewards_created": rewards_created
        }

    # ─── Chain Health Check ───────────────────────────────────────────────

    def check_chain_health(self) -> Dict[str, Any]:
        """Check connectivity to the Thronos chain RPC."""
        try:
            chain_url = CHAIN_RPC_URL.rstrip("/").replace("/evm", "")
            health_url = f"{chain_url}/api/health"

            req = urllib.request.Request(health_url, method="GET")
            start = time.time()
            with urllib.request.urlopen(req, timeout=10) as resp:
                latency_ms = round((time.time() - start) * 1000, 1)
                data = json.loads(resp.read().decode("utf-8"))

            return {
                "ok": True,
                "chain_url": chain_url,
                "status": "connected",
                "latency_ms": latency_ms,
                "chain_response": data
            }
        except Exception as e:
            return {
                "ok": False,
                "chain_url": CHAIN_RPC_URL,
                "status": "unreachable",
                "error": str(e)
            }

    # ─── AI Training Feedback ─────────────────────────────────────────────

    def record_ai_feedback(self, wallet_address: str, prompt: str,
                            answer: str, rating: str,
                            session_id: str = "") -> Dict[str, Any]:
        """
        Record user feedback (thumb-up/down) on AI responses.
        Positive feedback is queued for the Pythia training buffer.
        """
        try:
            data_hash = hashlib.sha256(
                f"{prompt}:{answer}:{wallet_address}".encode()
            ).hexdigest()

            contribution_type = "ai_feedback_positive" if rating == "up" else "ai_feedback_negative"

            # Only queue positive feedback for training
            if rating == "up":
                data_size = len(prompt.encode()) + len(answer.encode())
                result = self.record_training_contribution(
                    device_id=f"AI-FEEDBACK-{wallet_address[:16]}",
                    wallet_address=wallet_address,
                    contribution_type="ai_feedback",
                    data_hash=data_hash,
                    data_size_bytes=data_size,
                    quality_score=1.0
                )

                # Write to training buffer file for Pythia
                try:
                    buffer_file = os.path.join(DATA_DIR, "ai_training_buffer.jsonl")
                    entry = {
                        "prompt": prompt,
                        "answer": answer,
                        "wallet": wallet_address,
                        "rating": rating,
                        "session_id": session_id,
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "data_hash": data_hash
                    }
                    with open(buffer_file, "a") as f:
                        f.write(json.dumps(entry) + "\n")
                except Exception as e:
                    logger.warning(f"[VerifyID] Training buffer write error: {e}")

                return {
                    "ok": True,
                    "feedback": "positive",
                    "queued_for_training": True,
                    "reward_amount": result.get("reward_amount", 0)
                }
            else:
                return {
                    "ok": True,
                    "feedback": "negative",
                    "queued_for_training": False
                }

        except Exception as e:
            logger.exception(f"[VerifyID] AI feedback error: {e}")
            return {"ok": False, "error": str(e)}

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

                # Submit registration to blockchain (async-safe)
                reg_hash = hashlib.sha256(
                    f"{device_id}:{owner_wallet}:{hardware_hash}".encode()
                ).hexdigest()
                chain_result = self._submit_to_chain(
                    "device_registration", device_id, owner_wallet, reg_hash
                )

                return {
                    "ok": True,
                    "device_id": device_id,
                    "status": VerificationStatus.PENDING.value,
                    "chain_tx": chain_result.get("tx_hash", ""),
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

def _extract_jwt_role(request) -> str:
    """
    Extract user role from JWT Bearer token or X-User-Role header.
    Roles: 'inspector', 'driver', 'admin', '' (unknown).
    """
    import base64
    # Try Authorization header (Bearer token)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            # Decode JWT payload (middle segment) without full verification
            # In production, use proper JWT library with signature verification
            parts = token.split(".")
            if len(parts) == 3:
                # Pad base64 if needed
                payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
                payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                return payload.get("role", "")
        except Exception:
            pass

    # Fallback: X-User-Role header (for internal services)
    return request.headers.get("X-User-Role", "")


def _extract_jwt_wallet(request) -> str:
    """Extract wallet address from JWT token."""
    import base64
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            parts = token.split(".")
            if len(parts) == 3:
                payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
                payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                return payload.get("wallet", "")
        except Exception:
            pass
    return request.headers.get("X-User-Wallet", "")


def register_verify_id_routes(app):
    """Register VerifyID API routes with Flask app"""
    from flask import request, jsonify

    service = get_verify_id_service()
    app_version = os.getenv("APP_VERSION", "v3.6")
    app_git_sha = (
        os.getenv("RAILWAY_GIT_COMMIT_SHA")
        or os.getenv("RENDER_GIT_COMMIT")
        or os.getenv("SOURCE_COMMIT")
        or "unknown"
    )
    app_build_time = os.getenv("BUILD_TIME", os.getenv("RENDER_GIT_COMMIT_TIME", ""))

    @app.route("/health", methods=["GET", "OPTIONS"])
    def verifyid_health_root():
        """Canonical root health endpoint with CORS for status-board probes."""
        if request.method == "OPTIONS":
            resp = jsonify({"ok": True})
            resp.status_code = 204
        else:
            resp = jsonify({
                "ok": True,
                "service": "verifyid-api",
                "ts": int(time.time()),
            })
            resp.status_code = 200
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET,OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        return resp

    @app.route("/version", methods=["GET"])
    def verifyid_version_root():
        return jsonify({
            "ok": True,
            "service": "verifyid-api",
            "role": os.getenv("NODE_ROLE", "verifyid"),
            "version": app_version,
            "git_sha": app_git_sha,
            "build_time": app_build_time,
            "ts": int(time.time()),
        }), 200

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
        """Admin/Inspector: Approve/verify a pending device"""
        data = request.get_json() or {}

        device_id = data.get("device_id")
        admin_secret = data.get("admin_secret") or request.headers.get("X-Admin-Secret", "")

        if not device_id:
            return jsonify({"ok": False, "error": "device_id required"}), 400

        # RBAC: require admin secret or inspector role
        role = _extract_jwt_role(request)
        if admin_secret != ADMIN_SECRET and role != "inspector":
            return jsonify({"ok": False, "error": "Unauthorized. Inspector role or admin secret required."}), 403

        result = service.verify_device(device_id, admin_secret)
        return jsonify(result), 200 if result.get("ok") else 400

    # ─── Challenge-Response Endpoints ─────────────────────────────────────

    @app.route("/api/verify/challenge/create", methods=["POST"])
    def api_verify_challenge_create():
        """Create a challenge for secure device verification"""
        data = request.get_json() or {}
        device_id = data.get("device_id")
        public_key = data.get("public_key")

        if not device_id:
            return jsonify({"ok": False, "error": "device_id required"}), 400

        result = service.create_device_challenge(device_id, public_key)
        return jsonify(result), 200 if result.get("ok") else 400

    @app.route("/api/verify/challenge/respond", methods=["POST"])
    def api_verify_challenge_respond():
        """Respond to a device verification challenge"""
        data = request.get_json() or {}
        challenge_id = data.get("challenge_id")
        response = data.get("response")
        public_key = data.get("public_key")

        if not challenge_id or not response:
            return jsonify({"ok": False, "error": "challenge_id and response required"}), 400

        result = service.verify_challenge_response(challenge_id, response, public_key)
        return jsonify(result), 200 if result.get("ok") else 400

    # ─── Risk Score Endpoint ──────────────────────────────────────────────

    @app.route("/api/verify/riskscore", methods=["GET", "POST"])
    @app.route("/blockchain/riskscore", methods=["GET", "POST"])
    def api_verify_risk_score():
        """Calculate risk score for a wallet address"""
        if request.method == "POST":
            data = request.get_json() or {}
        else:
            data = dict(request.args)

        wallet = data.get("wallet", "").strip()
        ip_address = data.get("ip") or request.remote_addr

        if not wallet:
            return jsonify({"ok": False, "error": "wallet required"}), 400

        result = service.calculate_risk_score(wallet, ip_address)
        return jsonify(result), 200

    # ─── Live Telemetry / Truck Tracking Endpoints ────────────────────────

    @app.route("/api/telemetry/live", methods=["GET"])
    def api_telemetry_live():
        """Get the most recent GPS position for a device (live tracking)"""
        device_id = request.args.get("device_id", "").strip()
        if not device_id:
            return jsonify({"ok": False, "error": "device_id required"}), 400

        # RBAC: drivers can only see their own devices
        role = _extract_jwt_role(request)
        wallet = _extract_jwt_wallet(request)

        if role == "driver" and wallet:
            device = service.get_device(device_id)
            if device and device.get("owner_wallet") != wallet:
                return jsonify({"ok": False, "error": "Access denied. You can only view your own devices."}), 403

        pos = service.get_live_position(device_id)
        if not pos:
            return jsonify({"ok": True, "position": None, "message": "No GPS data available"}), 200

        return jsonify({"ok": True, "position": pos}), 200

    @app.route("/api/telemetry/fleet", methods=["GET"])
    def api_telemetry_fleet():
        """Get latest positions for all devices owned by a wallet (fleet view)"""
        wallet = request.args.get("wallet", "").strip()
        if not wallet:
            return jsonify({"ok": False, "error": "wallet required"}), 400

        positions = service.get_fleet_positions(wallet)
        return jsonify({
            "ok": True,
            "positions": positions,
            "count": len(positions)
        }), 200

    # ─── Blockchain Verification Endpoints ────────────────────────────────

    @app.route("/api/verify/blockchain/history", methods=["GET"])
    def api_verify_blockchain_history():
        """Get blockchain verification history"""
        device_id = request.args.get("device_id")
        wallet = request.args.get("wallet")
        limit = int(request.args.get("limit", 50))

        records = service.get_blockchain_verifications(device_id, wallet, limit)
        return jsonify({"ok": True, "verifications": records, "count": len(records)}), 200

    @app.route("/api/verify/blockchain/retry", methods=["POST"])
    def api_verify_blockchain_retry():
        """Retry pending blockchain submissions"""
        admin_secret = (request.get_json() or {}).get("admin_secret") or request.headers.get("X-Admin-Secret", "")
        if admin_secret != ADMIN_SECRET:
            return jsonify({"ok": False, "error": "Unauthorized"}), 401

        result = service.retry_pending_chain_submissions()
        return jsonify({"ok": True, **result}), 200

    # ─── Chain Health Check ───────────────────────────────────────────────

    @app.route("/api/verify/chain/health", methods=["GET"])
    def api_verify_chain_health():
        """Check connectivity to Thronos blockchain"""
        result = service.check_chain_health()
        status = 200 if result.get("ok") else 503
        return jsonify(result), status

    # ─── Driver Rewards Scheduler Endpoint ────────────────────────────────

    @app.route("/api/verify/rewards/process", methods=["POST"])
    def api_verify_process_rewards():
        """Process pending trips and distribute rewards (scheduler/admin)"""
        admin_secret = (request.get_json() or {}).get("admin_secret") or request.headers.get("X-Admin-Secret", "")
        if admin_secret != ADMIN_SECRET:
            return jsonify({"ok": False, "error": "Unauthorized"}), 401

        result = service.process_pending_trips()
        return jsonify({"ok": True, **result}), 200

    # ─── AI Training Feedback Endpoint ────────────────────────────────────

    @app.route("/api/verify/ai/feedback", methods=["POST"])
    def api_verify_ai_feedback():
        """Record AI response feedback (thumb-up/down) for training"""
        data = request.get_json() or {}
        wallet = data.get("wallet", "").strip()
        prompt = data.get("prompt", "")
        answer = data.get("answer", "")
        rating = data.get("rating", "")  # "up" or "down"
        session_id = data.get("session_id", "")

        if not wallet or not prompt or not answer or rating not in ("up", "down"):
            return jsonify({"ok": False, "error": "wallet, prompt, answer, and rating (up/down) required"}), 400

        result = service.record_ai_feedback(wallet, prompt, answer, rating, session_id)
        return jsonify(result), 200

    logger.info("[VerifyID] API routes registered (with blockchain, RBAC, live tracking)")


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
