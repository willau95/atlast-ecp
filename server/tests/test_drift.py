"""
Tests for behavioral drift detection.
"""

import os
import secrets
import time
import pytest
from httpx import AsyncClient, ASGITransport

os.environ.setdefault("ENVIRONMENT", "development")
os.environ["ECP_WEBHOOK_URL"] = ""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
import app.db.database as db_module
from app.db.database import Base
from app.db.models import Agent, Batch
from app.services.drift import compute_drift, _mean, _std, _z_score, DriftResult


@pytest.fixture
async def setup_test_db():
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


# ── Unit tests for helpers ──

def test_mean_empty():
    assert _mean([]) == 0.0

def test_mean_values():
    assert _mean([1, 2, 3, 4, 5]) == 3.0

def test_std_single():
    assert _std([42]) == 0.0

def test_std_values():
    s = _std([2, 4, 4, 4, 5, 5, 7, 9])
    assert 1.9 < s < 2.2  # sample std ~2.14

def test_z_score_zero_std():
    assert _z_score(5.0, 5.0, 0.0) == 0.0
    assert _z_score(6.0, 5.0, 0.0) == 3.0  # max signal

def test_z_score_normal():
    z = _z_score(7.0, 5.0, 1.0)
    assert z == 2.0


# ── Integration tests ──

async def _create_agent_with_batches(sf, did, batch_configs):
    """Helper: create agent + N batches with specified record_count and latency."""
    async with sf() as session:
        agent = Agent(did=did, public_key="ed25519:test", ecp_version="0.9.0")
        session.add(agent)
        await session.flush()

        for i, cfg in enumerate(batch_configs):
            batch = Batch(
                batch_id=f"batch_{did}_{i}_{secrets.token_hex(4)}",
                agent_did=did,
                merkle_root=f"sha256:{secrets.token_hex(32)}",
                record_count=cfg.get("record_count", 10),
                avg_latency_ms=cfg.get("avg_latency_ms", 100),
                batch_ts=int(time.time() * 1000) + i * 1000,
                sig=f"sha256:{secrets.token_hex(32)}",
                status="anchored",
            )
            session.add(batch)
        await session.commit()


@pytest.mark.anyio
async def test_drift_insufficient_data(setup_test_db):
    """No drift detected with too few batches."""
    sf = setup_test_db
    did = f"did:ecp:drift_few_{secrets.token_hex(4)}"
    await _create_agent_with_batches(sf, did, [{"record_count": 10}] * 3)

    result = await compute_drift(did)
    assert not result.drift_detected
    assert result.drift_score == 0.0
    assert result.total_batches == 3


@pytest.mark.anyio
async def test_drift_stable_agent(setup_test_db):
    """Stable agent should have no drift."""
    sf = setup_test_db
    did = f"did:ecp:drift_stable_{secrets.token_hex(4)}"
    # 25 batches all with similar record_count and latency
    configs = [{"record_count": 10, "avg_latency_ms": 100}] * 25
    await _create_agent_with_batches(sf, did, configs)

    result = await compute_drift(did)
    assert not result.drift_detected
    assert result.drift_score < 0.2
    assert result.baseline_window == 20
    assert result.current_window == 5


@pytest.mark.anyio
async def test_drift_detected_record_count(setup_test_db):
    """Agent that suddenly changes record_count should trigger drift."""
    sf = setup_test_db
    did = f"did:ecp:drift_count_{secrets.token_hex(4)}"
    # 20 baseline batches with ~10 records, then 5 with ~100 records
    configs = [{"record_count": 10, "avg_latency_ms": 100}] * 20
    configs += [{"record_count": 100, "avg_latency_ms": 100}] * 5
    await _create_agent_with_batches(sf, did, configs)

    result = await compute_drift(did)
    assert result.drift_detected
    assert result.drift_score > 0.5
    changed = [d.name for d in result.changed_dimensions]
    assert "record_count" in changed


@pytest.mark.anyio
async def test_drift_detected_latency(setup_test_db):
    """Agent with sudden latency spike should trigger drift."""
    sf = setup_test_db
    did = f"did:ecp:drift_latency_{secrets.token_hex(4)}"
    configs = [{"record_count": 10, "avg_latency_ms": 50}] * 20
    configs += [{"record_count": 10, "avg_latency_ms": 500}] * 5  # 10x latency spike
    await _create_agent_with_batches(sf, did, configs)

    result = await compute_drift(did)
    assert result.drift_detected
    changed = [d.name for d in result.changed_dimensions]
    assert "avg_latency_ms" in changed


@pytest.mark.anyio
async def test_drift_api_endpoint(setup_test_db):
    """GET /v1/agents/{did}/drift returns drift analysis."""
    sf = setup_test_db
    did = f"did:ecp:drift_api_{secrets.token_hex(4)}"
    configs = [{"record_count": 10}] * 25
    await _create_agent_with_batches(sf, did, configs)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/v1/agents/{did}/drift")
        assert resp.status_code == 200
        data = resp.json()
        assert "drift_score" in data
        assert "drift_detected" in data
        assert data["total_batches"] == 25


@pytest.mark.anyio
async def test_drift_agent_not_found(setup_test_db):
    """Drift endpoint returns 404 for unknown agent."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/agents/did:ecp:nonexistent/drift")
        assert resp.status_code == 404


@pytest.mark.anyio
async def test_drift_in_agent_stats(setup_test_db):
    """GET /v1/discovery/agents/{did}/stats includes drift_status."""
    sf = setup_test_db
    did = f"did:ecp:drift_stats_{secrets.token_hex(4)}"
    configs = [{"record_count": 10}] * 25
    await _create_agent_with_batches(sf, did, configs)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/v1/discovery/agents/{did}/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "drift_status" in data
        assert "drift_score" in data["drift_status"]
