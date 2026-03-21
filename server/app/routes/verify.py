"""
Verification endpoints — public, read-only.

GET  /v1/verify/{attestation_uid}  — check EAS on-chain attestation
POST /v1/verify/merkle             — verify Merkle tree integrity
GET  /v1/stats                     — global anchoring statistics
"""

import hashlib
import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = structlog.get_logger()
router = APIRouter(tags=["Verify"])

from ..config import settings


# ── Merkle Verification ────────────────────────────────────────────────────

class MerkleVerifyRequest(BaseModel):
    merkle_root: str
    record_hashes: list[str]


def _sha256(data: str) -> str:
    """SHA-256 with sha256: prefix — matches SDK and backend crypto.py."""
    return "sha256:" + hashlib.sha256(data.encode()).hexdigest()


def _compute_merkle_root(hashes: list[str]) -> str:
    """
    Recompute Merkle root from leaf hashes.
    Algorithm matches atlast-ecp SDK exactly:
    - No sorting (order-preserving)
    - sha256: prefix throughout
    - Odd layers: duplicate last element
    """
    if not hashes:
        return _sha256("empty")

    if len(hashes) == 1:
        return hashes[0]

    current = list(hashes)
    while len(current) > 1:
        if len(current) % 2 == 1:
            current.append(current[-1])  # duplicate last for odd length
        next_layer = []
        for i in range(0, len(current), 2):
            combined = _sha256(current[i] + current[i + 1])
            next_layer.append(combined)
        current = next_layer
    return current[0]


@router.post("/v1/verify/merkle")
async def verify_merkle(req: MerkleVerifyRequest):
    """
    Verify Merkle tree: recompute root from record hashes and compare.
    No auth required — this is a pure computation.
    """
    if not req.record_hashes:
        raise HTTPException(status_code=400, detail="record_hashes cannot be empty")

    computed = _compute_merkle_root(req.record_hashes)
    match = computed == req.merkle_root

    return {
        "valid": match,
        "expected_root": req.merkle_root,
        "computed_root": computed,
        "record_count": len(req.record_hashes),
    }


# ── EAS On-Chain Verification ──────────────────────────────────────────────

@router.get("/v1/verify/{attestation_uid}")
async def verify_attestation(attestation_uid: str):
    """
    Look up an attestation UID on EAS.
    Returns on-chain data if found, or 404 if not found / not yet indexed.
    """
    is_testnet = settings.EAS_CHAIN == "sepolia"

    # For now, return the EAS explorer link and metadata
    # Full on-chain verification via web3 will be added in Phase 5
    base_url = "https://base-sepolia.easscan.org" if is_testnet else "https://base.easscan.org"

    return {
        "attestation_uid": attestation_uid,
        "chain": settings.EAS_CHAIN,
        "chain_id": 84532 if is_testnet else 8453,
        "schema_uid": settings.EAS_SCHEMA_UID,
        "explorer_url": f"{base_url}/attestation/view/{attestation_uid}",
        "contract": "0x4200000000000000000000000000000000000021",
        "verified": "explorer_link",  # Will be "on_chain" after web3 integration
    }


# ── Stats ───────────────────────────────────────────────────────────────────

# In-memory stats counter (reset on restart — will use Redis in Phase 5)
_anchor_stats = {
    "total_anchored": 0,
    "total_errors": 0,
    "total_webhooks_sent": 0,
    "server_start": None,
}


def record_anchor_stats(anchored: int, errors: int):
    """Called by anchor cron to update stats."""
    _anchor_stats["total_anchored"] += anchored
    _anchor_stats["total_errors"] += errors


def record_webhook_sent():
    _anchor_stats["total_webhooks_sent"] += 1


def init_stats():
    from datetime import datetime, timezone
    _anchor_stats["server_start"] = datetime.now(timezone.utc).isoformat()


@router.get("/v1/stats")
async def get_stats():
    """Public stats — no auth, read-only."""
    return {
        "total_anchored": _anchor_stats["total_anchored"],
        "total_errors": _anchor_stats["total_errors"],
        "total_webhooks_sent": _anchor_stats["total_webhooks_sent"],
        "server_start": _anchor_stats["server_start"],
        "eas_chain": settings.EAS_CHAIN,
    }
