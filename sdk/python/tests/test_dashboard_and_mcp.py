"""
Tests for Dashboard Server API + MCP Query Tools.
"""

import json
import os
import time
import pytest
import threading
from pathlib import Path
from http.client import HTTPConnection
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def setup_ecp_dir(monkeypatch, tmp_path):
    """Set up test ECP directory with data."""
    ecp_dir = tmp_path / ".ecp"
    records_dir = ecp_dir / "records"
    vault_dir = ecp_dir / "vault"
    local_dir = ecp_dir / "local"

    for d in [ecp_dir, records_dir, vault_dir, local_dir]:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("ECP_DIR", str(ecp_dir))
    monkeypatch.setenv("ATLAST_ECP_DIR", str(ecp_dir))

    import atlast_ecp.storage as storage_mod
    monkeypatch.setattr(storage_mod, "ECP_DIR", ecp_dir)
    monkeypatch.setattr(storage_mod, "RECORDS_DIR", records_dir)
    monkeypatch.setattr(storage_mod, "VAULT_DIR", vault_dir)
    monkeypatch.setattr(storage_mod, "LOCAL_DIR", local_dir)
    monkeypatch.setattr(storage_mod, "INDEX_FILE", ecp_dir / "index.json")

    import atlast_ecp.query as query_mod
    monkeypatch.setattr(query_mod, "ECP_DIR", ecp_dir)
    monkeypatch.setattr(query_mod, "RECORDS_DIR", records_dir)
    monkeypatch.setattr(query_mod, "VAULT_DIR", vault_dir)
    monkeypatch.setattr(query_mod, "INDEX_DB", ecp_dir / "search.db")

    from datetime import datetime, timezone
    now_ms = int(time.time() * 1000)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    record_file = records_dir / f"{today}.jsonl"

    records = []
    for i in range(5):
        records.append({
            "id": f"rec_dash_{i:04d}",
            "agent": "did:ecp:dash_test",
            "ts": now_ms - i * 3600_000,
            "step": {
                "type": "tool_call",
                "action": "analyze" if i != 3 else "web_search",
                "model": "gpt-4o",
                "latency_ms": 200 + i * 100,
                "flags": ["error"] if i == 3 else [],
                "session_id": "sess_dash_001",
            },
            "chain": {"prev": f"rec_dash_{i-1:04d}" if i > 0 else "", "hash": f"sha256:{'b'*60}{i:04d}"},
        })

    with open(record_file, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    (ecp_dir / "index.json").write_text(json.dumps(
        {r["id"]: {"file": str(record_file), "date": today} for r in records}
    ))

    yield ecp_dir


# ── Dashboard Server API Tests ──────────────────────────────────────────────

class TestDashboardServer:
    def test_api_search(self, setup_ecp_dir):
        from atlast_ecp.dashboard_server import DashboardHandler
        from http.server import HTTPServer
        import urllib.request

        server = HTTPServer(("127.0.0.1", 0), DashboardHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/search?q=analyze")
        data = json.loads(resp.read())
        assert "records" in data
        assert data["total"] >= 1
        server.server_close()

    def test_api_timeline(self, setup_ecp_dir):
        from atlast_ecp.dashboard_server import DashboardHandler
        from http.server import HTTPServer
        import urllib.request

        server = HTTPServer(("127.0.0.1", 0), DashboardHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/timeline?days=7")
        data = json.loads(resp.read())
        assert "timeline" in data
        server.server_close()

    def test_api_audit(self, setup_ecp_dir):
        from atlast_ecp.dashboard_server import DashboardHandler
        from http.server import HTTPServer
        import urllib.request

        server = HTTPServer(("127.0.0.1", 0), DashboardHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/audit?days=7")
        data = json.loads(resp.read())
        assert data.get("status") in ("complete", "no_data")
        server.server_close()

    def test_api_trace(self, setup_ecp_dir):
        from atlast_ecp.dashboard_server import DashboardHandler
        from http.server import HTTPServer
        import urllib.request

        server = HTTPServer(("127.0.0.1", 0), DashboardHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/trace?id=rec_dash_0003")
        data = json.loads(resp.read())
        assert "chain" in data
        assert data["depth"] >= 1
        server.server_close()

    def test_api_index(self, setup_ecp_dir):
        from atlast_ecp.dashboard_server import DashboardHandler
        from http.server import HTTPServer
        import urllib.request

        server = HTTPServer(("127.0.0.1", 0), DashboardHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/index")
        data = json.loads(resp.read())
        assert data["indexed"] == 5
        server.server_close()

    def test_serves_html(self, setup_ecp_dir):
        from atlast_ecp.dashboard_server import DashboardHandler
        from http.server import HTTPServer
        import urllib.request

        server = HTTPServer(("127.0.0.1", 0), DashboardHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/")
        html = resp.read().decode()
        assert "ATLAST" in html
        assert "Evidence Chain" in html
        server.server_close()


# ── MCP Tool Tests ──────────────────────────────────────────────────────────

class TestMCPTools:
    def test_mcp_search(self, setup_ecp_dir):
        from atlast_ecp.mcp_server import _tool_ecp_search
        result = _tool_ecp_search(query="analyze")
        assert result["count"] >= 1
        assert "results" in result

    def test_mcp_search_errors(self, setup_ecp_dir):
        from atlast_ecp.mcp_server import _tool_ecp_search
        result = _tool_ecp_search(query="", errors_only=True)
        assert result["count"] == 1

    def test_mcp_trace(self, setup_ecp_dir):
        from atlast_ecp.mcp_server import _tool_ecp_trace
        result = _tool_ecp_trace(record_id="rec_dash_0003")
        assert result["depth"] >= 1
        assert result["direction"] == "back"

    def test_mcp_audit(self, setup_ecp_dir):
        from atlast_ecp.mcp_server import _tool_ecp_audit
        result = _tool_ecp_audit(days=7)
        assert result.get("status") in ("complete", "no_data")

    def test_mcp_timeline(self, setup_ecp_dir):
        from atlast_ecp.mcp_server import _tool_ecp_timeline
        result = _tool_ecp_timeline(days=7)
        assert "timeline" in result

    def test_mcp_handle_tool_call(self, setup_ecp_dir):
        from atlast_ecp.mcp_server import _handle_tool_call
        result = _handle_tool_call("ecp_search", {"query": "gpt-4o"})
        assert result["count"] == 5

    def test_mcp_handle_unknown_tool(self, setup_ecp_dir):
        from atlast_ecp.mcp_server import _handle_tool_call
        result = _handle_tool_call("ecp_nonexistent", {})
        assert "error" in result


class TestDashboardCLI:
    def test_cmd_dashboard_exists(self):
        from atlast_ecp.cli import cmd_dashboard
        assert callable(cmd_dashboard)
