"""
ECP Backend — Pydantic Models (Request / Response)
Strictly follows ECP-SPEC.md §10
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional
import re


# ─── Agent Registration ───────────────────────────────────────────────────────

class AgentRegisterRequest(BaseModel):
    did: str = Field(..., description="Agent DID. Format: did:ecp:{32 hex chars}")
    public_key: str = Field(..., description="ed25519 public key hex (64 chars)")
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    owner_x_handle: Optional[str] = Field(None, max_length=50)
    ecp_version: str = Field("0.1")

    @field_validator("did")
    @classmethod
    def validate_did(cls, v: str) -> str:
        if not re.match(r"^did:ecp:[0-9a-f]{32}$", v):
            raise ValueError("Invalid DID format. Expected: did:ecp:{32 hex chars}")
        return v

    @field_validator("public_key")
    @classmethod
    def validate_public_key(cls, v: str) -> str:
        if not re.match(r"^[0-9a-f]{64}$", v):
            raise ValueError("Invalid public_key. Expected 64 hex chars (ed25519 raw public key)")
        return v


class AgentRegisterResponse(BaseModel):
    agent_did: str
    claim_url: str
    verification_tweet: str
    status: str = "pending_verification"


# ─── Batch Upload ─────────────────────────────────────────────────────────────

class RecordHashEntry(BaseModel):
    """Individual record hash for Merkle proof storage."""
    id: str = Field(..., description="ECP record ID (rec_{hex})")
    hash: str = Field(..., description="Record chain hash (sha256:{hex})")
    flags: Optional[list[str]] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def validate_record_id(cls, v: str) -> str:
        if not v.startswith("rec_"):
            raise ValueError("Record ID must start with rec_")
        return v

    @field_validator("hash")
    @classmethod
    def validate_hash(cls, v: str) -> str:
        if not v.startswith("sha256:"):
            raise ValueError("Hash must start with sha256:")
        return v


class BatchUploadRequest(BaseModel):
    agent_did: str
    merkle_root: str = Field(..., description="Merkle root of this batch (sha256:{hex})")
    record_count: int = Field(..., ge=1, description="Number of records in batch")
    avg_latency_ms: int = Field(0, ge=0)
    batch_ts: int = Field(..., description="Unix timestamp ms of batch")
    ecp_version: str = Field("0.1")
    sig: str = Field(..., description="ed25519 signature of merkle_root (ed25519:{hex})")
    # Optional: individual record hashes for per-record verification
    record_hashes: Optional[list[RecordHashEntry]] = Field(
        None,
        description="Individual record hashes. Optional but enables per-record verification."
    )
    # Optional behavioral flags (aggregated counts from this batch)
    flag_counts: Optional[dict[str, int]] = Field(
        None,
        description="Aggregated flag counts: {retried: N, hedged: N, ...}"
    )

    @field_validator("merkle_root")
    @classmethod
    def validate_merkle_root(cls, v: str) -> str:
        if not v.startswith("sha256:"):
            raise ValueError("merkle_root must start with sha256:")
        return v

    @field_validator("sig")
    @classmethod
    def validate_sig(cls, v: str) -> str:
        if v != "unverified" and not v.startswith("ed25519:"):
            raise ValueError("sig must be 'unverified' or start with 'ed25519:'")
        return v


class BatchUploadResponse(BaseModel):
    batch_id: str
    attestation_uid: Optional[str] = None
    eas_url: Optional[str] = None
    anchored_at: Optional[int] = None
    status: str = "pending_anchor"   # or "anchored"
    message: str = "Batch received. EAS anchoring scheduled."


# ─── Agent Profile ────────────────────────────────────────────────────────────

class TrustScoreInputs(BaseModel):
    """Raw ECP data for Trust Score computation (computed by LLaChat, not ECP)."""
    total_records: int
    total_batches: int
    active_days: int
    chain_integrity: float
    avg_latency_ms: int
    flag_rates: dict[str, float]   # retried_rate, hedged_rate, etc.
    recording_level: str           # "turn" | "tool_call" | "llm_call"
    first_record_ts: Optional[int]
    last_record_ts: Optional[int]


class AgentProfileResponse(BaseModel):
    did: str
    name: Optional[str]
    description: Optional[str]
    owner_x_handle: Optional[str]
    ecp_version: str
    verified: bool
    created_at: int
    trust_score_inputs: TrustScoreInputs
    profile_url: str
    latest_attestation_uid: Optional[str] = None


# ─── Record Verification ──────────────────────────────────────────────────────

class MerkleProof(BaseModel):
    root: str
    path: list[dict]               # [{hash: "sha256:...", position: "left|right"}]
    attestation_uid: Optional[str]
    eas_url: Optional[str]


class VerifyResponse(BaseModel):
    record_id: str
    agent_did: str
    chain_hash: str
    chain_valid: bool
    merkle_proof: Optional[MerkleProof]
    verification_result: str       # "VALID" | "UNVERIFIED" | "INVALID"
    message: str


# ─── Health ───────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    ecp_version: str = "0.1"
    db: str = "ok"
    agents: int = 0
    total_batches: int = 0
