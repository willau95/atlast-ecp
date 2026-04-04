"""
ECP Storage — local .ecp/ file management.
Content NEVER leaves the device. Only hashes are transmitted.
"""

import gzip
import json
import threading
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
            # Only include system_prompt if present (first time or changed)
            if extra.get("system_prompt") is not None:
                vault_data["system_prompt"] = extra["system_prompt"]
            if extra.get("full_request_hash"):
                vault_data["full_request_hash"] = extra["full_request_hash"]
            if extra.get("full_response_hash"):
                vault_data["full_response_hash"] = extra["full_response_hash"]
            if extra.get("context_messages_count"):
                vault_data["context_messages_count"] = extra["context_messages_count"]
            if extra.get("session_id"):
                vault_data["session_id"] = extra["session_id"]

        indent = 2 if mode == "full" else None
        content_json = json.dumps(vault_data, ensure_ascii=False, indent=indent)
        vault_file = VAULT_DIR / f"{record_id}.json"
        vault_file.write_text(content_json, encoding="utf-8")

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
