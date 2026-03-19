"""
ECP Reference Server — SQLite Storage Layer

Three tables: agents, batches, record_hashes.
WAL mode for concurrent reads. Auto-migrate on startup.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .config import settings

_db: Optional[sqlite3.Connection] = None

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    did TEXT UNIQUE NOT NULL,
    public_key TEXT NOT NULL,
    handle TEXT UNIQUE NOT NULL,
    display_name TEXT,
    description TEXT,
    status TEXT,
    api_key_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS batches (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(id),
    batch_ts INTEGER NOT NULL,
    merkle_root TEXT NOT NULL,
    record_count INTEGER NOT NULL,
    flag_counts TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS record_hashes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL REFERENCES batches(id),
    record_id TEXT NOT NULL,
    chain_hash TEXT NOT NULL,
    step_type TEXT,
    ts INTEGER,
    flags TEXT,
    latency_ms INTEGER,
    model TEXT
);

CREATE INDEX IF NOT EXISTS idx_batches_agent ON batches(agent_id);
CREATE INDEX IF NOT EXISTS idx_record_hashes_batch ON record_hashes(batch_id);
"""


def _hash_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def _generate_api_key() -> str:
    return "atl_" + secrets.token_hex(16)


def _generate_handle(did: str) -> str:
    """Auto-generate a handle from DID."""
    short = did.replace("did:ecp:", "")[:8]
    return f"agent-{short}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db() -> sqlite3.Connection:
    global _db
    if _db is None:
        _db = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
        _db.row_factory = sqlite3.Row
        _db.execute("PRAGMA journal_mode=WAL")
        _db.execute("PRAGMA foreign_keys=ON")
        _db.executescript(SCHEMA_SQL)
        _db.commit()
    return _db


def close_db():
    global _db
    if _db:
        _db.close()
        _db = None


def reset_db():
    """Reset database (for testing)."""
    global _db
    close_db()
    if os.path.exists(settings.DB_PATH):
        os.remove(settings.DB_PATH)


# ─── Agent CRUD ───


def register_agent(
    did: str,
    public_key: str,
    handle: Optional[str] = None,
    display_name: Optional[str] = None,
) -> dict:
    db = get_db()
    agent_id = str(uuid.uuid4())
    api_key = _generate_api_key()
    handle = handle or _generate_handle(did)
    now = _now_iso()

    db.execute(
        """INSERT INTO agents (id, did, public_key, handle, display_name, api_key_hash, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (agent_id, did, public_key, handle, display_name, _hash_key(api_key), now, now),
    )
    db.commit()

    return {
        "agent_id": agent_id,
        "did": did,
        "handle": handle,
        "api_key": api_key,
    }


def get_agent_by_key(api_key: str) -> Optional[dict]:
    db = get_db()
    key_hash = _hash_key(api_key)
    row = db.execute("SELECT * FROM agents WHERE api_key_hash = ?", (key_hash,)).fetchone()
    return dict(row) if row else None


def get_agent_by_handle(handle: str) -> Optional[dict]:
    db = get_db()
    row = db.execute("SELECT * FROM agents WHERE handle = ?", (handle,)).fetchone()
    return dict(row) if row else None


def get_agent_by_did(did: str) -> Optional[dict]:
    db = get_db()
    row = db.execute("SELECT * FROM agents WHERE did = ?", (did,)).fetchone()
    return dict(row) if row else None


# ─── Batch CRUD ───


def create_batch(
    agent_id: str,
    batch_ts: int,
    merkle_root: str,
    record_count: int,
    flag_counts: Optional[dict] = None,
    record_hashes: Optional[list[dict]] = None,
) -> dict:
    db = get_db()
    batch_id = str(uuid.uuid4())
    now = _now_iso()

    db.execute(
        """INSERT INTO batches (id, agent_id, batch_ts, merkle_root, record_count, flag_counts, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (batch_id, agent_id, batch_ts, merkle_root, record_count,
         json.dumps(flag_counts) if flag_counts else None, now),
    )

    if record_hashes:
        for rh in record_hashes:
            db.execute(
                """INSERT INTO record_hashes (batch_id, record_id, chain_hash, step_type, ts, flags, latency_ms, model)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (batch_id, rh["record_id"], rh["chain_hash"],
                 rh.get("step_type"), rh.get("ts"),
                 json.dumps(rh.get("flags", [])),
                 rh.get("latency_ms"), rh.get("model")),
            )

    db.commit()
    return {"batch_id": batch_id, "record_count": record_count, "merkle_root": merkle_root}


def get_agent_stats(agent_id: str) -> dict:
    db = get_db()
    batch_row = db.execute(
        "SELECT COUNT(*) as cnt, COALESCE(SUM(record_count), 0) as total_records FROM batches WHERE agent_id = ?",
        (agent_id,),
    ).fetchone()

    first = db.execute(
        "SELECT MIN(created_at) as first_seen FROM batches WHERE agent_id = ?",
        (agent_id,),
    ).fetchone()

    last = db.execute(
        "SELECT MAX(created_at) as last_active FROM batches WHERE agent_id = ?",
        (agent_id,),
    ).fetchone()

    # Aggregate flag counts across all batches
    all_flags = {"hedged": 0, "high_latency": 0, "error": 0, "retried": 0, "incomplete": 0, "human_review": 0}
    rows = db.execute(
        "SELECT flag_counts FROM batches WHERE agent_id = ? AND flag_counts IS NOT NULL",
        (agent_id,),
    ).fetchall()
    for row in rows:
        fc = json.loads(row["flag_counts"])
        for k in all_flags:
            all_flags[k] += fc.get(k, 0)

    return {
        "total_batches": batch_row["cnt"],
        "total_records": batch_row["total_records"],
        "first_seen": first["first_seen"],
        "last_active": last["last_active"],
        "flag_counts": all_flags,
    }


# ─── Leaderboard ───


def get_leaderboard(period: str = "all", domain: str = "all", limit: int = 20) -> list[dict]:
    db = get_db()

    # Period filter
    where_clause = ""
    params: list[Any] = []
    if period != "all":
        days_map = {"24h": 1, "7d": 7, "30d": 30}
        days = days_map.get(period)
        if days:
            cutoff = datetime.now(timezone.utc).isoformat()
            # Simple: filter batches by created_at
            where_clause = "WHERE b.created_at >= datetime('now', ?)"
            params.append(f"-{days} days")

    query = f"""
        SELECT a.id, a.did, a.handle, a.display_name,
               COUNT(b.id) as batch_count,
               COALESCE(SUM(b.record_count), 0) as record_count
        FROM agents a
        LEFT JOIN batches b ON a.id = b.agent_id {where_clause.replace('WHERE', 'AND') if where_clause else ''}
        GROUP BY a.id
        HAVING record_count > 0
        ORDER BY record_count DESC
        LIMIT ?
    """
    params.append(limit)

    rows = db.execute(query, params).fetchall()
    return [dict(row) for row in rows]
