"""
Additional database models for ATLAST ECP Server.
API Keys, Agents, and Batch records for direct SDK → Server path.
"""

from sqlalchemy import Column, String, Integer, BigInteger, Float, Boolean, Text, Index, JSON
from sqlalchemy.types import TIMESTAMP
from datetime import datetime, timezone

from .database import Base


class AnchorLock(Base):
    """Distributed lock for anchor coordination — prevents concurrent anchoring."""
    __tablename__ = "anchor_lock"

    id = Column(String(32), primary_key=True, default="singleton")
    instance_id = Column(String(64), nullable=False)
    acquired_at = Column(TIMESTAMP(timezone=True), nullable=False)
    ttl_seconds = Column(Integer, default=300)


class AnchorState(Base):
    """Persistent anchor state — nonce tracking."""
    __tablename__ = "anchor_state"

    id = Column(String(32), primary_key=True, default="singleton")
    last_nonce = Column(Integer, nullable=True)
    last_tx_hash = Column(String(128), nullable=True)
    last_success_at = Column(TIMESTAMP(timezone=True), nullable=True)
    wallet_balance_wei = Column(String(64), nullable=True)


def _utcnow():
    return datetime.now(timezone.utc)


class Agent(Base):
    """Registered agent."""
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    did = Column(String(128), unique=True, nullable=False, index=True)
    public_key = Column(String(256), nullable=True)
    ecp_version = Column(String(16), default="0.1")
    created_at = Column(TIMESTAMP(timezone=True), default=_utcnow)
    last_seen = Column(TIMESTAMP(timezone=True), nullable=True)


class APIKey(Base):
    """API key for agent authentication."""
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key_prefix = Column(String(16), nullable=False, index=True)  # ak_live_xxxx (first 12 chars)
    key_hash = Column(String(128), unique=True, nullable=False)  # SHA-256 of full key
    agent_did = Column(String(128), nullable=False, index=True)
    rate_limit_tier = Column(String(32), default="free")  # free / pro / enterprise
    active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP(timezone=True), default=_utcnow)
    last_used = Column(TIMESTAMP(timezone=True), nullable=True)
    rotated_from = Column(String(128), nullable=True)  # Previous key hash (for rotation audit trail)


class Batch(Base):
    """Batch uploaded directly by SDK (not via LLaChat)."""
    __tablename__ = "batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String(64), unique=True, nullable=False, index=True)
    agent_did = Column(String(128), nullable=False, index=True)
    merkle_root = Column(String(128), nullable=False)
    record_count = Column(Integer, nullable=False, default=0)
    avg_latency_ms = Column(Integer, default=0)
    batch_ts = Column(BigInteger, nullable=False)  # Unix ms (needs BigInteger: >2^31)
    sig = Column(String(256), nullable=False)
    ecp_version = Column(String(16), default="0.1")
    record_hashes = Column(JSON, nullable=True)
    flag_counts = Column(JSON, nullable=True)
    chain_integrity = Column(Float, nullable=True)
    status = Column(String(32), default="pending")  # pending / anchored / failed
    attestation_uid = Column(String(128), nullable=True)
    eas_tx_hash = Column(String(128), nullable=True)
    retry_count = Column(Integer, default=0)
    last_retry_at = Column(TIMESTAMP(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), default=_utcnow)

    __table_args__ = (
        Index("ix_batches_status_created", "status", "created_at"),
        Index("ix_batches_agent_created", "agent_did", "created_at"),
    )
