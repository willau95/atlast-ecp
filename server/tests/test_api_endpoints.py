"""
Unit tests for ECP Server API endpoints.
Uses FastAPI TestClient — no external dependencies needed.
"""
import json
import hashlib
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """Create test client with EAS stub mode."""
    import os
    os.environ["EAS_STUB_MODE"] = "true"
    os.environ["EAS_CHAIN"] = "sepolia"
    os.environ["ENVIRONMENT"] = "test"
    os.environ["DATABASE_URL"] = ""  # Skip DB in tests
    os.environ["SENTRY_DSN"] = ""
    os.environ["LLACHAT_INTERNAL_TOKEN"] = "test-internal-token-123"
    os.environ["ECP_WEBHOOK_TOKEN"] = "test-webhook-token-456"
    os.environ["ECP_WEBHOOK_URL"] = ""

    from app.main import app
    return TestClient(app)


# ── Health ──────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_root(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["service"] == "ecp-server"
        assert data["version"] == "1.0.0"

    def test_health_v1(self, client):
        r = client.get("/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_health_has_eas_info(self, client):
        r = client.get("/v1/health")
        data = r.json()
        assert "eas_chain" in data
        assert "eas_stub" in data


# ── Discovery ──────────────────────────────────────────────────────────────

class TestDiscovery:
    def test_discovery_endpoint(self, client):
        r = client.get("/.well-known/ecp.json")
        assert r.status_code == 200
        data = r.json()
        assert data["ecp_version"] == "1.0"
        assert data["server"] == "atlast-ecp-server"

    def test_discovery_has_endpoints(self, client):
        r = client.get("/.well-known/ecp.json")
        eps = r.json()["endpoints"]
        assert "health" in eps
        assert "verify_merkle" in eps
        assert "attestations" in eps
        assert "metrics" in eps

    def test_discovery_has_eas(self, client):
        r = client.get("/.well-known/ecp.json")
        eas = r.json()["eas"]
        assert eas["chain"] == "sepolia"
        assert eas["chain_id"] == 84532
        assert eas["schema_uid"].startswith("0x")
        assert eas["contract"] == "0x4200000000000000000000000000000000000021"

    def test_discovery_has_capabilities(self, client):
        r = client.get("/.well-known/ecp.json")
        caps = r.json()["capabilities"]
        assert "eas_anchoring" in caps
        assert "webhook_dispatch" in caps


# ── Stats ──────────────────────────────────────────────────────────────────

class TestStats:
    def test_stats_endpoint(self, client):
        r = client.get("/v1/stats")
        assert r.status_code == 200
        data = r.json()
        assert "total_anchored" in data
        assert "total_errors" in data
        assert "total_webhooks_sent" in data
        assert "server_start" in data

    def test_stats_initial_values(self, client):
        r = client.get("/v1/stats")
        data = r.json()
        assert isinstance(data["total_anchored"], int)
        assert isinstance(data["total_errors"], int)


# ── Merkle Verification ───────────────────────────────────────────────────

def _sha256(data: str) -> str:
    return "sha256:" + hashlib.sha256(data.encode()).hexdigest()


class TestMerkleVerify:
    def test_single_hash(self, client):
        h = _sha256("test data")
        r = client.post("/v1/verify/merkle", json={
            "merkle_root": h,
            "record_hashes": [h]
        })
        assert r.status_code == 200
        assert r.json()["valid"] is True

    def test_two_hashes(self, client):
        h1 = _sha256("data1")
        h2 = _sha256("data2")
        root = _sha256(h1 + h2)
        r = client.post("/v1/verify/merkle", json={
            "merkle_root": root,
            "record_hashes": [h1, h2]
        })
        assert r.status_code == 200
        assert r.json()["valid"] is True

    def test_three_hashes_odd(self, client):
        """Odd number of hashes — last duplicated."""
        h1 = _sha256("a")
        h2 = _sha256("b")
        h3 = _sha256("c")
        # Layer 1: [hash(h1+h2), hash(h3+h3)]
        l1_0 = _sha256(h1 + h2)
        l1_1 = _sha256(h3 + h3)
        root = _sha256(l1_0 + l1_1)
        r = client.post("/v1/verify/merkle", json={
            "merkle_root": root,
            "record_hashes": [h1, h2, h3]
        })
        assert r.status_code == 200
        assert r.json()["valid"] is True

    def test_invalid_root(self, client):
        h = _sha256("test")
        r = client.post("/v1/verify/merkle", json={
            "merkle_root": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
            "record_hashes": [h]
        })
        assert r.status_code == 200
        assert r.json()["valid"] is False

    def test_empty_hashes_rejected(self, client):
        r = client.post("/v1/verify/merkle", json={
            "merkle_root": "sha256:abc",
            "record_hashes": []
        })
        assert r.status_code == 400

    def test_merkle_response_fields(self, client):
        h = _sha256("x")
        r = client.post("/v1/verify/merkle", json={
            "merkle_root": h,
            "record_hashes": [h]
        })
        data = r.json()
        assert "valid" in data
        assert "expected_root" in data
        assert "computed_root" in data
        assert "record_count" in data
        assert data["record_count"] == 1


# ── Attestation Verify ────────────────────────────────────────────────────

class TestAttestationVerify:
    def test_verify_returns_metadata(self, client):
        r = client.get("/v1/verify/0xabc123")
        assert r.status_code == 200
        data = r.json()
        assert data["attestation_uid"] == "0xabc123"
        assert data["chain"] == "sepolia"
        assert data["chain_id"] == 84532
        assert "explorer_url" in data

    def test_verify_explorer_url_format(self, client):
        r = client.get("/v1/verify/0xtest")
        url = r.json()["explorer_url"]
        assert "base-sepolia.easscan.org" in url
        assert "0xtest" in url


# ── Attestations List ─────────────────────────────────────────────────────

class TestAttestationsList:
    def test_list_no_db(self, client):
        """Without DB, returns empty list."""
        r = client.get("/v1/attestations")
        assert r.status_code == 200
        data = r.json()
        assert data["attestations"] == []
        assert data["total"] == 0

    def test_list_with_params(self, client):
        r = client.get("/v1/attestations?limit=5&offset=0&status=anchored")
        assert r.status_code == 200


# ── Internal Endpoints ────────────────────────────────────────────────────

class TestInternalEndpoints:
    def test_anchor_status_no_auth_in_test(self, client):
        """In test env (non-production), no auth required."""
        r = client.get("/v1/internal/anchor-status")
        assert r.status_code == 200
        data = r.json()
        assert data["service"] == "ecp-anchor"

    def test_cron_status_no_auth_in_test(self, client):
        r = client.get("/v1/internal/cron-status")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ["healthy", "degraded"]
        assert "interval_minutes" in data


# ── Metrics ───────────────────────────────────────────────────────────────

class TestMetrics:
    def test_metrics_endpoint(self, client):
        r = client.get("/metrics")
        assert r.status_code == 200
        assert "ecp_anchor_total" in r.text
        assert "ecp_webhook_total" in r.text
        assert "ecp_merkle_verify_total" in r.text

    def test_metrics_content_type(self, client):
        r = client.get("/metrics")
        assert "text/plain" in r.headers.get("content-type", "")


# ── Security Headers ─────────────────────────────────────────────────────

class TestSecurityHeaders:
    def test_security_headers_present(self, client):
        r = client.get("/v1/health")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("X-Frame-Options") == "DENY"
        assert "X-Request-ID" in r.headers

    def test_request_id_passthrough(self, client):
        r = client.get("/v1/health", headers={"X-Request-ID": "test-req-123"})
        assert r.headers.get("X-Request-ID") == "test-req-123"


# ── Request Size Limit ───────────────────────────────────────────────────

class TestRequestSizeLimit:
    def test_large_request_rejected(self, client):
        """Requests >10MB should be rejected."""
        r = client.post(
            "/v1/verify/merkle",
            content=b"x" * (11 * 1024 * 1024),
            headers={"Content-Type": "application/json", "Content-Length": str(11 * 1024 * 1024)}
        )
        assert r.status_code == 413
