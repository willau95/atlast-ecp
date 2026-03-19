"""
ECP Reference Server — Agent Routes

POST /v1/agents/register
GET  /v1/agents/{handle}/profile
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, HTTPException

from .. import database as db
from ..models import AgentProfile, AgentRegisterRequest, AgentRegisterResponse, TrustSignals
from ..scoring import compute_trust_signals

router = APIRouter(prefix="/v1/agents", tags=["agents"])


@router.post("/register", response_model=AgentRegisterResponse, status_code=201)
def register_agent(req: AgentRegisterRequest):
    try:
        result = db.register_agent(
            did=req.did,
            public_key=req.public_key,
            handle=req.handle,
            display_name=req.display_name,
        )
    except sqlite3.IntegrityError as e:
        err = str(e).lower()
        if "did" in err:
            raise HTTPException(status_code=409, detail="DID already registered")
        if "handle" in err:
            raise HTTPException(status_code=409, detail="Handle already taken")
        raise HTTPException(status_code=409, detail="Agent already exists")

    return AgentRegisterResponse(**result)


@router.get("/{handle}/profile", response_model=AgentProfile)
def get_agent_profile(handle: str):
    agent = db.get_agent_by_handle(handle)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    stats = db.get_agent_stats(agent["id"])

    signals = compute_trust_signals(
        total_records=stats["total_records"],
        total_batches=stats["total_batches"],
        flag_counts=stats["flag_counts"],
    )

    return AgentProfile(
        agent_id=agent["id"],
        did=agent["did"],
        handle=agent["handle"],
        display_name=agent.get("display_name"),
        description=agent.get("description"),
        status=agent.get("status"),
        total_records=stats["total_records"],
        total_batches=stats["total_batches"],
        first_seen=stats["first_seen"],
        last_active=stats["last_active"],
        trust_signals=TrustSignals(**signals),
    )
