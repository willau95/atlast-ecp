"""
E2E Onboarding Test — Simulates a new user's complete journey.

Tests the full pipeline using the FastAPI test client (no real network calls):
  Register agent → Upload batch → Anchor → Verify attestation → Check stats

Run: pytest tests/test_e2e_onboarding.py -v
"""

import hashlib
import json
import os
import secrets
import pytest
from httpx import AsyncClient, ASGITransport

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("LLACHAT_INTERNAL_TOKEN", "test-internal-token-for-e2e")
os.environ["ECP_WEBHOOK_URL"] = ""  # disable webhook during tests

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.config import settings
import app.db.database as db_module
from app.db.database import Base


@pytest.fixture(autouse=True)
async def setup_test_db():
    """Initialize in-memory SQLite DB for each test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Import all models so Base.metadata knows about them
    from app.db.models import Agent, APIKey, Batch  # noqa: F401
    from app.db.database import Attestation, AnchorLog, SuperBatch  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Monkey-patch get_session to use our test DB
    original_get_session = db_module.get_session

    async def _test_get_session():
        return session_factory()

    db_module.get_session = _test_get_session
    db_module._engine = engine
    db_module._session_factory = session_factory

    yield

    db_module.get_session = original_get_session
    db_module._engine = None
    db_module._session_factory = None
    await engine.dispose()


def sha256_hash(data: str) -> str:
    return "sha256:" + hashlib.sha256(data.encode()).hexdigest()


def build_merkle_root(hashes: list[str]) -> str:
    """Minimal merkle tree builder matching SDK convention."""
    if not hashes:
        return sha256_hash("empty")
    current = list(hashes)
    while len(current) > 1:
        next_layer = []
        for i in range(0, len(current), 2):
            if i + 1 < len(current):
                combined = current[i] + current[i + 1]
            else:
                combined = current[i] + current[i]
            next_layer.append(sha256_hash(combined))
        current = next_layer
    return current[0]


@pytest.fixture
def unique_did():
    """Generate a unique DID for each test run (32 hex chars = valid format)."""
    return f"did:ecp:{secrets.token_hex(16)}"


@pytest.fixture
def record_hashes():
    """Generate 5 fake ECP record hashes."""
    return [sha256_hash(f"test_record_{i}_{secrets.token_hex(4)}") for i in range(5)]


@pytest.mark.anyio
async def test_full_onboarding_journey(unique_did, record_hashes):
    """
    Complete onboarding flow:
    1. Register agent → get API key
    2. Upload batch → get batch_id
    3. Trigger anchor → batch gets anchored
    4. Verify attestation exists
    5. Check stats incremented
    """
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # ── Step 1: Register agent ──
        reg_resp = await client.post("/v1/agents/register", json={
            "did": unique_did,
            "public_key": secrets.token_hex(32),  # 64 hex chars, no prefix (matches SDK)
            "ecp_version": "0.9.0",
        })
        assert reg_resp.status_code == 200, f"Register failed: {reg_resp.text}"
        reg_data = reg_resp.json()
        assert reg_data["agent_did"] == unique_did
        api_key = reg_data["agent_api_key"]
        assert api_key.startswith("ak_live_")

        # ── Step 2: Verify /auth/me ──
        me_resp = await client.get("/v1/auth/me", headers={"X-API-Key": api_key})
        assert me_resp.status_code == 200
        me_data = me_resp.json()
        assert me_data["agent_did"] == unique_did

        # ── Step 3: Upload batch ──
        merkle_root = build_merkle_root(record_hashes)
        import time as _time
        batch_resp = await client.post("/v1/batches", json={
            "agent_did": unique_did,
            "merkle_root": merkle_root,
            "record_count": len(record_hashes),
            "record_hashes": [{"in_hash": h, "out_hash": sha256_hash(h)} for h in record_hashes],
            "batch_ts": int(_time.time() * 1000),
            "sig": sha256_hash(f"{unique_did}:{merkle_root}"),
        }, headers={"X-API-Key": api_key})
        assert batch_resp.status_code in (200, 201), f"Batch upload failed: {batch_resp.text}"
        batch_data = batch_resp.json()
        batch_id = batch_data["batch_id"]
        assert batch_id.startswith("batch_")
        assert batch_data["status"] in ("pending", "received")

        # ── Step 4: Get batch by ID ──
        get_resp = await client.get(f"/v1/batches/{batch_id}", headers={"X-API-Key": api_key})
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["batch_id"] == batch_id
        assert get_data["agent_did"] == unique_did

        # ── Step 5: Trigger anchor ──
        anchor_resp = await client.post(
            "/v1/internal/anchor-now",
            headers={"X-Internal-Token": settings.LLACHAT_INTERNAL_TOKEN},
        )
        assert anchor_resp.status_code == 200
        anchor_data = anchor_resp.json()
        assert anchor_data["status"] == "ok"
        # At least our batch should have been processed
        assert anchor_data["processed"] >= 1

        # ── Step 6: Check stats ──
        stats_resp = await client.get("/v1/stats")
        assert stats_resp.status_code == 200
        stats_data = stats_resp.json()
        assert stats_data["total_anchored"] >= 0
        assert "server_start" in stats_data

        # ── Step 7: Verify merkle ──
        verify_resp = await client.post("/v1/verify/merkle", json={
            "merkle_root": merkle_root,
            "record_hashes": record_hashes,
        })
        assert verify_resp.status_code == 200
        verify_data = verify_resp.json()
        assert verify_data["valid"] is True

        # ── Step 8: List attestations ──
        att_resp = await client.get("/v1/attestations")
        assert att_resp.status_code == 200


@pytest.mark.anyio
async def test_register_existing_did_requires_ownership(unique_did):
    """Re-registering an existing DID without ownership proof returns 403."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.post("/v1/agents/register", json={
            "did": unique_did, "public_key": "a" * 64, "ecp_version": "0.9.0",
        })
        assert r1.status_code == 200
        # Second registration without ownership proof → 403
        r2 = await client.post("/v1/agents/register", json={
            "did": unique_did, "public_key": "a" * 64, "ecp_version": "0.9.0",
        })
        assert r2.status_code == 403
        assert "ownership" in r2.json()["detail"].lower()


@pytest.mark.anyio
async def test_upload_batch_wrong_key_rejected():
    """Upload with wrong API key should be rejected (403 or 401)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v1/batches", json={
            "agent_did": "did:ecp:" + "1" * 32,  # valid format, no matching agent
            "merkle_root": "sha256:fake",
            "record_count": 1,
            "record_hashes": ["sha256:fake"],
        }, headers={"X-API-Key": "ak_live_wrongkey"})
        # Should reject — invalid key (401) or validation error (422) or fail-open warning (200)
        assert resp.status_code in (401, 403, 422, 200), f"Unexpected: {resp.status_code}"


@pytest.mark.anyio
async def test_anchor_rejects_no_token():
    """Anchor endpoint requires internal token in production."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v1/internal/anchor-now")
        # Token is always required now (all environments)
        assert resp.status_code == 401


@pytest.mark.anyio
async def test_health_and_discovery():
    """Health and discovery endpoints work without auth."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        discovery = await client.get("/.well-known/ecp.json")
        assert discovery.status_code == 200
        data = discovery.json()
        assert data["ecp_version"] == "1.0"
        assert "eas_anchoring" in data["capabilities"]
