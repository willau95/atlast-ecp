"""Tests for ATLAST Scoring Rules engine."""
import json
import os
import pytest
from unittest.mock import patch

from atlast_ecp.scoring_rules import (
    classify_record,
    classify_records,
    calculate_scores,
    aggregate_interactions,
    get_rules,
    reset_cache,
    DEFAULT_RULES,
)


# ─── classify_record() ────────────────────────────────────────────────────────

class TestClassifyRecord:
    """Test single record classification."""

    def test_normal_interaction(self):
        """Normal user↔agent conversation = interaction."""
        result = classify_record(flags=[], input_text="hello", output_text="hi there")
        assert result == "interaction"

    def test_heartbeat(self):
        """Heartbeat flag → heartbeat classification."""
        result = classify_record(flags=["heartbeat"], input_text="HEARTBEAT", output_text="HEARTBEAT_OK")
        assert result == "heartbeat"

    def test_heartbeat_with_other_flags(self):
        """Heartbeat should win even with other flags present."""
        result = classify_record(flags=["heartbeat", "streaming"], input_text="HEARTBEAT", output_text="HEARTBEAT_OK")
        assert result == "heartbeat"

    def test_system_error_provider(self):
        """Provider error flag → system_error."""
        result = classify_record(
            flags=["provider_error", "http_4xx"],
            output_text='{"type":"error","error":{"message":"Third-party apps"}}',
        )
        assert result == "system_error"

    def test_system_error_billing(self):
        """Billing error in output → system_error."""
        result = classify_record(
            flags=["provider_error"],
            output_text="billing quota exceeded",
        )
        assert result == "system_error"

    def test_system_error_auth(self):
        """Auth error → system_error."""
        result = classify_record(
            flags=["provider_error"],
            output_text="authentication failed invalid api_key",
        )
        assert result == "system_error"

    def test_infra_error_500(self):
        """HTTP 5xx → infra_error."""
        result = classify_record(flags=["http_5xx"], output_text="internal server error")
        assert result == "infra_error"

    def test_infra_error_429(self):
        """Rate limit (legacy infra_error flag) → infra_error."""
        result = classify_record(flags=["infra_error"], output_text="rate limit exceeded")
        assert result == "infra_error"

    def test_infra_error_overloaded(self):
        """Overloaded → infra_error."""
        result = classify_record(flags=["http_5xx"], output_text="service overloaded try again")
        assert result == "infra_error"

    def test_tool_intermediate_tool_call(self):
        """Tool call with empty output → tool_intermediate."""
        result = classify_record(
            flags=["has_tool_calls", "empty_output"],
            output_text="",
        )
        assert result == "tool_intermediate"

    def test_tool_intermediate_tool_continuation(self):
        """Tool continuation (tool_result in request) with empty output → tool_intermediate."""
        result = classify_record(
            flags=["tool_continuation", "empty_output"],
            output_text="",
        )
        assert result == "tool_intermediate"

    def test_tool_call_with_text_is_interaction(self):
        """Tool call with substantial text output = interaction, not intermediate."""
        result = classify_record(
            flags=["has_tool_calls"],
            output_text="Here's the file content you asked for, and I've also created the new file.",
        )
        assert result == "interaction"

    def test_empty_flags_is_interaction(self):
        """No flags at all → interaction."""
        result = classify_record(flags=[], input_text="help me", output_text="sure")
        assert result == "interaction"

    def test_only_behavioral_flags_is_interaction(self):
        """Only behavioral flags (hedged, high_latency) → still interaction."""
        result = classify_record(
            flags=["hedged", "high_latency"],
            output_text="I think maybe this could work",
        )
        assert result == "interaction"

    def test_streaming_is_interaction(self):
        """Streaming flag alone → interaction."""
        result = classify_record(flags=["streaming"], output_text="response text")
        assert result == "interaction"

    def test_error_flag_is_interaction(self):
        """Agent error → still interaction (counts toward score)."""
        result = classify_record(flags=["error"], output_text="Traceback: ...")
        assert result == "interaction"

    def test_priority_heartbeat_over_system(self):
        """Heartbeat should be classified before system_error (order matters)."""
        result = classify_record(
            flags=["heartbeat", "provider_error"],
            output_text="billing error",
        )
        assert result == "heartbeat"

    def test_custom_rules(self):
        """Custom rules can be passed to override defaults."""
        custom = {
            "classification": [
                {"label": "custom_exclude", "conditions": {"any_flag": ["my_flag"]}},
                {"label": "interaction", "conditions": {"default": True}},
            ]
        }
        result = classify_record(flags=["my_flag"], rules=custom)
        assert result == "custom_exclude"

    def test_none_flags_treated_as_empty(self):
        """None flags should not crash."""
        result = classify_record(flags=None, output_text="hello")
        assert result == "interaction"

    def test_http_4xx_without_provider_error_is_interaction(self):
        """HTTP 4xx alone without provider_error flag → interaction (might be agent's fault)."""
        result = classify_record(flags=["http_4xx"], output_text="bad request from agent")
        assert result == "interaction"


# ─── classify_records() ───────────────────────────────────────────────────────

class TestClassifyRecords:
    """Test bulk record classification."""

    def test_mixed_records(self):
        """Classify a mix of record types."""
        records = [
            {"flags": [], "input": "hello", "output": "hi"},
            {"flags": ["heartbeat"], "input": "HEARTBEAT", "output": "OK"},
            {"flags": ["provider_error"], "output": "billing error"},
            {"flags": ["http_5xx"], "output": "500 internal server error"},
            {"flags": ["has_tool_calls", "empty_output"], "output": ""},
        ]
        results = classify_records(records)
        assert len(results) == 5
        assert results[0]["classification"] == "interaction"
        assert results[1]["classification"] == "heartbeat"
        assert results[2]["classification"] == "system_error"
        assert results[3]["classification"] == "infra_error"
        assert results[4]["classification"] == "tool_intermediate"

    def test_empty_list(self):
        """Empty list returns empty list."""
        assert classify_records([]) == []

    def test_original_record_preserved(self):
        """Original record fields should be preserved."""
        records = [{"id": "rec_123", "flags": [], "input": "hi", "output": "hey", "custom": "data"}]
        results = classify_records(records)
        assert results[0]["id"] == "rec_123"
        assert results[0]["custom"] == "data"
        assert results[0]["classification"] == "interaction"

    def test_raw_record_format(self):
        """Support raw .jsonl record format with meta/step nesting."""
        records = [
            {"meta": {"flags": ["heartbeat"]}, "input": "HEARTBEAT", "output": "OK"},
            {"step": {"flags": ["error"]}, "input": "do thing", "output": "Traceback:"},
        ]
        results = classify_records(records)
        assert results[0]["classification"] == "heartbeat"
        assert results[1]["classification"] == "interaction"  # error is still interaction


# ─── calculate_scores() ──────────────────────────────────────────────────────

class TestCalculateScores:
    """Test score calculation from classified records."""

    def test_all_interactions(self):
        """All records are interactions → full scoring."""
        records = [
            {"classification": "interaction", "flags": [], "meta": {"latency_ms": 1000}},
            {"classification": "interaction", "flags": [], "meta": {"latency_ms": 2000}},
            {"classification": "interaction", "flags": [], "meta": {"latency_ms": 3000}},
        ]
        scores = calculate_scores(records)
        assert scores["total_records"] == 3
        assert scores["interactions"] == 3
        assert scores["reliability"] == 1.0
        assert scores["avg_latency_ms"] == 2000
        assert scores["error_rate"] == 0.0

    def test_excluded_records(self):
        """Excluded records don't count toward scoring."""
        records = [
            {"classification": "interaction", "flags": [], "meta": {"latency_ms": 1000}},
            {"classification": "heartbeat", "flags": ["heartbeat"], "meta": {"latency_ms": 500}},
            {"classification": "system_error", "flags": ["provider_error"], "meta": {"latency_ms": 100}},
            {"classification": "infra_error", "flags": ["http_5xx"], "meta": {"latency_ms": 50}},
            {"classification": "tool_intermediate", "flags": ["has_tool_calls"], "meta": {"latency_ms": 200}},
        ]
        scores = calculate_scores(records)
        assert scores["total_records"] == 5
        assert scores["interactions"] == 1
        assert scores["excluded"]["heartbeat"] == 1
        assert scores["excluded"]["system_error"] == 1
        assert scores["excluded"]["infra_error"] == 1
        assert scores["excluded"]["tool_intermediate"] == 1
        assert scores["reliability"] == 1.0
        assert scores["avg_latency_ms"] == 1000  # only interaction latency

    def test_agent_errors_affect_reliability(self):
        """Agent errors reduce reliability score."""
        records = [
            {"classification": "interaction", "flags": ["error"], "meta": {"latency_ms": 1000}},
            {"classification": "interaction", "flags": [], "meta": {"latency_ms": 2000}},
            {"classification": "interaction", "flags": [], "meta": {"latency_ms": 3000}},
            {"classification": "interaction", "flags": ["error"], "meta": {"latency_ms": 4000}},
        ]
        scores = calculate_scores(records)
        assert scores["interactions"] == 4
        assert scores["reliability"] == 0.5  # 2 errors / 4 interactions
        assert scores["error_rate"] == 0.5

    def test_empty_records(self):
        """No records → default scores."""
        scores = calculate_scores([])
        assert scores["total_records"] == 0
        assert scores["interactions"] == 0
        assert scores["reliability"] == 0.5  # Unknown, not perfect

    def test_all_excluded(self):
        """All records excluded → default scores."""
        records = [
            {"classification": "heartbeat", "flags": ["heartbeat"]},
            {"classification": "heartbeat", "flags": ["heartbeat"]},
        ]
        scores = calculate_scores(records)
        assert scores["total_records"] == 2
        assert scores["interactions"] == 0
        assert scores["reliability"] == 0.5  # Unknown, not perfect

    def test_hedge_and_incomplete_rates(self):
        """Hedged and incomplete flags are tracked."""
        records = [
            {"classification": "interaction", "flags": ["hedged"], "meta": {"latency_ms": 1000}},
            {"classification": "interaction", "flags": ["incomplete"], "meta": {"latency_ms": 2000}},
            {"classification": "interaction", "flags": [], "meta": {"latency_ms": 3000}},
        ]
        scores = calculate_scores(records)
        assert scores["hedge_rate"] == round(1/3, 4)
        assert scores["incomplete_rate"] == round(1/3, 4)

    def test_high_latency_rate(self):
        """High latency rate from flags."""
        records = [
            {"classification": "interaction", "flags": ["high_latency"], "meta": {"latency_ms": 20000}},
            {"classification": "interaction", "flags": [], "meta": {"latency_ms": 1000}},
        ]
        scores = calculate_scores(records)
        assert scores["high_latency_rate"] == 0.5

    def test_elena_scenario(self):
        """
        Simulate Elena's 9 records from the real test.
        Expected: 3 interactions, 3 heartbeats, 1 system_error, 2 tool_intermediate.
        """
        records = [
            # Round 1: tweet (complete, no tool)
            {"classification": "interaction", "flags": ["streaming", "high_latency"],
             "meta": {"latency_ms": 12347}},
            # Round 2: profile (tool chain)
            {"classification": "tool_intermediate", "flags": ["has_tool_calls", "empty_output", "streaming"],
             "meta": {"latency_ms": 66166}},
            {"classification": "interaction", "flags": ["streaming", "high_latency"],
             "meta": {"latency_ms": 8864}},
            # Round 3: game (tool chain with 3 calls)
            {"classification": "tool_intermediate", "flags": ["has_tool_calls", "empty_output", "streaming"],
             "meta": {"latency_ms": 12168}},
            {"classification": "tool_intermediate", "flags": ["tool_continuation", "has_tool_calls", "empty_output"],
             "meta": {"latency_ms": 90653}},
            {"classification": "interaction", "flags": ["streaming", "high_latency"],
             "meta": {"latency_ms": 11481}},
            # Heartbeats
            {"classification": "heartbeat", "flags": ["heartbeat"],
             "meta": {"latency_ms": 2349}},
            {"classification": "system_error", "flags": ["provider_error", "heartbeat"],
             "meta": {"latency_ms": 584}},
            {"classification": "heartbeat", "flags": ["heartbeat"],
             "meta": {"latency_ms": 2102}},
        ]
        scores = calculate_scores(records)
        assert scores["total_records"] == 9
        assert scores["interactions"] == 3
        assert scores["excluded"].get("heartbeat", 0) == 2
        assert scores["excluded"].get("system_error", 0) == 1
        assert scores["excluded"].get("tool_intermediate", 0) == 3
        assert scores["reliability"] == 1.0  # no agent errors
        # Latency only from 3 interactions
        expected_avg = int((12347 + 8864 + 11481) / 3)
        assert scores["avg_latency_ms"] == expected_avg


# ─── get_rules() ──────────────────────────────────────────────────────────────

class TestGetRules:
    """Test rules loading and caching."""

    def setup_method(self):
        reset_cache()

    def test_returns_default_rules(self):
        """When no cache or server, returns defaults."""
        rules = get_rules()
        assert rules["version"] == DEFAULT_RULES["version"]
        assert "classification" in rules
        assert "scoring" in rules

    def test_cache_works(self):
        """Second call uses cache."""
        r1 = get_rules()
        r2 = get_rules()
        assert r1 is r2  # same object from cache

    def test_reset_cache(self):
        """reset_cache clears the cache."""
        get_rules()
        reset_cache()
        # After reset, should re-fetch (will get defaults again)
        r = get_rules()
        assert r is not None

    def test_local_cache_file(self, tmp_path):
        """Local cache file is used when present."""
        custom_rules = {"version": "custom", "classification": [], "scoring": {}}
        cache_file = tmp_path / "scoring_rules_cache.json"
        cache_file.write_text(json.dumps(custom_rules))

        reset_cache()
        with patch.dict(os.environ, {"ATLAST_ECP_DIR": str(tmp_path)}):
            rules = get_rules()
            assert rules["version"] == "custom"


# ─── Integration: classify + score pipeline ───────────────────────────────────

class TestAggregateInteractions:
    """Test tool chain aggregation."""

    def test_no_tool_calls(self):
        """Records without tool chains pass through unchanged."""
        records = [
            {"classification": "interaction", "ts": 1, "session_id": "s1", "input": "hi", "output": "hey"},
            {"classification": "interaction", "ts": 2, "session_id": "s1", "input": "bye", "output": "cya"},
        ]
        result = aggregate_interactions(records)
        assert len(result) == 2
        assert "tool_steps" not in result[0]

    def test_simple_tool_chain(self):
        """Two-step tool chain: tool_intermediate + interaction → 1 aggregated."""
        records = [
            {"classification": "tool_intermediate", "ts": 1, "session_id": "s1",
             "id": "rec_001", "input": "write code", "output": "",
             "meta": {"latency_ms": 5000},
             "vault_extra": {"tool_calls": [{"name": "write_file", "input": {"path": "x.py"}}]}},
            {"classification": "interaction", "ts": 2, "session_id": "s1",
             "id": "rec_002", "input": "", "output": "Done! File created.",
             "meta": {"latency_ms": 3000}},
        ]
        result = aggregate_interactions(records)
        assert len(result) == 1
        assert result[0]["classification"] == "interaction"
        assert result[0]["total_api_calls"] == 2
        assert result[0]["total_latency_ms"] == 8000
        assert len(result[0]["tool_steps"]) == 1
        assert result[0]["tool_steps"][0]["name"] == "write_file"
        assert result[0]["raw_record_ids"] == ["rec_001", "rec_002"]

    def test_three_step_tool_chain(self):
        """Three-step: intermediate → intermediate → interaction."""
        records = [
            {"classification": "tool_intermediate", "ts": 1, "session_id": "s1",
             "id": "r1", "meta": {"latency_ms": 1000},
             "vault_extra": {"tool_calls": [{"name": "read_file", "input": {}}]}},
            {"classification": "tool_intermediate", "ts": 2, "session_id": "s1",
             "id": "r2", "meta": {"latency_ms": 2000},
             "vault_extra": {"tool_calls": [{"name": "write_file", "input": {}}]}},
            {"classification": "interaction", "ts": 3, "session_id": "s1",
             "id": "r3", "output": "All done", "meta": {"latency_ms": 3000}},
        ]
        result = aggregate_interactions(records)
        assert len(result) == 1
        assert result[0]["total_api_calls"] == 3
        assert result[0]["total_latency_ms"] == 6000
        assert len(result[0]["tool_steps"]) == 2

    def test_mixed_with_heartbeat(self):
        """Tool chain + heartbeat → heartbeat stays separate."""
        records = [
            {"classification": "tool_intermediate", "ts": 1, "session_id": "s1",
             "id": "r1", "meta": {"latency_ms": 1000}, "vault_extra": {"tool_calls": []}},
            {"classification": "heartbeat", "ts": 2, "session_id": "s2",
             "id": "r2", "meta": {"latency_ms": 100}},
            {"classification": "interaction", "ts": 3, "session_id": "s1",
             "id": "r3", "output": "Done", "meta": {"latency_ms": 2000}},
        ]
        result = aggregate_interactions(records)
        # The heartbeat breaks the chain — r1 flushed standalone, then heartbeat, then r3
        assert len(result) == 3

    def test_different_sessions_not_merged(self):
        """Tool chains from different sessions are not merged."""
        records = [
            {"classification": "tool_intermediate", "ts": 1, "session_id": "s1",
             "id": "r1", "meta": {"latency_ms": 1000}, "vault_extra": {"tool_calls": []}},
            {"classification": "interaction", "ts": 2, "session_id": "s2",
             "id": "r2", "output": "Different session", "meta": {"latency_ms": 500}},
        ]
        result = aggregate_interactions(records)
        assert len(result) == 2  # not merged

    def test_empty_list(self):
        result = aggregate_interactions([])
        assert result == []

    def test_elena_full_scenario(self):
        """Simulate Elena's 9 records → should produce 3 interactions + 2 heartbeats + 1 system."""
        records = [
            # Round 1: tweet (no tool, direct response)
            {"classification": "interaction", "ts": 1, "session_id": "s1",
             "id": "r1", "input": "写tweet", "output": "两条tweet...",
             "meta": {"latency_ms": 12347}},
            # Round 2: profile (tool chain: 2 API calls)
            {"classification": "tool_intermediate", "ts": 2, "session_id": "s1",
             "id": "r2", "input": "做html profile", "output": "",
             "meta": {"latency_ms": 66166},
             "vault_extra": {"tool_calls": [{"name": "write_file", "input": {"path": "profile.html"}}]}},
            {"classification": "interaction", "ts": 3, "session_id": "s1",
             "id": "r3", "output": "搞定！profile已创建",
             "meta": {"latency_ms": 8864}},
            # Round 3: game (tool chain: 3 API calls)
            {"classification": "tool_intermediate", "ts": 4, "session_id": "s1",
             "id": "r4", "input": "加小游戏", "output": "",
             "meta": {"latency_ms": 12168},
             "vault_extra": {"tool_calls": [{"name": "read_file", "input": {}}]}},
            {"classification": "tool_intermediate", "ts": 5, "session_id": "s1",
             "id": "r5", "output": "",
             "meta": {"latency_ms": 90653},
             "vault_extra": {"tool_calls": [{"name": "write_file", "input": {}}]}},
            {"classification": "interaction", "ts": 6, "session_id": "s1",
             "id": "r6", "output": "小游戏已嵌入",
             "meta": {"latency_ms": 11481}},
            # Heartbeats
            {"classification": "heartbeat", "ts": 7, "session_id": "s1",
             "id": "r7", "meta": {"latency_ms": 2349}},
            {"classification": "system_error", "ts": 8, "session_id": "s1",
             "id": "r8", "meta": {"latency_ms": 584}},
            {"classification": "heartbeat", "ts": 9, "session_id": "s1",
             "id": "r9", "meta": {"latency_ms": 2102}},
        ]
        result = aggregate_interactions(records)

        # Should be: 3 interactions (1 standalone + 2 aggregated) + 2 heartbeats + 1 system
        interactions = [r for r in result if r.get("classification") == "interaction"]
        heartbeats = [r for r in result if r.get("classification") == "heartbeat"]
        system_errors = [r for r in result if r.get("classification") == "system_error"]

        assert len(interactions) == 3
        assert len(heartbeats) == 2
        assert len(system_errors) == 1

        # First interaction: standalone tweet
        assert "tool_steps" not in interactions[0]

        # Second interaction: profile (2 API calls)
        assert interactions[1]["total_api_calls"] == 2
        assert len(interactions[1]["tool_steps"]) == 1
        assert interactions[1]["tool_steps"][0]["name"] == "write_file"

        # Third interaction: game (3 API calls)
        assert interactions[2]["total_api_calls"] == 3
        assert len(interactions[2]["tool_steps"]) == 2


class TestPipeline:
    """Test the full classify → score pipeline."""

    def setup_method(self):
        reset_cache()

    def test_end_to_end(self):
        """Full pipeline from raw records to scores."""
        raw_records = [
            {"flags": [], "input": "hello", "output": "world", "meta": {"latency_ms": 500}},
            {"flags": ["heartbeat"], "input": "HEARTBEAT", "output": "OK", "meta": {"latency_ms": 100}},
            {"flags": ["error"], "input": "break", "output": "Traceback:", "meta": {"latency_ms": 200}},
            {"flags": ["provider_error"], "input": "x", "output": "billing error", "meta": {"latency_ms": 50}},
        ]
        classified = classify_records(raw_records)
        scores = calculate_scores(classified)

        assert scores["interactions"] == 2  # hello + error
        assert scores["excluded"].get("heartbeat", 0) == 1
        assert scores["excluded"].get("system_error", 0) == 1
        assert scores["reliability"] == 0.5  # 1 error / 2 interactions

    def test_full_pipeline_with_aggregation(self):
        """classify → aggregate → score pipeline."""
        raw_records = [
            {"flags": ["has_tool_calls", "empty_output", "streaming"], "ts": 1,
             "input": "write code", "output": "", "meta": {"latency_ms": 5000, "session_id": "s1"}},
            {"flags": ["tool_continuation", "streaming"], "ts": 2,
             "input": "", "output": "Done!", "meta": {"latency_ms": 3000, "session_id": "s1"}},
            {"flags": ["heartbeat"], "ts": 3,
             "input": "HEARTBEAT", "output": "OK", "meta": {"latency_ms": 100}},
        ]
        classified = classify_records(raw_records)
        aggregated = aggregate_interactions(classified)
        scores = calculate_scores(aggregated)

        # Tool chain → 1 interaction, heartbeat → excluded
        assert scores["interactions"] == 1
        assert scores["excluded"].get("heartbeat", 0) == 1
        assert scores["reliability"] == 1.0
