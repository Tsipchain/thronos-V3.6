// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/**
 * @title PropertySeal
 * @notice Digital seals for real estate properties on Thronoschain
 * @dev Creates immutable, timestamped records of property ownership and metadata
 */

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/Counters.sol";

contract PropertySeal is ERC721, Ownable {
    using Counters for Counters.Counter;

    Counters.Counter private _sealIdCounter;

    struct Seal {
        uint256 sealId;
        string propertyId;
        string propertyName;
        string location;
        address owner;
        bytes32 dataHash;
        uint256 timestamp;
        uint256 blockNumber;
        bool verified;
        string ipfsHash;
    }

    struct PropertyRecord {
        string propertyId;
        address owner;
        uint256 totalSeals;
        uint256 lastSealTime;
        bool exists;
    }

    // Mappings
    mapping(uint256 => Seal) public seals;
    mapping(string => PropertyRecord) public properties;
    mapping(uint256 => bytes32[]) public sealHistory;
    mapping(address => uint256[]) public ownerSeals;

    // Events
    event SealCreated(
        uint256 indexed sealId,
        string indexed propertyId,
        address indexed owner,
        bytes32 dataHash,
        uint256 timestamp
    );

    event SealVerified(
        uint256 indexed sealId,
        bytes32 dataHash,
        uint256 blockNumber
    );

    event PropertyRegistered(
        string indexed propertyId,
        address indexed owner,
        uint256 timestamp
    );

    event SealUpdated(
        uint256 indexed sealId,
        string propertyId,
        bytes32 newHash,
        uint256 timestamp
    );

    constructor() ERC721("THRONOS PropertySeal", "SEAL") {}

    /**
     * @notice Create a new digital seal for a property
     * @param propertyId Unique property identifier
     * @param propertyName Name of the property
     * @param location Property location
     * @param dataHash Keccak256 hash of property metadata
     * @param ipfsHash IPFS hash of property documents
     */
    function createSeal(
        string memory propertyId,
        string memory propertyName,
        string memory location,
        bytes32 dataHash,
        string memory ipfsHash
    ) public returns (uint256) {
        require(bytes(propertyId).length > 0, "Property ID required");
        require(msg.sender != address(0), "Invalid sender");

        _sealIdCounter.increment();
        uint256 sealId = _sealIdCounter.current();

        Seal memory newSeal = Seal({
            sealId: sealId,
            propertyId: propertyId,
            propertyName: propertyName,
            location: location,
            owner: msg.sender,
            dataHash: dataHash,
            timestamp: block.timestamp,
            blockNumber: block.number,
            verified: true,
            ipfsHash: ipfsHash
        });

        seals[sealId] = newSeal;
        sealHistory[sealId].push(dataHash);
        ownerSeals[msg.sender].push(sealId);

        // Register property if not exists
        if (!properties[propertyId].exists) {
            properties[propertyId] = PropertyRecord({
                propertyId: propertyId,
                owner: msg.sender,
                totalSeals: 1,
                lastSealTime: block.timestamp,
                exists: true
            });
            emit PropertyRegistered(propertyId, msg.sender, block.timestamp);
        } else {
            properties[propertyId].totalSeals++;
            properties[propertyId].lastSealTime = block.timestamp;
        }

        // Mint NFT as proof
        _safeMint(msg.sender, sealId);

        emit SealCreated(sealId, propertyId, msg.sender, dataHash, block.timestamp);
        return sealId;
    }

    /**
     * @notice Verify a seal's authenticity
     * @param sealId ID of the seal to verify
     */
    function verifySeal(uint256 sealId) public view returns (bool, bytes32, uint256) {
        require(sealId > 0 && sealId <= _sealIdCounter.current(), "Invalid seal ID");

        Seal storage seal = seals[sealId];
        return (seal.verified, seal.dataHash, seal.blockNumber);
    }

    /**
     * @notice Update property seal with new data
     * @param sealId ID of the seal to update
     * @param newDataHash New data hash
     */
    function updateSeal(uint256 sealId, bytes32 newDataHash) public {
        require(sealId > 0 && sealId <= _sealIdCounter.current(), "Invalid seal ID");
        require(seals[sealId].owner == msg.sender, "Only seal owner can update");

        Seal storage seal = seals[sealId];
        seal.dataHash = newDataHash;
        seal.timestamp = block.timestamp;
        seal.blockNumber = block.number;

        sealHistory[sealId].push(newDataHash);

        emit SealUpdated(sealId, seal.propertyId, newDataHash, block.timestamp);
    }

    /**
     * @notice Get complete seal information
     * @param sealId ID of the seal
     */
    function getSeal(uint256 sealId)
        public
        view
        returns (Seal memory)
    {
        require(sealId > 0 && sealId <= _sealIdCounter.current(), "Invalid seal ID");
        return seals[sealId];
    }

    /**
     * @notice Get all seals for a property
     * @param propertyId Property identifier
     */
    function getPropertySeals(string memory propertyId)
        public
        view
        returns (uint256[] memory)
    {
        PropertyRecord memory prop = properties[propertyId];
        require(prop.exists, "Property not found");

        uint256[] memory result = new uint256[](prop.totalSeals);
        uint256 count = 0;

        for (uint256 i = 1; i <= _sealIdCounter.current(); i++) {
            if (
                keccak256(abi.encodePacked(seals[i].propertyId)) ==
                keccak256(abi.encodePacked(propertyId))
            ) {
                result[count] = i;
                count++;
            }
        }

        return result;
    }

    /**
     * @notice Get seal history (all data hash changes)
     * @param sealId ID of the seal
     */
    function getSealHistory(uint256 sealId)
        public
        view
        returns (bytes32[] memory)
    {
        require(sealId > 0 && sealId <= _sealIdCounter.current(), "Invalid seal ID");
        return sealHistory[sealId];
    }

    /**
     * @notice Get owner's seals
     * @param owner Address of seal owner
     */
    function getOwnerSeals(address owner) public view returns (uint256[] memory) {
        return ownerSeals[owner];
    }

    /**
     * @notice Get total number of seals created
     */
    function getTotalSeals() public view returns (uint256) {
        return _sealIdCounter.current();
    }

    /**
     * @notice Verify merkle proof against seal data
     * @param sealId Seal ID
     * @param leaf Merkle leaf
     * @param proof Merkle proof
     */
    function verifyMerkleProof(
        uint256 sealId,
        bytes32 leaf,
        bytes32[] memory proof
    ) public view returns (bool) {
        require(sealId > 0 && sealId <= _sealIdCounter.current(), "Invalid seal ID");

        bytes32 computedHash = leaf;
        for (uint256 i = 0; i < proof.length; i++) {
            bytes32 proofElement = proof[i];
            if (computedHash <= proofElement) {
                computedHash = keccak256(abi.encodePacked(computedHash, proofElement));
            } else {
                computedHash = keccak256(abi.encodePacked(proofElement, computedHash));
            }
        }

        return computedHash == seals[sealId].dataHash;
    }
}
