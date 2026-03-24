"""
ECP Webhook Sender — fires when EAS attestation succeeds.

Target: LLaChat internal endpoint POST /v1/internal/ecp-webhook
Auth: X-ECP-Webhook-Token header
Fail-Open: webhook failure never blocks anchoring.
"""

import hashlib
import hmac
import json as json_lib
import httpx
import structlog
from datetime import datetime, timezone
from ..config import settings

logger = structlog.get_logger()

# EAS constants
_USE_TESTNET = settings.EAS_CHAIN == "sepolia"
SCHEMA_UID = settings.EAS_SCHEMA_UID
CHAIN_ID = 84532 if _USE_TESTNET else 8453


async def fire_attestation_webhook(
    *,
    batch_id: str,
    agent_did: str,
    merkle_root: str,
    record_count: int,
    attestation_uid: str,
    eas_tx_hash: str | None = None,
    super_batch_id: str | None = None,
    super_merkle_root: str | None = None,
    inclusion_proof: list[dict] | None = None,
) -> bool:
    """POST webhook to LLaChat. Returns True if delivered."""
    url = settings.ECP_WEBHOOK_URL
    if not url:
        logger.debug("ecp_webhook_skipped", reason="ECP_WEBHOOK_URL not configured")
        return False

    payload = {
        "event": "attestation.anchored",
        "cert_id": batch_id,
        "agent_did": agent_did,
        "task_name": f"ECP Certification: {record_count} records anchored on-chain",
        "batch_merkle_root": merkle_root,
        "record_count": record_count,
        "attestation_uid": attestation_uid,
        "eas_tx_hash": eas_tx_hash,
        "schema_uid": SCHEMA_UID,
        "chain_id": CHAIN_ID,
        "on_chain": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if super_batch_id is not None:
        payload["super_batch_id"] = super_batch_id
    if super_merkle_root is not None:
        payload["super_merkle_root"] = super_merkle_root
    if inclusion_proof is not None:
        payload["inclusion_proof"] = inclusion_proof

    # Serialize payload once — use same bytes for signing and sending
    payload_bytes = json_lib.dumps(payload, separators=(",", ":"), sort_keys=True).encode()

    # HMAC-SHA256 signature for payload integrity
    signature = hmac.new(
        settings.ECP_WEBHOOK_TOKEN.encode(),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-ECP-Webhook-Token": settings.ECP_WEBHOOK_TOKEN,
        "X-ECP-Signature": f"sha256={signature}",
    }

    # Retry with exponential backoff (max 3 attempts)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, content=payload_bytes, headers=headers)
                resp.raise_for_status()
                logger.info("ecp_webhook_sent", batch_id=batch_id, status=resp.status_code, attempt=attempt + 1)
                from ..routes.verify import record_webhook_sent
                record_webhook_sent()
                from ..routes.metrics import webhook_total
                webhook_total.labels(status="success").inc()
                return True
        except Exception as e:
            logger.warning(
                "ecp_webhook_attempt_failed",
                batch_id=batch_id,
                attempt=attempt + 1,
                max_retries=max_retries,
                error=str(e),
            )
            if attempt < max_retries - 1:
                import asyncio
                wait = 2 ** attempt  # 1s, 2s
                await asyncio.sleep(wait)

    from .monitoring import capture_error
    err = RuntimeError(f"Webhook exhausted after {max_retries} attempts for {batch_id}")
    capture_error(err, {"context": "webhook", "batch_id": batch_id, "url": url})
    from ..routes.metrics import webhook_total
    webhook_total.labels(status="failed").inc()
    return False
