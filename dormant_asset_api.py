"""
Dormant Asset NFT System - REST API Endpoints
"""

import json
from flask import request, jsonify
from typing import Dict, Any
from dormant_asset_system import DormantAssetSystem, DORMANT_ASSET_NFT_CONTRACT


def register_dormant_asset_routes(app, data_dir: str):
    """Register dormant asset routes to Flask app."""

    dormant_system = DormantAssetSystem(data_dir)

    # ─── CHECK DORMANCY STATUS ────────────────────────────────────────

    @app.route("/api/dormant/check/<legacy_id>", methods=["POST"])
    def api_check_dormancy(legacy_id):
        """
        Check if legacy qualifies as dormant.

        Request body:
        {
            "legacy_doc": { /* full legacy document */ },
            "current_timestamp": 1715856000
        }

        Response:
        {
            "is_dormant": true,
            "reason": "asset_unused_30_years",
            "years_inactive": 35.5,
            "eligible_for_redistribution": true
        }
        """
        try:
            data = request.get_json() or {}
            legacy_doc = data.get("legacy_doc", {})
            current_timestamp = data.get("current_timestamp", int(__import__("time").time()))

            result = dormant_system.check_dormancy(
                legacy_id,
                legacy_doc,
                current_timestamp
            )

            return jsonify(
                status="success",
                dormancy_check=result
            ), 200

        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── CREATE DORMANT NFT ────────────────────────────────────────

    @app.route("/api/dormant/create-nft", methods=["POST"])
    def api_create_dormant_nft():
        """
        Create NFT for dormant asset.

        Request body:
        {
            "legacy_id": "abc123...",
            "asset_type": "BTC|ETH|property|token",
            "asset_identifier": "address or ID",
            "asset_value": 50000.5,
            "historical_price_usd": 70000,
            "locked_timestamp": 1715856000,
            "death_certificate_hash": "sha256..."
        }

        Response:
        {
            "status": "success",
            "nft_id": "nft123...",
            "nft_contract": "DORMANT_NFT_nft123",
            "current_value_thr": 50000.5,
            "historical_price_usd": 70000
        }
        """
        try:
            data = request.get_json() or {}

            legacy_id = data.get("legacy_id", "").strip()
            asset_type = data.get("asset_type", "").strip()
            asset_identifier = data.get("asset_identifier", "").strip()
            asset_value = float(data.get("asset_value", 0))
            historical_price_usd = float(data.get("historical_price_usd", 0))
            locked_timestamp = int(data.get("locked_timestamp", 0))
            death_certificate_hash = data.get("death_certificate_hash", "").strip()

            if not all([legacy_id, asset_type, asset_value, historical_price_usd]):
                return jsonify(error="Missing required fields"), 400

            nft = dormant_system.create_dormant_nft(
                legacy_id=legacy_id,
                asset_type=asset_type,
                asset_identifier=asset_identifier,
                asset_value=asset_value,
                historical_price_usd=historical_price_usd,
                locked_timestamp=locked_timestamp,
                death_certificate_hash=death_certificate_hash
            )

            return jsonify(
                status="success",
                nft_id=nft["nft_id"],
                nft_contract=nft["nft_contract"],
                current_value_thr=float(nft["current_value_thr"]),
                historical_price_usd=nft["historical_price_usd"]
            ), 201

        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── REGISTER FOUNDATION ──────────────────────────────────────

    @app.route("/api/dormant/register-foundation", methods=["POST"])
    def api_register_foundation():
        """
        Register charitable foundation for asset redistribution.

        Request body:
        {
            "foundation_name": "Medical Research Foundation",
            "foundation_address": "THR...",
            "mission": "Fund cancer research and treatment",
            "focus_areas": ["medical", "research"],
            "legal_entity_hash": "sha256(legal_docs)"
        }

        Response:
        {
            "status": "success",
            "foundation_id": "foundation123...",
            "status": "pending_verification"
        }
        """
        try:
            data = request.get_json() or {}

            foundation_name = data.get("foundation_name", "").strip()
            foundation_address = data.get("foundation_address", "").strip()
            mission = data.get("mission", "").strip()
            focus_areas = data.get("focus_areas", [])
            legal_entity_hash = data.get("legal_entity_hash", "").strip()

            if not all([foundation_name, foundation_address, mission, legal_entity_hash]):
                return jsonify(error="Missing required fields"), 400

            foundation = dormant_system.register_foundation(
                foundation_name=foundation_name,
                foundation_address=foundation_address,
                mission=mission,
                focus_areas=focus_areas,
                legal_entity_hash=legal_entity_hash
            )

            return jsonify(
                status="success",
                foundation_id=foundation["foundation_id"],
                foundation_name=foundation["foundation_name"],
                verification_status=foundation["status"]
            ), 201

        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── CREATE DAO PROPOSAL ────────────────────────────────────────

    @app.route("/api/dormant/propose-redistribution", methods=["POST"])
    def api_propose_redistribution():
        """
        Create DAO proposal to redistribute dormant asset.

        Request body:
        {
            "foundation_id": "foundation123...",
            "dormant_nft_id": "nft123...",
            "proposer_address": "THR...",
            "justification": "Medical research will cure cancer",
            "duration_years": 5
        }

        Response:
        {
            "status": "success",
            "proposal_id": "proposal123...",
            "voting_deadline": 1746345600
        }
        """
        try:
            data = request.get_json() or {}

            foundation_id = data.get("foundation_id", "").strip()
            dormant_nft_id = data.get("dormant_nft_id", "").strip()
            proposer_address = data.get("proposer_address", "").strip()
            justification = data.get("justification", "").strip()
            duration_years = int(data.get("duration_years", 5))

            if not all([foundation_id, dormant_nft_id, proposer_address, justification]):
                return jsonify(error="Missing required fields"), 400

            proposal = dormant_system.propose_redistribution(
                foundation_id=foundation_id,
                dormant_nft_id=dormant_nft_id,
                proposer_address=proposer_address,
                justification=justification,
                duration_years=duration_years
            )

            return jsonify(
                status="success",
                proposal_id=proposal["proposal_id"],
                voting_deadline=proposal["voting_deadline"],
                foundation_id=foundation_id
            ), 201

        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── VOTE ON PROPOSAL ──────────────────────────────────────────

    @app.route("/api/dormant/vote/<proposal_id>", methods=["POST"])
    def api_vote_on_proposal(proposal_id):
        """
        Vote on dormant asset redistribution proposal.

        Voting Method: Quadratic Voting
        - Cost = (vote_power)^2 THR
        - Example: voting with power 10 costs 100 THR

        Request body:
        {
            "voter_address": "THR...",
            "thr_amount": 100.5,
            "vote": "for|against"
        }

        Response:
        {
            "status": "success",
            "voted": true,
            "vote_power": 10.024,
            "current_approval": 62.5
        }
        """
        try:
            data = request.get_json() or {}

            voter_address = data.get("voter_address", "").strip()
            thr_amount = float(data.get("thr_amount", 0))
            vote = data.get("vote", "").lower().strip()

            if not all([voter_address, thr_amount > 0, vote in ["for", "against"]]):
                return jsonify(error="Invalid voting parameters"), 400

            result = dormant_system.vote_on_proposal(
                proposal_id=proposal_id,
                voter_address=voter_address,
                thr_amount=thr_amount,
                vote=vote
            )

            return jsonify(
                status="success",
                voted=True,
                voter_address=voter_address,
                vote=vote,
                vote_power=result["vote_power"],
                thr_cost=result["thr_cost"],
                current_approval_percentage=result["current_approval"]
            ), 200

        except ValueError as e:
            return jsonify(error=str(e)), 400
        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── FINALIZE PROPOSAL ────────────────────────────────────────

    @app.route("/api/dormant/finalize-proposal/<proposal_id>", methods=["POST"])
    def api_finalize_proposal(proposal_id):
        """
        Finalize voting and execute redistribution if approved (51%+).

        Response:
        {
            "status": "success",
            "approved": true,
            "approval_percentage": 65.5,
            "total_votes": 45000
        }
        """
        try:
            result = dormant_system.finalize_proposal(proposal_id)

            return jsonify(
                status="success",
                approved=result["approved"],
                approval_percentage=result["approval_percentage"],
                total_votes=result["total_votes"],
                proposal_status=result["status"]
            ), 200

        except ValueError as e:
            return jsonify(error=str(e)), 400
        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── GET DORMANT ASSETS ────────────────────────────────────────

    @app.route("/api/dormant/assets", methods=["GET"])
    def api_get_dormant_assets():
        """Get all dormant NFTs."""
        try:
            status = request.args.get("status")  # dormant, redistributed, claimed
            assets = dormant_system.get_dormant_assets(status)

            return jsonify(
                status="success",
                total_count=len(assets),
                assets=assets
            ), 200

        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── GET ACTIVE PROPOSALS ──────────────────────────────────────

    @app.route("/api/dormant/proposals", methods=["GET"])
    def api_get_active_proposals():
        """Get all active DAO voting proposals."""
        try:
            proposals = dormant_system.get_active_proposals()

            return jsonify(
                status="success",
                active_proposals=len(proposals),
                proposals=proposals
            ), 200

        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── GET FOUNDATION ────────────────────────────────────────────

    @app.route("/api/dormant/foundation/<foundation_id>", methods=["GET"])
    def api_get_foundation(foundation_id):
        """Get foundation details."""
        try:
            foundation = dormant_system.get_foundation(foundation_id)

            if not foundation:
                return jsonify(error="Foundation not found"), 404

            return jsonify(
                status="success",
                foundation=foundation
            ), 200

        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── UPDATE RESERVE ────────────────────────────────────────────

    @app.route("/api/dormant/update-reserve", methods=["POST"])
    def api_update_dormant_reserve():
        """
        Update dormant asset reserve from block rewards.

        Called by mining system every block.

        Request body:
        {
            "block_height": 500000,
            "new_blocks": 10,
            "thr_per_block": 0.25
        }

        Response:
        {
            "status": "success",
            "reserve_amount_added": 12.5,
            "total_accumulated": 50000
        }
        """
        try:
            data = request.get_json() or {}

            block_height = int(data.get("block_height", 0))
            new_blocks = int(data.get("new_blocks", 1))
            thr_per_block = float(data.get("thr_per_block", 0))

            result = dormant_system.update_dormant_reserve(
                block_height=block_height,
                new_blocks=new_blocks,
                thr_per_block=thr_per_block
            )

            return jsonify(
                status="success",
                block_height=block_height,
                reserve_added=result["reserve_amount_added"],
                total_accumulated=result["total_accumulated"]
            ), 200

        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── USE RESERVE TO STABILIZE ─────────────────────────────────

    @app.route("/api/dormant/stabilize-nft", methods=["POST"])
    def api_stabilize_nft():
        """
        Use dormant reserve to stabilize dormant asset price.

        Request body:
        {
            "dormant_nft_id": "nft123...",
            "target_price_thr": 50000
        }

        Response:
        {
            "status": "success",
            "nft_id": "nft123...",
            "price_stabilized": 50000,
            "reserve_remaining": 100000
        }
        """
        try:
            data = request.get_json() or {}

            dormant_nft_id = data.get("dormant_nft_id", "").strip()
            target_price_thr = float(data.get("target_price_thr", 0))

            if not dormant_nft_id or target_price_thr <= 0:
                return jsonify(error="Invalid parameters"), 400

            result = dormant_system.use_reserve_to_stabilize(
                dormant_nft_id=dormant_nft_id,
                target_price_thr=target_price_thr
            )

            return jsonify(
                status="success",
                nft_id=result["nft_id"],
                price_stabilized=result["price_stabilized"],
                reserve_remaining=result["reserve_remaining"]
            ), 200

        except ValueError as e:
            return jsonify(error=str(e)), 400
        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── GET CONTRACT TEMPLATE ────────────────────────────────────

    @app.route("/api/dormant/contract-template", methods=["GET"])
    def api_get_contract_template():
        """Get Solidity smart contract template for dormant asset NFTs."""
        return jsonify(
            status="success",
            contract_name="DormantAssetNFT",
            contract_code=DORMANT_ASSET_NFT_CONTRACT,
            description="Smart contract for creating and voting on dormant asset redistribution"
        ), 200

    return {
        "/api/dormant/check/<legacy_id>": "POST",
        "/api/dormant/create-nft": "POST",
        "/api/dormant/register-foundation": "POST",
        "/api/dormant/propose-redistribution": "POST",
        "/api/dormant/vote/<proposal_id>": "POST",
        "/api/dormant/finalize-proposal/<proposal_id>": "POST",
        "/api/dormant/assets": "GET",
        "/api/dormant/proposals": "GET",
        "/api/dormant/foundation/<foundation_id>": "GET",
        "/api/dormant/update-reserve": "POST",
        "/api/dormant/stabilize-nft": "POST",
        "/api/dormant/contract-template": "GET"
    }
