"""
Prometheus metrics endpoint.

GET /metrics — Prometheus-compatible metrics
"""

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

router = APIRouter(tags=["Metrics"])

# ── Metrics ─────────────────────────────────────────────────────────────────

anchor_total = Counter(
    "ecp_anchor_total", "Total anchor operations", ["status"]
)
anchor_latency = Histogram(
    "ecp_anchor_latency_seconds", "Anchor operation latency"
)
webhook_total = Counter(
    "ecp_webhook_total", "Total webhook dispatches", ["status"]
)
attestation_verify_total = Counter(
    "ecp_attestation_verify_total", "Total attestation verifications", ["result"]
)
merkle_verify_total = Counter(
    "ecp_merkle_verify_total", "Total Merkle verifications", ["result"]
)
cron_failures = Gauge(
    "ecp_cron_consecutive_failures", "Consecutive cron failures"
)


@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return PlainTextResponse(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
