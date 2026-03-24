"""
Behavioral Drift Detection — detects when an agent's patterns shift over time.

Compares recent batch statistics (token usage, tool calls, confidence, latency)
against a historical baseline window. When deviation exceeds thresholds,
drift_detected=True and changed_dimensions lists the anomalous metrics.

Algorithm:
  - Baseline: last N batches (default 20)
  - Current: most recent M batches (default 5)
  - For each metric: compute z-score of current mean vs baseline distribution
  - If any z-score > threshold (default 2.0): drift detected
"""

import math
from dataclasses import dataclass, field
from typing import Optional

import structlog

from ..db.database import get_session
from ..db.models import Batch

logger = structlog.get_logger()

# ── Configuration ──

BASELINE_WINDOW = 20  # number of older batches for baseline
CURRENT_WINDOW = 5    # number of recent batches for current
Z_THRESHOLD = 2.0     # z-score threshold for drift detection


@dataclass
class DriftDimension:
    name: str
    baseline_mean: float
    baseline_std: float
    current_mean: float
    z_score: float
    drifted: bool


@dataclass
class DriftResult:
    drift_score: float  # 0-1 normalized
    drift_detected: bool
    changed_dimensions: list[DriftDimension] = field(default_factory=list)
    baseline_window: int = 0
    current_window: int = 0
    total_batches: int = 0
    error: Optional[str] = None


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    variance = sum((v - m) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def _z_score(current_mean: float, baseline_mean: float, baseline_std: float) -> float:
    if baseline_std == 0:
        if current_mean == baseline_mean:
            return 0.0
        return 3.0  # max drift signal when baseline is constant but current differs
    return abs(current_mean - baseline_mean) / baseline_std


async def compute_drift(agent_did: str) -> DriftResult:
    """
    Compute behavioral drift for an agent based on their batch history.

    Returns DriftResult with drift_score (0-1), detection flag, and changed dimensions.
    """
    session = await get_session()
    if session is None:
        return DriftResult(
            drift_score=0.0, drift_detected=False,
            error="Database not available"
        )

    from sqlalchemy import select

    try:
        async with session:
            result = await session.execute(
                select(Batch)
                .where(Batch.agent_did == agent_did)
                .order_by(Batch.created_at.desc())
                .limit(BASELINE_WINDOW + CURRENT_WINDOW)
            )
            batches = result.scalars().all()
    except Exception as e:
        logger.warning("drift_query_failed", agent_did=agent_did, error=str(e))
        return DriftResult(
            drift_score=0.0, drift_detected=False,
            error=str(e)
        )

    total = len(batches)
    if total < CURRENT_WINDOW + 3:  # need at least 3 baseline + current window
        return DriftResult(
            drift_score=0.0, drift_detected=False,
            total_batches=total,
            error="Insufficient data for drift analysis" if total > 0 else None
        )

    # Split: most recent = current, rest = baseline
    # batches are ordered desc, so [0:CURRENT_WINDOW] = most recent
    current_batches = batches[:CURRENT_WINDOW]
    baseline_batches = batches[CURRENT_WINDOW:]

    # Extract metrics
    metrics = {
        "record_count": lambda b: b.record_count or 0,
        "avg_latency_ms": lambda b: b.avg_latency_ms or 0,
    }

    dimensions: list[DriftDimension] = []
    max_z = 0.0

    for metric_name, extractor in metrics.items():
        baseline_vals = [float(extractor(b)) for b in baseline_batches]
        current_vals = [float(extractor(b)) for b in current_batches]

        b_mean = _mean(baseline_vals)
        b_std = _std(baseline_vals)
        c_mean = _mean(current_vals)
        z = _z_score(c_mean, b_mean, b_std)

        drifted = z > Z_THRESHOLD
        dimensions.append(DriftDimension(
            name=metric_name,
            baseline_mean=round(b_mean, 2),
            baseline_std=round(b_std, 2),
            current_mean=round(c_mean, 2),
            z_score=round(z, 2),
            drifted=drifted,
        ))
        max_z = max(max_z, z)

    # Normalize drift_score to 0-1 (z=0 → 0, z≥4 → 1)
    drift_score = min(max_z / 4.0, 1.0)
    drift_detected = any(d.drifted for d in dimensions)

    return DriftResult(
        drift_score=round(drift_score, 3),
        drift_detected=drift_detected,
        changed_dimensions=[d for d in dimensions if d.drifted],
        baseline_window=len(baseline_batches),
        current_window=len(current_batches),
        total_batches=total,
    )
