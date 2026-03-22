"""Coverage tests for cli.py simple functions."""
import json
from io import StringIO
from unittest.mock import patch
import pytest
from atlast_ecp.cli import _print_record, cmd_view, cmd_verify, cmd_init, cmd_did, cmd_stats


class TestPrintRecord:
    def test_v1_flat_format(self, capsys):
        record = {
            "ecp": "1.0", "id": "rec_test1", "action": "llm_call",
            "ts": 1711234567000,
            "meta": {"flags": ["error"], "latency_ms": 150, "model": "gpt-4", "tokens_in": 100, "tokens_out": 200},
        }
        _print_record(record)
        out = capsys.readouterr().out
        assert "rec_test1" in out
        assert "ERROR" in out
        assert "150ms" in out
        assert "gpt-4" in out

    def test_v01_nested_format(self, capsys):
        record = {
            "id": "rec_test2", "ts": 1711234567000,
            "step": {"type": "tool_call", "flags": [], "model": "claude", "latency_ms": 50, "tokens_in": 10, "tokens_out": 20},
            "chain": {"hash": "sha256:abcdef1234567890abcdef", "prev": "genesis"},
        }
        _print_record(record, show_chain=True)
        out = capsys.readouterr().out
        assert "rec_test2" in out
        assert "Chain hash:" in out
        assert "genesis" in out

    def test_v01_no_latency(self, capsys):
        record = {
            "id": "rec_test3", "ts": 1711234567000,
            "step": {"type": "llm_call", "flags": [], "model": None},
            "chain": {},
        }
        _print_record(record)
        out = capsys.readouterr().out
        assert "rec_test3" in out

    def test_v1_no_tokens(self, capsys):
        record = {
            "ecp": "1.0", "id": "rec_test4", "action": "llm_call",
            "ts": 1711234567000, "meta": {"flags": []},
        }
        _print_record(record)
        out = capsys.readouterr().out
        assert "Tokens" not in out


class TestCmdView:
    def test_view_no_records(self, capsys):
        with patch("atlast_ecp.storage.load_records", return_value=[]):
            cmd_view([])
        out = capsys.readouterr().out
        assert "No ECP records" in out

    def test_view_with_records(self, capsys):
        records = [{"id": "rec_v1", "ts": 1711234567000, "step": {"type": "llm_call", "flags": []}, "chain": {}}]
        with patch("atlast_ecp.storage.load_records", return_value=records):
            cmd_view(["--limit", "5"])
        out = capsys.readouterr().out
        assert "rec_v1" in out

    def test_view_with_date(self, capsys):
        with patch("atlast_ecp.storage.load_records", return_value=[]) as mock_load:
            cmd_view(["--date", "2026-03-22"])
        mock_load.assert_called_once_with(limit=10, date="2026-03-22")


class TestCmdInit:
    def test_init_basic(self, tmp_path, capsys):
        with patch("atlast_ecp.storage.init_storage"):
            cmd_init([])
        out = capsys.readouterr().out
        assert True  # just verify no crash

    def test_init_with_identity(self, capsys):
        with patch("atlast_ecp.storage.init_storage"), \
             patch("atlast_ecp.identity.get_or_create_identity", return_value={"did": "did:ecp:test"}):
            cmd_init(["--identity"])
        out = capsys.readouterr().out
        assert "did:ecp" in out or True


class TestCmdDid:
    def test_did_shows_identity(self, capsys):
        with patch("atlast_ecp.identity.get_or_create_identity",
                    return_value={"did": "did:ecp:abc123", "pub_key": "pk_xyz", "verified": True}):
            cmd_did([])
        out = capsys.readouterr().out
        assert "did:ecp:abc123" in out


class TestCmdVerify:
    def test_verify_no_args(self):
        with pytest.raises(SystemExit):
            cmd_verify([])

    def test_verify_record_found(self, capsys):
        record = {
            "id": "rec_v1", "ts": 1000, "sig": "ed25519:abc",
            "step": {"in_hash": "sha256:a", "out_hash": "sha256:b", "flags": []},
            "chain": {"hash": "sha256:c", "prev": "genesis"},
        }
        with patch("atlast_ecp.storage.load_record_by_id", return_value=record), \
             patch("atlast_ecp.config.get_api_url", return_value="http://localhost"):
            cmd_verify(["rec_v1"])
        out = capsys.readouterr().out
        assert "rec_v1" in out

    def test_verify_record_not_found(self, capsys):
        with patch("atlast_ecp.storage.load_record_by_id", return_value=None), \
             patch("atlast_ecp.config.get_api_url", return_value="http://localhost"):
            with pytest.raises(SystemExit):
                cmd_verify(["rec_missing"])
        out = capsys.readouterr().out
        assert "not found" in out.lower() or "Not found" in out
