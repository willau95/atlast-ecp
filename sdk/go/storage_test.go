package ecp

import (
	"os"
	"path/filepath"
	"testing"
)

func TestSaveAndLoadRecords(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "test.jsonl")

	r1 := NewMinimalRecord("agent-a", "llm_call", "hello", "world")
	r2 := NewMinimalRecord("agent-b", "tool_call", "query", "result")

	if err := SaveRecord(path, r1); err != nil {
		t.Fatalf("SaveRecord r1: %v", err)
	}
	if err := SaveRecord(path, r2); err != nil {
		t.Fatalf("SaveRecord r2: %v", err)
	}

	records, err := LoadRecords(path)
	if err != nil {
		t.Fatalf("LoadRecords: %v", err)
	}
	if len(records) != 2 {
		t.Fatalf("Expected 2 records, got %d", len(records))
	}
	if records[0].Agent != "agent-a" {
		t.Errorf("records[0].Agent = %s, want agent-a", records[0].Agent)
	}
	if records[1].Agent != "agent-b" {
		t.Errorf("records[1].Agent = %s, want agent-b", records[1].Agent)
	}
}

func TestLoadRecordsFileNotFound(t *testing.T) {
	records, err := LoadRecords("/nonexistent/path.jsonl")
	if err != nil {
		t.Fatalf("Expected nil error for missing file, got %v", err)
	}
	if records != nil {
		t.Errorf("Expected nil records, got %v", records)
	}
}

func TestLoadRecordsMalformedLines(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "test.jsonl")

	// Write a valid record + a malformed line
	r := NewMinimalRecord("a", "b", "c", "d")
	_ = SaveRecord(path, r)
	f, _ := os.OpenFile(path, os.O_APPEND|os.O_WRONLY, 0644)
	f.WriteString("this is not json\n")
	f.Close()

	records, err := LoadRecords(path)
	if err != nil {
		t.Fatalf("LoadRecords: %v", err)
	}
	// Should skip malformed line (fail-open)
	if len(records) != 1 {
		t.Errorf("Expected 1 valid record, got %d", len(records))
	}
}
