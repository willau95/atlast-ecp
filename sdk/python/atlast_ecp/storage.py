"""
ECP Storage — local .ecp/ file management.
Content NEVER leaves the device. Only hashes are transmitted.
"""

import gzip
import json
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import os
ECP_DIR = Path(os.environ.get("ATLAST_ECP_DIR", os.environ.get("ECP_DIR", os.path.expanduser("~/.ecp"))))
RECORDS_DIR = ECP_DIR / "records"
LOCAL_DIR = ECP_DIR / "local"       # summaries, never uploaded
VAULT_DIR = ECP_DIR / "vault"       # raw content, never uploaded — for local audit
INDEX_FILE = ECP_DIR / "index.json" # record_id → file + line mapping
QUEUE_FILE = ECP_DIR / "upload_queue.jsonl"  # unuploaded batches

_lock = threading.Lock()


def init_storage():
    """Create .ecp/ directory structure if not exists."""
    ECP_DIR.mkdir(parents=True, exist_ok=True)
    RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_FILE.exists():
        INDEX_FILE.write_text(json.dumps({}))


@contextmanager
def _open_record_file(file_path: Path, mode: str = "r"):
    """Open a record file transparently — plain or gzip."""
    if file_path.suffix == ".gz":
        with gzip.open(file_path, mode + "t", encoding="utf-8") as fh:
            yield fh
    else:
        with open(file_path, mode, encoding="utf-8") as fh:
            yield fh


def _iter_record_files(date: Optional[str] = None):
    """Yield record file paths (both .jsonl and .jsonl.gz), newest first."""
    if date:
        candidates = [
            RECORDS_DIR / f"{date}.jsonl.gz",
            RECORDS_DIR / f"{date}.jsonl",
        ]
        return [f for f in candidates if f.exists()]
    all_files = list(RECORDS_DIR.glob("*.jsonl")) + list(RECORDS_DIR.glob("*.jsonl.gz"))
    return sorted(all_files, key=lambda f: f.name, reverse=True)


def save_record(record_dict: dict, local_summary: Optional[str] = None) -> str:
    """
    Save an ECP record to local storage.
    local_summary is saved separately in LOCAL_DIR — never uploaded.
    Respects ECP_STORAGE_COMPRESS env var for gzip compression.
    Returns the record_id.
    """
    init_storage()

    from .config import get_storage_compress
    compress = get_storage_compress()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if compress:
        record_file = RECORDS_DIR / f"{today}.jsonl.gz"
    else:
        record_file = RECORDS_DIR / f"{today}.jsonl"

    with _lock:
        # Append record to daily file (plain or gzip)
        with _open_record_file(record_file, "a") as f:
            f.write(json.dumps(record_dict, ensure_ascii=False) + "\n")

        # Update index
        index = _load_index()
        index[record_dict["id"]] = {
            "file": str(record_file),
            "date": today,
        }
        INDEX_FILE.write_text(json.dumps(index, indent=2))

    # Save local summary separately (never transmitted)
    if local_summary:
        summary_file = LOCAL_DIR / f"{record_dict['id']}.txt"
        summary_file.write_text(local_summary, encoding="utf-8")

    # Event-driven batch trigger: check if the 1000-record threshold crossed.
    # Throttled + fire-and-forget, so the writing process never blocks.
    try:
        from .batch import maybe_trigger_batch_on_write
        maybe_trigger_batch_on_write()
    except Exception:
        pass

    return record_dict["id"]


def load_records(
    limit: int = 10,
    date: Optional[str] = None,
    # ── Aliases for DX consistency ──
    agent_id: Optional[str] = None,
    ecp_dir: Optional[str] = None,
) -> list[dict]:
    """Load ECP records from local storage (newest first). Handles .jsonl and .jsonl.gz."""
    init_storage()

    files = _iter_record_files(date)

    records = []
    for f in files:
        if not f.exists():
            continue
        with _open_record_file(f) as fh:
            lines = fh.read().strip().splitlines()
        for line in reversed(lines):
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            if len(records) >= limit:
                break
        if len(records) >= limit:
            break

    # ── Filter by agent_id if provided ──
    if agent_id:
        records = [r for r in records if r.get("agent") == agent_id]

    return records[:limit]


def load_record_by_id(record_id: str) -> Optional[dict]:
    """Load a single record by ID. Handles .jsonl and .jsonl.gz transparently."""
    init_storage()
    index = _load_index()

    if record_id not in index:
        return None

    file_path = Path(index[record_id]["file"])
    if not file_path.exists():
        return None

    with _open_record_file(file_path) as fh:
        for line in fh:
            if line.strip():
                try:
                    r = json.loads(line)
                    if r.get("id") == record_id:
                        return r
                except json.JSONDecodeError:
                    continue
    return None


def load_local_summary(record_id: str) -> Optional[str]:
    """Load local-only summary for a record (never transmitted)."""
    summary_file = LOCAL_DIR / f"{record_id}.txt"
    return summary_file.read_text(encoding="utf-8") if summary_file.exists() else None


# ─── Content Vault ────────────────────────────────────────────────────────────
# Stores raw input/output content locally so users can pair hashes with content.
# NEVER transmitted. NEVER leaves the device. Only for local audit/inspect.

def upsert_record(record_dict: dict) -> str:
    """Write a record by id, replacing any prior version with the same id.

    Used by transcript_scanner so the same turn (deterministic id) can be
    written multiple times as more transcript entries arrive — each write
    supersedes the last. The daily JSONL file is rewritten with the prior
    version's line removed and the new one appended.

    Evidence-chain note: deterministic-id records form their own continuity
    — each update has a new chain_hash derived from the new content. The
    prior chain_hash is no longer referenced by future records since the
    index points to the latest line only. Readers who trust chain linking
    should rely on the *latest* record per id.
    """
    init_storage()
    rid = record_dict["id"]

    from .config import get_storage_compress
    compress = get_storage_compress()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    record_file = RECORDS_DIR / (f"{today}.jsonl.gz" if compress else f"{today}.jsonl")

    with _lock:
        # If a prior version of this id lives anywhere on disk, rewrite that
        # file with the old line removed. We then append the new line to
        # today's file so the index points at the freshest copy.
        index = _load_index()
        prior = index.get(rid)
        prior_file = Path(prior["file"]) if prior and prior.get("file") else None
        if prior_file and prior_file.exists():
            try:
                with _open_record_file(prior_file, "r") as rh:
                    lines = rh.read().splitlines()
                kept = []
                for line in lines:
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        kept.append(line)
                        continue
                    if obj.get("id") == rid:
                        continue  # drop the old version
                    kept.append(line)
                with _open_record_file(prior_file, "w") as wh:
                    for line in kept:
                        wh.write(line + "\n")
            except Exception:
                pass  # Fail-Open — at worst we end up with a duplicate we can dedupe later

        # Append the new version to today's file
        with _open_record_file(record_file, "a") as f:
            f.write(json.dumps(record_dict, ensure_ascii=False) + "\n")

        # Point the index at the new location
        index[rid] = {"file": str(record_file), "date": today}
        INDEX_FILE.write_text(json.dumps(index, indent=2))

        # Per-row upsert into the SQLite search index so dashboards see the
        # change immediately without a 3 s full rebuild. The record_dict plus
        # the freshly-saved vault give us everything we need; query.rebuild_index
        # reads the same fields from disk, we just skip the I/O pass.
        try:
            _upsert_search_row(record_dict)
        except Exception:
            pass  # Fail-Open — the next TTL-expiry rebuild will catch up

    # Event-driven batch trigger — same as save_record. A scanner/proxy write
    # that pushes the pending count over 1000 fires a batch in a daemon
    # thread before the writer's process exits.
    try:
        from .batch import maybe_trigger_batch_on_write
        maybe_trigger_batch_on_write()
    except Exception:
        pass

    return rid


def _upsert_search_row(record_dict: dict) -> None:
    """Insert-or-replace a single row in the SQLite search index.

    Mirrors the column layout in query.rebuild_index(). If the index DB
    doesn't exist yet, we leave it alone — the first rebuild will create
    it and pick this record up.
    """
    import sqlite3
    from datetime import timezone as _tz
    from .query import INDEX_DB
    if not INDEX_DB.exists():
        return
    rid = record_dict.get("id", "")
    if not rid:
        return

    step = record_dict.get("step", {}) or {}
    meta = record_dict.get("meta", {}) or {}
    chain = record_dict.get("chain", {}) or {}
    flags = step.get("flags") or meta.get("flags", []) or []
    if isinstance(flags, list):
        flags_str = json.dumps(flags)
    else:
        flags_str = str(flags)

    ts = record_dict.get("ts", 0) or 0
    date_str = datetime.fromtimestamp(ts / 1000, tz=_tz.utc).strftime("%Y-%m-%d") if ts else ""

    # Preview text from the freshly-saved vault (if present)
    vault_file = VAULT_DIR / f"{rid}.json"
    input_preview = ""
    output_preview = ""
    if vault_file.exists():
        try:
            vdata = json.loads(vault_file.read_text())
            input_preview = (vdata.get("input") or "")[:500]
            raw_output = vdata.get("output") or ""
            if raw_output.startswith('{"final_response"'):
                try:
                    parsed = json.loads(raw_output)
                    final_resp = parsed.get("final_response", "")
                    tool_calls = parsed.get("tool_calls_used", [])
                    steps = parsed.get("steps", 1)
                    meta_line = json.dumps({
                        "_aggregated": True,
                        "steps": steps,
                        "tool_calls": len(tool_calls),
                        "tool_names": [tc.get("name", "") for tc in tool_calls[:20]],
                    })
                    output_preview = meta_line + "\n" + (final_resp or "")[:4500]
                except (json.JSONDecodeError, TypeError):
                    output_preview = raw_output[:5000]
            else:
                output_preview = raw_output[:5000]
        except Exception:
            pass

    has_error = 1 if ("error" in (flags if isinstance(flags, list) else [])
                      or step.get("error")) else 0
    metadata = record_dict.get("metadata", {}) or {}
    is_infra = 1 if metadata.get("is_infra_error") else 0
    error_type = metadata.get("error_type", "") or ""

    confidence = step.get("confidence") or meta.get("confidence")
    if isinstance(confidence, dict):
        confidence = confidence.get("score")

    record_file_row = None
    try:
        idx = _load_index()
        if rid in idx:
            record_file_row = idx[rid].get("file", "")
    except Exception:
        pass

    row = (
        rid,
        record_dict.get("agent", ""),
        ts,
        date_str,
        step.get("type") or meta.get("type") or record_dict.get("action", ""),
        step.get("action") or meta.get("action") or record_dict.get("action", ""),
        step.get("model") or meta.get("model", "") or "",
        step.get("latency_ms") or meta.get("latency_ms", 0) or 0,
        confidence,
        step.get("session_id") or meta.get("session_id") or record_dict.get("session_id", ""),
        step.get("delegation_id") or meta.get("delegation_id") or record_dict.get("delegation_id", ""),
        step.get("delegation_depth") or meta.get("delegation_depth") or record_dict.get("delegation_depth"),
        chain.get("prev", "") or "",
        chain.get("hash", "") or "",
        flags_str,
        input_preview,
        output_preview,
        has_error,
        is_infra,
        error_type,
        meta.get("tokens_in") or 0,
        meta.get("tokens_out") or 0,
        int(time.time() * 1000),
        meta.get("thread_id") or record_dict.get("thread_id", ""),
    )

    conn = sqlite3.connect(str(INDEX_DB))
    try:
        conn.execute("""
            INSERT OR REPLACE INTO records
            (id, agent, ts, date, step_type, action, model, latency_ms,
             confidence, session_id, delegation_id, delegation_depth,
             chain_prev, chain_hash, flags, input_preview, output_preview,
             error, is_infra, error_type, tokens_in, tokens_out, indexed_at, thread_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, row)
        conn.commit()
    finally:
        conn.close()


def save_vault(record_id: str, input_content: str, output_content: str) -> None:
    """Save raw content to vault for local inspection. Never transmitted.

    Respects ECP_VAULT_MODE: full (default) | hash_only | compact.
    Also triggers encrypted backup if vault_backup_path is configured.
    """
    try:
        init_storage()
        from .config import get_vault_mode
        mode = get_vault_mode()

        if mode == "hash_only":
            return  # Skip vault save entirely

        indent = 2 if mode == "full" else None
        content_json = json.dumps({
            "record_id": record_id,
            "input": input_content,
            "output": output_content,
        }, ensure_ascii=False, indent=indent)
        vault_file = VAULT_DIR / f"{record_id}.json"
        vault_file.write_text(content_json, encoding="utf-8")
        try:
            import stat
            vault_file.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600 — vault contains PII
        except OSError:
            pass

        # Auto-backup if configured (Fail-Open)
        try:
            from .config import get_vault_backup_path
            backup_path = get_vault_backup_path()
            if backup_path:
                from .identity import get_or_create_identity
                identity = get_or_create_identity()
                priv_key = identity.get("priv_key")
                if priv_key:
                    from .vault_backup import backup_vault_entry
                    backup_vault_entry(record_id, content_json, backup_path, priv_key)
        except Exception:
            pass  # Fail-Open: backup failure never crashes agent
    except Exception:
        pass  # Fail-Open: vault save failure never crashes agent


def save_vault_v2(record_id: str, input_content: str, output_content: str,
                   extra: Optional[dict] = None) -> None:
    """
    Save vault with v2 structure (Proxy path).

    Respects ECP_VAULT_MODE: full (default) | hash_only | compact.

    Stores only NEW content per record. Audit metadata (full_request_hash,
    system_prompt, context_messages_count) enables complete reconstruction
    and verification of the original API call via chain traversal.

    Vault v2 file structure:
      {
        "record_id": "rec_xxx",
        "vault_version": 2,
        "input": "last user message (new content only)",
        "output": "full assistant response",
        "system_prompt": "..." or null,
        "full_request_hash": "sha256:...",
        "full_response_hash": "sha256:...",
        "context_messages_count": 8,
        "session_id": "sess_..."
      }
    """
    try:
        init_storage()
        from .config import get_vault_mode
        mode = get_vault_mode()

        if mode == "hash_only":
            return  # Skip vault save entirely

        vault_data = {
            "record_id": record_id,
            "input": input_content,
            "output": output_content,
        }

        if extra:
            vault_data["vault_version"] = extra.get("vault_version", 2)
            # Merge all remaining extra fields. Callers are trusted
            # (proxy, hooks, adapters) to pass only JSON-safe, non-sensitive data.
            # None values are treated as "omit" so callers can dedupe (e.g. system_prompt).
            for k, v in extra.items():
                if k in ("vault_version", "record_id", "input", "output"):
                    continue
                if v is None:
                    continue
                vault_data[k] = v

        indent = 2 if mode == "full" else None
        content_json = json.dumps(vault_data, ensure_ascii=False, indent=indent)
        vault_file = VAULT_DIR / f"{record_id}.json"
        vault_file.write_text(content_json, encoding="utf-8")
        try:
            import stat
            vault_file.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600 — vault contains PII
        except OSError:
            pass

        # Auto-backup if configured (Fail-Open) — same as save_vault
        try:
            from .config import get_vault_backup_path
            backup_path = get_vault_backup_path()
            if backup_path:
                from .identity import get_or_create_identity
                identity = get_or_create_identity()
                priv_key = identity.get("priv_key")
                if priv_key:
                    from .vault_backup import backup_vault_entry
                    backup_vault_entry(record_id, content_json, backup_path, priv_key)
        except Exception:
            pass  # Fail-Open
    except Exception:
        pass  # Fail-Open


def load_vault(record_id: str) -> Optional[dict]:
    """Load raw content from vault. Returns {input, output} or None.
    Checks global vault first, then per-agent vault dirs."""
    vault_file = VAULT_DIR / f"{record_id}.json"
    if not vault_file.exists():
        # Search per-agent vault directories
        agents_dir = ECP_DIR / "agents"
        if agents_dir.exists():
            for agent_vault in agents_dir.glob("*/vault"):
                candidate = agent_vault / f"{record_id}.json"
                if candidate.exists():
                    vault_file = candidate
                    break
            else:
                return None
        else:
            return None
    try:
        return json.loads(vault_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def cleanup_old_records(days: int = 90) -> dict:
    """
    Remove record files, vault files, and index entries older than `days` days.

    Returns a dict with counts: removed_files, removed_vault, removed_index.
    If days <= 0, does nothing (disabled).

    Respects ECP_STORAGE_TTL_DAYS env var when called as CLI entrypoint.
    """
    if days <= 0:
        return {"removed_files": 0, "removed_vault": 0, "removed_index": 0}

    init_storage()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_date = cutoff.strftime("%Y-%m-%d")

    removed_files = 0
    removed_vault = 0
    removed_index = 0

    with _lock:
        index = _load_index()

        # Find and remove old record files; collect their paths
        deleted_file_paths = set()
        for pattern in ("*.jsonl", "*.jsonl.gz"):
            for f in RECORDS_DIR.glob(pattern):
                name = f.name
                for ext in (".jsonl.gz", ".jsonl"):
                    if name.endswith(ext):
                        date_str = name[: -len(ext)]
                        break
                else:
                    continue
                if date_str < cutoff_date:
                    deleted_file_paths.add(str(f))
                    f.unlink()
                    removed_files += 1

        # Clean index: remove entries whose file was deleted or whose date is old
        new_index = {}
        for rid, meta in index.items():
            file_path = meta.get("file", "")
            date_str = meta.get("date", "")
            if file_path in deleted_file_paths or date_str < cutoff_date:
                removed_index += 1
                vault_file = VAULT_DIR / f"{rid}.json"
                if vault_file.exists():
                    vault_file.unlink()
                    removed_vault += 1
            else:
                new_index[rid] = meta

        INDEX_FILE.write_text(json.dumps(new_index, indent=2))

    return {
        "removed_files": removed_files,
        "removed_vault": removed_vault,
        "removed_index": removed_index,
    }


def enqueue_for_upload(batch: dict):
    """Queue a Merkle batch for upload (used if upload fails)."""
    init_storage()
    with _lock:
        with open(QUEUE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(batch, ensure_ascii=False) + "\n")


def get_upload_queue() -> list[dict]:
    """Get all pending upload batches."""
    if not QUEUE_FILE.exists():
        return []
    batches = []
    for line in QUEUE_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                batches.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return batches


def clear_upload_queue():
    """Clear the upload queue after successful upload."""
    if QUEUE_FILE.exists():
        QUEUE_FILE.write_text("")


def count_records(date: Optional[str] = None) -> int:
    """Count total ECP records (both .jsonl and .jsonl.gz)."""
    init_storage()
    total = 0
    patterns = [f"{date}.jsonl", f"{date}.jsonl.gz"] if date else ["*.jsonl", "*.jsonl.gz"]
    for pattern in patterns:
        for f in RECORDS_DIR.glob(pattern):
            with _open_record_file(f) as fh:
                total += sum(1 for line in fh if line.strip())
    return total


def _load_index() -> dict:
    if not INDEX_FILE.exists():
        return {}
    try:
        return json.loads(INDEX_FILE.read_text())
    except (json.JSONDecodeError, IOError):
        return {}


if __name__ == "__main__":
    """CLI entrypoint: python -m atlast_ecp.storage [--days N]"""
    import argparse
    from .config import get_storage_ttl_days

    parser = argparse.ArgumentParser(description="ECP Storage cleanup utility")
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Remove records older than N days (0=disabled). Defaults to ECP_STORAGE_TTL_DAYS.",
    )
    args = parser.parse_args()

    days = args.days if args.days is not None else get_storage_ttl_days()
    result = cleanup_old_records(days=days)
    print(
        f"Cleanup complete: {result['removed_files']} record files, "
        f"{result['removed_vault']} vault files, "
        f"{result['removed_index']} index entries removed."
    )
