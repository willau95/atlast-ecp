"""
Cron status endpoint — read-only, shows anchor cron health.
"""

from fastapi import APIRouter, Request, Header, HTTPException
from ..config import settings

router = APIRouter()


def _require_internal_token(token: str | None):
    if settings.ENVIRONMENT == "production":
        import secrets
        if not token or not secrets.compare_digest(token, settings.LLACHAT_INTERNAL_TOKEN):
            raise HTTPException(status_code=401, detail="Invalid internal token")


@router.get("/v1/internal/cron-status", tags=["Internal"])
async def cron_status(
    request: Request,
    x_internal_token: str | None = Header(None, alias="X-Internal-Token"),
):
    """
    Returns anchor cron health:
    - last_run: ISO timestamp of last execution
    - last_result: {processed, anchored, errors}
    - next_run: ISO timestamp of next scheduled run
    - consecutive_failures: 0 = healthy
    """
    _require_internal_token(x_internal_token)

    state = request.app.state.cron_state
    sched = request.app.state.scheduler

    # Get next run time
    job = sched.get_job("anchor_cron")
    next_run = job.next_run_time.isoformat() if job and job.next_run_time else None

    return {
        "status": "healthy" if state["consecutive_failures"] < 3 else "degraded",
        "last_run": state["last_run"],
        "last_result": state["last_result"],
        "last_error": state["last_error"],
        "consecutive_failures": state["consecutive_failures"],
        "next_run": next_run,
        "interval_minutes": settings.ANCHOR_INTERVAL_MINUTES,
    }
