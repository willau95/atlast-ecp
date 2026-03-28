"""
Prometheus metrics endpoint.

GET /metrics — Prometheus-compatible metrics
"""

import secrets

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import PlainTextResponse
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

from ..config import settings

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

batch_upload_total = Counter(
    "ecp_batch_upload_total", "Total batch uploads", ["status"]
)
batch_upload_size = Histogram(
    "ecp_batch_upload_size_records", "Records per batch upload"
)
api_request_latency = Histogram(
    "ecp_api_request_latency_seconds", "API request latency", ["path"]
)


@router.get("/metrics")
async def metrics(x_internal_token: str = Header(None, alias="X-Internal-Token")):
    """Prometheus metrics endpoint. Requires internal token."""
    if not x_internal_token or not settings.LLACHAT_INTERNAL_TOKEN or \
       not secrets.compare_digest(x_internal_token, settings.LLACHAT_INTERNAL_TOKEN):
        raise HTTPException(status_code=401, detail="Internal token required")
    return PlainTextResponse(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
