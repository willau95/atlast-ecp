"""
ECP Backend — SQLite Database
Zero external dependencies for MVP. Migrate to Postgres when scaling.
"""

import sqlite3
import json
import os
from contextlib import contextmanager
from pathlib import Path

DB_PATH = os.environ.get("ECP_DB_PATH", "ecp.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # Concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db():
    """Context manager for database access."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create all tables. Safe to call multiple times (IF NOT EXISTS)."""
    with db() as conn:
        conn.executescript("""
            -- Agents table
            CREATE TABLE IF NOT EXISTS agents (
                did             TEXT PRIMARY KEY,
                public_key      TEXT NOT NULL,
                name            TEXT,
                description     TEXT,
                owner_x_handle  TEXT,
                ecp_version     TEXT NOT NULL DEFAULT '0.1',
                created_at      INTEGER NOT NULL,
                verified        INTEGER NOT NULL DEFAULT 0,
                claim_token     TEXT UNIQUE,
                claim_expires   INTEGER
            );

            -- Batches table
            CREATE TABLE IF NOT EXISTS batches (
                batch_id        TEXT PRIMARY KEY,
                agent_did       TEXT NOT NULL REFERENCES agents(did),
                merkle_root     TEXT NOT NULL,
                record_count    INTEGER NOT NULL,
                avg_latency_ms  INTEGER NOT NULL DEFAULT 0,
                batch_ts        INTEGER NOT NULL,
                ecp_version     TEXT NOT NULL DEFAULT '0.1',
                sig             TEXT NOT NULL,
                attestation_uid TEXT,
                eas_url         TEXT,
                anchored_at     INTEGER,
                created_at      INTEGER NOT NULL,
                upload_status   TEXT NOT NULL DEFAULT 'pending'
            );

            -- Record hashes table (for per-record verification)
            CREATE TABLE IF NOT EXISTS record_hashes (
                record_id       TEXT PRIMARY KEY,
                agent_did       TEXT NOT NULL REFERENCES agents(did),
                batch_id        TEXT REFERENCES batches(batch_id),
                chain_hash      TEXT NOT NULL,
                merkle_proof    TEXT,           -- JSON array of proof steps
                created_at      INTEGER NOT NULL
            );

            -- Flag stats table (aggregated from batches)
            CREATE TABLE IF NOT EXISTS agent_stats (
                agent_did           TEXT PRIMARY KEY REFERENCES agents(did),
                total_records       INTEGER NOT NULL DEFAULT 0,
                total_batches       INTEGER NOT NULL DEFAULT 0,
                avg_latency_ms      INTEGER NOT NULL DEFAULT 0,
                retried_count       INTEGER NOT NULL DEFAULT 0,
                hedged_count        INTEGER NOT NULL DEFAULT 0,
                incomplete_count    INTEGER NOT NULL DEFAULT 0,
                high_latency_count  INTEGER NOT NULL DEFAULT 0,
                error_count         INTEGER NOT NULL DEFAULT 0,
                human_review_count  INTEGER NOT NULL DEFAULT 0,
                chain_integrity     REAL NOT NULL DEFAULT 1.0,
                active_days         INTEGER NOT NULL DEFAULT 0,
                first_record_ts     INTEGER,
                last_record_ts      INTEGER,
                updated_at          INTEGER NOT NULL
            );

            -- Indexes
            CREATE INDEX IF NOT EXISTS idx_batches_agent ON batches(agent_did);
            CREATE INDEX IF NOT EXISTS idx_record_hashes_agent ON record_hashes(agent_did);
            CREATE INDEX IF NOT EXISTS idx_record_hashes_batch ON record_hashes(batch_id);
            CREATE INDEX IF NOT EXISTS idx_batches_ts ON batches(batch_ts);
        """)
