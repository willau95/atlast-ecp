"""Tests for A2A multi-agent verification."""

import pytest
from atlast_ecp.a2a import (
    verify_handoff,
    discover_handoffs,
    build_a2a_chain,
    verify_a2a_chain,
    format_a2a_report,
    Handoff,
    A2AChain,
    A2AReport,
)
from atlast_ecp.record import hash_content


def _make_record(agent: str, action: str, input_text: str, output_text: str, ts: int, record_id: str = None):
    """Create a v1.0 ECP record."""
    return {
        "ecp": "1.0",
        "id": record_id or f"rec_{hash(input_text + output_text) & 0xFFFFFFFFFFFFFFFF:016x}",
        "ts": ts,
        "agent": agent,
        "action": action,
        "in_hash": hash_content(input_text),
        "out_hash": hash_content(output_text),
    }


def _make_v01_record(agent_did: str, input_text: str, output_text: str, ts: int, record_id: str = None):
    """Create a v0.1 ECP record (nested format)."""
    return {
        "ecp": "0.1",
        "id": record_id or f"rec_{hash(input_text) & 0xFFFFFFFFFFFFFFFF:016x}",
        "agent_did": agent_did,
        "ts": ts,
        "step": {
            "type": "llm_call",
            "in_hash": hash_content(input_text),
            "out_hash": hash_content(output_text),
        },
    }


# ─── Test verify_handoff ───


class TestVerifyHandoff:
    def test_valid_handoff(self):
        """Agent A outputs X, Agent B inputs X → valid handoff."""
        shared_data = "research results about quantum computing"
        r_a = _make_record("agent-a", "llm_call", "query", shared_data, ts=1000, record_id="rec_a1")
        r_b = _make_record("agent-b", "llm_call", shared_data, "summary", ts=2000, record_id="rec_b1")

        h = verify_handoff(r_a, r_b)
        assert h.valid is True
        assert h.causal_valid is True
        assert h.source_agent == "agent-a"
        assert h.target_agent == "agent-b"

    def test_handoff_batch_id_propagation(self):
        """batch_id from records should propagate to Handoff for Dashboard drill-down."""
        shared = "data payload"
        r_a = _make_record("agent-a", "llm_call", "q", shared, ts=1000, record_id="rec_a1")
        r_a["batch_id"] = "batch_aaa"
        r_b = _make_record("agent-b", "llm_call", shared, "out", ts=2000, record_id="rec_b1")
        r_b["batch_id"] = "batch_bbb"

        h = verify_handoff(r_a, r_b)
        assert h.valid is True
        assert h.source_batch_id == "batch_aaa"
        assert h.target_batch_id == "batch_bbb"

    def test_handoff_batch_id_none_when_absent(self):
        """batch_id should be None when not present in records."""
        shared = "data"
        r_a = _make_record("agent-a", "llm_call", "q", shared, ts=1000, record_id="rec_a1")
        r_b = _make_record("agent-b", "llm_call", shared, "out", ts=2000, record_id="rec_b1")

        h = verify_handoff(r_a, r_b)
        assert h.source_batch_id is None
        assert h.target_batch_id is None

    def test_invalid_handoff_hash_mismatch(self):
        r_a = _make_record("agent-a", "llm_call", "query", "result-a", ts=1000, record_id="rec_a1")
        r_b = _make_record("agent-b", "llm_call", "different-input", "result-b", ts=2000, record_id="rec_b1")

        h = verify_handoff(r_a, r_b)
        assert h.valid is False

    def test_causal_violation(self):
        """Target received data BEFORE source produced it."""
        shared = "data"
        r_a = _make_record("agent-a", "llm_call", "q", shared, ts=5000, record_id="rec_a1")
        r_b = _make_record("agent-b", "llm_call", shared, "out", ts=1000, record_id="rec_b1")

        h = verify_handoff(r_a, r_b)
        assert h.valid is True  # hash matches
        assert h.causal_valid is False  # but timeline is wrong

    def test_v01_format(self):
        shared = "handoff data"
        r_a = _make_v01_record("did:ecp:a", "q", shared, ts=1000, record_id="rec_a1")
        r_b = _make_v01_record("did:ecp:b", shared, "out", ts=2000, record_id="rec_b1")

        h = verify_handoff(r_a, r_b)
        assert h.valid is True


# ─── Test discover_handoffs ───


class TestDiscoverHandoffs:
    def test_simple_two_agent_pipeline(self):
        shared = "intermediate result"
        records = [
            _make_record("agent-a", "llm_call", "user query", shared, ts=1000, record_id="rec_a1"),
            _make_record("agent-b", "llm_call", shared, "final answer", ts=2000, record_id="rec_b1"),
        ]
        chain = discover_handoffs(records)
        assert len(chain.agents) == 2
        assert len(chain.handoffs) == 1
        assert chain.handoffs[0].valid is True

    def test_three_agent_chain(self):
        """A → B → C linear pipeline."""
        data_ab = "research data"
        data_bc = "analyzed data"
        records = [
            _make_record("researcher", "llm_call", "topic", data_ab, ts=1000, record_id="rec_r1"),
            _make_record("analyst", "llm_call", data_ab, data_bc, ts=2000, record_id="rec_an1"),
            _make_record("writer", "llm_call", data_bc, "final report", ts=3000, record_id="rec_w1"),
        ]
        chain = discover_handoffs(records)
        assert len(chain.agents) == 3
        assert len(chain.handoffs) == 2
        assert all(h.valid for h in chain.handoffs)

    def test_parallel_fanout(self):
        """A → B and A → C (parallel pipeline)."""
        shared = "shared data from A"
        records = [
            _make_record("agent-a", "llm_call", "input", shared, ts=1000, record_id="rec_a1"),
            _make_record("agent-b", "llm_call", shared, "result-b", ts=2000, record_id="rec_b1"),
            _make_record("agent-c", "llm_call", shared, "result-c", ts=2000, record_id="rec_c1"),
        ]
        chain = discover_handoffs(records)
        assert len(chain.handoffs) == 2  # A→B and A→C
        assert "agent-a" in chain.agents
        assert "agent-b" in chain.agents
        assert "agent-c" in chain.agents

    def test_orphan_output_detection(self):
        """Agent A produces output that no one consumes."""
        records = [
            _make_record("agent-a", "llm_call", "input", "output-nobody-reads", ts=1000, record_id="rec_a1"),
            _make_record("agent-b", "llm_call", "totally-different-input", "result-b", ts=2000, record_id="rec_b1"),
        ]
        chain = discover_handoffs(records)
        assert len(chain.handoffs) == 0
        assert len(chain.orphan_outputs) >= 1
        orphan_agents = [o["agent"] for o in chain.orphan_outputs]
        assert "agent-a" in orphan_agents

    def test_empty_records(self):
        chain = discover_handoffs([])
        assert chain.record_count == 0
        assert len(chain.handoffs) == 0

    def test_single_agent_no_handoff(self):
        """Single agent records → no handoffs, just orphans."""
        records = [
            _make_record("solo", "llm_call", "q1", "a1", ts=1000, record_id="rec_s1"),
            _make_record("solo", "llm_call", "q2", "a2", ts=2000, record_id="rec_s2"),
        ]
        chain = discover_handoffs(records)
        assert len(chain.handoffs) == 0
        assert len(chain.agents) == 1

    def test_mixed_v01_v10_formats(self):
        """v0.1 and v1.0 records in same chain."""
        shared = "cross-format data"
        records = [
            _make_v01_record("did:ecp:a", "query", shared, ts=1000, record_id="rec_a1"),
            _make_record("agent-b", "llm_call", shared, "result", ts=2000, record_id="rec_b1"),
        ]
        chain = discover_handoffs(records)
        assert len(chain.handoffs) == 1
        assert chain.handoffs[0].valid is True


# ─── Test verify_a2a_chain ───


class TestVerifyA2AChain:
    def test_valid_chain(self):
        shared = "handoff data"
        records = [
            _make_record("a", "llm_call", "input", shared, ts=1000, record_id="rec_a1"),
            _make_record("b", "llm_call", shared, "output", ts=2000, record_id="rec_b1"),
        ]
        chain = build_a2a_chain(records)
        report = verify_a2a_chain(chain)
        assert report.valid is True
        assert report.total_handoffs == 1
        assert report.invalid_handoffs == 0
        assert len(report.blame_trace) == 0

    def test_causal_violation_detected(self):
        shared = "data"
        records = [
            _make_record("a", "llm_call", "q", shared, ts=5000, record_id="rec_a1"),
            _make_record("b", "llm_call", shared, "out", ts=1000, record_id="rec_b1"),
        ]
        chain = build_a2a_chain(records)
        report = verify_a2a_chain(chain)
        assert report.valid is False
        assert report.causal_violations == 1
        assert any(b["type"] == "causal_violation" for b in report.blame_trace)

    def test_blame_trace_identifies_agent(self):
        shared = "data"
        records = [
            _make_record("agent-source", "llm_call", "q", shared, ts=5000, record_id="rec_s1"),
            _make_record("agent-target", "llm_call", shared, "out", ts=1000, record_id="rec_t1"),
        ]
        chain = build_a2a_chain(records)
        report = verify_a2a_chain(chain)
        blame = report.blame_trace[0]
        assert blame["source_agent"] == "agent-source"
        assert blame["target_agent"] == "agent-target"

    def test_no_handoffs_is_valid(self):
        """No handoffs found → still valid (nothing to break)."""
        records = [
            _make_record("a", "llm_call", "q1", "a1", ts=1000, record_id="rec_a1"),
        ]
        chain = build_a2a_chain(records)
        report = verify_a2a_chain(chain)
        assert report.valid is True
        assert report.total_handoffs == 0


# ─── Test format_a2a_report ───


class TestFormatReport:
    def test_valid_report_format(self):
        shared = "data"
        records = [
            _make_record("a", "llm_call", "q", shared, ts=1000, record_id="rec_a1"),
            _make_record("b", "llm_call", shared, "out", ts=2000, record_id="rec_b1"),
        ]
        chain = build_a2a_chain(records)
        report = verify_a2a_chain(chain)
        text = format_a2a_report(report)
        assert "✅ VALID" in text
        assert "a" in text
        assert "b" in text

    def test_invalid_report_format(self):
        shared = "data"
        records = [
            _make_record("x", "llm_call", "q", shared, ts=5000, record_id="rec_x1"),
            _make_record("y", "llm_call", shared, "out", ts=1000, record_id="rec_y1"),
        ]
        chain = build_a2a_chain(records)
        report = verify_a2a_chain(chain)
        text = format_a2a_report(report)
        assert "❌ INVALID" in text
        assert "Blame Trace" in text

    def test_orphan_in_report(self):
        records = [
            _make_record("a", "llm_call", "q", "orphan-output", ts=1000, record_id="rec_a1"),
        ]
        chain = build_a2a_chain(records)
        report = verify_a2a_chain(chain)
        text = format_a2a_report(report)
        assert "Orphan" in text
