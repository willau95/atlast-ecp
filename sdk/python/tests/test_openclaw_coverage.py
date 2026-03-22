"""Tests for openclaw_scanner.py — covers the major gaps (97 missed lines)."""
import json
import os
import warnings
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


# ─── scan_session_file ────────────────────────────────────────────────────────

def _write_jsonl(path, entries):
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")


class TestScanSessionFile:
    def test_simple_user_assistant_pair(self, tmp_path):
        f = tmp_path / "session.jsonl"
        _write_jsonl(f, [
            {"type": "message", "timestamp": "2024-01-01T10:00:00Z",
             "message": {"role": "user", "content": "Hello"}},
            {"type": "message", "timestamp": "2024-01-01T10:00:01Z",
             "message": {"role": "assistant", "content": "Hi there"}},
        ])
        from atlast_ecp.openclaw_scanner import scan_session_file
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = scan_session_file(str(f))
        assert len(result) == 1
        assert result[0]["input"] == "Hello"
        assert result[0]["output"] == "Hi there"

    def test_skips_entries_before_since_ts(self, tmp_path):
        f = tmp_path / "session.jsonl"
        _write_jsonl(f, [
            {"type": "message", "timestamp": "2024-01-01T09:00:00Z",
             "message": {"role": "user", "content": "Old"}},
            {"type": "message", "timestamp": "2024-01-01T09:00:01Z",
             "message": {"role": "assistant", "content": "Old reply"}},
            {"type": "message", "timestamp": "2024-01-01T11:00:00Z",
             "message": {"role": "user", "content": "New"}},
            {"type": "message", "timestamp": "2024-01-01T11:00:01Z",
             "message": {"role": "assistant", "content": "New reply"}},
        ])
        from atlast_ecp.openclaw_scanner import scan_session_file
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = scan_session_file(str(f), since_ts="2024-01-01T10:00:00Z")
        assert len(result) == 1
        assert result[0]["input"] == "New"

    def test_list_content_user_message(self, tmp_path):
        """User content as list of dicts."""
        f = tmp_path / "session.jsonl"
        _write_jsonl(f, [
            {"type": "message", "timestamp": "2024-01-01T10:00:00Z",
             "message": {"role": "user", "content": [{"text": "Part 1"}, {"text": " Part 2"}]}},
            {"type": "message", "timestamp": "2024-01-01T10:00:01Z",
             "message": {"role": "assistant", "content": "Answer"}},
        ])
        from atlast_ecp.openclaw_scanner import scan_session_file
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = scan_session_file(str(f))
        assert "Part 1" in result[0]["input"]

    def test_list_content_assistant_with_tool_use(self, tmp_path):
        """Assistant content as list with text and tool_use blocks."""
        f = tmp_path / "session.jsonl"
        _write_jsonl(f, [
            {"type": "message", "timestamp": "2024-01-01T10:00:00Z",
             "message": {"role": "user", "content": "Do something"}},
            {"type": "message", "timestamp": "2024-01-01T10:00:01Z",
             "message": {"role": "assistant", "content": [
                 {"type": "text", "text": "Sure, "},
                 {"type": "tool_use", "name": "bash"},
                 {"type": "text", "text": "done."},
             ]}},
        ])
        from atlast_ecp.openclaw_scanner import scan_session_file
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = scan_session_file(str(f))
        assert "Sure" in result[0]["output"]
        assert "[tool:bash]" in result[0]["output"]

    def test_cache_ttl_attaches_model(self, tmp_path):
        """custom openclaw.cache-ttl entries attach model to last interaction."""
        f = tmp_path / "session.jsonl"
        _write_jsonl(f, [
            {"type": "message", "timestamp": "2024-01-01T10:00:00Z",
             "message": {"role": "user", "content": "Q"}},
            {"type": "message", "timestamp": "2024-01-01T10:00:01Z",
             "message": {"role": "assistant", "content": "A"}},
            {"type": "custom", "customType": "openclaw.cache-ttl",
             "data": {"modelId": "claude-sonnet-4-6"}},
        ])
        from atlast_ecp.openclaw_scanner import scan_session_file
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = scan_session_file(str(f))
        assert result[0]["model"] == "claude-sonnet-4-6"

    def test_usage_data_attaches_tokens(self, tmp_path):
        """custom entries with usage data attach token counts."""
        f = tmp_path / "session.jsonl"
        _write_jsonl(f, [
            {"type": "message", "timestamp": "2024-01-01T10:00:00Z",
             "message": {"role": "user", "content": "Q"}},
            {"type": "message", "timestamp": "2024-01-01T10:00:01Z",
             "message": {"role": "assistant", "content": "A"}},
            {"type": "custom", "data": {"usage": {"input_tokens": 10, "output_tokens": 20}}},
        ])
        from atlast_ecp.openclaw_scanner import scan_session_file
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = scan_session_file(str(f))
        assert result[0]["tokens_in"] == 10
        assert result[0]["tokens_out"] == 20

    def test_latency_computed_from_timestamps(self, tmp_path):
        f = tmp_path / "session.jsonl"
        _write_jsonl(f, [
            {"type": "message", "timestamp": "2024-01-01T10:00:00.000Z",
             "message": {"role": "user", "content": "Q"}},
            {"type": "message", "timestamp": "2024-01-01T10:00:01.500Z",
             "message": {"role": "assistant", "content": "A"}},
        ])
        from atlast_ecp.openclaw_scanner import scan_session_file
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = scan_session_file(str(f))
        assert result[0]["latency_ms"] == 1500

    def test_invalid_json_lines_skipped(self, tmp_path):
        f = tmp_path / "session.jsonl"
        f.write_text('{"valid": true}\n{bad json}\n{"also": "valid"}\n')
        from atlast_ecp.openclaw_scanner import scan_session_file
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = scan_session_file(str(f))
        # No interactions (no user/assistant pairs)
        assert result == []

    def test_empty_lines_skipped(self, tmp_path):
        f = tmp_path / "session.jsonl"
        f.write_text("\n\n\n")
        from atlast_ecp.openclaw_scanner import scan_session_file
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = scan_session_file(str(f))
        assert result == []

    def test_warning_shown_once(self, tmp_path):
        import atlast_ecp.openclaw_scanner as scanner_mod
        scanner_mod._WARNED = False
        f = tmp_path / "session.jsonl"
        f.write_text("")
        from atlast_ecp.openclaw_scanner import scan_session_file
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            scan_session_file(str(f))
            scan_session_file(str(f))
        future_warns = [x for x in w if issubclass(x.category, FutureWarning)]
        assert len(future_warns) == 1  # Only once


# ─── _set_agent_ecp_dir ──────────────────────────────────────────────────────

class TestSetAgentEcpDir:
    def test_sets_env_and_storage_paths(self, tmp_path, monkeypatch):
        from atlast_ecp.openclaw_scanner import _set_agent_ecp_dir
        from atlast_ecp import storage
        with patch.object(storage, "init_storage"):
            _set_agent_ecp_dir("test-agent-123")
        expected = os.path.expanduser("~/.ecp/agents/test-agent-123")
        assert os.environ.get("ATLAST_ECP_DIR") == expected


# ─── scan_openclaw_agent ─────────────────────────────────────────────────────

class TestScanOpenclawAgent:
    def _make_agent_dir(self, tmp_path):
        """Create a mock OpenClaw agent directory structure."""
        sessions = tmp_path / "agents" / "main" / "sessions"
        sessions.mkdir(parents=True)
        return tmp_path, sessions

    def test_returns_error_when_no_sessions_dir(self, tmp_path, monkeypatch):
        from atlast_ecp.openclaw_scanner import scan_openclaw_agent
        result = scan_openclaw_agent(str(tmp_path), agent_name="test")
        assert result["error"] == "no sessions dir"

    def test_scans_sessions_and_creates_records(self, tmp_path, monkeypatch):
        agent_dir, sessions = self._make_agent_dir(tmp_path)
        f = sessions / "session1.jsonl"
        _write_jsonl(f, [
            {"type": "message", "timestamp": "2024-01-01T10:00:00Z",
             "message": {"role": "user", "content": "Hello"}},
            {"type": "message", "timestamp": "2024-01-01T10:00:01Z",
             "message": {"role": "assistant", "content": "World"}},
        ])

        with patch("atlast_ecp.openclaw_scanner._set_agent_ecp_dir"), \
             patch("atlast_ecp.openclaw_scanner.record", return_value="rec_123"), \
             patch("atlast_ecp.openclaw_scanner.scan_session_file",
                   return_value=[{"input": "Hello", "output": "World", "timestamp": "2024-01-01T10:00:01Z"}]):
            from atlast_ecp.openclaw_scanner import scan_openclaw_agent
            result = scan_openclaw_agent(str(agent_dir), agent_name="test-agent")

        assert result["new_records"] == 1
        assert result["agent_name"] == "test-agent"

    def test_reads_agent_name_from_identity_md(self, tmp_path):
        agent_dir, sessions = self._make_agent_dir(tmp_path)
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        identity_file = workspace / "IDENTITY.md"
        identity_file.write_text("# Agent\n**Name:** Alice Smith\n")

        with patch("atlast_ecp.openclaw_scanner._set_agent_ecp_dir"), \
             patch("atlast_ecp.openclaw_scanner.scan_session_file", return_value=[]):
            from atlast_ecp.openclaw_scanner import scan_openclaw_agent
            result = scan_openclaw_agent(str(agent_dir))
        assert result["agent_name"] == "Alice Smith"

    def test_fallback_agent_name_from_dir(self, tmp_path):
        named = tmp_path / ".openclaw-bob-jones"
        sessions = named / "agents" / "main" / "sessions"
        sessions.mkdir(parents=True)

        with patch("atlast_ecp.openclaw_scanner._set_agent_ecp_dir"), \
             patch("atlast_ecp.openclaw_scanner.scan_session_file", return_value=[]):
            from atlast_ecp.openclaw_scanner import scan_openclaw_agent
            result = scan_openclaw_agent(str(named))
        assert result["agent_name"] == "bob-jones"

    def test_loads_and_saves_state(self, tmp_path):
        agent_dir, sessions = self._make_agent_dir(tmp_path)
        f = sessions / "session1.jsonl"
        f.write_text("")  # empty

        with patch("atlast_ecp.openclaw_scanner._set_agent_ecp_dir"), \
             patch("atlast_ecp.openclaw_scanner.scan_session_file", return_value=[]):
            from atlast_ecp.openclaw_scanner import scan_openclaw_agent
            result = scan_openclaw_agent(str(agent_dir), agent_name="test")
        assert result["new_records"] == 0

    def test_counts_skipped_when_record_returns_none(self, tmp_path):
        agent_dir, sessions = self._make_agent_dir(tmp_path)
        (sessions / "session1.jsonl").write_text('{"role":"user"}\n')

        with patch("atlast_ecp.openclaw_scanner._set_agent_ecp_dir"), \
             patch("atlast_ecp.openclaw_scanner.record", return_value=None), \
             patch("atlast_ecp.openclaw_scanner.scan_session_file",
                   return_value=[{"input": "Q", "output": "A", "timestamp": "t"}]):
            from atlast_ecp.openclaw_scanner import scan_openclaw_agent
            result = scan_openclaw_agent(str(agent_dir), agent_name="test")
        assert result["skipped"] == 1
        assert result["new_records"] == 0
