"""
Tests for CLI commands (init, register, export, view, stats, did).
"""

import os
import sys
import json
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def temp_ecp_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from atlast_ecp.core import reset
    reset()
    yield tmp_path


class TestCLIInit:
    def test_init_creates_ecp_dir(self, capsys):
        from atlast_ecp.cli import cmd_init
        cmd_init([])
        captured = capsys.readouterr()
        assert "ATLAST ECP initialized" in captured.out
        assert "did:ecp:" in captured.out

    def test_init_creates_identity(self, capsys):
        from atlast_ecp.cli import cmd_init
        cmd_init([])
        from atlast_ecp.identity import get_or_create_identity
        identity = get_or_create_identity()
        assert identity["did"].startswith("did:ecp:")


class TestCLIRegister:
    def test_register_fails_gracefully(self, capsys):
        """Register should fail-open when backend is unavailable."""
        from atlast_ecp.cli import cmd_register
        cmd_register([])
        captured = capsys.readouterr()
        assert "Registering Agent" in captured.out
        # Backend available → registered; or unavailable → warning; either way no crash
        assert "not available" in captured.out or "Registered" in captured.out or "registered" in captured.out


class TestCLIDID:
    def test_did_shows_identity(self, capsys):
        from atlast_ecp.cli import cmd_did
        cmd_did([])
        captured = capsys.readouterr()
        assert "did:ecp:" in captured.out


class TestCLIExport:
    def test_export_empty(self, capsys):
        from atlast_ecp.cli import cmd_export
        cmd_export([])
        captured = capsys.readouterr()
        assert "No records" in captured.out

    def test_export_with_records(self, capsys):
        from atlast_ecp.core import record, reset
        import time
        reset()
        record("test input", "test output")
        time.sleep(0.1)
        from atlast_ecp.cli import cmd_export
        cmd_export([])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert len(data) >= 1
        assert data[0]["id"].startswith("rec_")


class TestCLIView:
    def test_view_empty(self, capsys):
        from atlast_ecp.cli import cmd_view
        cmd_view([])
        captured = capsys.readouterr()
        assert "No ECP records" in captured.out

    def test_view_with_records(self, capsys):
        from atlast_ecp.core import record, reset
        import time
        reset()
        record("input", "output")
        time.sleep(0.1)
        from atlast_ecp.cli import cmd_view
        cmd_view([])
        captured = capsys.readouterr()
        assert "Evidence Chain" in captured.out


class TestCLIStats:
    def test_stats_with_records(self, capsys):
        from atlast_ecp.core import record, reset
        import time
        reset()
        record("a", "b")
        time.sleep(0.1)
        from atlast_ecp.cli import cmd_stats
        cmd_stats([])
        captured = capsys.readouterr()
        assert "Trust Signals" in captured.out
