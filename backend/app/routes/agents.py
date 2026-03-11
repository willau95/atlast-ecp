"""
ECP Backend — Agent Routes
POST /v1/agent/register
GET  /v1/agent/{did}
"""

import secrets
import time
import os
from fastapi import APIRouter, HTTPException

from ..database import db
from ..models import AgentRegisterRequest, AgentRegisterResponse, AgentProfileResponse
from ..trust_score import compute_trust_inputs

router = APIRouter()

BASE_URL = os.environ.get("ECP_BASE_URL", "https://api.llachat.com")
LLACHAT_URL = os.environ.get("LLACHAT_URL", "https://llachat.com")
CLAIM_TOKEN_EXPIRY_MS = 7 * 24 * 60 * 60 * 1000  # 7 days


# ─── POST /v1/agent/register ──────────────────────────────────────────────────

@router.post("/v1/agent/register", response_model=AgentRegisterResponse, tags=["Agents"])
def register_agent(req: AgentRegisterRequest):
    """
    Register a new Agent with ECP.

    Called automatically by join.md flow:
    1. SDK generates Agent DID + ed25519 keypair locally
    2. Calls this endpoint with public key
    3. Returns claim_url for ownership verification via X tweet
    """
    with db() as conn:
        # Check if agent already exists
        existing = conn.execute(
            "SELECT did, verified FROM agents WHERE did = ?", (req.did,)
        ).fetchone()

        if existing:
            # Re-registration: return new claim token if not yet verified
            if existing["verified"]:
                raise HTTPException(
                    status_code=409,
                    detail=f"Agent {req.did} is already registered and verified."
                )
            # Not yet verified — allow re-claim
            claim_token = _generate_claim_token(conn, req.did)
        else:
            # New registration
            now = int(time.time() * 1000)
            conn.execute("""
                INSERT INTO agents (did, public_key, name, description, owner_x_handle, ecp_version, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (req.did, req.public_key, req.name, req.description, req.owner_x_handle, req.ecp_version, now))
            claim_token = _generate_claim_token(conn, req.did)

    short_did = req.did.replace("did:ecp:", "")[:8]
    agent_name = req.name or f"Agent-{short_did}"
    x_handle = req.owner_x_handle or "my_handle"

    return AgentRegisterResponse(
        agent_did=req.did,
        claim_url=f"{LLACHAT_URL}/claim/{claim_token}",
        verification_tweet=(
            f"I just registered {agent_name} on @LLaChat! "
            f"Verified by ATLAST Protocol 🔗 "
            f"{LLACHAT_URL}/agent/{short_did} "
            f"#LLaChat #WebA0 #ATLASTProtocol"
        ),
        status="pending_verification",
    )


def _generate_claim_token(conn, agent_did: str) -> str:
    """Generate and store a new claim token for an agent."""
    token = f"tok_{secrets.token_hex(16)}"
    expires_at = int(time.time() * 1000) + CLAIM_TOKEN_EXPIRY_MS
    conn.execute("""
        UPDATE agents SET claim_token = ?, claim_expires = ? WHERE did = ?
    """, (token, expires_at, agent_did))
    return token


# ─── POST /v1/agent/verify-claim ─────────────────────────────────────────────

@router.post("/v1/agent/verify-claim", tags=["Agents"])
def verify_claim(claim_token: str):
    """
    Mark agent as verified after owner confirms via X tweet.
    Called by LLaChat frontend after tweet verification.
    """
    with db() as conn:
        now = int(time.time() * 1000)
        agent = conn.execute(
            "SELECT did, claim_expires, verified FROM agents WHERE claim_token = ?",
            (claim_token,)
        ).fetchone()

        if not agent:
            raise HTTPException(status_code=404, detail="Claim token not found.")
        if agent["claim_expires"] and agent["claim_expires"] < now:
            raise HTTPException(status_code=410, detail="Claim token has expired.")
        if agent["verified"]:
            return {"status": "already_verified", "did": agent["did"]}

        conn.execute(
            "UPDATE agents SET verified = 1, claim_token = NULL WHERE did = ?",
            (agent["did"],)
        )
        return {"status": "verified", "did": agent["did"],
                "profile_url": f"{LLACHAT_URL}/agent/{agent['did'].replace('did:ecp:', '')[:8]}"}


# ─── GET /v1/agent/{did} ─────────────────────────────────────────────────────

@router.get("/v1/agent/{did}", response_model=AgentProfileResponse, tags=["Agents"])
def get_agent_profile(did: str):
    """
    Get agent profile + Trust Score inputs.
    DID can be full (did:ecp:abc123) or short (abc123).
    """
    # Normalize DID
    if not did.startswith("did:ecp:"):
        did = f"did:ecp:{did}"

    with db() as conn:
        agent = conn.execute(
            "SELECT * FROM agents WHERE did = ?", (did,)
        ).fetchone()

        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent not found: {did}")

        stats = conn.execute(
            "SELECT * FROM agent_stats WHERE agent_did = ?", (did,)
        ).fetchone()

        latest_batch = conn.execute(
            "SELECT attestation_uid FROM batches WHERE agent_did = ? AND attestation_uid IS NOT NULL "
            "ORDER BY created_at DESC LIMIT 1", (did,)
        ).fetchone()

    trust_inputs = compute_trust_inputs(dict(stats) if stats else {})
    short_did = did.replace("did:ecp:", "")

    return AgentProfileResponse(
        did=did,
        name=agent["name"],
        description=agent["description"],
        owner_x_handle=agent["owner_x_handle"],
        ecp_version=agent["ecp_version"],
        verified=bool(agent["verified"]),
        created_at=agent["created_at"],
        trust_score_inputs=trust_inputs,
        profile_url=f"{LLACHAT_URL}/agent/{short_did}",
        latest_attestation_uid=latest_batch["attestation_uid"] if latest_batch else None,
    )
