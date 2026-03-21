package ecp

import "testing"

func TestHashContent(t *testing.T) {
	// Must match Python SDK: hash_content("hello") output
	got := HashContent("hello")
	want := "sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
	if got != want {
		t.Errorf("HashContent(\"hello\") = %s, want %s", got, want)
	}
}

func TestHashContentEmpty(t *testing.T) {
	got := HashContent("")
	want := "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
	if got != want {
		t.Errorf("HashContent(\"\") = %s, want %s", got, want)
	}
}

func TestHashContentDeterministic(t *testing.T) {
	a := HashContent("test input")
	b := HashContent("test input")
	if a != b {
		t.Errorf("HashContent not deterministic: %s != %s", a, b)
	}
}

func TestHashContentDifferentInputs(t *testing.T) {
	a := HashContent("input a")
	b := HashContent("input b")
	if a == b {
		t.Error("Different inputs produced same hash")
	}
}
