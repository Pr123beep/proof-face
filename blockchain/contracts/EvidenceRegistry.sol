// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title ProofFace Evidence Registry
/// @notice Anchors a cryptographic fingerprint of a discovered social post.
contract EvidenceRegistry {
    struct Evidence {
        bytes32 sourceHash;
        string sourceUrl;
        uint64 anchoredAt;
        address submitter;
    }

    mapping(bytes32 => Evidence) private records;

    event EvidenceAnchored(
        bytes32 indexed evidenceHash,
        bytes32 indexed sourceHash,
        string sourceUrl,
        uint64 anchoredAt,
        address indexed submitter
    );

    function anchor(
        bytes32 evidenceHash,
        bytes32 sourceHash,
        string calldata sourceUrl
    ) external {
        require(evidenceHash != bytes32(0), "empty evidence hash");
        require(sourceHash != bytes32(0), "empty source hash");
        require(records[evidenceHash].anchoredAt == 0, "evidence already anchored");

        uint64 timestamp = uint64(block.timestamp);
        records[evidenceHash] = Evidence(sourceHash, sourceUrl, timestamp, msg.sender);
        emit EvidenceAnchored(evidenceHash, sourceHash, sourceUrl, timestamp, msg.sender);
    }

    function verify(
        bytes32 evidenceHash,
        bytes32 expectedSourceHash,
        string calldata expectedSourceUrl
    ) external view returns (bool) {
        Evidence memory item = records[evidenceHash];
        return item.anchoredAt != 0
            && item.sourceHash == expectedSourceHash
            && keccak256(bytes(item.sourceUrl)) == keccak256(bytes(expectedSourceUrl));
    }

    function getEvidence(bytes32 evidenceHash)
        external
        view
        returns (bytes32 sourceHash, string memory sourceUrl, uint64 anchoredAt, address submitter)
    {
        Evidence memory item = records[evidenceHash];
        return (item.sourceHash, item.sourceUrl, item.anchoredAt, item.submitter);
    }
}
