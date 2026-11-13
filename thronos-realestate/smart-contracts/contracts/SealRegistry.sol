// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/**
 * @title SealRegistry
 * @notice Registry of all property seals for bulk verification
 */

contract SealRegistry {
    struct SealEntry {
        uint256 sealId;
        string propertyId;
        address propertyOwner;
        bytes32 dataHash;
        uint256 sealTimestamp;
        bool isVerified;
    }

    mapping(bytes32 => SealEntry) public sealRegistry;
    mapping(string => bytes32[]) public propertyToSeals;
    bytes32[] public allSeals;

    event SealRegistered(bytes32 indexed sealHash, uint256 sealId, string propertyId);
    event SealVerificationUpdated(bytes32 indexed sealHash, bool isVerified);

    function registerSeal(
        uint256 sealId,
        string memory propertyId,
        address propertyOwner,
        bytes32 dataHash
    ) public returns (bytes32) {
        bytes32 sealHash = keccak256(
            abi.encodePacked(sealId, propertyId, propertyOwner, block.timestamp)
        );

        sealRegistry[sealHash] = SealEntry({
            sealId: sealId,
            propertyId: propertyId,
            propertyOwner: propertyOwner,
            dataHash: dataHash,
            sealTimestamp: block.timestamp,
            isVerified: true
        });

        propertyToSeals[propertyId].push(sealHash);
        allSeals.push(sealHash);

        emit SealRegistered(sealHash, sealId, propertyId);
        return sealHash;
    }

    function verifySealHash(bytes32 sealHash)
        public
        view
        returns (bool isValid, SealEntry memory entry)
    {
        SealEntry memory sealData = sealRegistry[sealHash];
        return (sealData.isVerified, sealData);
    }

    function getPropertySeals(string memory propertyId)
        public
        view
        returns (bytes32[] memory)
    {
        return propertyToSeals[propertyId];
    }

    function getAllSeals() public view returns (bytes32[] memory) {
        return allSeals;
    }

    function getTotalSeals() public view returns (uint256) {
        return allSeals.length;
    }
}
