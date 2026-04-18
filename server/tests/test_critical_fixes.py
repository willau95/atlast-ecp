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


# ── C1 (extended): EAS_STUB_MODE must be explicit in non-dev ──────────────────


def _run_config_import(env_overrides):
    """Import app.config in a subprocess with specified env vars. Returns
    (exit_code, stderr_text). Clean subprocess avoids polluting this process."""
    import subprocess, sys, os as _os
    env = {**_os.environ, **env_overrides}
    # Ensure we hit the repo's app package, not any installed copy.
    env["PYTHONPATH"] = str(_os.path.join(_os.path.dirname(__file__), ".."))
    r = subprocess.run(
        [sys.executable, "-c", "import app.config"],
        capture_output=True, text=True, env=env,
    )
    return r.returncode, r.stderr


def test_c1_startup_refuses_production_without_eas_mode():
    """Non-dev ENVIRONMENT with no EAS_STUB_MODE must refuse to start."""
    code, err = _run_config_import({
        "ENVIRONMENT": "production", "EAS_STUB_MODE": "", "EAS_PRIVATE_KEY": "",
    })
    assert code != 0
    assert "EAS_STUB_MODE is not configured" in err


def test_c1_startup_refuses_staging_without_eas_mode():
    """Staging (non-whitelist) must be treated as production and refuse."""
    code, err = _run_config_import({
        "ENVIRONMENT": "staging", "EAS_STUB_MODE": "", "EAS_PRIVATE_KEY": "",
    })
    assert code != 0
    assert "EAS_STUB_MODE is not configured" in err


def test_c1_startup_refuses_stub_false_without_private_key():
    """EAS_STUB_MODE=false requires EAS_PRIVATE_KEY in non-dev."""
    code, err = _run_config_import({
        "ENVIRONMENT": "production", "EAS_STUB_MODE": "false", "EAS_PRIVATE_KEY": "",
    })
    assert code != 0
    assert "requires EAS_PRIVATE_KEY" in err


def test_c1_startup_allows_production_with_explicit_stub_true():
    """Production + EAS_STUB_MODE=true is a valid explicit configuration."""
    code, err = _run_config_import({
        "ENVIRONMENT": "production", "EAS_STUB_MODE": "true", "EAS_PRIVATE_KEY": "",
    })
    assert code == 0, err


def test_c1_startup_allows_dev_without_eas_config():
    """Dev environment auto-defaults EAS_STUB_MODE to true — no explicit config needed."""
    code, err = _run_config_import({
        "ENVIRONMENT": "development", "EAS_STUB_MODE": "", "EAS_PRIVATE_KEY": "",
    })
    assert code == 0, err


# ── H3: Register endpoint rate limit ─────────────────────────────────────────


def test_h3_register_rate_limit_active_in_production():
    """When RATELIMIT_ENABLED=true, /v1/agents/register caps at 5/hour per IP.
    Runs in a subprocess so the module-level env-based enable flag is evaluated
    in isolation (not polluted by conftest's dev settings)."""
    import subprocess, sys, os as _os
    env = {
        **_os.environ,
        "ENVIRONMENT": "production",
        "EAS_STUB_MODE": "true",
        "RATELIMIT_ENABLED": "true",
        "DATABASE_URL": "",  # fall through to DB-unavailable path; we only care about rate limit
        "PYTHONPATH": str(_os.path.join(_os.path.dirname(__file__), "..")),
    }
    r = subprocess.run(
        [sys.executable, "-c", """
from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app)
statuses = []
for i in range(8):
    resp = c.post('/v1/agents/register', json={'did': f'did:ecp:{i:064x}', 'public_key': 'a'*64})
    statuses.append(resp.status_code)
print(statuses)
assert 429 in statuses, f'No 429 after 8 requests: {statuses}'
assert statuses[:5].count(429) == 0, f'Rate limit triggered too early: {statuses}'
"""],
        capture_output=True, text=True, env=env,
    )
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"


def test_h3_register_rate_limit_disabled_in_dev():
    """Dev environment defaults to disabled so stress tests aren't rate-limited."""
    import subprocess, sys, os as _os
    env = {
        **_os.environ,
        "ENVIRONMENT": "development",
        "EAS_STUB_MODE": "true",
        "DATABASE_URL": "",
        "PYTHONPATH": str(_os.path.join(_os.path.dirname(__file__), "..")),
    }
    r = subprocess.run(
        [sys.executable, "-c", """
from app.ratelimit import limiter
assert limiter.enabled is False, f'expected disabled in dev, got enabled={limiter.enabled}'
print('OK: limiter disabled in dev')
"""],
        capture_output=True, text=True, env=env,
    )
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"


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
@pytest.mark.parametrize("did,ok", [
    ("did:ecp:" + "a" * 32,  True),   # 32 hex OK
    ("did:ecp:" + "a" * 40,  True),   # 40 hex OK
    ("did:ecp:" + "a" * 64,  True),   # 64 hex OK
    ("did:ecp:" + "A" * 32,  True),   # uppercase hex OK
    ("did:ecp:",             False),  # empty suffix
    ("did:ecp:x",            False),  # 1 char, not enough
    ("did:ecp:" + "a" * 31,  False),  # 31 chars, below min
    ("did:ecp:" + "g" * 32,  False),  # g is not hex
    ("did:ecp:test_abc123",  False),  # non-hex characters
    ("did:ecp:" + "a" * 65,  False),  # 65 chars, above max
    ("ecp:abc",              False),  # wrong scheme
    ("",                     False),  # empty
])
async def test_m3_did_format_strict_regex(did, ok):
    """Register endpoint must strictly validate did:ecp:{32-64 hex chars}."""
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.post("/v1/agents/register", json={
        "did": did,
        "public_key": "a" * 64,
    })
    # Invalid DID → 422. Valid DID may return 429 (rate limit) or 503 (no DB in test), but NOT 422.
    if ok:
        assert resp.status_code != 422, f"Valid DID {did!r} was rejected: {resp.text}"
    else:
        assert resp.status_code == 422, f"Invalid DID {did!r} was accepted: {resp.status_code}"


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
