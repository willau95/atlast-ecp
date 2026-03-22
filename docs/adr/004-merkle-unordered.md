# ADR-004: Unordered Merkle Tree

**Status:** Accepted  
**Date:** 2026-03-18  
**Decision Makers:** Atlas

## Context

ECP batches aggregate multiple records into a Merkle tree, with the root anchored on-chain. Records within a batch may arrive out of order (network latency, concurrent agents). Should the Merkle tree enforce ordering?

## Decision

**Merkle tree does NOT sort leaf hashes before construction.**

Leaves are added in arrival order. The same set of records in different order produces a different Merkle root. This is acceptable because:

1. A batch is produced by a single SDK instance with deterministic ordering.
2. The batch is signed (`sig` field) by the agent's Ed25519 key, binding the exact Merkle root.
3. Verification checks `record_hash ∈ Merkle tree` (inclusion proof), not tree equivalence.

## Consequences

- **Simplicity**: No sorting step needed. O(n) tree construction.
- **Deterministic per-SDK**: Same SDK session always produces the same Merkle root for the same records.
- **Trade-off**: Two different SDK instances with the same records would produce different roots. This is fine — they are different batches with different signatures.
- **Inclusion proofs**: `verify_merkle_proof(record_hash, proof, root)` works regardless of ordering.

## Alternatives Considered

1. **Sort leaves before tree construction**: Guarantees canonical root for any record set. Rejected — adds O(n log n) cost, and "same records = same root" is not a requirement (batches are per-session, not per-agent).
2. **Append-only log (no tree)**: Simpler but no O(log n) inclusion proofs. Rejected — Merkle proofs are essential for efficient verification.
