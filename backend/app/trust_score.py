"""
ECP Backend — Trust Score Inputs
Computes raw ECP metrics from stored batch data.
Trust Score itself is computed by LLaChat, NOT ECP.
ECP only provides the objective behavioral data.
"""

import time
from typing import Optional


VALID_FLAGS = ["retried", "hedged", "incomplete", "high_latency", "error", "human_review", "a2a_delegated"]


def compute_trust_inputs(stats_row: dict, latest_attestation_uid: Optional[str] = None) -> dict:
    """
    Compute Trust Score input metrics from agent_stats row.
    Returns dict matching TrustScoreInputs model.
    """
    total = stats_row.get("total_records", 0)
    if total == 0:
        return _empty_inputs()

    def rate(count_key: str) -> float:
        count = stats_row.get(count_key, 0)
        return round(count / total, 4) if total > 0 else 0.0

    return {
        "total_records": total,
        "total_batches": stats_row.get("total_batches", 0),
        "active_days": stats_row.get("active_days", 0),
        "chain_integrity": float(stats_row.get("chain_integrity", 1.0)),
        "avg_latency_ms": stats_row.get("avg_latency_ms", 0),
        "flag_rates": {
            "retried_rate": rate("retried_count"),
            "hedged_rate": rate("hedged_count"),
            "incomplete_rate": rate("incomplete_count"),
            "high_latency_rate": rate("high_latency_count"),
            "error_rate": rate("error_count"),
            "human_review_rate": rate("human_review_count"),
        },
        "recording_level": _infer_recording_level(stats_row),
        "first_record_ts": stats_row.get("first_record_ts"),
        "last_record_ts": stats_row.get("last_record_ts"),
    }


def _empty_inputs() -> dict:
    return {
        "total_records": 0,
        "total_batches": 0,
        "active_days": 0,
        "chain_integrity": 1.0,
        "avg_latency_ms": 0,
        "flag_rates": {f"{f}_rate": 0.0 for f in VALID_FLAGS},
        "recording_level": "unknown",
        "first_record_ts": None,
        "last_record_ts": None,
    }


def _infer_recording_level(stats_row: dict) -> str:
    """
    Infer the recording level from the most common step type used.
    ECP-SPEC §3.1: llm_call > tool_call > turn
    """
    # TODO: store recording_level per batch and pick most common
    # For MVP, return "unknown" — UI shows this as generic
    return "unknown"


def update_stats_from_batch(
    conn,
    agent_did: str,
    record_count: int,
    avg_latency_ms: int,
    flag_counts: Optional[dict],
    batch_ts: int,
):
    """
    Update agent_stats after a new batch is received.
    Incremental update — safe to call repeatedly.
    """
    now = int(time.time() * 1000)
    flag_counts = flag_counts or {}

    # Upsert stats
    existing = conn.execute(
        "SELECT * FROM agent_stats WHERE agent_did = ?", (agent_did,)
    ).fetchone()

    if existing is None:
        conn.execute("""
            INSERT INTO agent_stats (
                agent_did, total_records, total_batches, avg_latency_ms,
                retried_count, hedged_count, incomplete_count,
                high_latency_count, error_count, human_review_count,
                chain_integrity, active_days,
                first_record_ts, last_record_ts, updated_at
            ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, 1.0, 1, ?, ?, ?)
        """, (
            agent_did, record_count, avg_latency_ms,
            flag_counts.get("retried", 0),
            flag_counts.get("hedged", 0),
            flag_counts.get("incomplete", 0),
            flag_counts.get("high_latency", 0),
            flag_counts.get("error", 0),
            flag_counts.get("human_review", 0),
            batch_ts, batch_ts, now,
        ))
    else:
        prev_total = existing["total_records"]
        new_total = prev_total + record_count
        # Weighted average latency
        new_avg_latency = int(
            (existing["avg_latency_ms"] * prev_total + avg_latency_ms * record_count)
            / new_total
        ) if new_total > 0 else 0

        conn.execute("""
            UPDATE agent_stats SET
                total_records = total_records + ?,
                total_batches = total_batches + 1,
                avg_latency_ms = ?,
                retried_count = retried_count + ?,
                hedged_count = hedged_count + ?,
                incomplete_count = incomplete_count + ?,
                high_latency_count = high_latency_count + ?,
                error_count = error_count + ?,
                human_review_count = human_review_count + ?,
                last_record_ts = MAX(last_record_ts, ?),
                updated_at = ?
            WHERE agent_did = ?
        """, (
            record_count, new_avg_latency,
            flag_counts.get("retried", 0),
            flag_counts.get("hedged", 0),
            flag_counts.get("incomplete", 0),
            flag_counts.get("high_latency", 0),
            flag_counts.get("error", 0),
            flag_counts.get("human_review", 0),
            batch_ts, now, agent_did,
        ))
