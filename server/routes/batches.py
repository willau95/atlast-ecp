"""
ECP Reference Server — Batch Routes

POST /v1/batches
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import database as db
from ..auth import verify_agent_key
from ..merkle import verify_merkle_root
from ..models import BatchUploadRequest, BatchUploadResponse

router = APIRouter(prefix="/v1", tags=["batches"])


@router.post("/batches", response_model=BatchUploadResponse, status_code=201)
def upload_batch(req: BatchUploadRequest, agent: dict = Depends(verify_agent_key)):
    # Verify agent_did matches authenticated agent
    if req.agent_did != agent["did"]:
        raise HTTPException(status_code=403, detail="agent_did does not match API key")

    # Verify record_count matches
    if req.record_count != len(req.record_hashes):
        raise HTTPException(
            status_code=400,
            detail=f"record_count ({req.record_count}) does not match record_hashes length ({len(req.record_hashes)})",
        )

    # Optional: verify Merkle root
    chain_hashes = [rh.chain_hash for rh in req.record_hashes]
    if chain_hashes and not verify_merkle_root(chain_hashes, req.merkle_root):
        raise HTTPException(status_code=400, detail="Merkle root verification failed")

    # Store
    result = db.create_batch(
        agent_id=agent["id"],
        batch_ts=req.batch_ts,
        merkle_root=req.merkle_root,
        record_count=req.record_count,
        flag_counts=req.flag_counts.model_dump() if req.flag_counts else None,
        record_hashes=[rh.model_dump() for rh in req.record_hashes],
    )

    return BatchUploadResponse(
        batch_id=result["batch_id"],
        record_count=result["record_count"],
        merkle_root=result["merkle_root"],
        status="accepted",
    )
