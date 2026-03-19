"""
ECP Reference Server — Trust Score Computation

Weights match SDK signals.py compute_trust_signals():
  Reliability 40%, Transparency 30%, Efficiency 20%, Authority 10%

This is a reference implementation — servers MAY use different algorithms.
"""

from __future__ import annotations

from .config import settings


def compute_trust_signals(
    total_records: int,
    total_batches: int,
    flag_counts: dict,
) -> dict:
    """Compute 4-dimensional trust signals from batch metadata."""
    total_flags = sum(flag_counts.values())

    # Reliability: 1.0 - (error + incomplete) / total_records
    error_flags = flag_counts.get("error", 0) + flag_counts.get("incomplete", 0)
    reliability = max(0.0, 1.0 - (error_flags / max(total_records, 1)))

    # Transparency: based on consistent batching (records per batch)
    # More consistent = more transparent. Max at 1.0.
    if total_batches > 0:
        avg_per_batch = total_records / total_batches
        # Sweet spot: 5-50 records per batch = 1.0
        if 5 <= avg_per_batch <= 50:
            transparency = 1.0
        elif avg_per_batch < 5:
            transparency = avg_per_batch / 5.0
        else:
            transparency = max(0.5, 50.0 / avg_per_batch)
    else:
        transparency = 0.0

    # Efficiency: 1.0 - (high_latency + retried) / total_records
    slow_flags = flag_counts.get("high_latency", 0) + flag_counts.get("retried", 0)
    efficiency = max(0.0, 1.0 - (slow_flags / max(total_records, 1)))

    # Authority: based on record volume (log scale, max at 1000 records)
    import math
    if total_records > 0:
        authority = min(1.0, math.log10(total_records) / 3.0)  # log10(1000) = 3
    else:
        authority = 0.0

    return {
        "reliability": round(reliability, 4),
        "transparency": round(transparency, 4),
        "efficiency": round(efficiency, 4),
        "authority": round(authority, 4),
    }


def compute_overall_score(signals: dict) -> float:
    """Weighted overall score."""
    score = (
        signals["reliability"] * settings.WEIGHT_RELIABILITY
        + signals["transparency"] * settings.WEIGHT_TRANSPARENCY
        + signals["efficiency"] * settings.WEIGHT_EFFICIENCY
        + signals["authority"] * settings.WEIGHT_AUTHORITY
    )
    return round(score, 4)
