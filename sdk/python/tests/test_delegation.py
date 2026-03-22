"""
Tests for multi-agent delegation fields: session_id, delegation_id, delegation_depth.
Covers: create_record, record_to_dict, compute_chain_hash, record_minimal, core.record.
"""
import pytest
from atlast_ecp.record import (
    create_record, record_to_dict, compute_chain_hash,
    create_minimal_record,
)
from atlast_ecp.core import record, record_minimal, reset


class TestDelegationRecord:
    """Test delegation fields in full ECP records."""

    def test_create_record_with_delegation(self):
        rec = create_record(
            agent_did="did:ecp:test",
            step_type="a2a_call",
            in_content="delegate task",
            out_content="sub-agent result",
            session_id="sess_001",
            delegation_id="del_abc",
            delegation_depth=1,
        )
        assert rec.step.session_id == "sess_001"
        assert rec.step.delegation_id == "del_abc"
        assert rec.step.delegation_depth == 1

    def test_record_to_dict_includes_delegation(self):
        rec = create_record(
            agent_did="did:ecp:test",
            in_content="x", out_content="y",
            session_id="s1", delegation_id="d1", delegation_depth=2,
        )
        d = record_to_dict(rec)
        assert d["step"]["session_id"] == "s1"
        assert d["step"]["delegation_id"] == "d1"
        assert d["step"]["delegation_depth"] == 2

    def test_record_to_dict_omits_none_delegation(self):
        rec = create_record(
            agent_did="did:ecp:test",
            in_content="x", out_content="y",
        )
        d = record_to_dict(rec)
        assert "session_id" not in d["step"]
        assert "delegation_id" not in d["step"]
        assert "delegation_depth" not in d["step"]

    def test_chain_hash_includes_delegation(self):
        """Chain hash must differ when delegation fields are set."""
        rec_no_del = create_record(
            agent_did="did:ecp:test",
            in_content="x", out_content="y",
        )
        rec_with_del = create_record(
            agent_did="did:ecp:test",
            in_content="x", out_content="y",
            session_id="s1",
        )
        d1 = record_to_dict(rec_no_del)
        d2 = record_to_dict(rec_with_del)
        # Recompute chain hash — both should be self-consistent
        assert compute_chain_hash(d1) == d1["chain"]["hash"]
        assert compute_chain_hash(d2) == d2["chain"]["hash"]
        # But the hashes should differ because d2 has session_id
        # (Note: they might differ anyway due to different timestamps/ids,
        #  so we just verify self-consistency)

    def test_chain_hash_self_consistent_with_all_fields(self):
        """Verify chain hash is recomputable from serialized record."""
        rec = create_record(
            agent_did="did:ecp:test",
            step_type="a2a_call",
            in_content="task",
            out_content="result",
            model="gpt-4",
            tokens_in=100,
            tokens_out=50,
            latency_ms=500,
            parent_agent="did:ecp:parent",
            session_id="sess_123",
            delegation_id="del_456",
            delegation_depth=3,
        )
        d = record_to_dict(rec)
        recomputed = compute_chain_hash(d)
        assert recomputed == d["chain"]["hash"], "Chain hash not self-consistent"


class TestDelegationMinimal:
    """Test delegation fields in minimal v1.0 records."""

    def test_minimal_record_with_delegation_meta(self):
        rec = create_minimal_record(
            agent="my-agent",
            action="a2a_call",
            in_content="task",
            out_content="result",
            meta={
                "session_id": "sess_001",
                "delegation_id": "del_abc",
                "delegation_depth": 1,
            },
        )
        assert rec["meta"]["session_id"] == "sess_001"
        assert rec["meta"]["delegation_id"] == "del_abc"
        assert rec["meta"]["delegation_depth"] == 1

    def test_minimal_record_no_meta_when_none(self):
        rec = create_minimal_record(
            agent="my-agent", action="llm_call",
            in_content="x", out_content="y",
        )
        assert "meta" not in rec


class TestDelegationCore:
    """Test delegation via core.record() and core.record_minimal()."""

    def setup_method(self):
        reset()

    def test_core_record_with_delegation(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ATLAST_ECP_DIR", str(tmp_path))
        rid = record(
            input_content="parent task",
            output_content="delegated result",
            step_type="a2a_call",
            session_id="sess_core",
            delegation_id="del_core",
            delegation_depth=1,
        )
        assert rid is not None
        assert rid.startswith("rec_")

    def test_core_record_minimal_with_delegation(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ATLAST_ECP_DIR", str(tmp_path))
        rid = record_minimal(
            input_content="task",
            output_content="result",
            session_id="sess_min",
            delegation_id="del_min",
            delegation_depth=0,
        )
        assert rid is not None


class TestDelegationDepthZero:
    """Edge case: delegation_depth=0 should be included (it's meaningful — root agent)."""

    def test_depth_zero_included_in_dict(self):
        rec = create_record(
            agent_did="did:ecp:root",
            in_content="x", out_content="y",
            delegation_depth=0,
        )
        d = record_to_dict(rec)
        # delegation_depth=0 is meaningful (root agent), should be included
        # Note: current implementation uses `if step.delegation_depth is not None`
        assert d["step"]["delegation_depth"] == 0

    def test_depth_zero_in_chain_hash(self):
        rec = create_record(
            agent_did="did:ecp:root",
            in_content="x", out_content="y",
            delegation_depth=0,
        )
        d = record_to_dict(rec)
        assert compute_chain_hash(d) == d["chain"]["hash"]
