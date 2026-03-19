package ecp

import (
	"strings"
	"testing"
)

func TestNewMinimalRecord(t *testing.T) {
	r := NewMinimalRecord("my-agent", "llm_call", "hello", "world")

	if r.ECP != "1.0" {
		t.Errorf("ECP = %s, want 1.0", r.ECP)
	}
	if !strings.HasPrefix(r.ID, "rec_") {
		t.Errorf("ID should start with rec_, got %s", r.ID)
	}
	if len(r.ID) != 20 { // rec_ + 16 hex
		t.Errorf("ID length = %d, want 20", len(r.ID))
	}
	if r.Agent != "my-agent" {
		t.Errorf("Agent = %s, want my-agent", r.Agent)
	}
	if r.Action != "llm_call" {
		t.Errorf("Action = %s, want llm_call", r.Action)
	}
	if !strings.HasPrefix(r.InHash, "sha256:") {
		t.Errorf("InHash should start with sha256:, got %s", r.InHash)
	}
	if !strings.HasPrefix(r.OutHash, "sha256:") {
		t.Errorf("OutHash should start with sha256:, got %s", r.OutHash)
	}
	if r.TS <= 0 {
		t.Error("TS should be positive")
	}
}

func TestNewRecord(t *testing.T) {
	meta := &Meta{Model: "gpt-4", LatencyMs: 500}
	r := NewRecord("agent", "llm_call", "in", "out", meta)
	if r.Meta == nil {
		t.Error("Meta should not be nil")
	}
	if r.Meta.Model != "gpt-4" {
		t.Errorf("Meta.Model = %s, want gpt-4", r.Meta.Model)
	}
}

func TestRecordIDUniqueness(t *testing.T) {
	ids := make(map[string]bool)
	for i := 0; i < 100; i++ {
		r := NewMinimalRecord("a", "b", "c", "d")
		if ids[r.ID] {
			t.Errorf("Duplicate ID: %s", r.ID)
		}
		ids[r.ID] = true
	}
}
