"""Vault v4 — wire-level evidence tests (Phase 1).

Covers:
  - save_wire roundtrip: data on disk matches what we asked to store
  - deterministic wire_id (same inputs → same id)
  - sensitive header redaction
  - SSE vs JSON response handling
  - load_wire returns inlined body text
  - verify_wire_integrity catches tampering
  - is_disabled() honors ATLAST_WIRE_DISABLE
  - fail-open: bad inputs don't raise
"""
import json
import os
import time
from pathlib import Path

import pytest

from atlast_ecp import wire


@pytest.fixture
def isolated_ecp(tmp_path, monkeypatch):
    """Use a tmp dir as ~/.ecp; clear any wire-disable env."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ATLAST_WIRE_DISABLE", raising=False)
    return tmp_path / ".ecp"


def _save_basic(ecp_dir, *, sse=False):
    req = json.dumps({
        "model": "claude-sonnet-4-5",
        "max_tokens": 50,
        "system": "You are Claude.",
        "tools": [{"name": "add", "description": "add two", "input_schema": {"type": "object"}}],
        "messages": [{"role": "user", "content": "hi"}],
    }).encode()
    if sse:
        resp = b'event: message_start\ndata: {"type":"message_start"}\n\nevent: message_stop\ndata: {"type":"message_stop"}\n\n'
        ct = "text/event-stream"
    else:
        resp = json.dumps({"id": "msg_1", "content": [{"type": "text", "text": "pong"}]}).encode()
        ct = "application/json"
    return wire.save_wire(
        request_url="https://api.anthropic.com/v1/messages",
        request_method="POST",
        request_headers={"authorization": "Bearer sk-ant-oat01-VERYLONGSECRETVAL", "content-type": "application/json"},
        request_body_bytes=req,
        response_status=200,
        response_headers={"content-type": ct, "request-id": "req_test_001"},
        response_body_bytes=resp,
        response_content_type=ct,
        started_at=1000.0,
        finished_at=1001.5,
        provider="anthropic",
        ecp_dir=ecp_dir,
    )


# ── basics ────────────────────────────────────────────────────────────────


def test_save_wire_writes_files(isolated_ecp):
    summary = _save_basic(isolated_ecp, sse=False)
    assert summary is not None
    wire_id = summary["wire_id"]
    assert wire_id.startswith("wire_") and len(wire_id) == len("wire_") + 16

    wd = isolated_ecp / "vault" / "wire" / wire_id
    assert wd.is_dir()
    assert (wd / "meta.json").exists()
    assert (wd / "request.json").exists()
    assert (wd / "response.json").exists()  # JSON response
    assert not (wd / "response.sse").exists()


def test_save_wire_sse_writes_sse_file(isolated_ecp):
    summary = _save_basic(isolated_ecp, sse=True)
    wire_id = summary["wire_id"]
    wd = isolated_ecp / "vault" / "wire" / wire_id
    assert (wd / "response.sse").exists()
    assert not (wd / "response.json").exists()
    assert summary["is_sse"] is True


def test_meta_contains_full_schema(isolated_ecp):
    summary = _save_basic(isolated_ecp)
    meta = json.loads((isolated_ecp / "vault" / "wire" / summary["wire_id"] / "meta.json").read_text())

    assert meta["wire_version"] == 4
    assert meta["schema"] == "atlast.wire.v4"
    assert meta["wire_id"] == summary["wire_id"]
    assert meta["request"]["url"].endswith("/v1/messages")
    assert meta["request"]["body_sha256"].startswith("sha256:")
    assert meta["request"]["model"] == "claude-sonnet-4-5"
    assert meta["request"]["tool_count"] == 1
    assert meta["request"]["message_count"] == 1
    assert meta["response"]["status"] == 200
    assert meta["response"]["request_id"] == "req_test_001"
    assert meta["response"]["body_sha256"].startswith("sha256:")
    assert meta["timing"]["duration_ms"] == 1500


def test_authorization_header_redacted(isolated_ecp):
    summary = _save_basic(isolated_ecp)
    meta = json.loads((isolated_ecp / "vault" / "wire" / summary["wire_id"] / "meta.json").read_text())

    auth = meta["request"]["headers"]["authorization"]
    # Long token: first6 + "..." + last4
    assert auth.startswith("Bearer") or auth.startswith("Bearer".lower())  # only lower keys?
    # value is the redacted form, "Bearer sk-ant-oat01-VERYLONGSECRETVAL" → "Bearer...EVAL"
    assert "VERYLONGSECRETVAL" not in auth
    # content-type should be untouched
    assert meta["request"]["headers"]["content-type"] == "application/json"


# ── determinism ───────────────────────────────────────────────────────────


def test_wire_id_deterministic(isolated_ecp):
    s1 = _save_basic(isolated_ecp)
    s2 = _save_basic(isolated_ecp)
    assert s1["wire_id"] == s2["wire_id"]


def test_wire_id_changes_with_response(isolated_ecp):
    s1 = wire.save_wire(
        request_body_bytes=b'{"x":1}', response_body_bytes=b'{"y":1}',
        started_at=1.0, finished_at=2.0,
        request_headers={}, response_headers={}, ecp_dir=isolated_ecp,
    )
    s2 = wire.save_wire(
        request_body_bytes=b'{"x":1}', response_body_bytes=b'{"y":2}',  # diff
        started_at=1.0, finished_at=2.0,
        request_headers={}, response_headers={}, ecp_dir=isolated_ecp,
    )
    assert s1["wire_id"] != s2["wire_id"]


# ── load + integrity ─────────────────────────────────────────────────────


def test_load_wire_inlines_body_text(isolated_ecp):
    summary = _save_basic(isolated_ecp, sse=True)
    loaded = wire.load_wire(summary["wire_id"], ecp_dir=isolated_ecp)
    assert loaded is not None
    assert "body_text" in loaded["response"]
    assert "message_start" in loaded["response"]["body_text"]
    assert "body_text" in loaded["request"]


def test_load_wire_missing_returns_none(isolated_ecp):
    assert wire.load_wire("wire_doesnotexist", ecp_dir=isolated_ecp) is None


def test_verify_integrity_passes_clean(isolated_ecp):
    summary = _save_basic(isolated_ecp)
    res = wire.verify_wire_integrity(summary["wire_id"], ecp_dir=isolated_ecp)
    assert res["ok"] is True
    assert res["issues"] == []


def test_verify_integrity_detects_tampering(isolated_ecp):
    summary = _save_basic(isolated_ecp)
    p = isolated_ecp / "vault" / "wire" / summary["wire_id"] / "response.json"
    p.write_bytes(b'{"id":"tampered"}')  # rewrite with different content
    res = wire.verify_wire_integrity(summary["wire_id"], ecp_dir=isolated_ecp)
    assert res["ok"] is False
    assert any("sha mismatch" in i for i in res["issues"])


def test_verify_integrity_no_evidence(isolated_ecp):
    res = wire.verify_wire_integrity("wire_nonexistent", ecp_dir=isolated_ecp)
    assert res["ok"] is False
    assert res["reason"] == "no_wire_evidence"


# ── env opt-out ──────────────────────────────────────────────────────────


def test_atlast_wire_disable(monkeypatch, isolated_ecp):
    monkeypatch.setenv("ATLAST_WIRE_DISABLE", "1")
    summary = _save_basic(isolated_ecp)
    assert summary is None
    # No directory should have been created either
    assert not (isolated_ecp / "vault" / "wire").exists()


# ── fail-open ────────────────────────────────────────────────────────────


def test_save_with_no_bodies(isolated_ecp):
    """No request or response body — still produces a meta file with zero counts."""
    summary = wire.save_wire(
        request_headers={}, response_headers={},
        started_at=1.0, finished_at=1.0,
        ecp_dir=isolated_ecp,
    )
    assert summary is not None
    meta = json.loads((isolated_ecp / "vault" / "wire" / summary["wire_id"] / "meta.json").read_text())
    assert meta["request"]["body_bytes"] == 0
    assert meta["response"]["body_bytes"] == 0


def test_list_wire_ids(isolated_ecp):
    s1 = _save_basic(isolated_ecp, sse=False)
    s2 = _save_basic(isolated_ecp, sse=True)
    ids = wire.list_wire_ids(ecp_dir=isolated_ecp)
    assert s1["wire_id"] in ids
    assert s2["wire_id"] in ids
