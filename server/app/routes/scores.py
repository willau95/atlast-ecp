"""
Score API — Trust Score lookup for LLAChat and third parties.

Endpoints:
  GET  /v1/scores?agent_did={DID}     — single agent score
  POST /v1/scores/batch               — bulk lookup (array of DIDs)
"""

import structlog
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..db.database import get_session
from ..db.models import Agent

logger = structlog.get_logger()
router = APIRouter()


def _agent_to_score_response(agent: Agent) -> dict:
    """Convert Agent model to score API response."""
    last_batch = agent.last_batch_at.isoformat() if agent.last_batch_at else None
    return {
        "agent_did": agent.did,
        "trust_score": agent.trust_score or 150,  # 150 = identity-only default
        "version": agent.score_version or 1,
        "record_count": agent.total_records or 0,
        "total_batches": agent.total_batches or 0,
        "last_batch_at": last_batch,
        "layers": agent.score_layers or {},
        "meta": agent.score_meta or {},
        "ecp_version": agent.ecp_version or "unknown",
    }


@router.get("/v1/scores")
async def get_score(agent_did: str = Query(..., description="Agent DID (did:ecp:xxxx)")):
    """Get trust score for a single agent."""
    session = await get_session()
    if session is None:
        raise HTTPException(status_code=503, detail="Database not available")

    from sqlalchemy import select
    async with session:
        result = await session.execute(select(Agent).where(Agent.did == agent_did))
        agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_did} not found")

    return _agent_to_score_response(agent)


class BatchScoreRequest(BaseModel):
    agent_dids: list[str]


@router.post("/v1/scores/batch")
async def get_scores_batch(req: BatchScoreRequest):
    """Bulk lookup trust scores for multiple agents."""
    if len(req.agent_dids) > 100:
        raise HTTPException(status_code=400, detail="Max 100 agents per request")

    session = await get_session()
    if session is None:
        raise HTTPException(status_code=503, detail="Database not available")

    from sqlalchemy import select
    async with session:
        result = await session.execute(
            select(Agent).where(Agent.did.in_(req.agent_dids))
        )
        agents = result.scalars().all()

    found = {a.did: _agent_to_score_response(a) for a in agents}

    # Include not-found agents with default score
    scores = []
    for did in req.agent_dids:
        if did in found:
            scores.append(found[did])
        else:
            scores.append({
                "agent_did": did,
                "trust_score": 150,
                "version": 2,
                "record_count": 0,
                "total_batches": 0,
                "last_batch_at": None,
                "layers": {},
                "meta": {},
                "ecp_version": "unknown",
            })

    return {"scores": scores, "total": len(scores)}
