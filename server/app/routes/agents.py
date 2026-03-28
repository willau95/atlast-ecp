"""
Agent Discovery & Record Sync endpoints.

GET /v1/agents/{did}/records — pull records for recovery
GET /v1/discovery/agents — list agents (public)
GET /v1/discovery/agents/{did}/stats — agent stats (public)
"""

from fastapi import APIRouter, Header, HTTPException, Query
from ..db.database import get_session
from ..db.models import Agent, Batch, APIKey
from ..routes.auth import verify_api_key

router = APIRouter()


@router.get("/v1/agents/{did}/records")
async def get_agent_records(
    did: str,
    limit: int = Query(100, le=10000),
    offset: int = Query(0, ge=0),
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """
    Get all batch records for an agent (for recovery/sync).
    
    Requires API key that belongs to this DID.
    Returns record_hashes and batch metadata.
    """
    # Auth: must be the agent's own key
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")
    
    try:
        key_did, _ = await verify_api_key(x_api_key)
    except HTTPException:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    if key_did != did:
        raise HTTPException(status_code=403, detail="Cannot access another agent's records")
    
    session = await get_session()
    if session is None:
        raise HTTPException(status_code=503, detail="Database not available")
    
    from sqlalchemy import select, func
    async with session:
        # Count total
        count_q = select(func.count()).select_from(Batch).where(Batch.agent_did == did)
        total = (await session.execute(count_q)).scalar() or 0
        
        # Get batches with record details
        q = (
            select(Batch)
            .where(Batch.agent_did == did)
            .order_by(Batch.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await session.execute(q)
        batches = result.scalars().all()
    
    records = []
    for b in batches:
        records.append({
            "batch_id": b.batch_id,
            "merkle_root": b.merkle_root,
            "record_count": b.record_count,
            "record_hashes": b.record_hashes or [],
            "chain_integrity": b.chain_integrity,
            "status": b.status,
            "attestation_uid": b.attestation_uid,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        })
    
    return {
        "did": did,
        "total_batches": total,
        "records": records,
        "offset": offset,
        "limit": limit,
    }


@router.get("/v1/discovery/agents")
async def list_agents(
    limit: int = Query(50, le=200),
):
    """List registered agents (public discovery)."""
    session = await get_session()
    if session is None:
        raise HTTPException(status_code=503, detail="Database not available")
    
    from sqlalchemy import select, func, outerjoin
    async with session:
        # Single query with LEFT JOIN to avoid N+1
        q = (
            select(
                Agent.did,
                Agent.created_at,
                func.count(Batch.id).label("batch_count"),
            )
            .outerjoin(Batch, Agent.did == Batch.agent_did)
            .group_by(Agent.did, Agent.created_at)
            .order_by(Agent.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(q)
        rows = result.all()
        
        agent_stats = [
            {
                "did": row.did,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "batch_count": row.batch_count,
            }
            for row in rows
        ]
    
    return {"agents": agent_stats, "total": len(agent_stats)}


@router.get("/v1/discovery/agents/{did}/stats")
async def get_agent_stats(did: str):
    """Get public stats for a specific agent."""
    session = await get_session()
    if session is None:
        raise HTTPException(status_code=503, detail="Database not available")
    
    from sqlalchemy import select, func
    async with session:
        agent_q = select(Agent).where(Agent.did == did)
        agent = (await session.execute(agent_q)).scalar_one_or_none()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        batch_count = (await session.execute(
            select(func.count()).select_from(Batch).where(Batch.agent_did == did)
        )).scalar() or 0
        
        anchored_count = (await session.execute(
            select(func.count()).select_from(Batch)
            .where(Batch.agent_did == did, Batch.status == "anchored")
        )).scalar() or 0
    
    # Include drift status
    from ..services.drift import compute_drift
    drift = await compute_drift(did)

    return {
        "did": did,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "total_batches": batch_count,
        "anchored_batches": anchored_count,
        "drift_status": {
            "drift_score": drift.drift_score,
            "drift_detected": drift.drift_detected,
            "changed_dimensions": [d.name for d in drift.changed_dimensions],
        },
    }


@router.get("/v1/agents/{did}/drift")
async def get_agent_drift(did: str):
    """Get detailed behavioral drift analysis for an agent."""
    session = await get_session()
    if session is None:
        raise HTTPException(status_code=503, detail="Database not available")

    from sqlalchemy import select
    async with session:
        agent = (await session.execute(
            select(Agent).where(Agent.did == did)
        )).scalar_one_or_none()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

    from ..services.drift import compute_drift
    drift = await compute_drift(did)

    return {
        "did": did,
        "drift_score": drift.drift_score,
        "drift_detected": drift.drift_detected,
        "changed_dimensions": [
            {
                "name": d.name,
                "baseline_mean": d.baseline_mean,
                "baseline_std": d.baseline_std,
                "current_mean": d.current_mean,
                "z_score": d.z_score,
                "drifted": d.drifted,
            }
            for d in drift.changed_dimensions
        ],
        "baseline_window": drift.baseline_window,
        "current_window": drift.current_window,
        "total_batches": drift.total_batches,
        "error": drift.error,
    }
