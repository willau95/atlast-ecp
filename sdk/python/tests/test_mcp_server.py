"""
Tests for MCP Server tool functions.

Tests the tool implementations directly (not the stdio transport).
Verifies: tool definitions, handle routing, each tool function output.
"""

import warnings
import pytest
from unittest.mock import patch, MagicMock

# Suppress FutureWarning from mcp_server import
with warnings.catch_warnings():
    warnings.simplefilter("ignore", FutureWarning)
    from atlast_ecp.mcp_server import (
        _get_tools,
        _handle_tool_call,
        _tool_ecp_get_did,
        _tool_ecp_verify,
        _tool_ecp_get_profile,
        _tool_ecp_recent_records,
        _tool_ecp_record,
        _tool_ecp_flush,
        _tool_ecp_stats,
        _tool_ecp_certify,
    )


class TestToolDefinitions:
    """Test MCP tool schema definitions."""

    def test_get_tools_returns_list(self):
        tools = _get_tools()
        assert isinstance(tools, list)
        assert len(tools) >= 6

    def test_all_tools_have_required_fields(self):
        tools = _get_tools()
        for tool in tools:
            assert "name" in tool, f"Tool missing name: {tool}"
            assert "description" in tool, f"Tool {tool.get('name')} missing description"
            assert "inputSchema" in tool, f"Tool {tool.get('name')} missing inputSchema"

    def test_tool_names_are_unique(self):
        tools = _get_tools()
        names = [t["name"] for t in tools]
        assert len(names) == len(set(names)), f"Duplicate tool names: {names}"

    def test_expected_tools_exist(self):
        tools = _get_tools()
        names = {t["name"] for t in tools}
        expected = {"ecp_verify", "ecp_get_profile", "ecp_get_did",
                    "ecp_certify", "ecp_recent_records", "ecp_record",
                    "ecp_flush", "ecp_stats"}
        assert expected.issubset(names), f"Missing tools: {expected - names}"


class TestHandleToolCall:
    """Test tool call routing."""

    def test_unknown_tool_returns_error(self):
        result = _handle_tool_call("nonexistent_tool", {})
        assert "error" in result
        assert "Unknown tool" in result["error"]

    def test_routes_to_ecp_get_did(self):
        result = _handle_tool_call("ecp_get_did", {})
        assert "did" in result or "error" in result

    def test_routes_to_ecp_verify(self):
        result = _handle_tool_call("ecp_verify", {"record_id": "rec_test123"})
        assert isinstance(result, dict)

    def test_routes_to_ecp_get_profile(self):
        result = _handle_tool_call("ecp_get_profile", {})
        assert isinstance(result, dict)

    def test_routes_to_ecp_stats(self):
        result = _handle_tool_call("ecp_stats", {})
        assert isinstance(result, dict)

    def test_routes_to_ecp_recent_records(self):
        result = _handle_tool_call("ecp_recent_records", {"limit": 3})
        assert isinstance(result, dict)

    def test_routes_to_ecp_flush(self):
        result = _handle_tool_call("ecp_flush", {})
        assert isinstance(result, dict)


class TestToolGetDid:
    """Test ecp_get_did tool."""

    def test_returns_did(self):
        result = _tool_ecp_get_did()
        assert "did" in result
        assert result["did"].startswith("did:ecp:")

    def test_returns_key_type(self):
        result = _tool_ecp_get_did()
        assert "key_type" in result
        assert result["key_type"] == "ed25519"


class TestToolVerify:
    """Test ecp_verify tool."""

    def test_nonexistent_record(self):
        result = _tool_ecp_verify("rec_nonexistent_123456")
        # Should return an error or not-found, not crash
        assert isinstance(result, dict)

    def test_empty_record_id(self):
        result = _tool_ecp_verify("")
        assert isinstance(result, dict)


class TestToolRecord:
    """Test ecp_record tool."""

    def test_creates_record(self):
        result = _tool_ecp_record(
            step_type="decision",
            input_text="Should I deploy?",
            output_text="Yes, all tests pass.",
            model="test-model",
            latency_ms=100,
        )
        assert isinstance(result, dict)
        # Should return record_id or success indicator
        assert "record_id" in result or "status" in result or "error" not in result


class TestToolStats:
    """Test ecp_stats tool."""

    def test_returns_stats_dict(self):
        result = _tool_ecp_stats()
        assert isinstance(result, dict)


class TestToolCertify:
    """Test ecp_certify tool."""

    def test_certify_returns_result(self):
        result = _tool_ecp_certify("Test Task", "A test certification")
        assert isinstance(result, dict)
