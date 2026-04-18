"""
Tests for 3 Critical production fixes:
  C1: EAS fail-closed (no stub fallback in production)
  C2: Batch upload authentication enforced
  C3: Anchor coordinator (lock + nonce + gas check)
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

# ── C1: EAS Fail-Closed ──────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_c1_eas_live_failure_raises():
    """EAS live failure should raise, NOT fallback to stub."""
    from app.services.eas import write_attestation

    with patch("app.services.eas.settings") as mock_settings:
        mock_settings.EAS_STUB_MODE = "false"
        mock_settings.EAS_CHAIN = "mainnet"

        with patch("app.services.eas._live_attestation", side_effect=ConnectionError("RPC timeout")):
            with pytest.raises(ConnectionError, match="RPC timeout"):
                await write_attestation(
                    merkle_root="sha256:abc123",
                    agent_did="did:ecp:test",
                    record_count=10,
                    avg_latency_ms=100,
                    batch_ts=1000,
                )


@pytest.mark.anyio
async def test_c1_stub_mode_still_works():
    """Stub mode should still work for dev/testing."""
    from app.services.eas import write_attestation

    with patch("app.services.eas.settings") as mock_settings:
        mock_settings.EAS_STUB_MODE = "true"
        mock_settings.EAS_CHAIN = "sepolia"

        result = await write_attestation(
            merkle_root="sha256:abc123",
            agent_did="did:ecp:test",
            record_count=10,
            avg_latency_ms=100,
            batch_ts=1000,
        )
        assert result["mode"] == "stub"
        assert "stub_" in result["attestation_uid"]


# ── C2: Batch Upload Auth ────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_c2_batch_upload_rejects_no_auth_production():
    """Production batch upload without API key should return 401."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    with patch("app.routes.batches.settings") as mock_settings:
        mock_settings.ENVIRONMENT = "production"
        mock_settings.LLACHAT_API_URL = ""
        mock_settings.LLACHAT_INTERNAL_TOKEN = ""

        resp = client.post("/v1/batches", json={
            "merkle_root": "sha256:abc",
            "agent_did": "did:ecp:fake",
            "record_count": 5,
            "batch_ts": 1000,
            "sig": "ed25519:fake",
        })
        assert resp.status_code == 401
        assert "API key required" in resp.json()["detail"]


@pytest.mark.anyio
@pytest.mark.parametrize("env_value", ["prod", "PRODUCTION", "Production", "staging", "", "garbage", "production "])
async def test_c3_environment_fail_closed_on_non_dev_values(env_value):
    """Any ENVIRONMENT value NOT in the dev whitelist (typos, staging, blank,
    unknown) must require auth on /v1/batches — fail-closed against
    misconfiguration, not just the exact string "production"."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    with patch("app.routes.batches.settings") as mock_settings:
        mock_settings.ENVIRONMENT = env_value
        mock_settings.LLACHAT_API_URL = ""
        mock_settings.LLACHAT_INTERNAL_TOKEN = ""

        resp = client.post("/v1/batches", json={
            "merkle_root": "sha256:abc",
            "agent_did": "did:ecp:fake",
            "record_count": 5,
            "batch_ts": 1000,
            "sig": "ed25519:fake",
        })
        assert resp.status_code == 401, (
            f"ENVIRONMENT={env_value!r} should be fail-closed (401) "
            f"but got {resp.status_code}"
        )


@pytest.mark.anyio
async def test_c2_batch_upload_rejects_wrong_did():
    """API key for agent A should not be able to upload as agent B."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    with patch("app.routes.batches.verify_api_key", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = ("did:ecp:agentA", "free")

        with patch("app.routes.batches.settings") as mock_settings:
            mock_settings.ENVIRONMENT = "production"
            mock_settings.LLACHAT_API_URL = ""
            mock_settings.LLACHAT_INTERNAL_TOKEN = ""

            resp = client.post(
                "/v1/batches",
                json={
                    "merkle_root": "sha256:abc",
                    "agent_did": "did:ecp:agentB",  # Different from key's DID
                    "record_count": 5,
                    "batch_ts": 1000,
                    "sig": "ed25519:fake",
                },
                headers={"X-API-Key": "ak_live_test"},
            )
            assert resp.status_code == 403
            assert "does not match" in resp.json()["detail"]


@pytest.mark.anyio
async def test_c2_register_validates_did_format():
    """Register should reject invalid DID format."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    resp = client.post("/v1/agents/register", json={
        "did": "invalid-did-format",
        "public_key": "abc123",
    })
    assert resp.status_code == 422 or resp.status_code == 400


# ── C3: Anchor Coordinator ──────────────────────────────────────────────────


@pytest.mark.anyio
async def test_c3_process_lock_prevents_concurrent():
    """Process-level lock should prevent concurrent anchoring."""
    from app.services.anchor_coordinator import _anchor_lock, try_acquire_lock

    # Simulate lock already held
    await _anchor_lock.acquire()
    try:
        result = await try_acquire_lock()
        assert result is False  # Should fail — lock held
    finally:
        _anchor_lock.release()


@pytest.mark.anyio
async def test_c3_gas_check_stub_mode():
    """Gas check should pass in stub mode."""
    from app.services.anchor_coordinator import check_gas_balance

    with patch("app.services.anchor_coordinator.settings") as mock_settings:
        mock_settings.EAS_STUB_MODE = "true"
        ok, balance = await check_gas_balance()
        assert ok is True


@pytest.mark.anyio
async def test_c3_should_retry_batch():
    """Retry logic should respect MAX_RETRY_COUNT."""
    from app.services.anchor_coordinator import should_retry_batch, MAX_RETRY_COUNT

    assert should_retry_batch({"retry_count": 0}) is True
    assert should_retry_batch({"retry_count": 2}) is True
    assert should_retry_batch({"retry_count": MAX_RETRY_COUNT}) is False
    assert should_retry_batch({"retry_count": MAX_RETRY_COUNT + 1}) is False
    assert should_retry_batch({}) is True  # No retry_count = 0


@pytest.mark.anyio
async def test_c3_mark_batch_retry_increments():
    """mark_batch_retry should increment retry_count."""
    from app.services.anchor_coordinator import mark_batch_retry

    # Mock DB
    mock_batch = MagicMock()
    mock_batch.retry_count = 1
    mock_batch.batch_id = "batch_test"

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_batch
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

    with patch("app.services.anchor_coordinator.get_session", new_callable=AsyncMock, return_value=mock_session):
        await mark_batch_retry("batch_test", "test error")
        assert mock_batch.retry_count == 2
        assert mock_batch.status == "retry_queued"
        assert mock_batch.error_message == "test error"


@pytest.mark.anyio
async def test_c3_mark_batch_permanently_failed():
    """After MAX_RETRY_COUNT, batch should be marked anchor_failed."""
    from app.services.anchor_coordinator import mark_batch_retry, MAX_RETRY_COUNT

    mock_batch = MagicMock()
    mock_batch.retry_count = MAX_RETRY_COUNT - 1  # One more = permanent fail
    mock_batch.batch_id = "batch_test"

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_batch
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

    with patch("app.services.anchor_coordinator.get_session", new_callable=AsyncMock, return_value=mock_session):
        await mark_batch_retry("batch_test", "final failure")
        assert mock_batch.retry_count == MAX_RETRY_COUNT
        assert mock_batch.status == "anchor_failed"


# ── Integration: Anchor flow with failures ──────────────────────────────────


@pytest.mark.anyio
async def test_anchor_pending_skips_when_locked():
    """_anchor_pending should skip if lock is held."""
    from app.routes.anchor import _anchor_pending
    from app.services.anchor_coordinator import _anchor_lock

    await _anchor_lock.acquire()
    try:
        result = await _anchor_pending()
        assert result.get("skipped") == "lock_held"
    finally:
        _anchor_lock.release()


@pytest.mark.anyio
async def test_anchor_pending_pauses_on_low_gas():
    """_anchor_pending should pause when gas is low."""
    from app.routes.anchor import _anchor_pending

    with patch("app.services.anchor_coordinator.try_acquire_lock", return_value=True), \
         patch("app.services.anchor_coordinator.release_lock", new_callable=AsyncMock), \
         patch("app.services.anchor_coordinator.check_gas_balance", return_value=(False, 100)), \
         patch("app.routes.anchor.capture_error"):
        result = await _anchor_pending()
        assert result.get("paused") == "low_gas"
