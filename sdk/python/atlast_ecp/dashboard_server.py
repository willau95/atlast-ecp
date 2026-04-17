"""
ATLAST ECP Local Dashboard Server.

Serves a web UI on localhost for visual record exploration.
All data stays local — reads from ~/.ecp/ SQLite index.

Usage: atlast dashboard [--port 3827] [--no-open]
"""

import json
import threading
import webbrowser
from datetime import datetime, timezone, timedelta
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ASSETS_DIR = Path(__file__).parent / "dashboard_assets"
DEFAULT_PORT = 3827


_TRUST_SCORE_CACHE: dict = {"ts": 0.0, "map": {}}
_TRUST_SCORE_TTL_S = 60.0


def _get_cached_trust_scores() -> dict:
    """Return {agent_name: trust_score} with a 60-second TTL cache.

    The underlying computation (classify + compute_trust_score_1000 per agent
    over the full batch) costs ~1 s on 7 k records and doesn't change per
    request. The dashboard polls /api/agents frequently; without the cache
    every refresh re-ran the full O(N·M) pass.
    """
    import time as _t
    now = _t.time()
    if now - _TRUST_SCORE_CACHE["ts"] < _TRUST_SCORE_TTL_S and _TRUST_SCORE_CACHE["map"]:
        return _TRUST_SCORE_CACHE["map"]
    try:
        from .scoring_rules import classify_records, compute_trust_score_1000
        from .signals import compute_trust_signals
        from .batch import collect_batch
        all_records, _ = collect_batch(since_ts=0)
        by_agent: dict = {}
        for r in all_records:
            key = r.get("agent") or r.get("agent_name")
            if not key:
                continue
            by_agent.setdefault(key, []).append(r)
        out: dict = {}
        for key, recs in by_agent.items():
            try:
                classified = classify_records(recs)
                trust_signals = compute_trust_signals(recs)
                ci = trust_signals.get("chain_integrity", 1.0)
                score_data = compute_trust_score_1000(classified, chain_integrity=ci)
                out[key] = score_data.get("trust_score")
            except Exception:
                out[key] = None
        _TRUST_SCORE_CACHE["map"] = out
        _TRUST_SCORE_CACHE["ts"] = now
        return out
    except Exception:
        return _TRUST_SCORE_CACHE["map"] or {}


class DashboardHandler(BaseHTTPRequestHandler):
    # Python's stdlib HTTP server does a reverse-DNS lookup on the client IP
    # for every request (via address_string() → getfqdn). That's a hidden
    # 500 ms–2 s stall per request on macOS. Return the numeric address and
    # silence the default access log (which also calls getfqdn).
    def address_string(self):
        return self.client_address[0]

    def log_message(self, format, *args):
        # Silent by default; dashboards don't need an access log on stderr.
        return

    """HTTP handler for the local dashboard."""

    def log_message(self, format, *args):
        """Suppress default request logging."""
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # API routes
        if path.startswith("/api/"):
            self._handle_api(path, params)
            return

        # Static files
        if path == "/" or path == "/index.html":
            self._serve_file("index.html", "text/html")
        elif path.endswith(".js"):
            self._serve_file(path.lstrip("/"), "application/javascript")
        elif path.endswith(".css"):
            self._serve_file(path.lstrip("/"), "text/css")
        else:
            self._serve_file("index.html", "text/html")

    def _serve_file(self, filename: str, content_type: str):
        filepath = (ASSETS_DIR / filename).resolve()
        # Prevent path traversal — file must be under ASSETS_DIR
        if not str(filepath).startswith(str(ASSETS_DIR.resolve())):
            self.send_error(403, "Forbidden")
            return
        if not filepath.exists():
            self.send_error(404)
            return
        data = filepath.read_bytes()
        if filename == "index.html":
            data = self._inject_enhancements(data)

        accept_enc = (self.headers.get("Accept-Encoding") or "").lower()
        use_gzip = "gzip" in accept_enc and len(data) >= 1024
        if use_gzip:
            import gzip as _gz
            data = _gz.compress(data, compresslevel=5)

        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        if use_gzip:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _inject_enhancements(self, html_bytes: bytes) -> bytes:
        """No-op: new React dashboard has all UX features built-in.
        Legacy enhancement injection disabled to avoid CSS/JS conflicts."""
        return html_bytes

    def _handle_api(self, path: str, params: dict):
        try:
            try:
                from .flush import flush_stale_buffers
                flush_stale_buffers()
            except Exception:
                pass
            result = self._dispatch_api(path, params)
            self._json_response(200, result)
        except Exception as e:
            self._json_response(500, {"error": str(e)})

    def _resolve_agent_name(self, name: str) -> str:
        """Convert a friendly agent name to its DID, or return as-is if already a DID."""
        if not name or name.startswith("did:"):
            return name
        from .query import _build_did_name_map
        did_map = _build_did_name_map()
        # Reverse: name → DID
        for did, n in did_map.items():
            if n == name:
                return did
        return name  # fallback: return as-is

    def _dispatch_api(self, path: str, params: dict) -> dict:
        from .query import search, trace, audit, timeline, rebuild_index, list_agents, list_threads, get_thread

        # ── Session Records (main + subagents grouped) ──
        if path == "/api/session-records":
            session_id = params.get("session", [""])[0]
            if not session_id:
                return {"error": "session parameter required"}
            from .query import _ensure_index as _sri, _get_db as _srdb
            _sri()
            db_sr = _srdb()
            rows = db_sr.execute(
                "SELECT id, agent, ts, step_type, action, model, latency_ms, "
                "tokens_in, tokens_out, input_preview, output_preview, error, is_infra, flags "
                "FROM records WHERE session_id = ? OR thread_id = ? ORDER BY ts ASC",
                (session_id, session_id)
            ).fetchall()
            db_sr.close()
            main_records = []
            sub_records = []
            for r in rows:
                rec = {
                    "id": r[0], "agent": r[1], "ts": r[2], "step_type": r[3],
                    "action": r[4], "model": r[5], "latency_ms": r[6],
                    "tokens_in": r[7], "tokens_out": r[8],
                    "input_preview": r[9], "output_preview": r[10],
                    "error": r[11], "is_infra": r[12], "flags": r[13],
                    "is_subagent": "/subagent" in (r[1] or ""),
                }
                if rec["is_subagent"]:
                    sub_records.append(rec)
                else:
                    main_records.append(rec)
            return {
                "session_id": session_id,
                "main_records": main_records,
                "sub_records": sub_records,
                "total_main": len(main_records),
                "total_sub": len(sub_records),
                "total_tokens_in": sum(r.get("tokens_in") or 0 for r in main_records + sub_records),
                "total_tokens_out": sum(r.get("tokens_out") or 0 for r in main_records + sub_records),
            }

        # ── Token Analytics ──
        elif path == "/api/token-stats":
            from .query import _ensure_index as _tei, _get_db as _tdb
            _tei()
            db_t = _tdb()
            agent = params.get("agent", [None])[0]
            if agent:
                agent = self._resolve_agent_name(agent)
            conds = ["1=1"]
            p_t = []
            if agent:
                conds.append("agent = ?")
                p_t.append(agent)
            # Per-model stats
            model_rows = db_t.execute(
                "SELECT model, COUNT(*) as calls, "
                "SUM(COALESCE(tokens_in,0)) as tin, SUM(COALESCE(tokens_out,0)) as tout, "
                "AVG(CASE WHEN tokens_in > 0 THEN tokens_in END) as avg_in, "
                "AVG(CASE WHEN tokens_out > 0 THEN tokens_out END) as avg_out, "
                "SUM(CASE WHEN tokens_in > 0 OR tokens_out > 0 THEN 1 ELSE 0 END) as with_tok "
                "FROM records WHERE %s AND model != '' GROUP BY model ORDER BY tin+tout DESC" % " AND ".join(conds), p_t
            ).fetchall()
            # Per-day timeline
            day_rows = db_t.execute(
                "SELECT date, SUM(COALESCE(tokens_in,0)) as tin, SUM(COALESCE(tokens_out,0)) as tout, "
                "COUNT(*) as calls "
                "FROM records WHERE %s GROUP BY date ORDER BY date" % " AND ".join(conds), p_t
            ).fetchall()
            # Totals
            totals = db_t.execute(
                "SELECT SUM(COALESCE(tokens_in,0)), SUM(COALESCE(tokens_out,0)), COUNT(*), "
                "SUM(CASE WHEN tokens_in > 0 OR tokens_out > 0 THEN 1 ELSE 0 END) "
                "FROM records WHERE %s" % " AND ".join(conds), p_t
            ).fetchone()
            db_t.close()

            models = [{
                "model": r[0], "calls": r[1], "tokens_in": r[2], "tokens_out": r[3],
                "tokens_total": r[2] + r[3],
                "avg_tokens_in": int(r[4] or 0), "avg_tokens_out": int(r[5] or 0),
                "coverage": round(r[6] / max(r[1], 1) * 100, 1),
            } for r in model_rows]

            timeline = [{"date": r[0], "tokens_in": r[1], "tokens_out": r[2], "calls": r[3]} for r in day_rows]

            return {
                "total_tokens_in": totals[0] or 0,
                "total_tokens_out": totals[1] or 0,
                "total_tokens": (totals[0] or 0) + (totals[1] or 0),
                "total_records": totals[2] or 0,
                "records_with_tokens": totals[3] or 0,
                "coverage_pct": round((totals[3] or 0) / max(totals[2] or 1, 1) * 100, 1),
                "models": models,
                "timeline": timeline,
            }

        # ── Attestations (proxy to ATLAST server) ──
        elif path == "/api/attestations":
            try:
                import urllib.request as _ur2
                resp = _ur2.urlopen("https://api.weba0.com/v1/attestations?limit=100", timeout=10)
                import json as _j2
                return _j2.loads(resp.read())
            except Exception as e:
                return {"attestations": [], "error": str(e)}

        # ── Incidents ──
        elif path == "/api/incidents":
            from .incidents import get_incidents, get_active_incident
            status = params.get("status", [None])[0]
            limit = int(params.get("limit", ["20"])[0])
            return {
                "incidents": get_incidents(limit=limit, status=status),
                "active": get_active_incident(),
            }

        # ── Semantic Search ──
        elif path == "/api/semantic-search":
            q = params.get("q", [""])[0]
            limit = int(params.get("limit", ["20"])[0])
            if not q:
                return {"results": [], "error": "Query required"}
            from .embeddings import semantic_search
            hits = semantic_search(q, limit=limit)
            if not hits:
                return {"results": [], "query": q, "total": 0}
            # Enrich with full record data
            from .query import _ensure_index as _sei, _get_db as _sgdb
            _sei()
            db_s = _sgdb()
            enriched = []
            for h in hits:
                row = db_s.execute(
                    "SELECT id, agent, ts, date, step_type, action, model, latency_ms, confidence, "
                    "session_id, chain_prev, chain_hash, flags, input_preview, output_preview, "
                    "error, is_infra, tokens_in, tokens_out FROM records WHERE id = ?",
                    (h["id"],)
                ).fetchone()
                if row:
                    enriched.append({
                        "id": row[0], "agent": row[1], "ts": row[2], "date": row[3],
                        "step_type": row[4], "action": row[5], "model": row[6],
                        "latency_ms": row[7], "confidence": row[8], "session_id": row[9],
                        "chain_prev": row[10], "chain_hash": row[11], "flags": row[12],
                        "input_preview": row[13], "output_preview": row[14],
                        "error": row[15], "is_infra": row[16],
                        "tokens_in": row[17], "tokens_out": row[18],
                        "score": h["score"],
                    })
            db_s.close()
            return {"results": enriched, "query": q, "total": len(enriched)}

        # ── Evaluation ──
        elif path == "/api/evaluation":
            agent = params.get("agent", [None])[0]
            days = int(params.get("days", ["30"])[0])
            from .query import _ensure_index as _ei2, _get_db as _gdb2
            _ei2()
            from .evaluation import evaluate_records
            db3 = _gdb2()
            conds = ["1=1"]
            p2 = []
            if agent:
                conds.append("agent = ?")
                p2.append(agent)
            rows = db3.execute(
                "SELECT id, agent, ts, model, flags, input_preview, output_preview, error, is_infra FROM records WHERE %s ORDER BY ts DESC LIMIT 500" % " AND ".join(conds), p2
            ).fetchall()
            db3.close()
            recs = [{"id":r[0],"agent":r[1],"ts":r[2],"model":r[3],"flags":r[4],"input_preview":r[5],"output_preview":r[6],"error":r[7],"is_infra":r[8]} for r in rows]
            return evaluate_records(recs)

        # ── Clusters ──
        elif path == "/api/clusters":
            agent = params.get("agent", [None])[0]
            days = int(params.get("days", ["30"])[0])
            min_size = int(params.get("min_size", ["2"])[0])
            # Get records for clustering
            from .query import _ensure_index as _ei, _get_db as _gdb
            _ei()
            from .clustering import discover_clusters
            db2 = _gdb()
            conditions = ["error = 1 OR is_infra = 1"]
            p = []
            if agent:
                conditions.append("agent = ?")
                p.append(agent)
            rows = db2.execute(
                "SELECT id, agent, ts, model, latency_ms, flags, error, is_infra FROM records WHERE %s ORDER BY ts DESC LIMIT 500" % " AND ".join(conditions), p
            ).fetchall()
            db2.close()
            recs = [{"id":r[0],"agent":r[1],"ts":r[2],"model":r[3],"latency_ms":r[4],"flags":r[5],"error":r[6],"is_infra":r[7]} for r in rows]
            return {"clusters": discover_clusters(recs, min_cluster_size=min_size)}

        # ── Suggestions ──
        elif path == "/api/suggestions":
            agent = params.get("agent", [None])[0]
            audit_data = audit(days=30, agent=agent, as_json=True)
            return {"suggestions": audit_data.get("suggestions", [])}

        # ── Threads: conversation grouping ──
        elif path == "/api/threads":
            agent = params.get("agent", [None])[0]
            limit = int(params.get("limit", ["20"])[0])
            return {"threads": list_threads(agent=agent, limit=limit, as_json=True)}

        elif path.startswith("/api/thread/"):
            thread_id = path.replace("/api/thread/", "")
            return {"thread_id": thread_id, "records": get_thread(thread_id, as_json=True)}

        # ── Agents: list all agents with stats ──
        elif path == "/api/agents":
            agents = list_agents(as_json=True)
            # Inject friendly names
            for a in agents:
                did = a.get("agent", "")
                name = a.get("agent_name", "")
                if name and name != did:
                    a["agent_did"] = did
                    a["agent"] = name
                a["is_subagent"] = "/subagent" in (a.get("agent_name") or "") or "/sub" in (a.get("agent_name") or "")

            # Merge subagent counts into main agents and filter
            sub_counts = {}
            for a in agents:
                if a.get("is_subagent"):
                    # "foo/subagent" → main = "foo"
                    main_name = (a.get("agent_name") or "").split("/")[0]
                    sub_counts[main_name] = sub_counts.get(main_name, 0) + a.get("total_records", 0)
            for a in agents:
                name = a.get("agent_name") or ""
                if name in sub_counts:
                    a["subagent_records"] = sub_counts[name]

            # Filter: hide subagents from main list (they're shown under main agent)
            show_sub = params.get("show_subagents", [""])[0] == "1"
            if not show_sub:
                agents = [a for a in agents if not a.get("is_subagent")]
            # Compute per-agent Trust Score — cached for 60 s. Without the
            # cache this block used to load every record from disk and run
            # a per-agent O(N·M) filter, adding 500-2000 ms per request.
            try:
                trust_map = _get_cached_trust_scores()
                for a in agents:
                    a["trust_score"] = trust_map.get(a.get("agent", ""))
            except Exception:
                for a in agents:
                    a["trust_score"] = None
            return {"agents": agents, "count": len(agents)}

        # ── Vault: raw input/output for a record ──
        if path.startswith("/api/vault/"):
            record_id = path.split("/api/vault/")[1]
            if not record_id:
                return {"error": "record_id required"}
            from .storage import ECP_DIR
            vault_file = ECP_DIR / "vault" / f"{record_id}.json"
            if not vault_file.exists():
                return {
                    "error": f"Vault file not found for {record_id}",
                    "hint": "Raw content is only stored when using wrap() or record(). Callback adapters may not store vault data.",
                    "vault_path": str(vault_file),
                }
            try:
                vault_data = json.loads(vault_file.read_text())
            except Exception as exc:
                return {"error": f"Failed to read vault: {exc}"}
            # Truncate very long content for display — but preserve JSON structure
            for key in ("input", "output"):
                val = vault_data.get(key, "")
                if isinstance(val, str) and len(val) > 50000:
                    # Only truncate extremely large content; preserve JSON-parseable data
                    vault_data[key] = val[:50000] + f"\n\n... (truncated, full content: {len(val)} chars)"
            vault_data["_vault_path"] = str(vault_file)
            vault_data["_ecp_dir"] = str(ECP_DIR)
            return vault_data

        # ── Guide: onboarding info for new users ──
        if path == "/api/guide":
            from .storage import ECP_DIR, RECORDS_DIR, VAULT_DIR
            from .identity import get_or_create_identity
            try:
                identity = get_or_create_identity()
                did = identity.get("did", "unknown")
            except Exception:
                did = "not initialized"
            record_files = sorted(RECORDS_DIR.glob("*.jsonl")) if RECORDS_DIR.exists() else []
            vault_count = len(list(VAULT_DIR.iterdir())) if VAULT_DIR.exists() else 0
            return {
                "welcome": "Welcome to ATLAST ECP Dashboard — your AI agent's evidence chain viewer.",
                "what_is_this": "Every time your AI agent makes an LLM call, ECP records a tamper-proof evidence trail locally on your machine.",
                "your_agent": {
                    "did": did,
                    "explanation": "This is your agent's unique identity (DID). All evidence records are tied to this ID."
                },
                "your_data": {
                    "ecp_dir": str(ECP_DIR),
                    "records_dir": str(RECORDS_DIR),
                    "vault_dir": str(VAULT_DIR),
                    "record_files": [str(f) for f in record_files],
                    "vault_files_count": vault_count,
                    "explanation": "Records contain hashed metadata (no raw content). Vault stores the original input/output locally."
                },
                "privacy": "All data stays on your machine. The vault (raw AI conversations) never leaves your device unless you explicitly push."
            }

        if path == "/api/search":
            query = params.get("q", [""])[0]
            limit = int(params.get("limit", ["20"])[0])
            errors_only = params.get("errors", [""])[0] == "1"
            infra_only = params.get("infra", [""])[0] == "1"  # noqa: F841
            agent = params.get("agent", [None])[0]
            if agent:
                agent = self._resolve_agent_name(agent)
            since = params.get("since", [None])[0]
            until = params.get("until", [None])[0]
            results = search(query, limit=limit, agent=agent, since=since,
                             until=until, errors_only=errors_only, as_json=True)
            return {"records": results, "total": len(results)}

        elif path == "/api/trace":
            record_id = params.get("id", [""])[0]
            direction = params.get("dir", ["back"])[0]
            if not record_id:
                return {"error": "id parameter required"}
            chain = trace(record_id, direction=direction, as_json=True)
            return {"chain": chain, "depth": len(chain)}

        elif path == "/api/audit":
            days = int(params.get("days", ["30"])[0])
            agent = params.get("agent", [None])[0]
            return audit(days=days, agent=agent, as_json=True)

        elif path == "/api/timeline":
            days = int(params.get("days", ["30"])[0])
            agent = params.get("agent", [None])[0]
            results = timeline(days=days, agent=agent, as_json=True)
            return {"timeline": results}

        elif path == "/api/index":
            count = rebuild_index()
            return {"indexed": count}

        elif path == "/api/version":
            # Check current vs latest version on PyPI
            try:
                from . import __version__ as current
            except Exception:
                current = "?"
            latest = current
            update_available = False
            try:
                import urllib.request as _ur
                resp = _ur.urlopen("https://pypi.org/pypi/atlast-ecp/json", timeout=5)
                import json as _json
                pypi = _json.loads(resp.read())
                latest = pypi.get("info", {}).get("version", current)
                if latest != current:
                    update_available = True
            except Exception:
                pass
            return {
                "current": current,
                "latest": latest,
                "update_available": update_available,
                "update_command": "pip3 install --upgrade atlast-ecp",
            }

        elif path == "/api/stats":
            agent = params.get("agent", [None])[0]
            return self._get_stats(agent=agent)

        elif path == "/api/overview":
            """High-level dashboard overview with all key metrics."""
            agent = params.get("agent", [None])[0]
            stats = self._get_stats(agent=agent)
            timeline_data = timeline(days=30, agent=agent, as_json=True)
            agents = list_agents(as_json=True)
            audit_data = audit(days=30, agent=agent, as_json=True)

            # Compute cost estimation (approximate pricing per model)
            # Approximate pricing per model (for cost estimation)
            # MODEL_PRICING kept as reference for future per-model breakdown
            total_cost = 0.0
            for a in agents:
                ti = a.get("tokens_in", 0)
                to_ = a.get("tokens_out", 0)
                # Use default pricing
                total_cost += (ti / 1_000_000 * 3.0) + (to_ / 1_000_000 * 15.0)

            return {
                "stats": stats,
                "timeline": timeline_data,
                "agents": agents,
                "audit_health": audit_data.get("health", "unknown"),
                "audit_anomalies": len(audit_data.get("anomalies", [])),
                "estimated_cost_usd": round(total_cost, 4),
            }

        elif path == "/api/scores":
            """Trust Score (0-1000) per agent. ?agent=name for specific agent."""
            try:
                from .scoring_rules import classify_records, compute_trust_score_v2
                from .signals import compute_trust_signals
                from .query import _ensure_index as _sei3, _get_db as _gdb3
                _sei3()
                db_sc = _gdb3()
                agent = params.get("agent", [None])[0]
                if agent:
                    agent = self._resolve_agent_name(agent)
                conds = ["1=1"]
                p_sc = []
                if agent:
                    conds.append("agent = ?")
                    p_sc.append(agent)
                rows_sc = db_sc.execute(
                    "SELECT id, agent, ts, model, latency_ms, flags, error, is_infra, "
                    "tokens_in, tokens_out, input_preview, output_preview, chain_hash, chain_prev "
                    "FROM records WHERE %s ORDER BY ts DESC LIMIT 2000" % " AND ".join(conds), p_sc
                ).fetchall()
                db_sc.close()
                records_all = [{
                    "id": r[0], "agent": r[1], "ts": r[2], "model": r[3],
                    "latency_ms": r[4], "flags": r[5], "error": r[6], "is_infra": r[7],
                    "tokens_in": r[8], "tokens_out": r[9], "input_preview": r[10],
                    "output_preview": r[11], "chain_hash": r[12], "chain_prev": r[13],
                } for r in rows_sc]
                classified = classify_records(records_all)
                trust_signals = compute_trust_signals(records_all)
                chain_integrity = trust_signals.get("chain_integrity", 1.0)
                result = compute_trust_score_v2(classified, chain_integrity=chain_integrity)
                from collections import Counter
                labels = Counter(r.get("classification", "unknown") for r in classified)
                result["classification_breakdown"] = dict(labels)
                result["agent"] = agent or "all"
                return result
            except Exception as e:
                return {"error": str(e)}

        elif path == "/api/records":
            """Paginated records list with filtering."""
            agent = params.get("agent", [None])[0]
            if agent:
                agent = self._resolve_agent_name(agent)
            limit = int(params.get("limit", ["50"])[0])
            offset = int(params.get("offset", ["0"])[0])
            since = params.get("since", [None])[0]
            until = params.get("until", [None])[0]
            exclude_infra = params.get("exclude_infra", [""])[0] == "1"

            from .query import _ensure_index, _get_db
            _ensure_index()
            db = _get_db()
            conditions = []
            p = []
            if agent:
                conditions.append("agent = ?")
                p.append(agent)
            if since:
                conditions.append("date >= ?")
                p.append(since)
            if until:
                conditions.append("date <= ?")
                p.append(until)
            if exclude_infra:
                conditions.append("is_infra = 0")
            where = "WHERE " + " AND ".join(conditions) if conditions else ""

            total_count = db.execute(f"SELECT COUNT(*) FROM records {where}", p).fetchone()[0]
            rows = db.execute(
                f"SELECT * FROM records {where} ORDER BY ts DESC LIMIT ? OFFSET ?",
                p + [limit, offset]
            ).fetchall()
            db.close()
            return {
                "records": [dict(r) for r in rows],
                "total": total_count,
                "limit": limit,
                "offset": offset,
            }

        elif path == "/api/models":
            """Model usage breakdown."""
            agent = params.get("agent", [None])[0]
            from .query import _ensure_index, _get_db
            _ensure_index()
            db = _get_db()
            cond = "WHERE is_infra = 0"
            p = []
            if agent:
                cond += " AND agent = ?"
                p.append(agent)
            rows = db.execute(f"""
                SELECT model,
                       COUNT(*) as count,
                       AVG(latency_ms) as avg_latency,
                       SUM(tokens_in) as tokens_in,
                       SUM(tokens_out) as tokens_out
                FROM records {cond}
                GROUP BY model ORDER BY count DESC
            """, p).fetchall()
            db.close()
            return {"models": [dict(r) for r in rows]}

        elif path == "/api/tools":
            """Tool usage analysis from output content."""
            agent = params.get("agent", [None])[0]
            from .query import _ensure_index, _get_db
            _ensure_index()
            db = _get_db()
            cond = "WHERE is_infra = 0 AND output_preview LIKE '%tools:%'"
            p = []
            if agent:
                cond += " AND agent = ?"
                p.append(agent)
            rows = db.execute(f"""
                SELECT output_preview FROM records {cond}
            """, p).fetchall()
            db.close()

            # Parse tool names from output previews
            from collections import Counter
            tool_counter = Counter()
            for row in rows:
                preview = row[0] or ""
                import re
                match = re.search(r'\[tools:\s*([^\]]+)\]', preview)
                if match:
                    tools = [t.strip() for t in match.group(1).split(",")]
                    for t in tools:
                        if t:
                            tool_counter[t] += 1
            return {"tools": [{"name": k, "count": v} for k, v in tool_counter.most_common(50)]}

        elif path == "/api/flags":
            """Flag distribution analysis."""
            agent = params.get("agent", [None])[0]
            from .query import _ensure_index, _get_db
            _ensure_index()
            db = _get_db()
            cond = "WHERE is_infra = 0"
            p = []
            if agent:
                cond += " AND agent = ?"
                p.append(agent)
            rows = db.execute(f"SELECT flags FROM records {cond}", p).fetchall()
            db.close()
            from collections import Counter
            flag_counter = Counter()
            total = 0
            for row in rows:
                total += 1
                flags = json.loads(row[0] or "[]")
                for f in flags:
                    flag_counter[f] += 1
            return {
                "flags": [{"name": k, "count": v, "rate": round(v/total*100, 1) if total else 0}
                         for k, v in flag_counter.most_common()],
                "total_records": total,
            }

        elif path == "/api/sessions":
            """Session breakdown."""
            agent = params.get("agent", [None])[0]
            from .query import _ensure_index, _get_db
            _ensure_index()
            db = _get_db()
            cond = "WHERE is_infra = 0 AND session_id != ''"
            p = []
            if agent:
                cond += " AND agent = ?"
                p.append(agent)
            rows = db.execute(f"""
                SELECT session_id,
                       COUNT(*) as count,
                       MIN(ts) as first_ts,
                       MAX(ts) as last_ts,
                       AVG(latency_ms) as avg_latency,
                       SUM(tokens_in) as tokens_in,
                       SUM(tokens_out) as tokens_out
                FROM records {cond}
                GROUP BY session_id ORDER BY last_ts DESC LIMIT 50
            """, p).fetchall()
            db.close()
            return {"sessions": [dict(r) for r in rows]}

        elif path == "/api/hourly":
            """Hourly activity heatmap data."""
            agent = params.get("agent", [None])[0]
            days = int(params.get("days", ["30"])[0])
            from .query import _ensure_index, _get_db
            _ensure_index()
            db = _get_db()
            since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
            cond = "WHERE is_infra = 0 AND date >= ?"
            p = [since]
            if agent:
                cond += " AND agent = ?"
                p.append(agent)
            rows = db.execute(f"""
                SELECT ts FROM records {cond}
            """, p).fetchall()
            db.close()
            # Build hourly heatmap: day_of_week x hour
            heatmap = [[0]*24 for _ in range(7)]
            for row in rows:
                ts = row[0]
                if ts:
                    dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                    heatmap[dt.weekday()][dt.hour] += 1
            return {"heatmap": heatmap, "days": ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]}

        return {"error": f"Unknown API: {path}"}

    def _get_stats(self, agent: "str | None" = None) -> dict:
        """Comprehensive stats with proper infra/agent separation."""
        from .storage import ECP_DIR, RECORDS_DIR, VAULT_DIR
        from .identity import get_or_create_identity
        from .query import _ensure_index, _get_db

        try:
            identity = get_or_create_identity()
            did = identity.get("did", "unknown")
        except Exception:
            did = "not initialized"

        _ensure_index()
        db = _get_db()

        cond = ""
        p = []
        if agent:
            cond = "WHERE agent = ?"
            p = [agent]

        # Core metrics
        row = db.execute(f"""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN is_infra = 0 THEN 1 ELSE 0 END) as interactions,
                   SUM(CASE WHEN error = 1 AND is_infra = 0 THEN 1 ELSE 0 END) as agent_errors,
                   SUM(CASE WHEN is_infra = 1 THEN 1 ELSE 0 END) as infra_errors,
                   AVG(CASE WHEN is_infra = 0 THEN latency_ms END) as avg_latency,
                   SUM(tokens_in) as tokens_in,
                   SUM(tokens_out) as tokens_out,
                   MIN(date) as first_date,
                   MAX(date) as last_date,
                   COUNT(DISTINCT date) as active_days,
                   COUNT(DISTINCT session_id) as sessions,
                   COUNT(DISTINCT model) as models_used
            FROM records {cond}
        """, p).fetchone()

        total = row[0] or 0
        interactions = row[1] or 0
        agent_errors = row[2] or 0
        infra_errors = row[3] or 0
        tokens_in = row[5] or 0
        tokens_out = row[6] or 0

        # Chain integrity check
        chain_ok = True
        chain_records = db.execute(f"""
            SELECT id, chain_prev, chain_hash FROM records
            {cond} {'AND' if cond else 'WHERE'} chain_prev != ''
            ORDER BY ts
        """.replace("WHERE AND", "WHERE"), p).fetchall()
        if chain_records:
            id_set = set(r[0] for r in chain_records)
            hash_set = set(r[2] for r in chain_records if r[2])
            broken = sum(1 for r in chain_records if r[1] != "genesis" and r[1] not in id_set and r[1] not in hash_set)
            chain_ok = broken == 0

        db.close()

        vault_count = 0
        if VAULT_DIR.exists():
            vault_count = len(list(VAULT_DIR.iterdir()))

        record_files = sorted(RECORDS_DIR.glob("*.jsonl")) if RECORDS_DIR.exists() else []

        reliability = round((interactions - agent_errors) / interactions, 4) if interactions else 1.0
        availability = round(interactions / total, 4) if total else 1.0

        return {
            "total_records": total,
            "total_interactions": interactions,
            "agent_errors": agent_errors,
            "infra_errors": infra_errors,
            "reliability": reliability,
            "availability": availability,
            "chain_integrity": 1.0 if chain_ok else 0.0,
            "avg_latency_ms": round(row[4] or 0),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "estimated_cost_usd": round((tokens_in / 1_000_000 * 3.0) + (tokens_out / 1_000_000 * 15.0), 4),
            "first_date": row[7],
            "last_date": row[8],
            "active_days": row[9] or 0,
            "sessions": row[10] or 0,
            "models_used": row[11] or 0,
            "agent_did": did,
            "ecp_dir": str(ECP_DIR),
            "vault_count": vault_count,
            "record_files": [f.name for f in record_files],
            "has_vault": vault_count > 0,
        }

    def _json_response(self, status: int, data: dict):
        body = json.dumps(data, default=str, ensure_ascii=False).encode("utf-8")
        self._send_body(status, body, "application/json; charset=utf-8")

    def _send_body(self, status: int, body: bytes, content_type: str):
        """Send a response body, gzipping when the client accepts it and the
        payload is large enough to benefit (skip tiny bodies — gzip overhead
        costs more than it saves)."""
        accept_enc = (self.headers.get("Accept-Encoding") or "").lower()
        use_gzip = "gzip" in accept_enc and len(body) >= 1024
        if use_gzip:
            import gzip as _gz
            body = _gz.compress(body, compresslevel=5)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        if use_gzip:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _get_enhancement_script() -> str:
    """Return the JS/CSS enhancement script injected into index.html."""
    return '''<style>
/* === ATLAST Dashboard Enhancements === */
#atlast-guide-banner {
  position: fixed; top: 0; left: 0; right: 0; z-index: 9999;
  background: linear-gradient(135deg, #1e40af 0%, #7c3aed 100%);
  color: white; padding: 10px 20px; font-family: system-ui, sans-serif;
  display: flex; align-items: center; justify-content: space-between;
  font-size: 14px; box-shadow: 0 2px 8px rgba(0,0,0,0.2);
}
#atlast-guide-banner a { color: #93c5fd; text-decoration: underline; cursor: pointer; }
#atlast-guide-banner .close-btn {
  background: rgba(255,255,255,0.2); border: none; color: white;
  padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 13px;
}
#atlast-guide-banner .close-btn:hover { background: rgba(255,255,255,0.3); }
body { padding-top: 44px !important; }
body.guide-dismissed { padding-top: 0 !important; }

/* Vault overlay */
#atlast-vault-overlay {
  display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.6); z-index: 10000;
  justify-content: center; align-items: center;
}
#atlast-vault-overlay.visible { display: flex; }
#atlast-vault-panel {
  background: white; border-radius: 12px; padding: 24px; max-width: 800px;
  width: 90%; max-height: 80vh; overflow-y: auto; position: relative;
  box-shadow: 0 20px 60px rgba(0,0,0,0.3); font-family: system-ui, sans-serif;
}
@media (prefers-color-scheme: dark) {
  #atlast-vault-panel { background: #1e1e2e; color: #e0e0e0; }
}
#atlast-vault-panel .vault-close {
  position: absolute; top: 12px; right: 16px; background: none;
  border: none; font-size: 24px; cursor: pointer; color: #888;
}
#atlast-vault-panel h3 { margin: 0 0 16px; font-size: 18px; color: #1e40af; }
#atlast-vault-panel .vault-section {
  margin: 12px 0; padding: 12px; border-radius: 8px;
  background: #f8fafc; border: 1px solid #e2e8f0;
}
@media (prefers-color-scheme: dark) {
  #atlast-vault-panel .vault-section { background: #2a2a3e; border-color: #3a3a5e; }
}
#atlast-vault-panel .vault-section h4 {
  margin: 0 0 8px; font-size: 13px; text-transform: uppercase;
  letter-spacing: 0.5px; color: #64748b;
}
#atlast-vault-panel .vault-content {
  white-space: pre-wrap; word-break: break-word; font-size: 14px;
  line-height: 1.6; max-height: 200px; overflow-y: auto;
}
#atlast-vault-panel .vault-path {
  font-family: monospace; font-size: 12px; color: #64748b;
  background: #f1f5f9; padding: 6px 10px; border-radius: 4px;
  margin-top: 12px; word-break: break-all;
}
@media (prefers-color-scheme: dark) {
  #atlast-vault-panel .vault-path { background: #2a2a3e; color: #94a3b8; }
}

/* Floating help button */
#atlast-help-btn {
  position: fixed; bottom: 20px; right: 20px; z-index: 9998;
  width: 48px; height: 48px; border-radius: 50%;
  background: linear-gradient(135deg, #1e40af, #7c3aed);
  color: white; border: none; font-size: 22px; cursor: pointer;
  box-shadow: 0 4px 12px rgba(0,0,0,0.2);
  display: flex; align-items: center; justify-content: center;
}
#atlast-help-btn:hover { transform: scale(1.1); }
#atlast-help-panel {
  display: none; position: fixed; bottom: 80px; right: 20px; z-index: 9998;
  background: white; border-radius: 12px; padding: 20px; width: 320px;
  box-shadow: 0 8px 30px rgba(0,0,0,0.2); font-family: system-ui, sans-serif;
}
@media (prefers-color-scheme: dark) {
  #atlast-help-panel { background: #1e1e2e; color: #e0e0e0; }
}
#atlast-help-panel.visible { display: block; }
#atlast-help-panel h4 { margin: 0 0 12px; font-size: 16px; }
#atlast-help-panel .help-item {
  padding: 8px 0; border-bottom: 1px solid #f1f5f9; font-size: 13px; line-height: 1.5;
}
#atlast-help-panel .help-item:last-child { border-bottom: none; }
#atlast-help-panel .help-item b { color: #1e40af; }

/* Vault click hint on record rows */
[data-record-id] { cursor: pointer; }
[data-record-id]:hover { background: rgba(30, 64, 175, 0.05) !important; }
</style>

<div id="atlast-guide-banner">
  <span>
    📊 <b>ATLAST ECP Dashboard</b> — Every AI agent action is recorded in a tamper-proof evidence chain.
    Your Trust Score (0-1000) shows how reliable your agent is. All data stays on your machine.
    <a id="guide-learn-more">Quick guide →</a>
  </span>
  <button class="close-btn" id="guide-dismiss">✕ Dismiss</button>
</div>

<div id="atlast-vault-overlay">
  <div id="atlast-vault-panel">
    <button class="vault-close" id="vault-close">×</button>
    <h3 id="vault-title">Loading...</h3>
    <div id="vault-body"></div>
  </div>
</div>

<button id="atlast-help-btn" title="Help & Guide">?</button>
<div id="atlast-help-panel">
  <h4>📖 Quick Guide</h4>
  <div class="help-item"><b>🏠 Overview</b> — Your agent's Trust Score (0-1000) at a glance. Higher = more reliable.</div>
  <div class="help-item"><b>📋 Records</b> — Every AI interaction with timing, model, and status. <em>Click any row to see exact input/output.</em></div>
  <div class="help-item"><b>👥 Agents</b> — Compare multiple agents' performance side by side</div>
  <div class="help-item"><b>🔗 Evidence Chain</b> — Visual proof: each record cryptographically links to the previous one</div>
  <div class="help-item"><b>📊 Audit</b> — 30-day health report with anomaly detection</div>
  <div class="help-item"><b>🔍 Search</b> — Find any record by keyword, date, or model</div>
  <div class="help-item"><b>🔐 Privacy</b> — All data stays on YOUR machine. Raw conversations never leave your device.</div>
  <div class="help-item" style="margin-top:8px; font-size:12px; color:#64748b;">
    Data dir: <code id="help-ecp-dir">~/.ecp/</code>
  </div>
</div>

<script>
(function() {
  "use strict";

  // === Guide Banner ===
  const banner = document.getElementById("atlast-guide-banner");
  const dismissed = localStorage.getItem("atlast-guide-dismissed");
  if (dismissed) {
    banner.style.display = "none";
    document.body.classList.add("guide-dismissed");
  }
  document.getElementById("guide-dismiss").onclick = function() {
    banner.style.display = "none";
    document.body.classList.add("guide-dismissed");
    localStorage.setItem("atlast-guide-dismissed", "1");
  };
  document.getElementById("guide-learn-more").onclick = function() {
    document.getElementById("atlast-help-panel").classList.toggle("visible");
  };

  // === Help Button ===
  document.getElementById("atlast-help-btn").onclick = function() {
    document.getElementById("atlast-help-panel").classList.toggle("visible");
  };

  // Fetch ECP dir for help panel
  fetch("/api/stats").then(r => r.json()).then(data => {
    if (data.ecp_dir) {
      document.getElementById("help-ecp-dir").textContent = data.ecp_dir;
    }
  }).catch(() => {});

  // === Vault Overlay ===
  const overlay = document.getElementById("atlast-vault-overlay");
  const vaultTitle = document.getElementById("vault-title");
  const vaultBody = document.getElementById("vault-body");

  document.getElementById("vault-close").onclick = closeVault;
  overlay.onclick = function(e) { if (e.target === overlay) closeVault(); };
  document.addEventListener("keydown", function(e) {
    if (e.key === "Escape") closeVault();
  });

  function closeVault() {
    overlay.classList.remove("visible");
  }

  function openVault(recordId) {
    vaultTitle.textContent = "Loading vault...";
    vaultBody.innerHTML = "";
    overlay.classList.add("visible");

    fetch("/api/vault/" + recordId)
      .then(r => r.json())
      .then(data => {
        if (data.error) {
          vaultTitle.textContent = "⚠️ Vault Not Available";
          vaultBody.innerHTML =
            '<div class="vault-section"><div class="vault-content">' +
            escapeHtml(data.error) +
            (data.hint ? "<br><br><em>" + escapeHtml(data.hint) + "</em>" : "") +
            "</div></div>" +
            (data.vault_path ? '<div class="vault-path">Expected path: ' + escapeHtml(data.vault_path) + "</div>" : "");
          return;
        }

        vaultTitle.textContent = "🔍 Record: " + recordId;

        var html = "";
        // Input section
        html += '<div class="vault-section"><h4>📥 Input (what was sent to AI)</h4>';
        html += '<div class="vault-content">' + formatVaultContent(data.input) + "</div></div>";

        // Output section
        html += '<div class="vault-section"><h4>📤 Output (AI response)</h4>';
        html += '<div class="vault-content">' + formatVaultContent(data.output) + "</div></div>";

        // Metadata (other fields)
        var metaKeys = Object.keys(data).filter(function(k) {
          return k !== "input" && k !== "output" && k !== "_vault_path" && k !== "_ecp_dir" && k !== "record_id";
        });
        if (metaKeys.length > 0) {
          html += '<div class="vault-section"><h4>📋 Metadata</h4>';
          html += '<div class="vault-content">';
          metaKeys.forEach(function(k) {
            html += "<b>" + escapeHtml(k) + ":</b> " + escapeHtml(JSON.stringify(data[k])) + "<br>";
          });
          html += "</div></div>";
        }

        // File path
        if (data._vault_path) {
          html += '<div class="vault-path">📁 Local file: ' + escapeHtml(data._vault_path) + "</div>";
        }
        if (data._ecp_dir) {
          html += '<div class="vault-path">📂 ECP directory: ' + escapeHtml(data._ecp_dir) + "</div>";
        }

        vaultBody.innerHTML = html;
      })
      .catch(function(err) {
        vaultTitle.textContent = "❌ Error";
        vaultBody.innerHTML = '<div class="vault-section"><div class="vault-content">Failed to load vault: ' + escapeHtml(String(err)) + "</div></div>";
      });
  }

  function escapeHtml(str) {
    if (str == null) return "(empty)";
    str = String(str);
    return str.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  }

  function formatVaultContent(val) {
    if (val == null) return "<em>(no content recorded)</em>";
    if (typeof val === "object") {
      try { return escapeHtml(JSON.stringify(val, null, 2)); } catch(e) {}
    }
    return escapeHtml(String(val));
  }

  // === Click Interception: watch for record IDs in the DOM ===
  // Use MutationObserver to attach click handlers to record rows
  function attachVaultClicks() {
    // Look for elements containing record IDs (rec_xxx pattern)
    document.querySelectorAll("tr, [class*='row'], [class*='card'], [class*='item']").forEach(function(el) {
      if (el._atlastBound) return;
      var text = el.textContent || "";
      var match = text.match(/\\b(rec_[a-f0-9]{16,})\\b/);
      if (match) {
        el._atlastBound = true;
        el.setAttribute("data-record-id", match[1]);
        el.title = "Click to view full AI input/output";
        el.addEventListener("click", function(e) {
          // Don't intercept clicks on links or buttons
          if (e.target.tagName === "A" || e.target.tagName === "BUTTON") return;
          e.preventDefault();
          e.stopPropagation();
          openVault(match[1]);
        });
      }
    });
  }

  // Run on load and observe DOM changes
  var observer = new MutationObserver(function() {
    setTimeout(attachVaultClicks, 100);
  });
  observer.observe(document.body, { childList: true, subtree: true });
  setTimeout(attachVaultClicks, 500);
  setTimeout(attachVaultClicks, 2000);

  // Also make window.openVault available for manual use
  window.atlastOpenVault = openVault;

  console.log("[ATLAST] Dashboard enhancements loaded. Click any record to view vault content.");
})();
</script>'''


def start_dashboard(port: int = DEFAULT_PORT, open_browser: bool = True, host: str = "127.0.0.1"):
    """Start the local dashboard server."""
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    # Make worker threads daemonic so Ctrl-C stops them with the main thread
    server.daemon_threads = True
    url = f"http://{host}:{port}"

    print("\n  📊 ATLAST ECP Dashboard")
    print(f"  Running at: {url}")
    print("  Data: ~/.ecp/ (local only, nothing leaves your machine)")
    print("  Press Ctrl+C to stop\n")

    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Dashboard stopped.")
        server.server_close()
