"""
Digital Legacy System API
Flask REST API for creating, managing, and claiming digital legacies.

10 endpoints for complete inheritance workflow:
1. Create legacy
2. Register heir
3. Register biometric
4. Add asset
5. Store document
6. Activate legacy
7. Verify heir
8. Claim and distribute
9. Get legacy details
10. Get audit trail
"""

from flask import Flask, request, jsonify
from functools import wraps
from digital_legacy_system import DigitalLegacySystem, LegacyStatus
import json

app = Flask(__name__)
legacy_system = DigitalLegacySystem()

# Rate limiting and auth simulation
VALID_TOKENS = {"demo": "demo_user", "test": "test_user"}


def require_auth(f):
    """Require authentication token"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if token not in VALID_TOKENS:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


@app.route("/api/legacy/create", methods=["POST"])
@require_auth
def create_legacy():
    """
    Create a new digital legacy
    
    POST /api/legacy/create
    {
        "owner_address": "0x...",
        "owner_name": "John Doe",
        "title": "My Digital Estate",
        "description": "Protection for my family"
    }
    """
    try:
        data = request.json
        
        legacy_id = legacy_system.create_legacy(
            owner_address=data["owner_address"],
            owner_name=data["owner_name"],
            title=data.get("title", ""),
            description=data.get("description", "")
        )
        
        return jsonify({
            "success": True,
            "legacy_id": legacy_id,
            "status": "created",
            "message": "Digital legacy created successfully"
        }), 201
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/legacy/<legacy_id>/register-heir", methods=["POST"])
@require_auth
def register_heir(legacy_id):
    """
    Register a heir to the legacy
    
    POST /api/legacy/{legacy_id}/register-heir
    {
        "heir_id": "heir_001",
        "full_name": "Jane Doe",
        "birth_date": "1990-01-01",
        "relationship": "daughter",
        "inheritance_percentage": 50.0
    }
    """
    try:
        data = request.json
        
        heir_id = legacy_system.add_heir_to_legacy(
            legacy_id=legacy_id,
            heir_id=data["heir_id"],
            full_name=data["full_name"],
            birth_date=data["birth_date"],
            relationship=data["relationship"],
            inheritance_percentage=data["inheritance_percentage"]
        )
        
        return jsonify({
            "success": True,
            "heir_id": heir_id,
            "message": "Heir registered successfully"
        }), 201
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/legacy/<legacy_id>/register-biometric", methods=["POST"])
@require_auth
def register_biometric(legacy_id):
    """
    Register heir biometric data
    
    POST /api/legacy/{legacy_id}/register-biometric
    {
        "heir_id": "heir_001",
        "biometric_type": "fingerprint",
        "biometric_data": "<base64_encoded>"
    }
    """
    try:
        data = request.json
        biometric_data = data["biometric_data"].encode() if isinstance(data["biometric_data"], str) else data["biometric_data"]
        
        success = legacy_system.register_heir_biometric(
            legacy_id=legacy_id,
            heir_id=data["heir_id"],
            biometric_type=data["biometric_type"],
            raw_data=biometric_data
        )
        
        return jsonify({
            "success": success,
            "message": "Biometric data registered"
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/legacy/<legacy_id>/add-asset", methods=["POST"])
@require_auth
def add_asset(legacy_id):
    """
    Add an asset to the legacy
    
    POST /api/legacy/{legacy_id}/add-asset
    {
        "asset_type": "thr",
        "description": "1000 THR tokens",
        "value": 1000.0,
        "blockchain_address": "0xaccount"
    }
    """
    try:
        data = request.json
        
        asset_id = legacy_system.add_asset_to_legacy(
            legacy_id=legacy_id,
            asset_type=data["asset_type"],
            description=data["description"],
            value=float(data["value"]),
            blockchain_address=data.get("blockchain_address", "")
        )
        
        return jsonify({
            "success": True,
            "asset_id": asset_id,
            "message": "Asset added to legacy"
        }), 201
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/legacy/<legacy_id>/store-document", methods=["POST"])
@require_auth
def store_document(legacy_id):
    """
    Store a document in the legacy
    
    POST /api/legacy/{legacy_id}/store-document
    {
        "document_type": "will",
        "content_hash": "0x...",
        "ipfs_hash": "Qm...",
        "url": "https://..."
    }
    """
    try:
        data = request.json
        
        doc_id = legacy_system.store_legacy_document(
            legacy_id=legacy_id,
            document_type=data["document_type"],
            content_hash=data["content_hash"],
            ipfs_hash=data.get("ipfs_hash", ""),
            url=data.get("url", "")
        )
        
        return jsonify({
            "success": True,
            "document_id": doc_id,
            "message": "Document stored in legacy"
        }), 201
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/legacy/<legacy_id>/activate", methods=["POST"])
@require_auth
def activate_legacy(legacy_id):
    """
    Activate the legacy (when owner is deceased)
    
    POST /api/legacy/{legacy_id}/activate
    {
        "activation_date": 1715851200
    }
    """
    try:
        data = request.json or {}
        
        success = legacy_system.activate_legacy(
            legacy_id=legacy_id,
            activation_date=data.get("activation_date", 0)
        )
        
        return jsonify({
            "success": success,
            "message": "Legacy activated - heirs can now claim"
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/legacy/<legacy_id>/verify-heir", methods=["POST"])
@require_auth
def verify_heir(legacy_id):
    """
    Verify heir identity using biometric
    
    POST /api/legacy/{legacy_id}/verify-heir
    {
        "heir_id": "heir_001",
        "biometric_data": "<base64_test_data>",
        "genetic_marker": "optional_genetic_code"
    }
    """
    try:
        data = request.json
        biometric_data = data["biometric_data"].encode() if isinstance(data["biometric_data"], str) else data["biometric_data"]
        
        verified = legacy_system.verify_heir_identity(
            legacy_id=legacy_id,
            heir_id=data["heir_id"],
            test_biometric=biometric_data,
            test_genetic=data.get("genetic_marker")
        )
        
        return jsonify({
            "success": True,
            "verified": verified,
            "message": "Heir verified" if verified else "Verification failed"
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/legacy/<legacy_id>/claim", methods=["POST"])
@require_auth
def claim_legacy(legacy_id):
    """
    Claim and distribute legacy to verified heir
    
    POST /api/legacy/{legacy_id}/claim
    {
        "heir_id": "heir_001"
    }
    """
    try:
        data = request.json
        
        distribution = legacy_system.claim_and_distribute(
            legacy_id=legacy_id,
            heir_id=data["heir_id"]
        )
        
        return jsonify({
            "success": True,
            "distribution": distribution,
            "message": "Legacy claimed and assets distributed"
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/legacy/<legacy_id>", methods=["GET"])
@require_auth
def get_legacy(legacy_id):
    """
    Get legacy details
    
    GET /api/legacy/{legacy_id}
    """
    try:
        legacy = legacy_system.get_legacy(legacy_id)
        
        if not legacy:
            return jsonify({"error": "Legacy not found"}), 404
        
        return jsonify({
            "success": True,
            "legacy": legacy
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/legacy/<legacy_id>/audit-trail", methods=["GET"])
@require_auth
def get_audit_trail(legacy_id):
    """
    Get immutable audit trail for legacy
    
    GET /api/legacy/{legacy_id}/audit-trail
    """
    try:
        audit_trail = legacy_system.get_legacy_audit_trail(legacy_id)
        
        if audit_trail is None:
            return jsonify({"error": "Legacy not found"}), 404
        
        return jsonify({
            "success": True,
            "audit_trail": audit_trail,
            "entry_count": len(audit_trail)
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/legacy/owner/<owner_address>", methods=["GET"])
@require_auth
def get_owner_legacies(owner_address):
    """
    Get all legacies for an owner
    
    GET /api/legacy/owner/{owner_address}
    """
    try:
        legacies = legacy_system.get_owner_legacies(owner_address)
        
        return jsonify({
            "success": True,
            "legacies": legacies,
            "count": len(legacies)
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/legacy/heir/<heir_id>", methods=["GET"])
@require_auth
def get_heir_legacies(heir_id):
    """
    Get all legacies where user is an heir
    
    GET /api/legacy/heir/{heir_id}
    """
    try:
        legacies = legacy_system.get_heir_legacies(heir_id)
        
        return jsonify({
            "success": True,
            "legacies": legacies,
            "count": len(legacies)
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/legacy/statistics", methods=["GET"])
@require_auth
def get_statistics():
    """
    Get system-wide statistics
    
    GET /api/legacy/statistics
    """
    try:
        stats = legacy_system.get_system_statistics()
        
        return jsonify({
            "success": True,
            "statistics": stats
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/legacy/contract-template", methods=["GET"])
@require_auth
def get_contract_template():
    """
    Get Solidity contract template for legacy NFT
    
    GET /api/legacy/contract-template
    """
    contract = '''
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract DigitalLegacyNFT {
    struct Legacy {
        string legacyId;
        address owner;
        uint256 createdTimestamp;
        uint256 activationTimestamp;
        string status;
        uint256 totalAssets;
    }
    
    mapping(string => Legacy) public legacies;
    mapping(address => string[]) public ownerLegacies;
    
    event LegacyCreated(string indexed legacyId, address indexed owner);
    event LegacyActivated(string indexed legacyId, uint256 timestamp);
    event AssetClaimed(string indexed legacyId, address indexed heir);
}
'''
    
    return jsonify({
        "success": True,
        "contract": contract,
        "language": "solidity",
        "version": "0.8.0"
    }), 200


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "digital_legacy_api",
        "version": "1.0",
        "legacies_active": legacy_system.total_legacies
    }), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)
