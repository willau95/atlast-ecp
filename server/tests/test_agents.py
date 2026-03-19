"""Tests for agent registration and profile endpoints."""

import pytest


def test_register_agent(client):
    resp = client.post("/v1/agents/register", json={
        "did": "did:ecp:z6MkTest",
        "public_key": "dGVzdA==",
        "handle": "my-agent",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["did"] == "did:ecp:z6MkTest"
    assert data["handle"] == "my-agent"
    assert data["api_key"].startswith("atl_")
    assert len(data["api_key"]) == 36  # atl_ + 32 hex


def test_register_auto_handle(client):
    resp = client.post("/v1/agents/register", json={
        "did": "did:ecp:abcdef12",
        "public_key": "dGVzdA==",
    })
    assert resp.status_code == 201
    assert resp.json()["handle"].startswith("agent-")


def test_register_duplicate_did(client, registered_agent):
    resp = client.post("/v1/agents/register", json={
        "did": "did:ecp:test123",
        "public_key": "dGVzdA==",
        "handle": "another-handle",
    })
    assert resp.status_code == 409


def test_register_duplicate_handle(client, registered_agent):
    resp = client.post("/v1/agents/register", json={
        "did": "did:ecp:different",
        "public_key": "dGVzdA==",
        "handle": "test-agent",
    })
    assert resp.status_code == 409


def test_get_profile(client, registered_agent):
    resp = client.get("/v1/agents/test-agent/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert data["did"] == "did:ecp:test123"
    assert data["handle"] == "test-agent"
    assert data["total_records"] == 0
    assert data["total_batches"] == 0
    assert "trust_signals" in data


def test_get_profile_not_found(client):
    resp = client.get("/v1/agents/nonexistent/profile")
    assert resp.status_code == 404
