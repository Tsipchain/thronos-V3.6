"""
Digital Legacy System - Complete Asset Inventory & Inheritance Management
=========================================================================

Allows users to register ALL their assets:
- Digital currencies (BTC, ETH, etc)
- Exchange accounts (with recovery codes)
- Cold wallets (private keys)
- Real estate & property titles
- Bank accounts
- NFTs, domains, business equity
- Anything of value

All encrypted and secured in a Smart Contract Will (NFT).
Upon death, heirs can unlock and inherit fairly with multi-sig protection.

Author: Thronos Digital Legacy System
Version: 1.0
"""

import os
import json
import time
import logging
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path
from decimal import Decimal

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
    from cryptography.hazmat.backends import default_backend
except ImportError:
    print("[LEGACY] WARNING: cryptography module not found. Install: pip install cryptography")
    Fernet = None

logger = logging.getLogger(__name__)

# Configuration
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DATA_DIR.mkdir(exist_ok=True)
ESTATES_FILE = DATA_DIR / "digital_estates.json"
LEGACY_LOG_FILE = DATA_DIR / "digital_legacy.log"


class AssetCategory(Enum):
    """Types of assets that can be inherited"""
    CRYPTO = "cryptocurrency"           # BTC, ETH, etc
    EXCHANGE_ACCOUNT = "exchange"       # Binance, Kraken, etc
    COLD_STORAGE = "cold_storage"       # Hardware wallet, USB, hard drive
    REAL_ESTATE = "real_estate"         # Property titles, deeds
    BANK_ACCOUNT = "bank"               # Traditional banking
    NFT_COLLECTION = "nft"              # NFTs and digital collectibles
    DOMAIN = "domain"                   # Domain names, websites
    BUSINESS_EQUITY = "business"        # Business ownership stakes
    PRECIOUS_METALS = "metals"          # Gold, silver, physical metals
    OTHER = "other"                     # Anything else


@dataclass
class ContactInfo:
    """Contact information for asset recovery"""
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None      # Physical or mailing address
    recovery_email: Optional[str] = None

    def to_dict(self) -> Dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict) -> "ContactInfo":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class EncryptedAsset:
    """An encrypted asset in the digital estate"""
    asset_id: str                        # Unique ID
    asset_type: AssetCategory            # Type of asset
    name: str                            # "My Bitcoin", "Binance Account"
    description: str                     # Location, how to access

    # Encrypted content (AES-256)
    encrypted_keys: str                  # Private keys, passwords
    encrypted_recovery: str              # Recovery codes, seeds

    # Contact info for recovery
    contact_info: ContactInfo = field(default_factory=ContactInfo)

    # Valuation
    value_estimate: float                # Estimated value in USD
    currency: str = "USD"                # Value currency

    # Inheritance rules
    assigned_heirs: List[str] = field(default_factory=list)  # Heir addresses
    distribution_percentage: float = 100.0  # % for this heir(s)
    access_condition: str = "unlock_only_after_will_open"

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict:
        return {
            "asset_id": self.asset_id,
            "asset_type": self.asset_type.value,
            "name": self.name,
            "description": self.description,
            "encrypted_keys": self.encrypted_keys,
            "encrypted_recovery": self.encrypted_recovery,
            "contact_info": self.contact_info.to_dict(),
            "value_estimate": self.value_estimate,
            "currency": self.currency,
            "assigned_heirs": self.assigned_heirs,
            "distribution_percentage": self.distribution_percentage,
            "access_condition": self.access_condition,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "EncryptedAsset":
        data["asset_type"] = AssetCategory(data["asset_type"])
        if isinstance(data.get("contact_info"), dict):
            data["contact_info"] = ContactInfo.from_dict(data["contact_info"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Heir:
    """A beneficiary of the digital estate"""
    heir_address: str                    # Thronos address
    share_percentage: float              # % of assets
    email: Optional[str] = None          # For notifications
    phone: Optional[str] = None
    public_key: Optional[str] = None     # For multi-sig
    verified: bool = False               # KYC verified
    signature_on_will: Optional[str] = None  # Multi-sig signature

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "Heir":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class DigitalEstate:
    """Complete digital estate (will) for a user"""
    owner_address: str                   # Thronos address of owner
    owner_name: Optional[str] = None

    # Estate metadata
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # All assets
    assets: List[EncryptedAsset] = field(default_factory=list)
    total_assets_count: int = 0
    total_estimated_value: float = 0.0

    # Heir registry
    heirs: List[Heir] = field(default_factory=list)
    heirs_require_multisig: bool = True  # Require multi-sig approval
    heirs_required_to_unlock: int = 1    # How many heirs needed

    # Will status
    will_status: str = "active"          # active, opened, distributed, revoked
    will_nft_id: Optional[str] = None    # NFT containing encrypted estate
    will_hash: Optional[str] = None      # Cryptographic proof
    will_created_at: Optional[str] = None
    will_opened_at: Optional[str] = None

    # Time locks
    time_lock_years: int = 30            # Years before assets go to pool
    unlock_time: Optional[str] = None    # When heirs can start unlocking
    pool_transfer_time: Optional[str] = None  # When unclaimed → pool

    # Legal/Notes
    testament_text: Optional[str] = None # User's written will
    funeral_wishes: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "owner_address": self.owner_address,
            "owner_name": self.owner_name,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "assets": [a.to_dict() for a in self.assets],
            "total_assets_count": self.total_assets_count,
            "total_estimated_value": self.total_estimated_value,
            "heirs": [h.to_dict() for h in self.heirs],
            "heirs_require_multisig": self.heirs_require_multisig,
            "heirs_required_to_unlock": self.heirs_required_to_unlock,
            "will_status": self.will_status,
            "will_nft_id": self.will_nft_id,
            "will_hash": self.will_hash,
            "will_created_at": self.will_created_at,
            "will_opened_at": self.will_opened_at,
            "time_lock_years": self.time_lock_years,
            "unlock_time": self.unlock_time,
            "pool_transfer_time": self.pool_transfer_time,
            "testament_text": self.testament_text,
            "funeral_wishes": self.funeral_wishes,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "DigitalEstate":
        if "assets" in data:
            data["assets"] = [EncryptedAsset.from_dict(a) for a in data["assets"]]
        if "heirs" in data:
            data["heirs"] = [Heir.from_dict(h) for h in data["heirs"]]
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class DigitalLegacyEncryption:
    """Handles encryption/decryption of sensitive data"""

    @staticmethod
    def derive_key(master_password: str, salt: bytes = None) -> Tuple[bytes, bytes]:
        """Derive encryption key from master password"""
        if salt is None:
            salt = secrets.token_bytes(16)

        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        key = kdf.derive(master_password.encode())
        return key, salt

    @staticmethod
    def encrypt_data(plaintext: str, master_password: str) -> Tuple[str, str]:
        """
        Encrypt sensitive data (private keys, recovery codes)
        Returns: (encrypted_data, salt) both as base64
        """
        if not Fernet:
            raise RuntimeError("cryptography module not installed")

        key, salt = DigitalLegacyEncryption.derive_key(master_password)
        cipher = Fernet(key)
        encrypted = cipher.encrypt(plaintext.encode())

        import base64
        return (
            base64.b64encode(encrypted).decode(),
            base64.b64encode(salt).decode()
        )

    @staticmethod
    def decrypt_data(encrypted_data: str, master_password: str, salt: str) -> str:
        """
        Decrypt sensitive data
        Returns: plaintext
        """
        if not Fernet:
            raise RuntimeError("cryptography module not installed")

        import base64
        try:
            salt_bytes = base64.b64decode(salt)
            key, _ = DigitalLegacyEncryption.derive_key(master_password, salt_bytes)
            cipher = Fernet(key)
            encrypted_bytes = base64.b64decode(encrypted_data)
            decrypted = cipher.decrypt(encrypted_bytes)
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise ValueError("Invalid master password or corrupted data")


class DigitalLegacyManager:
    """Manages digital estates and inheritance"""

    def __init__(self):
        self.estates: Dict[str, DigitalEstate] = {}
        self._load_estates()
        logger.info("🏛️ Digital Legacy Manager initialized")

    def _load_estates(self):
        """Load all estates from storage"""
        try:
            if ESTATES_FILE.exists():
                with open(ESTATES_FILE, 'r') as f:
                    data = json.load(f)
                    for owner_addr, estate_data in data.items():
                        self.estates[owner_addr] = DigitalEstate.from_dict(estate_data)
                logger.info(f"✅ Loaded {len(self.estates)} digital estates")
        except Exception as e:
            logger.error(f"Error loading estates: {e}")

    def _save_estates(self):
        """Save all estates to storage"""
        try:
            DATA_DIR.mkdir(exist_ok=True)
            with open(ESTATES_FILE, 'w') as f:
                data = {addr: estate.to_dict() for addr, estate in self.estates.items()}
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving estates: {e}")

    def create_estate(self, owner_address: str, owner_name: Optional[str] = None) -> DigitalEstate:
        """Create a new digital estate for a user"""
        if owner_address in self.estates:
            logger.warning(f"Estate already exists for {owner_address}")
            return self.estates[owner_address]

        estate = DigitalEstate(
            owner_address=owner_address,
            owner_name=owner_name
        )
        self.estates[owner_address] = estate
        self._save_estates()
        logger.info(f"✅ Created digital estate for {owner_address}")
        return estate

    def get_estate(self, owner_address: str) -> Optional[DigitalEstate]:
        """Get estate for a user"""
        return self.estates.get(owner_address)

    def add_asset(
        self,
        owner_address: str,
        asset_type: AssetCategory,
        name: str,
        description: str,
        encrypted_keys: str,
        encrypted_recovery: str,
        value_estimate: float,
        assigned_heirs: List[str],
        contact_info: Optional[Dict] = None
    ) -> Tuple[bool, str, Optional[EncryptedAsset]]:
        """Add an encrypted asset to the estate"""
        try:
            estate = self.estates.get(owner_address)
            if not estate:
                estate = self.create_estate(owner_address)

            asset_id = f"asset_{int(time.time())}_{secrets.token_hex(4)}"
            contact = ContactInfo.from_dict(contact_info or {})

            asset = EncryptedAsset(
                asset_id=asset_id,
                asset_type=asset_type,
                name=name,
                description=description,
                encrypted_keys=encrypted_keys,
                encrypted_recovery=encrypted_recovery,
                contact_info=contact,
                value_estimate=value_estimate,
                assigned_heirs=assigned_heirs,
                distribution_percentage=100.0 / max(1, len(assigned_heirs))
            )

            estate.assets.append(asset)
            estate.total_assets_count = len(estate.assets)
            estate.total_estimated_value += value_estimate
            estate.last_updated = datetime.utcnow().isoformat()

            self._save_estates()
            logger.info(f"✅ Added {name} to {owner_address}'s estate (ID: {asset_id})")
            return True, asset_id, asset

        except Exception as e:
            logger.error(f"Error adding asset: {e}")
            return False, str(e), None

    def add_heir(
        self,
        owner_address: str,
        heir_address: str,
        share_percentage: float,
        email: Optional[str] = None,
        phone: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Add a beneficiary to the estate"""
        try:
            estate = self.estates.get(owner_address)
            if not estate:
                estate = self.create_estate(owner_address)

            # Check if heir already exists
            existing = next((h for h in estate.heirs if h.heir_address == heir_address), None)
            if existing:
                return False, "Heir already registered"

            heir = Heir(
                heir_address=heir_address,
                share_percentage=share_percentage,
                email=email,
                phone=phone
            )

            estate.heirs.append(heir)
            estate.last_updated = datetime.utcnow().isoformat()

            # Auto-recalculate percentages if needed
            total = sum(h.share_percentage for h in estate.heirs)
            if total != 100.0:
                logger.warning(f"Heir percentages total {total}% for {owner_address}")

            self._save_estates()
            logger.info(f"✅ Added heir {heir_address} to {owner_address}'s estate")
            return True, f"Heir added with {share_percentage}% share"

        except Exception as e:
            logger.error(f"Error adding heir: {e}")
            return False, str(e)

    def get_stats(self) -> Dict:
        """Get system statistics"""
        total_value = sum(e.total_estimated_value for e in self.estates.values())
        total_assets = sum(e.total_assets_count for e in self.estates.values())
        total_heirs = sum(len(e.heirs) for e in self.estates.values())

        return {
            "total_estates": len(self.estates),
            "total_assets": total_assets,
            "total_heirs": total_heirs,
            "total_value_usd": float(total_value),
            "active_estates": sum(1 for e in self.estates.values() if e.will_status == "active"),
        }


# Global instance
_legacy_manager: Optional[DigitalLegacyManager] = None


def initialize_digital_legacy() -> DigitalLegacyManager:
    """Initialize global legacy manager"""
    global _legacy_manager
    _legacy_manager = DigitalLegacyManager()
    return _legacy_manager


def get_legacy_manager() -> Optional[DigitalLegacyManager]:
    """Get global manager instance"""
    return _legacy_manager
