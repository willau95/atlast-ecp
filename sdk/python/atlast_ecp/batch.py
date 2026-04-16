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
from pathlib import Path
from typing import Optional

from .storage import load_records, enqueue_for_upload, get_upload_queue, clear_upload_queue
from .identity import get_or_create_identity, sign as sign_data

def _batch_ecp_dir() -> Path:
    """Resolve ECP_DIR at call time (respects ATLAST_ECP_DIR env)."""
    import os
    return Path(os.environ.get("ATLAST_ECP_DIR", os.environ.get("ECP_DIR", os.path.expanduser("~/.ecp"))))

ECP_DIR = _batch_ecp_dir()
BATCH_STATE_FILE = ECP_DIR / "batch_state.json"
# Production backend — Railway deployment
# Server URL configured via ATLAST_API_URL env or ~/.atlast/config.json
# Fallback: direct Railway URL (always works)
from .config import get_api_url as _get_api_url, get_api_key as _get_config_api_key, save_config

# Backward-compatible alias (used by tests and external code)
ATLAST_API = _get_api_url()

_batch_timer: Optional[threading.Timer] = None
_batch_lock = threading.Lock()

# ─── Batch Policy ─────────────────────────────────────────────────────────────
# Two triggers (whichever comes first):
#   1. Record count >= BATCH_THRESHOLD → immediate batch
#   2. Days since last batch >= BATCH_MAX_DAYS → batch regardless of count
# This avoids wasteful per-hour batching while ensuring data gets anchored.
import os as _os
MIN_BATCH_INTERVAL_S = int(_os.environ.get("ATLAST_BATCH_INTERVAL", "60"))
MAX_RECORDS_PER_BATCH = int(_os.environ.get("ATLAST_MAX_BATCH_SIZE", "1000"))
BATCH_THRESHOLD = int(_os.environ.get("ATLAST_BATCH_THRESHOLD", "1000"))
BATCH_MAX_DAYS = int(_os.environ.get("ATLAST_BATCH_MAX_DAYS", "7"))


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
    Returns (records, record_hashes) — sorted by timestamp ascending.
    Only includes records that have a valid chain hash (required for Merkle tree).
    """
    records = load_records(limit=10000)

    # Filter to records with valid chain hashes (required for Merkle leaves)
    records = [r for r in records if r.get("chain", {}).get("hash")]

    if since_ts:
        records = [
            r for r in records
            if isinstance(r.get("ts", 0), (int, float)) and r.get("ts", 0) > since_ts
        ]

    # Sort by timestamp ascending so batch cursor advances correctly
    records.sort(key=lambda r: r.get("ts", 0) if isinstance(r.get("ts", 0), (int, float)) else 0)

    # Extract chain hashes as Merkle leaves
    hashes = [r.get("chain", {}).get("hash", "") for r in records]

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
        flags = r.get("step", {}).get("flags") or r.get("meta", {}).get("flags", [])
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
        flags = r.get("step", {}).get("flags") or r.get("meta", {}).get("flags", [])
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
        did = identity["did"]
        pub_key = identity.get("crypto_pub_key") or identity.get("pub_key", "")

        # Generate ownership signature for re-registration
        import time as _reg_time
        ownership_ts = str(int(_reg_time.time()))
        ownership_sig = None
        try:
            sig_result = sign_data(identity, f"register:{did}:{ownership_ts}")
            if sig_result and sig_result.startswith("ed25519:"):
                ownership_sig = sig_result[len("ed25519:"):]
        except Exception:
            pass

        body: dict = {
            "did": did,
            "public_key": pub_key,
            "ecp_version": "0.1",
        }
        if ownership_sig:
            body["ownership_sig"] = ownership_sig
            body["ownership_ts"] = ownership_ts

        payload = json.dumps(body).encode("utf-8")

        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    f"{_get_api_url()}/agents/register",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    result = json.loads(resp.read())
                    state["agent_registered"] = True
                    state["agent_api_key"] = result.get("agent_api_key", "")
                    state["claim_url"] = result.get("claim_url", "")
                    state["verification_tweet"] = result.get("verification_tweet", "")
                    _save_batch_state(state)
                    if result.get("agent_api_key"):
                        save_config({
                            "agent_did": did,
                            "agent_api_key": result["agent_api_key"],
                            "endpoint": _get_api_url(),
                        })
                    return True
            except urllib.error.HTTPError as e:
                if e.code == 409:
                    # Already registered — success
                    state["agent_registered"] = True
                    _save_batch_state(state)
                    return True
                if e.code == 403 and ownership_sig:
                    # Re-registration failed — ownership sig might be wrong
                    break
                if 400 <= e.code < 500:
                    break  # Permanent client error — don't retry
            except (urllib.error.URLError, TimeoutError, OSError):
                pass

            if attempt < 2:
                time.sleep(2 ** attempt)

    except Exception:
        pass

    # All retries failed — keep False so next batch run retries registration
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
    chain_integrity: Optional[float] = None,
    max_retries: int = 3,
) -> Optional[str]:
    """
    Upload Merkle Root to ATLAST API for EAS anchoring.
    Returns attestation_uid on success, None on failure (will be queued).

    Retries with exponential backoff: 1s → 2s → 4s (max_retries=3).
    Only retries on transient errors (5xx, timeout, connection error).
    Permanent errors (4xx) fail immediately.

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
    if chain_integrity is not None:
        body["chain_integrity"] = chain_integrity

    payload = json.dumps(body).encode("utf-8")

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if agent_api_key:
        headers["X-Agent-Key"] = agent_api_key

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                f"{_get_api_url()}/batches",
                data=payload,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                return result.get("attestation_uid") or result.get("batch_id")

        except urllib.error.HTTPError as e:
            # 4xx = permanent error (bad request, auth failure) — don't retry
            if 400 <= e.code < 500:
                return None
            # 5xx = transient — retry with backoff
        except (urllib.error.URLError, TimeoutError, OSError):
            # Connection refused, DNS failure, timeout — retry
            pass
        except Exception:
            return None  # Unknown error — Fail-Open, don't retry

        # Exponential backoff: 1s, 2s, 4s
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)

    return None  # All retries exhausted — Fail-Open: queued for retry


# ─── Main Batch Process ───────────────────────────────────────────────────────

def run_batch(flush: bool = False):
    """
    Main batch processing function. Called periodically by scheduler.
    Collects records → builds Merkle tree → signs → uploads.
    Queues on failure for next run. NEVER raises.

    Batch policy (unless flush=True):
      - Only batch when: record_count >= BATCH_THRESHOLD (1000) OR
        days since last batch >= BATCH_MAX_DAYS (7)
      - This prevents wasteful micro-batches while ensuring data gets anchored.
    """
    with _batch_lock:
        try:
            # Load state
            state = _load_batch_state()
            since_ts = state.get("last_batch_ts")

            # Anti-abuse throttle (C6): enforce minimum batch interval
            if not flush and since_ts:
                elapsed_s = (time.time() * 1000 - since_ts) / 1000
                if elapsed_s < MIN_BATCH_INTERVAL_S:
                    return {"status": "throttled", "retry_after_s": MIN_BATCH_INTERVAL_S - elapsed_s}

            # Collect records
            records, hashes = collect_batch(since_ts=since_ts)
            if not hashes:
                return {"status": "empty", "record_count": 0}  # Nothing to batch

            # Batch policy: only proceed if threshold met or max days elapsed
            if not flush:
                days_since_last = 0
                if since_ts:
                    days_since_last = (time.time() * 1000 - since_ts) / 1000 / 86400
                else:
                    days_since_last = BATCH_MAX_DAYS  # First batch ever — allow it

                record_count = len(hashes)
                threshold_met = record_count >= BATCH_THRESHOLD
                time_met = days_since_last >= BATCH_MAX_DAYS

                if not threshold_met and not time_met:
                    return {
                        "status": "waiting",
                        "record_count": record_count,
                        "threshold": BATCH_THRESHOLD,
                        "days_since_last": round(days_since_last, 1),
                        "max_days": BATCH_MAX_DAYS,
                        "reason": f"{record_count}/{BATCH_THRESHOLD} records, {days_since_last:.1f}/{BATCH_MAX_DAYS} days",
                    }

            # Anti-abuse throttle (C6): cap records per batch
            if len(hashes) > MAX_RECORDS_PER_BATCH:
                records = records[:MAX_RECORDS_PER_BATCH]
                hashes = hashes[:MAX_RECORDS_PER_BATCH]

            # Build Merkle tree (sha256: prefixed root)
            merkle_root, _ = build_merkle_tree(hashes)

            # Compute stats
            latencies = [
                r.get("step", {}).get("latency_ms") or r.get("meta", {}).get("latency_ms", 0)
                for r in records
                if r.get("step", {}).get("latency_ms") or r.get("meta", {}).get("latency_ms")
            ]
            avg_latency = int(sum(latencies) / len(latencies)) if latencies else 0
            batch_ts = int(time.time() * 1000)  # Unix ms

            # Compute the max record timestamp for cursor advancement
            # This ensures we only skip records that were actually included in this batch,
            # not future records that exceed MAX_RECORDS_PER_BATCH.
            record_timestamps = [
                r.get("ts", 0) for r in records
                if isinstance(r.get("ts", 0), (int, float))
            ]
            max_record_ts = max(record_timestamps) if record_timestamps else batch_ts

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

            # Compute chain integrity signal
            from .signals import compute_trust_signals
            trust_signals = compute_trust_signals(records)
            chain_integrity = trust_signals.get("chain_integrity", 1.0)

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
                chain_integrity=chain_integrity,
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
                    "last_batch_ts": max_record_ts,
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
    """Start batch scheduler (background daemon thread).

    Checks every hour whether batch policy is met:
      - >= 1000 records since last batch → upload
      - >= 7 days since last batch → upload
    Otherwise just logs "waiting" and checks again next hour.
    """
    global _batch_timer
    import logging
    _logger = logging.getLogger(__name__)

    def _scheduled_run():
        global _batch_timer
        result = run_batch()
        status = result.get("status", "unknown") if isinstance(result, dict) else "unknown"
        if status == "waiting":
            _logger.debug("Batch check: %s", result.get("reason", ""))
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
    """Atomic write: write to temp file then rename (prevents corruption on crash)."""
    ECP_DIR.mkdir(parents=True, exist_ok=True)
    import tempfile
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(ECP_DIR), suffix=".tmp")
    try:
        with _os.fdopen(tmp_fd, "w") as f:
            json.dump(state, f, indent=2)
        _os.replace(tmp_path, str(BATCH_STATE_FILE))  # Atomic on POSIX
    except Exception:
        try:
            _os.unlink(tmp_path)
        except OSError:
            pass
        raise
