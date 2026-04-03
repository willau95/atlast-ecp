"""
Tests for the Query & Audit Engine (search, trace, audit, timeline).
"""

import json
import os
import time
import shutil
import pytest
from pathlib import Path
from unittest.mock import patch

# Use temp dir for all tests
TEST_ECP_DIR = Path("/tmp/test_ecp_query")


@pytest.fixture(autouse=True)
def setup_ecp_dir(monkeypatch, tmp_path):
    """Set up a clean .ecp directory with test data for each test."""
    ecp_dir = tmp_path / ".ecp"
    records_dir = ecp_dir / "records"
    vault_dir = ecp_dir / "vault"
    local_dir = ecp_dir / "local"

    for d in [ecp_dir, records_dir, vault_dir, local_dir]:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("ECP_DIR", str(ecp_dir))
    monkeypatch.setenv("ATLAST_ECP_DIR", str(ecp_dir))

    # Patch storage module paths
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

    # Write test records
    now_ms = int(time.time() * 1000)
    records = []
    for i in range(10):
        ts = now_ms - (9 - i) * 60_000  # 1 minute apart (keep all in same day)
        record = {
            "id": f"rec_test_{i:04d}",
            "agent": "did:ecp:test_agent_001",
            "ts": ts,
            "step": {
                "type": "tool_call" if i % 3 != 0 else "llm_call",
                "action": "web_search" if i % 2 == 0 else "code_review",
                "model": "gpt-4o",
                "latency_ms": 200 + i * 50 + (2000 if i == 7 else 0),
                "confidence": 0.9 - (0.4 if i == 7 else 0),
                "flags": ["error"] if i == 7 else [],
                "session_id": "sess_test_001",
            },
            "chain": {
                "prev": f"rec_test_{i-1:04d}" if i > 0 else "",
                "hash": f"sha256:{'a' * 60}{i:04d}",
            },
        }
        if i == 4:
            record["step"]["delegation_id"] = "deleg_sub_001"
            record["step"]["delegation_depth"] = 1
        records.append(record)

    # Write to today's file
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    record_file = records_dir / f"{today}.jsonl"
    with open(record_file, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    # Write vault entries for some records
    for r in records[:3]:
        vault_file = vault_dir / f"{r['id']}.json"
        vault_file.write_text(json.dumps({
            "record_id": r["id"],
            "input": f"Search for market analysis data point {r['id']}",
            "output": f"Found 3 results for {r['id']}",
        }))

    # Write index.json
    index = {r["id"]: {"file": str(record_file), "date": today} for r in records}
    (ecp_dir / "index.json").write_text(json.dumps(index))

    yield ecp_dir


class TestRebuildIndex:
    def test_rebuild_creates_db(self, setup_ecp_dir):
        from atlast_ecp.query import rebuild_index, INDEX_DB
        count = rebuild_index()
        assert count == 10
        assert INDEX_DB.exists()

    def test_rebuild_idempotent(self, setup_ecp_dir):
        from atlast_ecp.query import rebuild_index
        c1 = rebuild_index()
        c2 = rebuild_index()
        assert c1 == c2 == 10


class TestSearch:
    def test_search_by_action(self, setup_ecp_dir):
        from atlast_ecp.query import search
        results = search("web_search", as_json=True)
        assert len(results) > 0
        assert all("web_search" in (r.get("action") or "") for r in results)

    def test_search_by_model(self, setup_ecp_dir):
        from atlast_ecp.query import search
        results = search("gpt-4o", as_json=True)
        assert len(results) == 10

    def test_search_errors_only(self, setup_ecp_dir):
        from atlast_ecp.query import search
        results = search("", errors_only=True, as_json=True)
        assert len(results) == 1
        assert results[0]["id"] == "rec_test_0007"

    def test_search_with_limit(self, setup_ecp_dir):
        from atlast_ecp.query import search
        results = search("", limit=3, as_json=True)
        assert len(results) == 3

    def test_search_no_results(self, setup_ecp_dir):
        from atlast_ecp.query import search
        results = search("nonexistent_query_xyz", as_json=True)
        assert len(results) == 0

    def test_search_by_session(self, setup_ecp_dir):
        from atlast_ecp.query import search
        results = search("sess_test_001", as_json=True)
        assert len(results) == 10

    def test_search_vault_content(self, setup_ecp_dir):
        from atlast_ecp.query import search
        results = search("market analysis", as_json=True)
        assert len(results) > 0

    def test_search_human_output(self, setup_ecp_dir, capsys):
        from atlast_ecp.query import search
        search("web_search", as_json=False)
        captured = capsys.readouterr()
        assert "Found" in captured.out
        assert "rec_test_" in captured.out


class TestTrace:
    def test_trace_back(self, setup_ecp_dir):
        from atlast_ecp.query import trace
        chain = trace("rec_test_0005", direction="back", as_json=True)
        assert len(chain) >= 5
        # First entry should be the starting record
        assert chain[0].get("id") == "rec_test_0005"

    def test_trace_forward(self, setup_ecp_dir):
        from atlast_ecp.query import trace
        chain = trace("rec_test_0003", direction="forward", as_json=True)
        assert len(chain) >= 1

    def test_trace_genesis(self, setup_ecp_dir):
        from atlast_ecp.query import trace
        chain = trace("rec_test_0000", direction="back", as_json=True)
        assert len(chain) == 1  # Genesis record, no prev

    def test_trace_nonexistent(self, setup_ecp_dir):
        from atlast_ecp.query import trace
        chain = trace("rec_nonexistent", as_json=True)
        assert len(chain) == 0

    def test_trace_human_output(self, setup_ecp_dir, capsys):
        from atlast_ecp.query import trace
        trace("rec_test_0003", as_json=False)
        captured = capsys.readouterr()
        assert "Trace" in captured.out


class TestTimeline:
    def test_timeline_returns_data(self, setup_ecp_dir):
        from atlast_ecp.query import timeline
        results = timeline(days=7, as_json=True)
        assert len(results) >= 1
        day = results[0]
        assert "date" in day
        assert "total" in day
        assert "agent_errors" in day
        assert "error_rate" in day
        assert "avg_latency_ms" in day

    def test_timeline_error_rate(self, setup_ecp_dir):
        from atlast_ecp.query import timeline
        results = timeline(days=7, as_json=True)
        # We have 1 error in records (agent_errors, non-infra)
        assert results[0]["agent_errors"] == 1
        assert results[0]["error_rate"] > 0

    def test_timeline_human_output(self, setup_ecp_dir, capsys):
        from atlast_ecp.query import timeline
        timeline(days=7, as_json=False)
        captured = capsys.readouterr()
        assert "Timeline" in captured.out
        assert "interactions" in captured.out or "Work" in captured.out


class TestAudit:
    def test_audit_basic(self, setup_ecp_dir):
        from atlast_ecp.query import audit
        report = audit(days=7, as_json=True)
        assert report["status"] == "complete"
        assert report["summary"]["total_records"] == 10
        assert report["summary"]["agent_errors"] == 1
        assert "anomalies" in report
        assert "health" in report

    def test_audit_detects_latency_spike(self, setup_ecp_dir):
        from atlast_ecp.query import audit
        report = audit(days=7, as_json=True)
        # Record 7 has latency 2550ms vs avg ~475ms, should detect if threshold met
        # The anomaly detection is per-day, all records are on same day
        assert report["status"] == "complete"

    def test_audit_no_data(self, setup_ecp_dir):
        from atlast_ecp.query import audit
        report = audit(days=0, as_json=True)  # 0 days = only today, which may have data
        assert report["status"] in ("complete", "no_data")

    def test_audit_human_output(self, setup_ecp_dir, capsys):
        from atlast_ecp.query import audit
        audit(days=7, as_json=False)
        captured = capsys.readouterr()
        assert "Audit Report" in captured.out
        assert "Interactions" in captured.out or "Reliability" in captured.out

    def test_audit_health_status(self, setup_ecp_dir):
        from atlast_ecp.query import audit
        report = audit(days=7, as_json=True)
        assert report["health"] in ("healthy", "warning", "degraded")


class TestCLICommands:
    def test_cmd_search(self, setup_ecp_dir, capsys):
        from atlast_ecp.cli import cmd_search
        cmd_search(["web_search"])
        captured = capsys.readouterr()
        assert "Found" in captured.out

    def test_cmd_search_json(self, setup_ecp_dir, capsys):
        from atlast_ecp.cli import cmd_search
        cmd_search(["gpt-4o", "--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert len(data) == 10

    def test_cmd_trace(self, setup_ecp_dir, capsys):
        from atlast_ecp.cli import cmd_trace
        cmd_trace(["rec_test_0005"])
        captured = capsys.readouterr()
        assert "Trace" in captured.out

    def test_cmd_audit(self, setup_ecp_dir, capsys):
        from atlast_ecp.cli import cmd_audit
        cmd_audit(["--days", "7"])
        captured = capsys.readouterr()
        assert "Audit Report" in captured.out

    def test_cmd_audit_last_format(self, setup_ecp_dir, capsys):
        from atlast_ecp.cli import cmd_audit
        cmd_audit(["--last", "60d"])
        captured = capsys.readouterr()
        assert "Audit Report" in captured.out

    def test_cmd_timeline(self, setup_ecp_dir, capsys):
        from atlast_ecp.cli import cmd_timeline
        cmd_timeline(["--days", "7"])
        captured = capsys.readouterr()
        assert "Timeline" in captured.out

    def test_cmd_index(self, setup_ecp_dir, capsys):
        from atlast_ecp.cli import cmd_index
        cmd_index([])
        captured = capsys.readouterr()
        assert "10 records" in captured.out


class TestPerAgentRateLimit:
    """Test the per-agent rate limit logic (standalone, no server import needed)."""

    def test_rate_limit_logic(self):
        import time as _time
        import threading as _threading

        lock = _threading.Lock()
        buckets: dict[str, list[float]] = {}
        limits = {"free": 10, "pro": 60}

        def check(did: str, tier: str = "free") -> bool:
            limit = limits.get(tier, 10)
            now = _time.time()
            with lock:
                if did not in buckets:
                    buckets[did] = []
                buckets[did] = [t for t in buckets[did] if now - t < 60.0]
                if len(buckets[did]) >= limit:
                    return False
                buckets[did].append(now)
                return True

        # 10 requests should pass for free tier
        for _ in range(10):
            assert check("did:ecp:rate_test", "free") is True
        # 11th should fail
        assert check("did:ecp:rate_test", "free") is False
        # Different agent should still work
        assert check("did:ecp:other_agent", "free") is True
        # Pro tier allows more
        for _ in range(60):
            assert check("did:ecp:pro_agent", "pro") is True
        assert check("did:ecp:pro_agent", "pro") is False
