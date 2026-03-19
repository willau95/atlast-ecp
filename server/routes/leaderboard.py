"""
ECP Reference Server — Leaderboard Route

GET /v1/leaderboard
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from .. import database as db
from ..models import LeaderboardEntry, LeaderboardResponse
from ..scoring import compute_overall_score, compute_trust_signals

router = APIRouter(prefix="/v1", tags=["leaderboard"])


@router.get("/leaderboard", response_model=LeaderboardResponse)
def get_leaderboard(
    period: str = Query("all", pattern="^(24h|7d|30d|all)$"),
    domain: str = Query("all"),
    limit: int = Query(20, ge=1, le=100),
):
    rows = db.get_leaderboard(period=period, domain=domain, limit=limit)

    entries = []
    for i, row in enumerate(rows):
        # Get full stats for scoring
        stats = db.get_agent_stats(row["id"])
        signals = compute_trust_signals(
            total_records=stats["total_records"],
            total_batches=stats["total_batches"],
            flag_counts=stats["flag_counts"],
        )
        score = compute_overall_score(signals)

        entries.append(LeaderboardEntry(
            rank=i + 1,
            handle=row["handle"],
            did=row["did"],
            score=score,
            record_count=row["record_count"],
            batch_count=row["batch_count"],
        ))

    # Re-sort by score (not just record count)
    entries.sort(key=lambda e: e.score, reverse=True)
    for i, e in enumerate(entries):
        e.rank = i + 1

    return LeaderboardResponse(period=period, domain=domain, agents=entries)
