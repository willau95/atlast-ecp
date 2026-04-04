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
            # If there's substantial text output, this is NOT a tool_intermediate
            # (it's the final response that happens to also have tool_calls)
            if len(text_content) > 10:
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

    results = []
    for rec in records:
        # Extract fields from either vault or raw format
        flags = (
            rec.get("flags") or
            rec.get("meta", {}).get("flags") or
            rec.get("step", {}).get("flags") or
            []
        )
        input_text = rec.get("input", "")
        output_text = rec.get("output", "")
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
