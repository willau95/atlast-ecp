"""
ECP Backend — FastAPI Application
ECP-SPEC.md §10: POST /v1/agent/register, POST /v1/batch,
                  GET /v1/agent/{did}, GET /v1/verify/{record_id},
                  GET /v1/health
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .database import init_db
from .routes import agents, batches, verify, health

# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB on startup."""
    init_db()
    print("✅ ECP Backend started. DB initialized.")
    print(f"   EAS mode: {os.environ.get('EAS_MODE', 'stub')}")
    print(f"   DB path: {os.environ.get('ECP_DB_PATH', 'ecp.db')}")
    yield


# ─── App Setup ────────────────────────────────────────────────────────────────

app = FastAPI(
    lifespan=lifespan,
    title="ECP Backend API",
    description=(
        "ATLAST Evidence Chain Protocol — Backend API\n\n"
        "Records Merkle Root hashes from ECP SDK clients and anchors them "
        "on-chain via EAS on Base.\n\n"
        "**Privacy:** Only cryptographic hashes are stored. Content NEVER leaves "
        "the user's device."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow SDK and LLaChat frontend
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ─── Routes ───────────────────────────────────────────────────────────────────

app.include_router(health.router)
app.include_router(agents.router)
app.include_router(batches.router)
app.include_router(verify.router)

# ─── Root ─────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def root():
    return {
        "name": "ECP Backend API",
        "version": "0.1.0",
        "ecp_version": "0.1",
        "docs": "/docs",
        "health": "/v1/health",
        "protocol": "ATLAST Evidence Chain Protocol",
        "homepage": "https://llachat.com",
    }


# ─── Global Error Handler ─────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all: never expose internal errors to clients."""
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )



