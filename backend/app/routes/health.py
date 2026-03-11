from fastapi import APIRouter
from ..database import db
from ..models import HealthResponse

router = APIRouter()


@router.get("/v1/health", response_model=HealthResponse, tags=["System"])
def health_check():
    """Health check endpoint."""
    try:
        with db() as conn:
            agents = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
            batches = conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0]
        return HealthResponse(status="ok", db="ok", agents=agents, total_batches=batches)
    except Exception as e:
        return HealthResponse(status="degraded", db=str(e), agents=0, total_batches=0)
