"""
ECP Backend API Tests
Run: pytest tests/test_api.py -v
"""

import json
import os
import sys
import time
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["EAS_MODE"] = "stub"

import app.database as db_mod
from app.database import init_db

# ─── Setup ────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def setup_db(tmp_path):
    """Each test gets a fresh file-based DB (avoids SQLite :memory: isolation issue)."""
    db_path = str(tmp_path / "test_ecp.db")
    db_mod.DB_PATH = db_path
    os.environ["ECP_DB_PATH"] = db_path
    init_db()
    yield
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def client(setup_db):
    from app.main import app
    return TestClient(app)


# Shared test agent data
TEST_DID = "did:ecp:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
TEST_PUBKEY = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
TEST_MERKLE_ROOT = "sha256:aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899"
TEST_BATCH_TS = int(time.time() * 1000)


def register_test_agent(client: TestClient) -> dict:
    """Helper to register a test agent."""
    resp = client.post("/v1/agent/register", json={
        "did": TEST_DID,
        "public_key": TEST_PUBKEY,
        "name": "Test Agent",
        "description": "Test agent for unit tests",
        "owner_x_handle": "testuser",
    })
    assert resp.status_code == 200
    return resp.json()


# ─── Health ───────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["db"] == "ok"

    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["name"] == "ECP Backend API"


# ─── Agent Registration ───────────────────────────────────────────────────────

class TestAgentRegistration:
    def test_register_success(self, client):
        resp = client.post("/v1/agent/register", json={
            "did": TEST_DID,
            "public_key": TEST_PUBKEY,
            "name": "My Agent",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_did"] == TEST_DID
        assert "claim_url" in data
        assert "claim/" in data["claim_url"]
        assert data["status"] == "pending_verification"

    def test_register_generates_verification_tweet(self, client):
        resp = client.post("/v1/agent/register", json={
            "did": TEST_DID,
            "public_key": TEST_PUBKEY,
            "name": "Alex CTO",
            "owner_x_handle": "celestwong",
        })
        data = resp.json()
        assert "@LLaChat" in data["verification_tweet"]
        assert "#LLaChat" in data["verification_tweet"]
        assert "#WebA0" in data["verification_tweet"]

    def test_register_invalid_did_format(self, client):
        resp = client.post("/v1/agent/register", json={
            "did": "invalid-did",
            "public_key": TEST_PUBKEY,
        })
        assert resp.status_code == 422  # Validation error

    def test_register_invalid_pubkey_length(self, client):
        resp = client.post("/v1/agent/register", json={
            "did": TEST_DID,
            "public_key": "tooshort",
        })
        assert resp.status_code == 422

    def test_register_duplicate_unverified_allowed(self, client):
        """Re-registering an unverified agent should succeed with new claim token."""
        client.post("/v1/agent/register", json={"did": TEST_DID, "public_key": TEST_PUBKEY})
        resp = client.post("/v1/agent/register", json={"did": TEST_DID, "public_key": TEST_PUBKEY})
        assert resp.status_code == 200

    def test_register_verified_agent_rejected(self, client):
        """Cannot re-register an already-verified agent."""
        reg = register_test_agent(client)
        token = reg["claim_url"].split("/claim/")[1]
        client.post("/v1/agent/verify-claim", params={"claim_token": token})

        resp = client.post("/v1/agent/register", json={"did": TEST_DID, "public_key": TEST_PUBKEY})
        assert resp.status_code == 409


# ─── Batch Upload ─────────────────────────────────────────────────────────────

class TestBatchUpload:
    def test_batch_upload_success(self, client):
        register_test_agent(client)
        resp = client.post("/v1/batch", json={
            "agent_did": TEST_DID,
            "merkle_root": TEST_MERKLE_ROOT,
            "record_count": 10,
            "avg_latency_ms": 342,
            "batch_ts": TEST_BATCH_TS,
            "ecp_version": "0.1",
            "sig": "unverified",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "batch_id" in data
        assert data["batch_id"].startswith("batch_")
        assert data["status"] in ["pending_anchor", "already_received"]

    def test_batch_upload_unregistered_agent_rejected(self, client):
        resp = client.post("/v1/batch", json={
            "agent_did": "did:ecp:deadbeefdeadbeefdeadbeefdeadbeef",
            "merkle_root": TEST_MERKLE_ROOT,
            "record_count": 5,
            "avg_latency_ms": 100,
            "batch_ts": TEST_BATCH_TS,
            "sig": "unverified",
        })
        assert resp.status_code == 404

    def test_batch_upload_invalid_merkle_root_format(self, client):
        register_test_agent(client)
        resp = client.post("/v1/batch", json={
            "agent_did": TEST_DID,
            "merkle_root": "no-sha256-prefix",
            "record_count": 5,
            "avg_latency_ms": 100,
            "batch_ts": TEST_BATCH_TS,
            "sig": "unverified",
        })
        assert resp.status_code == 422

    def test_batch_idempotent(self, client):
        """Same batch uploaded twice returns same batch_id."""
        register_test_agent(client)
        payload = {
            "agent_did": TEST_DID,
            "merkle_root": TEST_MERKLE_ROOT,
            "record_count": 10,
            "avg_latency_ms": 100,
            "batch_ts": TEST_BATCH_TS,
            "sig": "unverified",
        }
        r1 = client.post("/v1/batch", json=payload)
        r2 = client.post("/v1/batch", json=payload)
        assert r1.json()["batch_id"] == r2.json()["batch_id"]

    def test_batch_with_record_hashes(self, client):
        """Batch with record_hashes enables per-record verification."""
        register_test_agent(client)
        resp = client.post("/v1/batch", json={
            "agent_did": TEST_DID,
            "merkle_root": TEST_MERKLE_ROOT,
            "record_count": 2,
            "avg_latency_ms": 200,
            "batch_ts": TEST_BATCH_TS,
            "sig": "unverified",
            "record_hashes": [
                {"id": "rec_abc123", "hash": "sha256:aabbccdd", "flags": ["hedged"]},
                {"id": "rec_def456", "hash": "sha256:eeff0011", "flags": []},
            ],
        })
        assert resp.status_code == 200

    def test_batch_with_flag_counts(self, client):
        """Flag counts should update agent stats."""
        register_test_agent(client)
        resp = client.post("/v1/batch", json={
            "agent_did": TEST_DID,
            "merkle_root": TEST_MERKLE_ROOT,
            "record_count": 100,
            "avg_latency_ms": 500,
            "batch_ts": TEST_BATCH_TS,
            "sig": "unverified",
            "flag_counts": {
                "retried": 5,
                "hedged": 23,
                "incomplete": 2,
                "error": 1,
                "human_review": 8,
            },
        })
        assert resp.status_code == 200

        # Verify stats updated in agent profile
        profile_resp = client.get(f"/v1/agent/{TEST_DID}")
        inputs = profile_resp.json()["trust_score_inputs"]
        assert inputs["total_records"] == 100
        assert inputs["flag_rates"]["hedged_rate"] == 0.23
        assert inputs["flag_rates"]["retried_rate"] == 0.05

    def test_get_batch_status(self, client):
        """GET /v1/batch/{batch_id} returns batch status."""
        register_test_agent(client)
        r = client.post("/v1/batch", json={
            "agent_did": TEST_DID,
            "merkle_root": TEST_MERKLE_ROOT,
            "record_count": 5,
            "avg_latency_ms": 100,
            "batch_ts": TEST_BATCH_TS,
            "sig": "unverified",
        })
        batch_id = r.json()["batch_id"]
        time.sleep(0.2)  # Let background task run

        resp = client.get(f"/v1/batch/{batch_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["batch_id"] == batch_id
        assert data["agent_did"] == TEST_DID
        assert data["merkle_root"] == TEST_MERKLE_ROOT
        # In stub mode, attestation_uid is set by background task
        assert "status" in data


# ─── Agent Profile ────────────────────────────────────────────────────────────

class TestAgentProfile:
    def test_get_profile_success(self, client):
        register_test_agent(client)
        resp = client.get(f"/v1/agent/{TEST_DID}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["did"] == TEST_DID
        assert data["name"] == "Test Agent"
        assert "trust_score_inputs" in data
        assert "profile_url" in data

    def test_get_profile_short_did(self, client):
        """Short DID (without did:ecp: prefix) should work."""
        register_test_agent(client)
        short_did = TEST_DID.replace("did:ecp:", "")
        resp = client.get(f"/v1/agent/{short_did}")
        assert resp.status_code == 200

    def test_get_profile_not_found(self, client):
        resp = client.get("/v1/agent/did:ecp:ffffffffffffffffffffffffffffffff")
        assert resp.status_code == 404

    def test_profile_trust_inputs_after_batches(self, client):
        """Trust Score inputs should aggregate across multiple batches."""
        register_test_agent(client)

        # Upload 3 batches
        for i in range(3):
            unique_root = f"sha256:{'a' * 60}{i:04d}"
            client.post("/v1/batch", json={
                "agent_did": TEST_DID,
                "merkle_root": unique_root,
                "record_count": 50,
                "avg_latency_ms": 300 + i * 50,
                "batch_ts": TEST_BATCH_TS + i * 3600000,
                "sig": "unverified",
                "flag_counts": {"hedged": 10, "retried": 2},
            })

        resp = client.get(f"/v1/agent/{TEST_DID}")
        inputs = resp.json()["trust_score_inputs"]
        assert inputs["total_records"] == 150
        assert inputs["total_batches"] == 3

    def test_no_confidence_anywhere(self, client):
        """'confidence' field must not appear anywhere in API responses."""
        register_test_agent(client)
        resp = client.get(f"/v1/agent/{TEST_DID}")
        response_str = json.dumps(resp.json())
        assert "confidence" not in response_str


# ─── Record Verification ──────────────────────────────────────────────────────

class TestVerification:
    def test_verify_unknown_record(self, client):
        resp = client.get("/v1/verify/rec_nonexistent0000")
        assert resp.status_code == 404

    def test_verify_uploaded_record(self, client):
        """After batch upload with record_hashes, record should be verifiable."""
        register_test_agent(client)
        client.post("/v1/batch", json={
            "agent_did": TEST_DID,
            "merkle_root": TEST_MERKLE_ROOT,
            "record_count": 1,
            "avg_latency_ms": 100,
            "batch_ts": TEST_BATCH_TS,
            "sig": "unverified",
            "record_hashes": [
                {"id": "rec_testrecord001", "hash": "sha256:aabbccdd", "flags": []},
            ],
        })

        resp = client.get("/v1/verify/rec_testrecord001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["record_id"] == "rec_testrecord001"
        assert data["agent_did"] == TEST_DID
        assert data["chain_hash"] == "sha256:aabbccdd"
        assert "verification_result" in data

    def test_verify_response_has_no_content(self, client):
        """Verify response must never contain actual content."""
        register_test_agent(client)
        client.post("/v1/batch", json={
            "agent_did": TEST_DID,
            "merkle_root": TEST_MERKLE_ROOT,
            "record_count": 1,
            "avg_latency_ms": 100,
            "batch_ts": TEST_BATCH_TS,
            "sig": "unverified",
            "record_hashes": [{"id": "rec_privacytest", "hash": "sha256:aabbccdd"}],
        })
        resp = client.get("/v1/verify/rec_privacytest")
        response_str = json.dumps(resp.json())
        # Should only contain hashes, never actual content
        assert "actual content" not in response_str
        assert "prompt" not in response_str
        assert "message" in resp.json()  # verification_result message
