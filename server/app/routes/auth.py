"""
Auth routes — Agent registration, API key management.

Flow:
  1. POST /v1/agents/register → creates agent + returns API key (ak_live_xxx)
  2. All subsequent requests use X-API-Key header
  3. POST /v1/auth/rotate-key → rotates API key
  4. GET /v1/auth/me → returns agent info for current key
"""

import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel
import structlog

from ..db.database import get_session
from ..db.models import Agent, APIKey

logger = structlog.get_logger()
router = APIRouter()


def _generate_api_key() -> str:
    """Generate a secure API key: ak_live_{40 random chars}."""
    return f"ak_live_{secrets.token_urlsafe(30)}"


def _hash_key(key: str) -> str:
    """SHA-256 hash of API key for storage (never store raw key)."""
    return hashlib.sha256(key.encode()).hexdigest()


# ── Middleware helper ────────────────────────────────────────────────────────

async def verify_api_key(x_api_key: str | None) -> tuple[str, str]:
    """
    Verify X-API-Key header. Returns (agent_did, rate_limit_tier).
    Raises HTTPException(401) if invalid.
    """
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    session = await get_session()
    if session is None:
        raise HTTPException(status_code=503, detail="Database not available")

    key_hash = _hash_key(x_api_key)
    from sqlalchemy import select

    async with session:
        result = await session.execute(
            select(APIKey).where(APIKey.key_hash == key_hash, APIKey.active == True)
        )
        api_key = result.scalar_one_or_none()

        if not api_key:
            raise HTTPException(status_code=401, detail="Invalid API key")

        # Update last_used
        api_key.last_used = datetime.now(timezone.utc)
        await session.commit()

        return api_key.agent_did, api_key.rate_limit_tier


# ── Routes ──────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    did: str
    public_key: str | None = None
    ecp_version: str = "0.1"


class RegisterResponse(BaseModel):
    agent_did: str
    agent_api_key: str
    message: str


@router.post("/v1/agents/register", response_model=RegisterResponse)
async def register_agent(req: RegisterRequest, request: Request):
    """
    Register a new agent and return an API key.
    Idempotent: if agent already exists, returns a new API key (old ones stay valid).
    """
    # Validate DID format
    if not req.did or not req.did.startswith("did:ecp:"):
        raise HTTPException(status_code=422, detail="Invalid DID format. Expected: did:ecp:{hex}")

    session = await get_session()
    if session is None:
        raise HTTPException(status_code=503, detail="Database not available")

    from sqlalchemy import select

    async with session:
        # Upsert agent
        result = await session.execute(
            select(Agent).where(Agent.did == req.did)
        )
        agent = result.scalar_one_or_none()

        if not agent:
            agent = Agent(
                did=req.did,
                public_key=req.public_key,
                ecp_version=req.ecp_version,
            )
            session.add(agent)
        else:
            # Update public key if provided
            if req.public_key:
                agent.public_key = req.public_key
            agent.last_seen = datetime.now(timezone.utc)

        # Generate new API key
        raw_key = _generate_api_key()
        api_key = APIKey(
            key_prefix=raw_key[:16],
            key_hash=_hash_key(raw_key),
            agent_did=req.did,
        )
        session.add(api_key)
        await session.commit()

        logger.info("agent_registered", did=req.did)
        return RegisterResponse(
            agent_did=req.did,
            agent_api_key=raw_key,
            message="Agent registered. Save your API key — it won't be shown again.",
        )


class RotateKeyResponse(BaseModel):
    agent_did: str
    new_api_key: str
    message: str


@router.post("/v1/auth/rotate-key", response_model=RotateKeyResponse)
async def rotate_key(x_api_key: str = Header(None, alias="X-API-Key")):
    """Rotate API key: deactivate current, issue new one."""
    agent_did, _ = await verify_api_key(x_api_key)

    session = await get_session()
    if session is None:
        raise HTTPException(status_code=503, detail="Database not available")

    from sqlalchemy import select

    old_hash = _hash_key(x_api_key)
    raw_key = _generate_api_key()

    async with session:
        # Deactivate old key
        result = await session.execute(
            select(APIKey).where(APIKey.key_hash == old_hash)
        )
        old_key = result.scalar_one_or_none()
        if old_key:
            old_key.active = False

        # Create new key
        new_key = APIKey(
            key_prefix=raw_key[:16],
            key_hash=_hash_key(raw_key),
            agent_did=agent_did,
            rotated_from=old_hash,
        )
        session.add(new_key)
        await session.commit()

    logger.info("api_key_rotated", did=agent_did)
    return RotateKeyResponse(
        agent_did=agent_did,
        new_api_key=raw_key,
        message="Key rotated. Old key deactivated. Save your new key.",
    )


class MeResponse(BaseModel):
    agent_did: str
    rate_limit_tier: str
    key_prefix: str


@router.get("/v1/auth/me", response_model=MeResponse)
async def get_me(x_api_key: str = Header(None, alias="X-API-Key")):
    """Get current agent info for the authenticated API key."""
    agent_did, tier = await verify_api_key(x_api_key)

    return MeResponse(
        agent_did=agent_did,
        rate_limit_tier=tier,
        key_prefix=x_api_key[:16] if x_api_key else "",
    )
