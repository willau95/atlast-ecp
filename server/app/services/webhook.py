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

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, content=payload_bytes, headers=headers)
            resp.raise_for_status()
            logger.info("ecp_webhook_sent", batch_id=batch_id, status=resp.status_code)
            from ..routes.verify import record_webhook_sent
            record_webhook_sent()
            return True
    except Exception as e:
        logger.warning("ecp_webhook_failed", batch_id=batch_id, error=str(e))
        return False
