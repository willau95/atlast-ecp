"""Anchor threshold gate tests (Phase 3.1 C2):

Defends against gas-waste attacks where a client floods cheap micro-batches
to force expensive on-chain transactions. The gate in routes/anchor.py only
fires an anchor when:
  (a) pending_batches >= MIN_ANCHOR_BATCHES AND total_records >= MIN_ANCHOR_RECORDS
  (b) oldest batch has waited >= MAX_ANCHOR_WAIT_HOURS (anti-starvation)
"""

import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def _mk_batch(batch_id: str, record_count: int, age_hours: float = 0.0):
    """Build a fake pending batch dict in the shape _get_local_pending_batches returns."""
    now_ms = int(time.time() * 1000)
    batch_ts = now_ms - int(age_hours * 3600 * 1000)
    return {
        "batch_id": batch_id,
        "agent_did": "did:ecp:fake",
        "merkle_root": f"sha256:{batch_id}",
        "record_count": record_count,
        "avg_latency_ms": 100,
        "batch_ts": batch_ts,
        "sig": "ed25519:fake",
        "retry_count": 0,
        "_source": "local",
    }


@pytest.mark.anyio
async def test_anchor_deferred_when_below_batch_count():
    """5 batches when MIN_ANCHOR_BATCHES=10 → deferred (not anchored)."""
    from app.routes import anchor as anchor_mod

    fake_batches = [_mk_batch(f"b{i}", 1000) for i in range(5)]  # plenty of records, too few batches

    with patch.object(anchor_mod, "_get_local_pending_batches", AsyncMock(return_value=fake_batches)), \
         patch.object(anchor_mod, "get_pending_batches", AsyncMock(return_value=[])), \
         patch("app.services.anchor_coordinator.try_acquire_lock", AsyncMock(return_value=True)), \
         patch("app.services.anchor_coordinator.release_lock", AsyncMock()), \
         patch("app.services.anchor_coordinator.check_gas_balance", AsyncMock(return_value=(True, 10**18))), \
         patch("app.services.anchor_coordinator.should_retry_batch", lambda b: True), \
         patch.object(anchor_mod.settings, "MIN_ANCHOR_BATCHES", 10), \
         patch.object(anchor_mod.settings, "MIN_ANCHOR_RECORDS", 1), \
         patch.object(anchor_mod.settings, "MAX_ANCHOR_WAIT_HOURS", 168), \
         patch.object(anchor_mod.settings, "SUPER_BATCH_MIN_SIZE", 1):

        result = await anchor_mod._anchor_pending()

    assert result.get("deferred") == 5
    assert result.get("reason") == "below_anchor_threshold"
    assert result.get("anchored", 0) == 0


@pytest.mark.anyio
async def test_anchor_deferred_when_below_total_records():
    """20 batches with 2 records each (total 40) when MIN_RECORDS=100 → deferred."""
    from app.routes import anchor as anchor_mod

    fake_batches = [_mk_batch(f"b{i}", 2) for i in range(20)]  # plenty batches, too few records

    with patch.object(anchor_mod, "_get_local_pending_batches", AsyncMock(return_value=fake_batches)), \
         patch.object(anchor_mod, "get_pending_batches", AsyncMock(return_value=[])), \
         patch("app.services.anchor_coordinator.try_acquire_lock", AsyncMock(return_value=True)), \
         patch("app.services.anchor_coordinator.release_lock", AsyncMock()), \
         patch("app.services.anchor_coordinator.check_gas_balance", AsyncMock(return_value=(True, 10**18))), \
         patch("app.services.anchor_coordinator.should_retry_batch", lambda b: True), \
         patch.object(anchor_mod.settings, "MIN_ANCHOR_BATCHES", 10), \
         patch.object(anchor_mod.settings, "MIN_ANCHOR_RECORDS", 100), \
         patch.object(anchor_mod.settings, "MAX_ANCHOR_WAIT_HOURS", 168), \
         patch.object(anchor_mod.settings, "SUPER_BATCH_MIN_SIZE", 1):

        result = await anchor_mod._anchor_pending()

    assert result.get("deferred") == 20
    assert result.get("pending_records") == 40
    assert result.get("anchored", 0) == 0


@pytest.mark.anyio
async def test_anchor_fires_when_both_thresholds_met():
    """15 batches × 20 records each (total 300, meets MIN_BATCHES=10 + MIN_RECORDS=100) → anchored."""
    from app.routes import anchor as anchor_mod

    fake_batches = [_mk_batch(f"b{i}", 20) for i in range(15)]

    with patch.object(anchor_mod, "_get_local_pending_batches", AsyncMock(return_value=fake_batches)), \
         patch.object(anchor_mod, "get_pending_batches", AsyncMock(return_value=[])), \
         patch("app.services.anchor_coordinator.try_acquire_lock", AsyncMock(return_value=True)), \
         patch("app.services.anchor_coordinator.release_lock", AsyncMock()), \
         patch("app.services.anchor_coordinator.check_gas_balance", AsyncMock(return_value=(True, 10**18))), \
         patch("app.services.anchor_coordinator.should_retry_batch", lambda b: True), \
         patch.object(anchor_mod, "_anchor_super_batch", AsyncMock(return_value={"processed": 15, "anchored": 15, "errors": 0, "super_batch_id": "sb_test"})), \
         patch.object(anchor_mod.settings, "MIN_ANCHOR_BATCHES", 10), \
         patch.object(anchor_mod.settings, "MIN_ANCHOR_RECORDS", 100), \
         patch.object(anchor_mod.settings, "MAX_ANCHOR_WAIT_HOURS", 168), \
         patch.object(anchor_mod.settings, "SUPER_BATCH_MIN_SIZE", 10):

        result = await anchor_mod._anchor_pending()

    assert result.get("anchored") == 15
    assert result.get("deferred") is None or result.get("deferred") == 0


@pytest.mark.anyio
async def test_anchor_starvation_forces_low_volume_anchor():
    """1 batch aged 200 hours > MAX_WAIT=168h → force anchor even below count/records threshold."""
    from app.routes import anchor as anchor_mod

    fake_batches = [_mk_batch("old", 5, age_hours=200)]  # 1 batch, 5 records, 200h old

    with patch.object(anchor_mod, "_get_local_pending_batches", AsyncMock(return_value=fake_batches)), \
         patch.object(anchor_mod, "get_pending_batches", AsyncMock(return_value=[])), \
         patch("app.services.anchor_coordinator.try_acquire_lock", AsyncMock(return_value=True)), \
         patch("app.services.anchor_coordinator.release_lock", AsyncMock()), \
         patch("app.services.anchor_coordinator.check_gas_balance", AsyncMock(return_value=(True, 10**18))), \
         patch("app.services.anchor_coordinator.should_retry_batch", lambda b: True), \
         patch.object(anchor_mod, "_anchor_super_batch", AsyncMock(return_value={"processed": 1, "anchored": 1, "errors": 0, "super_batch_id": "sb_test"})), \
         patch.object(anchor_mod.settings, "MIN_ANCHOR_BATCHES", 10), \
         patch.object(anchor_mod.settings, "MIN_ANCHOR_RECORDS", 100), \
         patch.object(anchor_mod.settings, "MAX_ANCHOR_WAIT_HOURS", 168), \
         patch.object(anchor_mod.settings, "SUPER_BATCH_MIN_SIZE", 1):

        result = await anchor_mod._anchor_pending()

    assert result.get("anchored") == 1, f"Expected starvation override to anchor, got {result}"
