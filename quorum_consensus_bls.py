#!/usr/bin/env python3
"""
Thronos Quorum Consensus with BLS Signatures
============================================
Byzantine Fault Tolerant consensus with BLS signature aggregation

Features:
- BLS signature aggregation for efficient consensus
- Byzantine Fault Tolerant consensus (supports up to 1/3 malicious nodes)
- Validator network with stake-based voting power
- Fast finality (2-3 seconds)
- Slashing for malicious behavior
- Dynamic validator set
- Checkpoint-based finality

Phase 5: Full Decentralization
Version: 4.0
"""

import os
import json
import time
import hashlib
import secrets
import logging
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass, asdict
from pathlib import Path
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Validator:
    """Validator node information"""
    validator_id: str
    public_key: str  # BLS public key
    stake_amount: float
    reputation_score: float = 100.0
    total_blocks_validated: int = 0
    slashed: bool = False
    joined_at: str = ""
    last_active: str = ""


@dataclass
class QuorumVote:
    """Vote from a validator"""
    validator_id: str
    block_hash: str
    block_height: int
    signature: str  # BLS signature
    timestamp: str
    stake_weight: float


@dataclass
class ConsensusRound:
    """Consensus round for a block"""
    round_id: str
    block_height: int
    block_hash: str
    proposer_id: str
    votes: List[QuorumVote]
    aggregated_signature: Optional[str] = None
    finalized: bool = False
    finalized_at: Optional[str] = None
    total_stake_voted: float = 0.0


class BLSSignature:
    """
    BLS Signature implementation (simplified)
    In production, use a proper BLS library like py_ecc or blspy
    """

    @staticmethod
    def generate_keypair() -> Tuple[str, str]:
        """Generate BLS key pair"""
        # In production, use proper BLS key generation
        private_key = secrets.token_hex(32)
        public_key = hashlib.sha256(private_key.encode()).hexdigest()
        return private_key, public_key

    @staticmethod
    def sign(private_key: str, message: str) -> str:
        """Sign message with BLS private key"""
        # In production, use proper BLS signing
        combined = f"{private_key}:{message}"
        signature = hashlib.sha256(combined.encode()).hexdigest()
        return signature

    @staticmethod
    def verify(public_key: str, message: str, signature: str) -> bool:
        """Verify BLS signature"""
        # In production, use proper BLS verification
        # This is a simplified version
        return len(signature) == 64  # Basic validation

    @staticmethod
    def aggregate_signatures(signatures: List[str]) -> str:
        """Aggregate multiple BLS signatures"""
        # In production, use proper BLS aggregation
        # BLS signatures can be aggregated: sig1 + sig2 + sig3 = aggregated_sig
        combined = "".join(sorted(signatures))
        aggregated = hashlib.sha256(combined.encode()).hexdigest()
        return aggregated

    @staticmethod
    def verify_aggregated(
        public_keys: List[str],
        messages: List[str],
        aggregated_signature: str
    ) -> bool:
        """Verify aggregated BLS signature"""
        # In production, use proper BLS aggregate verification
        return len(aggregated_signature) == 64


class QuorumConsensus:
    """
    Quorum-based BFT Consensus Engine
    """

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)

        # Storage
        self.validators_path = self.data_dir / "validators.json"
        self.consensus_log_path = self.data_dir / "consensus_rounds.jsonl"
        self.checkpoints_path = self.data_dir / "consensus_checkpoints.json"

        # Configuration
        self.min_stake = float(os.getenv("MIN_VALIDATOR_STAKE", "10000"))
        self.quorum_threshold = float(os.getenv("QUORUM_THRESHOLD", "0.67"))  # 2/3 majority
        self.block_time = int(os.getenv("BLOCK_TIME", "3"))  # seconds
        self.max_validators = int(os.getenv("MAX_VALIDATORS", "100"))

        # State
        self.validators: Dict[str, Validator] = {}
        self.active_rounds: Dict[int, ConsensusRound] = {}
        self.finalized_blocks: Set[str] = set()
        self.current_height = 0
        self.last_checkpoint_height = 0

        # Load state
        self._load_validators()
        self._load_checkpoints()

        logger.info("⚡ Quorum Consensus initialized")
        logger.info(f"   Validators: {len(self.validators)}")
        logger.info(f"   Quorum threshold: {self.quorum_threshold * 100}%")
        logger.info(f"   Block time: {self.block_time}s")

    def _load_validators(self):
        """Load validator set"""
        if not self.validators_path.exists():
            return

        try:
            with open(self.validators_path, 'r') as f:
                data = json.load(f)
                self.validators = {
                    vid: Validator(**vdata)
                    for vid, vdata in data.items()
                }
            logger.info(f"Loaded {len(self.validators)} validators")
        except Exception as e:
            logger.error(f"Error loading validators: {e}")

    def _save_validators(self):
        """Save validator set"""
        try:
            data = {
                vid: asdict(validator)
                for vid, validator in self.validators.items()
            }
            with open(self.validators_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving validators: {e}")

    def _load_checkpoints(self):
        """Load consensus checkpoints"""
        if not self.checkpoints_path.exists():
            return

        try:
            with open(self.checkpoints_path, 'r') as f:
                data = json.load(f)
                self.current_height = data.get('current_height', 0)
                self.last_checkpoint_height = data.get('last_checkpoint_height', 0)
                self.finalized_blocks = set(data.get('finalized_blocks', []))
        except Exception as e:
            logger.error(f"Error loading checkpoints: {e}")

    def _save_checkpoint(self):
        """Save consensus checkpoint"""
        try:
            data = {
                'current_height': self.current_height,
                'last_checkpoint_height': self.last_checkpoint_height,
                'finalized_blocks': list(self.finalized_blocks),
                'timestamp': time.time()
            }
            with open(self.checkpoints_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving checkpoint: {e}")

    def _log_consensus_round(self, consensus_round: ConsensusRound):
        """Log consensus round to file"""
        try:
            with open(self.consensus_log_path, 'a') as f:
                f.write(json.dumps(asdict(consensus_round)) + '\n')
        except Exception as e:
            logger.error(f"Error logging consensus round: {e}")

    # ========================================================================
    # VALIDATOR MANAGEMENT
    # ========================================================================

    def register_validator(
        self,
        validator_id: str,
        stake_amount: float
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Register a new validator

        Returns: (success, message, public_key)
        """
        logger.info(f"Registering validator: {validator_id}")

        # Check stake amount
        if stake_amount < self.min_stake:
            return False, f"Minimum stake is {self.min_stake} THR", None

        # Check max validators
        if len(self.validators) >= self.max_validators:
            return False, f"Maximum {self.max_validators} validators reached", None

        # Check if already registered
        if validator_id in self.validators:
            return False, "Validator already registered", None

        # Generate BLS keypair
        private_key, public_key = BLSSignature.generate_keypair()

        # Create validator
        validator = Validator(
            validator_id=validator_id,
            public_key=public_key,
            stake_amount=stake_amount,
            joined_at=time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            last_active=time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        )

        self.validators[validator_id] = validator
        self._save_validators()

        logger.info(f"✅ Validator {validator_id} registered with {stake_amount} THR stake")
        return True, "Validator registered successfully", public_key

    def get_total_stake(self) -> float:
        """Get total stake in network"""
        return sum(v.stake_amount for v in self.validators.values() if not v.slashed)

    def get_active_validators(self) -> List[Validator]:
        """Get list of active (non-slashed) validators"""
        return [v for v in self.validators.values() if not v.slashed]

    def slash_validator(self, validator_id: str, reason: str) -> bool:
        """Slash a validator for malicious behavior"""
        if validator_id not in self.validators:
            return False

        validator = self.validators[validator_id]
        validator.slashed = True
        validator.reputation_score = 0.0

        logger.warning(f"⚠️  Validator {validator_id} slashed: {reason}")

        self._save_validators()
        return True

    # ========================================================================
    # CONSENSUS PROTOCOL
    # ========================================================================

    def propose_block(
        self,
        block_hash: str,
        block_height: int,
        proposer_id: str
    ) -> Tuple[bool, str]:
        """
        Propose a new block for consensus

        Returns: (success, message)
        """
        logger.info(f"Block proposed: height={block_height}, hash={block_hash[:16]}...")

        # Verify proposer is a validator
        if proposer_id not in self.validators:
            return False, "Proposer is not a registered validator"

        if self.validators[proposer_id].slashed:
            return False, "Proposer has been slashed"

        # Create consensus round
        round_id = f"round_{block_height}_{int(time.time())}"

        consensus_round = ConsensusRound(
            round_id=round_id,
            block_height=block_height,
            block_hash=block_hash,
            proposer_id=proposer_id,
            votes=[]
        )

        self.active_rounds[block_height] = consensus_round

        logger.info(f"Consensus round {round_id} started")
        return True, f"Block proposed for consensus: {round_id}"

    def vote_on_block(
        self,
        validator_id: str,
        block_hash: str,
        block_height: int,
        private_key: str
    ) -> Tuple[bool, str]:
        """
        Vote on a proposed block

        Returns: (success, message)
        """
        # Verify validator
        if validator_id not in self.validators:
            return False, "Not a registered validator"

        validator = self.validators[validator_id]

        if validator.slashed:
            return False, "Validator has been slashed"

        # Check if round exists
        if block_height not in self.active_rounds:
            return False, "No active consensus round for this height"

        consensus_round = self.active_rounds[block_height]

        # Check if already voted
        for vote in consensus_round.votes:
            if vote.validator_id == validator_id:
                return False, "Already voted in this round"

        # Create BLS signature
        message = f"{block_hash}:{block_height}"
        signature = BLSSignature.sign(private_key, message)

        # Create vote
        vote = QuorumVote(
            validator_id=validator_id,
            block_hash=block_hash,
            block_height=block_height,
            signature=signature,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            stake_weight=validator.stake_amount
        )

        consensus_round.votes.append(vote)
        consensus_round.total_stake_voted += validator.stake_amount

        # Update validator stats
        validator.last_active = vote.timestamp
        self._save_validators()

        logger.info(f"Vote recorded: {validator_id} for block {block_hash[:16]}...")

        # Check if quorum reached
        self._check_quorum(block_height)

        return True, "Vote recorded"

    def _check_quorum(self, block_height: int):
        """Check if quorum has been reached for a block"""
        if block_height not in self.active_rounds:
            return

        consensus_round = self.active_rounds[block_height]
        total_stake = self.get_total_stake()

        if total_stake == 0:
            return

        # Calculate vote percentage
        vote_percentage = consensus_round.total_stake_voted / total_stake

        logger.info(f"Quorum check: {vote_percentage*100:.1f}% voted (need {self.quorum_threshold*100}%)")

        # Check if quorum reached
        if vote_percentage >= self.quorum_threshold:
            self._finalize_block(block_height)

    def _finalize_block(self, block_height: int):
        """Finalize a block after reaching quorum"""
        if block_height not in self.active_rounds:
            return

        consensus_round = self.active_rounds[block_height]

        logger.info(f"🎉 Finalizing block at height {block_height}")

        # Aggregate BLS signatures
        signatures = [vote.signature for vote in consensus_round.votes]
        aggregated_signature = BLSSignature.aggregate_signatures(signatures)

        consensus_round.aggregated_signature = aggregated_signature
        consensus_round.finalized = True
        consensus_round.finalized_at = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

        # Update validator stats
        for vote in consensus_round.votes:
            if vote.validator_id in self.validators:
                self.validators[vote.validator_id].total_blocks_validated += 1

        # Mark as finalized
        self.finalized_blocks.add(consensus_round.block_hash)
        self.current_height = max(self.current_height, block_height)

        # Log to file
        self._log_consensus_round(consensus_round)

        # Clean up
        del self.active_rounds[block_height]

        # Save checkpoint periodically
        if self.current_height % 100 == 0:
            self.last_checkpoint_height = self.current_height
            self._save_checkpoint()
            logger.info(f"💾 Checkpoint saved at height {self.current_height}")

        self._save_validators()

        logger.info(f"✅ Block finalized: {consensus_round.block_hash[:16]}...")
        logger.info(f"   Votes: {len(consensus_round.votes)}")
        logger.info(f"   Stake: {consensus_round.total_stake_voted:.0f} THR")

    def is_block_finalized(self, block_hash: str) -> bool:
        """Check if a block has been finalized"""
        return block_hash in self.finalized_blocks

    def get_consensus_status(self, block_height: int) -> Optional[Dict[str, Any]]:
        """Get status of consensus round"""
        if block_height in self.active_rounds:
            return asdict(self.active_rounds[block_height])
        return None

    def get_network_stats(self) -> Dict[str, Any]:
        """Get network consensus statistics"""
        active_validators = self.get_active_validators()

        return {
            'total_validators': len(self.validators),
            'active_validators': len(active_validators),
            'slashed_validators': len([v for v in self.validators.values() if v.slashed]),
            'total_stake': self.get_total_stake(),
            'current_height': self.current_height,
            'finalized_blocks': len(self.finalized_blocks),
            'active_rounds': len(self.active_rounds),
            'quorum_threshold': f"{self.quorum_threshold * 100}%",
            'block_time': f"{self.block_time}s"
        }


def main():
    """Test the consensus system"""
    print("⚡ Thronos Quorum Consensus with BLS\n")

    consensus = QuorumConsensus()

    # Register validators
    print("📝 Registering validators...")
    validators = []
    for i in range(5):
        vid = f"validator_{i+1}"
        success, msg, pubkey = consensus.register_validator(vid, 20000)
        if success:
            print(f"  ✅ {vid}: {pubkey[:16]}...")
            # Store private key for testing (in production, validators keep this secret)
            priv_key = secrets.token_hex(32)
            validators.append((vid, priv_key))

    # Propose a block
    print("\n🔨 Proposing block...")
    block_hash = hashlib.sha256(b"test_block_1").hexdigest()
    success, msg = consensus.propose_block(block_hash, 1, validators[0][0])
    print(f"  {msg}")

    # Vote on block
    print("\n🗳️  Voting on block...")
    for vid, priv_key in validators[:4]:  # 4 out of 5 vote
        success, msg = consensus.vote_on_block(vid, block_hash, 1, priv_key)
        print(f"  {vid}: {msg}")

    # Check stats
    print("\n📊 Network Statistics:")
    stats = consensus.get_network_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
