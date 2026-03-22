"""Coverage tests for mcp_server.py tool functions."""
from unittest.mock import patch, MagicMock
import pytest


class TestMcpVerifyRecord:
    def test_verify_found_record(self):
        from atlast_ecp.mcp_server import _tool_ecp_verify
        record = {
            "id": "rec_abc", "agent": "test-agent", "ts": 1000,
            "step": {"flags": ["error"]},
            "chain": {"prev": "genesis", "hash": "sha256:abc123def456"},
            "sig": "ed25519:xyz",
            "anchor": {"attestation_uid": "att_123"},
        }
        with patch("atlast_ecp.storage.load_record_by_id", return_value=record):
            result = _tool_ecp_verify("rec_abc")
        assert result["verified"] is True
        assert result["signature"] == "✅ signed"
        assert result["on_chain"]["status"] == "✅ anchored"

    def test_verify_not_found(self):
        from atlast_ecp.mcp_server import _tool_ecp_verify
        with patch("atlast_ecp.storage.load_record_by_id", return_value=None):
            result = _tool_ecp_verify("rec_missing")
        assert result["verified"] is False

    def test_verify_unverified_sig(self):
        from atlast_ecp.mcp_server import _tool_ecp_verify
        record = {
            "id": "rec_x", "agent": "a", "ts": 1, "step": {"flags": []},
            "chain": {"prev": "genesis", "hash": "sha256:abc"},
            "sig": "unverified", "anchor": {},
        }
        with patch("atlast_ecp.storage.load_record_by_id", return_value=record):
            result = _tool_ecp_verify("rec_x")
        assert "unverified" in result["signature"]
        assert result["on_chain"]["status"] == "⏳ pending"


class TestMcpGetProfile:
    def test_get_profile_success(self):
        from atlast_ecp.mcp_server import _tool_ecp_get_profile
        with patch("atlast_ecp.identity.get_or_create_identity", return_value={"did": "did:ecp:test"}), \
             patch("atlast_ecp.storage.load_records", return_value=[]), \
             patch("atlast_ecp.storage.count_records", return_value=42), \
             patch("atlast_ecp.signals.compute_trust_signals", return_value={
                 "retried_rate": 0.05, "hedged_rate": 0.0, "incomplete_rate": 0.01,
                 "error_rate": 0.02, "chain_integrity": 1.0, "avg_latency_ms": 150,
             }):
            result = _tool_ecp_get_profile()
        assert result["did"] == "did:ecp:test"
        assert result["total_records"] == 42

    def test_get_profile_error(self):
        from atlast_ecp.mcp_server import _tool_ecp_get_profile
        with patch("atlast_ecp.identity.get_or_create_identity", side_effect=Exception("fail")):
            result = _tool_ecp_get_profile()
        assert "error" in result


class TestMcpGetDid:
    def test_get_did(self):
        from atlast_ecp.mcp_server import _tool_ecp_get_did
        with patch("atlast_ecp.identity.get_or_create_identity", 
                    return_value={"did": "did:ecp:abc", "verified": True}):
            result = _tool_ecp_get_did()
        assert result["did"] == "did:ecp:abc"
        assert result["key_type"] == "ed25519"


class TestMcpCertify:
    def test_certify_success(self):
        from atlast_ecp.mcp_server import _tool_ecp_certify
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"cert_id":"c1","trust_score_at_issue":800,"steps_count":5,"verify_url":"http://x"}'
        with patch("atlast_ecp.identity.get_or_create_identity", return_value={"did": "did:ecp:t"}), \
             patch("atlast_ecp.storage.load_records", return_value=[{"id": "rec_1"}]), \
             patch("atlast_ecp.config.get_api_url", return_value="http://localhost"), \
             patch("urllib.request.urlopen", return_value=mock_resp):
            result = _tool_ecp_certify("My Task", "desc")
        assert result["cert_id"] == "c1"

    def test_certify_error(self):
        from atlast_ecp.mcp_server import _tool_ecp_certify
        with patch("atlast_ecp.identity.get_or_create_identity", side_effect=Exception("no")):
            result = _tool_ecp_certify("Task")
        assert "error" in result


class TestMcpRecord:
    def test_record_success(self):
        from atlast_ecp.mcp_server import _tool_ecp_record
        with patch("atlast_ecp.core.record", return_value="rec_new"):
            result = _tool_ecp_record("llm_call", "input", "output", model="gpt-4")
        assert result["record_id"] == "rec_new"

    def test_record_error(self):
        from atlast_ecp.mcp_server import _tool_ecp_record
        with patch("atlast_ecp.core.record", side_effect=Exception("fail")):
            result = _tool_ecp_record("llm_call", "in", "out")
        assert "error" in result


class TestMcpFlush:
    def test_flush_success(self):
        from atlast_ecp.mcp_server import _tool_ecp_flush
        with patch("atlast_ecp.batch.run_batch"), \
             patch("atlast_ecp.batch._load_batch_state", return_value={"total_batches": 3, "last_merkle_root": "sha256:abc123"}):
            result = _tool_ecp_flush()
        assert "Batch upload triggered" in result["message"]

    def test_flush_error(self):
        from atlast_ecp.mcp_server import _tool_ecp_flush
        with patch("atlast_ecp.batch.run_batch", side_effect=Exception("boom")):
            result = _tool_ecp_flush()
        assert "error" in result


class TestMcpStats:
    def test_stats_success(self):
        from atlast_ecp.mcp_server import _tool_ecp_stats
        with patch("atlast_ecp.identity.get_or_create_identity", return_value={"did": "did:ecp:s"}), \
             patch("atlast_ecp.storage.load_records", return_value=[]), \
             patch("atlast_ecp.storage.count_records", return_value=10), \
             patch("atlast_ecp.signals.compute_trust_signals", return_value={
                 "retried_rate": 0.0, "hedged_rate": 0.0, "incomplete_rate": 0.0,
                 "error_rate": 0.0, "chain_integrity": 1.0, "avg_latency_ms": 200,
                 "human_review_rate": 0.0, "a2a_delegated_rate": 0.0,
             }), \
             patch("atlast_ecp.batch._load_batch_state", return_value={"total_batches": 2}):
            result = _tool_ecp_stats()
        assert result["agent_did"] == "did:ecp:s"


class TestMcpRecentRecords:
    def test_recent_records(self):
        from atlast_ecp.mcp_server import _tool_ecp_recent_records
        records = [
            {"id": "rec_1", "ts": 1000, "step": {"type": "llm_call", "flags": []}},
            {"id": "rec_2", "ts": 2000, "step": {"type": "tool_call", "flags": ["error"]}},
        ]
        with patch("atlast_ecp.storage.load_records", return_value=records):
            result = _tool_ecp_recent_records(limit=5)
        assert len(result["records"]) == 2

    def test_recent_records_error(self):
        from atlast_ecp.mcp_server import _tool_ecp_recent_records
        with patch("atlast_ecp.storage.load_records", side_effect=Exception("boom")):
            result = _tool_ecp_recent_records()
        assert "error" in result
