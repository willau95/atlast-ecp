"""
LLaChat Internal API Client — pulls pending batches, updates anchored status.

Uses X-Internal-Token auth (service-to-service).
"""

import httpx
import structlog
from ..config import settings

logger = structlog.get_logger()


async def get_pending_batches() -> list[dict]:
    """Fetch pending batches from LLaChat backend."""
    url = f"{settings.LLACHAT_API_URL}/v1/internal/pending-batches"
    headers = {"X-Internal-Token": settings.LLACHAT_INTERNAL_TOKEN}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            batches = data.get("batches", [])
            logger.info("pending_batches_fetched", count=len(batches))
            return batches
    except Exception as e:
        logger.error("pending_batches_fetch_failed", error=str(e))
        return []


async def mark_batch_anchored(
    *,
    batch_id: str,
    attestation_uid: str,
    eas_tx_hash: str | None = None,
) -> bool:
    """Notify LLaChat that a batch has been anchored on-chain."""
    url = f"{settings.LLACHAT_API_URL}/v1/internal/batch-anchored"
    headers = {
        "X-Internal-Token": settings.LLACHAT_INTERNAL_TOKEN,
        "Content-Type": "application/json",
    }
    payload = {
        "batch_id": batch_id,
        "attestation_uid": attestation_uid,
        "eas_tx_hash": eas_tx_hash,
        "upload_status": "anchored",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            logger.info("batch_anchored_notified", batch_id=batch_id)
            return True
    except Exception as e:
        logger.error("batch_anchored_notify_failed", batch_id=batch_id, error=str(e))
        return False
