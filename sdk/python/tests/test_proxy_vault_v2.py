"""
Tests for Proxy Vault v2 — smart content extraction.

Verifies:
1. Only new user message stored as input (not full history)
2. System prompt stored only on first call / when changed
3. full_request_hash present for audit verification
4. Full response always stored completely
5. Backward compat: non-chat requests store full body
6. Multimodal messages: text extracted correctly
"""

import json
import hashlib
import threading

import pytest


# ─── _extract_new_content tests ──────────────────────────────────────────────

class TestExtractNewContent:
    """Test the proxy's message extraction logic."""

    def setup_method(self):
        """Reset session tracking between tests."""
        from atlast_ecp.proxy import _session_system_prompts, _session_lock
        with _session_lock:
            _session_system_prompts.clear()

    def _make_request(self, messages, model="gpt-4o"):
        return json.dumps({
            "model": model,
            "messages": messages,
            "max_tokens": 4096,
        }).encode("utf-8")

    def test_single_user_message(self):
        """First message: input = user content, system prompt stored."""
        from atlast_ecp.proxy import _extract_new_content

        req = self._make_request([
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is 2+2?"},
        ])

        result = _extract_new_content(req, "openai")

        assert result["input"] == "What is 2+2?"
        assert result["system_prompt"] == "You are a helpful assistant."
        assert result["context_messages_count"] == 2
        assert result["full_request_hash"].startswith("sha256:")
        assert result["session_id"].startswith("sess_")

    def test_multi_turn_only_last_user(self):
        """Multi-turn: input = only the LAST user message."""
        from atlast_ecp.proxy import _extract_new_content

        req = self._make_request([
            {"role": "system", "content": "You are a research agent."},
            {"role": "user", "content": "What is TSMC's revenue?"},
            {"role": "assistant", "content": "TSMC Q4 revenue was $25.1B."},
            {"role": "user", "content": "Compare with Samsung."},
            {"role": "assistant", "content": "Samsung was $21.3B."},
            {"role": "user", "content": "Now write a summary of both."},
        ])

        result = _extract_new_content(req, "openai")

        # Input should be ONLY the last user message
        assert result["input"] == "Now write a summary of both."
        # NOT the full request body
        assert "TSMC" not in result["input"]
        assert "Samsung" not in result["input"]
        # 6 messages total
        assert result["context_messages_count"] == 6

    def test_system_prompt_dedup_same_session(self):
        """System prompt stored on first call, not on subsequent calls."""
        from atlast_ecp.proxy import _extract_new_content

        system = "You are a research agent."

        # First call
        req1 = self._make_request([
            {"role": "system", "content": system},
            {"role": "user", "content": "Hello"},
        ])
        r1 = _extract_new_content(req1, "openai")
        assert r1["system_prompt"] == system  # stored

        # Second call (same system prompt)
        req2 = self._make_request([
            {"role": "system", "content": system},
            {"role": "user", "content": "Hello again"},
        ])
        r2 = _extract_new_content(req2, "openai")
        assert r2["system_prompt"] is None  # NOT stored again (dedup)
        assert r2["session_id"] == r1["session_id"]  # same session

    def test_system_prompt_change_detected(self):
        """If system prompt changes, store the new one."""
        from atlast_ecp.proxy import _extract_new_content

        req1 = self._make_request([
            {"role": "system", "content": "You are a research agent."},
            {"role": "user", "content": "Hello"},
        ])
        r1 = _extract_new_content(req1, "openai")
        assert r1["system_prompt"] == "You are a research agent."

        # Different system prompt
        req2 = self._make_request([
            {"role": "system", "content": "You are a code reviewer."},
            {"role": "user", "content": "Review this PR"},
        ])
        r2 = _extract_new_content(req2, "openai")
        assert r2["system_prompt"] == "You are a code reviewer."  # stored (changed)
        assert r2["session_id"] != r1["session_id"]  # different session

    def test_full_request_hash_integrity(self):
        """full_request_hash matches actual SHA-256 of request body."""
        from atlast_ecp.proxy import _extract_new_content

        req = self._make_request([
            {"role": "user", "content": "Test"},
        ])

        result = _extract_new_content(req, "openai")

        expected_hash = "sha256:" + hashlib.sha256(req).hexdigest()
        assert result["full_request_hash"] == expected_hash

    def test_no_messages_array_stores_full_body(self):
        """Non-chat requests (embeddings, etc.) store full body."""
        from atlast_ecp.proxy import _extract_new_content

        req = json.dumps({
            "model": "text-embedding-3-small",
            "input": "Hello world",
        }).encode("utf-8")

        result = _extract_new_content(req, "openai")

        # Falls back to full body since no messages array
        assert "Hello world" in result["input"]
        assert result["context_messages_count"] == 0

    def test_invalid_json_stores_full_body(self):
        """Invalid JSON falls back gracefully."""
        from atlast_ecp.proxy import _extract_new_content

        req = b"not valid json"
        result = _extract_new_content(req, "openai")

        assert result["input"] == "not valid json"
        assert result["full_request_hash"].startswith("sha256:")

    def test_multimodal_text_extraction(self):
        """Multimodal messages: extract text parts only."""
        from atlast_ecp.proxy import _extract_new_content

        req = self._make_request([
            {"role": "user", "content": [
                {"type": "text", "text": "What is in this image?"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc123"}},
            ]},
        ])

        result = _extract_new_content(req, "openai")
        assert result["input"] == "What is in this image?"

    def test_no_user_message(self):
        """Edge case: only system message, no user message."""
        from atlast_ecp.proxy import _extract_new_content

        req = self._make_request([
            {"role": "system", "content": "You are a test."},
        ])

        result = _extract_new_content(req, "openai")
        # Falls back to full body since no user message found
        assert "You are a test" in result["input"]


# ─── save_vault_v2 tests ────────────────────────────────────────────────────

class TestSaveVaultV2:
    """Test vault v2 storage format."""

    def test_vault_v2_with_extra(self, tmp_path, monkeypatch):
        """Vault v2 includes audit metadata."""
        monkeypatch.setenv("ECP_DIR", str(tmp_path))

        # Reset storage module
        import atlast_ecp.storage as storage
        storage.ECP_DIR = tmp_path
        storage.RECORDS_DIR = tmp_path / "records"
        storage.VAULT_DIR = tmp_path / "vault"
        storage._initialized = False

        from atlast_ecp.storage import save_vault_v2, load_vault

        save_vault_v2(
            record_id="rec_test123",
            input_content="What is 2+2?",
            output_content="2+2 equals 4.",
            extra={
                "vault_version": 2,
                "system_prompt": "You are a math tutor.",
                "full_request_hash": "sha256:abc123",
                "full_response_hash": "sha256:def456",
                "context_messages_count": 3,
                "session_id": "sess_abc",
            },
        )

        vault = load_vault("rec_test123")
        assert vault is not None
        assert vault["input"] == "What is 2+2?"
        assert vault["output"] == "2+2 equals 4."
        assert vault["vault_version"] == 2
        assert vault["system_prompt"] == "You are a math tutor."
        assert vault["full_request_hash"] == "sha256:abc123"
        assert vault["full_response_hash"] == "sha256:def456"
        assert vault["context_messages_count"] == 3
        assert vault["session_id"] == "sess_abc"

    def test_vault_v2_no_system_prompt(self, tmp_path, monkeypatch):
        """Vault v2 without system prompt (deduped)."""
        monkeypatch.setenv("ECP_DIR", str(tmp_path))

        import atlast_ecp.storage as storage
        storage.ECP_DIR = tmp_path
        storage.RECORDS_DIR = tmp_path / "records"
        storage.VAULT_DIR = tmp_path / "vault"
        storage._initialized = False

        from atlast_ecp.storage import save_vault_v2, load_vault

        save_vault_v2(
            record_id="rec_test456",
            input_content="Continue the analysis",
            output_content="Here is the continued analysis...",
            extra={
                "vault_version": 2,
                "system_prompt": None,  # deduped — not stored
                "full_request_hash": "sha256:xyz",
                "context_messages_count": 6,
            },
        )

        vault = load_vault("rec_test456")
        assert vault is not None
        assert vault["input"] == "Continue the analysis"
        assert "system_prompt" not in vault  # not stored when None
        assert vault["full_request_hash"] == "sha256:xyz"

    def test_vault_v1_backward_compat(self, tmp_path, monkeypatch):
        """Original save_vault still works (v1 format)."""
        monkeypatch.setenv("ECP_DIR", str(tmp_path))

        import atlast_ecp.storage as storage
        storage.ECP_DIR = tmp_path
        storage.RECORDS_DIR = tmp_path / "records"
        storage.VAULT_DIR = tmp_path / "vault"
        storage._initialized = False

        from atlast_ecp.storage import save_vault, load_vault

        save_vault("rec_v1test", "hello input", "hello output")

        vault = load_vault("rec_v1test")
        assert vault is not None
        assert vault["input"] == "hello input"
        assert vault["output"] == "hello output"
        assert "vault_version" not in vault  # v1 doesn't have this


# ─── Storage size verification ───────────────────────────────────────────────

class TestStorageSize:
    """Verify that vault v2 actually reduces storage."""

    def test_v2_smaller_than_full_body(self):
        """Vault v2 input is smaller than full request body for multi-turn."""
        from atlast_ecp.proxy import _extract_new_content, _session_system_prompts, _session_lock
        with _session_lock:
            _session_system_prompts.clear()

        # Simulate 10-turn conversation
        messages = [
            {"role": "system", "content": "You are a detailed research assistant. " * 10},
        ]
        for i in range(10):
            messages.append({"role": "user", "content": f"Question {i}: " + "Analyze market data. " * 20})
            messages.append({"role": "assistant", "content": f"Answer {i}: " + "The market shows growth. " * 20})
        messages.append({"role": "user", "content": "Write the final summary."})

        req = json.dumps({"model": "gpt-4o", "messages": messages}).encode()
        full_body_size = len(req)

        result = _extract_new_content(req, "openai")
        extracted_input_size = len(result["input"].encode())

        # The extracted input should be MUCH smaller than full body
        assert extracted_input_size < full_body_size / 5, \
            f"Extracted {extracted_input_size} bytes should be << full body {full_body_size} bytes"

        # But full_request_hash is still present for verification
        assert result["full_request_hash"].startswith("sha256:")
        assert result["context_messages_count"] == 22  # 1 system + 10 user + 10 assistant + 1 final user
