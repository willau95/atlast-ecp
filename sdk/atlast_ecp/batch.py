"""
ECP Batch Processor — Merkle Root computation and upload.
Runs every hour. Cost: ~$3/month on Base regardless of record count.
Fail-Open: batch failure NEVER affects LLM calls.
"""

import hashlib
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .storage import load_records, count_records, enqueue_for_upload, get_upload_queue, clear_upload_queue

ECP_DIR = Path(".ecp")
BATCH_STATE_FILE = ECP_DIR / "batch_state.json"
ATLAST_API = "https://api.llachat.com/v1"

_batch_timer: Optional[threading.Timer] = None
_batch_lock = threading.Lock()


# ─── Merkle Tree ──────────────────────────────────────────────────────────────

def sha256(data: str) -> str:
    """SHA-256 with sha256: prefix — matches ECP-SPEC format."""
    return "sha256:" + hashlib.sha256(data.encode()).hexdigest()


def build_merkle_tree(hashes: list[str]) -> tuple[str, list[list[str]]]:
    """
    Build a Merkle Tree from a list of hashes (sha256: prefixed).
    Returns (merkle_root, tree_layers) — root has sha256: prefix.
    Algorithm matches backend crypto.py exactly.
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
            # Concatenate two sha256: prefixed strings, hash them → new sha256: string
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

        # Build next layer
        current = [sha256(current[i] + current[i + 1]) for i in range(0, len(current), 2)]
        idx //= 2

    return proof


# ─── Batch Collection ─────────────────────────────────────────────────────────

def collect_batch(since_ts: Optional[int] = None) -> tuple[list[dict], list[str]]:
    """
    Collect all ECP records since last batch.
    Returns (records, record_hashes).
    """
    # Load records from storage (all if no since_ts)
    records = load_records(limit=10000)

    if since_ts:
        records = [r for r in records if r.get("ts", 0) > since_ts]

    # Use each record's chain hash as the Merkle leaf
    hashes = [r.get("chain", {}).get("hash", "") for r in records if r.get("chain", {}).get("hash")]

    return records, hashes


# ─── Upload to ATLAST API ──────────────────────────────────────────────────────

def upload_merkle_root(
    merkle_root: str,
    agent_did: str,
    record_count: int,
    avg_latency_ms: int,
    ecp_version: str = "0.1",
) -> Optional[str]:
    """
    Upload Merkle Root to ATLAST API for EAS anchoring.
    Returns attestation_uid on success, None on failure.
    """
    try:
        import urllib.request
        import urllib.error

        payload = json.dumps({
            "merkle_root": merkle_root,
            "agent_did": agent_did,
            "record_count": record_count,
            "avg_latency_ms": avg_latency_ms,
            "batch_timestamp": datetime.now(timezone.utc).isoformat(),
            "ecp_version": ecp_version,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{ATLAST_API}/batch",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return result.get("attestation_uid")

    except Exception:
        return None  # Will be queued for retry


# ─── Main Batch Process ───────────────────────────────────────────────────────

def run_batch(flush: bool = False):
    """
    Main batch processing function.
    Collects records → builds Merkle tree → uploads to ATLAST API.
    Queues on failure for next run.
    """
    with _batch_lock:
        try:
            # Load state
            state = _load_batch_state()
            since_ts = state.get("last_batch_ts")

            # Collect records
            records, hashes = collect_batch(since_ts=since_ts)
            if not hashes:
                return  # Nothing to batch

            # Build Merkle tree
            merkle_root, _ = build_merkle_tree(hashes)

            # Compute stats
            latencies = [
                r.get("step", {}).get("latency_ms", 0)
                for r in records
                if r.get("step", {}).get("latency_ms")
            ]
            avg_latency = int(sum(latencies) / len(latencies)) if latencies else 0

            # Get agent DID
            from .identity import get_or_create_identity
            identity = get_or_create_identity()
            agent_did = identity["did"]

            # Try upload (also retry queued batches)
            _retry_queued()

            attestation_uid = upload_merkle_root(
                merkle_root=merkle_root,
                agent_did=agent_did,
                record_count=len(hashes),
                avg_latency_ms=avg_latency,
            )

            if attestation_uid:
                # Success — update state
                _save_batch_state({
                    "last_batch_ts": int(time.time() * 1000),
                    "last_merkle_root": merkle_root,
                    "last_attestation_uid": attestation_uid,
                    "total_batches": state.get("total_batches", 0) + 1,
                })
            else:
                # Failure — queue for next run
                enqueue_for_upload({
                    "merkle_root": merkle_root,
                    "agent_did": agent_did,
                    "record_count": len(hashes),
                    "avg_latency_ms": avg_latency,
                    "queued_at": int(time.time() * 1000),
                })

        except Exception:
            pass  # Fail-Open: batch failure NEVER crashes the agent


def _retry_queued():
    """Retry previously failed uploads."""
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
        )
        if uid:
            success_count += 1

    if success_count == len(queue):
        clear_upload_queue()


# ─── Scheduler ────────────────────────────────────────────────────────────────

def start_scheduler(interval_seconds: int = 3600):
    """Start hourly batch scheduler (background thread)."""
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
