"""
ECP Record — data structure, chaining, and hashing.

Supports two formats:
  - v1.0 Minimal (flat): 6 required fields, no chain/sig needed
  - v0.1 Full (nested):  chain + signature + DID (backward compat)

Key conventions:
  - id format:          rec_{uuid_hex}
  - in_hash/out_hash:   sha256:{hex}
  - chain.prev:         "genesis" for first record (NOT None)
  - chain.hash:         sha256:{hex} of canonical JSON record
  - sig:                ed25519:{hex} (from identity.sign)
  - agent DID:          did:ecp:{sha256(pubkey)[:32]}
"""

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


# ─── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class ECPStep:
    type: str                       # "llm_call" | "tool_call" | "turn" | "a2a_call"
    in_hash: str                    # "sha256:{hex}"
    out_hash: str                   # "sha256:{hex}"
    latency_ms: int = 0
    flags: list = field(default_factory=list)
    model: Optional[str] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost_usd: Optional[float] = None
    parent_agent: Optional[str] = None   # for A2A scenarios


@dataclass
class ECPChain:
    prev: str                       # "genesis" for first, else rec_id
    hash: str                       # "sha256:{hex}" of canonical record


@dataclass
class ECPAnchor:
    batch_id: Optional[str] = None
    tx_hash: Optional[str] = None
    ts: Optional[int] = None


@dataclass
class ECPRecord:
    id: str                         # "rec_{hex}"
    agent: str                      # "did:ecp:{id}"
    ts: int                         # unix ms
    step: ECPStep
    chain: ECPChain
    sig: str                        # "ed25519:{hex}" or "unverified"
    anchor: ECPAnchor = field(default_factory=ECPAnchor)


# ─── Hashing ──────────────────────────────────────────────────────────────────

def _sha256_hex(data: str) -> str:
    """Raw SHA-256 hex."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def sha256(data: str) -> str:
    """SHA-256 with sha256: prefix (spec format)."""
    return f"sha256:{_sha256_hex(data)}"


def hash_content(content) -> str:
    """
    Hash any content (str, list, dict) with sha256: prefix.
    Content stays local — only hash is transmitted.
    """
    if isinstance(content, str):
        raw = content
    else:
        raw = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256(raw)


def compute_chain_hash(record_dict: dict) -> str:
    """
    Compute chain.hash per ECP-SPEC §5.3:
    sha256 of canonical JSON of the record, with chain.hash and sig zeroed.
    Both chain.hash and sig are excluded from the hash computation because:
    - chain.hash is the output (circular dependency)
    - sig is computed AFTER chain.hash (depends on chain.hash)
    Returns "sha256:{hex}".
    """
    # Deep copy to avoid mutation
    import copy
    r = copy.deepcopy(record_dict)
    r.setdefault("chain", {})["hash"] = ""
    r["sig"] = ""
    # Canonical JSON: sorted keys, no spaces
    canonical = json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256(canonical)


# ─── Record Creation ──────────────────────────────────────────────────────────

def create_record(
    agent_did: str = "",
    step_type: str = "llm_call",
    in_content=None,
    out_content=None,
    identity: Optional[dict] = None,
    prev_record: Optional["ECPRecord"] = None,
    model: Optional[str] = None,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    latency_ms: int = 0,
    flags: Optional[list] = None,
    parent_agent: Optional[str] = None,
    # ── Aliases for DX consistency ──
    agent_id: Optional[str] = None,
    agent: Optional[str] = None,
    action: Optional[str] = None,
    input_data: Optional[dict] = None,
    output_data=None,
    reasoning: Optional[dict] = None,
    execution: Optional[list] = None,
    duration_ms: Optional[int] = None,
    ecp_dir: Optional[str] = None,  # accepted but unused (config via ECP_DIR env)
    parent_hash: Optional[str] = None,
    confidence: Optional[dict] = None,
) -> ECPRecord:
    """
    Create a new ECP record, correctly chained to prev_record.
    Follows ECP-SPEC.md v0.1 field conventions.

    Accepts multiple naming conventions for DX convenience:
      - agent_did / agent_id / agent  → agent DID string
      - step_type / action            → step type label
      - in_content / input_data       → input payload (hashed)
      - out_content / output_data     → output payload (hashed)
      - latency_ms / duration_ms      → step latency
    """
    # ── Resolve aliases ──
    agent_did = agent_did or agent_id or agent or ""
    step_type = action or step_type
    in_content = in_content if in_content is not None else (
        input_data if input_data is not None else ""
    )
    out_content = out_content if out_content is not None else (
        output_data if output_data is not None else ""
    )
    if duration_ms is not None and latency_ms == 0:
        latency_ms = duration_ms

    # If no identity provided, try to get/create one
    if identity is None:
        from .identity import get_or_create_identity
        identity = get_or_create_identity()

    record_id = f"rec_{uuid.uuid4().hex[:16]}"
    ts = int(time.time() * 1000)

    in_hash = hash_content(in_content)
    out_hash = hash_content(out_content)

    # chain.prev: "genesis" for first record (spec §6.1)
    prev_id = prev_record.id if prev_record else "genesis"

    step = ECPStep(
        type=step_type,
        in_hash=in_hash,
        out_hash=out_hash,
        latency_ms=latency_ms,
        flags=flags or [],
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        parent_agent=parent_agent,
    )

    # Build partial record dict for chain hash computation
    partial = {
        "ecp": "0.1",
        "id": record_id,
        "agent": agent_did,
        "ts": ts,
        "step": {
            "type": step.type,
            "in_hash": step.in_hash,
            "out_hash": step.out_hash,
            "latency_ms": step.latency_ms,
            "flags": step.flags,
            **({"model": step.model} if step.model else {}),
            **({"tokens_in": step.tokens_in} if step.tokens_in is not None else {}),
            **({"tokens_out": step.tokens_out} if step.tokens_out is not None else {}),
        },
        "chain": {"prev": prev_id, "hash": ""},
        "sig": "",
    }

    chain_hash = compute_chain_hash(partial)

    from .identity import sign
    sig = sign(identity, chain_hash)

    chain = ECPChain(prev=prev_id, hash=chain_hash)
    anchor = ECPAnchor()

    return ECPRecord(
        id=record_id,
        agent=agent_did,
        ts=ts,
        step=step,
        chain=chain,
        sig=sig,
        anchor=anchor,
    )


# ─── Serialization ────────────────────────────────────────────────────────────

def record_to_dict(record: ECPRecord) -> dict[str, Any]:
    """Serialize ECPRecord to dict matching ECP-SPEC canonical format."""
    step = record.step
    chain = record.chain
    anchor = record.anchor

    step_dict: dict[str, Any] = {
        "type": step.type,
        "in_hash": step.in_hash,
        "out_hash": step.out_hash,
        "latency_ms": step.latency_ms,
        "flags": step.flags,
    }

    # Optional step fields (only include if set)
    if step.model:
        step_dict["model"] = step.model
    if step.tokens_in is not None:
        step_dict["tokens_in"] = step.tokens_in
    if step.tokens_out is not None:
        step_dict["tokens_out"] = step.tokens_out
    if step.cost_usd is not None:
        step_dict["cost_usd"] = step.cost_usd
    if step.parent_agent:
        step_dict["parent_agent"] = step.parent_agent

    d: dict[str, Any] = {
        "ecp": "0.1",
        "id": record.id,
        "agent": record.agent,
        "ts": record.ts,
        "step": step_dict,
        "chain": {
            "prev": chain.prev,
            "hash": chain.hash,
        },
        "sig": record.sig,
    }

    # Anchor (filled async after on-chain batch)
    if anchor.batch_id or anchor.tx_hash:
        anchor_dict: dict[str, Any] = {}
        if anchor.batch_id:
            anchor_dict["batch_id"] = anchor.batch_id
        if anchor.tx_hash:
            anchor_dict["tx_hash"] = anchor.tx_hash
        if anchor.ts:
            anchor_dict["ts"] = anchor.ts
        d["anchor"] = anchor_dict

    return d


# ─── Minimal v1.0 Records ─────────────────────────────────────────────────────

def create_minimal_record(
    agent: str = "",
    action: str = "llm_call",
    in_content=None,
    out_content=None,
    meta: Optional[dict] = None,
    # ── Aliases for DX consistency ──
    agent_id: Optional[str] = None,
    agent_did: Optional[str] = None,
    input_text: Optional[str] = None,
    output_text: Optional[str] = None,
    step_type: Optional[str] = None,
    ecp_dir: Optional[str] = None,  # accepted but unused
) -> dict:
    """
    Create a minimal ECP v1.0 record.

    No chain, no signature, no DID required.
    This is the simplest valid ECP record — 6 required fields.
    Anyone in any language can produce this format.

    Args:
        agent: Any string identifier (e.g. "my-agent", not necessarily a DID)
        action: Record type — "llm_call", "tool_call", "message", "a2a_call"
        in_content: Input content (will be SHA-256 hashed; content stays local)
        out_content: Output content (will be SHA-256 hashed; content stays local)
        meta: Optional metadata dict with keys like:
              model, tokens_in, tokens_out, latency_ms, flags, cost_usd

    Returns:
        dict: A valid ECP v1.0 record ready for storage.
    """
    # ── Resolve aliases ──
    agent = agent or agent_id or agent_did or ""
    action = step_type or action
    in_content = in_content if in_content is not None else (input_text if input_text is not None else "")
    out_content = out_content if out_content is not None else (output_text if output_text is not None else "")

    record = {
        "ecp": "1.0",
        "id": f"rec_{uuid.uuid4().hex[:16]}",
        "ts": int(time.time() * 1000),
        "agent": agent,
        "action": action,
        "in_hash": hash_content(in_content),
        "out_hash": hash_content(out_content),
    }
    if meta:
        # Only include non-None values
        record["meta"] = {k: v for k, v in meta.items() if v is not None}
    return record
