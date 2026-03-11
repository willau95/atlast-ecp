"""
ECP Backend — Batch Upload Route
POST /v1/batch

Core flow:
  1. Verify agent exists + signature valid
  2. Store batch metadata in SQLite
  3. Store individual record hashes (for per-record verification)
  4. Write Merkle Root to EAS on Base (async)
  5. Update agent trust stats
  6. Return attestation_uid
"""

import time
import hashlib
import json
import asyncio
from fastapi import APIRouter, HTTPException, BackgroundTasks

from ..database import db
from ..models import BatchUploadRequest, BatchUploadResponse
from ..crypto import verify_batch_signature, build_merkle_proof
from ..trust_score import update_stats_from_batch
from ..eas import write_attestation

router = APIRouter()


# ─── POST /v1/batch ───────────────────────────────────────────────────────────

@router.post("/v1/batch", response_model=BatchUploadResponse, tags=["Batches"])
async def upload_batch(req: BatchUploadRequest, background_tasks: BackgroundTasks):
    """
    Upload a Merkle batch from an ECP SDK client.

    SDK calls this endpoint hourly with:
    - merkle_root: SHA-256 of all record chain.hashes in this batch
    - record_hashes: individual record IDs + hashes (optional, enables per-record verification)
    - flag_counts: aggregated behavioral flags
    - sig: ed25519 signature over merkle_root

    Process:
    1. Verify agent registered + signature valid
    2. Deduplicate (idempotent — same root = same batch_id)
    3. Store batch + record hashes
    4. Trigger async EAS anchoring
    5. Update trust score inputs
    """
    agent_did = req.agent_did

    with db() as conn:
        # 1. Verify agent exists
        agent = conn.execute(
            "SELECT did, public_key FROM agents WHERE did = ?", (agent_did,)
        ).fetchone()

        if not agent:
            raise HTTPException(
                status_code=404,
                detail=f"Agent not found: {agent_did}. Register first: POST /v1/agent/register"
            )

        # 2. Verify signature
        if not verify_batch_signature(agent["public_key"], req.sig, req.merkle_root):
            raise HTTPException(
                status_code=401,
                detail="Invalid signature. Batch rejected."
            )

        # 3. Idempotency: same agent + merkle_root = same batch
        batch_id = _generate_batch_id(agent_did, req.merkle_root, req.batch_ts)

        existing = conn.execute(
            "SELECT batch_id, attestation_uid, upload_status FROM batches WHERE batch_id = ?",
            (batch_id,)
        ).fetchone()

        if existing:
            # Already received this exact batch
            return BatchUploadResponse(
                batch_id=existing["batch_id"],
                attestation_uid=existing["attestation_uid"],
                eas_url=_eas_url(existing["attestation_uid"]) if existing["attestation_uid"] else None,
                status="already_received",
                message="Batch already processed.",
            )

        # 4. Store batch
        now = int(time.time() * 1000)
        conn.execute("""
            INSERT INTO batches (
                batch_id, agent_did, merkle_root, record_count, avg_latency_ms,
                batch_ts, ecp_version, sig, created_at, upload_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        """, (
            batch_id, agent_did, req.merkle_root, req.record_count,
            req.avg_latency_ms, req.batch_ts, req.ecp_version, req.sig, now,
        ))

        # 5. Store individual record hashes (for per-record verification)
        if req.record_hashes:
            all_hashes = [r.hash for r in req.record_hashes]
            for i, entry in enumerate(req.record_hashes):
                proof = build_merkle_proof(all_hashes, entry.hash)
                conn.execute("""
                    INSERT OR IGNORE INTO record_hashes
                        (record_id, agent_did, batch_id, chain_hash, merkle_proof, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    entry.id, agent_did, batch_id,
                    entry.hash, json.dumps(proof), now,
                ))

        # 6. Update trust stats
        update_stats_from_batch(
            conn=conn,
            agent_did=agent_did,
            record_count=req.record_count,
            avg_latency_ms=req.avg_latency_ms,
            flag_counts=req.flag_counts,
            batch_ts=req.batch_ts,
        )

    # 7. Async EAS anchoring (non-blocking — returns immediately)
    background_tasks.add_task(
        _anchor_batch,
        batch_id=batch_id,
        agent_did=agent_did,
        merkle_root=req.merkle_root,
        record_count=req.record_count,
        avg_latency_ms=req.avg_latency_ms,
        batch_ts=req.batch_ts,
        ecp_version=req.ecp_version,
    )

    return BatchUploadResponse(
        batch_id=batch_id,
        attestation_uid=None,       # Will be set after async anchoring
        status="pending_anchor",
        message="Batch received. EAS anchoring in progress.",
    )


# ─── Background Task: EAS Anchoring ──────────────────────────────────────────

async def _anchor_batch(
    batch_id: str,
    agent_did: str,
    merkle_root: str,
    record_count: int,
    avg_latency_ms: int,
    batch_ts: int,
    ecp_version: str,
):
    """
    Write Merkle Root to EAS on Base.
    Runs as FastAPI background task after response is returned to client.
    Updates batch record with attestation_uid on success.
    """
    try:
        result = await write_attestation(
            merkle_root=merkle_root,
            agent_did=agent_did,
            record_count=record_count,
            avg_latency_ms=avg_latency_ms,
            batch_ts=batch_ts,
            ecp_version=ecp_version,
        )

        attestation_uid = result.get("attestation_uid")
        eas_url = result.get("eas_url")
        anchored_at = result.get("anchored_at")

        # Update batch record with attestation result
        with db() as conn:
            conn.execute("""
                UPDATE batches
                SET attestation_uid = ?, eas_url = ?, anchored_at = ?, upload_status = 'anchored'
                WHERE batch_id = ?
            """, (attestation_uid, eas_url, anchored_at, batch_id))

    except Exception:
        # EAS failure is non-fatal — batch data is stored, can be re-anchored
        with db() as conn:
            conn.execute(
                "UPDATE batches SET upload_status = 'anchor_failed' WHERE batch_id = ?",
                (batch_id,)
            )


# ─── GET /v1/batch/{batch_id} ────────────────────────────────────────────────

@router.get("/v1/batch/{batch_id}", tags=["Batches"])
def get_batch(batch_id: str):
    """Get batch status including attestation_uid if anchored."""
    with db() as conn:
        batch = conn.execute(
            "SELECT * FROM batches WHERE batch_id = ?", (batch_id,)
        ).fetchone()

        if not batch:
            raise HTTPException(status_code=404, detail=f"Batch not found: {batch_id}")

        return {
            "batch_id": batch["batch_id"],
            "agent_did": batch["agent_did"],
            "merkle_root": batch["merkle_root"],
            "record_count": batch["record_count"],
            "batch_ts": batch["batch_ts"],
            "attestation_uid": batch["attestation_uid"],
            "eas_url": batch["eas_url"],
            "anchored_at": batch["anchored_at"],
            "status": batch["upload_status"],
        }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _generate_batch_id(agent_did: str, merkle_root: str, batch_ts: int) -> str:
    """Deterministic batch ID from agent + root + timestamp."""
    payload = f"{agent_did}:{merkle_root}:{batch_ts}"
    h = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"batch_{h}"


def _eas_url(attestation_uid: str) -> str:
    if attestation_uid:
        return f"https://base.easscan.org/attestation/view/{attestation_uid}"
    return None
