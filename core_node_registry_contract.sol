// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/**
 * Core Node Registry Contract
 *
 * Manages blockchain nodes that provide services (hospitals, schools, charities)
 * and receive 5% of block rewards from the Thronos network.
 *
 * Philosophy: Stop burning value. Start building infrastructure.
 * No more 10% wasted. Instead, 5% funds hospitals, schools, research.
 * 5% funds community treasury (DAO governance).
 */

contract CoreNodeRegistry {

    // ─── DATA STRUCTURES ────────────────────────────────────────

    struct CoreNode {
        string nodeId;
        address organizationAddress;
        string nodeType;                // "hospital", "university", "charity", "mesh", "archive"
        string organizationName;
        string mission;
        bytes32 legalRegistrationHash;  // Hash of legal documents (never store docs)
        uint256 registeredBlock;
        uint256 registeredTimestamp;
        bool daoApproved;               // Requires DAO vote
        uint256 rewardTier;             // Base reward multiplier
        uint256 impactMetric;           // How many it serves (patients, students, etc)
        uint256 totalRewardsEarned;
        bool active;
        string reportingUrl;            // URL for quarterly reports
        uint256 lastReportTimestamp;
    }

    struct RewardAllocation {
        string nodeId;
        uint256 baseRewardPerBlock;     // Fixed: 0.00625 THR
        uint256 impactBonusPerUnit;     // Varies by type
        uint256 totalAllocatedThisEpoch;
        uint256 nodesCount;
    }

    struct ImpactReport {
        string nodeId;
        uint256 reportTimestamp;
        uint256 peopleServed;
        uint256 servicesDelivered;
        string reportHash;              // IPFS hash of full report
        bool daoApproved;
    }

    // ─── STATE VARIABLES ────────────────────────────────────────

    address public admin;
    uint256 public epoch3StartBlock = 630000;  // August 2026
    uint256 public currentEpoch = 2;

    mapping(string => CoreNode) public coreNodes;
    mapping(address => string) public addressToNodeId;
    mapping(string => ImpactReport[]) public nodeReports;

    uint256 public totalRegisteredNodes;
    uint256 public totalRewardsDistributed;

    // Epoch 3+ constants
    uint256 public constant EPOCH3_BLOCK_REWARD = 0.125 ether;  // 0.125 THR
    uint256 public constant CORE_NODE_ALLOCATION = 5;           // 5% of rewards
    uint256 public constant BASE_REWARD = 0.00625 ether;        // Base per node

    mapping(string => uint256) public impactBonusPerType;       // Bonus per unit by type

    // ─── EVENTS ─────────────────────────────────────────────────

    event CoreNodeRegistered(
        string indexed nodeId,
        address indexed organizationAddress,
        string nodeType,
        uint256 blockNumber
    );

    event CoreNodeApprovedByDAO(
        string indexed nodeId,
        uint256 blockNumber,
        uint256 approvalPercentage
    );

    event RewardDistributed(
        string indexed nodeId,
        uint256 rewardAmount,
        uint256 blockNumber
    );

    event ImpactReportSubmitted(
        string indexed nodeId,
        uint256 peopleServed,
        uint256 servicesDelivered,
        uint256 blockNumber
    );

    event NodeDeactivated(
        string indexed nodeId,
        string reason,
        uint256 blockNumber
    );

    // ─── MODIFIERS ──────────────────────────────────────────────

    modifier onlyAdmin() {
        require(msg.sender == admin, "Only admin");
        _;
    }

    modifier onlyActiveNode(string memory nodeId) {
        require(coreNodes[nodeId].active, "Node not active");
        require(coreNodes[nodeId].daoApproved, "Node not DAO approved");
        _;
    }

    modifier onlyNodeOrganization(string memory nodeId) {
        require(
            msg.sender == coreNodes[nodeId].organizationAddress,
            "Only node organization"
        );
        _;
    }

    // ─── INITIALIZATION ─────────────────────────────────────────

    constructor() {
        admin = msg.sender;

        // Set impact bonuses by type
        impactBonusPerType["hospital"] = 0.001 ether;      // 0.001 THR per patient
        impactBonusPerType["university"] = 0.001 ether;    // 0.001 THR per student
        impactBonusPerType["charity"] = 0.0005 ether;      // 0.0005 THR per person helped
        impactBonusPerType["mesh"] = 0.0001 ether;         // 0.0001 THR per km²
        impactBonusPerType["archive"] = 0.0001 ether;      // 0.0001 THR per TB
    }

    // ─── REGISTRATION ───────────────────────────────────────────

    function registerCoreNode(
        string memory nodeId,
        string memory nodeType,
        string memory organizationName,
        string memory mission,
        bytes32 legalRegistrationHash
    ) public {
        require(bytes(nodeId).length > 0, "Invalid node ID");
        require(
            keccak256(abi.encodePacked(nodeType)) == keccak256(abi.encodePacked("hospital")) ||
            keccak256(abi.encodePacked(nodeType)) == keccak256(abi.encodePacked("university")) ||
            keccak256(abi.encodePacked(nodeType)) == keccak256(abi.encodePacked("charity")) ||
            keccak256(abi.encodePacked(nodeType)) == keccak256(abi.encodePacked("mesh")) ||
            keccak256(abi.encodePacked(nodeType)) == keccak256(abi.encodePacked("archive")),
            "Invalid node type"
        );
        require(coreNodes[nodeId].registeredBlock == 0, "Node already registered");

        CoreNode memory newNode = CoreNode({
            nodeId: nodeId,
            organizationAddress: msg.sender,
            nodeType: nodeType,
            organizationName: organizationName,
            mission: mission,
            legalRegistrationHash: legalRegistrationHash,
            registeredBlock: block.number,
            registeredTimestamp: block.timestamp,
            daoApproved: false,
            rewardTier: 1,
            impactMetric: 0,
            totalRewardsEarned: 0,
            active: false,
            reportingUrl: "",
            lastReportTimestamp: 0
        });

        coreNodes[nodeId] = newNode;
        addressToNodeId[msg.sender] = nodeId;
        totalRegisteredNodes++;

        emit CoreNodeRegistered(
            nodeId,
            msg.sender,
            nodeType,
            block.number
        );
    }

    // ─── DAO APPROVAL ────────────────────────────────────────────

    function approveCoreNodeByDAO(
        string memory nodeId,
        uint256 approvalPercentage
    ) public onlyAdmin {
        // In production: Called by DAO governance contract
        require(approvalPercentage >= 51, "Need 51% approval");
        require(coreNodes[nodeId].registeredBlock > 0, "Node not found");

        coreNodes[nodeId].daoApproved = true;
        coreNodes[nodeId].active = true;
        coreNodes[nodeId].registeredBlock = block.number;

        emit CoreNodeApprovedByDAO(nodeId, block.number, approvalPercentage);
    }

    // ─── REWARD DISTRIBUTION ────────────────────────────────────

    function calculateNodeReward(
        string memory nodeId
    ) public view returns (uint256) {
        require(coreNodes[nodeId].active, "Node not active");

        CoreNode memory node = coreNodes[nodeId];

        // Base reward
        uint256 baseReward = BASE_REWARD;

        // Impact bonus
        uint256 impactBonus = node.impactMetric * impactBonusPerType[node.nodeType];

        return baseReward + impactBonus;
    }

    function distributeReward(
        string memory nodeId,
        uint256 rewardAmount
    ) public onlyAdmin onlyActiveNode(nodeId) {
        CoreNode storage node = coreNodes[nodeId];
        node.totalRewardsEarned += rewardAmount;
        totalRewardsDistributed += rewardAmount;

        // In production: Transfer THR tokens to node organization
        // transfer(node.organizationAddress, rewardAmount);

        emit RewardDistributed(nodeId, rewardAmount, block.number);
    }

    function distributeRewardsForEpoch(
        string[] memory nodeIds,
        uint256[] memory rewards
    ) public onlyAdmin {
        require(nodeIds.length == rewards.length, "Array length mismatch");

        for (uint i = 0; i < nodeIds.length; i++) {
            if (coreNodes[nodeIds[i]].active) {
                distributeReward(nodeIds[i], rewards[i]);
            }
        }
    }

    // ─── IMPACT REPORTING ────────────────────────────────────────

    function submitImpactReport(
        string memory nodeId,
        uint256 peopleServed,
        uint256 servicesDelivered,
        string memory reportHash
    ) public onlyNodeOrganization(nodeId) onlyActiveNode(nodeId) {

        ImpactReport memory report = ImpactReport({
            nodeId: nodeId,
            reportTimestamp: block.timestamp,
            peopleServed: peopleServed,
            servicesDelivered: servicesDelivered,
            reportHash: reportHash,
            daoApproved: false
        });

        nodeReports[nodeId].push(report);

        // Update impact metric for bonus calculation
        coreNodes[nodeId].impactMetric = peopleServed;
        coreNodes[nodeId].lastReportTimestamp = block.timestamp;

        emit ImpactReportSubmitted(
            nodeId,
            peopleServed,
            servicesDelivered,
            block.number
        );
    }

    function approveImpactReport(
        string memory nodeId,
        uint256 reportIndex
    ) public onlyAdmin {
        require(reportIndex < nodeReports[nodeId].length, "Report not found");
        nodeReports[nodeId][reportIndex].daoApproved = true;
    }

    // ─── DEACTIVATION ───────────────────────────────────────────

    function deactivateNode(
        string memory nodeId,
        string memory reason
    ) public onlyAdmin {
        require(coreNodes[nodeId].active, "Node already inactive");

        coreNodes[nodeId].active = false;

        emit NodeDeactivated(nodeId, reason, block.number);
    }

    // ─── QUERIES ─────────────────────────────────────────────────

    function getNodeInfo(string memory nodeId)
        public
        view
        returns (CoreNode memory)
    {
        return coreNodes[nodeId];
    }

    function getNodeReportCount(string memory nodeId)
        public
        view
        returns (uint256)
    {
        return nodeReports[nodeId].length;
    }

    function getNodeReport(string memory nodeId, uint256 index)
        public
        view
        returns (ImpactReport memory)
    {
        require(index < nodeReports[nodeId].length, "Report not found");
        return nodeReports[nodeId][index];
    }

    function getTotalRewardsByType(string memory nodeType)
        public
        view
        returns (uint256)
    {
        uint256 total = 0;
        // In production: Iterate through all nodes and sum by type
        return total;
    }

    // ─── STATISTICS ──────────────────────────────────────────────

    function getRegistryStats() public view returns (
        uint256 totalNodes,
        uint256 totalRewardsDistributed,
        uint256 currentEpochStartBlock,
        uint256 coreNodeAllocationPercent
    ) {
        return (
            totalRegisteredNodes,
            totalRewardsDistributed,
            epoch3StartBlock,
            CORE_NODE_ALLOCATION
        );
    }
}
