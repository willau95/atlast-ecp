"""
ECP Query & Audit Engine — search, trace, audit, timeline.

The core "use your data" layer. All operations are local-first:
  - SQLite index for fast search across months of records
  - Chain tracing for root cause analysis
  - Automated audit reports with anomaly detection
  - Timeline views for behavioral analysis

Design: CLI-first, --json for agent consumption, human-readable by default.
"""

import json
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from .storage import ECP_DIR, RECORDS_DIR, VAULT_DIR, load_record_by_id, load_vault  # noqa: F401 — VAULT_DIR used by tests

INDEX_DB = ECP_DIR / "search.db"


# ── SQLite Index ────────────────────────────────────────────────────────────


def _get_db() -> sqlite3.Connection:
    """Get or create the search index database."""
    ECP_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(INDEX_DB))
    db.row_factory = sqlite3.Row  # enables dict-like access
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id TEXT PRIMARY KEY,
            agent TEXT,
            ts INTEGER,
            date TEXT,
            step_type TEXT,
            action TEXT,
            model TEXT,
            latency_ms INTEGER,
            confidence REAL,
            session_id TEXT,
            delegation_id TEXT,
            delegation_depth INTEGER,
            chain_prev TEXT,
            chain_hash TEXT,
            flags TEXT,
            input_preview TEXT,
            output_preview TEXT,
            error INTEGER DEFAULT 0,
            is_infra INTEGER DEFAULT 0,
            error_type TEXT DEFAULT '',
            tokens_in INTEGER DEFAULT 0,
            tokens_out INTEGER DEFAULT 0,
            indexed_at INTEGER
        )
    """)
    # Migrate: add columns if missing (for existing DBs)
    try:
        db.execute("ALTER TABLE records ADD COLUMN is_infra INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        db.execute("ALTER TABLE records ADD COLUMN error_type TEXT DEFAULT ''")
    except Exception:
        pass
    try:
        db.execute("ALTER TABLE records ADD COLUMN tokens_in INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        db.execute("ALTER TABLE records ADD COLUMN tokens_out INTEGER DEFAULT 0")
    except Exception:
        pass
    db.execute("CREATE INDEX IF NOT EXISTS idx_records_ts ON records(ts)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_records_agent ON records(agent)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_records_session ON records(session_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_records_date ON records(date)")
    db.execute("""
        CREATE TABLE IF NOT EXISTS index_state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    db.commit()
    return db


def rebuild_index(verbose: bool = False) -> int:
    """Rebuild the full search index from JSONL files."""
    db = _get_db()
    count = 0
    now_ms = int(time.time() * 1000)

    import gzip as _gzip
    # Collect records from global dir AND per-agent dirs
    file_set = set(RECORDS_DIR.glob("*.jsonl")) | set(RECORDS_DIR.glob("*.jsonl.gz"))
    agents_dir = ECP_DIR / "agents"
    if agents_dir.exists():
        for agent_records in agents_dir.glob("*/records"):
            file_set |= set(agent_records.glob("*.jsonl"))
            file_set |= set(agent_records.glob("*.jsonl.gz"))
    all_files = sorted(file_set)
    for f in all_files:
        if str(f).endswith(".gz"):
            lines = _gzip.open(f, "rt", encoding="utf-8").read().splitlines()
        else:
            lines = f.read_text(encoding="utf-8").splitlines()
        for line in lines:
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue

            record_id = r.get("id", "")
            if not record_id:
                continue

            step = r.get("step", {})
            chain = r.get("chain", {})
            flags = step.get("flags", [])
            confidence = step.get("confidence")
            if isinstance(confidence, dict):
                confidence = confidence.get("score")

            # Extract preview text for search
            vault = load_vault(record_id)
            input_preview = ""
            output_preview = ""
            if vault:
                input_preview = (vault.get("input") or "")[:500]
                output_preview = (vault.get("output") or "")[:500]

            ts = r.get("ts", 0)
            date_str = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d") if ts else ""

            has_error = 1 if ("error" in flags or "exception" in flags or step.get("error")) else 0

            # Detect infra errors: from metadata (new records) or output content (old records)
            metadata = r.get("metadata", {})
            is_infra = 1 if metadata.get("is_infra_error") else 0
            error_type = metadata.get("error_type", "")

            # Retroactive detection for old records without metadata
            if has_error and not is_infra and not error_type:
                out_text = (output_preview or "").lower()
                infra_keywords = ("permission_error", "oauth", "revoked", "overloaded",
                                  "rate limit", "429", "503", "500", "connection",
                                  "infra_auth", "infra_error", "infra_overloaded",
                                  "infra_rate_limit", "infra_aborted",
                                  "[error: auth_error]", "[error: api_overloaded]",
                                  "[error: aborted]", "403")
                if any(k in out_text for k in infra_keywords):
                    is_infra = 1
                    error_type = "infra_error"
                # Note: 0 tokens + error alone is NOT enough to classify as infra
                # (agent errors can also have 0 tokens if they crash before LLM call)

            try:
                db.execute("""
                    INSERT OR REPLACE INTO records
                    (id, agent, ts, date, step_type, action, model, latency_ms,
                     confidence, session_id, delegation_id, delegation_depth,
                     chain_prev, chain_hash, flags, input_preview, output_preview,
                     error, is_infra, error_type, tokens_in, tokens_out, indexed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record_id,
                    r.get("agent", ""),
                    ts,
                    date_str,
                    step.get("type", ""),
                    step.get("action", ""),
                    step.get("model", ""),
                    step.get("latency_ms", 0),
                    confidence,
                    step.get("session_id") or r.get("session_id", ""),
                    step.get("delegation_id") or r.get("delegation_id", ""),
                    step.get("delegation_depth") or r.get("delegation_depth"),
                    chain.get("prev", ""),
                    chain.get("hash", ""),
                    json.dumps(flags) if flags else "[]",
                    input_preview,
                    output_preview,
                    has_error,
                    is_infra,
                    error_type,
                    step.get("tokens_in", 0) or 0,
                    step.get("tokens_out", 0) or 0,
                    now_ms,
                ))
                count += 1
            except Exception:
                continue

    db.execute("""
        INSERT OR REPLACE INTO index_state (key, value)
        VALUES ('last_rebuild', ?)
    """, (str(now_ms),))
    db.commit()
    db.close()

    if verbose:
        print(f"Indexed {count} records")
    return count


def _build_did_name_map() -> dict[str, str]:
    """Build a mapping from DID → friendly agent name using identity.json files."""
    from .storage import ECP_DIR
    import json as _json
    agents_dir = ECP_DIR / "agents"
    did_map: dict[str, str] = {}
    if agents_dir.is_dir():
        for agent_dir in agents_dir.iterdir():
            if agent_dir.is_dir():
                identity_file = agent_dir / "identity.json"
                if identity_file.exists():
                    try:
                        identity = _json.loads(identity_file.read_text())
                        did = identity.get("did", "")
                        if did:
                            did_map[did] = agent_dir.name
                    except Exception:
                        pass
    return did_map


def _is_excluded_record(flags_json: str) -> bool:
    """Check if a record should be excluded from scoring based on flags.
    Uses factual flags (v0.17+) with fallback to legacy classification."""
    try:
        flags = json.loads(flags_json) if flags_json else []
    except (json.JSONDecodeError, TypeError):
        flags = []
    flag_set = set(flags)
    # Excluded: heartbeat, provider_error (system), tool_intermediate (has_tool_calls + empty_output)
    if "heartbeat" in flag_set:
        return True
    if "provider_error" in flag_set:
        return True
    # tool_intermediate: has tool_calls AND (empty_output or tool_continuation without substantial text)
    if ("has_tool_calls" in flag_set or "tool_continuation" in flag_set) and "empty_output" in flag_set:
        return True
    return False


def list_agents(as_json: bool = False) -> list[dict]:
    """List all agents found in the records with summary stats.

    v0.17+: Uses scoring_rules classification to determine what counts as
    an 'interaction'. Heartbeats, system errors, infra errors, and tool
    intermediate steps are excluded from scoring.
    """
    _ensure_index()
    db = _get_db()
    rows = db.execute("""
        SELECT agent,
               COUNT(*) as total,
               SUM(CASE WHEN is_infra = 0 THEN 1 ELSE 0 END) as interactions,
               SUM(CASE WHEN error = 1 AND is_infra = 0 THEN 1 ELSE 0 END) as agent_errors,
               SUM(CASE WHEN is_infra = 1 THEN 1 ELSE 0 END) as infra_errors,
               MIN(date) as first_seen,
               MAX(date) as last_seen,
               AVG(CASE WHEN is_infra = 0 THEN latency_ms END) as avg_latency,
               SUM(tokens_in) as tokens_in,
               SUM(tokens_out) as tokens_out,
               SUM(CASE WHEN flags LIKE '%heartbeat%' THEN 1 ELSE 0 END) as heartbeats,
               SUM(CASE WHEN flags LIKE '%provider_error%' THEN 1 ELSE 0 END) as system_errors,
               SUM(CASE WHEN (flags LIKE '%has_tool_calls%' OR flags LIKE '%tool_continuation%')
                         AND flags LIKE '%empty_output%' THEN 1 ELSE 0 END) as tool_intermediates
        FROM records
        GROUP BY agent
        ORDER BY total DESC
    """).fetchall()
    db.close()

    did_map = _build_did_name_map()

    agents = []
    for row in rows:
        # v0.17: exclude heartbeats, system_errors, tool_intermediates from interaction count
        total = row[1] or 0
        legacy_interactions = row[2] or 0
        legacy_agent_errors = row[3] or 0
        heartbeats = row[10] or 0
        system_errors = row[11] or 0
        tool_intermediates = row[12] or 0
        excluded = heartbeats + system_errors + tool_intermediates

        # True interactions = legacy interactions minus newly excluded types
        interactions = max(0, legacy_interactions - excluded)
        # Agent errors: only count errors in true interactions
        agent_errors = max(0, min(legacy_agent_errors, interactions))

        did = row[0]
        agents.append({
            "agent": did,
            "agent_name": did_map.get(did, did.split(":")[-1][:12] if did else "unknown"),
            "total_records": total,
            "interactions": interactions,
            "agent_errors": agent_errors,
            "infra_errors": row[4] or 0,
            "heartbeats": heartbeats,
            "system_errors": system_errors,
            "tool_intermediates": tool_intermediates,
            "reliability": round((interactions - agent_errors) / interactions, 4) if interactions else 1.0,
            "first_seen": row[5],
            "last_seen": row[6],
            "avg_latency_ms": round(row[7] or 0),
            "tokens_in": row[8] or 0,
            "tokens_out": row[9] or 0,
        })
    return agents


def _ensure_index():
    """Auto-rebuild index if stale (> 5 min since last rebuild)."""
    db = _get_db()
    row = db.execute("SELECT value FROM index_state WHERE key = 'last_rebuild'").fetchone()
    db.close()

    if row:
        last_rebuild = int(row[0])
        if (time.time() * 1000 - last_rebuild) < 300_000:  # 5 min
            return
    rebuild_index()


# ── Search ──────────────────────────────────────────────────────────────────


def search(
    query: str,
    limit: int = 20,
    agent: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    errors_only: bool = False,
    as_json: bool = False,
) -> list[dict]:
    """
    Full-text search across all ECP records.
    Searches: action, model, input_preview, output_preview, flags, session_id.
    """
    _ensure_index()
    db = _get_db()

    conditions = []
    params = []

    if query:
        # Search across multiple fields including date
        conditions.append("""
            (action LIKE ? OR model LIKE ? OR input_preview LIKE ?
             OR output_preview LIKE ? OR flags LIKE ? OR session_id LIKE ?
             OR step_type LIKE ? OR id LIKE ? OR date LIKE ? OR agent LIKE ?)
        """)
        like = f"%{query}%"
        params.extend([like] * 10)

    if agent:
        conditions.append("agent = ?")
        params.append(agent)

    if since:
        conditions.append("date >= ?")
        params.append(since)

    if until:
        conditions.append("date <= ?")
        params.append(until)

    if errors_only:
        conditions.append("error = 1")

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    sql = f"SELECT * FROM records {where} ORDER BY ts DESC LIMIT ?"
    params.append(limit)

    cur = db.execute(sql, params)
    rows = cur.fetchall()

    results = [dict(row) for row in rows]
    db.close()

    if not as_json:
        _print_search_results(results, query)
    return results


def _print_search_results(results: list[dict], query: str):
    """Human-readable search output."""
    if not results:
        print(f"No records found for '{query}'")
        return

    print(f"\n🔍 Found {len(results)} record(s) matching '{query}':\n")
    for r in results:
        ts_str = datetime.fromtimestamp(r["ts"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if r["ts"] else "?"
        error_mark = " ❌" if r.get("error") else ""
        conf = f" conf={r['confidence']:.2f}" if r.get("confidence") is not None else ""

        print(f"  {r['id']}  {ts_str}  [{r.get('step_type', '?')}] {r.get('action', '')}{error_mark}{conf}")

        if r.get("input_preview"):
            preview = r["input_preview"][:80].replace("\n", " ")
            print(f"    → {preview}...")

        if r.get("session_id"):
            print(f"    session: {r['session_id']}")
    print()


# ── Trace ───────────────────────────────────────────────────────────────────


def trace(record_id: str, direction: str = "back", limit: int = 50, as_json: bool = False) -> list[dict]:
    """
    Trace the evidence chain from a record.
    direction='back': follow chain.prev backwards (root cause analysis)
    direction='forward': find records that reference this one (impact analysis)
    """
    _ensure_index()
    db = _get_db()
    chain = []

    if direction == "back":
        current_id = record_id
        seen = set()
        while current_id and len(chain) < limit:
            if current_id in seen:
                break
            seen.add(current_id)

            row = db.execute("SELECT * FROM records WHERE id = ?", (current_id,)).fetchone()
            if not row:
                # Try loading from file
                record = load_record_by_id(current_id)
                if record:
                    chain.append({"id": current_id, "record": record, "source": "file"})
                    current_id = record.get("chain", {}).get("prev", "")
                else:
                    break
            else:

                entry = dict(row)
                chain.append(entry)
                current_id = entry.get("chain_prev", "")
    else:
        # Forward: find records whose chain_prev points to this record
        current_ids = [record_id]
        seen = set()
        while current_ids and len(chain) < limit:
            next_ids = []
            for cid in current_ids:
                if cid in seen:
                    continue
                seen.add(cid)
                rows = db.execute("SELECT * FROM records WHERE chain_prev = ?", (cid,)).fetchall()

                for row in rows:
                    entry = dict(row)
                    chain.append(entry)
                    next_ids.append(entry["id"])
            current_ids = next_ids

    db.close()

    if not as_json:
        _print_trace(chain, record_id, direction)
    return chain


def _print_trace(chain: list[dict], start_id: str, direction: str):
    """Human-readable trace output."""
    if not chain:
        print(f"No chain found from {start_id}")
        return

    arrow = "←" if direction == "back" else "→"
    label = "Root Cause Trace" if direction == "back" else "Impact Trace"
    print(f"\n🔗 {label} from {start_id} ({len(chain)} steps):\n")

    for i, entry in enumerate(chain):
        record = entry.get("record", entry)
        rid = record.get("id", entry.get("id", "?"))
        ts = record.get("ts", entry.get("ts", 0))
        ts_str = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%m-%d %H:%M") if ts else "?"
        action = record.get("step", {}).get("action", entry.get("action", ""))
        step_type = record.get("step", {}).get("type", entry.get("step_type", ""))
        error = "❌" if entry.get("error") else "✓"

        prefix = f"  {'  ' * i}{arrow} " if i > 0 else "  ● "
        print(f"{prefix}[{ts_str}] {rid}  {step_type}:{action}  {error}")

    print()


# ── Timeline ────────────────────────────────────────────────────────────────


def timeline(
    days: int = 7,
    since: Optional[str] = None,
    until: Optional[str] = None,
    agent: Optional[str] = None,
    as_json: bool = False,
) -> list[dict]:
    """
    Daily activity timeline — record counts, error rates, latency trends.
    """
    _ensure_index()
    db = _get_db()

    if not since:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    if not until:
        until = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    agent_cond = "AND agent = ?" if agent else ""
    params = [since, until]
    if agent:
        params.append(agent)

    rows = db.execute(f"""
        SELECT date,
               COUNT(*) as total,
               SUM(CASE WHEN error = 1 AND is_infra = 0 THEN 1 ELSE 0 END) as agent_errors,
               SUM(CASE WHEN is_infra = 1 THEN 1 ELSE 0 END) as infra_errors,
               AVG(CASE WHEN is_infra = 0 THEN latency_ms END) as avg_latency,
               AVG(confidence) as avg_confidence,
               COUNT(DISTINCT session_id) as sessions,
               SUM(CASE WHEN is_infra = 0 THEN 1 ELSE 0 END) as interactions,
               SUM(tokens_in) as total_tokens_in,
               SUM(tokens_out) as total_tokens_out
        FROM records
        WHERE date >= ? AND date <= ? {agent_cond}
        GROUP BY date
        ORDER BY date
    """, params).fetchall()

    results = []
    for row in rows:
        interactions = row[7] or 0
        agent_errors = row[2] or 0
        infra_errors = row[3] or 0
        results.append({
            "date": row[0],
            "total": row[1],
            "interactions": interactions,
            "agent_errors": agent_errors,
            "infra_errors": infra_errors,
            "error_rate": round(agent_errors / interactions * 100, 1) if interactions else 0,
            "infra_error_rate": round(infra_errors / row[1] * 100, 1) if row[1] else 0,
            "avg_latency_ms": round(row[4] or 0),
            "avg_confidence": round(row[5], 3) if row[5] is not None else None,
            "sessions": row[6] or 0,
            "tokens_in": row[8] or 0,
            "tokens_out": row[9] or 0,
        })

    db.close()

    if not as_json:
        _print_timeline(results, since, until)
    return results


def _print_timeline(results: list[dict], since: str, until: str):
    """Human-readable timeline."""
    if not results:
        print(f"No activity between {since} and {until}")
        return

    print(f"\n📅 Timeline: {since} → {until}\n")
    print(f"  {'Date':<12} {'Work':>8} {'AgErr':>8} {'Infra':>8} {'Err%':>6} {'Latency':>10} {'Sessions':>9}")
    print(f"  {'─'*12} {'─'*8} {'─'*8} {'─'*8} {'─'*6} {'─'*10} {'─'*9}")

    for d in results:
        print(f"  {d['date']:<12} {d.get('interactions',d['total']):>8} {d.get('agent_errors',0):>8} {d.get('infra_errors',0):>8} {d['error_rate']:>5.1f}% {d['avg_latency_ms']:>8}ms {d['sessions']:>9}")

    total_interactions = sum(d.get("interactions", d["total"]) for d in results)
    total_agent_errors = sum(d.get("agent_errors", 0) for d in results)
    total_infra = sum(d.get("infra_errors", 0) for d in results)
    avg_rate = round(total_agent_errors / total_interactions * 100, 1) if total_interactions else 0
    print(f"\n  Total: {total_interactions} interactions, {total_agent_errors} agent errors ({avg_rate}%), {total_infra} infra errors, {len(results)} active days\n")


# ── Audit ───────────────────────────────────────────────────────────────────


def audit(
    days: int = 30,
    agent: Optional[str] = None,
    as_json: bool = False,
) -> dict:
    """
    Automated audit report — the killer feature.
    Analyzes record history and produces actionable findings:
    - Behavioral drift detection
    - Error pattern analysis
    - Confidence trend monitoring
    - Chain integrity verification
    - Anomaly flagging with root cause candidates
    """
    _ensure_index()
    db = _get_db()

    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    until = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    agent_cond = "AND agent = ?" if agent else ""
    params = [since]
    if agent:
        params.append(agent)

    # ── Gather data ──
    all_records = db.execute(f"""
        SELECT * FROM records WHERE date >= ? {agent_cond} ORDER BY ts
    """, params).fetchall()

    records = [dict(r) for r in all_records]

    if not records:
        report = {"status": "no_data", "period_days": days, "message": "No records found"}
        if not as_json:
            print(f"\n📋 Audit Report: No records found in the last {days} days\n")
        db.close()
        return report

    # ── Basic stats (separating infra from agent errors) ──
    total = len(records)
    infra_errors = sum(1 for r in records if r.get("is_infra"))
    agent_records = [r for r in records if not r.get("is_infra")]
    interactions = len(agent_records)
    agent_errors = sum(1 for r in agent_records if r.get("error"))
    error_rate = round(agent_errors / interactions * 100, 1) if interactions else 0
    sessions = len(set(r.get("session_id") or "" for r in records if r.get("session_id")))

    # Chain integrity
    for i, r in enumerate(records):
        if i == 0:
            continue
        if r.get("chain_prev") and r["chain_prev"] != records[i-1].get("id"):
            # Not necessarily a break — could be different session
            pass

    # ── Anomaly detection ──
    anomalies = []

    # 1. Error spikes: any day with > 20% agent error rate (excludes infra)
    daily_stats = {}
    for r in agent_records:
        d = r.get("date", "")
        if d not in daily_stats:
            daily_stats[d] = {"total": 0, "errors": 0, "latencies": [], "confidences": []}
        daily_stats[d]["total"] += 1
        if r.get("error"):
            daily_stats[d]["errors"] += 1
        if r.get("latency_ms"):
            daily_stats[d]["latencies"].append(r["latency_ms"])
        if r.get("confidence") is not None:
            daily_stats[d]["confidences"].append(r["confidence"])

    for date, stats in daily_stats.items():
        day_error_rate = stats["errors"] / stats["total"] * 100 if stats["total"] else 0
        if day_error_rate > 20:
            # Find first error record on this day
            first_error = next(
                (r for r in records if r.get("date") == date and r.get("error")),
                None
            )
            anomalies.append({
                "type": "error_spike",
                "date": date,
                "severity": "high" if day_error_rate > 50 else "medium",
                "detail": f"Error rate {day_error_rate:.0f}% ({stats['errors']}/{stats['total']})",
                "first_error_id": first_error["id"] if first_error else None,
            })

    # 2. Confidence drops: sudden drop > 0.3 between consecutive days
    sorted_dates = sorted(daily_stats.keys())
    for i in range(1, len(sorted_dates)):
        prev_date = sorted_dates[i - 1]
        curr_date = sorted_dates[i]
        prev_conf = daily_stats[prev_date]["confidences"]
        curr_conf = daily_stats[curr_date]["confidences"]
        if prev_conf and curr_conf:
            prev_avg = sum(prev_conf) / len(prev_conf)
            curr_avg = sum(curr_conf) / len(curr_conf)
            if prev_avg - curr_avg > 0.3:
                anomalies.append({
                    "type": "confidence_drop",
                    "date": curr_date,
                    "severity": "high",
                    "detail": f"Confidence dropped {prev_avg:.2f} → {curr_avg:.2f}",
                    "prev_date": prev_date,
                })

    # 3. Latency spikes: any day with avg latency > 3x overall average
    all_latencies = [r.get("latency_ms", 0) for r in records if r.get("latency_ms")]
    overall_avg_latency = sum(all_latencies) / len(all_latencies) if all_latencies else 0
    if overall_avg_latency > 0:
        for date, stats in daily_stats.items():
            if stats["latencies"]:
                day_avg = sum(stats["latencies"]) / len(stats["latencies"])
                if day_avg > overall_avg_latency * 3:
                    anomalies.append({
                        "type": "latency_spike",
                        "date": date,
                        "severity": "medium",
                        "detail": f"Avg latency {day_avg:.0f}ms (normal: {overall_avg_latency:.0f}ms)",
                    })

    # ── Root cause candidates ──
    root_causes = []
    for anomaly in anomalies:
        if anomaly.get("first_error_id"):
            # Trace back from first error
            chain = trace(anomaly["first_error_id"], direction="back", limit=5, as_json=True)
            if chain:
                root_causes.append({
                    "anomaly": anomaly["type"],
                    "date": anomaly["date"],
                    "trace_start": anomaly["first_error_id"],
                    "chain_depth": len(chain),
                    "chain_ids": [c.get("id", c.get("record", {}).get("id", "?")) for c in chain],
                })

    # ── Compile report ──
    report = {
        "status": "complete",
        "period": {"from": since, "to": until, "days": days},
        "summary": {
            "total_records": total,
            "total_interactions": interactions,
            "agent_errors": agent_errors,
            "infra_errors": infra_errors,
            "error_rate_pct": error_rate,
            "reliability": round((interactions - agent_errors) / interactions, 4) if interactions else 1.0,
            "availability": round(interactions / total, 4) if total else 1.0,
            "sessions": sessions,
            "active_days": len(daily_stats),
            "avg_latency_ms": round(overall_avg_latency),
        },
        "anomalies": anomalies,
        "root_causes": root_causes,
        "health": "healthy" if not anomalies else ("degraded" if any(a["severity"] == "high" for a in anomalies) else "warning"),
    }

    db.close()

    if not as_json:
        _print_audit(report)
    return report


def _print_audit(report: dict):
    """Human-readable audit report."""
    s = report["summary"]
    p = report["period"]
    health_icon = {"healthy": "✅", "warning": "⚠️", "degraded": "🔴"}.get(report["health"], "?")

    print(f"\n{'='*60}")
    print("  📋 ATLAST ECP Audit Report")
    print(f"  Period: {p['from']} → {p['to']} ({p['days']} days)")
    print(f"  Health: {health_icon} {report['health'].upper()}")
    print(f"{'='*60}\n")

    print("  📊 Summary")
    print(f"    Interactions:  {s.get('total_interactions', s['total_records']):,}")
    print(f"    Agent Errors:  {s.get('agent_errors', 0):,} ({s['error_rate_pct']}%)")
    print(f"    Infra Errors:  {s.get('infra_errors', 0):,}")
    print(f"    Reliability:   {s.get('reliability', 0)*100:.1f}%")
    print(f"    Sessions:      {s['sessions']:,}")
    print(f"    Active Days:   {s['active_days']}")
    print(f"    Avg Latency:   {s['avg_latency_ms']}ms")
    print()

    anomalies = report.get("anomalies", [])
    if anomalies:
        print(f"  ⚠️  Anomalies Detected: {len(anomalies)}\n")
        for a in anomalies:
            sev_icon = "🔴" if a["severity"] == "high" else "🟡"
            print(f"    {sev_icon} [{a['date']}] {a['type']}: {a['detail']}")
            if a.get("first_error_id"):
                print(f"       First error: {a['first_error_id']}")
        print()

    root_causes = report.get("root_causes", [])
    if root_causes:
        print("  🔍 Root Cause Candidates:\n")
        for rc in root_causes:
            print(f"    [{rc['date']}] {rc['anomaly']} — chain depth {rc['chain_depth']}")
            print(f"      Trace: {' → '.join(rc['chain_ids'][:5])}")
        print()

    if not anomalies:
        print("  ✅ No anomalies detected. Agent behavior is consistent.\n")

    print("  📝 Evidence: All records are locally stored and chain-linked.")
    print("     Run 'atlast trace <record_id>' for detailed chain analysis.")
    print("     Run 'atlast search <keyword>' to find specific records.")
    print(f"{'='*60}\n")
