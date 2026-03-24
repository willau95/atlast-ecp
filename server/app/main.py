"""
ATLAST ECP Server — Evidence Chain Protocol Backend

Handles:
- EAS on-chain anchoring (automated cron)
- Webhook dispatch to LLaChat
- .well-known/ecp.json discovery
- Attestation verification
- Health + metrics
"""

import uuid
import structlog
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .config import settings

# ── Rate Limiter ────────────────────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

# ── Structured Logging ──────────────────────────────────────────────────────

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer() if settings.ENVIRONMENT != "production"
        else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),
)
logger = structlog.get_logger()

# ── Sentry ──────────────────────────────────────────────────────────────────

if settings.SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=0.1,
        environment=settings.ENVIRONMENT,
    )

# ── Scheduler ───────────────────────────────────────────────────────────────

scheduler = AsyncIOScheduler()
_cron_state = {
    "last_run": None,
    "last_result": None,
    "last_error": None,
    "consecutive_failures": 0,
}


async def _scheduled_anchor():
    """Cron job: anchor pending batches."""
    from .routes.anchor import _anchor_pending

    _cron_state["last_run"] = datetime.now(timezone.utc).isoformat()
    try:
        result = await _anchor_pending()
        _cron_state["last_result"] = result
        _cron_state["last_error"] = None
        _cron_state["consecutive_failures"] = 0
        from .routes.metrics import cron_failures
        cron_failures.set(0)
        logger.info("cron_anchor_done", **result)
    except Exception as e:
        _cron_state["last_error"] = str(e)
        _cron_state["consecutive_failures"] += 1
        from .routes.metrics import cron_failures
        cron_failures.set(_cron_state["consecutive_failures"])
        logger.error("cron_anchor_failed", error=str(e), consecutive=_cron_state["consecutive_failures"])
        if _cron_state["consecutive_failures"] >= 3:
            from .services.monitoring import capture_error
            capture_error(e, {"context": "cron_anchor", "consecutive": _cron_state["consecutive_failures"]})


# ── Lifespan ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    interval = settings.ANCHOR_INTERVAL_MINUTES
    logger.info(
        "ecp_server_starting",
        eas_chain=settings.EAS_CHAIN,
        stub=settings.EAS_STUB_MODE,
        anchor_interval=f"{interval}min",
    )
    # Run first anchor 60s after startup, then every interval
    from datetime import timedelta
    first_run = datetime.now(timezone.utc) + timedelta(seconds=60)
    scheduler.add_job(
        _scheduled_anchor,
        "interval",
        minutes=interval,
        id="anchor_cron",
        next_run_time=first_run,
    )
    scheduler.start()
    logger.info("cron_started", interval_minutes=interval)

    # Init database (if configured)
    try:
        from .db.database import init_db
        await init_db()
    except Exception as e:
        logger.warning("db_init_failed", error=str(e))

    yield

    # Cleanup
    try:
        from .db.database import close_db
        await close_db()
    except Exception:
        pass
    scheduler.shutdown(wait=False)
    logger.info("ecp_server_stopped")


# ── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="ATLAST ECP Server",
    description="Evidence Chain Protocol — EAS anchoring, verification, and webhook dispatch",
    version="1.0.0",
    lifespan=lifespan,
)

# Rate limiting — SlowAPIMiddleware applies default_limits to all routes
from slowapi.middleware import SlowAPIMiddleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS — production-safe origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ── Security Headers Middleware ─────────────────────────────────────────────

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # X-Request-ID
    req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    response.headers["X-Request-ID"] = req_id
    return response


# ── Request Size Limit Middleware ───────────────────────────────────────────

@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 10 * 1024 * 1024:  # 10MB
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=413, content={"detail": "Request body too large"})
    return await call_next(request)


# ── Global Exception Handler ────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    from .services.monitoring import capture_error
    capture_error(exc, {"context": "unhandled", "path": str(request.url), "method": request.method})
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


# ── Routes ──────────────────────────────────────────────────────────────────

from .routes.health import router as health_router
from .routes.discovery import router as discovery_router
from .routes.anchor import router as anchor_router
from .routes.cron import router as cron_router
from .routes.verify import router as verify_router
from .routes.attestations import router as attestations_router
from .routes.metrics import router as metrics_router
from .routes.auth import router as auth_router
from .routes.batches import router as batches_router
from .routes.agents import router as agents_router
from .routes.super_batches import router as super_batches_router

app.include_router(health_router)
app.include_router(discovery_router)
app.include_router(anchor_router)
app.include_router(cron_router)
app.include_router(verify_router)
app.include_router(attestations_router)
app.include_router(metrics_router)
app.include_router(auth_router)
app.include_router(batches_router)
app.include_router(agents_router)
app.include_router(super_batches_router)

# Init stats tracking
from .routes.verify import init_stats
init_stats()

# Expose cron_state for cron router
app.state.cron_state = _cron_state
app.state.scheduler = scheduler
