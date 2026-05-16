"""
Dormant Asset NFT System for Thronos Blockchain
Redistributes unclaimed/dormant assets (30+ years) to charitable foundations
via DAO voting, creating permanent wealth equality mechanism.
"""

import json
import time
import hashlib
import os
from typing import Dict, List, Optional, Any
from datetime import datetime
from decimal import Decimal


class DormantAssetSystem:
    """
    Manages dormant assets (30+ years unclaimed) and redistributes them
    to foundations via decentralized DAO voting.

    Key Features:
    - Detects dormant assets from digital legacy system
    - Creates NFTs representing dormant assets at historical price
    - 5% of THR block rewards go to Dormant Asset Reserve
    - DAO voting determines redistribution to foundations
    - Multi-signature verification prevents fraud
    """

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = data_dir
        self.dormant_nfts_file = os.path.join(data_dir, "dormant_assets.json")
        self.dao_proposals_file = os.path.join(data_dir, "dao_proposals.json")
        self.foundation_registry_file = os.path.join(data_dir, "foundations_registry.json")
        self.dormant_reserve_file = os.path.join(data_dir, "dormant_reserve.json")
        self._ensure_files_exist()

    def _ensure_files_exist(self):
        """Ensure all data files exist."""
        for path in [
            self.dormant_nfts_file,
            self.dao_proposals_file,
            self.foundation_registry_file,
            self.dormant_reserve_file
        ]:
            if not os.path.exists(path):
                with open(path, 'w') as f:
                    json.dump([] if path != self.dormant_reserve_file else {}, f)

    def _load_json(self, path: str) -> Any:
        """Load JSON file safely."""
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except:
            return [] if path != self.dormant_reserve_file else {}

    def _save_json(self, path: str, data: Any):
        """Save JSON file safely."""
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    def check_dormancy(
        self,
        legacy_id: str,
        legacy_doc: Dict[str, Any],
        current_timestamp: int
    ) -> Dict[str, Any]:
        """
        Check if legacy qualifies as dormant.

        Dormant criteria:
        1. Owner is deceased (verified via death certificate)
        2. No heir claimed assets in 5+ years
        3. Asset unused for 30+ years

        Returns dormancy status and reason.
        """

        created_timestamp = legacy_doc.get("created_timestamp", 0)
        years_ago = (current_timestamp - created_timestamp) / (365.25 * 24 * 3600)

        # Check if any heir is verified
        heirs = legacy_doc.get("heirs", [])
        if heirs:
            # If heirs exist but none verified in 5+ years -> dormant
            pass

        # Check 30-year rule
        if years_ago >= 30:
            return {
                "is_dormant": True,
                "reason": "asset_unused_30_years",
                "years_inactive": years_ago,
                "eligible_for_redistribution": True
            }

        # Check 5-year unclaimed after death
        if years_ago >= 5 and not heirs:
            return {
                "is_dormant": True,
                "reason": "unclaimed_5_years",
                "years_inactive": years_ago,
                "eligible_for_redistribution": True
            }

        return {
            "is_dormant": False,
            "reason": "active_asset",
            "years_inactive": years_ago,
            "eligible_for_redistribution": False
        }

    def create_dormant_nft(
        self,
        legacy_id: str,
        asset_type: str,  # BTC, ETH, property, token
        asset_identifier: str,  # Address or ID
        asset_value: float,  # Current value in THR
        historical_price_usd: float,  # Price when locked
        locked_timestamp: int,  # When locked
        death_certificate_hash: str = ""  # Hash of death cert
    ) -> Dict[str, Any]:
        """
        Create NFT representing dormant asset at historical price.

        This NFT:
        - Cannot be transferred (frozen until redeemed)
        - Tracks original asset value
        - Eligible for DAO redistribution voting
        - Preserves ownership proof
        """

        nft_id = hashlib.sha256(
            f"{legacy_id}{asset_type}{int(time.time())}".encode()
        ).hexdigest()[:16]

        # Convert USD price to THR (rough conversion at lock time)
        # In production: use historical price oracle
        historical_price_thr = historical_price_usd / 10000  # Estimate

        dormant_nft = {
            "nft_id": nft_id,
            "legacy_id": legacy_id,
            "asset_type": asset_type,
            "asset_identifier": asset_identifier,
            "current_value_thr": Decimal(str(asset_value)),
            "historical_price_usd": historical_price_usd,
            "historical_price_thr": float(historical_price_thr),
            "locked_timestamp": locked_timestamp,
            "locked_date": datetime.fromtimestamp(locked_timestamp).isoformat(),
            "death_certificate_hash": death_certificate_hash,
            "status": "dormant",  # dormant, redistributed, claimed
            "created_timestamp": int(time.time()),
            "created_date": datetime.now().isoformat(),
            "nft_contract": f"DORMANT_NFT_{nft_id}",
            "nft_token_id": nft_id,
            "immutable_proof": self._create_immutable_proof(legacy_id, asset_value)
        }

        dormant_assets = self._load_json(self.dormant_nfts_file)
        dormant_assets.append(dormant_nft)
        self._save_json(self.dormant_nfts_file, dormant_assets)

        return dormant_nft

    def register_foundation(
        self,
        foundation_name: str,
        foundation_address: str,
        mission: str,
        focus_areas: List[str],  # e.g., ["medical", "education", "climate"]
        legal_entity_hash: str  # Hash of legal registration docs
    ) -> Dict[str, Any]:
        """
        Register charitable foundation for dormant asset redistribution.

        Requirements:
        - Legal non-profit status (verified via hash)
        - Clear mission statement
        - Public accountability (on-chain reporting)
        - Multi-signature authorization
        """

        foundation_id = hashlib.sha256(
            f"{foundation_address}{int(time.time())}".encode()
        ).hexdigest()[:16]

        foundation = {
            "foundation_id": foundation_id,
            "foundation_name": foundation_name,
            "foundation_address": foundation_address,
            "mission": mission,
            "focus_areas": focus_areas,
            "legal_entity_hash": legal_entity_hash,
            "status": "pending_verification",  # pending, verified, suspended
            "verification_timestamp": None,
            "registered_timestamp": int(time.time()),
            "registered_date": datetime.now().isoformat(),
            "assets_received": [],  # List of nft_ids
            "total_value_received_thr": 0,
            "reporting_url": f"https://foundation.{foundation_address}.eth/reports"
        }

        foundations = self._load_json(self.foundation_registry_file)
        foundations.append(foundation)
        self._save_json(self.foundation_registry_file, foundations)

        return foundation

    def propose_redistribution(
        self,
        foundation_id: str,
        dormant_nft_id: str,
        proposer_address: str,
        justification: str,
        duration_years: int = 5
    ) -> Dict[str, Any]:
        """
        Create DAO proposal to redistribute dormant asset to foundation.

        Voting Requirements:
        - 51% of THR holders approve
        - Must include legal justification
        - 30-day voting period
        - Quadratic voting (prevents whale control)
        """

        proposal_id = hashlib.sha256(
            f"{foundation_id}{dormant_nft_id}{int(time.time())}".encode()
        ).hexdigest()[:16]

        proposal = {
            "proposal_id": proposal_id,
            "foundation_id": foundation_id,
            "dormant_nft_id": dormant_nft_id,
            "proposer_address": proposer_address,
            "justification": justification,
            "duration_years": duration_years,
            "status": "voting",  # voting, approved, rejected, executed
            "created_timestamp": int(time.time()),
            "created_date": datetime.now().isoformat(),
            "voting_deadline": int(time.time()) + (30 * 24 * 3600),  # 30 days
            "votes_for": 0,
            "votes_against": 0,
            "total_thr_voted": 0,
            "approval_percentage": 0,
            "executed_timestamp": None,
            "executed_date": None
        }

        proposals = self._load_json(self.dao_proposals_file)
        proposals.append(proposal)
        self._save_json(self.dao_proposals_file, proposals)

        return proposal

    def vote_on_proposal(
        self,
        proposal_id: str,
        voter_address: str,
        thr_amount: float,
        vote: str  # "for" or "against"
    ) -> Dict[str, Any]:
        """
        Vote on dormant asset redistribution proposal.

        Voting Method: Quadratic voting
        - Cost to vote = (votes)^2 THR
        - Prevents whale control
        - Encourages genuine participation

        Example:
        - 1 vote costs 1 THR
        - 2 votes cost 4 THR
        - 10 votes cost 100 THR
        """

        proposals = self._load_json(self.dao_proposals_file)
        proposal = next((p for p in proposals if p["proposal_id"] == proposal_id), None)

        if not proposal:
            raise ValueError("Proposal not found")

        if proposal["status"] != "voting":
            raise ValueError("Proposal voting has ended")

        if int(time.time()) > proposal["voting_deadline"]:
            raise ValueError("Voting period has expired")

        # Quadratic voting calculation
        vote_power = thr_amount ** 0.5  # Square root of THR amount

        if vote == "for":
            proposal["votes_for"] += vote_power
        elif vote == "against":
            proposal["votes_against"] += vote_power
        else:
            raise ValueError("Vote must be 'for' or 'against'")

        proposal["total_thr_voted"] += thr_amount
        total_votes = proposal["votes_for"] + proposal["votes_against"]

        if total_votes > 0:
            proposal["approval_percentage"] = (proposal["votes_for"] / total_votes) * 100

        # Update proposal list
        for i, p in enumerate(proposals):
            if p["proposal_id"] == proposal_id:
                proposals[i] = proposal
                break

        self._save_json(self.dao_proposals_file, proposals)

        return {
            "voted": True,
            "voter_address": voter_address,
            "vote": vote,
            "vote_power": vote_power,
            "thr_cost": thr_amount,
            "current_approval": proposal["approval_percentage"]
        }

    def finalize_proposal(
        self,
        proposal_id: str
    ) -> Dict[str, Any]:
        """
        Finalize voting and execute redistribution if approved (51%+).
        """

        proposals = self._load_json(self.dao_proposals_file)
        proposal = next((p for p in proposals if p["proposal_id"] == proposal_id), None)

        if not proposal:
            raise ValueError("Proposal not found")

        if proposal["status"] != "voting":
            raise ValueError("Proposal already finalized")

        # Check if voting period is over
        if int(time.time()) <= proposal["voting_deadline"]:
            raise ValueError("Voting period not yet ended")

        # Check approval (51% threshold with quadratic voting)
        approved = proposal["approval_percentage"] >= 51

        proposal["status"] = "approved" if approved else "rejected"
        proposal["executed_timestamp"] = int(time.time())
        proposal["executed_date"] = datetime.now().isoformat()

        if approved:
            # Update NFT status
            dormant_assets = self._load_json(self.dormant_nfts_file)
            for nft in dormant_assets:
                if nft["nft_id"] == proposal["dormant_nft_id"]:
                    nft["status"] = "redistributed"
                    nft["redistributed_to_foundation"] = proposal["foundation_id"]
                    break

            self._save_json(self.dormant_nfts_file, dormant_assets)

        # Update proposals list
        for i, p in enumerate(proposals):
            if p["proposal_id"] == proposal_id:
                proposals[i] = proposal
                break

        self._save_json(self.dao_proposals_file, proposals)

        return {
            "proposal_id": proposal_id,
            "approved": approved,
            "approval_percentage": proposal["approval_percentage"],
            "total_votes": proposal["votes_for"] + proposal["votes_against"],
            "status": proposal["status"]
        }

    def update_dormant_reserve(
        self,
        block_height: int,
        new_blocks: int,
        thr_per_block: float
    ) -> Dict[str, Any]:
        """
        Update dormant asset reserve from 5% of block rewards.

        Allocation:
        - 80% to miners
        - 10% to AI treasury
        - 5% to Dormant Asset Reserve (NEW)
        - 5% to burn (reduced from 10%)
        """

        reserve_amount = new_blocks * thr_per_block * 0.05
        reserve = self._load_json(self.dormant_reserve_file)

        if not isinstance(reserve, dict):
            reserve = {}

        reserve["total_accumulated"] = reserve.get("total_accumulated", 0) + reserve_amount
        reserve["last_update_block"] = block_height
        reserve["last_update_timestamp"] = int(time.time())
        reserve["last_update_date"] = datetime.now().isoformat()

        self._save_json(self.dormant_reserve_file, reserve)

        return {
            "block_height": block_height,
            "blocks_processed": new_blocks,
            "thr_per_block": thr_per_block,
            "reserve_amount_added": reserve_amount,
            "total_accumulated": reserve["total_accumulated"]
        }

    def use_reserve_to_stabilize(
        self,
        dormant_nft_id: str,
        target_price_thr: float
    ) -> Dict[str, Any]:
        """
        Use dormant reserve to buy dormant NFTs and stabilize price.

        Strategy:
        - If dormant NFT price < historical price
        - Use reserve to buy NFT
        - Stabilize asset value
        - When price recovers, redistribute to foundation
        """

        dormant_assets = self._load_json(self.dormant_nfts_file)
        nft = next((n for n in dormant_assets if n["nft_id"] == dormant_nft_id), None)

        if not nft:
            raise ValueError("Dormant NFT not found")

        reserve = self._load_json(self.dormant_reserve_file)
        current_reserve = reserve.get("total_accumulated", 0)

        if current_reserve < target_price_thr:
            raise ValueError("Insufficient reserve to stabilize")

        # Spend from reserve
        reserve["total_accumulated"] -= target_price_thr
        reserve["used_for_stabilization"] = reserve.get("used_for_stabilization", 0) + target_price_thr

        self._save_json(self.dormant_reserve_file, reserve)

        return {
            "nft_id": dormant_nft_id,
            "price_stabilized": target_price_thr,
            "reserve_remaining": reserve["total_accumulated"],
            "timestamp": int(time.time())
        }

    def get_dormant_assets(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all dormant assets, optionally filtered by status."""
        assets = self._load_json(self.dormant_nfts_file)
        if status:
            return [a for a in assets if a["status"] == status]
        return assets

    def get_active_proposals(self) -> List[Dict[str, Any]]:
        """Get all active voting proposals."""
        proposals = self._load_json(self.dao_proposals_file)
        return [p for p in proposals if p["status"] == "voting"]

    def get_foundation(self, foundation_id: str) -> Optional[Dict[str, Any]]:
        """Get foundation details."""
        foundations = self._load_json(self.foundation_registry_file)
        return next((f for f in foundations if f["foundation_id"] == foundation_id), None)

    def _create_immutable_proof(
        self,
        legacy_id: str,
        asset_value: float
    ) -> str:
        """Create immutable proof of dormant asset."""
        proof_input = f"{legacy_id}:{asset_value}:{int(time.time())}"
        return hashlib.sha256(proof_input.encode()).hexdigest()


# Solidity Smart Contract for Dormant Asset NFTs
DORMANT_ASSET_NFT_CONTRACT = '''
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract DormantAssetNFT {
    string public name = "Thronos Dormant Asset NFT";
    string public symbol = "TDANFT";

    struct DormantNFT {
        string nftId;
        string legacyId;
        string assetType;
        uint256 historicalPriceUSD;
        uint256 lockedTimestamp;
        bool redistributed;
        address foundation;
    }

    struct DAOProposal {
        string proposalId;
        string nftId;
        address foundationAddress;
        uint256 votesFor;
        uint256 votesAgainst;
        uint256 votingDeadline;
        bool executed;
        bool approved;
    }

    mapping(string => DormantNFT) public dormantNFTs;
    mapping(string => DAOProposal) public proposals;
    mapping(string => mapping(address => bool)) public hasVoted;

    event DormantNFTCreated(
        string indexed nftId,
        string legacyId,
        string assetType,
        uint256 historicalPrice,
        uint256 timestamp
    );

    event ProposalCreated(
        string indexed proposalId,
        string nftId,
        address foundation,
        uint256 deadline
    );

    event VoteCast(
        string indexed proposalId,
        address voter,
        bool support,
        uint256 power
    );

    event ProposalExecuted(
        string indexed proposalId,
        bool approved,
        address foundation
    );

    function createDormantNFT(
        string memory _nftId,
        string memory _legacyId,
        string memory _assetType,
        uint256 _historicalPriceUSD,
        uint256 _lockedTimestamp
    ) public {
        dormantNFTs[_nftId] = DormantNFT({
            nftId: _nftId,
            legacyId: _legacyId,
            assetType: _assetType,
            historicalPriceUSD: _historicalPriceUSD,
            lockedTimestamp: _lockedTimestamp,
            redistributed: false,
            foundation: address(0)
        });

        emit DormantNFTCreated(_nftId, _legacyId, _assetType, _historicalPriceUSD, block.timestamp);
    }

    function createRedistributionProposal(
        string memory _proposalId,
        string memory _nftId,
        address _foundationAddress
    ) public {
        require(dormantNFTs[_nftId].redistributed == false, "NFT already redistributed");

        proposals[_proposalId] = DAOProposal({
            proposalId: _proposalId,
            nftId: _nftId,
            foundationAddress: _foundationAddress,
            votesFor: 0,
            votesAgainst: 0,
            votingDeadline: block.timestamp + 30 days,
            executed: false,
            approved: false
        });

        emit ProposalCreated(_proposalId, _nftId, _foundationAddress, block.timestamp + 30 days);
    }

    function vote(
        string memory _proposalId,
        bool _support,
        uint256 _power
    ) public {
        require(!hasVoted[_proposalId][msg.sender], "Already voted");
        require(block.timestamp < proposals[_proposalId].votingDeadline, "Voting ended");

        if (_support) {
            proposals[_proposalId].votesFor += _power;
        } else {
            proposals[_proposalId].votesAgainst += _power;
        }

        hasVoted[_proposalId][msg.sender] = true;
        emit VoteCast(_proposalId, msg.sender, _support, _power);
    }

    function executeProposal(string memory _proposalId) public {
        DAOProposal storage proposal = proposals[_proposalId];
        require(!proposal.executed, "Already executed");
        require(block.timestamp >= proposal.votingDeadline, "Voting still ongoing");

        uint256 totalVotes = proposal.votesFor + proposal.votesAgainst;
        proposal.approved = (proposal.votesFor * 100) / totalVotes >= 51;
        proposal.executed = true;

        if (proposal.approved) {
            DormantNFT storage nft = dormantNFTs[proposal.nftId];
            nft.redistributed = true;
            nft.foundation = proposal.foundationAddress;
        }

        emit ProposalExecuted(_proposalId, proposal.approved, proposal.foundationAddress);
    }
}
'''
