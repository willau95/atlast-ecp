"""
Attestation query endpoints — public, read-only.

GET /v1/attestations/{batch_id}  — single batch attestation details
GET /v1/attestations             — list anchored attestations (paginated)
"""

import structlog
from fastapi import APIRouter, HTTPException, Query

from ..config import settings
from ..services.llachat_client import get_pending_batches

logger = structlog.get_logger()
router = APIRouter(tags=["Attestations"])

_is_testnet = settings.EAS_CHAIN == "sepolia"
_explorer_base = "https://base-sepolia.easscan.org" if _is_testnet else "https://base.easscan.org"


def _format_attestation(batch: dict) -> dict:
    """Format a batch dict into a public attestation response."""
    uid = batch.get("attestation_uid")
    return {
        "batch_id": batch["batch_id"],
        "agent_did": batch.get("agent_did"),
        "merkle_root": batch.get("merkle_root"),
        "record_count": batch.get("record_count", 0),
        "attestation_uid": uid,
        "eas_tx_hash": batch.get("eas_tx_hash"),
        "status": "anchored" if uid else "pending",
        "explorer_url": f"{_explorer_base}/attestation/view/{uid}" if uid else None,
        "chain": settings.EAS_CHAIN,
        "schema_uid": settings.EAS_SCHEMA_UID,
    }


@router.get("/v1/attestations/{batch_id}")
async def get_attestation(batch_id: str):
    """
    Look up attestation details for a specific batch.
    Proxies to LLaChat internal API.
    """
    # For now, we pull from pending-batches endpoint
    # In Phase 5, this will query Atlas's own DB
    import httpx
    url = f"{settings.LLACHAT_API_URL}/v1/batches/{batch_id}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail=f"Batch not found: {batch_id}")
            resp.raise_for_status()
            data = resp.json()
            return _format_attestation(data)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("attestation_fetch_failed", batch_id=batch_id, error=str(e))
        raise HTTPException(status_code=502, detail="Failed to fetch attestation data")


@router.get("/v1/attestations")
async def list_attestations(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: str = Query("all", pattern="^(all|anchored|pending)$"),
):
    """
    List attestations with pagination.
    Note: In Phase 5, this will use Atlas's own DB. Currently limited.
    """
    # For MVP, return info from pending-batches (limited view)
    return {
        "attestations": [],
        "total": 0,
        "limit": limit,
        "offset": offset,
        "note": "Full attestation listing available in Phase 5 (Atlas DB migration)",
    }
