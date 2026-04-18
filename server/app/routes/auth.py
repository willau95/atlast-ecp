"""
Auth routes — Agent registration, API key management.

Flow:
  1. POST /v1/agents/register → creates agent + returns API key (ak_live_xxx)
  2. All subsequent requests use X-API-Key header
  3. POST /v1/auth/rotate-key → rotates API key
  4. GET /v1/auth/me → returns agent info for current key
"""

import hashlib
import os
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel
import structlog

from ..db.database import get_session
from ..db.models import Agent, APIKey
from ..ratelimit import limiter

logger = structlog.get_logger()
router = APIRouter()

# Discord webhook for new user notifications
_DISCORD_NEW_USERS_WEBHOOK = os.getenv("ATLAST_DISCORD_NEW_USERS_WEBHOOK", "")


async def _notify_new_user_discord(did: str, ecp_version: str = "?", ip: str = "?"):
    """Send new agent registration to Discord. Fail-open."""
    if not _DISCORD_NEW_USERS_WEBHOOK:
        return
    import urllib.request
    import json
    import time as _t
    try:
        payload = json.dumps({
            "content": "\n".join([
                "🎉 **NEW AGENT REGISTERED**",
                "",
                f"**DID:** `{did}`",
                f"**Source:** Server API (register)",
                f"**ECP Version:** v{ecp_version}",
                f"**IP:** {ip}",
                f"\n*{_t.strftime('%Y-%m-%d %H:%M UTC', _t.gmtime())}*",
            ]),
            "username": "ATLAST New Users",
        })
        req = urllib.request.Request(
            _DISCORD_NEW_USERS_WEBHOOK,
            data=payload.encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


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
    public_key: str  # Required: Ed25519 public key hex (64 chars)
    ecp_version: str = "0.1"
    # Ownership proof: required when re-registering an existing DID
    ownership_sig: str | None = None  # ed25519 signature over "register:{did}:{timestamp}"
    ownership_ts: int | None = None   # Unix ms timestamp used in signature


class RegisterResponse(BaseModel):
    agent_did: str
    agent_api_key: str
    message: str


def _verify_ownership_sig(public_key_hex: str, did: str, sig: str, ts: int) -> bool:
    """Verify Ed25519 ownership signature over 'register:{did}:{ts}'."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        message = f"register:{did}:{ts}".encode()
        sig_bytes = bytes.fromhex(sig.replace("ed25519:", ""))
        pub_bytes = bytes.fromhex(public_key_hex)
        public_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        public_key.verify(sig_bytes, message)
        return True
    except Exception:
        return False


@router.post("/v1/agents/register", response_model=RegisterResponse)
@limiter.limit("5/hour")  # Anti-spam: DID registration from single IP
async def register_agent(req: RegisterRequest, request: Request):
    """
    Register a new agent and return an API key.

    New DID: public_key required, no ownership proof needed.
    Existing DID: ownership_sig + ownership_ts required to prove key ownership.
    This prevents DID hijacking (anyone registering keys for DIDs they don't own).
    """
    # Validate DID format strictly: `did:ecp:` + 32-64 hex chars.
    # Previous check (startswith only) accepted "did:ecp:" (empty),
    # "did:ecp:x" (non-hex), "did:ecp:00…" (collision/replay), etc.
    import re as _re
    if not req.did or not _re.match(r"^did:ecp:[0-9a-fA-F]{32,64}$", req.did):
        raise HTTPException(
            status_code=422,
            detail="Invalid DID format. Expected: did:ecp:{32-64 hex chars}",
        )

    # Validate public_key format (Ed25519 = 32 bytes = 64 hex chars)
    if not req.public_key or not _re.match(r"^[0-9a-fA-F]{64}$", req.public_key):
        raise HTTPException(
            status_code=422,
            detail="public_key must be 64 hex chars (Ed25519 public key raw bytes)",
        )

    session = await get_session()
    if session is None:
        raise HTTPException(status_code=503, detail="Database not available")

    from sqlalchemy import select
    import time as _time

    async with session:
        # Check if agent already exists
        result = await session.execute(
            select(Agent).where(Agent.did == req.did)
        )
        agent = result.scalar_one_or_none()

        if agent:
            # ── Existing DID: require ownership proof ──
            if not req.ownership_sig or not req.ownership_ts:
                raise HTTPException(
                    status_code=403,
                    detail="DID already registered. Provide ownership_sig and ownership_ts to prove key ownership.",
                )

            # Check timestamp freshness (within 5 minutes)
            now_ms = int(_time.time() * 1000)
            if abs(now_ms - req.ownership_ts) > 300_000:
                raise HTTPException(status_code=403, detail="Ownership timestamp expired (>5min)")

            # Verify signature against registered public key
            registered_pk = agent.public_key
            if not registered_pk:
                raise HTTPException(status_code=403, detail="Agent has no registered public key — cannot verify ownership")

            if not _verify_ownership_sig(registered_pk, req.did, req.ownership_sig, req.ownership_ts):
                raise HTTPException(status_code=403, detail="Ownership signature verification failed")

            agent.last_seen = datetime.now(timezone.utc)
            logger.info("agent_re_registered", did=req.did)
        else:
            # ── New DID: register with public key ──
            agent = Agent(
                did=req.did,
                public_key=req.public_key,
                ecp_version=req.ecp_version,
            )
            session.add(agent)
            logger.info("agent_registered_new", did=req.did)

            # Notify Discord #new-users (fire-and-forget)
            try:
                import asyncio
                asyncio.create_task(_notify_new_user_discord(
                    did=req.did,
                    ecp_version=req.ecp_version or "?",
                    ip=request.client.host if request.client else "?",
                ))
            except Exception:
                pass  # Fail-open

        # Generate new API key
        raw_key = _generate_api_key()
        api_key = APIKey(
            key_prefix=raw_key[:16],
            key_hash=_hash_key(raw_key),
            agent_did=req.did,
        )
        session.add(api_key)
        await session.commit()

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
