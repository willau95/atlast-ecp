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
            "anchor_trigger": "/v1/internal/anchor-now",
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
