package ecp

import (
	"crypto/rand"
	"encoding/hex"
	"time"
)

// NewMinimalRecord creates a Level 1 ECP v1.0 record.
// This is the minimum valid ECP record: 7 fields.
func NewMinimalRecord(agent, action, input, output string) Record {
	return Record{
		ECP:     "1.0",
		ID:      generateRecordID(),
		TS:      time.Now().UnixMilli(),
		Agent:   agent,
		Action:  action,
		InHash:  HashContent(input),
		OutHash: HashContent(output),
	}
}

// NewRecord creates a Level 2 ECP record with metadata.
func NewRecord(agent, action, input, output string, meta *Meta) Record {
	r := NewMinimalRecord(agent, action, input, output)
	r.Meta = meta
	return r
}

// generateRecordID returns "rec_" + 16 hex chars (matches Python SDK).
func generateRecordID() string {
	b := make([]byte, 8)
	_, _ = rand.Read(b)
	return "rec_" + hex.EncodeToString(b)
}
