"""
.well-known/ecp.json — ECP Server Discovery Endpoint

Allows clients to discover ECP server capabilities and configuration.
"""

from fastapi import APIRouter
from ..config import settings

router = APIRouter()


@router.get("/.well-known/ecp.json")
async def ecp_discovery():
    return {
        "ecp_version": "1.0",
        "server": "atlast-ecp-server",
        "server_version": "1.0.0",
        "endpoints": {
            "health": "/v1/health",
            "stats": "/v1/stats",
            "verify_merkle": "/v1/verify/merkle",
            "verify_attestation": "/v1/verify/{attestation_uid}",
            "attestations": "/v1/attestations",
            "attestation_detail": "/v1/attestations/{batch_id}",
            "metrics": "/metrics",
            "anchor_trigger": "/v1/internal/anchor-now",
            "anchor_status": "/v1/internal/anchor-status",
            "cron_status": "/v1/internal/cron-status",
        },
        "eas": {
            "chain": settings.EAS_CHAIN,
            "chain_id": 84532 if settings.EAS_CHAIN == "sepolia" else 8453,
            "schema_uid": settings.EAS_SCHEMA_UID,
            "contract": "0x4200000000000000000000000000000000000021",
        },
        "capabilities": [
            "eas_anchoring",
            "webhook_dispatch",
            "batch_certification",
        ],
    }
