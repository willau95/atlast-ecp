"""
Tests for P3 (API Key Management) and batch upload routes.
Uses FastAPI sync TestClient — no DB in test env.
"""

import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    os.environ["EAS_STUB_MODE"] = "true"
    os.environ["EAS_CHAIN"] = "sepolia"
    os.environ["ENVIRONMENT"] = "test"
    os.environ["DATABASE_URL"] = ""
    os.environ["SENTRY_DSN"] = ""
    os.environ["LLACHAT_INTERNAL_TOKEN"] = "test-token"
    os.environ["ECP_WEBHOOK_TOKEN"] = "test-webhook"
    os.environ["ECP_WEBHOOK_URL"] = ""

    from app.main import app
    return TestClient(app)


# ── Agent Registration ──────────────────────────────────────────────────────

class TestAgentRegistration:
    def test_register_returns_503_without_db(self, client):
        """Without DB, register returns 503."""
        resp = client.post("/v1/agents/register", json={
            "did": "did:ecp:test123",
            "public_key": "a" * 64,
        })
        assert resp.status_code == 503

    def test_register_missing_did(self, client):
        """Missing required 'did' field returns 422."""
        resp = client.post("/v1/agents/register", json={
            "public_key": "abc",
        })
        assert resp.status_code == 422


# ── Batch Upload ────────────────────────────────────────────────────────────

class TestBatchUpload:
    def test_batch_upload_no_db(self, client):
        """Without DB, batch is accepted but storage fails gracefully."""
        resp = client.post("/v1/batches", json={
            "merkle_root": "sha256:abc123",
            "agent_did": "did:ecp:test",
            "record_count": 5,
            "avg_latency_ms": 100,
            "batch_ts": 1234567890000,
            "sig": "ed25519:test",
        })
        # Without DB: may return 200 (no-DB path logs warning) or 500
        assert resp.status_code in (200, 500)

    def test_batch_upload_missing_required(self, client):
        """Missing required fields returns 422."""
        resp = client.post("/v1/batches", json={
            "merkle_root": "sha256:abc",
        })
        assert resp.status_code == 422

    def test_batch_upload_with_enrichment(self, client):
        """Batch with optional enrichment fields."""
        resp = client.post("/v1/batches", json={
            "merkle_root": "sha256:def456",
            "agent_did": "did:ecp:test2",
            "record_count": 3,
            "avg_latency_ms": 200,
            "batch_ts": 1234567890000,
            "sig": "ed25519:test2",
            "record_hashes": [{"id": "rec_1", "hash": "sha256:h1", "flags": ["error"]}],
            "flag_counts": {"error": 1},
            "chain_integrity": 0.95,
        })
        assert resp.status_code in (200, 500)

    def test_get_batch_requires_auth(self, client):
        """GET /v1/batches/{id} without API key returns 401."""
        resp = client.get("/v1/batches/batch_nonexistent")
        assert resp.status_code == 401


# ── Auth Me ─────────────────────────────────────────────────────────────────

class TestAuthMe:
    def test_me_no_key(self, client):
        """No API key returns 401."""
        resp = client.get("/v1/auth/me")
        assert resp.status_code == 401

    def test_me_invalid_key(self, client):
        """Invalid API key without DB returns 503."""
        resp = client.get("/v1/auth/me", headers={"X-API-Key": "ak_live_invalid"})
        assert resp.status_code == 503


# ── Rotate Key ──────────────────────────────────────────────────────────────

class TestRotateKey:
    def test_rotate_no_key(self, client):
        """Rotate without key returns 401."""
        resp = client.post("/v1/auth/rotate-key")
        assert resp.status_code == 401

    def test_rotate_invalid_key(self, client):
        """Rotate with invalid key without DB returns 503."""
        resp = client.post("/v1/auth/rotate-key", headers={"X-API-Key": "ak_live_bad"})
        assert resp.status_code == 503
