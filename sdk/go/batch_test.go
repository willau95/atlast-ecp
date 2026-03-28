package ecp

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestBuildBatchEmpty(t *testing.T) {
	b := BuildBatch(nil)
	if b.RecordCount != 0 {
		t.Errorf("empty batch record count: want 0, got %d", b.RecordCount)
	}
	if !strings.HasPrefix(b.MerkleRoot, "sha256:") {
		t.Errorf("empty batch merkle root should be sha256 hash, got %q", b.MerkleRoot)
	}
	if !strings.HasPrefix(b.ID, "batch_") {
		t.Errorf("batch ID should start with 'batch_', got %q", b.ID)
	}
	if len(b.ID) != len("batch_")+16 {
		t.Errorf("batch ID should be 'batch_' + 16 hex chars, got len=%d", len(b.ID))
	}
	if b.CreatedAt == 0 {
		t.Error("CreatedAt should be set")
	}
}

func TestBuildBatchSingle(t *testing.T) {
	r := NewMinimalRecord("agent", "llm_call", "input", "output")
	b := BuildBatch([]Record{r})

	if b.RecordCount != 1 {
		t.Errorf("want RecordCount=1, got %d", b.RecordCount)
	}
	if len(b.RecordHashes) != 1 {
		t.Errorf("want 1 record hash, got %d", len(b.RecordHashes))
	}
	if !strings.HasPrefix(b.RecordHashes[0].Hash, "sha256:") {
		t.Errorf("record hash should start with 'sha256:', got %q", b.RecordHashes[0].Hash)
	}
	// Single record: merkle root == the hash itself
	if b.MerkleRoot != b.RecordHashes[0].Hash {
		t.Errorf("single-record merkle root should equal the record hash")
	}
}

func TestBuildBatchMultiple(t *testing.T) {
	records := []Record{
		NewMinimalRecord("a", "call", "i1", "o1"),
		NewMinimalRecord("a", "call", "i2", "o2"),
		NewMinimalRecord("a", "call", "i3", "o3"),
	}
	b := BuildBatch(records)

	if b.RecordCount != 3 {
		t.Errorf("want RecordCount=3, got %d", b.RecordCount)
	}
	if len(b.RecordHashes) != 3 {
		t.Errorf("want 3 record hashes, got %d", len(b.RecordHashes))
	}
	if !strings.HasPrefix(b.MerkleRoot, "sha256:") {
		t.Errorf("merkle root should start with 'sha256:', got %q", b.MerkleRoot)
	}
	// Verify root matches what BuildMerkleRoot would produce
	hashes := make([]string, len(b.RecordHashes))
	for i, e := range b.RecordHashes {
		hashes[i] = e.Hash
	}
	expected := BuildMerkleRoot(hashes)
	if b.MerkleRoot != expected {
		t.Errorf("MerkleRoot mismatch: want %q, got %q", expected, b.MerkleRoot)
	}
}

func TestBuildBatchUsesChainHash(t *testing.T) {
	r := NewMinimalRecord("a", "call", "in", "out")
	chainHash := "sha256:deadbeef" + strings.Repeat("0", 56)
	r.Chain = &Chain{Prev: "", Hash: chainHash}

	b := BuildBatch([]Record{r})
	if b.RecordHashes[0].Hash != chainHash {
		t.Errorf("should use chain.hash when present: want %q, got %q", chainHash, b.RecordHashes[0].Hash)
	}
}

func TestBuildBatchFallsBackToComputedHash(t *testing.T) {
	r := NewMinimalRecord("a", "call", "in", "out")
	// No chain field
	b := BuildBatch([]Record{r})
	expected := ComputeChainHash(r)
	if b.RecordHashes[0].Hash != expected {
		t.Errorf("should fall back to ComputeChainHash: want %q, got %q", expected, b.RecordHashes[0].Hash)
	}
}

func TestBuildBatchRecordHashEntryFields(t *testing.T) {
	r := NewMinimalRecord("a", "call", "in", "out")
	r.Meta = &Meta{Flags: []string{"hedged", "retried"}}
	b := BuildBatch([]Record{r})

	entry := b.RecordHashes[0]
	if entry.ID != r.ID {
		t.Errorf("entry ID: want %q, got %q", r.ID, entry.ID)
	}
	if len(entry.Flags) != 2 {
		t.Errorf("entry Flags: want 2, got %d", len(entry.Flags))
	}
}

func TestBuildBatchUniqueIDs(t *testing.T) {
	b1 := BuildBatch(nil)
	b2 := BuildBatch(nil)
	if b1.ID == b2.ID {
		t.Error("batch IDs should be unique")
	}
}

func TestUploadBatchSuccess(t *testing.T) {
	var received map[string]interface{}
	var receivedKey string

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/batches" || r.Method != http.MethodPost {
			http.Error(w, "not found", http.StatusNotFound)
			return
		}
		receivedKey = r.Header.Get("X-API-Key")
		_ = json.NewDecoder(r.Body).Decode(&received)
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"status":"ok"}`))
	}))
	defer srv.Close()

	records := []Record{
		NewMinimalRecord("agent", "llm_call", "hello", "world"),
	}
	batch := BuildBatch(records)

	if err := UploadBatch(srv.URL+"/v1", "my-key", "did:ecp:test", "ed25519:testsig", batch); err != nil {
		t.Fatalf("UploadBatch error: %v", err)
	}

	if receivedKey != "my-key" {
		t.Errorf("X-API-Key header: want %q, got %q", "my-key", receivedKey)
	}
	if received["merkle_root"] != batch.MerkleRoot {
		t.Errorf("merkle_root mismatch in payload")
	}
	if int(received["record_count"].(float64)) != batch.RecordCount {
		t.Errorf("record_count mismatch in payload")
	}
}

func TestUploadBatchNoAPIKey(t *testing.T) {
	var receivedKey string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedKey = r.Header.Get("X-API-Key")
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	batch := BuildBatch(nil)
	if err := UploadBatch(srv.URL+"/v1", "", "did:ecp:test", "ed25519:sig", batch); err != nil {
		t.Fatalf("UploadBatch error: %v", err)
	}
	if receivedKey != "" {
		t.Errorf("X-API-Key should be absent when empty, got %q", receivedKey)
	}
}

func TestUploadBatchHTTPError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
	}))
	defer srv.Close()

	batch := BuildBatch(nil)
	err := UploadBatch(srv.URL+"/v1", "bad-key", "did:ecp:test", "ed25519:sig", batch)
	if err == nil {
		t.Error("expected error for HTTP 401")
	}
}

func TestUploadBatchConnectionError(t *testing.T) {
	batch := BuildBatch(nil)
	err := UploadBatch("http://127.0.0.1:1", "", "did:ecp:test", "ed25519:sig", batch)
	if err == nil {
		t.Error("expected error for connection refused")
	}
}
