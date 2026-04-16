"""
ATLAST Scoring Rules — server-side classification and scoring engine.

Architecture principle:
    SDK emits FACTUAL flags (http_4xx, has_tool_calls, heartbeat, etc.)
    This module applies RULES to classify and score records.
    Rules can be updated server-side without SDK upgrades.

Classification pipeline:
    raw record (with factual flags)
    → classify_record() → classification label
    → calculate_scores() → Trust Score components

Classification labels:
    "interaction"        — real user↔agent interaction (counts toward score)
    "heartbeat"          — system heartbeat (excluded from scoring)
    "system_error"       — billing/auth/quota error (not agent's fault)
    "infra_error"        — provider infrastructure error (not agent's fault)
    "tool_intermediate"  — mid-chain tool_call/tool_result (aggregated into parent)
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

_logger = logging.getLogger(__name__)

# ─── Default Rules (built-in, used when server is unreachable) ────────────────

DEFAULT_RULES: dict[str, Any] = {
    "version": "1.0",
    "updated_at": "2026-04-05",

    # Classification rules: checked in order, first match wins
    "classification": [
        {
            "label": "heartbeat",
            "description": "System heartbeat message, not a user interaction",
            "conditions": {"any_flag": ["heartbeat"]},
        },
        {
            "label": "system_error",
            "description": "Billing, auth, or quota error from the provider",
            "conditions": {"any_flag": ["provider_error"]},
            # Additional pattern matching on output content
            "output_patterns": [
                "extra usage", "billing", "quota", "Third-party apps",
                "api_key", "invalid_request_error", "authentication",
                "insufficient_quota", "account", "plan limits",
            ],
        },
        {
            "label": "infra_error",
            "description": "Provider infrastructure failure",
            "conditions": {"any_flag": ["http_5xx", "infra_error"]},
            "output_patterns": [
                "rate limit", "overloaded", "capacity", "maintenance",
                "service_unavailable", "internal_server_error",
            ],
        },
        {
            "label": "tool_intermediate",
            "description": "Mid-chain API call (tool_call or tool_result continuation)",
            "conditions": {
                "any_flag": ["has_tool_calls", "tool_continuation"],
                "all_flag": [],  # no additional requirements
            },
            # Only classify as intermediate if output has no user-facing text
            "require_empty_text_output": True,
        },
        {
            "label": "interaction",
            "description": "Real user↔agent interaction (default)",
            "conditions": {"default": True},
        },
    ],

    # Scoring configuration
    "scoring": {
        # These classifications are excluded from scoring
        "exclude_from_scoring": ["heartbeat", "system_error", "infra_error", "tool_intermediate"],

        # Flags excluded from latency calculation
        "exclude_from_latency": ["heartbeat", "infra_error", "system_error"],

        # High latency threshold (ms) — 30s for LLM agents (10-30s normal)
        "high_latency_threshold_ms": 30000,

        # Incomplete detection: min output chars for "complete"
        "incomplete_max_chars": 5,
    },

    # Custom rules (extensible — Boss can add new ones anytime)
    "custom_rules": [],
}


# ─── Classification Engine ────────────────────────────────────────────────────

def classify_record(
    flags: list[str],
    input_text: str = "",
    output_text: str = "",
    http_status: int = 200,
    rules: Optional[dict] = None,
) -> str:
    """
    Classify a single ECP record based on its factual flags and content.

    Returns a classification label: "interaction", "heartbeat", "system_error",
    "infra_error", or "tool_intermediate".

    Rules are checked in order; first match wins.
    """
    if rules is None:
        rules = get_rules()

    flag_set = set(flags) if flags else set()
    output_lower = (output_text or "").lower()
    output_stripped = (output_text or "").strip()

    # ── Retroactive detection for pre-v0.17 records (no factual flags) ──
    # Detect heartbeat from content even if flag is missing (retroactive for pre-v0.17 records)
    # HEARTBEAT is a system-injected prompt from OpenClaw, never user-generated
    if "heartbeat" not in flag_set and "HEARTBEAT" in (input_text or ""):
        flag_set.add("heartbeat")

    # Detect provider_error from content
    if "provider_error" not in flag_set:
        provider_error_patterns = [
            "extra usage", "billing", "quota", "third-party apps",
            "invalid_request_error", "insufficient_quota",
        ]
        # Check if output looks like a provider error JSON
        if output_lower.startswith('{"type":"error"') or output_lower.startswith('{"error"'):
            flag_set.add("provider_error")
        elif any(p in output_lower for p in provider_error_patterns):
            flag_set.add("provider_error")

    # Detect empty_output
    if "empty_output" not in flag_set and not output_stripped:
        flag_set.add("empty_output")

    # Detect has_tool_calls from incomplete flag + empty output (legacy heuristic)
    # In v0.16, tool_call responses were marked "incomplete" because output was empty
    if "incomplete" in flag_set and not output_stripped:
        flag_set.add("has_tool_calls")
        flag_set.add("empty_output")

    for rule in rules.get("classification", []):
        if rule.get("conditions", {}).get("default"):
            return rule["label"]

        conditions = rule.get("conditions", {})

        # Check any_flag: at least one flag must match
        any_flags = conditions.get("any_flag", [])
        if any_flags and not flag_set.intersection(any_flags):
            continue

        # Check all_flag: all flags must match (if specified and non-empty)
        all_flags = conditions.get("all_flag", [])
        if all_flags and not flag_set.issuperset(all_flags):
            continue

        # Check output_patterns (if any match, it's a stronger signal)
        output_patterns = rule.get("output_patterns", [])
        if output_patterns:
            # For system_error with provider_error flag: flag is sufficient
            # For system_error without flag: need pattern match
            if not flag_set.intersection(conditions.get("any_flag", [])):
                # No flag match, check patterns
                if not any(p.lower() in output_lower for p in output_patterns):
                    continue

        # Check require_empty_text_output
        if rule.get("require_empty_text_output"):
            text_content = (output_text or "").strip()
            # If there's any meaningful text output, this is NOT a tool_intermediate
            # (it's the final response that happens to also have tool_calls)
            if text_content:
                continue

        return rule["label"]

    return "interaction"  # fallback


def classify_records(records: list[dict], rules: Optional[dict] = None) -> list[dict]:
    """
    Classify a list of ECP records in bulk.
    Each record gets a "classification" field added.

    Expects records in vault v2 format (with flags, input, output).
    Also accepts raw record format from .jsonl files.
    """
    if rules is None:
        rules = get_rules()

    # Pre-load vault data for raw records that lack input/output
    vault_cache = {}
    for rec in records:
        if "input" not in rec and rec.get("id"):
            try:
                from pathlib import Path
                ecp_dir = Path(os.environ.get("ATLAST_ECP_DIR", os.environ.get("ECP_DIR", os.path.expanduser("~/.ecp"))))
                vault_path = ecp_dir / "vault" / f"{rec['id']}.json"
                if vault_path.exists():
                    import json as _json
                    vault_cache[rec["id"]] = _json.loads(vault_path.read_text())
            except Exception:
                pass

    results = []
    for rec in records:
        # Extract fields from either vault or raw format
        flags = (
            rec.get("flags") or
            rec.get("meta", {}).get("flags") or
            rec.get("step", {}).get("flags") or
            []
        )
        # For raw JSONL records, fall back to vault for input/output
        vault_data = vault_cache.get(rec.get("id", ""), {})
        input_text = rec.get("input", "") or vault_data.get("input", "")
        output_text = rec.get("output", "") or vault_data.get("output", "")
        http_status = rec.get("http_status") or rec.get("vault_extra", {}).get("http_status") or 200

        classification = classify_record(
            flags=flags,
            input_text=input_text,
            output_text=output_text,
            http_status=http_status,
            rules=rules,
        )

        result = dict(rec)
        result["classification"] = classification
        results.append(result)

    return results


# ─── Score Calculation ─────────────────────────────────────────────────────────

def calculate_scores(
    classified_records: list[dict],
    rules: Optional[dict] = None,
) -> dict:
    """
    Calculate Trust Score components from classified records.

    Only "interaction" records count toward scoring.
    Other classifications are reported separately.

    Returns:
        {
            "total_records": int,
            "interactions": int,
            "excluded": {
                "heartbeat": int,
                "system_error": int,
                "infra_error": int,
                "tool_intermediate": int,
            },
            "reliability": float (0-1),
            "avg_latency_ms": int,
            "hedge_rate": float,
            "incomplete_rate": float,
            "error_rate": float,
            "high_latency_rate": float,
        }
    """
    if rules is None:
        rules = get_rules()

    scoring = rules.get("scoring", {})
    exclude_labels = set(scoring.get("exclude_from_scoring", []))

    total = len(classified_records)
    excluded_counts: dict[str, int] = {}
    interaction_records = []

    # Anti-gaming filters
    import hashlib as _hashlib
    _seen_input_hashes: dict[str, int] = {}  # hash → count

    for rec in classified_records:
        cls = rec.get("classification", "interaction")
        if cls in exclude_labels:
            excluded_counts[cls] = excluded_counts.get(cls, 0) + 1
            continue

        # Filter 1: Minimum interaction time — <100ms is suspicious (scripted)
        lat = (
            rec.get("latency_ms") or
            rec.get("meta", {}).get("latency_ms") or
            rec.get("step", {}).get("latency_ms") or 0
        )
        if lat > 0 and lat < 100:
            excluded_counts["too_fast"] = excluded_counts.get("too_fast", 0) + 1
            continue

        # Filter 2: Minimum output length — <5 chars is not real work
        # (Generous threshold to avoid false positives on short valid responses)
        output = rec.get("output", "") or rec.get("output_preview", "") or ""
        if isinstance(output, str) and 0 < len(output.strip()) < 5:
            excluded_counts["trivial_output"] = excluded_counts.get("trivial_output", 0) + 1
            continue

        # Filter 3: Duplicate input — same input hash >3 times doesn't count
        input_text = rec.get("input", "") or rec.get("input_preview", "") or ""
        if input_text:
            inp_hash = _hashlib.md5(str(input_text).encode()).hexdigest()[:12]
            _seen_input_hashes[inp_hash] = _seen_input_hashes.get(inp_hash, 0) + 1
            if _seen_input_hashes[inp_hash] > 3:
                excluded_counts["duplicate_input"] = excluded_counts.get("duplicate_input", 0) + 1
                continue

        interaction_records.append(rec)

    interactions = len(interaction_records)

    if interactions == 0:
        return {
            "total_records": total,
            "interactions": 0,
            "excluded": excluded_counts,
            "reliability": 1.0,
            "avg_latency_ms": 0,
            "hedge_rate": 0.0,
            "incomplete_rate": 0.0,
            "error_rate": 0.0,
            "high_latency_rate": 0.0,
        }

    # Count flags in interaction records only
    def _flag_count(flag: str) -> int:
        return sum(1 for r in interaction_records if flag in (
            r.get("flags") or r.get("meta", {}).get("flags") or
            r.get("step", {}).get("flags") or []))

    agent_errors = _flag_count("error")
    hedged = _flag_count("hedged")
    incomplete = _flag_count("incomplete")
    high_latency = _flag_count("high_latency")

    # Latency from interaction records only
    latencies = []
    for r in interaction_records:
        lat = (
            r.get("latency_ms") or
            r.get("meta", {}).get("latency_ms") or
            r.get("step", {}).get("latency_ms")
        )
        if lat:
            latencies.append(lat)

    return {
        "total_records": total,
        "interactions": interactions,
        "excluded": excluded_counts,
        "reliability": round((interactions - agent_errors) / interactions, 4),
        "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else 0,
        "hedge_rate": round(hedged / interactions, 4),
        "incomplete_rate": round(incomplete / interactions, 4),
        "error_rate": round(agent_errors / interactions, 4),
        "high_latency_rate": round(high_latency / interactions, 4),
    }


def compute_trust_score_1000(classified_records: list[dict], chain_integrity: float = 1.0) -> dict:
    """
    Compute ATLAST Trust Score (0-1000) — Confidence-Based Scoring.

    Core principle: Trust is EARNED through proven work, not assumed.
    A new agent starts at 500 (unknown). Score rises with successful work
    and data volume. More usage = higher potential score (not lower).

    Three signal layers:
      Layer 1: Proven Reliability (70%)    — Bayesian success rate
      Layer 2: Evidence Integrity (15%)    — chain completeness
      Layer 3: Activity Confidence (15%)   — how much data backs the score

    Bayesian approach (Layer 1):
      score = (successes + prior) / (total + prior_total)
      Prior: 5 successes out of 10 (50% = "unknown")
      - 0 interactions: 5/10 = 0.5 (neutral)
      - 100 interactions, 0 errors: 105/110 = 0.95 (proven reliable)
      - 1000 interactions, 50 errors: 955/1010 = 0.95 (still excellent)
      - 10 interactions, 5 errors: 10/20 = 0.5 (concerning)

    What does NOT affect score:
      - high_latency: API/model speed is the provider's issue
      - hedge_rate: cautious language is responsible, not a flaw
      - infra_error/system_error: not the agent's fault
      - incomplete (when due to tool limitations): honest behavior

    Returns:
        {
            "trust_score": int (0-1000),
            "layers": { ... },
            "raw_scores": { ... }
        }
    """
    raw = calculate_scores(classified_records)
    interactions = raw["interactions"]
    error_rate = raw.get("error_rate", 0.0)

    # Count actual agent successes and failures
    agent_errors = round(error_rate * interactions) if interactions else 0
    successes = interactions - agent_errors

    # ── Layer 1: Proven Reliability (70%) ──
    # Bayesian estimate with prior (5 successes / 10 total = 50% prior)
    # This naturally handles the volume-quality tradeoff:
    # - Few interactions → pulled toward 50% (uncertain)
    # - Many interactions → approaches actual success rate
    # - More data always helps if quality is maintained
    PRIOR_SUCCESSES = 5
    PRIOR_TOTAL = 10
    layer1 = (successes + PRIOR_SUCCESSES) / (interactions + PRIOR_TOTAL)

    # ── Layer 2: Evidence Integrity (15%) ──
    # Chain completeness ratio (0.0-1.0)
    # Measures protocol integrity, not agent behavior
    layer2 = chain_integrity

    # ── Layer 3: Activity Confidence (15%) ──
    # How much data backs this score? More interactions = higher confidence.
    # Logarithmic scale: diminishing returns after ~100 interactions.
    import math
    if interactions <= 0:
        layer3 = 0.0
    elif interactions >= 1000:
        layer3 = 1.0
    else:
        # log curve: 10→0.5, 50→0.78, 100→0.87, 500→0.97
        layer3 = min(1.0, math.log10(interactions) / 3.0)

    # ── Weighted sum → 0-1000 ──
    weighted_1 = layer1 * 0.70
    weighted_2 = layer2 * 0.15
    weighted_3 = layer3 * 0.15

    total = weighted_1 + weighted_2 + weighted_3
    trust_score = round(total * 1000)
    trust_score = max(0, min(1000, trust_score))

    return {
        "trust_score": trust_score,
        "layers": {
            "proven_reliability":   {"score": round(layer1, 4), "weight": 0.70, "weighted": round(weighted_1, 4)},
            "evidence_integrity":   {"score": round(layer2, 4), "weight": 0.15, "weighted": round(weighted_2, 4)},
            "activity_confidence":  {"score": round(layer3, 4), "weight": 0.15, "weighted": round(weighted_3, 4)},
        },
        "raw_scores": raw,
    }


# ─── Trust Score v2 — Legal-Grade Architecture ──────────────────────────────

def compute_trust_score_v2(records: list[dict], chain_integrity: float = 1.0) -> dict:
    """
    ATLAST Trust Score v2 (0-1000) — Legal-Grade Reliability Architecture.

    Philosophy: Score measures the OPERATIONAL RELIABILITY of the Agent+LLM
    system when it is used. Not how often it's used (user's responsibility),
    not how smart it is (subjective), but how reliably it operates.

    Attribution principle:
      - Agent errors (wrong tool, hallucination)     → COUNTS against score
      - LLM provider errors (500, 429, timeout)      → EXCLUDED (not agent's fault)
      - Infra errors (network, DNS, disk)             → EXCLUDED
      - User interruptions (manual stop)              → EXCLUDED
      - Evidence gaps (missing vault, broken chain)    → COUNTS (agent should ensure completeness)

    5 dimensions:
      1. Operational Reliability (35%) — time-weighted agent error-free rate
      2. Evidence Completeness (25%)   — chain integrity + record field completeness
      3. Behavioral Consistency (20%)  — stability over time (low variance)
      4. Operational Maturity (10%)    — history length (not volume!)
      5. Data Integrity (10%)          — anti-gaming checks

    Score distribution target:
      900+ : ~5%  (exceptional — months of consistent, complex, error-free work)
      700-899: ~30% (good — reliable with minor issues)
      500-699: ~45% (normal — new or moderately reliable agents)
      300-499: ~15% (needs improvement)
      <300  : ~5%  (problematic)

    New agent starts at ~500 (Bayesian prior pulls toward center).
    """
    import math
    from collections import defaultdict

    if not records:
        return _v2_empty_result()

    raw = calculate_scores(records)
    interactions = raw["interactions"]
    total_records = raw["total_records"]

    if interactions == 0:
        return _v2_empty_result()

    import time as _time
    now_ms = int(_time.time() * 1000)  # Real current time, not max(ts)

    # ═══════════════════════════════════════════════════════════
    # DIMENSION 1: Operational Reliability (35%)
    # Time-weighted Bayesian agent-error-free rate
    # Recent performance matters more than historical
    # ═══════════════════════════════════════════════════════════
    recent_7d = 0; recent_7d_err = 0
    recent_30d = 0; recent_30d_err = 0
    older = 0; older_err = 0

    for r in records:
        ts = r.get("ts") or 0
        is_agent_error = bool(r.get("error")) and not bool(r.get("is_infra"))
        # Classify flags
        flags = r.get("flags") or ""
        if isinstance(flags, str):
            try:
                import json as _j
                flags = _j.loads(flags)
            except Exception:
                flags = []
        if not isinstance(flags, list):
            flags = []

        is_excluded = "infra_error" in flags or "system_error" in flags
        if is_excluded:
            continue  # Don't count infra/system errors at all

        age_days = (now_ms - ts) / 86400000 if ts and now_ms else 999

        if age_days <= 7:
            recent_7d += 1
            if is_agent_error: recent_7d_err += 1
        elif age_days <= 30:
            recent_30d += 1
            if is_agent_error: recent_30d_err += 1
        else:
            older += 1
            if is_agent_error: older_err += 1

    # Weighted counts (recent 3x, mid 2x, old 1x)
    w_total = recent_7d * 3 + recent_30d * 2 + older * 1
    w_errors = recent_7d_err * 3 + recent_30d_err * 2 + older_err * 1

    # Bayesian: prior = 2 successes / 4 total (50% prior, tighter than v1)
    w_successes = w_total - w_errors
    dim1 = (w_successes + 2) / (w_total + 4) if w_total > 0 else 0.5

    # ═══════════════════════════════════════════════════════════
    # DIMENSION 2: Evidence Completeness (25%)
    # Chain integrity + record field completeness
    # ═══════════════════════════════════════════════════════════
    chain_score = chain_integrity  # 0.0 - 1.0

    # Field completeness: how many records have all key fields?
    complete = 0
    for r in records:
        has_model = bool(r.get("model"))
        has_input = bool(r.get("input_preview") or r.get("input"))
        has_output = bool(r.get("output_preview") or r.get("output"))
        has_chain = bool(r.get("chain_hash"))
        if has_model and has_input and has_output and has_chain:
            complete += 1
    field_completeness = complete / len(records) if records else 0

    dim2 = chain_score * 0.6 + field_completeness * 0.4

    # ═══════════════════════════════════════════════════════════
    # DIMENSION 3: Behavioral Consistency (20%)
    # Low variance in daily error rate = more trustworthy
    # A stable 3% error rate is better than swinging 0%-20%
    # ═══════════════════════════════════════════════════════════
    daily_errors = defaultdict(lambda: {"total": 0, "errors": 0})
    for r in records:
        ts = r.get("ts") or 0
        if not ts:
            continue
        day_key = ts // 86400000  # Day bucket
        daily_errors[day_key]["total"] += 1
        is_agent_error = bool(r.get("error")) and not bool(r.get("is_infra"))
        if is_agent_error:
            daily_errors[day_key]["errors"] += 1

    if len(daily_errors) >= 3:
        daily_rates = [d["errors"] / max(d["total"], 1) for d in daily_errors.values()]
        mean_rate = sum(daily_rates) / len(daily_rates)
        variance = sum((r - mean_rate) ** 2 for r in daily_rates) / len(daily_rates)
        std_dev = math.sqrt(variance)
        # Score: lower std_dev = better. std_dev of 0 = perfect (1.0), std_dev of 0.3+ = bad (0.0)
        dim3 = max(0.0, 1.0 - (std_dev / 0.3))
    elif len(daily_errors) >= 1:
        # Not enough days for consistency — give benefit of doubt but cap at 0.7
        dim3 = 0.7
    else:
        dim3 = 0.5

    # ═══════════════════════════════════════════════════════════
    # DIMENSION 4: Operational Maturity (10%)
    # Combines: history span + recency (when was the agent last seen?)
    # Long history + recently active = highest maturity
    # Long history + inactive = decayed maturity
    # Short history = low maturity (can't be gamed — time can't be faked)
    # ═══════════════════════════════════════════════════════════
    timestamps = [r.get("ts") or 0 for r in records if r.get("ts")]
    if timestamps:
        first_ts = min(timestamps)
        last_ts = max(timestamps)
        history_days = (last_ts - first_ts) / 86400000
        # Recency: how many days since last record?
        days_since_last = (now_ms - last_ts) / 86400000 if now_ms > last_ts else 0
    else:
        history_days = 0
        days_since_last = 999

    # History component: 7d→0.3, 30d→0.65, 90d→0.9
    if history_days <= 0:
        history_component = 0.1  # At least one record
    else:
        history_component = min(1.0, 1.0 - math.exp(-history_days / 60))

    # Recency decay: inactive agents lose maturity
    # 0 days inactive → 1.0, 30 days → 0.6, 90 days → 0.2, 180 days → 0.05
    recency_factor = max(0.05, math.exp(-days_since_last / 60))

    dim4 = history_component * recency_factor

    # ═══════════════════════════════════════════════════════════
    # DIMENSION 5: Data Integrity (10%)
    # Anti-gaming: detect synthetic/spam patterns
    # ═══════════════════════════════════════════════════════════
    import hashlib as _hl
    input_hashes = defaultdict(int)
    burst_windows = defaultdict(int)  # 5-min windows

    for r in records:
        inp = r.get("input_preview") or r.get("input") or ""
        # Exclude HEARTBEAT and system messages from duplicate counting
        if inp and "HEARTBEAT" not in inp and not inp.startswith("<"):
            h = _hl.md5(str(inp).encode()).hexdigest()[:12]
            input_hashes[h] += 1
        ts = r.get("ts") or 0
        if ts:
            window = ts // 300000  # 5-min window
            burst_windows[window] += 1

    # Duplicate rate: what % of inputs are repeated >3 times?
    total_duped = sum(c - 3 for c in input_hashes.values() if c > 3)
    dup_rate = total_duped / max(len(records), 1)
    dup_penalty = min(1.0, dup_rate * 5)  # 20% duped → full penalty

    # Burst rate: any 5-min window with >50 records?
    max_burst = max(burst_windows.values()) if burst_windows else 0
    burst_penalty = min(1.0, max(0, max_burst - 50) / 100)

    dim5 = max(0.0, 1.0 - dup_penalty * 0.6 - burst_penalty * 0.4)

    # ═══════════════════════════════════════════════════════════
    # WEIGHTED SUM → 0-1000
    # ═══════════════════════════════════════════════════════════
    weights = {
        "operational_reliability": 0.35,
        "evidence_completeness": 0.25,
        "behavioral_consistency": 0.20,
        "operational_maturity": 0.10,
        "data_integrity": 0.10,
    }
    dims = {
        "operational_reliability": dim1,
        "evidence_completeness": dim2,
        "behavioral_consistency": dim3,
        "operational_maturity": dim4,
        "data_integrity": dim5,
    }

    total = sum(dims[k] * weights[k] for k in weights)
    trust_score = round(total * 1000)
    trust_score = max(0, min(1000, trust_score))

    # Volume floor: insufficient data = capped confidence
    # < 10 interactions: max 600 (we can't be confident yet)
    # < 30 interactions: max 750
    # < 100 interactions: max 900
    if interactions < 10:
        trust_score = min(trust_score, 600)
    elif interactions < 30:
        trust_score = min(trust_score, 750)
    elif interactions < 100:
        trust_score = min(trust_score, 900)

    # ═══════════════════════════════════════════════════════════
    # LLM Performance Profile (separate, not in Trust Score)
    # ═══════════════════════════════════════════════════════════
    model_stats = defaultdict(lambda: {"calls": 0, "errors": 0, "latency": []})
    for r in records:
        model = r.get("model") or "unknown"
        model_stats[model]["calls"] += 1
        if r.get("is_infra"):
            model_stats[model]["errors"] += 1
        lat = r.get("latency_ms") or 0
        if lat > 0:
            model_stats[model]["latency"].append(lat)

    llm_profile = {}
    for model, stats in model_stats.items():
        lats = stats["latency"]
        llm_profile[model] = {
            "calls": stats["calls"],
            "error_rate": round(stats["errors"] / max(stats["calls"], 1), 4),
            "avg_latency_ms": int(sum(lats) / len(lats)) if lats else 0,
            "p95_latency_ms": int(sorted(lats)[int(len(lats) * 0.95)]) if len(lats) >= 5 else 0,
        }

    # ═══════════════════════════════════════════════════════════
    # RESULT
    # ═══════════════════════════════════════════════════════════
    layers = {}
    dim_labels = {
        "operational_reliability": "How reliably does the agent operate without errors?",
        "evidence_completeness": "Is the evidence chain and record data complete?",
        "behavioral_consistency": "Is performance stable over time?",
        "operational_maturity": "How long has this agent been observed?",
        "data_integrity": "Is the data genuine (not gamed/synthetic)?",
    }
    for k in weights:
        layers[k] = {
            "score": round(dims[k], 4),
            "weight": weights[k],
            "weighted": round(dims[k] * weights[k], 4),
            "description": dim_labels[k],
        }

    return {
        "trust_score": trust_score,
        "version": 2,
        "layers": layers,
        "raw_scores": raw,
        "llm_profile": llm_profile,
        "meta": {
            "records_analyzed": len(records),
            "interactions_scored": interactions,
            "history_days": round(history_days, 1),
            "active_days": len(daily_errors),
            "models_used": len(model_stats),
        },
    }


def _v2_empty_result():
    return {
        "trust_score": 500,
        "version": 2,
        "layers": {
            "operational_reliability": {"score": 0.5, "weight": 0.35, "weighted": 0.175, "description": "No data yet"},
            "evidence_completeness": {"score": 0.5, "weight": 0.25, "weighted": 0.125, "description": "No data yet"},
            "behavioral_consistency": {"score": 0.5, "weight": 0.20, "weighted": 0.100, "description": "No data yet"},
            "operational_maturity": {"score": 0.0, "weight": 0.10, "weighted": 0.000, "description": "No data yet"},
            "data_integrity": {"score": 1.0, "weight": 0.10, "weighted": 0.100, "description": "No data yet"},
        },
        "raw_scores": {"total_records": 0, "interactions": 0, "excluded": {}, "reliability": 1.0,
                        "avg_latency_ms": 0, "hedge_rate": 0.0, "incomplete_rate": 0.0, "error_rate": 0.0, "high_latency_rate": 0.0},
        "llm_profile": {},
        "meta": {"records_analyzed": 0, "interactions_scored": 0, "history_days": 0, "active_days": 0, "models_used": 0},
    }


# ─── Rules Management ─────────────────────────────────────────────────────────

_rules_cache: Optional[dict] = None
_rules_cache_time: float = 0
_CACHE_TTL_SECONDS = 86400  # 24 hours


def get_rules() -> dict:
    """
    Get current scoring rules.
    Priority: cache → local file → remote server → built-in defaults.
    Fail-Open: always returns valid rules, never raises.
    """
    global _rules_cache, _rules_cache_time

    # 1. In-memory cache (fastest)
    if _rules_cache and (time.time() - _rules_cache_time) < _CACHE_TTL_SECONDS:
        return _rules_cache

    # 2. Local cache file
    cache_path = Path(os.environ.get("ATLAST_ECP_DIR", "~/.ecp")).expanduser() / "scoring_rules_cache.json"
    try:
        if cache_path.exists():
            mtime = cache_path.stat().st_mtime
            if (time.time() - mtime) < _CACHE_TTL_SECONDS:
                rules = json.loads(cache_path.read_text(encoding="utf-8"))
                _rules_cache = rules
                _rules_cache_time = time.time()
                return rules
    except Exception:
        pass

    # 3. Remote server
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.weba0.com/v1/scoring/rules",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            rules = json.loads(resp.read().decode("utf-8"))
            # Save to cache
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(rules, indent=2), encoding="utf-8")
            except Exception:
                pass
            _rules_cache = rules
            _rules_cache_time = time.time()
            return rules
    except Exception:
        _logger.debug("Could not fetch scoring rules from server, using defaults")

    # 4. Built-in defaults (always available)
    _rules_cache = DEFAULT_RULES
    _rules_cache_time = time.time()
    return DEFAULT_RULES


def reset_cache():
    """Reset the rules cache (for testing)."""
    global _rules_cache, _rules_cache_time
    _rules_cache = None
    _rules_cache_time = 0


# ─── Tool Chain Aggregation ───────────────────────────────────────────────────

def aggregate_interactions(classified_records: list[dict]) -> list[dict]:
    """
    Aggregate classified records into logical interactions.

    A tool chain is a sequence of API calls for a single user intent:
      1. user message → LLM returns tool_call (tool_intermediate)
      2. tool_result → LLM returns tool_call (tool_intermediate)
      3. tool_result → LLM returns text (interaction)

    This function merges sequential tool_intermediate + final interaction
    records into a single "interaction" with tool_steps detail.

    Records must be sorted by timestamp. Non-interaction records
    (heartbeat, system_error, infra_error) pass through unchanged.

    Returns list of aggregated records, each with:
      - All fields from the final interaction record
      - "tool_steps": list of intermediate tool calls
      - "total_api_calls": number of raw API calls in this interaction
      - "total_latency_ms": sum of all latencies
      - "raw_record_ids": list of all constituent record IDs
    """
    if not classified_records:
        return []

    # Sort by timestamp
    def _get_ts(r: dict) -> int:
        return r.get("ts") or r.get("timestamp") or 0

    sorted_records = sorted(classified_records, key=_get_ts)

    result = []
    pending_chain: list[dict] = []  # accumulator for tool_intermediate records

    for rec in sorted_records:
        cls = rec.get("classification", "interaction")
        session = (
            rec.get("session_id") or
            rec.get("meta", {}).get("session_id") or
            rec.get("step", {}).get("session_id") or
            ""
        )

        if cls == "tool_intermediate":
            # Accumulate into pending chain
            # But check session continuity
            if pending_chain:
                prev_session = (
                    pending_chain[-1].get("session_id") or
                    pending_chain[-1].get("meta", {}).get("session_id") or
                    pending_chain[-1].get("step", {}).get("session_id") or
                    ""
                )
                if session != prev_session:
                    # Different session — flush the old chain as standalone records
                    result.extend(pending_chain)
                    pending_chain = []
            pending_chain.append(rec)

        elif cls == "interaction" and pending_chain:
            # Check if this interaction belongs to the same session as the chain
            prev_session = (
                pending_chain[-1].get("session_id") or
                pending_chain[-1].get("meta", {}).get("session_id") or
                pending_chain[-1].get("step", {}).get("session_id") or
                ""
            )
            if session == prev_session:
                # Merge: chain + final interaction → one aggregated interaction
                all_records = pending_chain + [rec]
                tool_steps = []
                total_latency = 0
                raw_ids = []

                for r in all_records:
                    rid = r.get("id") or r.get("record_id") or ""
                    if rid:
                        raw_ids.append(rid)
                    lat = (
                        r.get("latency_ms") or
                        r.get("meta", {}).get("latency_ms") or
                        r.get("step", {}).get("latency_ms") or 0
                    )
                    total_latency += lat

                    # Extract tool info from intermediate records
                    if r.get("classification") == "tool_intermediate":
                        vault_extra = r.get("vault_extra", {})
                        tool_calls = vault_extra.get("tool_calls") or r.get("tool_calls", [])
                        for tc in tool_calls:
                            tool_steps.append({
                                "name": tc.get("name", ""),
                                "input_preview": str(tc.get("input", ""))[:200],
                            })

                # Build aggregated record from the final interaction
                aggregated = dict(rec)
                aggregated["tool_steps"] = tool_steps
                aggregated["total_api_calls"] = len(all_records)
                aggregated["total_latency_ms"] = total_latency
                aggregated["raw_record_ids"] = raw_ids
                # Use the first record's input (the original user message)
                first_input = pending_chain[0].get("input") or pending_chain[0].get("vault", {}).get("input", "")
                if first_input:
                    aggregated["aggregated_input"] = first_input

                result.append(aggregated)
                pending_chain = []
            else:
                # Different session — flush chain, add interaction standalone
                result.extend(pending_chain)
                pending_chain = []
                result.append(rec)
        else:
            # Non-tool record (heartbeat, system_error, infra, standalone interaction)
            if pending_chain:
                # Flush any pending chain first
                result.extend(pending_chain)
                pending_chain = []
            result.append(rec)

    # Flush any remaining pending chain
    if pending_chain:
        result.extend(pending_chain)

    return result
