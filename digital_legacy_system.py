"""
Digital Legacy System for Thronos Blockchain
Enables decentralized inheritance, asset protection, and heir verification
"""

import json
import time
import hashlib
import qrcode
import os
from typing import Dict, List, Optional, Any
from datetime import datetime
from io import BytesIO
import base64


class DigitalLegacySystem:
    """
    Manages digital wills, inheritance NFTs, and heir verification.

    Features:
    - NFT-based digital wills
    - Biometric heir verification
    - Immutable asset audit trail
    - QR code recovery
    - Automated heir distribution
    """

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = data_dir
        self.legacy_file = os.path.join(data_dir, "digital_legacies.json")
        self.heirs_file = os.path.join(data_dir, "heir_verification.json")
        self.asset_trail_file = os.path.join(data_dir, "asset_audit_trail.json")
        self._ensure_files_exist()

    def _ensure_files_exist(self):
        """Ensure all data files exist."""
        for path in [self.legacy_file, self.heirs_file, self.asset_trail_file]:
            if not os.path.exists(path):
                with open(path, 'w') as f:
                    json.dump([], f)

    def _load_json(self, path: str) -> List[Dict]:
        """Load JSON file safely."""
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except:
            return []

    def _save_json(self, path: str, data: List[Dict]):
        """Save JSON file safely."""
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    def create_legacy_document(
        self,
        owner_address: str,
        owner_signature: str,
        assets: List[Dict[str, Any]],
        heirs: List[Dict[str, str]],
        metadata: Dict[str, str] = None
    ) -> Dict[str, Any]:
        """
        Create a digital legacy document (NFT-based will).

        Args:
            owner_address: THR address of asset owner
            owner_signature: Digital signature from owner
            assets: List of assets to inherit (wallets, tokens, properties)
            heirs: List of heirs with verification requirements
            metadata: Optional metadata (name, created_date, etc)

        Returns:
            Legacy document with NFT details
        """

        # Validate signature (simplified - in production use full crypto)
        sig_hash = hashlib.sha256(owner_signature.encode()).hexdigest()
        if not owner_signature or len(owner_signature) < 32:
            raise ValueError("Invalid owner signature")

        legacy_id = hashlib.sha256(
            f"{owner_address}{int(time.time())}".encode()
        ).hexdigest()[:16]

        legacy_doc = {
            "legacy_id": legacy_id,
            "owner_address": owner_address,
            "owner_signature_hash": sig_hash,
            "created_timestamp": int(time.time()),
            "created_date": datetime.now().isoformat(),
            "assets": assets,
            "heirs": heirs,
            "nft_contract": f"LEGACY_NFT_{legacy_id}",
            "nft_token_id": legacy_id,
            "status": "active",
            "total_asset_value_thr": sum(a.get("value_thr", 0) for a in assets),
            "metadata": metadata or {"description": "Digital Legacy Document"},
            "immutable_proof": self._create_immutable_proof(owner_address, assets)
        }

        legacies = self._load_json(self.legacy_file)
        legacies.append(legacy_doc)
        self._save_json(self.legacy_file, legacies)

        # Add to audit trail
        self._add_audit_entry(
            legacy_id,
            "created",
            owner_address,
            f"Legacy created with {len(heirs)} heirs"
        )

        return legacy_doc

    def register_heir(
        self,
        legacy_id: str,
        heir_address: str,
        heir_name: str,
        biometric_hash: str,
        genetic_marker: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Register an heir with biometric/genetic verification.

        Args:
            legacy_id: ID of the legacy document
            heir_address: THR address of heir
            heir_name: Name of heir
            biometric_hash: Hash of biometric data (fingerprint, face, iris)
            genetic_marker: Optional genetic marker for verification

        Returns:
            Heir registration record
        """

        heir_record = {
            "heir_id": hashlib.sha256(
                f"{heir_address}{int(time.time())}".encode()
            ).hexdigest()[:16],
            "legacy_id": legacy_id,
            "heir_address": heir_address,
            "heir_name": heir_name,
            "biometric_hash": biometric_hash,
            "genetic_marker": genetic_marker,
            "verified": False,
            "verification_timestamp": None,
            "registered_timestamp": int(time.time()),
            "registered_date": datetime.now().isoformat()
        }

        heirs = self._load_json(self.heirs_file)
        heirs.append(heir_record)
        self._save_json(self.heirs_file, heirs)

        self._add_audit_entry(
            legacy_id,
            "heir_registered",
            heir_address,
            f"Heir {heir_name} registered"
        )

        return heir_record

    def verify_heir(
        self,
        heir_id: str,
        biometric_data: str,
        genetic_data: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Verify heir identity using biometric/genetic data.

        Args:
            heir_id: ID of heir record
            biometric_data: Biometric data for verification
            genetic_data: Optional genetic data for verification

        Returns:
            Verification result with access token
        """

        heirs = self._load_json(self.heirs_file)
        heir = next((h for h in heirs if h["heir_id"] == heir_id), None)

        if not heir:
            raise ValueError("Heir not found")

        # Verify biometric match
        provided_hash = hashlib.sha256(biometric_data.encode()).hexdigest()
        biometric_match = provided_hash == heir["biometric_hash"]

        # Verify genetic marker if provided
        genetic_match = True
        if heir.get("genetic_marker") and genetic_data:
            provided_genetic = hashlib.sha256(genetic_data.encode()).hexdigest()
            genetic_match = provided_genetic == heir["genetic_marker"]

        if not (biometric_match and genetic_match):
            return {
                "verified": False,
                "error": "Biometric/genetic verification failed"
            }

        # Update heir record
        heir["verified"] = True
        heir["verification_timestamp"] = int(time.time())

        # Find and update in list
        for i, h in enumerate(heirs):
            if h["heir_id"] == heir_id:
                heirs[i] = heir
                break

        self._save_json(self.heirs_file, heirs)

        # Generate access token
        access_token = hashlib.sha256(
            f"{heir_id}{int(time.time())}".encode()
        ).hexdigest()

        self._add_audit_entry(
            heir["legacy_id"],
            "heir_verified",
            heir["heir_address"],
            f"Heir {heir['heir_name']} verified"
        )

        return {
            "verified": True,
            "heir_id": heir_id,
            "heir_name": heir["heir_name"],
            "access_token": access_token,
            "access_valid_until": int(time.time()) + (30 * 24 * 3600)  # 30 days
        }

    def generate_recovery_qr(
        self,
        legacy_id: str,
        heir_id: str,
        access_token: str
    ) -> Dict[str, Any]:
        """
        Generate QR code for recovery/asset access.

        Args:
            legacy_id: ID of legacy
            heir_id: ID of verified heir
            access_token: Verification access token

        Returns:
            QR code data and recovery link
        """

        recovery_data = {
            "legacy_id": legacy_id,
            "heir_id": heir_id,
            "access_token": access_token,
            "timestamp": int(time.time()),
            "type": "legacy_recovery"
        }

        recovery_json = json.dumps(recovery_data)
        recovery_hash = hashlib.sha256(recovery_json.encode()).hexdigest()

        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(recovery_json)
        qr.make(fit=True)

        qr_img = qr.make_image(fill_color="black", back_color="white")

        # Convert to base64
        buffer = BytesIO()
        qr_img.save(buffer, format='PNG')
        qr_base64 = base64.b64encode(buffer.getvalue()).decode()

        recovery_record = {
            "recovery_id": recovery_hash[:16],
            "legacy_id": legacy_id,
            "heir_id": heir_id,
            "qr_code_base64": qr_base64,
            "qr_code_hash": recovery_hash,
            "generated_timestamp": int(time.time()),
            "generated_date": datetime.now().isoformat(),
            "valid_until": int(time.time()) + (30 * 24 * 3600)
        }

        self._add_audit_entry(
            legacy_id,
            "recovery_qr_generated",
            "",
            f"Recovery QR generated for heir {heir_id}"
        )

        return recovery_record

    def get_legacy_document(self, legacy_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve legacy document by ID."""
        legacies = self._load_json(self.legacy_file)
        return next((l for l in legacies if l["legacy_id"] == legacy_id), None)

    def get_legacy_by_owner(self, owner_address: str) -> List[Dict[str, Any]]:
        """Get all legacy documents for an owner."""
        legacies = self._load_json(self.legacy_file)
        return [l for l in legacies if l["owner_address"] == owner_address]

    def get_heir_legacies(self, heir_address: str) -> List[Dict[str, Any]]:
        """Get all legacy documents where someone is an heir."""
        heirs = self._load_json(self.heirs_file)
        heir_legacy_ids = [h["legacy_id"] for h in heirs if h["heir_address"] == heir_address]

        legacies = self._load_json(self.legacy_file)
        return [l for l in legacies if l["legacy_id"] in heir_legacy_ids]

    def get_audit_trail(self, legacy_id: str) -> List[Dict[str, Any]]:
        """Get complete audit trail for a legacy."""
        trail = self._load_json(self.asset_trail_file)
        return [t for t in trail if t["legacy_id"] == legacy_id]

    def _add_audit_entry(
        self,
        legacy_id: str,
        event_type: str,
        actor_address: str,
        description: str
    ):
        """Add entry to immutable audit trail."""
        trail = self._load_json(self.asset_trail_file)

        entry = {
            "entry_id": hashlib.sha256(
                f"{legacy_id}{event_type}{int(time.time())}".encode()
            ).hexdigest()[:16],
            "legacy_id": legacy_id,
            "event_type": event_type,
            "actor_address": actor_address,
            "description": description,
            "timestamp": int(time.time()),
            "date": datetime.now().isoformat()
        }

        trail.append(entry)
        self._save_json(self.asset_trail_file, trail)

    def _create_immutable_proof(
        self,
        owner_address: str,
        assets: List[Dict]
    ) -> str:
        """Create immutable proof of asset ownership."""
        asset_data = json.dumps(assets, sort_keys=True)
        proof_input = f"{owner_address}:{asset_data}:{int(time.time())}"
        return hashlib.sha256(proof_input.encode()).hexdigest()

    def distribute_to_heir(
        self,
        legacy_id: str,
        heir_id: str,
        access_token: str
    ) -> Dict[str, Any]:
        """
        Execute legacy distribution to verified heir.
        Returns assets and wallet access information.
        """

        # Verify heir is legitimately verified
        heirs = self._load_json(self.heirs_file)
        heir = next((h for h in heirs if h["heir_id"] == heir_id), None)

        if not heir or not heir.get("verified"):
            raise ValueError("Heir not verified")

        legacy = self.get_legacy_document(legacy_id)
        if not legacy:
            raise ValueError("Legacy not found")

        # Create distribution record
        distribution = {
            "distribution_id": hashlib.sha256(
                f"{legacy_id}{heir_id}{int(time.time())}".encode()
            ).hexdigest()[:16],
            "legacy_id": legacy_id,
            "heir_id": heir_id,
            "heir_address": heir["heir_address"],
            "heir_name": heir["heir_name"],
            "distributed_assets": legacy["assets"],
            "total_value_thr": legacy["total_asset_value_thr"],
            "distributed_timestamp": int(time.time()),
            "distributed_date": datetime.now().isoformat(),
            "nft_transfer_receipt": f"LEGACY_TRANSFER_{hashlib.sha256(legacy_id.encode()).hexdigest()[:8]}"
        }

        self._add_audit_entry(
            legacy_id,
            "distributed",
            heir["heir_address"],
            f"Legacy distributed to heir {heir['heir_name']}"
        )

        return distribution


# Solidity contract template for Digital Legacy NFT
LEGACY_NFT_CONTRACT_TEMPLATE = '''
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract DigitalLegacyNFT {
    string public name = "Thronos Digital Legacy";
    string public symbol = "TLEG";

    struct LegacyDocument {
        string legacyId;
        address owner;
        address[] heirs;
        uint256 createdTime;
        bool active;
        string ipfsHash;
    }

    struct Heir {
        address heirAddress;
        bool verified;
        bytes32 biometricHash;
        uint256 verificationTime;
    }

    mapping(string => LegacyDocument) public legacies;
    mapping(string => Heir[]) public heirsList;
    mapping(string => uint256) public tokenIdCounter;

    event LegacyCreated(
        string indexed legacyId,
        address indexed owner,
        uint256 heirCount,
        uint256 timestamp
    );

    event HeirVerified(
        string indexed legacyId,
        address indexed heir,
        uint256 timestamp
    );

    event LegacyDistributed(
        string indexed legacyId,
        address indexed heir,
        uint256 timestamp
    );

    function createLegacy(
        string memory _legacyId,
        address[] memory _heirs,
        string memory _ipfsHash
    ) public {
        require(bytes(_legacyId).length > 0, "Invalid legacy ID");
        require(_heirs.length > 0, "Must have at least one heir");

        legacies[_legacyId] = LegacyDocument({
            legacyId: _legacyId,
            owner: msg.sender,
            heirs: _heirs,
            createdTime: block.timestamp,
            active: true,
            ipfsHash: _ipfsHash
        });

        emit LegacyCreated(_legacyId, msg.sender, _heirs.length, block.timestamp);
    }

    function verifyHeir(
        string memory _legacyId,
        address _heir,
        bytes32 _biometricHash
    ) public {
        require(legacies[_legacyId].owner == msg.sender, "Not legacy owner");

        Heir memory newHeir = Heir({
            heirAddress: _heir,
            verified: true,
            biometricHash: _biometricHash,
            verificationTime: block.timestamp
        });

        heirsList[_legacyId].push(newHeir);
        emit HeirVerified(_legacyId, _heir, block.timestamp);
    }

    function distributeLegacy(
        string memory _legacyId,
        address _heir
    ) public {
        require(legacies[_legacyId].active, "Legacy not active");
        require(legacies[_legacyId].owner != msg.sender, "Owner cannot distribute");

        // Verify heir is in the list and verified
        bool isValidHeir = false;
        for (uint i = 0; i < heirsList[_legacyId].length; i++) {
            if (heirsList[_legacyId][i].heirAddress == _heir &&
                heirsList[_legacyId][i].verified) {
                isValidHeir = true;
                break;
            }
        }

        require(isValidHeir, "Heir not verified");

        legacies[_legacyId].active = false;
        emit LegacyDistributed(_legacyId, _heir, block.timestamp);
    }
}
'''
