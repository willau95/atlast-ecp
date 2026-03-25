"""
ATLAST ECP Webhook — fire-and-forget notification on batch/attestation events.

Fail-Open: webhook failures never crash the agent or block batch operations.

Payload format matches CERTIFICATE-SCHEMA.md Section 3 exactly.
"""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from typing import Any, Optional

logger = logging.getLogger("atlast_ecp.webhook")

DEFAULT_TIMEOUT = 5  # seconds
MAX_RETRIES = 1


def build_webhook_payload(batch_data: dict) -> dict:
    """
    Build webhook payload matching CERTIFICATE-SCHEMA.md Section 3.

    Expected batch_data keys (all optional — missing ones become None):
        cert_id, agent_did, batch_merkle_root, record_count,
        attestation_uid, eas_tx_hash, schema_uid, chain_id,
        on_chain, created_at
    """
    return {
        "event": "attestation.anchored",
        "cert_id": batch_data.get("cert_id") or batch_data.get("batch_id"),
        "agent_did": batch_data.get("agent_did"),
        "batch_merkle_root": batch_data.get("batch_merkle_root") or batch_data.get("merkle_root"),
        "record_count": batch_data.get("record_count"),
        "attestation_uid": batch_data.get("attestation_uid"),
        "eas_tx_hash": batch_data.get("eas_tx_hash"),
        "schema_uid": batch_data.get("schema_uid"),
        "chain_id": batch_data.get("chain_id"),
        "on_chain": batch_data.get("on_chain", False),
        "created_at": batch_data.get("created_at"),
    }


def fire_webhook(
    payload: dict,
    url: str,
    token: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> bool:
    """
    POST webhook payload to url. Fail-open: returns False on failure, never raises.

    Payload is serialized with compact separators + sort_keys for deterministic
    HMAC-SHA256 signing (matches ECP Server webhook format exactly).

    Args:
        payload: JSON-serializable dict
        url: Target webhook URL
        token: Value for X-ECP-Webhook-Token header (optional, also used as HMAC key)
        timeout: Request timeout in seconds

    Returns:
        True if 2xx response, False otherwise
    """
    import hashlib
    import hmac as hmac_mod

    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-ECP-Webhook-Token"] = token

    # Deterministic serialization — same bytes for signing and sending
    data = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

    # HMAC-SHA256 signature (matches ECP Server webhook.py exactly)
    if token:
        signature = hmac_mod.new(
            token.encode(), data, hashlib.sha256
        ).hexdigest()
        headers["X-ECP-Signature"] = f"sha256={signature}"

    for attempt in range(1 + MAX_RETRIES):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if 200 <= resp.status < 300:
                    return True
                # Non-2xx but not 5xx — don't retry
                if resp.status < 500:
                    logger.warning("Webhook returned %d: %s", resp.status, url)
                    return False
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt >= MAX_RETRIES:
                logger.warning("Webhook HTTP error %d: %s", e.code, url)
                return False
            # 5xx — retry
            logger.info("Webhook %d, retrying (%d/%d): %s", e.code, attempt + 1, MAX_RETRIES, url)
            continue
        except Exception as e:
            logger.warning("Webhook failed (%s): %s", type(e).__name__, url)
            return False

    return False
