"""
Anchor routes — manual trigger + cron-compatible endpoint.
"""

import secrets
from fastapi import APIRouter, Header, HTTPException
import structlog

from ..config import settings
from ..services.llachat_client import get_pending_batches, mark_batch_anchored
from ..services.eas import write_attestation
from ..services.webhook import fire_attestation_webhook

from ..db.database import get_session, Attestation

from ..services.merkle import build_super_merkle_tree, get_inclusion_proof
from ..services.monitoring import capture_error
import json as json_lib
import uuid as _uuid

logger = structlog.get_logger()
router = APIRouter()


async def _save_attestation(batch: dict, attestation_uid: str, eas_tx_hash: str | None):
    """Persist anchored attestation to local DB. Fail-open: DB errors don't block anchoring."""
    try:
        session = await get_session()
        if session is None:
            return
        from datetime import datetime, timezone
        async with session:
            record = Attestation(
                batch_id=batch["batch_id"],
                agent_did=batch.get("agent_did", ""),
                merkle_root=batch.get("merkle_root", ""),
                record_count=batch.get("record_count", 0),
                attestation_uid=attestation_uid,
                eas_tx_hash=eas_tx_hash,
                schema_uid=settings.EAS_SCHEMA_UID,
                chain_id=84532 if settings.EAS_CHAIN == "sepolia" else 8453,
                on_chain=bool(attestation_uid),
                webhook_sent=True,
                anchored_at=datetime.now(timezone.utc),
            )
            session.add(record)
            await session.commit()
            logger.info("attestation_saved_to_db", batch_id=batch["batch_id"])
    except Exception as e:
        logger.warning("db_save_failed", batch_id=batch.get("batch_id"), error=str(e))


async def _get_local_pending_batches() -> list[dict]:
    """Fetch pending batches from local DB (direct SDK uploads)."""
    try:
        session = await get_session()
        if session is None:
            return []
        from sqlalchemy import select
        from ..db.models import Batch
        async with session:
            result = await session.execute(
                select(Batch).where(Batch.status == "pending").order_by(Batch.created_at).limit(50)
            )
            rows = result.scalars().all()
            return [{
                "batch_id": r.batch_id,
                "agent_did": r.agent_did,
                "merkle_root": r.merkle_root,
                "record_count": r.record_count,
                "avg_latency_ms": r.avg_latency_ms,
                "batch_ts": r.batch_ts,
                "sig": r.sig,
                "_source": "local",
            } for r in rows]
    except Exception as e:
        logger.warning("local_pending_fetch_failed", error=str(e))
        return []


async def _mark_local_batch_anchored(batch_id: str, attestation_uid: str, eas_tx_hash: str | None):
    """Update local batch status to anchored."""
    try:
        session = await get_session()
        if session is None:
            return
        from sqlalchemy import select
        from ..db.models import Batch
        async with session:
            result = await session.execute(
                select(Batch).where(Batch.batch_id == batch_id)
            )
            batch = result.scalar_one_or_none()
            if batch:
                batch.status = "anchored"
                batch.attestation_uid = attestation_uid
                batch.eas_tx_hash = eas_tx_hash
                await session.commit()
    except Exception as e:
        logger.warning("local_batch_update_failed", batch_id=batch_id, error=str(e))


async def _anchor_super_batch(batches: list[dict], _anchor_start: float) -> dict:
    """Anchor multiple batches as a single super-batch with one EAS attestation."""
    from datetime import datetime, timezone
    import time as _time

    roots = [b["merkle_root"] for b in batches]
    super_root, _layers = build_super_merkle_tree(roots)
    super_batch_id = f"sb_{_uuid.uuid4().hex[:16]}"

    # Single EAS attestation
    try:
        eas_result = await write_attestation(
            merkle_root=super_root,
            agent_did="did:ecp:atlast-server",
            record_count=sum(b.get("record_count", 0) for b in batches),
            avg_latency_ms=0,
            batch_ts=0,
        )
        attestation_uid = eas_result.get("attestation_uid", "")
        eas_tx_hash = eas_result.get("tx_hash")
    except Exception as e:
        capture_error(e, {"context": "super_batch_eas", "batch_count": len(batches)})
        return {"processed": len(batches), "anchored": 0, "errors": len(batches)}

    # Store SuperBatch record
    try:
        from ..db.database import get_session, SuperBatch
        session = await get_session()
        if session is not None:
            async with session:
                record = SuperBatch(
                    super_batch_id=super_batch_id,
                    super_merkle_root=super_root,
                    attestation_uid=attestation_uid,
                    eas_tx_hash=eas_tx_hash,
                    batch_count=len(batches),
                    batch_ids=json_lib.dumps([b["batch_id"] for b in batches]),
                    status="anchored",
                    anchored_at=datetime.now(timezone.utc),
                )
                session.add(record)
                await session.commit()
    except Exception as e:
        logger.warning("super_batch_db_save_failed", error=str(e))

    # Update each batch and fire webhooks
    anchored = 0
    errors = 0
    for i, batch in enumerate(batches):
        try:
            proof = get_inclusion_proof(roots, i)

            if batch.get("_source") == "local":
                await _mark_local_batch_anchored(batch["batch_id"], attestation_uid, eas_tx_hash)
            else:
                await mark_batch_anchored(
                    batch_id=batch["batch_id"],
                    attestation_uid=attestation_uid,
                    eas_tx_hash=eas_tx_hash,
                )

            await _save_attestation(batch, attestation_uid, eas_tx_hash)

            await fire_attestation_webhook(
                batch_id=batch["batch_id"],
                agent_did=batch["agent_did"],
                merkle_root=batch["merkle_root"],
                record_count=batch.get("record_count", 0),
                attestation_uid=attestation_uid,
                eas_tx_hash=eas_tx_hash,
                super_batch_id=super_batch_id,
                super_merkle_root=super_root,
                inclusion_proof=proof,
            )
            anchored += 1
        except Exception as e:
            capture_error(e, {"context": "super_batch_item", "batch_id": batch.get("batch_id")})
            errors += 1

    # Stats + logs
    from .verify import record_anchor_stats
    record_anchor_stats(anchored, errors)

    try:
        from ..db.database import get_session, AnchorLog
        session = await get_session()
        if session is not None:
            async with session:
                log = AnchorLog(
                    processed=len(batches),
                    anchored=anchored,
                    errors=errors,
                    duration_ms=int((_time.time() - _anchor_start) * 1000),
                    run_at=datetime.now(timezone.utc),
                )
                session.add(log)
                await session.commit()
    except Exception as e:
        logger.warning("anchor_log_save_failed", error=str(e))

    from .metrics import anchor_total, anchor_latency
    anchor_total.labels(status="success").inc(anchored)
    anchor_total.labels(status="error").inc(errors)

    logger.info("super_batch_anchor_done", super_batch_id=super_batch_id, batch_count=len(batches), anchored=anchored, errors=errors)
    return {"processed": len(batches), "anchored": anchored, "errors": errors, "super_batch_id": super_batch_id}


async def _anchor_pending():
    """Core anchor logic — fetch pending batches from LLaChat + local DB, anchor to EAS, fire webhooks."""
    import time as _time
    _anchor_start = _time.time()

    # Fetch from both sources
    llachat_batches = await get_pending_batches()
    local_batches = await _get_local_pending_batches()
    batches = llachat_batches + local_batches

    if not batches:
        return {"processed": 0, "anchored": 0, "errors": 0}

    # Super-batch aggregation: if enough pending batches, anchor as one
    if len(batches) >= settings.SUPER_BATCH_MIN_SIZE:
        result = await _anchor_super_batch(batches, _anchor_start)
        return result

    anchored = 0
    errors = 0

    for batch in batches:
        try:
            # Step 1: Write EAS attestation
            eas_result = await write_attestation(
                merkle_root=batch["merkle_root"],
                agent_did=batch["agent_did"],
                record_count=batch.get("record_count", 0),
                avg_latency_ms=batch.get("avg_latency_ms", 0),
                batch_ts=batch.get("batch_ts", 0),
            )

            attestation_uid = eas_result.get("attestation_uid", "")
            eas_tx_hash = eas_result.get("tx_hash")

            # Step 2: Mark batch as anchored (local DB or LLaChat depending on source)
            if batch.get("_source") == "local":
                await _mark_local_batch_anchored(batch["batch_id"], attestation_uid, eas_tx_hash)
            else:
                await mark_batch_anchored(
                    batch_id=batch["batch_id"],
                    attestation_uid=attestation_uid,
                    eas_tx_hash=eas_tx_hash,
                )

            # Step 3: Persist to attestations table
            await _save_attestation(batch, attestation_uid, eas_tx_hash)

            # Step 4: Fire webhook (if configured)
            await fire_attestation_webhook(
                batch_id=batch["batch_id"],
                agent_did=batch["agent_did"],
                merkle_root=batch["merkle_root"],
                record_count=batch.get("record_count", 0),
                attestation_uid=attestation_uid,
                eas_tx_hash=eas_tx_hash,
            )

            anchored += 1
        except Exception as e:
            capture_error(e, {"context": "anchor_batch", "batch_id": batch.get("batch_id")})
            errors += 1

    # Update global stats
    from .verify import record_anchor_stats
    record_anchor_stats(anchored, errors)

    # Persist anchor run to DB
    try:
        from ..db.database import get_session, AnchorLog
        session = await get_session()
        if session is not None:
            import time as _time
            from datetime import datetime, timezone
            async with session:
                log = AnchorLog(
                    processed=len(batches),
                    anchored=anchored,
                    errors=errors,
                    duration_ms=int((_time.time() - _anchor_start) * 1000),
                    run_at=datetime.now(timezone.utc),
                )
                session.add(log)
                await session.commit()
    except Exception as e:
        logger.warning("anchor_log_save_failed", error=str(e))

    # Prometheus counters
    from .metrics import anchor_total, anchor_latency
    anchor_total.labels(status="success").inc(anchored)
    anchor_total.labels(status="error").inc(errors)

    logger.info("anchor_cron_done", processed=len(batches), anchored=anchored, errors=errors)
    return {"processed": len(batches), "anchored": anchored, "errors": errors}


@router.post("/v1/internal/anchor-now")
async def anchor_now(x_internal_token: str = Header(None, alias="X-Internal-Token")):
    """Manual trigger for anchoring. Can also be called by Railway cron."""
    # Allow unauthenticated in dev, require token in production
    if settings.ENVIRONMENT == "production":
        if not x_internal_token or not secrets.compare_digest(x_internal_token, settings.LLACHAT_INTERNAL_TOKEN):
            raise HTTPException(status_code=401, detail="Invalid internal token")

    result = await _anchor_pending()
    return {"status": "ok", **result}


@router.get("/v1/internal/anchor-status")
async def anchor_status(x_internal_token: str = Header(None, alias="X-Internal-Token")):
    """Check anchor service status."""
    if settings.ENVIRONMENT == "production":
        if not x_internal_token or not secrets.compare_digest(x_internal_token, settings.LLACHAT_INTERNAL_TOKEN):
            raise HTTPException(status_code=401, detail="Invalid internal token")

    return {
        "service": "ecp-anchor",
        "eas_chain": settings.EAS_CHAIN,
        "eas_stub": settings.EAS_STUB_MODE,
        "webhook_url": settings.ECP_WEBHOOK_URL or "not configured",
        "llachat_api": settings.LLACHAT_API_URL,
    }
