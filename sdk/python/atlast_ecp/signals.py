"""
ECP Signals — passive behavioral signal detection.
All signals are detected locally via rule engine. Never LLM-as-Judge.
Agent CANNOT control or self-report these flags.

Two categories of flags:

1. FACTUAL FLAGS (v0.17+) — objective observations, no judgment:
   http_4xx / http_5xx    — HTTP status code ranges
   streaming              — response used SSE streaming
   has_tool_calls         — response contains tool_use / function_call
   tool_continuation      — request contains tool_result (mid-chain)
   empty_output           — response text content is empty
   empty_input            — no user message found in request
   provider_error         — response body is an error from the provider
   heartbeat              — system heartbeat message (not user interaction)
   latency_ms_<N>         — raw latency value (attached as metadata, not flag)

2. BEHAVIORAL FLAGS (legacy, still emitted for compatibility):
   retried        — Agent was asked to redo this task (Negative)
   hedged         — Output contained uncertainty language (Neutral)
   incomplete     — Conversation ended without resolution (Negative)
   high_latency   — Response time > 2x agent's median (Neutral)
   error          — Agent returned an error state (Negative)
   human_review   — Agent requested human verification (Positive)
   a2a_delegated  — Task delegated to sub-agent (Neutral)
   speed_anomaly  — Output suspiciously fast for its length (Neutral)

Architecture principle (v0.17):
   SDK emits FACTUAL flags. Server-side scoring_rules decide what they MEAN.
   e.g., SDK says "http_429" (fact). Server decides "exclude from scoring" (judgment).
"""

import re
import statistics
from typing import Optional

# ─── Pattern Banks ─────────────────────────────────────────────────────────────

HEDGE_PATTERNS = [
    # English
    r"\bi think\b", r"\bi believe\b", r"\bi'm not sure\b", r"\bi am not sure\b",
    r"\bprobably\b", r"\bperhaps\b", r"\bmaybe\b", r"\bmight be\b",
    r"\bcould be\b", r"\bit's possible\b", r"\bpossibly\b",
    r"\buncertain\b", r"\bnot certain\b", r"\bnot sure\b",
    r"\bi'm unsure\b", r"\bapproximately\b",
    r"\bit seems\b", r"\bseems like\b", r"\bappears to\b",
    r"\bto the best of my knowledge\b", r"\bif i recall correctly\b",
    r"\bi may be wrong\b", r"\bi might be wrong\b",
    r"\bI cannot guarantee\b", r"\bnot 100%\b",
    # Chinese
    r"我觉得", r"我认为", r"可能", r"也许", r"大概",
    r"不确定", r"应该是", r"或许", r"似乎", r"好像",
    r"不太清楚", r"不是很确定",
]

INCOMPLETE_PATTERNS = [
    r"\bi cannot\b", r"\bi can't\b", r"\bi cant\b", r"\bunable to\b",
    r"\bnot able to\b",
    r"\boutside my (capabilities|scope|knowledge|ability)\b",
    r"\bi don't have access\b", r"\bi do not have access\b",
    r"\bi (cannot|can't) (help|assist|access|do)\b",
    r"\bbeyond (my|the) (scope|capabilities)\b",
    r"无法", r"做不到", r"超出了我的", r"我没有权限", r"无权访问",
]

ERROR_PATTERNS = [
    r"Traceback \(most recent call last\)",   # Python traceback (no \b after paren)
    r"\bException:", r"\bError:", r"\bValueError:", r"\bTypeError:",
    r"\bRuntimeError:", r"\bAttributeError:", r"\bKeyError:",
    r"500 Internal Server Error",
    r"\bfailed with exit code\b",
]

HUMAN_REVIEW_PATTERNS = [
    r"\bplease (verify|review|confirm|check)\b",
    r"\byou (should|may want to) (verify|review|confirm|check)\b",
    r"\bI recommend (verifying|reviewing|checking)\b",
    r"\bconsult (a|an) (lawyer|doctor|expert|professional|specialist)\b",
    r"\bseek (professional|legal|medical|expert) (advice|opinion|review)\b",
    r"\bhuman (review|oversight|verification) (is|may be) (recommended|required|advised)\b",
    r"建议核实", r"请专业人士", r"建议咨询", r"人工审核",
]

A2A_PATTERNS = [
    r"\bi('ll| will) (delegate|pass|hand off|forward) (this|that)\b",
    r"\bcalling (sub-?agent|another agent|agent)\b",
    r"\bdelegating to\b",
    r"\busing (tool|agent):",
]

# Pre-compile for performance
_HEDGE = [re.compile(p, re.IGNORECASE) for p in HEDGE_PATTERNS]
_INCOMPLETE = [re.compile(p, re.IGNORECASE) for p in INCOMPLETE_PATTERNS]
_ERROR = [re.compile(p, re.IGNORECASE) for p in ERROR_PATTERNS]
_HUMAN_REVIEW = [re.compile(p, re.IGNORECASE) for p in HUMAN_REVIEW_PATTERNS]
_A2A = [re.compile(p, re.IGNORECASE) for p in A2A_PATTERNS]

# High-latency threshold (ms) — default 30 seconds
# LLM agents routinely take 10-30s per call; 5s was too aggressive.
# When median_latency_ms is available, 2x median is used instead.
HIGH_LATENCY_THRESHOLD_MS = 30000


# ─── Flag Detection ────────────────────────────────────────────────────────────

def detect_flags(
    output_text: str,
    is_retry: bool = False,
    latency_ms: Optional[int] = None,
    median_latency_ms: Optional[int] = None,
    is_a2a: bool = False,
    **kwargs,
) -> list[str]:
    """
    Passively detect all applicable behavioral flags from output text.
    Returns sorted list of flag strings.

    Emits BOTH factual flags (v0.17+) and legacy behavioral flags (backward compat).

    Keyword args:
        has_tool_calls: if True, empty text output is NOT incomplete (agent used tools)
        http_status: HTTP status code from the upstream response
        is_heartbeat: True if this is a heartbeat message
        is_tool_continuation: True if request contains tool_result
        is_streaming: True if response used SSE streaming
        is_provider_error: True if response body is a provider error
    """
    has_tool_calls = kwargs.get("has_tool_calls", False)
    http_status = kwargs.get("http_status")
    is_heartbeat = kwargs.get("is_heartbeat", False)
    is_tool_continuation = kwargs.get("is_tool_continuation", False)
    is_streaming = kwargs.get("is_streaming", False)
    is_provider_error = kwargs.get("is_provider_error", False)

    flags = []
    text = (output_text or "").strip()

    # ── Factual flags (v0.17+) ──
    if http_status is not None:
        if 400 <= http_status < 500:
            flags.append("http_4xx")
        elif 500 <= http_status < 600:
            flags.append("http_5xx")

    if is_streaming:
        flags.append("streaming")

    if has_tool_calls:
        flags.append("has_tool_calls")

    if is_tool_continuation:
        flags.append("tool_continuation")

    if not text:
        flags.append("empty_output")

    if is_heartbeat:
        flags.append("heartbeat")

    if is_provider_error:
        flags.append("provider_error")

    # ── Legacy behavioral flags (backward compat) ──
    if is_retry:
        flags.append("retried")

    if not text and not has_tool_calls:
        flags.append("incomplete")
        return sorted(flags)

    if _match_any(_HEDGE, text):
        flags.append("hedged")

    if _match_any(_INCOMPLETE, text):
        flags.append("incomplete")

    # high_latency: > 2x median OR > absolute threshold
    if latency_ms is not None:
        threshold = (median_latency_ms * 2) if median_latency_ms else HIGH_LATENCY_THRESHOLD_MS
        if latency_ms > threshold:
            flags.append("high_latency")

    if _match_any(_ERROR, text):
        flags.append("error")

    if _match_any(_HUMAN_REVIEW, text):
        flags.append("human_review")

    if is_a2a or _match_any(_A2A, text):
        flags.append("a2a_delegated")

    # Speed anomaly: output too long for the latency
    # Heuristic: >500 chars output in <100ms is suspicious
    if latency_ms is not None and latency_ms < 100 and len(text) > 500:
        flags.append("speed_anomaly")

    # Latency outlier: latency < 10% of median (suspiciously fast for median-context)
    if latency_ms is not None and median_latency_ms and median_latency_ms > 0:
        if latency_ms < median_latency_ms * 0.1:
            if "speed_anomaly" not in flags:
                flags.append("speed_anomaly")

    return sorted(flags)


def _match_any(patterns: list, text: str) -> bool:
    return any(p.search(text) for p in patterns)


# ─── Aggregate Trust Signals ───────────────────────────────────────────────────

def compute_trust_signals(records: list[dict]) -> dict:
    """
    Compute aggregate Trust Score input signals from a list of ECP records.
    All signals are passive and objective. No self-reporting.

    Key distinction:
    - Agent errors: bugs/failures in the agent's own logic
    - Infra errors: API provider issues (403, 429, timeouts) — NOT agent's fault
    - Error rate only counts AGENT errors (fair to the agent)
    - Infra health is reported separately
    """
    if not records:
        return {
            "total": 0,
            "total_interactions": 0,
            "infra_errors": 0,
            "agent_errors": 0,
            "retried_rate": 0.0,
            "hedged_rate": 0.0,
            "incomplete_rate": 0.0,
            "high_latency_rate": 0.0,
            "error_rate": 0.0,
            "infra_error_rate": 0.0,
            "human_review_rate": 0.0,
            "chain_integrity": 1.0,
            "avg_latency_ms": 0,
            "reliability": 1.0,
            "availability": 1.0,
        }

    total = len(records)

    # Separate infra errors from agent work
    infra_errors = sum(1 for r in records if r.get("metadata", {}).get("is_infra_error"))
    agent_records = [r for r in records if not r.get("metadata", {}).get("is_infra_error")]
    total_interactions = len(agent_records)

    def _flag_count(flag: str, recs: "list[dict] | None" = None) -> int:
        target = recs if recs is not None else records
        return sum(1 for r in target if flag in (
            r.get("step", {}).get("flags") or r.get("meta", {}).get("flags") or []))

    # Agent errors: error flag in non-infra records
    agent_errors = _flag_count("error", agent_records)

    latencies = []
    for r in agent_records:
        lat = r.get("step", {}).get("latency_ms") or r.get("meta", {}).get("latency_ms")
        if lat:
            latencies.append(lat)

    chain_ok = _check_chain_integrity(records)

    # Reliability: % of agent interactions without errors (excludes infra)
    reliability = round((total_interactions - agent_errors) / total_interactions, 4) if total_interactions else 1.0
    # Availability: % of all attempts that weren't infra failures
    availability = round(total_interactions / total, 4) if total else 1.0

    return {
        "total": total,
        "total_interactions": total_interactions,
        "infra_errors": infra_errors,
        "agent_errors": agent_errors,
        "retried_rate": round(_flag_count("retried", agent_records) / total_interactions, 4) if total_interactions else 0.0,
        "hedged_rate": round(_flag_count("hedged", agent_records) / total_interactions, 4) if total_interactions else 0.0,
        "incomplete_rate": round(_flag_count("incomplete", agent_records) / total_interactions, 4) if total_interactions else 0.0,
        "high_latency_rate": round(_flag_count("high_latency", agent_records) / total_interactions, 4) if total_interactions else 0.0,
        "error_rate": round(agent_errors / total_interactions, 4) if total_interactions else 0.0,
        "infra_error_rate": round(infra_errors / total, 4) if total else 0.0,
        "human_review_rate": round(_flag_count("human_review", agent_records) / total_interactions, 4) if total_interactions else 0.0,
        "chain_integrity": _chain_integrity_ratio(records),
        "avg_latency_ms": int(statistics.mean(latencies)) if latencies else 0,
        "reliability": reliability,
        "availability": availability,
    }


def _chain_integrity_ratio(records: list[dict]) -> float:
    """Return chain integrity as 0.0-1.0 ratio (visited/total)."""
    if len(records) <= 1:
        return 1.0
    chained = [r for r in records if r.get("chain", {}).get("hash")]
    if not chained:
        return 1.0
    genesis = [r for r in chained if r.get("chain", {}).get("prev") == "genesis"]
    if not genesis:
        return 0.0
    key_to_next: dict[str, list] = {}
    for r in chained:
        prev = r.get("chain", {}).get("prev")
        if prev and prev != "genesis":
            key_to_next.setdefault(prev, []).append(r)
    visited = set()
    for g in genesis:
        current = g
        visited.add(current["id"])
        while True:
            current_hash = current.get("chain", {}).get("hash", "")
            current_id = current.get("id", "")
            nexts = key_to_next.get(current_hash) or key_to_next.get(current_id)
            if not nexts:
                break
            if len(nexts) > 1:
                # Fork: still walk first branch, count what we can
                current = nexts[0]
            else:
                current = nexts[0]
            if current["id"] in visited:
                break
            visited.add(current["id"])
    return round(len(visited) / len(chained), 4)


def _check_chain_integrity(records: list[dict]) -> bool:
    """
    Verify chain.prev links form valid chain(s).
    Supports multiple independent chains (different agents/sessions).
    Returns True if ALL chains are internally consistent.

    A record without a chain field (v1.0 minimal) is always valid.
    """
    if len(records) <= 1:
        return True

    # Separate chained records from chainless (v1.0 minimal)
    chained = [r for r in records if r.get("chain", {}).get("hash")]
    if not chained:
        return True  # All minimal records — no chain to verify

    # Build id→record lookup
    {r["id"]: r for r in chained}

    # Find genesis records (can be multiple for multiple agents/sessions)
    genesis = [r for r in chained if r.get("chain", {}).get("prev") == "genesis"]

    if not genesis:
        return False  # No genesis in any chain

    # Walk each chain forward via reverse lookup.
    # prev field may store record id (SDK create_record) OR chain hash (proxy record_minimal_v2).
    # Build lookup by both id and hash to support both formats.
    key_to_next: dict[str, list] = {}
    for r in chained:
        prev = r.get("chain", {}).get("prev")
        if prev and prev != "genesis":
            key_to_next.setdefault(prev, []).append(r)

    visited = set()
    for g in genesis:
        # Walk from this genesis
        current = g
        visited.add(current["id"])
        while True:
            # Try both: next record may reference current by id or by hash
            current_hash = current.get("chain", {}).get("hash", "")
            current_id = current.get("id", "")
            nexts = key_to_next.get(current_hash) or key_to_next.get(current_id)
            if not nexts:
                break
            if len(nexts) > 1:
                return False  # Fork detected
            current = nexts[0]
            if current["id"] in visited:
                return False  # Cycle detected
            visited.add(current["id"])

    # Ratio-based: a few orphaned records shouldn't tank the score
    if len(chained) == 0:
        return True
    return len(visited) / len(chained) >= 0.9
