// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title EvidenceAnchor — one Merkle root per scoring run, anchored on a public testnet.
/// @notice Build Spec v2 §C1. What this stores is a COMMITMENT, not a claim: no token, no DAO,
///         no on-chain scoring, and no raw or licensed data ever reaches the chain. A database's
///         operator can silently rewrite history; a hash anchored here cannot be re-written, so
///         our evidence trail becomes independently verifiable without trusting us.
/// @dev    Append-only by construction — `anchor()` reverts on a run id that already exists, so a
///         run can never be silently re-anchored with different evidence. That single `require`
///         IS the tamper-evidence story.
contract EvidenceAnchor {
    address public immutable signer;

    struct Anchor { bytes32 root; uint64 timestamp; }

    mapping(bytes32 => Anchor) public anchors;          // run_id => anchor

    event Anchored(bytes32 indexed runId, bytes32 root, uint64 timestamp);

    constructor() { signer = msg.sender; }

    function anchor(bytes32 runId, bytes32 root) external {
        require(msg.sender == signer, "not signer");
        require(anchors[runId].timestamp == 0, "run already anchored");   // append-only
        anchors[runId] = Anchor(root, uint64(block.timestamp));
        emit Anchored(runId, root, uint64(block.timestamp));
    }

    /// @notice Read side used by the verification page (public RPC, no wallet needed).
    function getAnchor(bytes32 runId) external view returns (bytes32 root, uint64 timestamp) {
        Anchor memory a = anchors[runId];
        return (a.root, a.timestamp);
    }
}
