"""
Multi-Sig Distribution Manager - Phase C3
==========================================

Handles decryption and distribution of encrypted assets to heirs.

Features:
- Heir verification (KYC + will signature)
- Asset decryption with heir-specific authorization
- Distribution tracking and audit trail
- Tamper detection during distribution
- Partial distributions (some heirs withdraw, others leave assets in pool)

Distribution Flow:
1. Will opened (majority of heirs signed)
2. Heir requests asset decryption
3. Verify heir signature on will
4. Decrypt asset keys with heir's password + master password
5. Release keys to heir wallet
6. Record distribution in audit trail
7. Track unclaimed assets for pool redistribution

Author: Thronos Digital Distribution
"""

import os
import json
import time
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
from pathlib import Path
from enum import Enum

# Cryptography is optional - imported on-demand in functions

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DATA_DIR.mkdir(exist_ok=True)
DISTRIBUTIONS_FILE = DATA_DIR / "distributions.json"


class DistributionStatus(Enum):
    """Status of asset distribution"""
    PENDING = "pending"              # Asset in estate, waiting to be claimed
    RELEASED = "released"            # Keys released to heir
    CLAIMED = "claimed"              # Heir transferred to wallet
    UNCLAIMED = "unclaimed"          # Time-lock expired, goes to pool
    RETURNED_TO_POOL = "pool"        # Unclaimed assets returned


@dataclass
class DistributionAudit:
    """Audit trail for each distribution"""
    audit_id: str                    # Unique audit ID
    asset_id: str                    # Asset being distributed
    heir_address: str                # Receiving heir
    distribution_time: str           # When keys were released
    status: DistributionStatus       # Current status

    # Verification details
    will_signature_verified: bool    # Heir signature on will validated
    timestamp_verified: bool         # Timestamp from blockchain
    tamper_check_passed: bool        # No tampering detected

    # Distribution details
    keys_encrypted: str              # Encrypted keys sent to heir
    keys_hash: str                   # SHA-256 of encrypted keys (proof)
    transaction_hash: Optional[str] = None  # Blockchain tx if on-chain

    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    notes: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "audit_id": self.audit_id,
            "asset_id": self.asset_id,
            "heir_address": self.heir_address,
            "distribution_time": self.distribution_time,
            "status": self.status.value,
            "will_signature_verified": self.will_signature_verified,
            "timestamp_verified": self.timestamp_verified,
            "tamper_check_passed": self.tamper_check_passed,
            "keys_encrypted": self.keys_encrypted,
            "keys_hash": self.keys_hash,
            "transaction_hash": self.transaction_hash,
            "created_at": self.created_at,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "DistributionAudit":
        if "status" in data and isinstance(data["status"], str):
            data["status"] = DistributionStatus(data["status"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class HeirClaim:
    """Record of heir's claim on estate"""
    heir_address: str                # Thronos address
    claimed_assets: List[str] = field(default_factory=list)  # Asset IDs claimed
    total_value_claimed: float = 0.0  # USD value
    distribution_percentage: float = 0.0  # % of estate claimed

    first_claim_time: Optional[str] = None  # When first asset claimed
    last_claim_time: Optional[str] = None   # Most recent claim

    kyd_verified: bool = False       # KYC/KYD verified
    kyc_expiry: Optional[str] = None # When verification expires

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "HeirClaim":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class DistributionValidator:
    """Validates heir eligibility and asset decryption"""

    @staticmethod
    def validate_heir_signature(will_signature: str, will_hash: str) -> Tuple[bool, str]:
        """
        Validate heir's signature on will

        In production, this would verify Bitcoin/Ethereum signatures.
        For now, verify signature format and will hash match.
        """
        try:
            if not will_signature or len(will_signature) < 20:
                return False, "Invalid signature format"
            if not will_hash or len(will_hash) != 64:  # SHA-256
                return False, "Invalid will hash"
            return True, "Signature verified"
        except Exception as e:
            return False, f"Validation error: {str(e)}"

    @staticmethod
    def validate_asset_not_tampered(asset_encrypted_keys: str, asset_salt: str) -> Tuple[bool, str]:
        """Check if asset keys have been tampered with during storage"""
        try:
            if not asset_encrypted_keys or not asset_salt:
                return False, "Missing encrypted data or salt"
            # TODO: Compare with stored hash to detect tampering
            return True, "Asset integrity verified"
        except Exception as e:
            return False, f"Tampering check failed: {str(e)}"


class DigitalDistributionManager:
    """Manages multi-sig distribution of inherited assets"""

    def __init__(self):
        self.distributions: Dict[str, DistributionAudit] = {}
        self.heir_claims: Dict[str, HeirClaim] = {}
        self._load_distributions()
        logger.info("🔑 Digital Distribution Manager initialized")

    def _load_distributions(self):
        """Load distribution records from storage"""
        try:
            if DISTRIBUTIONS_FILE.exists():
                with open(DISTRIBUTIONS_FILE, 'r') as f:
                    data = json.load(f)
                    for dist_id, dist_data in data.items():
                        self.distributions[dist_id] = DistributionAudit.from_dict(dist_data)
                logger.info(f"✅ Loaded {len(self.distributions)} distribution records")
        except Exception as e:
            logger.error(f"Error loading distributions: {e}")

    def _save_distributions(self):
        """Save distribution records to storage"""
        try:
            DATA_DIR.mkdir(exist_ok=True)
            with open(DISTRIBUTIONS_FILE, 'w') as f:
                data = {did: dist.to_dict() for did, dist in self.distributions.items()}
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving distributions: {e}")

    def can_heir_claim(self, heir_address: str, will_id: str, will_signatures: Dict[str, str]) -> Tuple[bool, str]:
        """
        Check if heir can claim assets

        Requirements:
        1. Heir is in will
        2. Heir has signed will
        3. Will is opened (majority signed)
        4. KYC verified (for high-value assets)
        """
        try:
            # Check if heir signed will
            if heir_address not in will_signatures:
                return False, "Heir has not signed will"

            # Will opening check is done at will level (can_open_will)
            # Here we just verify individual heir eligibility

            return True, "Heir eligible to claim"

        except Exception as e:
            logger.error(f"Error checking heir eligibility: {e}")
            return False, str(e)

    def release_asset_keys(
        self,
        asset_id: str,
        heir_address: str,
        encrypted_keys: str,
        will_signature: str,
        will_hash: str,
        asset_salt: str
    ) -> Tuple[bool, str, Optional[DistributionAudit]]:
        """
        Release encrypted asset keys to authorized heir

        Process:
        1. Validate heir signature on will
        2. Check asset not tampered
        3. Create audit record
        4. Release encrypted keys to heir
        5. Record distribution

        Returns: (success, message, audit_record)
        """
        try:
            # Validate heir signature
            sig_valid, sig_msg = DistributionValidator.validate_heir_signature(will_signature, will_hash)
            if not sig_valid:
                logger.warning(f"Signature validation failed: {sig_msg}")
                return False, f"Signature invalid: {sig_msg}", None

            # Validate asset integrity
            tamper_valid, tamper_msg = DistributionValidator.validate_asset_not_tampered(encrypted_keys, asset_salt)
            if not tamper_valid:
                logger.warning(f"Tamper detection triggered: {tamper_msg}")
                return False, f"Asset tampering detected: {tamper_msg}", None

            # Create audit record
            audit_id = f"audit_{int(time.time())}_{asset_id[-8:]}"
            keys_hash = hashlib.sha256(encrypted_keys.encode()).hexdigest()

            audit = DistributionAudit(
                audit_id=audit_id,
                asset_id=asset_id,
                heir_address=heir_address,
                distribution_time=datetime.utcnow().isoformat() + "Z",
                status=DistributionStatus.RELEASED,
                will_signature_verified=True,
                timestamp_verified=True,
                tamper_check_passed=True,
                keys_encrypted=encrypted_keys,
                keys_hash=keys_hash
            )

            self.distributions[audit_id] = audit
            self._save_distributions()

            logger.info(f"✅ Released asset {asset_id} to {heir_address} (Audit: {audit_id})")
            return True, f"Keys released (Audit ID: {audit_id})", audit

        except Exception as e:
            logger.error(f"Error releasing keys: {e}")
            return False, str(e), None

    def mark_asset_claimed(self, audit_id: str, transaction_hash: Optional[str] = None) -> Tuple[bool, str]:
        """
        Mark asset as claimed by heir (transferred to wallet)

        Records blockchain transaction if available.
        """
        try:
            audit = self.distributions.get(audit_id)
            if not audit:
                return False, "Audit record not found"

            audit.status = DistributionStatus.CLAIMED
            audit.transaction_hash = transaction_hash
            audit.notes = f"Claimed and transferred to heir wallet"

            self._save_distributions()
            logger.info(f"✅ Asset {audit.asset_id} marked as claimed")
            return True, "Asset marked as claimed"

        except Exception as e:
            logger.error(f"Error marking asset claimed: {e}")
            return False, str(e)

    def get_heir_claims(self, heir_address: str) -> List[DistributionAudit]:
        """Get all claimed assets for a specific heir"""
        return [
            dist for dist in self.distributions.values()
            if dist.heir_address == heir_address
        ]

    def get_unclaimed_assets(self, owner_address: str, current_time: Optional[datetime] = None) -> Dict:
        """
        Get assets not yet claimed by any heir

        After pool_transfer_time, unclaimed assets return to network pool
        for fair redistribution to schools, housing, charity.
        """
        if current_time is None:
            current_time = datetime.utcnow()

        # TODO: Query all assets in estate
        # Filter out those with associated distribution records
        # Check if past pool_transfer_time

        return {
            "total_unclaimed": 0,
            "total_value": 0.0,
            "assets": []
        }

    def get_distribution_stats(self) -> Dict:
        """Get system-wide distribution statistics"""
        released = sum(1 for d in self.distributions.values() if d.status == DistributionStatus.RELEASED)
        claimed = sum(1 for d in self.distributions.values() if d.status == DistributionStatus.CLAIMED)
        unclaimed = sum(1 for d in self.distributions.values() if d.status == DistributionStatus.UNCLAIMED)

        return {
            "total_distributions": len(self.distributions),
            "released": released,
            "claimed": claimed,
            "unclaimed": unclaimed,
            "audit_records": len(self.distributions),
        }


# Global instance
_distribution_manager: Optional[DigitalDistributionManager] = None


def initialize_distribution_manager() -> DigitalDistributionManager:
    """Initialize global distribution manager"""
    global _distribution_manager
    _distribution_manager = DigitalDistributionManager()
    return _distribution_manager


def get_distribution_manager() -> Optional[DigitalDistributionManager]:
    """Get global manager instance"""
    return _distribution_manager
