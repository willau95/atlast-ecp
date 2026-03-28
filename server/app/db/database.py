"""
PostgreSQL Database Connection + SQLAlchemy Models.

ECP Server stores attestation records in Postgres for:
- Historical attestation lookup (vs LLaChat API polling)
- Independent audit trail (decoupled from LLaChat)
- Analytics and metrics
"""

import structlog
import sqlalchemy
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, Index, TIMESTAMP
from datetime import datetime, timezone

from ..config import settings

logger = structlog.get_logger()


class Base(DeclarativeBase):
    pass


class Attestation(Base):
    """On-chain attestation record."""
    __tablename__ = "attestations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String(64), unique=True, nullable=False, index=True)
    agent_did = Column(String(128), nullable=False, index=True)
    merkle_root = Column(String(128), nullable=False)
    record_count = Column(Integer, nullable=False, default=0)
    attestation_uid = Column(String(128), nullable=True, index=True)  # not unique: super-batch shares UID
    eas_tx_hash = Column(String(128), nullable=True)
    schema_uid = Column(String(128), nullable=True)
    chain_id = Column(Integer, nullable=True)
    on_chain = Column(Boolean, default=False)
    webhook_sent = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc))
    anchored_at = Column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_attestations_agent_created", "agent_did", "created_at"),
    )


class SuperBatch(Base):
    """Super-batch aggregation record — groups multiple agent batches into one EAS attestation."""
    __tablename__ = "super_batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    super_batch_id = Column(String(64), unique=True, nullable=False, index=True)
    super_merkle_root = Column(String(128), nullable=False)
    attestation_uid = Column(String(128), nullable=True)
    eas_tx_hash = Column(String(128), nullable=True)
    batch_count = Column(Integer, nullable=False)
    batch_ids = Column(Text, nullable=False)  # JSON array of batch_ids
    status = Column(String(20), default="pending")
    created_at = Column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc))
    anchored_at = Column(TIMESTAMP(timezone=True), nullable=True)


class AnchorLog(Base):
    """Cron anchor run log."""
    __tablename__ = "anchor_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_at = Column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc))
    processed = Column(Integer, default=0)
    anchored = Column(Integer, default=0)
    errors = Column(Integer, default=0)
    duration_ms = Column(Integer, default=0)
    error_detail = Column(Text, nullable=True)


# ── Engine + Session ────────────────────────────────────────────────────────

_engine = None
_session_factory = None


def _get_async_url(url: str) -> str:
    """Convert sync postgres URL to async (asyncpg)."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


async def init_db():
    """Initialize database: create engine + tables."""
    global _engine, _session_factory

    if not settings.DATABASE_URL:
        logger.info("db_skipped", reason="DATABASE_URL not configured")
        return

    async_url = _get_async_url(settings.DATABASE_URL)
    _engine = create_async_engine(async_url, echo=False, pool_size=10, max_overflow=20, pool_recycle=1800)
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    # Import all models so Base.metadata knows about them
    from .models import Agent, APIKey, Batch, AnchorLock, AnchorState  # noqa: F401

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Run lightweight schema migrations (idempotent ALTER statements)
    await _run_migrations()

    logger.info("db_initialized", tables=["attestations", "anchor_logs", "agents", "api_keys", "batches"])


async def _run_migrations():
    """Idempotent schema migrations — safe to run on every startup."""
    if _engine is None:
        return
    migrations = [
        # v0.9.0: Fix DateTime → TIMESTAMPTZ for asyncpg tz-aware compat
        "ALTER TABLE attestations ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC'",
        "ALTER TABLE attestations ALTER COLUMN anchored_at TYPE TIMESTAMPTZ USING anchored_at AT TIME ZONE 'UTC'",
        "ALTER TABLE anchor_logs ALTER COLUMN run_at TYPE TIMESTAMPTZ USING run_at AT TIME ZONE 'UTC'",
        # v1.1.0: Batch retry tracking
        "ALTER TABLE batches ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0",
        "ALTER TABLE batches ADD COLUMN IF NOT EXISTS last_retry_at TIMESTAMPTZ",
        "ALTER TABLE batches ADD COLUMN IF NOT EXISTS error_message TEXT",
    ]
    async with _engine.begin() as conn:
        for sql in migrations:
            try:
                await conn.execute(sqlalchemy.text(sql))
            except Exception:
                pass  # Column already correct type — ignore


async def get_session() -> AsyncSession | None:
    """Get a database session (or None if DB not configured)."""
    if _session_factory is None:
        return None
    return _session_factory()


async def close_db():
    """Close database connection."""
    global _engine
    if _engine:
        await _engine.dispose()
        logger.info("db_closed")
