"""Tests for leaderboard endpoint."""

import hashlib
from server.merkle import build_merkle_root


def _register_and_upload(client, did: str, handle: str, record_count: int = 5):
    """Register agent + upload a batch."""
    reg = client.post("/v1/agents/register", json={
        "did": did, "public_key": "dGVzdA==", "handle": handle,
    })
    api_key = reg.json()["api_key"]

    hashes = [f"sha256:{hashlib.sha256(f'{handle}_{i}'.encode()).hexdigest()}" for i in range(record_count)]
    merkle_root = build_merkle_root(hashes)
    client.post("/v1/batches", json={
        "agent_did": did,
        "batch_ts": 1710700000000,
        "record_hashes": [{"record_id": f"rec_{i:016x}", "chain_hash": h} for i, h in enumerate(hashes)],
        "merkle_root": merkle_root,
        "record_count": record_count,
    }, headers={"X-Agent-Key": api_key})
    return api_key


def test_empty_leaderboard(client):
    resp = client.get("/v1/leaderboard")
    assert resp.status_code == 200
    assert resp.json()["agents"] == []


def test_leaderboard_with_agents(client):
    _register_and_upload(client, "did:ecp:a1", "agent-a", 10)
    _register_and_upload(client, "did:ecp:b2", "agent-b", 5)

    resp = client.get("/v1/leaderboard")
    data = resp.json()
    assert len(data["agents"]) == 2
    assert data["agents"][0]["rank"] == 1
    assert data["agents"][0]["record_count"] >= data["agents"][1]["record_count"]


def test_leaderboard_limit(client):
    for i in range(5):
        _register_and_upload(client, f"did:ecp:l{i}", f"agent-l{i}", 3)
    resp = client.get("/v1/leaderboard?limit=2")
    assert len(resp.json()["agents"]) == 2


def test_leaderboard_period(client):
    _register_and_upload(client, "did:ecp:p1", "agent-p1", 5)
    resp = client.get("/v1/leaderboard?period=7d")
    assert resp.status_code == 200
