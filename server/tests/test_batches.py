"""Tests for batch upload endpoint."""

import hashlib
import pytest

from server.merkle import build_merkle_root


def _make_batch_payload(agent_did: str, hashes: list[str] = None):
    """Helper to build a valid batch upload payload."""
    if hashes is None:
        hashes = [f"sha256:{hashlib.sha256(f'record{i}'.encode()).hexdigest()}" for i in range(3)]
    merkle_root = build_merkle_root(hashes)
    return {
        "agent_did": agent_did,
        "batch_ts": 1710700000000,
        "record_hashes": [
            {"record_id": f"rec_{i:016x}", "chain_hash": h, "step_type": "llm_call"}
            for i, h in enumerate(hashes)
        ],
        "merkle_root": merkle_root,
        "record_count": len(hashes),
        "flag_counts": {"hedged": 1, "high_latency": 0, "error": 0, "retried": 0, "incomplete": 0, "human_review": 0},
    }


def test_upload_batch(client, registered_agent):
    payload = _make_batch_payload(registered_agent["did"])
    resp = client.post("/v1/batches", json=payload, headers={"X-Agent-Key": registered_agent["api_key"]})
    assert resp.status_code == 201
    data = resp.json()
    assert data["record_count"] == 3
    assert data["status"] == "accepted"


def test_upload_batch_no_key(client, registered_agent):
    payload = _make_batch_payload(registered_agent["did"])
    resp = client.post("/v1/batches", json=payload)
    assert resp.status_code == 422  # missing header


def test_upload_batch_wrong_key(client, registered_agent):
    payload = _make_batch_payload(registered_agent["did"])
    resp = client.post("/v1/batches", json=payload, headers={"X-Agent-Key": "atl_wrong"})
    assert resp.status_code == 401


def test_upload_batch_wrong_did(client, registered_agent):
    payload = _make_batch_payload("did:ecp:wrong")
    resp = client.post("/v1/batches", json=payload, headers={"X-Agent-Key": registered_agent["api_key"]})
    assert resp.status_code == 403


def test_upload_batch_count_mismatch(client, registered_agent):
    payload = _make_batch_payload(registered_agent["did"])
    payload["record_count"] = 99
    resp = client.post("/v1/batches", json=payload, headers={"X-Agent-Key": registered_agent["api_key"]})
    assert resp.status_code == 400


def test_upload_batch_bad_merkle(client, registered_agent):
    payload = _make_batch_payload(registered_agent["did"])
    payload["merkle_root"] = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    resp = client.post("/v1/batches", json=payload, headers={"X-Agent-Key": registered_agent["api_key"]})
    assert resp.status_code == 400


def test_profile_after_batch(client, registered_agent):
    payload = _make_batch_payload(registered_agent["did"])
    client.post("/v1/batches", json=payload, headers={"X-Agent-Key": registered_agent["api_key"]})

    resp = client.get(f"/v1/agents/{registered_agent['handle']}/profile")
    data = resp.json()
    assert data["total_records"] == 3
    assert data["total_batches"] == 1
    assert data["trust_signals"]["reliability"] == 1.0
