"""Tests for ECP v1.0 Minimal Record support."""

import json
import os
import pytest
from unittest.mock import patch

from atlast_ecp.record import create_minimal_record, hash_content
from atlast_ecp.core import record_minimal, record_minimal_async
from atlast_ecp.storage import load_records


class TestCreateMinimalRecord:
    """Test create_minimal_record() produces valid v1.0 format."""

    def test_basic_fields(self):
        rec = create_minimal_record("my-agent", "llm_call", "hello", "world")
        assert rec["ecp"] == "1.0"
        assert rec["id"].startswith("rec_")
        assert len(rec["id"]) == 20  # rec_ + 16 hex
        assert isinstance(rec["ts"], int)
        assert rec["agent"] == "my-agent"
        assert rec["action"] == "llm_call"
        assert rec["in_hash"].startswith("sha256:")
        assert rec["out_hash"].startswith("sha256:")

    def test_no_chain_no_sig(self):
        rec = create_minimal_record("agent", "tool_call", "in", "out")
        assert "chain" not in rec
        assert "sig" not in rec
        assert "step" not in rec  # v1.0 uses flat format

    def test_hash_consistency(self):
        rec1 = create_minimal_record("a", "llm_call", "same input", "same output")
        rec2 = create_minimal_record("a", "llm_call", "same input", "same output")
        assert rec1["in_hash"] == rec2["in_hash"]
        assert rec1["out_hash"] == rec2["out_hash"]

    def test_different_content_different_hash(self):
        rec1 = create_minimal_record("a", "llm_call", "hello", "world")
        rec2 = create_minimal_record("a", "llm_call", "different", "content")
        assert rec1["in_hash"] != rec2["in_hash"]
        assert rec1["out_hash"] != rec2["out_hash"]

    def test_with_meta(self):
        meta = {"model": "claude-sonnet-4-6", "tokens_in": 100, "tokens_out": 50, "latency_ms": 500}
        rec = create_minimal_record("a", "llm_call", "in", "out", meta=meta)
        assert rec["meta"]["model"] == "claude-sonnet-4-6"
        assert rec["meta"]["tokens_in"] == 100
        assert rec["meta"]["tokens_out"] == 50
        assert rec["meta"]["latency_ms"] == 500

    def test_meta_none_values_excluded(self):
        meta = {"model": "gpt-4", "tokens_in": None, "latency_ms": 200}
        rec = create_minimal_record("a", "llm_call", "in", "out", meta=meta)
        assert "tokens_in" not in rec["meta"]
        assert rec["meta"]["model"] == "gpt-4"

    def test_no_meta_when_none(self):
        rec = create_minimal_record("a", "llm_call", "in", "out")
        assert "meta" not in rec

    def test_all_action_types(self):
        for action in ["llm_call", "tool_call", "message", "a2a_call"]:
            rec = create_minimal_record("a", action, "in", "out")
            assert rec["action"] == action

    def test_dict_content_hashing(self):
        content = {"messages": [{"role": "user", "content": "hello"}]}
        rec = create_minimal_record("a", "llm_call", content, "out")
        assert rec["in_hash"] == hash_content(content)

    def test_agent_any_string(self):
        """Agent field accepts any string, not just DIDs."""
        for agent in ["my-agent", "agent-42", "did:ecp:abc123", "anything goes"]:
            rec = create_minimal_record(agent, "llm_call", "in", "out")
            assert rec["agent"] == agent


class TestRecordMinimal:
    """Test core.record_minimal() end-to-end."""

    def test_returns_record_id(self, tmp_path):
        with patch.dict(os.environ, {"ATLAST_ECP_DIR": str(tmp_path)}):
            from atlast_ecp import storage
            storage.ECP_DIR = tmp_path
            storage.RECORDS_DIR = tmp_path / "records"
            storage.LOCAL_DIR = tmp_path / "local"
            storage.INDEX_FILE = tmp_path / "index.json"

            rid = record_minimal("hello", "world", agent="test-agent")
            assert rid is not None
            assert rid.startswith("rec_")

    def test_saves_to_storage(self, tmp_path):
        with patch.dict(os.environ, {"ATLAST_ECP_DIR": str(tmp_path)}):
            from atlast_ecp import storage
            storage.ECP_DIR = tmp_path
            storage.RECORDS_DIR = tmp_path / "records"
            storage.LOCAL_DIR = tmp_path / "local"
            storage.INDEX_FILE = tmp_path / "index.json"

            record_minimal("input", "output", agent="test")
            records = load_records(limit=10)
            assert len(records) >= 1
            rec = records[0]
            assert rec["ecp"] == "1.0"
            assert rec["agent"] == "test"
            assert rec["action"] == "llm_call"

    def test_with_model_and_latency(self, tmp_path):
        with patch.dict(os.environ, {"ATLAST_ECP_DIR": str(tmp_path)}):
            from atlast_ecp import storage
            storage.ECP_DIR = tmp_path
            storage.RECORDS_DIR = tmp_path / "records"
            storage.LOCAL_DIR = tmp_path / "local"
            storage.INDEX_FILE = tmp_path / "index.json"

            record_minimal("in", "out", agent="a", model="gpt-4", latency_ms=1000)
            records = load_records(limit=1)
            assert records[0]["meta"]["model"] == "gpt-4"
            assert records[0]["meta"]["latency_ms"] == 1000

    def test_detects_flags(self, tmp_path):
        with patch.dict(os.environ, {"ATLAST_ECP_DIR": str(tmp_path)}):
            from atlast_ecp import storage
            storage.ECP_DIR = tmp_path
            storage.RECORDS_DIR = tmp_path / "records"
            storage.LOCAL_DIR = tmp_path / "local"
            storage.INDEX_FILE = tmp_path / "index.json"

            record_minimal("in", "I think maybe this could work", agent="a")
            records = load_records(limit=1)
            assert "hedged" in records[0]["meta"]["flags"]

    def test_fail_open(self):
        """record_minimal never raises."""
        # Even with broken storage, should return None not raise
        with patch("atlast_ecp.core.save_record", side_effect=Exception("boom")):
            result = record_minimal("in", "out")
            assert result is None


class TestRecordMinimalAsync:
    """Test fire-and-forget async version."""

    def test_does_not_raise(self):
        """Async version should never raise."""
        record_minimal_async("in", "out", agent="test")
        # No assertion needed — just verifying no exception
