package ecp

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
)

// ComputeChainHash computes the chain hash for a record.
// Matches Python SDK record.py compute_chain_hash():
// SHA-256 of canonical JSON of the full record, with chain.hash and sig zeroed.
// Uses map[string]interface{} so json.Marshal produces alphabetically sorted keys,
// matching Python's json.dumps(sort_keys=True) and TS's stableStringify().
func ComputeChainHash(r Record) string {
	// Build a map for alphabetically-sorted key output
	m := map[string]interface{}{
		"ecp":      r.ECP,
		"id":       r.ID,
		"ts":       r.TS,
		"agent":    r.Agent,
		"action":   r.Action,
		"in_hash":  r.InHash,
		"out_hash": r.OutHash,
		"sig":      "",
	}

	// Include meta if present (omit if nil)
	if r.Meta != nil {
		metaMap := map[string]interface{}{}
		if r.Meta.Model != "" {
			metaMap["model"] = r.Meta.Model
		}
		if r.Meta.TokensIn != 0 {
			metaMap["tokens_in"] = r.Meta.TokensIn
		}
		if r.Meta.TokensOut != 0 {
			metaMap["tokens_out"] = r.Meta.TokensOut
		}
		if r.Meta.LatencyMs != 0 {
			metaMap["latency_ms"] = r.Meta.LatencyMs
		}
		if r.Meta.CostUSD != 0 {
			metaMap["cost_usd"] = r.Meta.CostUSD
		}
		if len(r.Meta.Flags) > 0 {
			metaMap["flags"] = r.Meta.Flags
		}
		if len(metaMap) > 0 {
			m["meta"] = metaMap
		}
	}

	// Chain: always include with hash zeroed
	if r.Chain != nil {
		m["chain"] = map[string]interface{}{
			"prev": r.Chain.Prev,
			"hash": "",
		}
	}

	data, _ := json.Marshal(m)
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
		// Match Python/TS: sha256("empty") with sha256: prefix
		h := sha256.Sum256([]byte("empty"))
		return fmt.Sprintf("sha256:%x", h)
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
		return claimedRoot == BuildMerkleRoot(nil)
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
