"""
ATLAST ECP Insights — local analysis of ECP records.

Usage:
    atlast insights              # Full report
    atlast insights --top 5      # Top 5 issues
    atlast insights --json       # Machine-readable output
    atlast insights --section performance|trends|tools

Analyzes locally stored ECP records to surface:
- Latency bottlenecks
- Cost hotspots (by model)
- Error/retry patterns
- Flag distribution
- Agent activity summary
- Trend analysis over time
- Tool usage patterns

Privacy: runs entirely locally. No data leaves your device.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from typing import Any, Optional


# ── Helpers ─────────────────────────────────────────────────────────────────

def _get_ts(rec: dict) -> Optional[int]:
    """Extract timestamp (epoch ms) from v0.1 or v1.0 record."""
    ts = rec.get("ts")
    if ts and isinstance(ts, (int, float)):
        return int(ts)
    # v0.1 ISO8601
    iso = rec.get("timestamp")
    if iso and isinstance(iso, str):
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return int(dt.timestamp() * 1000)
        except Exception:
            pass
    return None


def _get_meta(rec: dict) -> dict:
    """Extract meta/step data from v0.1 or v1.0 record."""
    meta = rec.get("meta", {})
    if meta:
        return meta
    # v0.1 fallback: extract from execution array
    execution = rec.get("execution", [])
    if execution and isinstance(execution, list) and len(execution) > 0:
        step = execution[0]
        result = {}
        if step.get("duration_ms"):
            result["duration_ms"] = step["duration_ms"]
        if step.get("model"):
            result["model"] = step["model"]
        if step.get("action"):
            result["tool"] = step["action"]
        return result
    return {}


def _get_action(rec: dict) -> str:
    """Extract action from v0.1 or v1.0 record."""
    return rec.get("action") or rec.get("step", {}).get("type", "unknown")


def _get_agent(rec: dict) -> str:
    """Extract agent identifier from v0.1 or v1.0 record."""
    return rec.get("agent") or rec.get("agent_did", "unknown")


# ── Sub-functions (P3-1: Insights Layer B) ──────────────────────────────────

def analyze_performance(records: list[dict]) -> dict:
    """
    Analyze performance metrics: latency, throughput, success rate, by-model breakdown.

    Returns:
        {
            "total_records": int,
            "avg_latency_ms": float,
            "p50_latency_ms": float,
            "p95_latency_ms": float,
            "max_latency_ms": float,
            "success_rate": float,         # 0.0 - 1.0
            "throughput_per_min": float,
            "by_model": {model: {count, avg_ms, p95_ms, max_ms}}
        }
    """
    if not records:
        return {
            "total_records": 0, "avg_latency_ms": 0, "p50_latency_ms": 0,
            "p95_latency_ms": 0, "max_latency_ms": 0, "success_rate": 1.0,
            "throughput_per_min": 0, "by_model": {},
        }

    latencies = []
    by_model: dict[str, list[int]] = defaultdict(list)
    error_count = 0
    timestamps = []

    for rec in records:
        meta = _get_meta(rec)
        ts = _get_ts(rec)
        if ts:
            timestamps.append(ts)

        lat = meta.get("latency_ms") or meta.get("duration_ms")
        model = meta.get("model") or "unknown"

        if lat and isinstance(lat, (int, float)):
            latencies.append(int(lat))
            by_model[model].append(int(lat))

        flags = meta.get("flags", [])
        if "error" in flags:
            error_count += 1

    total = len(records)
    success_rate = (total - error_count) / total if total else 1.0

    # Throughput
    throughput = 0.0
    if len(timestamps) >= 2:
        span_ms = max(timestamps) - min(timestamps)
        if span_ms > 0:
            throughput = total / (span_ms / 60000)

    # Latency percentiles
    avg_ms = sum(latencies) / len(latencies) if latencies else 0
    sorted_lats = sorted(latencies)
    p50 = sorted_lats[len(sorted_lats) // 2] if sorted_lats else 0
    p95 = sorted_lats[int(len(sorted_lats) * 0.95)] if len(sorted_lats) >= 2 else (sorted_lats[0] if sorted_lats else 0)
    max_ms = max(sorted_lats) if sorted_lats else 0

    # By model
    model_stats = {}
    for model, lats in sorted(by_model.items(), key=lambda x: -len(x[1])):
        s = sorted(lats)
        model_stats[model] = {
            "count": len(lats),
            "avg_ms": round(sum(lats) / len(lats)),
            "p95_ms": round(s[int(len(s) * 0.95)] if len(s) >= 2 else s[0]),
            "max_ms": max(s),
        }

    return {
        "total_records": total,
        "avg_latency_ms": round(avg_ms),
        "p50_latency_ms": round(p50),
        "p95_latency_ms": round(p95),
        "max_latency_ms": round(max_ms),
        "success_rate": round(success_rate, 4),
        "throughput_per_min": round(throughput, 2),
        "by_model": model_stats,
    }


def analyze_trends(records: list[dict], bucket: str = "day") -> dict:
    """
    Analyze time-series trends bucketed by day or hour.

    Args:
        records: ECP records
        bucket: "day" or "hour"

    Returns:
        {
            "bucket_size": "day"|"hour",
            "buckets": [{period, record_count, avg_latency_ms, error_count}]
        }
    """
    if not records:
        return {"bucket_size": bucket, "buckets": []}

    from datetime import datetime, timezone

    bucket_ms = 86400000 if bucket == "day" else 3600000  # ms
    buckets: dict[str, dict] = {}

    for rec in records:
        ts = _get_ts(rec)
        if not ts:
            continue

        # Bucket key
        dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        if bucket == "day":
            key = dt.strftime("%Y-%m-%d")
        else:
            key = dt.strftime("%Y-%m-%d %H:00")

        if key not in buckets:
            buckets[key] = {"period": key, "record_count": 0, "total_latency": 0, "latency_count": 0, "error_count": 0}

        b = buckets[key]
        b["record_count"] += 1

        meta = _get_meta(rec)
        lat = meta.get("latency_ms") or meta.get("duration_ms")
        if lat and isinstance(lat, (int, float)):
            b["total_latency"] += lat
            b["latency_count"] += 1

        flags = meta.get("flags", [])
        if "error" in flags:
            b["error_count"] += 1

    # Format output
    result = []
    for key in sorted(buckets.keys()):
        b = buckets[key]
        avg = round(b["total_latency"] / b["latency_count"]) if b["latency_count"] else 0
        result.append({
            "period": b["period"],
            "record_count": b["record_count"],
            "avg_latency_ms": avg,
            "error_count": b["error_count"],
        })

    return {"bucket_size": bucket, "buckets": result}


def analyze_tools(records: list[dict], top_n: int = 10) -> dict:
    """
    Analyze tool usage patterns.

    Returns:
        {
            "total_tool_calls": int,
            "tools": [{name, count, avg_duration_ms, error_rate}]
        }
    """
    if not records:
        return {"total_tool_calls": 0, "tools": []}

    tool_stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "total_ms": 0, "latency_count": 0, "errors": 0})
    total_tool_calls = 0

    for rec in records:
        action = _get_action(rec)
        meta = _get_meta(rec)

        # Identify tool calls
        tool = meta.get("tool") or meta.get("tool_name")
        if not tool:
            # Check if action itself indicates a tool call
            if action in ("tool_call", "function_call") or action.startswith("tool:"):
                tool = action
            else:
                continue

        total_tool_calls += 1
        t = tool_stats[tool]
        t["count"] += 1

        lat = meta.get("latency_ms") or meta.get("duration_ms")
        if lat and isinstance(lat, (int, float)):
            t["total_ms"] += lat
            t["latency_count"] += 1

        flags = meta.get("flags", [])
        if "error" in flags:
            t["errors"] += 1

    # Sort by count, take top N
    sorted_tools = sorted(tool_stats.items(), key=lambda x: -x[1]["count"])[:top_n]
    tools = []
    for name, stats in sorted_tools:
        avg_ms = round(stats["total_ms"] / stats["latency_count"]) if stats["latency_count"] else 0
        error_rate = round(stats["errors"] / stats["count"], 4) if stats["count"] else 0
        tools.append({
            "name": name,
            "count": stats["count"],
            "avg_duration_ms": avg_ms,
            "error_rate": error_rate,
        })

    return {"total_tool_calls": total_tool_calls, "tools": tools}


# ── Original aggregate function (backward compatible) ───────────────────────

def analyze_records(records: list[dict], top_n: int = 10) -> dict:
    """
    Analyze a list of ECP records and return insights.

    Returns a dict with sections: summary, latency_by_model, model_usage, flags,
    error_count, high_latency_count, recommendations.

    This is the original aggregate function. Internally delegates to sub-functions
    but maintains backward-compatible return format.
    """
    if not records:
        return {
            "summary": {"total_records": 0, "unique_agents": 0, "agents": [],
                        "action_breakdown": {}, "time_span_hours": 0,
                        "avg_latency_ms": 0, "total_tokens_in": 0,
                        "total_tokens_out": 0, "total_tokens": 0},
            "latency_by_model": {}, "model_usage": [], "flags": {},
            "error_count": 0, "high_latency_count": 0,
            "recommendations": ["No records found. Start recording with: atlast run python my_agent.py"],
        }

    # ── Summary ───────────────────────────────────────────────────────────
    total = len(records)
    agents = set()
    actions: Counter[str] = Counter()
    models: Counter[str] = Counter()
    total_latency = 0
    latency_count = 0
    total_tokens_in = 0
    total_tokens_out = 0
    flag_counter: Counter[str] = Counter()
    error_records = []
    high_latency_records = []
    timestamps = []

    for rec in records:
        agent = _get_agent(rec)
        agents.add(agent)

        action = _get_action(rec)
        actions[action] += 1

        ts = _get_ts(rec)
        if ts:
            timestamps.append(ts)

        meta = _get_meta(rec)

        model = meta.get("model")
        if model:
            models[model] += 1

        latency = meta.get("latency_ms") or meta.get("duration_ms", 0)
        if latency:
            total_latency += latency
            latency_count += 1

        if meta.get("tokens_in"):
            total_tokens_in += meta["tokens_in"]
        if meta.get("tokens_out"):
            total_tokens_out += meta["tokens_out"]

        flags = meta.get("flags", [])
        for f in flags:
            flag_counter[f] += 1

        if "error" in flags:
            error_records.append(rec)
        if "high_latency" in flags:
            high_latency_records.append(rec)

    avg_latency = total_latency / latency_count if latency_count else 0

    time_span_hours: float = 0
    if len(timestamps) >= 2:
        time_span_ms = max(timestamps) - min(timestamps)
        time_span_hours = time_span_ms / (1000 * 60 * 60)

    summary = {
        "total_records": total,
        "unique_agents": len(agents),
        "agents": sorted(agents),
        "action_breakdown": dict(actions.most_common()),
        "time_span_hours": round(time_span_hours, 1),
        "avg_latency_ms": round(avg_latency),
        "total_tokens_in": total_tokens_in,
        "total_tokens_out": total_tokens_out,
        "total_tokens": total_tokens_in + total_tokens_out,
    }

    # ── Latency Analysis ──────────────────────────────────────────────────
    latency_by_model = defaultdict(list)
    for rec in records:
        meta = _get_meta(rec)
        model = meta.get("model", "unknown")
        lat = meta.get("latency_ms") or meta.get("duration_ms")
        if lat:
            latency_by_model[model].append(lat)

    latency_insights = {}
    for model, lats in sorted(latency_by_model.items(), key=lambda x: -max(x[1])):
        latency_insights[model] = {
            "count": len(lats),
            "avg_ms": round(sum(lats) / len(lats)),
            "max_ms": max(lats),
            "min_ms": min(lats),
            "p90_ms": round(sorted(lats)[int(len(lats) * 0.9)] if len(lats) >= 2 else lats[0]),
        }

    # ── Model Usage ───────────────────────────────────────────────────────
    model_usage = []
    for model, count in models.most_common(top_n):
        pct = round(count / total * 100, 1)
        model_usage.append({"model": model, "calls": count, "percentage": pct})

    # ── Flag Analysis ─────────────────────────────────────────────────────
    flag_analysis = {}
    for flag, count in flag_counter.most_common():
        pct = round(count / total * 100, 1)
        flag_analysis[flag] = {"count": count, "percentage": pct}

    # ── Recommendations ───────────────────────────────────────────────────
    recommendations = []

    error_rate = len(error_records) / total * 100 if total else 0
    if error_rate > 5:
        recommendations.append(f"⚠️  High error rate: {error_rate:.1f}% of records have errors. Check your prompts or API reliability.")
    
    high_lat_rate = len(high_latency_records) / total * 100 if total else 0
    if high_lat_rate > 10:
        recommendations.append(f"🐌 {high_lat_rate:.1f}% of calls have high latency. Consider using a faster model or reducing prompt size.")

    if flag_counter.get("hedged", 0) / total > 0.2 if total else False:
        recommendations.append("🤔 >20% of responses are hedged. Consider more specific prompts to reduce uncertainty.")

    if flag_counter.get("retried", 0) / total > 0.1 if total else False:
        recommendations.append("🔄 >10% retry rate. Check for rate limiting or transient API errors.")

    if avg_latency > 10000:
        recommendations.append(f"⏱️  Average latency is {avg_latency/1000:.1f}s. Consider streaming or async patterns.")

    for model, stats in latency_insights.items():
        if stats["max_ms"] > 30000:
            recommendations.append(f"🔥 {model}: max latency {stats['max_ms']/1000:.1f}s. Consider timeout + retry logic.")

    if not recommendations:
        recommendations.append("✅ No major issues detected. Your agent is running well!")

    return {
        "summary": summary,
        "latency_by_model": latency_insights,
        "model_usage": model_usage,
        "flags": flag_analysis,
        "error_count": len(error_records),
        "high_latency_count": len(high_latency_records),
        "recommendations": recommendations,
    }


# ── Report Formatting ───────────────────────────────────────────────────────

def format_report(insights: dict) -> str:
    """Format insights as a human-readable report."""
    lines = []
    lines.append("\n🔗 ATLAST ECP Insights Report")
    lines.append("=" * 50)

    s = insights["summary"]
    lines.append(f"\n📊 Summary")
    lines.append(f"   Records: {s['total_records']}")
    lines.append(f"   Agents:  {s['unique_agents']} ({', '.join(s.get('agents', [])[:5])})")
    lines.append(f"   Period:  {s['time_span_hours']}h")
    if s["avg_latency_ms"]:
        lines.append(f"   Avg latency: {s['avg_latency_ms']}ms")
    if s["total_tokens"]:
        lines.append(f"   Tokens: {s['total_tokens']:,} ({s['total_tokens_in']:,} in / {s['total_tokens_out']:,} out)")

    actions = s.get("action_breakdown", {})
    if actions:
        lines.append(f"\n📋 Actions")
        for action, count in actions.items():
            lines.append(f"   {action}: {count}")

    models = insights.get("model_usage", [])
    if models:
        lines.append(f"\n🤖 Model Usage")
        for m in models:
            lines.append(f"   {m['model']}: {m['calls']} calls ({m['percentage']}%)")

    latency = insights.get("latency_by_model", {})
    if latency:
        lines.append(f"\n⏱️  Latency by Model")
        for model, stats in latency.items():
            lines.append(f"   {model}: avg {stats['avg_ms']}ms, p90 {stats['p90_ms']}ms, max {stats['max_ms']}ms")

    flags = insights.get("flags", {})
    if flags:
        lines.append(f"\n🚩 Flags Detected")
        for flag, info in flags.items():
            lines.append(f"   {flag}: {info['count']} ({info['percentage']}%)")

    recs = insights.get("recommendations", [])
    if recs:
        lines.append(f"\n💡 Recommendations")
        for r in recs:
            lines.append(f"   {r}")

    lines.append("")
    return "\n".join(lines)


def format_performance_report(perf: dict) -> str:
    """Format performance analysis as a human-readable report."""
    lines = ["\n⚡ Performance Analysis", "=" * 40]
    lines.append(f"   Records:    {perf['total_records']}")
    lines.append(f"   Avg:        {perf['avg_latency_ms']}ms")
    lines.append(f"   P50:        {perf['p50_latency_ms']}ms")
    lines.append(f"   P95:        {perf['p95_latency_ms']}ms")
    lines.append(f"   Max:        {perf['max_latency_ms']}ms")
    lines.append(f"   Success:    {perf['success_rate']*100:.1f}%")
    lines.append(f"   Throughput: {perf['throughput_per_min']}/min")
    if perf["by_model"]:
        lines.append(f"\n   By Model:")
        for m, s in perf["by_model"].items():
            lines.append(f"     {m}: {s['count']} calls, avg {s['avg_ms']}ms, p95 {s['p95_ms']}ms")
    lines.append("")
    return "\n".join(lines)


def format_trends_report(trends: dict) -> str:
    """Format trends analysis as a human-readable report."""
    lines = [f"\n📈 Trends (by {trends['bucket_size']})", "=" * 40]
    for b in trends["buckets"]:
        err_str = f" ⚠️{b['error_count']}err" if b["error_count"] else ""
        lines.append(f"   {b['period']}: {b['record_count']} records, avg {b['avg_latency_ms']}ms{err_str}")
    if not trends["buckets"]:
        lines.append("   No time-series data available.")
    lines.append("")
    return "\n".join(lines)


def format_tools_report(tools: dict) -> str:
    """Format tools analysis as a human-readable report."""
    lines = ["\n🔧 Tool Usage", "=" * 40]
    lines.append(f"   Total tool calls: {tools['total_tool_calls']}")
    for t in tools["tools"]:
        err_str = f" ({t['error_rate']*100:.0f}% err)" if t["error_rate"] > 0 else ""
        lines.append(f"   {t['name']}: {t['count']}x, avg {t['avg_duration_ms']}ms{err_str}")
    if not tools["tools"]:
        lines.append("   No tool calls detected.")
    lines.append("")
    return "\n".join(lines)


# ── CLI Entry Point ─────────────────────────────────────────────────────────

def cmd_insights(args: list[str]):
    """CLI entry point for 'atlast insights'."""
    from .storage import load_records

    limit = 1000
    top_n = 10
    as_json = "--json" in args
    section = None
    bucket = "day"

    for i, a in enumerate(args):
        if a == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])
        if a == "--top" and i + 1 < len(args):
            top_n = int(args[i + 1])
        if a == "--section" and i + 1 < len(args):
            section = args[i + 1].lower()
        if a == "--bucket" and i + 1 < len(args):
            bucket = args[i + 1].lower()

    records = load_records(limit=limit)

    if section:
        if section in ("performance", "perf"):
            result = analyze_performance(records)
            if as_json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(format_performance_report(result))
        elif section == "trends":
            result = analyze_trends(records, bucket=bucket)
            if as_json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(format_trends_report(result))
        elif section == "tools":
            result = analyze_tools(records, top_n=top_n)
            if as_json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(format_tools_report(result))
        else:
            print(f"Unknown section: {section}")
            print("Available sections: performance, trends, tools")
            sys.exit(1)
    else:
        # Original behavior: full report
        insights = analyze_records(records, top_n=top_n)
        if as_json:
            print(json.dumps(insights, indent=2, ensure_ascii=False))
        else:
            print(format_report(insights))
