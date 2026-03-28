package ecp

import (
	"strings"
	"testing"
)

func TestBuildMerkleRootSingle(t *testing.T) {
	root := BuildMerkleRoot([]string{"sha256:abc"})
	if root != "sha256:abc" {
		t.Errorf("Single hash should return itself, got %s", root)
	}
}

func TestBuildMerkleRootEmpty(t *testing.T) {
	root := BuildMerkleRoot(nil)
	if !strings.HasPrefix(root, "sha256:") {
		t.Errorf("Empty should return sha256 hash of 'empty', got %s", root)
	}
}

func TestBuildMerkleRootDeterministic(t *testing.T) {
	hashes := []string{"sha256:aaa", "sha256:bbb", "sha256:ccc"}
	a := BuildMerkleRoot(hashes)
	b := BuildMerkleRoot(hashes)
	if a != b {
		t.Error("Merkle root not deterministic")
	}
}

func TestBuildMerkleRootOrderDependent(t *testing.T) {
	// Order matters — no sorting. Different order = different root.
	a := BuildMerkleRoot([]string{"sha256:bbb", "sha256:aaa"})
	b := BuildMerkleRoot([]string{"sha256:aaa", "sha256:bbb"})
	if a == b {
		t.Error("Merkle root should be order-dependent (no sorting)")
	}
}

func TestVerifyMerkleRoot(t *testing.T) {
	hashes := []string{"sha256:aaa", "sha256:bbb"}
	root := BuildMerkleRoot(hashes)
	if !VerifyMerkleRoot(hashes, root) {
		t.Error("VerifyMerkleRoot should return true for correct root")
	}
	if VerifyMerkleRoot(hashes, "sha256:wrong") {
		t.Error("VerifyMerkleRoot should return false for wrong root")
	}
}

func TestComputeChainHash(t *testing.T) {
	r := Record{
		ECP: "1.0", ID: "rec_test", TS: 1000,
		Agent: "a", Action: "llm_call",
		InHash: "sha256:in", OutHash: "sha256:out",
	}
	h := ComputeChainHash(r)
	if h == "" {
		t.Error("Chain hash should not be empty")
	}
	// Deterministic
	if ComputeChainHash(r) != h {
		t.Error("Chain hash not deterministic")
	}
}
