"""
Digital Legacy API Endpoints
REST API for Thronos Digital Legacy System
"""

import json
import hashlib
from flask import request, jsonify
from typing import Dict, Any
from digital_legacy_system import DigitalLegacySystem, LEGACY_NFT_CONTRACT_TEMPLATE


def register_legacy_routes(app, data_dir: str):
    """Register digital legacy routes to Flask app."""

    legacy_system = DigitalLegacySystem(data_dir)

    # ─── CREATE LEGACY DOCUMENT ─────────────────────────────────────────

    @app.route("/api/legacy/create", methods=["POST"])
    def api_legacy_create():
        """
        Create a digital legacy document (NFT-based will).

        Request body:
        {
            "owner_address": "THR address",
            "owner_signature": "digital signature from owner",
            "assets": [
                {
                    "asset_type": "wallet|token|property",
                    "identifier": "wallet address or token id",
                    "value_thr": 1000.5,
                    "description": "Primary wallet"
                }
            ],
            "heirs": [
                {
                    "heir_name": "John Doe",
                    "share_percentage": 50
                }
            ],
            "metadata": {
                "created_by": "optional",
                "notes": "My digital will"
            }
        }

        Response:
        {
            "status": "success",
            "legacy_id": "abc123...",
            "nft_contract": "LEGACY_NFT_abc123",
            "nft_token_id": "abc123...",
            "total_asset_value_thr": 1000.5
        }
        """
        try:
            data = request.get_json() or {}

            owner_address = data.get("owner_address", "").strip()
            owner_signature = data.get("owner_signature", "").strip()
            assets = data.get("assets", [])
            heirs = data.get("heirs", [])
            metadata = data.get("metadata", {})

            if not owner_address or not owner_signature or not assets or not heirs:
                return jsonify(error="Missing required fields"), 400

            legacy_doc = legacy_system.create_legacy_document(
                owner_address=owner_address,
                owner_signature=owner_signature,
                assets=assets,
                heirs=heirs,
                metadata=metadata
            )

            return jsonify(
                status="success",
                legacy_id=legacy_doc["legacy_id"],
                nft_contract=legacy_doc["nft_contract"],
                nft_token_id=legacy_doc["nft_token_id"],
                total_asset_value_thr=legacy_doc["total_asset_value_thr"],
                heirs_count=len(heirs)
            ), 201

        except ValueError as e:
            return jsonify(error=str(e)), 400
        except Exception as e:
            return jsonify(error=f"Internal error: {str(e)}"), 500

    # ─── REGISTER HEIR ─────────────────────────────────────────────────

    @app.route("/api/legacy/<legacy_id>/register-heir", methods=["POST"])
    def api_register_heir(legacy_id):
        """
        Register an heir with biometric/genetic verification.

        Request body:
        {
            "heir_address": "THR address",
            "heir_name": "John Doe",
            "biometric_hash": "hash of fingerprint/face/iris scan",
            "genetic_marker": "optional hash of genetic data"
        }

        Response:
        {
            "status": "success",
            "heir_id": "heir123...",
            "verified": false
        }
        """
        try:
            data = request.get_json() or {}

            heir_address = data.get("heir_address", "").strip()
            heir_name = data.get("heir_name", "").strip()
            biometric_hash = data.get("biometric_hash", "").strip()
            genetic_marker = data.get("genetic_marker", "").strip() or None

            if not heir_address or not heir_name or not biometric_hash:
                return jsonify(error="Missing required fields"), 400

            # Verify legacy exists
            legacy = legacy_system.get_legacy_document(legacy_id)
            if not legacy:
                return jsonify(error="Legacy not found"), 404

            heir_record = legacy_system.register_heir(
                legacy_id=legacy_id,
                heir_address=heir_address,
                heir_name=heir_name,
                biometric_hash=biometric_hash,
                genetic_marker=genetic_marker
            )

            return jsonify(
                status="success",
                heir_id=heir_record["heir_id"],
                heir_name=heir_record["heir_name"],
                verified=heir_record["verified"]
            ), 201

        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── VERIFY HEIR ───────────────────────────────────────────────────

    @app.route("/api/legacy/verify-heir", methods=["POST"])
    def api_verify_heir():
        """
        Verify heir identity using biometric/genetic data.

        Request body:
        {
            "heir_id": "heir123...",
            "biometric_data": "raw biometric data for matching",
            "genetic_data": "optional genetic data"
        }

        Response:
        {
            "verified": true,
            "access_token": "token123...",
            "access_valid_until": 1234567890
        }
        """
        try:
            data = request.get_json() or {}

            heir_id = data.get("heir_id", "").strip()
            biometric_data = data.get("biometric_data", "").strip()
            genetic_data = data.get("genetic_data", "").strip() or None

            if not heir_id or not biometric_data:
                return jsonify(error="Missing required fields"), 400

            result = legacy_system.verify_heir(
                heir_id=heir_id,
                biometric_data=biometric_data,
                genetic_data=genetic_data
            )

            if not result.get("verified"):
                return jsonify(
                    verified=False,
                    error=result.get("error", "Verification failed")
                ), 403

            return jsonify(
                verified=True,
                heir_id=result["heir_id"],
                heir_name=result["heir_name"],
                access_token=result["access_token"],
                access_valid_until=result["access_valid_until"]
            ), 200

        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── GENERATE RECOVERY QR ──────────────────────────────────────────

    @app.route("/api/legacy/recovery-qr", methods=["POST"])
    def api_generate_recovery_qr():
        """
        Generate QR code for heir recovery access.

        Request body:
        {
            "legacy_id": "abc123...",
            "heir_id": "heir123...",
            "access_token": "token123..."
        }

        Response:
        {
            "recovery_id": "rec123...",
            "qr_code_base64": "data:image/png;base64,...",
            "valid_until": 1234567890
        }
        """
        try:
            data = request.get_json() or {}

            legacy_id = data.get("legacy_id", "").strip()
            heir_id = data.get("heir_id", "").strip()
            access_token = data.get("access_token", "").strip()

            if not legacy_id or not heir_id or not access_token:
                return jsonify(error="Missing required fields"), 400

            recovery_record = legacy_system.generate_recovery_qr(
                legacy_id=legacy_id,
                heir_id=heir_id,
                access_token=access_token
            )

            return jsonify(
                status="success",
                recovery_id=recovery_record["recovery_id"],
                qr_code_base64=f"data:image/png;base64,{recovery_record['qr_code_base64']}",
                valid_until=recovery_record["valid_until"]
            ), 200

        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── GET LEGACY DOCUMENT ───────────────────────────────────────────

    @app.route("/api/legacy/<legacy_id>", methods=["GET"])
    def api_get_legacy(legacy_id):
        """Retrieve legacy document by ID."""
        try:
            legacy = legacy_system.get_legacy_document(legacy_id)
            if not legacy:
                return jsonify(error="Legacy not found"), 404

            return jsonify(
                status="success",
                legacy=legacy
            ), 200

        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── GET USER'S LEGACIES (AS OWNER) ────────────────────────────────

    @app.route("/api/legacy/owner/<owner_address>", methods=["GET"])
    def api_get_owner_legacies(owner_address):
        """Get all legacy documents for an owner."""
        try:
            legacies = legacy_system.get_legacy_by_owner(owner_address)

            return jsonify(
                status="success",
                owner_address=owner_address,
                legacies_count=len(legacies),
                legacies=legacies
            ), 200

        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── GET USER'S LEGACIES (AS HEIR) ────────────────────────────────

    @app.route("/api/legacy/heir/<heir_address>", methods=["GET"])
    def api_get_heir_legacies(heir_address):
        """Get all legacy documents where someone is an heir."""
        try:
            legacies = legacy_system.get_heir_legacies(heir_address)

            return jsonify(
                status="success",
                heir_address=heir_address,
                legacies_count=len(legacies),
                legacies=legacies
            ), 200

        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── GET AUDIT TRAIL ───────────────────────────────────────────────

    @app.route("/api/legacy/<legacy_id>/audit-trail", methods=["GET"])
    def api_get_audit_trail(legacy_id):
        """Get complete immutable audit trail for a legacy."""
        try:
            trail = legacy_system.get_audit_trail(legacy_id)

            return jsonify(
                status="success",
                legacy_id=legacy_id,
                audit_entries=len(trail),
                trail=trail
            ), 200

        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── DISTRIBUTE LEGACY ─────────────────────────────────────────────

    @app.route("/api/legacy/<legacy_id>/distribute", methods=["POST"])
    def api_distribute_legacy(legacy_id):
        """
        Execute legacy distribution to verified heir.

        Request body:
        {
            "heir_id": "heir123...",
            "access_token": "token123..."
        }

        Response:
        {
            "distribution_id": "dist123...",
            "heir_name": "John Doe",
            "total_value_thr": 1000.5,
            "nft_transfer_receipt": "LEGACY_TRANSFER_..."
        }
        """
        try:
            data = request.get_json() or {}

            heir_id = data.get("heir_id", "").strip()
            access_token = data.get("access_token", "").strip()

            if not heir_id or not access_token:
                return jsonify(error="Missing required fields"), 400

            distribution = legacy_system.distribute_to_heir(
                legacy_id=legacy_id,
                heir_id=heir_id,
                access_token=access_token
            )

            return jsonify(
                status="success",
                distribution_id=distribution["distribution_id"],
                heir_name=distribution["heir_name"],
                total_value_thr=distribution["total_value_thr"],
                nft_transfer_receipt=distribution["nft_transfer_receipt"]
            ), 200

        except ValueError as e:
            return jsonify(error=str(e)), 400
        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── DEPLOY LEGACY NFT CONTRACT ────────────────────────────────────

    @app.route("/api/legacy/contract-template", methods=["GET"])
    def api_get_legacy_contract():
        """Get Solidity contract template for Digital Legacy NFT."""
        return jsonify(
            status="success",
            contract_name="DigitalLegacyNFT",
            contract_code=LEGACY_NFT_CONTRACT_TEMPLATE,
            description="Smart contract for managing digital legacies and heir verification"
        ), 200

    return {
        "/api/legacy/create": "POST",
        "/api/legacy/<legacy_id>/register-heir": "POST",
        "/api/legacy/verify-heir": "POST",
        "/api/legacy/recovery-qr": "POST",
        "/api/legacy/<legacy_id>": "GET",
        "/api/legacy/owner/<owner_address>": "GET",
        "/api/legacy/heir/<heir_address>": "GET",
        "/api/legacy/<legacy_id>/audit-trail": "GET",
        "/api/legacy/<legacy_id>/distribute": "POST",
        "/api/legacy/contract-template": "GET"
    }
