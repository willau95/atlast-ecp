"""Tests for ATLAST ECP Insights — local analysis tool."""

import json
import os
import subprocess
import sys
import time

import pytest

from atlast_ecp.core import record_minimal, reset
from atlast_ecp.insights import analyze_records, format_report


@pytest.fixture(autouse=True)
def clean_ecp(tmp_path):
    d = str(tmp_path / "ecp")
    old = os.environ.get("ATLAST_ECP_DIR")
    os.environ["ATLAST_ECP_DIR"] = d
    reset()
    yield d
    if old:
        os.environ["ATLAST_ECP_DIR"] = old
    else:
        os.environ.pop("ATLAST_ECP_DIR", None)


class TestAnalyzeRecords:

    def test_empty_records(self):
        result = analyze_records([])
        assert result["summary"]["total_records"] == 0
        assert len(result["recommendations"]) > 0

    def test_basic_summary(self):
        records = [
            {"ecp": "1.0", "id": "rec_001", "ts": 1000, "agent": "a1", "action": "llm_call",
             "in_hash": "sha256:x", "out_hash": "sha256:y", "meta": {"model": "gpt-4", "latency_ms": 500}},
            {"ecp": "1.0", "id": "rec_002", "ts": 2000, "agent": "a1", "action": "tool_call",
             "in_hash": "sha256:x", "out_hash": "sha256:y", "meta": {"model": "gpt-4", "latency_ms": 300}},
        ]
        result = analyze_records(records)
        assert result["summary"]["total_records"] == 2
        assert result["summary"]["unique_agents"] == 1
        assert result["summary"]["avg_latency_ms"] == 400

    def test_model_usage(self):
        records = [
            {"ecp": "1.0", "id": f"rec_{i}", "ts": i, "agent": "a", "action": "llm_call",
             "in_hash": "sha256:x", "out_hash": "sha256:y",
             "meta": {"model": "gpt-4" if i < 7 else "claude-sonnet-4-20250514"}}
            for i in range(10)
        ]
        result = analyze_records(records)
        assert len(result["model_usage"]) == 2
        assert result["model_usage"][0]["model"] == "gpt-4"
        assert result["model_usage"][0]["calls"] == 7

    def test_flag_analysis(self):
        records = [
            {"ecp": "1.0", "id": "rec_1", "ts": 1, "agent": "a", "action": "llm_call",
             "in_hash": "x", "out_hash": "y", "meta": {"flags": ["error", "high_latency"]}},
            {"ecp": "1.0", "id": "rec_2", "ts": 2, "agent": "a", "action": "llm_call",
             "in_hash": "x", "out_hash": "y", "meta": {"flags": ["error"]}},
            {"ecp": "1.0", "id": "rec_3", "ts": 3, "agent": "a", "action": "llm_call",
             "in_hash": "x", "out_hash": "y", "meta": {}},
        ]
        result = analyze_records(records)
        assert result["flags"]["error"]["count"] == 2
        assert result["high_latency_count"] == 1
        assert result["error_count"] == 2

    def test_recommendations_high_error_rate(self):
        records = [
            {"ecp": "1.0", "id": f"rec_{i}", "ts": i, "agent": "a", "action": "llm_call",
             "in_hash": "x", "out_hash": "y",
             "meta": {"flags": ["error"] if i < 8 else []}}
            for i in range(10)
        ]
        result = analyze_records(records)
        assert any("error rate" in r.lower() for r in result["recommendations"])

    def test_recommendations_high_latency(self):
        records = [
            {"ecp": "1.0", "id": f"rec_{i}", "ts": i, "agent": "a", "action": "llm_call",
             "in_hash": "x", "out_hash": "y",
             "meta": {"flags": ["high_latency"] if i < 5 else [], "latency_ms": 20000 if i < 5 else 500}}
            for i in range(10)
        ]
        result = analyze_records(records)
        assert any("latency" in r.lower() for r in result["recommendations"])

    def test_recommendations_clean(self):
        records = [
            {"ecp": "1.0", "id": f"rec_{i}", "ts": i, "agent": "a", "action": "llm_call",
             "in_hash": "x", "out_hash": "y", "meta": {"latency_ms": 200}}
            for i in range(10)
        ]
        result = analyze_records(records)
        assert any("no major issues" in r.lower() for r in result["recommendations"])

    def test_latency_by_model(self):
        records = [
            {"ecp": "1.0", "id": "rec_1", "ts": 1, "agent": "a", "action": "llm_call",
             "in_hash": "x", "out_hash": "y", "meta": {"model": "gpt-4", "latency_ms": 1000}},
            {"ecp": "1.0", "id": "rec_2", "ts": 2, "agent": "a", "action": "llm_call",
             "in_hash": "x", "out_hash": "y", "meta": {"model": "gpt-4", "latency_ms": 2000}},
            {"ecp": "1.0", "id": "rec_3", "ts": 3, "agent": "a", "action": "llm_call",
             "in_hash": "x", "out_hash": "y", "meta": {"model": "claude-sonnet-4-20250514", "latency_ms": 500}},
        ]
        result = analyze_records(records)
        assert result["latency_by_model"]["gpt-4"]["avg_ms"] == 1500
        assert result["latency_by_model"]["gpt-4"]["max_ms"] == 2000

    def test_token_counting(self):
        records = [
            {"ecp": "1.0", "id": "rec_1", "ts": 1, "agent": "a", "action": "llm_call",
             "in_hash": "x", "out_hash": "y", "meta": {"tokens_in": 100, "tokens_out": 50}},
            {"ecp": "1.0", "id": "rec_2", "ts": 2, "agent": "a", "action": "llm_call",
             "in_hash": "x", "out_hash": "y", "meta": {"tokens_in": 200, "tokens_out": 100}},
        ]
        result = analyze_records(records)
        assert result["summary"]["total_tokens_in"] == 300
        assert result["summary"]["total_tokens_out"] == 150
        assert result["summary"]["total_tokens"] == 450

    def test_v01_records_compatible(self):
        """Insights should handle v0.1 format too."""
        records = [
            {"ecp": "0.1", "id": "rec_1", "agent_did": "did:ecp:abc", "ts": 1000,
             "step": {"type": "llm_call", "in_hash": "sha256:x", "out_hash": "sha256:y"},
             "chain": {"prev": "genesis", "hash": "sha256:z"}, "sig": "ed25519:..."},
        ]
        result = analyze_records(records)
        assert result["summary"]["total_records"] == 1

    def test_multiple_agents(self):
        records = [
            {"ecp": "1.0", "id": f"rec_{i}", "ts": i, "agent": f"agent-{i % 3}", "action": "llm_call",
             "in_hash": "x", "out_hash": "y"}
            for i in range(9)
        ]
        result = analyze_records(records)
        assert result["summary"]["unique_agents"] == 3


class TestFormatReport:

    def test_format_not_empty(self):
        insights = analyze_records([
            {"ecp": "1.0", "id": "rec_1", "ts": 1, "agent": "a", "action": "llm_call",
             "in_hash": "x", "out_hash": "y", "meta": {"model": "gpt-4", "latency_ms": 500}}
        ])
        report = format_report(insights)
        assert "ATLAST ECP Insights" in report
        assert "gpt-4" in report

    def test_format_empty(self):
        insights = analyze_records([])
        report = format_report(insights)
        assert "0" in report


class TestInsightsCLI:

    def _record_via_cli(self, ecp_dir, agent="cli-test"):
        subprocess.run(
            [sys.executable, "-m", "atlast_ecp.cli", "record",
             "--in", "test prompt", "--out", "test response", "--agent", agent],
            capture_output=True, timeout=10,
            env={**os.environ, "ATLAST_ECP_DIR": ecp_dir},
        )

    def test_cli_insights_runs(self, clean_ecp):
        for _ in range(3):
            self._record_via_cli(clean_ecp)

        r = subprocess.run(
            [sys.executable, "-m", "atlast_ecp.cli", "insights"],
            capture_output=True, text=True, timeout=10,
            env={**os.environ, "ATLAST_ECP_DIR": clean_ecp},
        )
        assert r.returncode == 0
        assert "ATLAST ECP Insights" in r.stdout

    def test_cli_insights_json(self, clean_ecp):
        self._record_via_cli(clean_ecp, agent="json-test")

        r = subprocess.run(
            [sys.executable, "-m", "atlast_ecp.cli", "insights", "--json"],
            capture_output=True, text=True, timeout=10,
            env={**os.environ, "ATLAST_ECP_DIR": clean_ecp},
        )
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["summary"]["total_records"] >= 1


# ── P3-1: Sub-function tests ──────────────────────────────────────────────

from atlast_ecp.insights import (
    analyze_performance,
    analyze_trends,
    analyze_tools,
    format_performance_report,
    format_trends_report,
    format_tools_report,
)

# Sample records for sub-function testing
_SAMPLE_RECORDS = [
    {"ecp": "1.0", "id": "rec_01", "ts": 1710000000000, "agent": "did:ecp:aaa",
     "action": "llm_call", "in_hash": "sha256:a1", "out_hash": "sha256:b1",
     "meta": {"model": "gpt-4", "latency_ms": 500, "tokens_in": 100, "tokens_out": 200, "flags": []}},
    {"ecp": "1.0", "id": "rec_02", "ts": 1710000060000, "agent": "did:ecp:aaa",
     "action": "tool_call", "in_hash": "sha256:a2", "out_hash": "sha256:b2",
     "meta": {"tool": "web_search", "duration_ms": 1200, "flags": []}},
    {"ecp": "1.0", "id": "rec_03", "ts": 1710000120000, "agent": "did:ecp:aaa",
     "action": "llm_call", "in_hash": "sha256:a3", "out_hash": "sha256:b3",
     "meta": {"model": "gpt-4", "latency_ms": 800, "tokens_in": 150, "tokens_out": 300, "flags": ["error"]}},
    {"ecp": "1.0", "id": "rec_04", "ts": 1710086400000, "agent": "did:ecp:bbb",
     "action": "llm_call", "in_hash": "sha256:a4", "out_hash": "sha256:b4",
     "meta": {"model": "claude-3", "latency_ms": 300, "flags": []}},
    {"ecp": "1.0", "id": "rec_05", "ts": 1710086460000, "agent": "did:ecp:bbb",
     "action": "tool_call", "in_hash": "sha256:a5", "out_hash": "sha256:b5",
     "meta": {"tool": "web_search", "duration_ms": 900, "flags": ["error"]}},
]


class TestAnalyzePerformance:
    def test_basic(self):
        r = analyze_performance(_SAMPLE_RECORDS)
        assert r["total_records"] == 5
        assert r["avg_latency_ms"] > 0
        assert r["p50_latency_ms"] > 0
        assert r["p95_latency_ms"] >= r["p50_latency_ms"]
        assert r["max_latency_ms"] >= r["p95_latency_ms"]
        assert 0 < r["success_rate"] < 1.0  # 2 errors out of 5
        assert r["throughput_per_min"] >= 0  # can be tiny with spread-out records
        assert "gpt-4" in r["by_model"]
        assert "claude-3" in r["by_model"]

    def test_empty(self):
        r = analyze_performance([])
        assert r["total_records"] == 0
        assert r["success_rate"] == 1.0
        assert r["by_model"] == {}

    def test_success_rate(self):
        r = analyze_performance(_SAMPLE_RECORDS)
        # 2 errors out of 5 records
        assert r["success_rate"] == 0.6

    def test_format(self):
        r = analyze_performance(_SAMPLE_RECORDS)
        text = format_performance_report(r)
        assert "Performance" in text
        assert "gpt-4" in text


class TestAnalyzeTrends:
    def test_day_buckets(self):
        r = analyze_trends(_SAMPLE_RECORDS, bucket="day")
        assert r["bucket_size"] == "day"
        assert len(r["buckets"]) == 2  # Two different days

    def test_hour_buckets(self):
        r = analyze_trends(_SAMPLE_RECORDS, bucket="hour")
        assert r["bucket_size"] == "hour"
        assert len(r["buckets"]) >= 2

    def test_empty(self):
        r = analyze_trends([])
        assert r["buckets"] == []

    def test_error_counted(self):
        r = analyze_trends(_SAMPLE_RECORDS, bucket="day")
        total_errors = sum(b["error_count"] for b in r["buckets"])
        assert total_errors == 2

    def test_format(self):
        r = analyze_trends(_SAMPLE_RECORDS)
        text = format_trends_report(r)
        assert "Trends" in text

    def test_v01_records(self):
        """v0.1 records with ISO timestamp should work."""
        recs = [{"version": "0.1", "timestamp": "2026-03-20T00:00:00Z",
                 "agent_id": "a1", "execution": [{"step": 1, "action": "llm", "duration_ms": 100}]}]
        r = analyze_trends(recs)
        assert r["bucket_size"] == "day"
        assert len(r["buckets"]) == 1


class TestAnalyzeTools:
    def test_basic(self):
        r = analyze_tools(_SAMPLE_RECORDS)
        assert r["total_tool_calls"] == 2
        assert len(r["tools"]) == 1  # web_search
        assert r["tools"][0]["name"] == "web_search"
        assert r["tools"][0]["count"] == 2

    def test_empty(self):
        r = analyze_tools([])
        assert r["total_tool_calls"] == 0
        assert r["tools"] == []

    def test_error_rate(self):
        r = analyze_tools(_SAMPLE_RECORDS)
        # 1 error out of 2 web_search calls
        assert r["tools"][0]["error_rate"] == 0.5

    def test_format(self):
        r = analyze_tools(_SAMPLE_RECORDS)
        text = format_tools_report(r)
        assert "Tool Usage" in text
        assert "web_search" in text

    def test_no_tool_calls(self):
        """Records with only llm_call should return 0 tool calls."""
        recs = [{"ecp": "1.0", "id": "r1", "ts": 1710000000000, "agent": "a",
                 "action": "llm_call", "in_hash": "sha256:x", "out_hash": "sha256:y",
                 "meta": {"model": "gpt-4", "latency_ms": 100}}]
        r = analyze_tools(recs)
        assert r["total_tool_calls"] == 0


class TestAnalyzeRecordsBackwardCompat:
    """Ensure analyze_records() still returns the exact same keys after refactor."""

    def test_keys_unchanged(self):
        r = analyze_records(_SAMPLE_RECORDS)
        expected_keys = {"summary", "latency_by_model", "model_usage", "flags",
                         "error_count", "high_latency_count", "recommendations"}
        assert set(r.keys()) == expected_keys

    def test_summary_keys_unchanged(self):
        r = analyze_records(_SAMPLE_RECORDS)
        expected = {"total_records", "unique_agents", "agents", "action_breakdown",
                    "time_span_hours", "avg_latency_ms", "total_tokens_in",
                    "total_tokens_out", "total_tokens"}
        assert set(r["summary"].keys()) == expected
