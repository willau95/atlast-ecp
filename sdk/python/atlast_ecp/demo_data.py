"""
Generate realistic demo data for ATLAST ECP.

Two real-world scenarios:

Scenario A — "Research Agent" (did:ecp:demo_research_agent)
  A market research agent analyzing semiconductor trends.
  Day 1-25: Normal operation, high confidence, low errors.
  Day 26-30: Data source starts returning stale data → confidence drifts down.
  Day 31-34: API key expires → error spike (40%+ errors).
  Day 35-37: Key rotated, recovery.
  Day 38-60: Back to normal.

Scenario B — "Code Review Agent" (did:ecp:demo_code_review_agent)
  A code review agent that checks PRs for bugs.
  Day 1-20: Normal operation.
  Day 21-25: Model switched gpt-4o → gpt-4o-mini → latency drops but confidence tanks.
  Day 26-30: Reverted to gpt-4o, back to normal.
  Day 31-60: Stable, occasional errors from complex PRs.

Both agents produce FULL vault content (input + output) for every single record.
Chain linking is correct: each record's chain.prev = previous record's id.
"""

import json
import hashlib
import random
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .storage import ECP_DIR, RECORDS_DIR, VAULT_DIR, init_storage


def _sha256(data: str) -> str:
    return "sha256:" + hashlib.sha256(data.encode()).hexdigest()


def _rid() -> str:
    return f"rec_{uuid.uuid4().hex[:16]}"


# ─── Scenario A: Research Agent ─────────────────────────────────────────────

RESEARCH_AGENT = "did:ecp:demo_research_agent"

# Coherent task sequences — each is a "session" (a day's work)
RESEARCH_SESSIONS = [
    # Normal research day
    [
        {"action": "web_search", "type": "tool_call", "model": "gpt-4o",
         "input": "Search: Q4 2025 global semiconductor revenue reports",
         "output": "Found 8 results. Top: SIA reports global semiconductor sales reached $167B in Q4 2025, up 23% YoY. TSMC revenue $25.1B, Samsung $18.3B."},
        {"action": "data_query", "type": "tool_call", "model": "gpt-4o",
         "input": "Query: SELECT company, revenue_q4, yoy_growth FROM semiconductor_companies WHERE year=2025 ORDER BY revenue DESC LIMIT 10",
         "output": "10 rows returned. TSMC: $25.1B (+28%), Samsung: $18.3B (+19%), Intel: $14.2B (+5%), SK Hynix: $13.8B (+42%), Broadcom: $10.1B..."},
        {"action": "trend_analysis", "type": "llm_call", "model": "gpt-4o",
         "input": "Analyze the semiconductor revenue trend from the collected Q4 2025 data. Focus on: (1) YoY growth drivers, (2) market concentration, (3) AI chip segment share.",
         "output": "Analysis complete.\n\n1. YoY Growth: +23% driven primarily by AI accelerator demand (HBM, GPU). Memory sector recovered strongly (+35% YoY) after 2024 downturn.\n2. Market Concentration: Top 5 companies hold 62% of revenue, up from 58% in Q3. TSMC alone commands 15%.\n3. AI Chip Segment: Estimated 28% of total semiconductor revenue, up from 19% in Q4 2024. NVIDIA H200/B200 and AMD MI300X are primary drivers.\n\nRisk: Overcapacity signals in mature nodes (28nm+). Leading-edge (3nm, 2nm) remains supply-constrained."},
        {"action": "draft_report", "type": "llm_call", "model": "gpt-4o",
         "input": "Draft the Executive Summary section for the Q4 2025 Semiconductor Market Report based on analysis results.",
         "output": "## Executive Summary\n\nThe global semiconductor market achieved record Q4 2025 revenues of $167B, representing 23% year-over-year growth. This expansion was driven by three key factors:\n\n1. **AI Infrastructure Build-out**: Data center GPU and accelerator spending surged 47%, with NVIDIA and AMD capturing the majority of growth.\n2. **Memory Recovery**: DRAM and NAND prices stabilized, driving memory segment revenue up 35% as hyperscalers expanded capacity.\n3. **Automotive Semiconductor Growth**: EV adoption drove 18% growth in automotive chips, particularly power semiconductors and ADAS processors.\n\nHowever, warning signs emerged: mature-node utilization rates dropped to 72% (from 85% in Q3), suggesting potential overcapacity in consumer electronics segments."},
        {"action": "fact_check", "type": "llm_call", "model": "gpt-4o",
         "input": "Verify: 'TSMC Q4 2025 revenue $25.1B' against official sources",
         "output": "✅ VERIFIED. TSMC Monthly Revenue Report (Jan 10, 2026): NT$786.1B for Q4 2025. At avg exchange rate NT$31.3/USD = $25.11B. Matches our figure."},
    ],
    # Another normal day — different topic
    [
        {"action": "arxiv_search", "type": "tool_call", "model": "gpt-4o",
         "input": "Search arXiv: latest papers on AI agent frameworks and multi-agent systems, published after 2025-10-01",
         "output": "Found 23 results. Top papers:\n1. 'AgentBench 2.0: Evaluating LLM Agents at Scale' (2025-11-15)\n2. 'Cooperative Multi-Agent Planning with Shared Memory' (2025-12-03)\n3. 'Safety Boundaries for Autonomous AI Agents' (2025-11-28)"},
        {"action": "summarize", "type": "llm_call", "model": "gpt-4o",
         "input": "Summarize the top 3 arXiv papers found on AI agent frameworks. Extract: key contribution, methodology, results, limitations.",
         "output": "Paper Summaries:\n\n**1. AgentBench 2.0** — Introduces 15 new benchmarks for LLM agents across code, web, and tool-use. Key finding: GPT-4o scores 78.3% (up from 64% in v1.0), Claude scores 76.1%. Gap between frontier and mid-tier models widening.\n\n**2. Cooperative Multi-Agent Planning** — Proposes SharedMem architecture where agents share a structured memory pool. Results: 34% better task completion on collaborative tasks vs independent agents. Limitation: Scaling beyond 8 agents causes memory contention.\n\n**3. Safety Boundaries** — Formal framework for defining and enforcing agent safety constraints. Uses constitutional AI approach with runtime monitoring. Reduced harmful actions by 91% with only 3% task performance degradation."},
        {"action": "compare_data", "type": "llm_call", "model": "gpt-4o",
         "input": "Compare the AgentBench 2.0 results with our internal agent performance data. How does our research agent stack up?",
         "output": "Comparison:\n- AgentBench 2.0 tool-use average: 72.5% accuracy\n- Our research agent (last 30 days): 89.3% task completion, 0.84 avg confidence\n- Our agent outperforms benchmark in structured research tasks but has no data for web navigation or code generation benchmarks.\n- Note: AgentBench measures accuracy; our ECP measures confidence+error rate — not directly comparable but directionally positive."},
    ],
    # Day with quality check
    [
        {"action": "news_fetch", "type": "tool_call", "model": "gpt-4o",
         "input": "Fetch latest news: NVIDIA earnings report January 2026",
         "output": "Retrieved 5 articles:\n1. Reuters: 'NVIDIA Q4 FY2026 Revenue $42.3B, Beats Estimates' (2026-01-15)\n2. Bloomberg: 'NVIDIA Blackwell GPU Demand Exceeds Supply Through 2026' (2026-01-15)\n3. WSJ: 'AI Chip Race Intensifies as NVIDIA Posts Record Quarter' (2026-01-16)"},
        {"action": "summarize", "type": "llm_call", "model": "gpt-4o",
         "input": "Summarize NVIDIA's Q4 FY2026 earnings results. Key metrics: revenue, data center segment, gross margin, guidance.",
         "output": "NVIDIA Q4 FY2026 Highlights:\n- Revenue: $42.3B (+78% YoY), beat consensus $40.1B\n- Data Center: $36.8B (+92% YoY), 87% of total revenue\n- Gross Margin: 73.5% (down from 75.2% in Q3 due to Blackwell ramp costs)\n- Q1 FY2027 Guidance: $43-45B (street expected $41B)\n- Blackwell shipments exceeded 200K units in Q4\n- Jensen Huang: 'The next industrial revolution has begun'"},
        {"action": "cross_reference", "type": "llm_call", "model": "gpt-4o",
         "input": "Cross-reference NVIDIA's $42.3B revenue claim with SEC filing and analyst estimates",
         "output": "✅ Revenue $42.3B confirmed in 10-Q filing (SEC EDGAR, filed 2026-01-14). Analyst consensus was $40.1B (range $38.5-$41.8B). Beat by 5.5%. Revenue figure is internally consistent across press release, 10-Q, and earnings call transcript."},
        {"action": "quality_score", "type": "llm_call", "model": "gpt-4o",
         "input": "Score the quality and reliability of today's research output on NVIDIA earnings",
         "output": "Quality Assessment:\n- Data freshness: 10/10 (same-day earnings data)\n- Source reliability: 9/10 (Reuters, Bloomberg, SEC filing)\n- Cross-validation: 9/10 (3 independent sources confirm)\n- Completeness: 8/10 (missing: segment breakdown beyond data center, CapEx details)\n- Overall: 9.0/10\n\nRecommendation: High confidence in core figures. Suggest adding segment detail in next iteration."},
    ],
]

# Drift day — data source returning stale info
RESEARCH_DRIFT_STEPS = [
    {"action": "web_search", "type": "tool_call", "model": "gpt-4o",
     "input": "Search: latest AI chip market share data February 2026",
     "output": "Found 6 results, but top 3 are from October 2025. Data source may be returning cached/stale results. Proceeding with available data."},
    {"action": "data_query", "type": "tool_call", "model": "gpt-4o",
     "input": "Query: SELECT * FROM market_data WHERE date > '2026-01-01'",
     "output": "WARNING: Only 2 rows returned (expected ~30). Data ingestion pipeline may be stalled. Last entry date: 2026-01-15."},
    {"action": "trend_analysis", "type": "llm_call", "model": "gpt-4o",
     "input": "Analyze AI chip market trends for February 2026 using available data",
     "output": "⚠️ LOW CONFIDENCE: Analysis based on incomplete data (Jan 2026 only, Feb data missing). With available data: market share appears stable — NVIDIA 82%, AMD 12%, others 6%. However, this may not reflect recent developments. Flagging for human review."},
    {"action": "draft_report", "type": "llm_call", "model": "gpt-4o",
     "input": "Draft market update section noting data limitations",
     "output": "## February 2026 Market Update (PRELIMINARY)\n\n⚠️ **Data Quality Notice**: This update is based on incomplete data. Our primary data feed has not been updated since January 15, 2026. Figures below should be treated as estimates.\n\nBased on available data, the AI accelerator market..."},
]

# Error spike day — API key expired
RESEARCH_ERROR_STEPS = [
    {"action": "web_search", "type": "tool_call", "model": "gpt-4o",
     "input": "Search: semiconductor industry news March 2026",
     "output": "ERROR: HTTP 401 Unauthorized — API key expired. SerpAPI returned: 'Invalid API key. Please renew your subscription.' Falling back to cached results from 2026-02-28.",
     "error": True},
    {"action": "data_query", "type": "tool_call", "model": "gpt-4o",
     "input": "Query: SELECT * FROM market_data WHERE date > '2026-02-01'",
     "output": "ERROR: Connection refused — data provider endpoint returned HTTP 403. Account suspended due to expired billing. 0 rows returned.",
     "error": True},
    {"action": "trend_analysis", "type": "llm_call", "model": "gpt-4o",
     "input": "Attempt trend analysis with whatever data is available",
     "output": "ERROR: Cannot perform meaningful trend analysis. Both primary (SerpAPI) and secondary (market data DB) sources are unavailable. Last reliable data point: 2026-01-15. Aborting analysis — output would be unreliable.",
     "error": True},
    {"action": "summarize", "type": "llm_call", "model": "gpt-4o",
     "input": "Generate status report explaining data access failures",
     "output": "Status Report — Data Access Failure\n\nMultiple data sources are currently inaccessible:\n1. SerpAPI: 401 Unauthorized (API key expired)\n2. Market Data DB: 403 Forbidden (billing issue)\n\nImpact: Cannot produce reliable market analysis. All outputs since 2026-02-26 should be treated as low-confidence.\n\nRecommended Action: Renew API keys and restore database access immediately."},
]

# Recovery day
RESEARCH_RECOVERY_STEPS = [
    {"action": "web_search", "type": "tool_call", "model": "gpt-4o",
     "input": "Search: semiconductor market news March 2026 (testing restored API access)",
     "output": "✅ API access restored. Found 15 results. Top: 'Global Chip Sales Hit $180B in Q1 2026' (SIA, 2026-03-10). Data feeds operational."},
    {"action": "data_query", "type": "tool_call", "model": "gpt-4o",
     "input": "Query: SELECT COUNT(*) FROM market_data WHERE date > '2026-02-01'",
     "output": "47 rows returned. Data pipeline backfill complete — all missing February+March data now ingested. Latest entry: 2026-03-12."},
    {"action": "trend_analysis", "type": "llm_call", "model": "gpt-4o",
     "input": "Re-run trend analysis for Feb-March 2026 with restored data. Flag any discrepancies with estimates made during outage period.",
     "output": "Analysis complete with full dataset.\n\nKey findings:\n1. Market grew 8% in Feb (vs our outage-period estimate of 'flat') — we were wrong during the data gap\n2. AMD gained 2% market share due to MI350 launch (missed entirely during outage)\n3. Memory prices rose 12% (not captured in stale data)\n\nDiscrepancy alert: 4 reports generated during Feb 26 - Mar 5 used stale data and should be flagged as unreliable."},
    {"action": "quality_score", "type": "llm_call", "model": "gpt-4o",
     "input": "Assess data quality and completeness after recovery",
     "output": "Recovery Assessment:\n- Data freshness: 9/10 (backfill complete, latest=today)\n- Source reliability: 10/10 (all API keys renewed, connections verified)\n- Historical gap: Feb 26 - Mar 5 (8 days of degraded output)\n- Records affected: ~32 records should be marked low-confidence\n- Current status: FULLY OPERATIONAL\n\nRecommendation: Re-run all analyses from the gap period. Mark affected records in ECP."},
]


# ─── Scenario B: Code Review Agent ──────────────────────────────────────────

CODE_AGENT = "did:ecp:demo_code_review_agent"

CODE_SESSIONS_NORMAL = [
    [
        {"action": "fetch_pr", "type": "tool_call", "model": "gpt-4o",
         "input": "Fetch PR #482: 'Add user authentication middleware' — 12 files changed, +340 -89 lines",
         "output": "PR #482 loaded. Files: auth_middleware.py, routes/login.py, routes/register.py, models/user.py, tests/test_auth.py, + 7 config files. Languages: Python (92%), YAML (8%)."},
        {"action": "analyze_code", "type": "llm_call", "model": "gpt-4o",
         "input": "Review auth_middleware.py for security vulnerabilities. Check: SQL injection, XSS, CSRF, improper auth, secrets in code.",
         "output": "Security Review — auth_middleware.py:\n\n🔴 CRITICAL (1):\n- Line 45: `db.execute(f\"SELECT * FROM users WHERE token='{token}'\")` — SQL injection vulnerability. Token is user-supplied and not parameterized.\n\n🟡 WARNING (2):\n- Line 23: JWT secret loaded from environment variable but no fallback validation. If env var missing, secret defaults to empty string.\n- Line 67: Session timeout set to 30 days — unusually long, recommend 24h with refresh token.\n\n✅ GOOD:\n- CSRF protection properly implemented via double-submit cookie pattern\n- Password hashing uses bcrypt with cost=12"},
        {"action": "analyze_code", "type": "llm_call", "model": "gpt-4o",
         "input": "Review tests/test_auth.py — check test coverage completeness for the authentication flow",
         "output": "Test Coverage Review — test_auth.py:\n\n- Login success: ✅ covered\n- Login wrong password: ✅ covered\n- Login nonexistent user: ✅ covered\n- Token refresh: ✅ covered\n- Token expiry: ❌ NOT covered — no test for expired token behavior\n- SQL injection attempt: ❌ NOT covered — no security test\n- Rate limiting: ❌ NOT covered\n- Concurrent sessions: ❌ NOT covered\n\nCoverage: 4/8 critical paths tested (50%). Recommend adding at minimum: token expiry and SQL injection tests before merge."},
        {"action": "generate_review", "type": "llm_call", "model": "gpt-4o",
         "input": "Generate PR review comment for PR #482 with findings",
         "output": "## PR Review: #482 — Add user authentication middleware\n\n**Verdict: 🔴 Request Changes**\n\n### Critical\n1. **SQL Injection in auth_middleware.py:45** — `f-string` query with user-supplied token. Must use parameterized query: `db.execute('SELECT * FROM users WHERE token=?', (token,))`\n\n### Warnings\n2. JWT secret fallback to empty string when env var missing\n3. 30-day session timeout should be reduced\n\n### Missing Tests\n4. No test for expired token handling\n5. No SQL injection security test\n\n### Positive\n- Clean code structure\n- Good CSRF protection\n- Proper bcrypt usage\n\n**Blocking on #1 — SQL injection must be fixed before merge.**"},
    ],
    [
        {"action": "fetch_pr", "type": "tool_call", "model": "gpt-4o",
         "input": "Fetch PR #491: 'Refactor database connection pooling' — 6 files changed, +156 -203 lines",
         "output": "PR #491 loaded. Files: db/pool.py, db/connection.py, db/config.py, tests/test_pool.py, tests/test_connection.py, docs/database.md. Net reduction: -47 lines (cleanup)."},
        {"action": "analyze_code", "type": "llm_call", "model": "gpt-4o",
         "input": "Review db/pool.py for performance issues: connection leaks, pool sizing, timeout handling, thread safety",
         "output": "Performance Review — db/pool.py:\n\n✅ GOOD:\n- Connection pool uses context manager pattern — proper cleanup\n- Pool size configurable via env (default: 10, max: 50)\n- Health check ping before returning connection from pool\n- Thread-safe with threading.Lock on checkout/checkin\n\n🟡 MINOR:\n- Line 34: Pool exhaustion returns None silently — should raise or block with timeout\n- Line 78: No metrics/logging for pool utilization — hard to debug in production\n\n📊 Overall: Clean refactor, net code reduction. Two minor improvements suggested."},
        {"action": "generate_review", "type": "llm_call", "model": "gpt-4o",
         "input": "Generate PR review for #491",
         "output": "## PR Review: #491 — Refactor database connection pooling\n\n**Verdict: ✅ Approve with suggestions**\n\nClean refactor that reduces code by 47 lines while improving structure.\n\n### Suggestions (non-blocking)\n1. Pool exhaustion (line 34): Raise `PoolExhaustedError` instead of returning None\n2. Add pool utilization metrics (checkout count, wait time, pool size)\n\n### Positive\n- Proper context manager cleanup\n- Thread-safe implementation\n- Health check on checkout\n- Good test coverage (2 new test files)\n\n**Approved — suggestions can be addressed in follow-up PR.**"},
    ],
]

# Model switch day — gpt-4o-mini, lower quality
CODE_MODEL_SWITCH_STEPS = [
    {"action": "fetch_pr", "type": "tool_call", "model": "gpt-4o-mini",
     "input": "Fetch PR #503: 'Implement payment processing webhook handler' — 8 files changed, +420 -12 lines",
     "output": "PR #503 loaded. Files: webhooks/payment.py, services/billing.py, models/transaction.py, tests/test_payment.py, + 4 others."},
    {"action": "analyze_code", "type": "llm_call", "model": "gpt-4o-mini",
     "input": "Review webhooks/payment.py for security: webhook signature verification, idempotency, error handling, sensitive data logging",
     "output": "Review of payment.py:\n- Webhook signature: present, uses HMAC-SHA256 ✅\n- Idempotency: not clearly implemented, might have duplicate processing\n- Error handling: basic try/except, could be better\n- Data logging: looks OK\n\nOverall seems fine, a few things to improve."},
    {"action": "analyze_code", "type": "llm_call", "model": "gpt-4o-mini",
     "input": "Review services/billing.py for correctness: amount calculations, currency handling, refund logic",
     "output": "Billing review:\n- Amounts use float — this is a common pattern\n- Currency is hardcoded to USD\n- Refund logic exists\n- Looks reasonable overall"},
    {"action": "generate_review", "type": "llm_call", "model": "gpt-4o-mini",
     "input": "Generate PR review for #503",
     "output": "## PR Review: #503 — Payment webhook handler\n\n**Verdict: ✅ Approve**\n\nImplementation looks good overall.\n- Webhook signature verification present\n- Basic error handling\n- Tests included\n\nMinor: Consider adding idempotency key check.\n\n**Approved.**"},
]

# What GPT-4o WOULD have caught on the same PR
CODE_MODEL_SWITCH_MISSED = """CRITICAL ISSUES MISSED BY GPT-4O-MINI:
1. 🔴 billing.py uses FLOAT for money — must use Decimal to avoid rounding errors ($10.30 becomes $10.299999...)
2. 🔴 No idempotency key → duplicate webhook = double charge
3. 🟡 Currency hardcoded to USD — breaks for international customers
4. 🟡 Refund has no maximum check — could refund more than original charge
GPT-4O-MINI approved this PR. GPT-4O would have caught all 4 issues."""


def _make_record(agent: str, step_template: dict, ts: int, prev_id: str, session_id: str,
                 confidence_penalty: float = 0.0, latency_add: int = 0) -> tuple[dict, dict]:
    """Create a record + vault pair. Returns (record, vault_content)."""
    record_id = _rid()

    is_error = step_template.get("error", False)
    base_confidence = random.uniform(0.82, 0.95)
    confidence = round(max(0.15, base_confidence - confidence_penalty), 3)

    base_latency = random.randint(180, 650) if step_template["type"] == "llm_call" else random.randint(80, 300)
    latency = base_latency + latency_add

    flags = []
    if is_error:
        flags.append("error")
    if confidence < 0.5:
        flags.append("low_confidence")

    record = {
        "id": record_id,
        "agent": agent,
        "ts": ts,
        "step": {
            "type": step_template["type"],
            "action": step_template["action"],
            "model": step_template.get("model", "gpt-4o"),
            "latency_ms": latency,
            "confidence": confidence,
            "flags": flags,
            "session_id": session_id,
        },
        "chain": {
            "prev": prev_id,
            "hash": _sha256(f"{record_id}:{prev_id}:{ts}"),
        },
    }

    vault = {
        "record_id": record_id,
        "input": step_template["input"],
        "output": step_template["output"],
    }

    return record, vault


def generate_demo_data(days: int = 60) -> int:
    """Generate two-scenario demo data."""
    init_storage()

    # Clear old demo data
    for f in RECORDS_DIR.glob("*.jsonl"):
        f.unlink()
    for f in VAULT_DIR.glob("rec_*.json"):
        f.unlink()
    # Clear old index
    search_db = ECP_DIR / "search.db"
    if search_db.exists():
        search_db.unlink()

    total = 0
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Per-agent chain tracking
    prev_ids = {RESEARCH_AGENT: "", CODE_AGENT: ""}

    # Day-by-day generation
    daily_records: dict[str, list] = {}  # date_str -> records

    for day in range(days):
        current_date = start_date + timedelta(days=day)
        date_str = current_date.strftime("%Y-%m-%d")
        if date_str not in daily_records:
            daily_records[date_str] = []

        base_ts = int(current_date.timestamp() * 1000) + 9 * 3600_000  # 9am start

        # ── Scenario A: Research Agent ──
        research_session = f"sess_research_{date_str.replace('-', '')}"

        if day <= 25:
            # Normal: pick a random session template
            steps = random.choice(RESEARCH_SESSIONS)
            conf_penalty = 0.0
            lat_add = 0
        elif day <= 30:
            # Drift: stale data
            steps = RESEARCH_DRIFT_STEPS
            conf_penalty = 0.1 + (day - 25) * 0.05  # 0.1 → 0.35
            lat_add = 0
        elif day <= 34:
            # Error spike
            steps = RESEARCH_ERROR_STEPS
            conf_penalty = 0.4
            lat_add = random.randint(200, 800)
        elif day <= 37:
            # Recovery
            steps = RESEARCH_RECOVERY_STEPS
            conf_penalty = max(0, 0.15 - (day - 34) * 0.05)
            lat_add = 0
        else:
            # Back to normal
            steps = random.choice(RESEARCH_SESSIONS)
            conf_penalty = 0.0
            lat_add = 0

        for i, step in enumerate(steps):
            ts = base_ts + i * 300_000 + random.randint(0, 60_000)  # ~5min apart
            record, vault = _make_record(
                RESEARCH_AGENT, step, ts, prev_ids[RESEARCH_AGENT],
                research_session, conf_penalty, lat_add
            )
            daily_records[date_str].append(record)
            prev_ids[RESEARCH_AGENT] = record["id"]
            total += 1

            # Write vault
            vault_file = VAULT_DIR / f"{record['id']}.json"
            vault_file.write_text(json.dumps(vault, ensure_ascii=False, indent=2), encoding="utf-8")

        # ── Scenario B: Code Review Agent ──
        code_session = f"sess_codereview_{date_str.replace('-', '')}"
        code_base_ts = base_ts + 4 * 3600_000  # starts at 1pm

        if day <= 20:
            # Normal
            steps = random.choice(CODE_SESSIONS_NORMAL)
            conf_penalty = 0.0
            lat_add = 0
        elif day <= 25:
            # Model switch: gpt-4o-mini, fast but low quality
            steps = CODE_MODEL_SWITCH_STEPS
            conf_penalty = 0.25  # lower confidence
            lat_add = -100  # faster but worse
        elif day <= 30:
            # Reverted to gpt-4o
            steps = random.choice(CODE_SESSIONS_NORMAL)
            conf_penalty = 0.0
            lat_add = 0
        else:
            # Stable with occasional errors
            steps = random.choice(CODE_SESSIONS_NORMAL)
            conf_penalty = 0.0
            lat_add = 0
            # Occasional complex PR error
            if random.random() < 0.08:
                steps = list(steps)  # copy
                steps[-1] = {
                    **steps[-1],
                    "output": steps[-1]["output"].replace("Approve", "Request Changes — complexity exceeds review capacity, flagging for human reviewer"),
                    "error": True,
                }

        for i, step in enumerate(steps):
            ts = code_base_ts + i * 300_000 + random.randint(0, 60_000)
            record, vault = _make_record(
                CODE_AGENT, step, ts, prev_ids[CODE_AGENT],
                code_session, conf_penalty, max(0, lat_add)
            )
            daily_records[date_str].append(record)
            prev_ids[CODE_AGENT] = record["id"]
            total += 1

            vault_file = VAULT_DIR / f"{record['id']}.json"
            vault_file.write_text(json.dumps(vault, ensure_ascii=False, indent=2), encoding="utf-8")

    # Write JSONL files
    for date_str, records in sorted(daily_records.items()):
        record_file = RECORDS_DIR / f"{date_str}.jsonl"
        with open(record_file, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Build index
    index = {}
    for f in sorted(RECORDS_DIR.glob("*.jsonl")):
        for line in f.read_text().splitlines():
            if line.strip():
                try:
                    r = json.loads(line)
                    index[r["id"]] = {"file": str(f), "date": f.stem}
                except Exception:
                    pass
    (ECP_DIR / "index.json").write_text(json.dumps(index))

    return total
