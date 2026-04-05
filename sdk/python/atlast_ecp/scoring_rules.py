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

        # High latency threshold (ms)
        "high_latency_threshold_ms": 10000,

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

    for rec in classified_records:
        cls = rec.get("classification", "interaction")
        if cls in exclude_labels:
            excluded_counts[cls] = excluded_counts.get(cls, 0) + 1
        else:
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
    Compute ATLAST Trust Score (0-1000) per whitepaper §7.2.

    Four signal layers:
      Layer 1: Behavioral Reliability (40%) — error, retry, completion, latency consistency
      Layer 2: Consistency (25%)            — output stability, drift (placeholder)
      Layer 3: Transparency (20%)           — chain integrity, recording coverage
      Layer 4: External Validation (15%)    — owner feedback (placeholder)

    Returns:
        {
            "trust_score": int (0-1000),
            "layers": {
                "behavioral_reliability": {"score": float, "weight": 0.40, "weighted": float},
                "consistency":            {"score": float, "weight": 0.25, "weighted": float},
                "transparency":           {"score": float, "weight": 0.20, "weighted": float},
                "external_validation":    {"score": float, "weight": 0.15, "weighted": float},
            },
            "raw_scores": {...}  # underlying calculate_scores output
        }
    """
    raw = calculate_scores(classified_records)
    interactions = raw["interactions"]

    # ── Layer 1: Behavioral Reliability (40%) ──
    # Reliability (no errors) = 60% of layer, latency consistency = 40% of layer
    reliability = raw.get("reliability", 1.0)
    high_latency_rate = raw.get("high_latency_rate", 0.0)
    latency_score = max(0, 1.0 - high_latency_rate)  # lower high_latency = better
    layer1 = reliability * 0.6 + latency_score * 0.4

    # ── Layer 2: Consistency (25%) ──
    # Placeholder: based on incomplete_rate and hedge_rate for now
    # Full implementation needs cross-temporal hash comparison
    incomplete_rate = raw.get("incomplete_rate", 0.0)
    hedge_rate = raw.get("hedge_rate", 0.0)
    layer2 = max(0, 1.0 - incomplete_rate - hedge_rate)

    # ── Layer 3: Transparency (20%) ──
    # Chain integrity + recording coverage
    layer3 = chain_integrity

    # ── Layer 4: External Validation (15%) ──
    # Placeholder: no owner feedback system yet → neutral 0.7
    layer4 = 0.7 if interactions > 0 else 0.0

    # ── Weighted sum → 0-1000 ──
    weighted_1 = layer1 * 0.40
    weighted_2 = layer2 * 0.25
    weighted_3 = layer3 * 0.20
    weighted_4 = layer4 * 0.15

    total = weighted_1 + weighted_2 + weighted_3 + weighted_4
    trust_score = round(total * 1000)

    # Clamp
    trust_score = max(0, min(1000, trust_score))

    return {
        "trust_score": trust_score,
        "layers": {
            "behavioral_reliability": {"score": round(layer1, 4), "weight": 0.40, "weighted": round(weighted_1, 4)},
            "consistency":            {"score": round(layer2, 4), "weight": 0.25, "weighted": round(weighted_2, 4)},
            "transparency":           {"score": round(layer3, 4), "weight": 0.20, "weighted": round(weighted_3, 4)},
            "external_validation":    {"score": round(layer4, 4), "weight": 0.15, "weighted": round(weighted_4, 4)},
        },
        "raw_scores": raw,
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
