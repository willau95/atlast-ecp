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

logger = structlog.get_logger()
router = APIRouter()


async def _anchor_pending():
    """Core anchor logic — fetch pending batches, anchor to EAS, fire webhooks."""
    batches = await get_pending_batches()
    if not batches:
        return {"processed": 0, "anchored": 0, "errors": 0}

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

            # Step 2: Notify LLaChat that batch is anchored
            await mark_batch_anchored(
                batch_id=batch["batch_id"],
                attestation_uid=attestation_uid,
                eas_tx_hash=eas_tx_hash,
            )

            # Step 3: Fire webhook to LLaChat (creates cert + feed)
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
            logger.warning("anchor_batch_failed", batch_id=batch.get("batch_id"), error=str(e))
            errors += 1

    # Update global stats
    from .verify import record_anchor_stats
    record_anchor_stats(anchored, errors)

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
