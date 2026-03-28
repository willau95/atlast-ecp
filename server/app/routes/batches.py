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
from ..db.models import Agent, Batch, APIKey
from .auth import verify_api_key

logger = structlog.get_logger()
router = APIRouter()

# ── Per-Agent Rate Limiter ──────────────────────────────────────────────────
# Lightweight in-memory rate limit per agent DID.
# Limits: free=10/min, pro=60/min, enterprise=300/min

import time as _time
import threading as _threading

_agent_rate_lock = _threading.Lock()
_agent_rate_buckets: dict[str, list[float]] = {}
_RATE_LIMITS = {"free": 10, "pro": 60, "enterprise": 300}


_last_gc = _time.time()
_GC_INTERVAL = 300  # Clean stale buckets every 5 minutes


def _check_agent_rate(agent_did: str, tier: str = "free") -> bool:
    """Returns True if request is allowed, False if rate limited."""
    global _last_gc
    limit = _RATE_LIMITS.get(tier, 10)
    now = _time.time()
    window = 60.0  # 1 minute

    with _agent_rate_lock:
        # Periodic GC: remove agents with no recent activity
        if now - _last_gc > _GC_INTERVAL:
            stale = [k for k, v in _agent_rate_buckets.items() if not v or now - v[-1] > window]
            for k in stale:
                del _agent_rate_buckets[k]
            _last_gc = now

        if agent_did not in _agent_rate_buckets:
            _agent_rate_buckets[agent_did] = []

        # Prune old entries
        bucket = _agent_rate_buckets[agent_did]
        _agent_rate_buckets[agent_did] = [t for t in bucket if now - t < window]

        if len(_agent_rate_buckets[agent_did]) >= limit:
            return False

        _agent_rate_buckets[agent_did].append(now)
        return True


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

    rate_tier = "free"
    if api_key:
        try:
            agent_did, rate_tier = await verify_api_key(api_key)
            # Verify the DID matches the key's agent
            if agent_did != req.agent_did:
                raise HTTPException(
                    status_code=403,
                    detail="API key does not match agent_did in request",
                )
        except HTTPException as e:
            if e.status_code == 503:
                # DB not available — reject (fail-closed)
                raise HTTPException(status_code=503, detail="Database not available, cannot verify auth")
            raise
    else:
        # No API key — reject in production (fail-closed)
        if settings.ENVIRONMENT == "production":
            raise HTTPException(
                status_code=401,
                detail="API key required. Register at POST /v1/agents/register first.",
            )
        # Non-production: accept without auth for local development
        logger.warning("batch_upload_no_api_key_dev", did=req.agent_did)

    # Server-side signature verification (if agent has registered public_key)
    if api_key and req.sig and req.sig.startswith("ed25519:"):
        try:
            _session = await get_session()
            if _session is not None:
                from sqlalchemy import select
                async with _session:
                    agent_row = (await _session.execute(
                        select(Agent).where(Agent.did == req.agent_did)
                    )).scalar_one_or_none()
                    if agent_row and agent_row.public_key:
                        try:
                            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
                            sig_bytes = bytes.fromhex(req.sig[len("ed25519:"):])
                            pub_bytes = bytes.fromhex(agent_row.public_key)
                            public_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
                            public_key.verify(sig_bytes, req.merkle_root.encode())
                        except ImportError:
                            pass  # No cryptography package — skip verification
                        except Exception:
                            logger.warning("batch_sig_invalid", did=req.agent_did)
                            raise HTTPException(
                                status_code=400,
                                detail="Signature verification failed against registered public key",
                            )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("sig_verify_check_failed", error=str(e))

    # Per-agent rate limit
    if not _check_agent_rate(req.agent_did, rate_tier):
        limit = _RATE_LIMITS.get(rate_tier, 10)
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {limit} requests/min for {rate_tier} tier",
            headers={"Retry-After": "60"},
        )

    # Generate batch_id
    batch_id = f"batch_{secrets.token_hex(8)}"

    # Deduplication: reject if identical merkle_root from same agent within 5 minutes
    session = await get_session()
    if session is not None:
        try:
            from sqlalchemy import select, and_
            from datetime import timedelta
            from ..db.models import Batch as BatchModel
            async with session:
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
                dup = await session.execute(
                    select(BatchModel.batch_id).where(
                        and_(
                            BatchModel.agent_did == req.agent_did,
                            BatchModel.merkle_root == req.merkle_root,
                            BatchModel.created_at >= cutoff,
                        )
                    ).limit(1)
                )
                existing = dup.scalar_one_or_none()
                if existing:
                    return BatchUploadResponse(
                        batch_id=existing,
                        status="duplicate",
                        message="Identical batch already submitted within the last 5 minutes.",
                    )
        except Exception as e:
            logger.warning("dedup_check_failed", error=str(e))

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
                from .metrics import batch_upload_total, batch_upload_size
                batch_upload_total.labels(status="success").inc()
                batch_upload_size.observe(req.record_count)
        except Exception as e:
            logger.error("batch_store_failed", error=str(e), did=req.agent_did)
            from .metrics import batch_upload_total
            batch_upload_total.labels(status="failure").inc()
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
    """Get batch status by ID. Requires API key — returns only own batches."""
    api_key = x_api_key or x_agent_key
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")

    try:
        agent_did, _ = await verify_api_key(api_key)
    except HTTPException:
        raise HTTPException(status_code=401, detail="Invalid API key")

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

    # Verify ownership
    if batch.agent_did != agent_did:
        raise HTTPException(status_code=403, detail="Cannot access another agent's batch")

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
