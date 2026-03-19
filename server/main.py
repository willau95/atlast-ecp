"""
ECP Reference Server — FastAPI Application

A minimal, open-source ECP-compatible server.
Run: python -m server.main  OR  uvicorn server.main:app

5 minutes to your own ECP Server.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import close_db, get_db
from .models import HealthResponse
from .routes.agents import router as agents_router
from .routes.batches import router as batches_router
from .routes.leaderboard import router as leaderboard_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize DB
    get_db()
    yield
    # Shutdown: close DB
    close_db()


app = FastAPI(
    title="ECP Reference Server",
    description="Open-source Evidence Chain Protocol server. Anyone can run their own.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(agents_router)
app.include_router(batches_router)
app.include_router(leaderboard_router)


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse()


@app.get("/v1/health", response_model=HealthResponse)
def health_v1():
    return HealthResponse()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.main:app", host=settings.HOST, port=settings.PORT, log_level=settings.LOG_LEVEL)
