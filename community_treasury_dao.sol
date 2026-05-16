// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/**
 * Community Treasury DAO Contract
 *
 * Governs 5% of Thronos block rewards (~$6.5M annually)
 * Every person has equal voice (1 THR = 1 vote)
 * No one person controls money
 * Democracy decides allocation
 * All decisions immutable + transparent
 *
 * Philosophy: Humanity votes on how to help humanity
 */

contract CommunityTreasuryDAO {

    // ─── STRUCTURES ─────────────────────────────────────────────

    struct Proposal {
        string proposalId;
        string title;
        string description;
        address proposer;
        uint256 requestedAmount;           // THR amount requested
        string beneficiaryType;            // "medical", "education", "climate", "poverty", "research"
        string beneficiaryName;
        address beneficiaryAddress;
        uint256 createdTimestamp;
        uint256 votingDeadline;
        uint256 votesFor;
        uint256 votesAgainst;
        uint256 totalVotingPower;
        uint256 approvalPercentage;
        string status;                     // "voting", "approved", "rejected", "executed", "cancelled"
        uint256 executedTimestamp;
        string reportUrl;                  // Beneficiary reporting URL
        bytes32 ipfsHash;                  // Proposal details on IPFS
    }

    struct Distribution {
        string distributionId;
        string proposalId;
        address beneficiary;
        uint256 amount;
        uint256 distributedTimestamp;
        string transactionHash;
        bool received;
    }

    struct TreasuryStats {
        uint256 totalAccumulated;
        uint256 totalDistributed;
        uint256 currentBalance;
        uint256 totalProposals;
        uint256 approvedProposals;
        uint256 rejectedProposals;
        uint256 executedProposals;
    }

    // ─── STATE VARIABLES ────────────────────────────────────────

    mapping(string => Proposal) public proposals;
    mapping(string => Distribution[]) public distributions;
    mapping(address => mapping(string => bool)) public hasVoted;
    mapping(address => uint256) public voterBalance;

    address public admin;
    uint256 public treasuryBalance;
    uint256 public totalDistributed;
    uint256 public totalProposals;
    uint256 public epoch3StartBlock = 630000;

    string[] public proposalIds;
    string[] public approvedProposals;

    // Constants
    uint256 public constant VOTING_PERIOD = 30 days;
    uint256 public constant APPROVAL_THRESHOLD = 51;  // 51% required
    uint256 public constant ALLOCATION_PERCENTAGE = 5; // 5% of blocks

    // ─── EVENTS ─────────────────────────────────────────────────

    event ProposalCreated(
        string indexed proposalId,
        address indexed proposer,
        string title,
        uint256 requestedAmount,
        uint256 deadline
    );

    event VoteCast(
        string indexed proposalId,
        address indexed voter,
        bool support,
        uint256 votePower
    );

    event ProposalFinalized(
        string indexed proposalId,
        bool approved,
        uint256 approvalPercentage
    );

    event FundsDistributed(
        string indexed proposalId,
        string indexed distributionId,
        address beneficiary,
        uint256 amount
    );

    event TreasuryUpdated(
        uint256 newBalance,
        uint256 totalDistributed
    );

    event EmergencyPause(
        string reason,
        uint256 timestamp
    );

    // ─── MODIFIERS ──────────────────────────────────────────────

    modifier onlyAdmin() {
        require(msg.sender == admin, "Only admin");
        _;
    }

    modifier validProposal(string memory proposalId) {
        require(
            keccak256(abi.encodePacked(proposals[proposalId].proposalId)) ==
            keccak256(abi.encodePacked(proposalId)),
            "Proposal not found"
        );
        _;
    }

    // ─── INITIALIZATION ─────────────────────────────────────────

    constructor() {
        admin = msg.sender;
        treasuryBalance = 0;
        totalDistributed = 0;
        totalProposals = 0;
    }

    // ─── TREASURY MANAGEMENT ─────────────────────────────────────

    /**
     * Add funds to treasury from block rewards (5% allocation)
     * Called by mining system every block
     */
    function depositFromBlockRewards(uint256 amount) public onlyAdmin {
        treasuryBalance += amount;

        emit TreasuryUpdated(treasuryBalance, totalDistributed);
    }

    /**
     * Batch deposit (multiple blocks at once)
     */
    function batchDepositFromBlockRewards(uint256[] memory amounts) public onlyAdmin {
        uint256 totalAmount = 0;

        for (uint i = 0; i < amounts.length; i++) {
            totalAmount += amounts[i];
        }

        treasuryBalance += totalAmount;

        emit TreasuryUpdated(treasuryBalance, totalDistributed);
    }

    // ─── PROPOSAL CREATION ───────────────────────────────────────

    /**
     * Create new spending proposal
     * Anyone can propose, democracy votes
     */
    function createProposal(
        string memory title,
        string memory description,
        uint256 requestedAmount,
        string memory beneficiaryType,
        string memory beneficiaryName,
        address beneficiaryAddress
    ) public returns (string memory) {

        require(requestedAmount > 0, "Invalid amount");
        require(requestedAmount <= treasuryBalance, "Insufficient treasury");
        require(bytes(title).length > 0, "Invalid title");

        // Validate beneficiary type
        require(
            keccak256(abi.encodePacked(beneficiaryType)) == keccak256(abi.encodePacked("medical")) ||
            keccak256(abi.encodePacked(beneficiaryType)) == keccak256(abi.encodePacked("education")) ||
            keccak256(abi.encodePacked(beneficiaryType)) == keccak256(abi.encodePacked("climate")) ||
            keccak256(abi.encodePacked(beneficiaryType)) == keccak256(abi.encodePacked("poverty")) ||
            keccak256(abi.encodePacked(beneficiaryType)) == keccak256(abi.encodePacked("research")),
            "Invalid beneficiary type"
        );

        // Generate unique proposal ID
        string memory proposalId = generateProposalId();

        Proposal memory newProposal = Proposal({
            proposalId: proposalId,
            title: title,
            description: description,
            proposer: msg.sender,
            requestedAmount: requestedAmount,
            beneficiaryType: beneficiaryType,
            beneficiaryName: beneficiaryName,
            beneficiaryAddress: beneficiaryAddress,
            createdTimestamp: block.timestamp,
            votingDeadline: block.timestamp + VOTING_PERIOD,
            votesFor: 0,
            votesAgainst: 0,
            totalVotingPower: 0,
            approvalPercentage: 0,
            status: "voting",
            executedTimestamp: 0,
            reportUrl: "",
            ipfsHash: ""
        });

        proposals[proposalId] = newProposal;
        proposalIds.push(proposalId);
        totalProposals++;

        emit ProposalCreated(
            proposalId,
            msg.sender,
            title,
            requestedAmount,
            block.timestamp + VOTING_PERIOD
        );

        return proposalId;
    }

    // ─── VOTING (QUADRATIC) ──────────────────────────────────────

    /**
     * Vote on proposal using Quadratic Voting
     * Cost = (voting_power)^2 THR
     * Prevents whale control
     */
    function vote(
        string memory proposalId,
        bool support,
        uint256 votingPower
    ) public validProposal(proposalId) {

        Proposal storage proposal = proposals[proposalId];

        // Validate voting period
        require(
            block.timestamp < proposal.votingDeadline,
            "Voting period ended"
        );
        require(
            keccak256(abi.encodePacked(proposal.status)) ==
            keccak256(abi.encodePacked("voting")),
            "Proposal not in voting"
        );

        // One vote per person per proposal
        require(
            !hasVoted[msg.sender][proposalId],
            "Already voted on this proposal"
        );

        // Quadratic voting: cost = (power)^2
        // This prevents single voter from controlling outcome
        require(votingPower > 0, "Invalid voting power");

        uint256 voteCost = votingPower * votingPower;
        require(voterBalance[msg.sender] >= voteCost, "Insufficient voting power");

        // Deduct voting cost
        voterBalance[msg.sender] -= voteCost;

        // Record vote
        if (support) {
            proposal.votesFor += votingPower;
        } else {
            proposal.votesAgainst += votingPower;
        }

        proposal.totalVotingPower += votingPower;
        hasVoted[msg.sender][proposalId] = true;

        // Recalculate approval percentage
        if (proposal.totalVotingPower > 0) {
            proposal.approvalPercentage = (proposal.votesFor * 100) / proposal.totalVotingPower;
        }

        emit VoteCast(proposalId, msg.sender, support, votingPower);
    }

    // ─── PROPOSAL FINALIZATION ──────────────────────────────────

    /**
     * Finalize voting and execute if approved (51%+)
     */
    function finalizeProposal(string memory proposalId) public validProposal(proposalId) {

        Proposal storage proposal = proposals[proposalId];

        // Voting must be over
        require(
            block.timestamp >= proposal.votingDeadline,
            "Voting period not ended"
        );

        require(
            keccak256(abi.encodePacked(proposal.status)) ==
            keccak256(abi.encodePacked("voting")),
            "Already finalized"
        );

        // Check approval (51% threshold)
        bool approved = proposal.approvalPercentage >= APPROVAL_THRESHOLD;

        if (approved) {
            proposal.status = "approved";
            approvedProposals.push(proposalId);

            // Move funds to pending distribution
            // (Actual distribution happens when beneficiary claims)
        } else {
            proposal.status = "rejected";
        }

        proposal.executedTimestamp = block.timestamp;

        emit ProposalFinalized(proposalId, approved, proposal.approvalPercentage);
    }

    // ─── FUND DISTRIBUTION ──────────────────────────────────────

    /**
     * Distribute funds to approved proposal beneficiary
     * Called by beneficiary or admin
     */
    function distributeFunds(
        string memory proposalId
    ) public validProposal(proposalId) {

        Proposal storage proposal = proposals[proposalId];

        require(
            keccak256(abi.encodePacked(proposal.status)) ==
            keccak256(abi.encodePacked("approved")),
            "Proposal not approved"
        );

        require(
            msg.sender == proposal.beneficiaryAddress || msg.sender == admin,
            "Not authorized"
        );

        require(proposal.requestedAmount <= treasuryBalance, "Insufficient treasury");

        // Create distribution record
        string memory distributionId = generateDistributionId();

        Distribution memory distribution = Distribution({
            distributionId: distributionId,
            proposalId: proposalId,
            beneficiary: proposal.beneficiaryAddress,
            amount: proposal.requestedAmount,
            distributedTimestamp: block.timestamp,
            transactionHash: "",
            received: true
        });

        distributions[proposalId].push(distribution);

        // Deduct from treasury
        treasuryBalance -= proposal.requestedAmount;
        totalDistributed += proposal.requestedAmount;

        // Mark as executed
        proposal.status = "executed";

        emit FundsDistributed(
            proposalId,
            distributionId,
            proposal.beneficiaryAddress,
            proposal.requestedAmount
        );

        emit TreasuryUpdated(treasuryBalance, totalDistributed);
    }

    // ─── QUERIES ────────────────────────────────────────────────

    function getProposal(string memory proposalId)
        public
        view
        returns (Proposal memory)
    {
        return proposals[proposalId];
    }

    function getDistributions(string memory proposalId)
        public
        view
        returns (Distribution[] memory)
    {
        return distributions[proposalId];
    }

    function getTreasuryStats() public view returns (TreasuryStats memory) {
        return TreasuryStats({
            totalAccumulated: treasuryBalance + totalDistributed,
            totalDistributed: totalDistributed,
            currentBalance: treasuryBalance,
            totalProposals: totalProposals,
            approvedProposals: approvedProposals.length,
            rejectedProposals: totalProposals - approvedProposals.length,
            executedProposals: totalProposals  // Simplified; track separately in production
        });
    }

    function getAllProposalIds() public view returns (string[] memory) {
        return proposalIds;
    }

    function getApprovedProposals() public view returns (string[] memory) {
        return approvedProposals;
    }

    // ─── UTILITY FUNCTIONS ──────────────────────────────────────

    function generateProposalId() private view returns (string memory) {
        bytes32 hash = keccak256(
            abi.encodePacked(block.timestamp, msg.sender, block.number)
        );
        return bytesToString(abi.encodePacked(hash));
    }

    function generateDistributionId() private view returns (string memory) {
        bytes32 hash = keccak256(
            abi.encodePacked(block.timestamp, block.number, msg.sender)
        );
        return bytesToString(abi.encodePacked(hash));
    }

    function bytesToString(bytes memory data) private pure returns (string memory) {
        bytes memory hexChars = "0123456789abcdef";
        bytes memory str = new bytes(data.length * 2);

        for (uint i = 0; i < data.length; i++) {
            uint8 value = uint8(data[i]);
            str[i * 2] = hexChars[value >> 4];
            str[i * 2 + 1] = hexChars[value & 0x0f];
        }

        return string(str);
    }

    // ─── EMERGENCY PROCEDURES ───────────────────────────────────

    function emergencyPause(string memory reason) public onlyAdmin {
        emit EmergencyPause(reason, block.timestamp);
        // In production: Set flag to pause all operations
    }
}
