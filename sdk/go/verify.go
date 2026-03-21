package ecp

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"sort"
)

// ComputeChainHash computes the chain hash for a record.
// Matches Python SDK record.py compute_chain_hash().
func ComputeChainHash(r Record) string {
	// Canonical JSON: sorted keys, no extra whitespace
	canonical := map[string]interface{}{
		"ecp":      r.ECP,
		"id":       r.ID,
		"ts":       r.TS,
		"agent":    r.Agent,
		"action":   r.Action,
		"in_hash":  r.InHash,
		"out_hash": r.OutHash,
	}
	data, _ := json.Marshal(canonical)
	h := sha256.Sum256(data)
	return fmt.Sprintf("sha256:%x", h)
}

// BuildMerkleRoot builds a Merkle root from a list of hash strings.
// Algorithm matches Python SDK verify.py build_merkle_root():
// 1. Sort hashes lexicographically
// 2. Pair adjacent, SHA-256 each pair
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
	sort.Strings(layer)

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
