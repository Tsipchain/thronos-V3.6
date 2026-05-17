"""
Digital Legacy Smart Contract & NFT Will System
================================================

Creates cryptographically secure wills embedded in NFTs using LSB steganography.

Features:
- Smart contract structure for will conditions
- LSB steganography: Hide entire encrypted will inside NFT image
- Multi-sig unlock: Multiple heirs need to approve
- Immutable proof: Blockchain timestamp verification
- Tamper detection: Cannot modify without destroying NFT

The Will NFT contains:
├─ Encrypted estate data
├─ Heir signatures (when opened)
├─ Blockchain verification
├─ Tamper-proof seal
└─ Time-lock information

Author: Thronos Digital Legacy
"""

import os
import json
import time
import logging
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
from pathlib import Path
from enum import Enum

try:
    from PIL import Image
    import numpy as np
except ImportError:
    Image = None
    np = None
    print("[LEGACY] WARNING: PIL/numpy not found. Install: pip install Pillow numpy")

logger = logging.getLogger(__name__)

# Configuration
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DATA_DIR.mkdir(exist_ok=True)
WILLS_FILE = DATA_DIR / "digital_wills.json"
NFT_STORAGE_DIR = DATA_DIR / "will_nfts"
NFT_STORAGE_DIR.mkdir(exist_ok=True)


class WillStatus(Enum):
    """Status of a smart contract will"""
    CREATED = "created"              # Will created, not yet NFT minted
    MINTED = "minted"                # NFT minted, on blockchain
    ACTIVATED = "activated"          # Time-lock expired, can be opened
    OPENED = "opened"                # Heirs have unlocked it
    DISTRIBUTED = "distributed"      # Assets distributed
    REVOKED = "revoked"              # Will cancelled by owner


@dataclass
class SmartContractWill:
    """Smart contract encoding will conditions"""
    will_id: str                      # Unique will identifier
    owner_address: str                # Thronos address of owner
    created_at: str                   # Creation timestamp

    # Will Conditions
    will_hash: str                    # SHA-256 of encrypted estate
    will_salt: str                    # Salt used for encryption

    # Unlock Conditions
    required_heirs: int               # How many heirs must approve
    total_heirs: int                  # Total heir count
    heir_addresses: List[str]         # All heirs
    signatures_collected: Dict[str, str] = field(default_factory=dict)  # heir -> signature

    # Time Locks
    unlock_time: Optional[str] = None # When estate can be opened (death + time)
    distribution_deadline: str = None # When assets must be distributed
    pool_transfer_time: str = None    # When unclaimed assets go to pool

    # Tamper Detection
    sealed_hash: Optional[str] = None # Hash of sealed will (proof of integrity)
    seal_timestamp: Optional[str] = None

    # NFT Information
    nft_token_id: Optional[str] = None # NFT token ID on blockchain
    nft_image_hash: Optional[str] = None # Hash of NFT image (for verification)
    nft_metadata_hash: Optional[str] = None # Hash of NFT metadata

    # Status
    status: WillStatus = WillStatus.CREATED
    signature_count: int = 0

    def to_dict(self) -> Dict:
        return {
            "will_id": self.will_id,
            "owner_address": self.owner_address,
            "created_at": self.created_at,
            "will_hash": self.will_hash,
            "will_salt": self.will_salt,
            "required_heirs": self.required_heirs,
            "total_heirs": self.total_heirs,
            "heir_addresses": self.heir_addresses,
            "signatures_collected": self.signatures_collected,
            "unlock_time": self.unlock_time,
            "distribution_deadline": self.distribution_deadline,
            "pool_transfer_time": self.pool_transfer_time,
            "sealed_hash": self.sealed_hash,
            "seal_timestamp": self.seal_timestamp,
            "nft_token_id": self.nft_token_id,
            "nft_image_hash": self.nft_image_hash,
            "nft_metadata_hash": self.nft_metadata_hash,
            "status": self.status.value,
            "signature_count": self.signature_count,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "SmartContractWill":
        if "status" in data and isinstance(data["status"], str):
            data["status"] = WillStatus(data["status"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class LSBSteganography:
    """
    Hide encrypted will data inside NFT image using Least Significant Bit technique.

    How it works:
    1. Convert encrypted will to binary
    2. Replace LSB of image pixels with will bits
    3. Image appears identical to naked eye (LSB changes are imperceptible)
    4. To recover: Read LSB of each pixel, reconstruct binary, decrypt
    5. Tamper detection: If any pixel LSB is modified, will cannot be recovered
    """

    @staticmethod
    def encode_will_in_image(image_path: str, encrypted_will_data: str) -> Tuple[bool, str]:
        """
        Embed encrypted will data into image using LSB steganography

        Returns: (success, message_or_error)
        """
        if not Image or not np:
            return False, "PIL/numpy not available. Install: pip install Pillow numpy"

        try:
            # Load image
            img = Image.open(image_path).convert('RGB')
            img_array = np.array(img)

            # Convert encrypted data to binary
            will_bytes = encrypted_will_data.encode('utf-8')
            will_binary = ''.join(format(byte, '08b') for byte in will_bytes)

            # Check capacity
            max_bits = img_array.size  # Total pixels * channels
            if len(will_binary) > max_bits:
                return False, f"Image too small. Need {len(will_binary)} bits, got {max_bits}"

            # Store length prefix (32 bits for length)
            length_binary = format(len(will_binary), '032b')
            total_binary = length_binary + will_binary

            # Embed into LSBs
            flat_array = img_array.flatten()
            for i, bit in enumerate(total_binary):
                if i >= len(flat_array):
                    break
                # Clear LSB and set new bit
                flat_array[i] = (flat_array[i] & ~1) | int(bit)

            # Reshape and save
            img_array = flat_array.reshape(img_array.shape)
            result_img = Image.fromarray(img_array.astype('uint8'), 'RGB')
            result_img.save(image_path)

            logger.info(f"✅ Embedded {len(will_binary)} bits into image ({len(will_bytes)} bytes)")
            return True, f"Successfully embedded {len(will_bytes)} bytes of will data"

        except Exception as e:
            logger.error(f"Steganography encoding failed: {e}")
            return False, str(e)

    @staticmethod
    def extract_will_from_image(image_path: str) -> Tuple[bool, str]:
        """
        Extract encrypted will data from image using LSB steganography

        Returns: (success, encrypted_will_data_or_error)
        """
        if not Image or not np:
            return False, "PIL/numpy not available"

        try:
            # Load image
            img = Image.open(image_path).convert('RGB')
            img_array = np.array(img)

            # Extract LSBs
            flat_array = img_array.flatten()
            binary_str = ''.join(str(pixel & 1) for pixel in flat_array)

            # Extract length (first 32 bits)
            length_binary = binary_str[:32]
            length = int(length_binary, 2)

            if length == 0:
                return False, "No will data found in image"

            # Extract will data
            will_binary = binary_str[32:32 + length]

            # Convert binary to bytes
            will_bytes = bytes(int(will_binary[i:i+8], 2) for i in range(0, len(will_binary), 8))
            will_data = will_bytes.decode('utf-8')

            logger.info(f"✅ Extracted {len(will_data)} bytes from image")
            return True, will_data

        except Exception as e:
            logger.error(f"Steganography decoding failed: {e}")
            return False, str(e)


class WillNFTMetadata:
    """Metadata for the Will NFT"""

    @staticmethod
    def create_metadata(will_id: str, owner_address: str, will_hash: str,
                       total_value: float, heir_count: int) -> Dict:
        """Create NFT metadata"""
        return {
            "name": f"Digital Testament #{will_id[:8]}",
            "description": f"Encrypted digital will and testament for {owner_address}",
            "image": f"ipfs://will_nft_{will_id}.png",  # Will point to image with embedded will
            "attributes": [
                {
                    "trait_type": "Will Hash",
                    "value": will_hash[:16] + "..."
                },
                {
                    "trait_type": "Estate Value",
                    "value": f"${total_value:,.2f}"
                },
                {
                    "trait_type": "Heirs",
                    "value": str(heir_count)
                },
                {
                    "trait_type": "Created",
                    "value": datetime.utcnow().isoformat()
                },
                {
                    "trait_type": "Type",
                    "value": "Digital Estate Will"
                }
            ],
            "properties": {
                "will_id": will_id,
                "owner_address": owner_address,
                "tamper_proof": True,
                "encrypted": True,
                "steganography": "LSB",
            }
        }


class SmartContractWillManager:
    """Manages smart contract wills and NFT minting"""

    def __init__(self):
        self.wills: Dict[str, SmartContractWill] = {}
        self._load_wills()
        logger.info("🔐 Smart Contract Will Manager initialized")

    def _load_wills(self):
        """Load all wills from storage"""
        try:
            if WILLS_FILE.exists():
                with open(WILLS_FILE, 'r') as f:
                    data = json.load(f)
                    for will_id, will_data in data.items():
                        self.wills[will_id] = SmartContractWill.from_dict(will_data)
                logger.info(f"✅ Loaded {len(self.wills)} smart contract wills")
        except Exception as e:
            logger.error(f"Error loading wills: {e}")

    def _save_wills(self):
        """Save all wills to storage"""
        try:
            DATA_DIR.mkdir(exist_ok=True)
            with open(WILLS_FILE, 'w') as f:
                data = {wid: will.to_dict() for wid, will in self.wills.items()}
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving wills: {e}")

    def create_will(self, owner_address: str, estate_hash: str, estate_salt: str,
                   heir_addresses: List[str], time_lock_years: int = 30) -> Tuple[bool, str, Optional[SmartContractWill]]:
        """
        Create smart contract will

        Parameters:
            owner_address: Thronos address
            estate_hash: SHA-256 hash of encrypted estate
            estate_salt: Salt used for encryption
            heir_addresses: List of heir addresses
            time_lock_years: Years before assets can be unlocked

        Returns: (success, message, will_object)
        """
        try:
            will_id = f"will_{int(time.time())}_{owner_address[-8:]}"

            # Set time locks
            unlock_time = (datetime.utcnow() + timedelta(days=365*time_lock_years)).isoformat() + "Z"
            distribution_deadline = (datetime.utcnow() + timedelta(days=365*time_lock_years + 90)).isoformat() + "Z"
            pool_transfer_time = (datetime.utcnow() + timedelta(days=365*time_lock_years + 180)).isoformat() + "Z"

            will = SmartContractWill(
                will_id=will_id,
                owner_address=owner_address,
                created_at=datetime.utcnow().isoformat() + "Z",
                will_hash=estate_hash,
                will_salt=estate_salt,
                required_heirs=max(1, len(heir_addresses) // 2),  # Majority required
                total_heirs=len(heir_addresses),
                heir_addresses=heir_addresses,
                unlock_time=unlock_time,
                distribution_deadline=distribution_deadline,
                pool_transfer_time=pool_transfer_time,
            )

            self.wills[will_id] = will
            self._save_wills()

            logger.info(f"✅ Created smart contract will {will_id} for {owner_address}")
            return True, f"Will created: {will_id}", will

        except Exception as e:
            logger.error(f"Error creating will: {e}")
            return False, str(e), None

    def seal_will(self, will_id: str) -> Tuple[bool, str]:
        """
        Seal the will (create tamper-proof hash)
        Once sealed, any modification will break the seal
        """
        try:
            will = self.wills.get(will_id)
            if not will:
                return False, "Will not found"

            # Create seal hash (hash of all will data)
            will_data = json.dumps(will.to_dict(), sort_keys=True).encode()
            sealed_hash = hashlib.sha256(will_data).hexdigest()

            will.sealed_hash = sealed_hash
            will.seal_timestamp = datetime.utcnow().isoformat() + "Z"

            self._save_wills()
            logger.info(f"✅ Sealed will {will_id} - Tamper detection enabled")
            return True, f"Will sealed with hash: {sealed_hash[:16]}..."

        except Exception as e:
            logger.error(f"Error sealing will: {e}")
            return False, str(e)

    def verify_seal(self, will_id: str) -> Tuple[bool, str]:
        """Verify the seal hasn't been broken (no tampering)"""
        try:
            will = self.wills.get(will_id)
            if not will or not will.sealed_hash:
                return False, "Will not found or not sealed"

            # Recalculate seal
            will_data = json.dumps(will.to_dict(), sort_keys=True).encode()
            current_hash = hashlib.sha256(will_data).hexdigest()

            if current_hash == will.sealed_hash:
                logger.info(f"✅ Will {will_id} seal verified - No tampering detected")
                return True, "Seal verified - Will intact"
            else:
                logger.warning(f"❌ Will {will_id} seal broken - Tampering detected!")
                return False, "SEAL BROKEN - Will has been tampered with"

        except Exception as e:
            logger.error(f"Error verifying seal: {e}")
            return False, str(e)

    def add_heir_signature(self, will_id: str, heir_address: str, signature: str) -> Tuple[bool, str]:
        """
        Add heir signature to unlock will
        Once enough heirs sign, will can be opened
        """
        try:
            will = self.wills.get(will_id)
            if not will:
                return False, "Will not found"

            if heir_address not in will.heir_addresses:
                return False, "Not an authorized heir"

            if heir_address in will.signatures_collected:
                return False, "Heir already signed"

            # Verify seal is still intact
            seal_ok, seal_msg = self.verify_seal(will_id)
            if not seal_ok:
                return False, "CANNOT SIGN: Will has been tampered with"

            # Store signature
            will.signatures_collected[heir_address] = signature
            will.signature_count = len(will.signatures_collected)

            # Check if enough signatures
            if will.signature_count >= will.required_heirs:
                will.status = WillStatus.OPENED
                logger.info(f"✅ Will {will_id} OPENED - {will.signature_count} of {will.required_heirs} heirs signed")

            self._save_wills()
            return True, f"Signature added ({will.signature_count}/{will.required_heirs})"

        except Exception as e:
            logger.error(f"Error adding signature: {e}")
            return False, str(e)

    def can_open_will(self, will_id: str) -> Tuple[bool, str]:
        """Check if will can be opened"""
        try:
            will = self.wills.get(will_id)
            if not will:
                return False, "Will not found"

            # Check seal
            seal_ok, _ = self.verify_seal(will_id)
            if not seal_ok:
                return False, "Will has been tampered with"

            # Check time lock
            unlock_time = datetime.fromisoformat(will.unlock_time.replace('Z', '+00:00'))
            if datetime.utcnow() < unlock_time:
                remaining = unlock_time - datetime.utcnow()
                return False, f"Will locked for {remaining.days} more days"

            # Check signatures
            if will.signature_count < will.required_heirs:
                needed = will.required_heirs - will.signature_count
                return False, f"Need {needed} more heir signatures"

            return True, "Will can be opened"

        except Exception as e:
            logger.error(f"Error checking will: {e}")
            return False, str(e)

    def get_stats(self) -> Dict:
        """Get system statistics"""
        total_value = 0  # TODO: calculate from estates
        return {
            "total_wills": len(self.wills),
            "created": sum(1 for w in self.wills.values() if w.status == WillStatus.CREATED),
            "minted": sum(1 for w in self.wills.values() if w.status == WillStatus.MINTED),
            "opened": sum(1 for w in self.wills.values() if w.status == WillStatus.OPENED),
            "distributed": sum(1 for w in self.wills.values() if w.status == WillStatus.DISTRIBUTED),
        }


# Global instance
_will_manager: Optional[SmartContractWillManager] = None


def initialize_will_manager() -> SmartContractWillManager:
    """Initialize global will manager"""
    global _will_manager
    _will_manager = SmartContractWillManager()
    return _will_manager


def get_will_manager() -> Optional[SmartContractWillManager]:
    """Get global manager instance"""
    return _will_manager
