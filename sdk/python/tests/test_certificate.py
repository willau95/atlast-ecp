"""
Tests for certificate CLI command and MCP tool.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def temp_ecp_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from atlast_ecp.core import reset
    reset()
    yield tmp_path


class TestCertifyCLI:
    def test_certify_no_args(self, capsys):
        from atlast_ecp.cli import cmd_certify
        cmd_certify([])
        captured = capsys.readouterr()
        assert "Usage" in captured.out

    def test_certify_with_title(self, capsys):
        """Certify should attempt backend call (may fail if backend down)."""
        from atlast_ecp.core import record
        import time
        record("input", "output")
        time.sleep(0.1)
        from atlast_ecp.cli import cmd_certify
        cmd_certify(["Test Report"])
        captured = capsys.readouterr()
        assert "Creating Work Certificate" in captured.out
        # Either succeeds or fails gracefully
        assert "Certificate" in captured.out

    def test_certify_with_description(self, capsys):
        from atlast_ecp.cli import cmd_certify
        cmd_certify(["Report", "--desc", "A detailed analysis"])
        captured = capsys.readouterr()
        assert "Creating Work Certificate" in captured.out


class TestCertifyMCP:
    def test_mcp_certify_tool_exists(self):
        from atlast_ecp.mcp_server import _get_tools
        tools = _get_tools()
        tool_names = {t["name"] for t in tools}
        assert "ecp_certify" in tool_names

    def test_mcp_certify_returns_dict(self):
        from atlast_ecp.mcp_server import _handle_tool_call
        result = _handle_tool_call("ecp_certify", {"title": "Test"})
        assert isinstance(result, dict)
        # Either has cert_id (success) or error (backend not available)
        assert "cert_id" in result or "error" in result

    def test_mcp_has_tools(self):
        from atlast_ecp.mcp_server import _get_tools
        assert len(_get_tools()) == 8  # verify, profile, did, certify, recent, record, flush, stats
