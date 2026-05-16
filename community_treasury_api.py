"""
Community Treasury DAO API
REST endpoints for democratic treasury governance
5% of block rewards voted by community
"""

import json
import hashlib
import time
import os
from flask import request, jsonify
from typing import Dict, List, Any, Optional
from datetime import datetime


class CommunityTreasuryDAO:
    """
    Manages community treasury (5% of block rewards)
    Democratic voting determines allocation
    Every person has equal voice
    """

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = data_dir
        self.proposals_file = os.path.join(data_dir, "treasury_proposals.json")
        self.distributions_file = os.path.join(data_dir, "treasury_distributions.json")
        self.treasury_file = os.path.join(data_dir, "treasury_balance.json")
        self._ensure_files_exist()

    def _ensure_files_exist(self):
        """Create data files if they don't exist"""
        for path in [self.proposals_file, self.distributions_file, self.treasury_file]:
            if not os.path.exists(path):
                if path == self.treasury_file:
                    with open(path, 'w') as f:
                        json.dump({
                            "total_accumulated": 0,
                            "current_balance": 0,
                            "total_distributed": 0,
                            "last_update": int(time.time())
                        }, f)
                else:
                    with open(path, 'w') as f:
                        json.dump([], f)

    def _load_json(self, path: str) -> Any:
        """Load JSON file"""
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except:
            return [] if path != self.treasury_file else {}

    def _save_json(self, path: str, data: Any):
        """Save JSON file"""
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    def create_proposal(
        self,
        title: str,
        description: str,
        requested_amount: float,
        beneficiary_type: str,
        beneficiary_name: str,
        beneficiary_address: str,
        proposer_address: str
    ) -> Dict[str, Any]:
        """Create new spending proposal"""

        if requested_amount <= 0:
            raise ValueError("Amount must be positive")

        if beneficiary_type not in ["medical", "education", "climate", "poverty", "research"]:
            raise ValueError("Invalid beneficiary type")

        proposal_id = hashlib.sha256(
            f"{proposer_address}{int(time.time())}".encode()
        ).hexdigest()[:16]

        proposal = {
            "proposal_id": proposal_id,
            "title": title,
            "description": description,
            "proposer_address": proposer_address,
            "requested_amount": requested_amount,
            "beneficiary_type": beneficiary_type,
            "beneficiary_name": beneficiary_name,
            "beneficiary_address": beneficiary_address,
            "created_timestamp": int(time.time()),
            "created_date": datetime.now().isoformat(),
            "voting_deadline": int(time.time()) + (30 * 24 * 3600),  # 30 days
            "votes_for": 0,
            "votes_against": 0,
            "total_voting_power": 0,
            "approval_percentage": 0,
            "status": "voting",  # voting, approved, rejected, executed
            "executed_timestamp": None,
            "executed_date": None,
            "voters": {}  # Track who voted and how much
        }

        proposals = self._load_json(self.proposals_file)
        proposals.append(proposal)
        self._save_json(self.proposals_file, proposals)

        return proposal

    def vote_on_proposal(
        self,
        proposal_id: str,
        voter_address: str,
        thr_amount: float,
        vote: str  # "for" or "against"
    ) -> Dict[str, Any]:
        """
        Vote on proposal using quadratic voting.
        Cost = (voting_power)^2 THR
        Prevents whale control
        """

        if vote not in ["for", "against"]:
            raise ValueError("Vote must be 'for' or 'against'")

        proposals = self._load_json(self.proposals_file)
        proposal = next((p for p in proposals if p["proposal_id"] == proposal_id), None)

        if not proposal:
            raise ValueError("Proposal not found")

        if proposal["status"] != "voting":
            raise ValueError("Proposal not in voting phase")

        if int(time.time()) > proposal["voting_deadline"]:
            raise ValueError("Voting period has ended")

        if voter_address in proposal["voters"]:
            raise ValueError("Already voted on this proposal")

        if thr_amount <= 0:
            raise ValueError("Invalid voting amount")

        # Quadratic voting: voting power = sqrt(cost)
        # Cost to vote with power 10 = 100 THR
        voting_power = thr_amount ** 0.5

        if vote == "for":
            proposal["votes_for"] += voting_power
        else:
            proposal["votes_against"] += voting_power

        proposal["total_voting_power"] += voting_power
        proposal["voters"][voter_address] = {
            "vote": vote,
            "power": voting_power,
            "cost": thr_amount,
            "timestamp": int(time.time())
        }

        # Calculate approval percentage
        if proposal["total_voting_power"] > 0:
            proposal["approval_percentage"] = (proposal["votes_for"] / proposal["total_voting_power"]) * 100

        # Update in list
        for i, p in enumerate(proposals):
            if p["proposal_id"] == proposal_id:
                proposals[i] = proposal
                break

        self._save_json(self.proposals_file, proposals)

        return {
            "voted": True,
            "proposal_id": proposal_id,
            "voter": voter_address,
            "vote": vote,
            "voting_power": voting_power,
            "cost_thr": thr_amount,
            "current_approval": proposal["approval_percentage"]
        }

    def finalize_proposal(self, proposal_id: str) -> Dict[str, Any]:
        """Finalize voting and determine outcome"""

        proposals = self._load_json(self.proposals_file)
        proposal = next((p for p in proposals if p["proposal_id"] == proposal_id), None)

        if not proposal:
            raise ValueError("Proposal not found")

        if proposal["status"] != "voting":
            raise ValueError("Proposal already finalized")

        if int(time.time()) <= proposal["voting_deadline"]:
            raise ValueError("Voting period not ended")

        # Check approval threshold (51%)
        approved = proposal["approval_percentage"] >= 51

        proposal["status"] = "approved" if approved else "rejected"
        proposal["executed_timestamp"] = int(time.time())
        proposal["executed_date"] = datetime.now().isoformat()

        # Update in list
        for i, p in enumerate(proposals):
            if p["proposal_id"] == proposal_id:
                proposals[i] = proposal
                break

        self._save_json(self.proposals_file, proposals)

        return {
            "proposal_id": proposal_id,
            "approved": approved,
            "approval_percentage": proposal["approval_percentage"],
            "total_votes": proposal["votes_for"] + proposal["votes_against"],
            "status": proposal["status"]
        }

    def distribute_funds(
        self,
        proposal_id: str,
        beneficiary_address: str
    ) -> Dict[str, Any]:
        """Distribute approved funds to beneficiary"""

        proposals = self._load_json(self.proposals_file)
        proposal = next((p for p in proposals if p["proposal_id"] == proposal_id), None)

        if not proposal:
            raise ValueError("Proposal not found")

        if proposal["status"] != "approved":
            raise ValueError("Proposal not approved")

        # Check treasury balance
        treasury = self._load_json(self.treasury_file)
        if proposal["requested_amount"] > treasury["current_balance"]:
            raise ValueError("Insufficient treasury balance")

        # Create distribution record
        distribution_id = hashlib.sha256(
            f"{proposal_id}{int(time.time())}".encode()
        ).hexdigest()[:16]

        distribution = {
            "distribution_id": distribution_id,
            "proposal_id": proposal_id,
            "beneficiary_address": beneficiary_address,
            "amount": proposal["requested_amount"],
            "distributed_timestamp": int(time.time()),
            "distributed_date": datetime.now().isoformat(),
            "status": "executed"
        }

        distributions = self._load_json(self.distributions_file)
        distributions.append(distribution)
        self._save_json(self.distributions_file, distributions)

        # Update treasury
        treasury["current_balance"] -= proposal["requested_amount"]
        treasury["total_distributed"] += proposal["requested_amount"]
        treasury["last_update"] = int(time.time())
        self._save_json(self.treasury_file, treasury)

        # Mark proposal as executed
        proposal["status"] = "executed"
        for i, p in enumerate(proposals):
            if p["proposal_id"] == proposal_id:
                proposals[i] = proposal
                break
        self._save_json(self.proposals_file, proposals)

        return distribution

    def deposit_from_blocks(
        self,
        amount: float,
        block_height: int
    ) -> Dict[str, Any]:
        """Add funds from block rewards (5% allocation)"""

        treasury = self._load_json(self.treasury_file)
        treasury["current_balance"] += amount
        treasury["total_accumulated"] += amount
        treasury["last_update"] = int(time.time())
        self._save_json(self.treasury_file, treasury)

        return {
            "deposited": amount,
            "block_height": block_height,
            "new_balance": treasury["current_balance"],
            "total_accumulated": treasury["total_accumulated"]
        }

    def get_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """Get proposal details"""
        proposals = self._load_json(self.proposals_file)
        return next((p for p in proposals if p["proposal_id"] == proposal_id), None)

    def get_all_proposals(self) -> List[Dict[str, Any]]:
        """Get all proposals"""
        return self._load_json(self.proposals_file)

    def get_active_proposals(self) -> List[Dict[str, Any]]:
        """Get proposals still in voting"""
        proposals = self._load_json(self.proposals_file)
        return [p for p in proposals if p["status"] == "voting"]

    def get_approved_proposals(self) -> List[Dict[str, Any]]:
        """Get approved proposals"""
        proposals = self._load_json(self.proposals_file)
        return [p for p in proposals if p["status"] == "approved"]

    def get_treasury_balance(self) -> Dict[str, Any]:
        """Get current treasury status"""
        return self._load_json(self.treasury_file)

    def get_proposal_voters(self, proposal_id: str) -> Dict[str, Any]:
        """Get all voters for a proposal"""
        proposal = self.get_proposal(proposal_id)
        if not proposal:
            raise ValueError("Proposal not found")
        return proposal["voters"]


def register_treasury_routes(app, data_dir: str):
    """Register community treasury routes to Flask app"""

    treasury = CommunityTreasuryDAO(data_dir)

    # ─── CREATE PROPOSAL ────────────────────────────────────────

    @app.route("/api/treasury/create-proposal", methods=["POST"])
    def api_create_proposal():
        """Create new spending proposal"""
        try:
            data = request.get_json() or {}

            title = data.get("title", "").strip()
            description = data.get("description", "").strip()
            requested_amount = float(data.get("requested_amount", 0))
            beneficiary_type = data.get("beneficiary_type", "").strip()
            beneficiary_name = data.get("beneficiary_name", "").strip()
            beneficiary_address = data.get("beneficiary_address", "").strip()
            proposer_address = data.get("proposer_address", "").strip()

            if not all([title, description, requested_amount > 0, beneficiary_type, beneficiary_address]):
                return jsonify(error="Missing required fields"), 400

            proposal = treasury.create_proposal(
                title=title,
                description=description,
                requested_amount=requested_amount,
                beneficiary_type=beneficiary_type,
                beneficiary_name=beneficiary_name,
                beneficiary_address=beneficiary_address,
                proposer_address=proposer_address
            )

            return jsonify(
                status="success",
                proposal_id=proposal["proposal_id"],
                title=proposal["title"],
                voting_deadline=proposal["voting_deadline"],
                requested_amount=requested_amount
            ), 201

        except ValueError as e:
            return jsonify(error=str(e)), 400
        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── VOTE ON PROPOSAL ───────────────────────────────────────

    @app.route("/api/treasury/vote/<proposal_id>", methods=["POST"])
    def api_vote(proposal_id):
        """Vote on proposal (quadratic voting)"""
        try:
            data = request.get_json() or {}

            voter_address = data.get("voter_address", "").strip()
            thr_amount = float(data.get("thr_amount", 0))
            vote = data.get("vote", "").lower().strip()

            if not all([voter_address, thr_amount > 0, vote in ["for", "against"]]):
                return jsonify(error="Invalid voting parameters"), 400

            result = treasury.vote_on_proposal(
                proposal_id=proposal_id,
                voter_address=voter_address,
                thr_amount=thr_amount,
                vote=vote
            )

            return jsonify(
                status="success",
                voted=True,
                proposal_id=proposal_id,
                vote=vote,
                voting_power=result["voting_power"],
                cost_thr=result["cost_thr"],
                current_approval=result["current_approval"]
            ), 200

        except ValueError as e:
            return jsonify(error=str(e)), 400
        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── FINALIZE PROPOSAL ──────────────────────────────────────

    @app.route("/api/treasury/finalize/<proposal_id>", methods=["POST"])
    def api_finalize(proposal_id):
        """Finalize voting"""
        try:
            result = treasury.finalize_proposal(proposal_id)

            return jsonify(
                status="success",
                proposal_id=proposal_id,
                approved=result["approved"],
                approval_percentage=result["approval_percentage"],
                total_votes=result["total_votes"],
                new_status=result["status"]
            ), 200

        except ValueError as e:
            return jsonify(error=str(e)), 400
        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── DISTRIBUTE FUNDS ───────────────────────────────────────

    @app.route("/api/treasury/distribute/<proposal_id>", methods=["POST"])
    def api_distribute(proposal_id):
        """Distribute approved funds"""
        try:
            data = request.get_json() or {}
            beneficiary_address = data.get("beneficiary_address", "").strip()

            if not beneficiary_address:
                return jsonify(error="Missing beneficiary address"), 400

            distribution = treasury.distribute_funds(
                proposal_id=proposal_id,
                beneficiary_address=beneficiary_address
            )

            return jsonify(
                status="success",
                distribution_id=distribution["distribution_id"],
                amount=distribution["amount"],
                beneficiary=beneficiary_address
            ), 200

        except ValueError as e:
            return jsonify(error=str(e)), 400
        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── GET PROPOSAL ───────────────────────────────────────────

    @app.route("/api/treasury/proposal/<proposal_id>", methods=["GET"])
    def api_get_proposal(proposal_id):
        """Get proposal details"""
        try:
            proposal = treasury.get_proposal(proposal_id)
            if not proposal:
                return jsonify(error="Proposal not found"), 404

            return jsonify(
                status="success",
                proposal=proposal
            ), 200

        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── GET ALL PROPOSALS ──────────────────────────────────────

    @app.route("/api/treasury/proposals", methods=["GET"])
    def api_get_proposals():
        """Get all proposals"""
        try:
            status_filter = request.args.get("status")
            proposals = treasury.get_all_proposals()

            if status_filter:
                proposals = [p for p in proposals if p["status"] == status_filter]

            return jsonify(
                status="success",
                total_count=len(proposals),
                proposals=proposals
            ), 200

        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── GET ACTIVE PROPOSALS ───────────────────────────────────

    @app.route("/api/treasury/proposals/active", methods=["GET"])
    def api_get_active_proposals():
        """Get proposals in voting"""
        try:
            proposals = treasury.get_active_proposals()

            return jsonify(
                status="success",
                active_count=len(proposals),
                proposals=proposals
            ), 200

        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── GET TREASURY BALANCE ───────────────────────────────────

    @app.route("/api/treasury/balance", methods=["GET"])
    def api_get_balance():
        """Get treasury balance"""
        try:
            balance = treasury.get_treasury_balance()

            return jsonify(
                status="success",
                current_balance=balance["current_balance"],
                total_accumulated=balance["total_accumulated"],
                total_distributed=balance["total_distributed"]
            ), 200

        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    # ─── DEPOSIT FROM BLOCKS ────────────────────────────────────

    @app.route("/api/treasury/deposit", methods=["POST"])
    def api_deposit():
        """Add funds from block rewards"""
        try:
            data = request.get_json() or {}
            amount = float(data.get("amount", 0))
            block_height = int(data.get("block_height", 0))

            if amount <= 0:
                return jsonify(error="Invalid amount"), 400

            result = treasury.deposit_from_blocks(amount, block_height)

            return jsonify(
                status="success",
                deposited=result["deposited"],
                block_height=result["block_height"],
                new_balance=result["new_balance"]
            ), 200

        except Exception as e:
            return jsonify(error=f"Error: {str(e)}"), 500

    return {
        "/api/treasury/create-proposal": "POST",
        "/api/treasury/vote/<proposal_id>": "POST",
        "/api/treasury/finalize/<proposal_id>": "POST",
        "/api/treasury/distribute/<proposal_id>": "POST",
        "/api/treasury/proposal/<proposal_id>": "GET",
        "/api/treasury/proposals": "GET",
        "/api/treasury/proposals/active": "GET",
        "/api/treasury/balance": "GET",
        "/api/treasury/deposit": "POST"
    }
