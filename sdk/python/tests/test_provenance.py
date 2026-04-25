"""Phase 4 — agent.provenance record tests.

Provenance is fired once per session at the first observed (system, tools)
pair. We test the gate logic (no double-fire) and the recorded payload shape.
We mock the underlying record_minimal_v2 so we don't write to ~/.ecp/ during
the test.
"""
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture(autouse=True)
def reset_provenance_state():
    """Wipe the module-level idempotency set between tests."""
    from atlast_ecp import proxy
    proxy._session_provenance_emitted.clear()
    yield
    proxy._session_provenance_emitted.clear()


def _emit(**overrides):
    from atlast_ecp.proxy import _emit_provenance_if_needed
    kwargs = {
        "session_id": "sess_abc",
        "system_prompt": "You are Claude Code.",
        "tools_obj": [{"name": "Read", "input_schema": {}}, {"name": "Bash", "input_schema": {}}],
        "model": "claude-sonnet-4-5",
        "agent": "test-agent",
        "wire_summary": {"wire_id": "wire_abc123"},
    }
    kwargs.update(overrides)
    _emit_provenance_if_needed(**kwargs)


def test_provenance_fires_once_per_session():
    with patch("atlast_ecp.core.record_minimal_v2") as mock_rec:
        _emit()
        _emit()
        _emit()
    assert mock_rec.call_count == 1


def test_provenance_payload_shape():
    with patch("atlast_ecp.core.record_minimal_v2") as mock_rec:
        _emit()
    args, kwargs = mock_rec.call_args
    assert kwargs["action"] == "agent.provenance"
    assert kwargs["agent"] == "test-agent"
    assert kwargs["session_id"] == "sess_abc"
    assert "provenance" in (kwargs.get("flags") or [])

    import json as _json
    payload = _json.loads(kwargs["output_content"])
    assert payload["session_id"] == "sess_abc"
    assert payload["model"] == "claude-sonnet-4-5"
    assert payload["tool_count"] == 2
    assert sorted(payload["tool_names"]) == ["Bash", "Read"]
    assert payload["system_prompt_sha256"].startswith("sha256:")
    assert payload["tool_definitions_sha256"].startswith("sha256:")
    assert payload["wire_id"] == "wire_abc123"
    assert "claude_code_version" in payload["runtime"]


def test_provenance_skips_unknown_session():
    with patch("atlast_ecp.core.record_minimal_v2") as mock_rec:
        _emit(session_id="unknown")
        _emit(session_id="")
        _emit(session_id=None)
    assert mock_rec.call_count == 0


def test_provenance_independent_sessions():
    with patch("atlast_ecp.core.record_minimal_v2") as mock_rec:
        _emit(session_id="sess_a")
        _emit(session_id="sess_b")
        _emit(session_id="sess_a")  # repeat — should NOT fire again
    assert mock_rec.call_count == 2


def test_provenance_no_tools_still_fires():
    """A session with system prompt but no tools is still a valid agent."""
    with patch("atlast_ecp.core.record_minimal_v2") as mock_rec:
        _emit(tools_obj=None)
    assert mock_rec.call_count == 1
    import json as _json
    payload = _json.loads(mock_rec.call_args.kwargs["output_content"])
    assert payload["tool_count"] == 0
    assert payload["tool_definitions_sha256"] is None


def test_provenance_no_system_prompt_still_fires():
    """A session that defines tools but no system prompt is also valid."""
    with patch("atlast_ecp.core.record_minimal_v2") as mock_rec:
        _emit(system_prompt=None)
    assert mock_rec.call_count == 1
    import json as _json
    payload = _json.loads(mock_rec.call_args.kwargs["output_content"])
    assert payload["system_prompt_sha256"] is None


def test_provenance_failure_does_not_raise():
    """If record_minimal_v2 throws, _emit_provenance_if_needed must swallow.
    A failed provenance write should never break the agent's main flow."""
    with patch("atlast_ecp.core.record_minimal_v2", side_effect=RuntimeError("boom")):
        # Must not raise
        _emit()
