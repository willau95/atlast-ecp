"""Health check endpoint."""

from fastapi import APIRouter
from ..config import settings

router = APIRouter()


@router.get("/health")
@router.get("/v1/health")
async def health():
    return {
        "status": "ok",
        "service": "ecp-server",
        "version": "1.0.0",
        "eas_chain": settings.EAS_CHAIN,
        "eas_stub": settings.EAS_STUB_MODE,
    }
