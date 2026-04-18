"""
Multi-Agent Stress Test — simulates Day-1 concurrent agent load.

ST-A: 10 agents, 50 records each, concurrent upload
ST-B: 10 concurrent uploads → super-batch trigger
ST-C: Verify super-batch merkle tree + inclusion proofs
ST-D: Verify webhooks fired (mocked)
ST-E: 3 rounds, check DB consistency

Run: pytest tests/test_stress_multi_agent.py -v
"""

import asyncio
import hashlib
import json
import os
import secrets
import time
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

os.environ.setdefault("ENVIRONMENT", "development")
os.environ["ECP_WEBHOOK_URL"] = ""
os.environ["EAS_STUB_MODE"] = "true"

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, func

from app.main import app
from app.config import settings
import app.db.database as db_module
from app.db.database import Base, Attestation, SuperBatch
from app.db.models import Agent, APIKey, Batch
from app.services.merkle import build_super_merkle_tree, get_inclusion_proof, verify_inclusion


def sha256_hash(data: str) -> str:
    return "sha256:" + hashlib.sha256(data.encode()).hexdigest()


def build_merkle_root(hashes: list[str]) -> str:
    if not hashes:
        return sha256_hash("empty")
    current = list(hashes)
    while len(current) > 1:
        nl = []
        for i in range(0, len(current), 2):
            if i + 1 < len(current):
                nl.append(sha256_hash(current[i] + current[i + 1]))
            else:
                nl.append(sha256_hash(current[i] + current[i]))
        current = nl
    return current[0]


@pytest.fixture(autouse=True)
async def setup_test_db():
    """Initialize in-memory SQLite DB."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    orig = db_module.get_session

    async def _test_get_session():
        return sf()

    db_module.get_session = _test_get_session
    db_module._engine = engine
    db_module._session_factory = sf

    yield sf

    db_module.get_session = orig
    db_module._engine = None
    db_module._session_factory = None
    await engine.dispose()


async def register_agent(client, did):
    """Register an agent and return API key."""
    r = await client.post("/v1/agents/register", json={
        "did": did,
        "public_key": secrets.token_hex(32),  # 64 hex chars, no prefix (matches SDK identity.py format)
        "ecp_version": "0.9.0",
    })
    assert r.status_code == 200
    return r.json()["agent_api_key"]


async def upload_batch(client, did, api_key, record_count=50):
    """Upload a batch for an agent."""
    hashes = [sha256_hash(f"rec_{did}_{i}_{secrets.token_hex(4)}") for i in range(record_count)]
    root = build_merkle_root(hashes)
    r = await client.post("/v1/batches", json={
        "agent_did": did,
        "merkle_root": root,
        "record_count": len(hashes),
        "record_hashes": [{"in_hash": h, "out_hash": sha256_hash(h)} for h in hashes],
        "batch_ts": int(time.time() * 1000),
        "sig": sha256_hash(f"{did}:{root}"),
    }, headers={"X-API-Key": api_key})
    assert r.status_code in (200, 201), f"Upload failed: {r.text}"
    return r.json()["batch_id"], root, hashes


@pytest.mark.anyio
async def test_st_a_concurrent_multi_agent_upload():
    """ST-A: 10 agents register + upload concurrently."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register 10 agents
        agents = {}
        for i in range(10):
            did = f"did:ecp:{secrets.token_hex(16)}"  # 32 hex chars (valid format)
            key = await register_agent(client, did)
            agents[did] = key

        # Concurrent upload — 10 agents × 50 records each
        start = time.time()
        tasks = []
        for did, key in agents.items():
            tasks.append(upload_batch(client, did, key, record_count=50))

        results = await asyncio.gather(*tasks)
        elapsed = time.time() - start

        assert len(results) == 10
        batch_ids = [r[0] for r in results]
        assert len(set(batch_ids)) == 10  # all unique
        print(f"\n  ST-A: 10 agents × 50 records uploaded in {elapsed:.2f}s ({10/elapsed:.1f} uploads/s)")


@pytest.mark.anyio
async def test_st_b_super_batch_trigger(setup_test_db):
    """ST-B: 10 concurrent uploads → should trigger super-batch (≥5 pending)."""
    sf = setup_test_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register and upload 10 batches
        batch_ids = []
        for i in range(10):
            did = f"did:ecp:{secrets.token_hex(16)}"
            key = await register_agent(client, did)
            bid, _, _ = await upload_batch(client, did, key, record_count=10)
            batch_ids.append(bid)

        # Verify 10 pending batches in DB
        async with sf() as session:
            count = await session.scalar(select(func.count()).select_from(Batch).where(Batch.status == "pending"))
            assert count == 10, f"Expected 10 pending, got {count}"

        # Trigger anchor — should create super-batch
        r = await client.post("/v1/internal/anchor-now",
                              headers={"X-Internal-Token": settings.LLACHAT_INTERNAL_TOKEN})
        assert r.status_code == 200
        data = r.json()
        assert data["processed"] == 10
        assert data["anchored"] == 10
        assert "super_batch_id" in data, "Expected super-batch to be created"
        print(f"\n  ST-B: Super-batch created: {data['super_batch_id']}, {data['anchored']}/10 anchored")


@pytest.mark.anyio
async def test_st_c_merkle_proof_verification(setup_test_db):
    """ST-C: Verify super-batch merkle tree — each batch's inclusion proof works."""
    sf = setup_test_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create 7 batches (odd number to test duplicate-last merkle behavior)
        roots = []
        for i in range(7):
            did = f"did:ecp:{secrets.token_hex(16)}"
            key = await register_agent(client, did)
            _, root, _ = await upload_batch(client, did, key, record_count=5)
            roots.append(root)

        # Build expected super merkle tree
        super_root, layers = build_super_merkle_tree(roots)

        # Verify each batch's inclusion proof
        for i, root in enumerate(roots):
            proof = get_inclusion_proof(roots, i)
            assert verify_inclusion(root, proof, super_root), f"Proof failed for batch {i}"

        print(f"\n  ST-C: All 7 inclusion proofs verified against super merkle root")


@pytest.mark.anyio
async def test_st_d_webhook_fires_for_all(setup_test_db):
    """ST-D: Verify webhook fires for every batch in super-batch."""
    sf = setup_test_db
    transport = ASGITransport(app=app)
    webhook_calls = []

    async def mock_webhook(**kwargs):
        webhook_calls.append(kwargs)
        return True

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Upload 6 batches
        for i in range(6):
            did = f"did:ecp:{secrets.token_hex(16)}"
            key = await register_agent(client, did)
            await upload_batch(client, did, key, record_count=5)

        # Mock webhook and trigger anchor
        with patch("app.routes.anchor.fire_attestation_webhook", side_effect=mock_webhook):
            r = await client.post("/v1/internal/anchor-now",
                                  headers={"X-Internal-Token": settings.LLACHAT_INTERNAL_TOKEN})
            assert r.status_code == 200

        # All 6 batches should have triggered webhooks
        assert len(webhook_calls) == 6, f"Expected 6 webhook calls, got {len(webhook_calls)}"

        # Each should have super_batch_id and inclusion_proof
        for call in webhook_calls:
            assert call.get("super_batch_id") is not None
            assert call.get("inclusion_proof") is not None
            assert call.get("super_merkle_root") is not None

        print(f"\n  ST-D: {len(webhook_calls)} webhooks fired, all with super_batch_id + inclusion_proof")


@pytest.mark.anyio
async def test_st_e_three_rounds_consistency(setup_test_db):
    """ST-E: 3 rounds of upload→anchor, verify DB consistency."""
    sf = setup_test_db
    transport = ASGITransport(app=app)

    total_batches = 0
    total_anchored = 0

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for round_num in range(3):
            # Upload 6 batches per round
            for i in range(6):
                did = f"did:ecp:{secrets.token_hex(16)}"
                key = await register_agent(client, did)
                await upload_batch(client, did, key, record_count=5)
            total_batches += 6

            # Anchor
            r = await client.post("/v1/internal/anchor-now",
                                  headers={"X-Internal-Token": settings.LLACHAT_INTERNAL_TOKEN})
            assert r.status_code == 200
            data = r.json()
            total_anchored += data["anchored"]

        # Verify DB consistency
        async with sf() as session:
            # No pending batches should remain
            pending = await session.scalar(
                select(func.count()).select_from(Batch).where(Batch.status == "pending")
            )
            assert pending == 0, f"Expected 0 pending after 3 rounds, got {pending}"

            # All batches should be anchored
            anchored = await session.scalar(
                select(func.count()).select_from(Batch).where(Batch.status == "anchored")
            )
            assert anchored == total_batches, f"Expected {total_batches} anchored, got {anchored}"

            # Should have 3 super-batches (one per round)
            sb_count = await session.scalar(
                select(func.count()).select_from(SuperBatch)
            )
            assert sb_count == 3, f"Expected 3 super-batches, got {sb_count}"

            # No duplicate attestation UIDs across super-batches
            sbs = (await session.execute(select(SuperBatch))).scalars().all()
            uids = [sb.attestation_uid for sb in sbs]
            assert len(set(uids)) == len(uids), "Duplicate attestation UIDs found!"

        print(f"\n  ST-E: 3 rounds complete. {total_batches} batches, {total_anchored} anchored, 3 super-batches, 0 pending, no duplicates")
