"""
Tests for Prometheus metrics counters.

Verifies that counters/histograms are incremented by the relevant code paths.
"""

import pytest
from prometheus_client import REGISTRY


def _counter(metric_name: str, labels: dict) -> float:
    """Get current counter value (returns 0.0 if not yet set)."""
    value = REGISTRY.get_sample_value(metric_name + "_total", labels)
    return value or 0.0


def _histogram_count(metric_name: str, labels: dict | None = None) -> float:
    """Get histogram observation count (returns 0.0 if not yet set)."""
    value = REGISTRY.get_sample_value(metric_name + "_count", labels or {})
    return value or 0.0


# ── Direct counter/histogram increment tests ────────────────────────────────

class TestAnchorMetrics:
    def test_anchor_total_success_increments(self):
        from app.routes.metrics import anchor_total
        before = _counter("ecp_anchor", {"status": "success"})
        anchor_total.labels(status="success").inc()
        assert _counter("ecp_anchor", {"status": "success"}) == before + 1

    def test_anchor_total_error_increments(self):
        from app.routes.metrics import anchor_total
        before = _counter("ecp_anchor", {"status": "error"})
        anchor_total.labels(status="error").inc()
        assert _counter("ecp_anchor", {"status": "error"}) == before + 1

    def test_anchor_latency_observed(self):
        from app.routes.metrics import anchor_latency
        before = _histogram_count("ecp_anchor_latency_seconds")
        anchor_latency.observe(0.5)
        assert _histogram_count("ecp_anchor_latency_seconds") == before + 1

    def test_anchor_latency_observe_multiple(self):
        from app.routes.metrics import anchor_latency
        before = _histogram_count("ecp_anchor_latency_seconds")
        anchor_latency.observe(0.1)
        anchor_latency.observe(1.2)
        anchor_latency.observe(3.5)
        assert _histogram_count("ecp_anchor_latency_seconds") == before + 3


class TestWebhookMetrics:
    def test_webhook_success_increments(self):
        from app.routes.metrics import webhook_total
        before = _counter("ecp_webhook", {"status": "success"})
        webhook_total.labels(status="success").inc()
        assert _counter("ecp_webhook", {"status": "success"}) == before + 1

    def test_webhook_failed_increments(self):
        from app.routes.metrics import webhook_total
        before = _counter("ecp_webhook", {"status": "failed"})
        webhook_total.labels(status="failed").inc()
        assert _counter("ecp_webhook", {"status": "failed"}) == before + 1


class TestAttestationVerifyMetrics:
    def test_attestation_verify_valid(self):
        from app.routes.metrics import attestation_verify_total
        before = _counter("ecp_attestation_verify", {"result": "valid"})
        attestation_verify_total.labels(result="valid").inc()
        assert _counter("ecp_attestation_verify", {"result": "valid"}) == before + 1

    def test_attestation_verify_invalid(self):
        from app.routes.metrics import attestation_verify_total
        before = _counter("ecp_attestation_verify", {"result": "invalid"})
        attestation_verify_total.labels(result="invalid").inc()
        assert _counter("ecp_attestation_verify", {"result": "invalid"}) == before + 1

    def test_attestation_verify_not_found(self):
        from app.routes.metrics import attestation_verify_total
        before = _counter("ecp_attestation_verify", {"result": "not_found"})
        attestation_verify_total.labels(result="not_found").inc()
        assert _counter("ecp_attestation_verify", {"result": "not_found"}) == before + 1


class TestMerkleVerifyMetrics:
    def test_merkle_valid_increments(self):
        from app.routes.metrics import merkle_verify_total
        before = _counter("ecp_merkle_verify", {"result": "valid"})
        merkle_verify_total.labels(result="valid").inc()
        assert _counter("ecp_merkle_verify", {"result": "valid"}) == before + 1

    def test_merkle_invalid_increments(self):
        from app.routes.metrics import merkle_verify_total
        before = _counter("ecp_merkle_verify", {"result": "invalid"})
        merkle_verify_total.labels(result="invalid").inc()
        assert _counter("ecp_merkle_verify", {"result": "invalid"}) == before + 1


class TestCronFailureMetrics:
    def test_cron_failures_set_zero(self):
        from app.routes.metrics import cron_failures
        cron_failures.set(0)
        assert REGISTRY.get_sample_value("ecp_cron_consecutive_failures", {}) == 0.0

    def test_cron_failures_set_nonzero(self):
        from app.routes.metrics import cron_failures
        cron_failures.set(5)
        assert REGISTRY.get_sample_value("ecp_cron_consecutive_failures", {}) == 5.0
        cron_failures.set(0)  # reset


class TestBatchUploadMetrics:
    def test_batch_upload_total_success(self):
        from app.routes.metrics import batch_upload_total
        before = _counter("ecp_batch_upload", {"status": "success"})
        batch_upload_total.labels(status="success").inc()
        assert _counter("ecp_batch_upload", {"status": "success"}) == before + 1

    def test_batch_upload_total_failure(self):
        from app.routes.metrics import batch_upload_total
        before = _counter("ecp_batch_upload", {"status": "failure"})
        batch_upload_total.labels(status="failure").inc()
        assert _counter("ecp_batch_upload", {"status": "failure"}) == before + 1

    def test_batch_upload_size_histogram(self):
        from app.routes.metrics import batch_upload_size
        before = _histogram_count("ecp_batch_upload_size_records")
        batch_upload_size.observe(42)
        assert _histogram_count("ecp_batch_upload_size_records") == before + 1

    def test_batch_upload_size_histogram_zero_records(self):
        from app.routes.metrics import batch_upload_size
        before = _histogram_count("ecp_batch_upload_size_records")
        batch_upload_size.observe(0)
        assert _histogram_count("ecp_batch_upload_size_records") == before + 1


class TestApiRequestLatencyMetrics:
    def test_api_request_latency_observed(self):
        from app.routes.metrics import api_request_latency
        before = _histogram_count("ecp_api_request_latency_seconds", {"path": "/v1/health"})
        api_request_latency.labels(path="/v1/health").observe(0.01)
        assert _histogram_count("ecp_api_request_latency_seconds", {"path": "/v1/health"}) == before + 1

    def test_api_request_latency_different_paths(self):
        from app.routes.metrics import api_request_latency
        before_metrics = _histogram_count("ecp_api_request_latency_seconds", {"path": "/metrics"})
        before_verify = _histogram_count(
            "ecp_api_request_latency_seconds",
            {"path": "/v1/verify/{attestation_uid}"},
        )
        api_request_latency.labels(path="/metrics").observe(0.005)
        api_request_latency.labels(path="/v1/verify/{attestation_uid}").observe(0.020)
        assert _histogram_count("ecp_api_request_latency_seconds", {"path": "/metrics"}) == before_metrics + 1
        assert _histogram_count(
            "ecp_api_request_latency_seconds",
            {"path": "/v1/verify/{attestation_uid}"},
        ) == before_verify + 1


# ── Endpoint integration tests (pure-computation routes, no DB needed) ───────
# Use a single TestClient to avoid repeated app lifespan start/stop which causes
# "Event loop is closed" errors from apscheduler in CI.

import hashlib as _hashlib

@pytest.fixture(scope="module")
def test_client():
    """Shared TestClient — one app lifespan per module."""
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


class TestMerkleVerifyEndpointMetrics:
    """Verify that the /v1/verify/merkle endpoint increments the counter."""

    def test_valid_merkle_increments_counter(self, test_client):
        leaf = "sha256:" + _hashlib.sha256(b"test").hexdigest()
        before = _counter("ecp_merkle_verify", {"result": "valid"})

        resp = test_client.post(
            "/v1/verify/merkle",
            json={"merkle_root": leaf, "record_hashes": [leaf]},
        )

        assert resp.status_code == 200
        assert resp.json()["valid"] is True
        assert _counter("ecp_merkle_verify", {"result": "valid"}) == before + 1

    def test_invalid_merkle_increments_counter(self, test_client):
        leaf = "sha256:" + _hashlib.sha256(b"test").hexdigest()
        before = _counter("ecp_merkle_verify", {"result": "invalid"})

        resp = test_client.post(
            "/v1/verify/merkle",
            json={"merkle_root": "sha256:wrongrootvalue", "record_hashes": [leaf]},
        )

        assert resp.status_code == 200
        assert resp.json()["valid"] is False
        assert _counter("ecp_merkle_verify", {"result": "invalid"}) == before + 1


class TestAttestationVerifyEndpointMetrics:
    """Verify that GET /v1/verify/{uid} increments attestation_verify_total."""

    def test_verify_attestation_increments_counter(self, test_client):
        before = _counter("ecp_attestation_verify", {"result": "valid"})

        resp = test_client.get("/v1/verify/0xdeadbeef1234")

        assert resp.status_code == 200
        assert _counter("ecp_attestation_verify", {"result": "valid"}) == before + 1


class TestMetricsEndpointOutput:
    """Verify /metrics returns Prometheus text with our metric names."""

    def test_metrics_endpoint_contains_ecp_metrics(self, test_client):
        # Ensure at least one metric has been observed so it appears in output
        from app.routes.metrics import anchor_total
        anchor_total.labels(status="success").inc()

        resp = test_client.get("/metrics")

        assert resp.status_code == 200
        body = resp.text
        assert "ecp_anchor_total" in body
        assert "ecp_webhook_total" in body
        assert "ecp_merkle_verify_total" in body
        assert "ecp_attestation_verify_total" in body
        assert "ecp_cron_consecutive_failures" in body
        assert "ecp_batch_upload_total" in body
        assert "ecp_batch_upload_size_records" in body
        assert "ecp_api_request_latency_seconds" in body
