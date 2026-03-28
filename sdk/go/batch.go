package ecp

import (
	"bytes"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// Batch represents a batch of ECP records ready for upload.
type Batch struct {
	ID           string   `json:"id"`
	MerkleRoot   string   `json:"merkle_root"`
	RecordCount  int      `json:"record_count"`
	RecordHashes []string `json:"record_hashes"`
	CreatedAt    int64    `json:"created_at"`
}

// BuildBatch creates a Batch from a slice of records.
// The MerkleRoot is computed from each record's chain hash (or computed hash if chain is absent).
func BuildBatch(records []Record) Batch {
	hashes := make([]string, 0, len(records))
	for _, r := range records {
		h := ""
		if r.Chain != nil && r.Chain.Hash != "" {
			h = r.Chain.Hash
		} else {
			h = ComputeChainHash(r)
		}
		hashes = append(hashes, h)
	}

	root := BuildMerkleRoot(hashes)

	b := make([]byte, 8)
	_, _ = rand.Read(b)

	return Batch{
		ID:           "batch_" + hex.EncodeToString(b),
		MerkleRoot:   root,
		RecordCount:  len(records),
		RecordHashes: hashes,
		CreatedAt:    time.Now().UnixMilli(),
	}
}

// UploadBatch POSTs a batch to the ATLAST API.
// apiURL should be the full versioned base URL, e.g. "https://api.weba0.com/v1".
// apiKey is sent as X-API-Key header (omitted if empty).
// agentDID and sig are required by the server.
func UploadBatch(apiURL, apiKey, agentDID, sig string, batch Batch) error {
	payload, err := json.Marshal(map[string]interface{}{
		"merkle_root":   batch.MerkleRoot,
		"agent_did":     agentDID,
		"record_count":  batch.RecordCount,
		"record_hashes": batch.RecordHashes,
		"batch_ts":      batch.CreatedAt,
		"sig":           sig,
		"ecp_version":   "0.1",
	})
	if err != nil {
		return err
	}

	req, err := http.NewRequest(http.MethodPost, apiURL+"/batches", bytes.NewReader(payload))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	if apiKey != "" {
		req.Header.Set("X-API-Key", apiKey)
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	io.Copy(io.Discard, resp.Body) //nolint

	if resp.StatusCode >= 400 {
		return fmt.Errorf("upload failed: HTTP %d", resp.StatusCode)
	}
	return nil
}
