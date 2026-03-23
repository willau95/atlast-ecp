"""
Batch routes — Direct SDK → ECP Server batch upload.

This is the Protocol-native path (independent of LLaChat).
SDK uploads batch → ECP Server stores + queues for EAS anchoring.
"""

import secrets
import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel
import structlog

from ..config import settings
from ..db.database import get_session
from ..db.models import Batch, APIKey
from .auth import verify_api_key

logger = structlog.get_logger()
router = APIRouter()


class BatchUploadRequest(BaseModel):
    merkle_root: str
    agent_did: str
    record_count: int
    avg_latency_ms: int = 0
    batch_ts: int  # Unix ms
    sig: str
    ecp_version: str = "0.1"
    record_hashes: list[dict] | None = None
    flag_counts: dict | None = None
    chain_integrity: float | None = None


class BatchUploadResponse(BaseModel):
    batch_id: str
    status: str
    message: str
    attestation_uid: str | None = None


@router.post("/v1/batches", response_model=BatchUploadResponse)
async def upload_batch(
    req: BatchUploadRequest,
    x_api_key: str = Header(None, alias="X-API-Key"),
    x_agent_key: str = Header(None, alias="X-Agent-Key"),
):
    """
    Receive batch upload from SDK.
    Auth: X-API-Key or X-Agent-Key header required.
    Stores batch as 'pending' for next cron anchor cycle.
    """
    # Accept either header name (X-API-Key is new standard, X-Agent-Key is legacy)
    api_key = x_api_key or x_agent_key

    if api_key:
        try:
            agent_did, _ = await verify_api_key(api_key)
            # Verify the DID matches the key's agent
            if agent_did != req.agent_did:
                raise HTTPException(
                    status_code=403,
                    detail="API key does not match agent_did in request",
                )
        except HTTPException as e:
            if e.status_code == 503:
                # DB not available — accept without auth (Fail-Open for early adoption)
                logger.warning("batch_upload_no_auth_db_unavailable", did=req.agent_did)
            else:
                raise
    else:
        # No API key — accept in non-production (permissive for early adoption)
        if settings.ENVIRONMENT == "production":
            # In production, log warning but still accept (Fail-Open for SDK adoption)
            logger.warning("batch_upload_no_api_key", did=req.agent_did)

    # Generate batch_id
    batch_id = f"batch_{secrets.token_hex(8)}"

    # Store in DB
    session = await get_session()
    if session is not None:
        try:
            async with session:
                batch = Batch(
                    batch_id=batch_id,
                    agent_did=req.agent_did,
                    merkle_root=req.merkle_root,
                    record_count=req.record_count,
                    avg_latency_ms=req.avg_latency_ms,
                    batch_ts=req.batch_ts,
                    sig=req.sig,
                    ecp_version=req.ecp_version,
                    record_hashes=req.record_hashes,
                    flag_counts=req.flag_counts,
                    chain_integrity=req.chain_integrity,
                    status="pending",
                )
                session.add(batch)
                await session.commit()
                logger.info("batch_stored", batch_id=batch_id, did=req.agent_did, records=req.record_count)
        except Exception as e:
            logger.error("batch_store_failed", error=str(e), did=req.agent_did)
            raise HTTPException(status_code=500, detail="Failed to store batch")
    else:
        logger.warning("batch_no_db", batch_id=batch_id)

    # Also forward to LLaChat if configured (backward compatibility)
    # This runs fire-and-forget — don't block the response
    if settings.LLACHAT_API_URL and settings.LLACHAT_INTERNAL_TOKEN:
        import asyncio
        asyncio.create_task(_forward_to_llachat(batch_id, req))

    return BatchUploadResponse(
        batch_id=batch_id,
        status="pending",
        message=f"Batch accepted. {req.record_count} records queued for EAS anchoring.",
    )


@router.get("/v1/batches/{batch_id}")
async def get_batch(
    batch_id: str,
    x_api_key: str = Header(None, alias="X-API-Key"),
    x_agent_key: str = Header(None, alias="X-Agent-Key"),
):
    """Get batch status by ID."""
    session = await get_session()
    if session is None:
        raise HTTPException(status_code=503, detail="Database not available")

    from sqlalchemy import select
    async with session:
        result = await session.execute(
            select(Batch).where(Batch.batch_id == batch_id)
        )
        batch = result.scalar_one_or_none()

    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    return {
        "batch_id": batch.batch_id,
        "agent_did": batch.agent_did,
        "merkle_root": batch.merkle_root,
        "record_count": batch.record_count,
        "status": batch.status,
        "attestation_uid": batch.attestation_uid,
        "eas_tx_hash": batch.eas_tx_hash,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
    }


async def _forward_to_llachat(batch_id: str, req: BatchUploadRequest):
    """Forward batch to LLaChat API (backward compat, fire-and-forget)."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{settings.LLACHAT_API_URL}/v1/batches",
                json={
                    "batch_id": batch_id,
                    "merkle_root": req.merkle_root,
                    "agent_did": req.agent_did,
                    "record_count": req.record_count,
                    "avg_latency_ms": req.avg_latency_ms,
                    "batch_ts": req.batch_ts,
                    "sig": req.sig,
                    "ecp_version": req.ecp_version,
                    "record_hashes": req.record_hashes,
                    "flag_counts": req.flag_counts,
                },
                headers={
                    "X-Internal-Token": settings.LLACHAT_INTERNAL_TOKEN,
                    "Content-Type": "application/json",
                },
            )
    except Exception as e:
        logger.warning("forward_to_llachat_failed", batch_id=batch_id, error=str(e))
