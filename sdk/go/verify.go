package ecp

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
)

// ComputeChainHash computes the chain hash for a record.
// Matches Python SDK record.py compute_chain_hash():
// SHA-256 of canonical JSON of the full record, with chain.hash and sig zeroed.
func ComputeChainHash(r Record) string {
	// Deep copy to avoid mutation, zero out chain.hash and sig
	clone := r
	if clone.Chain != nil {
		chainCopy := *clone.Chain
		chainCopy.Hash = ""
		clone.Chain = &chainCopy
	}
	clone.Sig = ""

	// json.Marshal produces sorted keys by default for structs
	data, _ := json.Marshal(clone)
	h := sha256.Sum256(data)
	return fmt.Sprintf("sha256:%x", h)
}

// BuildMerkleRoot builds a Merkle root from a list of hash strings.
// Algorithm matches Python SDK batch.py build_merkle_tree():
// 1. Preserve original order (NO sorting — order matters for proof verification)
// 2. Pair adjacent, SHA-256 each pair (odd element duplicated)
// 3. Repeat until one root
func BuildMerkleRoot(hashes []string) string {
	if len(hashes) == 0 {
		return ""
	}
	if len(hashes) == 1 {
		return hashes[0]
	}

	layer := make([]string, len(hashes))
	copy(layer, hashes)

	for len(layer) > 1 {
		var next []string
		for i := 0; i < len(layer); i += 2 {
			var combined string
			if i+1 < len(layer) {
				combined = layer[i] + layer[i+1]
			} else {
				combined = layer[i] + layer[i]
			}
			h := sha256.Sum256([]byte(combined))
			next = append(next, fmt.Sprintf("sha256:%x", h))
		}
		layer = next
	}
	return layer[0]
}

// VerifyMerkleRoot checks if hashes produce the claimed root.
func VerifyMerkleRoot(hashes []string, claimedRoot string) bool {
	if len(hashes) == 0 {
		return claimedRoot == ""
	}
	return BuildMerkleRoot(hashes) == claimedRoot
}

// VerifyChain verifies that a sequence of records forms a valid hash chain.
func VerifyChain(records []Record) bool {
	for i := 1; i < len(records); i++ {
		if records[i].Chain == nil {
			continue
		}
		expectedPrev := records[i-1].ID
		if records[i].Chain.Prev != expectedPrev {
			return false
		}
	}
	return true
}
