// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title NodeRewardPool
 * @notice Live reward pool funded by 5% of the burn allocation.
 *
 * Block reward distribution:
 *   80% -> Miners (existing)
 *   10% -> AI Services (existing)
 *    5% -> Active node replicas (this contract, node pool)
 *    5% -> ASICs by hashrate    (this contract, ASIC pool)
 *
 * Node types that can register:
 *   CHAIN_NODE      - Thronos blockchain replica node
 *   API_NODE_MEDICE - ThronomedICE API replica
 *   ASIC_MINER      - SHA256 ASIC via Stratum
 *   IOT_MINER       - IoT device miner (medical, parking...)
 *
 * Nodes must call heartbeat() every 24h to remain active.
 * Rewards accumulate per 24h epoch and are claimable anytime.
 */
contract NodeRewardPool {

    // ---------------------------------------------------------------
    // Types
    // ---------------------------------------------------------------

    enum NodeType { CHAIN_NODE, API_NODE_MEDICE, ASIC_MINER, IOT_MINER }

    struct NodeInfo {
        address  thrAddress;      // THR wallet that receives rewards
        NodeType nodeType;
        uint256  registeredAt;
        uint256  lastHeartbeat;
        uint256  hashrate;        // H/s for ASICs; 0 for others
        bool     isActive;
        string   nodeId;          // e.g. "thronos-node-1", "medice-api-railway-2"
        uint256  totalEarned;
    }

    struct Epoch {
        uint256 startTime;
        uint256 endTime;
        uint256 nodePoolAmount;   // 5% share for non-ASIC nodes
        uint256 asicPoolAmount;   // 5% share for ASIC miners
        uint256 totalActiveNodes;
        uint256 totalHashrate;
        bool    distributed;
    }

    // ---------------------------------------------------------------
    // Storage
    // ---------------------------------------------------------------

    address public owner;
    mapping(address => bool)   public authorizedServices;

    mapping(address => NodeInfo) public nodes;
    mapping(string  => address)  public nodeIdToAddress;
    address[] public registeredNodes;

    Epoch[]   public epochs;
    uint256   public currentEpochId;

    uint256 public constant EPOCH_DURATION    = 1 days;
    uint256 public constant HEARTBEAT_EXPIRY  = 24 hours;

    mapping(address => uint256) public pendingRewards;

    // ---------------------------------------------------------------
    // Events
    // ---------------------------------------------------------------

    event NodeRegistered(address indexed node, string nodeId, NodeType nodeType);
    event HeartbeatReceived(address indexed node, string nodeId);
    event HashrateUpdated(address indexed node, uint256 hashrate);
    event RewardDeposited(uint256 indexed epochId, uint256 nodeAmt, uint256 asicAmt);
    event EpochDistributed(uint256 indexed epochId, uint256 activeNodes, uint256 totalHashrate);
    event RewardClaimed(address indexed node, uint256 amount);
    event NodeDeactivated(address indexed node, string reason);
    event ServiceAuthorized(address service);

    // ---------------------------------------------------------------
    // Modifiers
    // ---------------------------------------------------------------

    modifier onlyOwner() {
        require(msg.sender == owner, "NRP: not owner");
        _;
    }

    modifier onlyService() {
        require(authorizedServices[msg.sender] || msg.sender == owner, "NRP: not authorized");
        _;
    }

    // ---------------------------------------------------------------
    // Constructor
    // ---------------------------------------------------------------

    constructor() {
        owner = msg.sender;
        authorizedServices[msg.sender] = true;
        _startNewEpoch();
    }

    // ---------------------------------------------------------------
    // Admin
    // ---------------------------------------------------------------

    function authorizeService(address svc) external onlyOwner {
        authorizedServices[svc] = true;
        emit ServiceAuthorized(svc);
    }

    function revokeService(address svc) external onlyOwner {
        authorizedServices[svc] = false;
    }

    // ---------------------------------------------------------------
    // Registration
    // ---------------------------------------------------------------

    /**
     * @notice Register this wallet as a node operator.
     * @param nodeId   Human-readable unique ID (e.g. "medice-api-railway-0")
     * @param nodeType Type from the NodeType enum
     * @param hashrate H/s for ASIC_MINER; pass 0 for other types
     */
    function registerNode(
        string  memory nodeId,
        NodeType nodeType,
        uint256 hashrate
    ) external {
        require(nodeIdToAddress[nodeId] == address(0), "NRP: nodeId taken");
        require(nodes[msg.sender].registeredAt == 0,    "NRP: address already registered");

        nodes[msg.sender] = NodeInfo({
            thrAddress:    msg.sender,
            nodeType:      nodeType,
            registeredAt:  block.timestamp,
            lastHeartbeat: block.timestamp,
            hashrate:      nodeType == NodeType.ASIC_MINER ? hashrate : 0,
            isActive:      true,
            nodeId:        nodeId,
            totalEarned:   0
        });

        nodeIdToAddress[nodeId] = msg.sender;
        registeredNodes.push(msg.sender);

        emit NodeRegistered(msg.sender, nodeId, nodeType);
    }

    // ---------------------------------------------------------------
    // Heartbeat
    // ---------------------------------------------------------------

    /**
     * @notice Node calls this to prove liveness. Must be called every 24h.
     */
    function heartbeat(string memory nodeId) external {
        address nodeAddr = nodeIdToAddress[nodeId];
        require(
            nodeAddr == msg.sender || authorizedServices[msg.sender],
            "NRP: not node owner"
        );
        _touch(nodeAddr);
        emit HeartbeatReceived(nodeAddr, nodeId);
    }

    /**
     * @notice Backend service calls this on behalf of a node (cron job).
     */
    function serviceHeartbeat(string memory nodeId) external onlyService {
        address nodeAddr = nodeIdToAddress[nodeId];
        require(nodeAddr != address(0), "NRP: unknown node");
        _touch(nodeAddr);
        emit HeartbeatReceived(nodeAddr, nodeId);
    }

    /**
     * @notice Stratum server updates ASIC hashrate each epoch.
     */
    function updateHashrate(address node, uint256 newHashrate) external onlyService {
        require(nodes[node].nodeType == NodeType.ASIC_MINER, "NRP: not ASIC");
        nodes[node].hashrate = newHashrate;
        emit HashrateUpdated(node, newHashrate);
    }

    // ---------------------------------------------------------------
    // Reward deposit (called by chain block reward logic)
    // ---------------------------------------------------------------

    /**
     * @notice Deposit the combined 10% burn-redirect into this contract.
     *         Half goes to node pool, half to ASIC pool.
     */
    function depositRewards() external payable onlyService {
        require(msg.value > 0, "NRP: zero value");
        uint256 nodeAmt = msg.value / 2;
        uint256 asicAmt = msg.value - nodeAmt;
        epochs[currentEpochId].nodePoolAmount += nodeAmt;
        epochs[currentEpochId].asicPoolAmount += asicAmt;
        emit RewardDeposited(currentEpochId, nodeAmt, asicAmt);
    }

    // ---------------------------------------------------------------
    // Epoch distribution (permissionless — anyone can trigger)
    // ---------------------------------------------------------------

    function distributeEpoch(uint256 epochId) external {
        require(epochId < epochs.length,     "NRP: bad epoch");
        Epoch storage epoch = epochs[epochId];
        require(!epoch.distributed,          "NRP: already distributed");
        require(block.timestamp >= epoch.endTime, "NRP: epoch not ended");

        _distributeNodePool(epochId);
        _distributeAsicPool(epochId);

        epoch.distributed = true;
        emit EpochDistributed(epochId, epoch.totalActiveNodes, epoch.totalHashrate);

        if (epochId == currentEpochId) {
            _startNewEpoch();
        }
    }

    function _distributeNodePool(uint256 epochId) internal {
        Epoch storage epoch = epochs[epochId];
        if (epoch.nodePoolAmount == 0) return;

        address[] memory active = new address[](registeredNodes.length);
        uint256 count;

        for (uint256 i; i < registeredNodes.length; i++) {
            NodeInfo storage n = nodes[registeredNodes[i]];
            if (!n.isActive || n.nodeType == NodeType.ASIC_MINER) continue;
            if (block.timestamp - n.lastHeartbeat > HEARTBEAT_EXPIRY) {
                n.isActive = false;
                emit NodeDeactivated(registeredNodes[i], "heartbeat expired");
                continue;
            }
            active[count++] = registeredNodes[i];
        }

        epoch.totalActiveNodes = count;
        if (count == 0) return;

        uint256 perNode = epoch.nodePoolAmount / count;
        for (uint256 i; i < count; i++) {
            pendingRewards[active[i]]   += perNode;
            nodes[active[i]].totalEarned += perNode;
        }
    }

    function _distributeAsicPool(uint256 epochId) internal {
        Epoch storage epoch = epochs[epochId];
        if (epoch.asicPoolAmount == 0) return;

        uint256 totalHash;
        for (uint256 i; i < registeredNodes.length; i++) {
            NodeInfo storage n = nodes[registeredNodes[i]];
            if (!n.isActive || n.nodeType != NodeType.ASIC_MINER) continue;
            if (block.timestamp - n.lastHeartbeat <= HEARTBEAT_EXPIRY) {
                totalHash += n.hashrate;
            }
        }

        epoch.totalHashrate = totalHash;
        if (totalHash == 0) return;

        for (uint256 i; i < registeredNodes.length; i++) {
            NodeInfo storage n = nodes[registeredNodes[i]];
            if (!n.isActive || n.nodeType != NodeType.ASIC_MINER || n.hashrate == 0) continue;
            if (block.timestamp - n.lastHeartbeat > HEARTBEAT_EXPIRY) continue;
            uint256 share = (epoch.asicPoolAmount * n.hashrate) / totalHash;
            pendingRewards[registeredNodes[i]]   += share;
            n.totalEarned                         += share;
        }
    }

    // ---------------------------------------------------------------
    // Claim
    // ---------------------------------------------------------------

    function claimRewards() external {
        uint256 amount = pendingRewards[msg.sender];
        require(amount > 0, "NRP: nothing to claim");
        pendingRewards[msg.sender] = 0;
        (bool ok,) = msg.sender.call{value: amount}("");
        require(ok, "NRP: transfer failed");
        emit RewardClaimed(msg.sender, amount);
    }

    // ---------------------------------------------------------------
    // View helpers
    // ---------------------------------------------------------------

    function getActiveNodeCounts() external view
        returns (uint256 chainNodes, uint256 medicNodes, uint256 asics, uint256 iotMiners)
    {
        for (uint256 i; i < registeredNodes.length; i++) {
            NodeInfo storage n = nodes[registeredNodes[i]];
            if (!n.isActive || block.timestamp - n.lastHeartbeat > HEARTBEAT_EXPIRY) continue;
            if (n.nodeType == NodeType.CHAIN_NODE)      chainNodes++;
            else if (n.nodeType == NodeType.API_NODE_MEDICE) medicNodes++;
            else if (n.nodeType == NodeType.ASIC_MINER)  asics++;
            else if (n.nodeType == NodeType.IOT_MINER)   iotMiners++;
        }
    }

    function getCurrentEpoch() external view returns (Epoch memory) {
        return epochs[currentEpochId];
    }

    function getPendingReward(address node) external view returns (uint256) {
        return pendingRewards[node];
    }

    function getNodeInfo(string memory nodeId) external view returns (NodeInfo memory) {
        return nodes[nodeIdToAddress[nodeId]];
    }

    // ---------------------------------------------------------------
    // Internal
    // ---------------------------------------------------------------

    function _touch(address nodeAddr) internal {
        NodeInfo storage n = nodes[nodeAddr];
        require(n.isActive, "NRP: node inactive");
        n.lastHeartbeat = block.timestamp;
    }

    function _startNewEpoch() internal {
        currentEpochId = epochs.length;
        epochs.push(Epoch({
            startTime:        block.timestamp,
            endTime:          block.timestamp + EPOCH_DURATION,
            nodePoolAmount:   0,
            asicPoolAmount:   0,
            totalActiveNodes: 0,
            totalHashrate:    0,
            distributed:      false
        }));
    }

    receive() external payable {}
}
