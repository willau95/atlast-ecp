"""
ECP Batch Processor — Merkle Root computation and upload.
Runs every hour. Cost: ~$3/month on Base regardless of record count.
Fail-Open: batch failure NEVER affects LLM calls.

Upload flow:
  1. Collect records since last batch
  2. Build Merkle tree (sha256: prefixed — matches backend crypto.py exactly)
  3. Sign merkle_root with agent's ed25519 private key
  4. Auto-register agent if first upload (fire-and-forget, non-blocking)
  5. POST to ATLAST_API /v1/batches with all required fields
  6. Queue on failure for hourly retry
"""

import hashlib
import json
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .storage import load_records, count_records, enqueue_for_upload, get_upload_queue, clear_upload_queue
from .identity import get_or_create_identity, sign as sign_data

ECP_DIR = Path(".ecp")
BATCH_STATE_FILE = ECP_DIR / "batch_state.json"
# Production backend — Railway deployment
# Server URL configured via ATLAST_API_URL env or ~/.atlast/config.json
# Fallback: direct Railway URL (always works)
from .config import get_api_url as _get_api_url, get_api_key as _get_config_api_key, save_config

# Backward-compatible alias (used by tests and external code)
ATLAST_API = _get_api_url()

_batch_timer: Optional[threading.Timer] = None
_batch_lock = threading.Lock()


# ─── Merkle Tree ──────────────────────────────────────────────────────────────

def sha256(data: str) -> str:
    """SHA-256 with sha256: prefix — matches ECP-SPEC format and backend crypto.py."""
    return "sha256:" + hashlib.sha256(data.encode()).hexdigest()


def build_merkle_tree(hashes: list[str]) -> tuple[str, list[list[str]]]:
    """
    Build a Merkle Tree from a list of hashes (sha256: prefixed).
    Returns (merkle_root, tree_layers) — root always has sha256: prefix.
    Algorithm matches backend crypto.py exactly (consistent sha256: prefix throughout).
    """
    if not hashes:
        return sha256("empty"), [[]]

    if len(hashes) == 1:
        return hashes[0], [hashes]

    layers = [list(hashes)]
    current = list(hashes)

    while len(current) > 1:
        # Pad odd-length layer by duplicating last element
        if len(current) % 2 == 1:
            current = current + [current[-1]]
        next_layer = []
        for i in range(0, len(current), 2):
            # Concatenate two sha256: strings, hash → new sha256: string
            combined = sha256(current[i] + current[i + 1])
            next_layer.append(combined)
        layers.append(next_layer)
        current = next_layer

    return current[0], layers


def get_merkle_proof(hashes: list[str], index: int) -> list[dict]:
    """
    Get Merkle proof path for a specific record (by index).
    Returns list of {hash, position} for verification.
    """
    if not hashes or index >= len(hashes):
        return []

    proof = []
    current = list(hashes)
    idx = index

    while len(current) > 1:
        if len(current) % 2 == 1:
            current = current + [current[-1]]

        sibling_idx = idx ^ 1  # XOR to get sibling
        position = "right" if idx % 2 == 0 else "left"
        proof.append({"hash": current[sibling_idx], "position": position})

        # Build next layer (sha256: prefix consistent)
        current = [sha256(current[i] + current[i + 1]) for i in range(0, len(current), 2)]
        idx //= 2

    return proof


# ─── Batch Collection ─────────────────────────────────────────────────────────

def collect_batch(since_ts: Optional[int] = None) -> tuple[list[dict], list[str]]:
    """
    Collect all ECP records since last batch.
    Returns (records, record_hashes).
    """
    records = load_records(limit=10000)

    if since_ts:
        records = [r for r in records if r.get("ts", 0) > since_ts]

    # Use each record's chain hash as the Merkle leaf
    hashes = [
        r.get("chain", {}).get("hash", "")
        for r in records
        if r.get("chain", {}).get("hash")
    ]

    return records, hashes


def _build_record_hashes_payload(records: list[dict]) -> list[dict]:
    """
    Build the record_hashes list for the batch upload payload.
    Each entry: {id, hash, flags, in_hash?, out_hash?} — matches backend RecordHashEntry model.
    in_hash/out_hash are SHA-256 hashes of input/output data (optional, format: sha256:{hex}).
    """
    entries = []
    for r in records:
        record_id = r.get("id", "")
        chain_hash = r.get("chain", {}).get("hash", "")
        flags = r.get("step", {}).get("flags", [])
        # Only include records with valid ids and hashes
        if record_id.startswith("rec_") and chain_hash.startswith("sha256:"):
            entry = {"id": record_id, "hash": chain_hash, "flags": flags}
            # Include in_hash/out_hash if present (ECP v1.0 flat format)
            in_hash = r.get("in_hash") or r.get("step", {}).get("in_hash")
            out_hash = r.get("out_hash") or r.get("step", {}).get("out_hash")
            if in_hash and in_hash.startswith("sha256:"):
                entry["in_hash"] = in_hash
            if out_hash and out_hash.startswith("sha256:"):
                entry["out_hash"] = out_hash
            entries.append(entry)
    return entries


def _aggregate_flag_counts(records: list[dict]) -> dict:
    """
    Aggregate behavioral flag counts across all records in the batch.
    Matches backend BatchUploadRequest.flag_counts field.
    """
    counts: dict[str, int] = {}
    for r in records:
        flags = r.get("step", {}).get("flags", [])
        for flag in flags:
            counts[flag] = counts.get(flag, 0) + 1
    return counts


# ─── Agent Auto-Registration ──────────────────────────────────────────────────

def _ensure_agent_registered(identity: dict) -> bool:
    """
    Auto-register agent with ATLAST API on first batch upload.
    Non-blocking: failure is logged but never raises.
    Returns True if registered (or already registered), False if failed.
    """
    state = _load_batch_state()
    if state.get("agent_registered"):
        return True

    try:

        payload = json.dumps({
            "did": identity["did"],
            "public_key": identity["pub_key"],
            "ecp_version": "0.1",
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{_get_api_url()}/agents/register",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            # Store claim_url for user to verify ownership
            state["agent_registered"] = True
            state["agent_api_key"] = result.get("agent_api_key", "")
            state["claim_url"] = result.get("claim_url", "")
            state["verification_tweet"] = result.get("verification_tweet", "")
            _save_batch_state(state)
            # Also persist to local config for CLI access
            if result.get("agent_api_key"):
                save_config({
                    "agent_did": identity["did"],
                    "agent_api_key": result["agent_api_key"],
                    "endpoint": _get_api_url(),
                })
            return True

    except Exception:
        # 409 = already registered — that's OK
        # Other failures = will retry next batch
        state["agent_registered"] = True  # Optimistic: don't block indefinitely
        _save_batch_state(state)
        return False


# ─── Upload to ATLAST API ──────────────────────────────────────────────────────

def upload_merkle_root(
    merkle_root: str,
    agent_did: str,
    record_count: int,
    avg_latency_ms: int,
    batch_ts: int,
    sig: str,
    ecp_version: str = "0.1",
    record_hashes: Optional[list[dict]] = None,
    flag_counts: Optional[dict] = None,
    agent_api_key: Optional[str] = None,
) -> Optional[str]:
    """
    Upload Merkle Root to ATLAST API for EAS anchoring.
    Returns attestation_uid on success, None on failure (will be queued).

    Payload matches backend BatchUploadRequest exactly:
    - merkle_root: sha256:{hex}
    - agent_did: did:ecp:{32 hex}
    - record_count: int
    - avg_latency_ms: int
    - batch_ts: int (Unix ms)        ← NOT ISO string
    - sig: ed25519:{hex} or "unverified"
    - ecp_version: "0.1"
    - record_hashes: [{id, hash, flags}] (optional)
    - flag_counts: {flag: count} (optional)
    """
    try:

        body: dict = {
            "merkle_root": merkle_root,
            "agent_did": agent_did,
            "record_count": record_count,
            "avg_latency_ms": avg_latency_ms,
            "batch_ts": batch_ts,        # int Unix ms — backend REQUIRED field
            "sig": sig,                   # ed25519:{hex} or "unverified" — backend REQUIRED
            "ecp_version": ecp_version,
        }
        if record_hashes:
            body["record_hashes"] = record_hashes
        if flag_counts:
            body["flag_counts"] = flag_counts

        payload = json.dumps(body).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if agent_api_key:
            headers["X-Agent-Key"] = agent_api_key

        req = urllib.request.Request(
            f"{_get_api_url()}/batches",
            data=payload,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return result.get("attestation_uid") or result.get("batch_id")

    except Exception:
        return None  # Fail-Open: queued for retry


# ─── Main Batch Process ───────────────────────────────────────────────────────

def run_batch(flush: bool = False):
    """
    Main batch processing function. Called hourly by scheduler.
    Collects records → builds Merkle tree → signs → uploads.
    Queues on failure for next run. NEVER raises.
    """
    with _batch_lock:
        try:
            # Load state
            state = _load_batch_state()
            since_ts = state.get("last_batch_ts")

            # Collect records
            records, hashes = collect_batch(since_ts=since_ts)
            if not hashes:
                return {"status": "empty", "record_count": 0}  # Nothing to batch

            # Build Merkle tree (sha256: prefixed root)
            merkle_root, _ = build_merkle_tree(hashes)

            # Compute stats
            latencies = [
                r.get("step", {}).get("latency_ms", 0)
                for r in records
                if r.get("step", {}).get("latency_ms")
            ]
            avg_latency = int(sum(latencies) / len(latencies)) if latencies else 0
            batch_ts = int(time.time() * 1000)  # Unix ms

            # Get identity and sign
            identity = get_or_create_identity()
            agent_did = identity["did"]
            sig = sign_data(identity, merkle_root)

            # Auto-register agent if first upload (non-blocking)
            _ensure_agent_registered(identity)

            # Retry any previously failed uploads first
            _retry_queued()

            # Collect optional enrichment data
            record_hashes_payload = _build_record_hashes_payload(records)
            flag_counts = _aggregate_flag_counts(records)

            # Upload to ATLAST API
            agent_api_key = state.get("agent_api_key") or _get_config_api_key()
            attestation_uid = upload_merkle_root(
                merkle_root=merkle_root,
                agent_did=agent_did,
                record_count=len(hashes),
                avg_latency_ms=avg_latency,
                batch_ts=batch_ts,
                sig=sig,
                record_hashes=record_hashes_payload or None,
                flag_counts=flag_counts or None,
                agent_api_key=agent_api_key,
            )

            batch_result = {
                "status": "ok",
                "merkle_root": merkle_root,
                "agent_did": agent_did,
                "record_count": len(hashes),
                "avg_latency_ms": avg_latency,
                "batch_ts": batch_ts,
                "sig": sig,
            }

            if attestation_uid:
                # Success — update state
                batch_result["attestation_uid"] = attestation_uid
                batch_result["uploaded"] = True
                _save_batch_state({
                    **state,
                    "last_batch_ts": batch_ts,
                    "last_merkle_root": merkle_root,
                    "last_attestation_uid": attestation_uid,
                    "total_batches": state.get("total_batches", 0) + 1,
                })
            else:
                # Failure — queue for next run (include all required fields)
                batch_result["uploaded"] = False
                batch_result["queued"] = True
                enqueue_for_upload({
                    "merkle_root": merkle_root,
                    "agent_did": agent_did,
                    "record_count": len(hashes),
                    "avg_latency_ms": avg_latency,
                    "batch_ts": batch_ts,         # preserve original timestamp
                    "sig": sig,                    # preserve original sig
                    "ecp_version": "0.1",
                    "record_hashes": record_hashes_payload or None,
                    "flag_counts": flag_counts or None,
                    "queued_at": int(time.time() * 1000),
                })

            return batch_result

        except Exception:
            return {"status": "error"}  # Fail-Open: batch failure NEVER crashes the agent


def _retry_queued():
    """Retry previously failed uploads (preserving original batch_ts and sig)."""
    queue = get_upload_queue()
    if not queue:
        return

    success_count = 0
    for batch in queue:
        uid = upload_merkle_root(
            merkle_root=batch["merkle_root"],
            agent_did=batch["agent_did"],
            record_count=batch["record_count"],
            avg_latency_ms=batch.get("avg_latency_ms", 0),
            batch_ts=batch["batch_ts"],    # original timestamp (idempotency)
            sig=batch["sig"],              # original sig
            ecp_version=batch.get("ecp_version", "0.1"),
            record_hashes=batch.get("record_hashes"),
            flag_counts=batch.get("flag_counts"),
        )
        if uid:
            success_count += 1

    if success_count == len(queue):
        clear_upload_queue()


# ─── Scheduler ────────────────────────────────────────────────────────────────

def start_scheduler(interval_seconds: int = 3600):
    """Start hourly batch scheduler (background daemon thread)."""
    def _scheduled_run():
        global _batch_timer
        run_batch()
        _batch_timer = threading.Timer(interval_seconds, _scheduled_run)
        _batch_timer.daemon = True
        _batch_timer.start()

    _batch_timer = threading.Timer(interval_seconds, _scheduled_run)
    _batch_timer.daemon = True
    _batch_timer.start()


def trigger_batch_upload(flush: bool = False):
    """Manually trigger a batch upload (e.g., on session end)."""
    threading.Thread(target=run_batch, kwargs={"flush": flush}, daemon=True).start()


# ─── State Management ─────────────────────────────────────────────────────────

def _load_batch_state() -> dict:
    if not BATCH_STATE_FILE.exists():
        return {}
    try:
        return json.loads(BATCH_STATE_FILE.read_text())
    except Exception:
        return {}


def _save_batch_state(state: dict):
    ECP_DIR.mkdir(exist_ok=True)
    BATCH_STATE_FILE.write_text(json.dumps(state, indent=2))
