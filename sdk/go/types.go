// Package ecp provides the ATLAST Evidence Chain Protocol SDK for Go.
//
// Create, store, and verify ECP records locally.
// Privacy by design: only SHA-256 hashes leave the device.
package ecp

// Record represents an ECP v1.0 flat-format record.
type Record struct {
	ECP     string `json:"ecp"`
	ID      string `json:"id"`
	TS      int64  `json:"ts"`
	Agent   string `json:"agent"`
	Action  string `json:"action"`
	InHash  string `json:"in_hash"`
	OutHash string `json:"out_hash"`
	Meta    *Meta  `json:"meta,omitempty"`
	Chain   *Chain `json:"chain,omitempty"`
	Sig     string `json:"sig,omitempty"`
}

// Meta contains optional metadata (Level 2).
type Meta struct {
	Model     string   `json:"model,omitempty"`
	TokensIn  int      `json:"tokens_in,omitempty"`
	TokensOut int      `json:"tokens_out,omitempty"`
	LatencyMs int      `json:"latency_ms,omitempty"`
	CostUSD   float64  `json:"cost_usd,omitempty"`
	Flags     []string `json:"flags,omitempty"`
}

// Chain contains chaining fields (Level 3).
type Chain struct {
	Prev string `json:"prev"`
	Hash string `json:"hash"`
}
