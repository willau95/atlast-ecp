"""
ECP Reference Server — Pydantic Models

Request/response schemas for all 4 ECP Server endpoints.
Supports both ECP v0.1 (nested) and v1.0 (flat) record formats.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ─── Agent Registration ───


class AgentRegisterRequest(BaseModel):
    did: str = Field(..., description="Agent DID, e.g. did:ecp:z6Mk...")
    public_key: str = Field(..., description="Base64-encoded Ed25519 public key")
    handle: Optional[str] = Field(None, description="Optional handle (auto-generated if omitted)")
    display_name: Optional[str] = Field(None, description="Optional display name")


class AgentRegisterResponse(BaseModel):
    agent_id: str
    did: str
    handle: str
    api_key: str = Field(..., description="API key (atl_ + 32 hex). Returned once — store it.")
    claim_url: Optional[str] = None


# ─── Batch Upload ───


class RecordHash(BaseModel):
    """Per-record metadata in a batch upload. Hashes only, no content."""
    record_id: str
    chain_hash: str
    step_type: Optional[str] = None
    ts: Optional[int] = None
    flags: list[str] = Field(default_factory=list)
    latency_ms: Optional[int] = None
    model: Optional[str] = None


class FlagCounts(BaseModel):
    hedged: int = 0
    high_latency: int = 0
    error: int = 0
    retried: int = 0
    incomplete: int = 0
    human_review: int = 0


class BatchUploadRequest(BaseModel):
    agent_did: str
    batch_ts: int
    record_hashes: list[RecordHash]
    merkle_root: str
    record_count: int
    flag_counts: Optional[FlagCounts] = None


class BatchUploadResponse(BaseModel):
    batch_id: str
    record_count: int
    merkle_root: str
    status: str = "accepted"


# ─── Agent Profile ───


class TrustSignals(BaseModel):
    reliability: float = 0.0
    transparency: float = 0.0
    efficiency: float = 0.0
    authority: float = 0.0


class AgentProfile(BaseModel):
    agent_id: str
    did: str
    handle: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    total_records: int = 0
    total_batches: int = 0
    first_seen: Optional[str] = None
    last_active: Optional[str] = None
    trust_signals: TrustSignals = Field(default_factory=TrustSignals)


# ─── Leaderboard ───


class LeaderboardEntry(BaseModel):
    rank: int
    handle: str
    did: str
    score: float
    record_count: int = 0
    batch_count: int = 0


class LeaderboardResponse(BaseModel):
    period: str = "all"
    domain: str = "all"
    agents: list[LeaderboardEntry] = Field(default_factory=list)


# ─── Health ───


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    ecp_spec: str = "1.0"
