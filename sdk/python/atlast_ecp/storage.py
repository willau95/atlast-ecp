"""
ECP Storage — local .ecp/ file management.
Content NEVER leaves the device. Only hashes are transmitted.
"""

import json
import threading
from datetime import datetime, timezone
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


def save_record(record_dict: dict, local_summary: Optional[str] = None) -> str:
    """
    Save an ECP record to local storage.
    local_summary is saved separately in LOCAL_DIR — never uploaded.
    Returns the record_id.
    """
    init_storage()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    record_file = RECORDS_DIR / f"{today}.jsonl"

    with _lock:
        # Append record to daily JSONL file
        with open(record_file, "a", encoding="utf-8") as f:
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
    """Load ECP records from local storage (newest first)."""
    init_storage()

    if date:
        files = [RECORDS_DIR / f"{date}.jsonl"]
    else:
        files = sorted(RECORDS_DIR.glob("*.jsonl"), reverse=True)

    records = []
    for f in files:
        if not f.exists():
            continue
        lines = f.read_text(encoding="utf-8").strip().splitlines()
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
    """Load a single record by ID."""
    init_storage()
    index = _load_index()

    if record_id not in index:
        return None

    file_path = Path(index[record_id]["file"])
    if not file_path.exists():
        return None

    for line in file_path.read_text(encoding="utf-8").splitlines():
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
    """Save raw content to vault for local inspection. Never transmitted."""
    try:
        init_storage()
        vault_file = VAULT_DIR / f"{record_id}.json"
        vault_file.write_text(json.dumps({
            "record_id": record_id,
            "input": input_content,
            "output": output_content,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass  # Fail-Open: vault save failure never crashes agent


def load_vault(record_id: str) -> Optional[dict]:
    """Load raw content from vault. Returns {input, output} or None."""
    vault_file = VAULT_DIR / f"{record_id}.json"
    if not vault_file.exists():
        return None
    try:
        return json.loads(vault_file.read_text(encoding="utf-8"))
    except Exception:
        return None


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
    """Count total ECP records."""
    init_storage()
    total = 0
    pattern = f"{date}.jsonl" if date else "*.jsonl"
    for f in RECORDS_DIR.glob(pattern):
        total += sum(1 for line in f.read_text().splitlines() if line.strip())
    return total


def _load_index() -> dict:
    if not INDEX_FILE.exists():
        return {}
    try:
        return json.loads(INDEX_FILE.read_text())
    except (json.JSONDecodeError, IOError):
        return {}
