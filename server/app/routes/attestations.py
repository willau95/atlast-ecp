"""
Attestation query endpoints — public, read-only.

GET /v1/attestations/{batch_id}  — single batch attestation details
GET /v1/attestations             — list anchored attestations (paginated)
"""

import structlog
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, func, desc

from ..config import settings
from ..db.database import get_session, Attestation

logger = structlog.get_logger()
router = APIRouter(tags=["Attestations"])

_is_testnet = settings.EAS_CHAIN == "sepolia"
_explorer_base = "https://base-sepolia.easscan.org" if _is_testnet else "https://base.easscan.org"


def _format_attestation(row: Attestation) -> dict:
    """Format a DB row into a public attestation response."""
    uid = row.attestation_uid
    return {
        "batch_id": row.batch_id,
        "agent_did": row.agent_did,
        "merkle_root": row.merkle_root,
        "record_count": row.record_count,
        "attestation_uid": uid,
        "eas_tx_hash": row.eas_tx_hash,
        "status": "anchored" if uid else "pending",
        "explorer_url": f"{_explorer_base}/attestation/view/{uid}" if uid else None,
        "chain": settings.EAS_CHAIN,
        "schema_uid": settings.EAS_SCHEMA_UID,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "anchored_at": row.anchored_at.isoformat() if row.anchored_at else None,
    }


import re

_BATCH_ID_RE = re.compile(r"^(batch_[a-f0-9]{16}|sb_[a-f0-9]{16})$")


@router.get("/v1/attestations/{batch_id}")
async def get_attestation(batch_id: str):
    """Look up attestation details for a specific batch."""
    if not _BATCH_ID_RE.match(batch_id):
        raise HTTPException(status_code=400, detail="Invalid batch_id format")
    session = await get_session()
    if session is None:
        # DB not configured — fallback to LLaChat proxy
        return await _proxy_attestation(batch_id)

    async with session:
        result = await session.execute(
            select(Attestation).where(Attestation.batch_id == batch_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail=f"Batch not found: {batch_id}")
        return _format_attestation(row)


@router.get("/v1/attestations")
async def list_attestations(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    agent_did: str = Query(None),
    status: str = Query("all", pattern="^(all|anchored|pending)$"),
):
    """List attestations with pagination."""
    session = await get_session()
    if session is None:
        return {"attestations": [], "total": 0, "limit": limit, "offset": offset}

    async with session:
        # Build query
        query = select(Attestation)
        count_query = select(func.count(Attestation.id))

        if agent_did:
            query = query.where(Attestation.agent_did == agent_did)
            count_query = count_query.where(Attestation.agent_did == agent_did)
        if status == "anchored":
            query = query.where(Attestation.on_chain == True)
            count_query = count_query.where(Attestation.on_chain == True)
        elif status == "pending":
            query = query.where(Attestation.on_chain == False)
            count_query = count_query.where(Attestation.on_chain == False)

        query = query.order_by(desc(Attestation.created_at)).offset(offset).limit(limit)

        result = await session.execute(query)
        rows = result.scalars().all()
        total_result = await session.execute(count_query)
        total = total_result.scalar()

        return {
            "attestations": [_format_attestation(r) for r in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


async def _proxy_attestation(batch_id: str) -> dict:
    """Fallback: proxy to LLaChat API when DB not configured."""
    import httpx
    url = f"{settings.LLACHAT_API_URL}/v1/batches/{batch_id}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail=f"Batch not found: {batch_id}")
            resp.raise_for_status()
            data = resp.json()
            uid = data.get("attestation_uid")
            return {
                "batch_id": data["batch_id"],
                "agent_did": data.get("agent_did"),
                "merkle_root": data.get("merkle_root"),
                "record_count": data.get("record_count", 0),
                "attestation_uid": uid,
                "eas_tx_hash": data.get("eas_tx_hash"),
                "status": "anchored" if uid else "pending",
                "explorer_url": f"{_explorer_base}/attestation/view/{uid}" if uid else None,
                "chain": settings.EAS_CHAIN,
                "schema_uid": settings.EAS_SCHEMA_UID,
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("attestation_proxy_failed", batch_id=batch_id, error=str(e))
        raise HTTPException(status_code=502, detail="Failed to fetch attestation data")
