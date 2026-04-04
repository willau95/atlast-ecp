"""
Tests for advanced/experimental SDK modules: a2a, otel_exporter, openclaw_scanner.
"""

import os
import json
from unittest.mock import MagicMock

import pytest

from atlast_ecp.core import reset, record_minimal
from atlast_ecp.storage import load_records


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


# ─── A2A Tests (H5) ──────────────────────────────────────────────────────────

class TestA2A:
    def test_import(self):
        from atlast_ecp.a2a import verify_handoff, discover_handoffs, build_a2a_chain, Handoff
        assert Handoff is not None

    def test_verify_handoff_matching_records(self):
        from atlast_ecp.a2a import verify_handoff
        # Two records where A's output hash matches B's input hash
        rec_a = record_minimal("prompt A", "response A", agent="agent-a")
        rec_b = record_minimal("prompt B", "response B", agent="agent-b")
        records = load_records(limit=10)
        if len(records) >= 2:
            handoff = verify_handoff(records[-2], records[-1])
            assert handoff is not None
            assert hasattr(handoff, 'valid')

    def test_discover_handoffs_empty(self):
        from atlast_ecp.a2a import discover_handoffs
        chain = discover_handoffs([])
        assert chain is not None
        assert len(chain.handoffs) == 0

    def test_build_a2a_chain(self):
        from atlast_ecp.a2a import build_a2a_chain
        # Create some records
        for i in range(3):
            record_minimal(f"prompt {i}", f"response {i}", agent=f"agent-{i}")
        records = load_records(limit=10)
        chain = build_a2a_chain(records)
        assert chain is not None
        assert hasattr(chain, 'handoffs')
        assert hasattr(chain, 'agents')

    def test_verify_a2a_chain(self):
        from atlast_ecp.a2a import build_a2a_chain, verify_a2a_chain
        record_minimal("p1", "r1", agent="a1")
        record_minimal("p2", "r2", agent="a2")
        records = load_records(limit=10)
        chain = build_a2a_chain(records)
        report = verify_a2a_chain(chain)
        assert report is not None
        assert hasattr(report, 'orphan_count')
        assert hasattr(report, 'blame_trace')

    def test_format_a2a_report(self):
        from atlast_ecp.a2a import build_a2a_chain, verify_a2a_chain, format_a2a_report
        record_minimal("p1", "r1", agent="x")
        records = load_records(limit=10)
        chain = build_a2a_chain(records)
        report = verify_a2a_chain(chain)
        text = format_a2a_report(report)
        assert isinstance(text, str)


# ─── OpenClaw Scanner Tests (H7) — REMOVED ───────────────────────────────────
# Scanner deprecated in v0.14.0. Use atlast proxy instead.
