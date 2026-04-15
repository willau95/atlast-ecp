"""
ATLAST ECP — Cluster Discovery

Auto-groups similar failure records by pattern.
Rule-based grouping (no ML dependencies required).
Optional scikit-learn clustering if available.
"""

import json
from collections import Counter
from typing import Optional


def discover_clusters(
    records: list,
    min_cluster_size: int = 2,
) -> list:
    """Group similar records into clusters.

    Strategy: group by (error_type, model, flag_pattern) tuple.
    Returns: [{cluster_id, label, pattern, count, records, first_ts, last_ts}]
    """
    if not records:
        return []

    # Build feature tuples for each record
    grouped = {}
    for r in records:
        # Extract features
        model = r.get("model") or r.get("meta", {}).get("model", "unknown")
        model_short = model.split("/")[-1] if "/" in model else model

        flags_raw = r.get("flags", "")
        if isinstance(flags_raw, str):
            try:
                flags_list = json.loads(flags_raw)
            except Exception:
                flags_list = [f.strip() for f in flags_raw.split(",") if f.strip()]
        else:
            flags_list = flags_raw or []

        # Determine error type
        error_type = "success"
        if r.get("error") or r.get("is_infra"):
            if r.get("is_infra"):
                error_type = "infra_error"
            elif "rate_limit" in flags_list or "429" in str(flags_list):
                error_type = "rate_limit"
            elif "error" in flags_list:
                error_type = "agent_error"
            else:
                error_type = "unknown_error"

        # Only cluster non-success records (failures are what we want to discover)
        if error_type == "success":
            continue

        # Create cluster key
        flag_key = ",".join(sorted(set(flags_list)))[:50] if flags_list else "none"
        cluster_key = "%s|%s|%s" % (error_type, model_short, flag_key)

        if cluster_key not in grouped:
            grouped[cluster_key] = {
                "error_type": error_type,
                "model": model_short,
                "flags": flag_key,
                "records": [],
            }
        grouped[cluster_key]["records"].append(r)

    # Build cluster output
    clusters = []
    for key, group in grouped.items():
        if len(group["records"]) < min_cluster_size:
            continue

        timestamps = [r.get("ts", 0) for r in group["records"]]
        label = _generate_label(group["error_type"], group["model"], group["flags"])

        clusters.append({
            "cluster_id": "clust_%s" % abs(hash(key)) % 10**8,
            "label": label,
            "pattern": {
                "error_type": group["error_type"],
                "model": group["model"],
                "flags": group["flags"],
            },
            "count": len(group["records"]),
            "record_ids": [r.get("id", "") for r in group["records"]],
            "first_ts": min(timestamps) if timestamps else 0,
            "last_ts": max(timestamps) if timestamps else 0,
        })

    # Sort by count descending
    clusters.sort(key=lambda c: c["count"], reverse=True)
    return clusters


def _generate_label(error_type: str, model: str, flags: str) -> str:
    """Generate a human-readable label for a cluster."""
    parts = []

    if error_type == "rate_limit":
        parts.append("Rate limiting")
    elif error_type == "infra_error":
        parts.append("Infrastructure failure")
    elif error_type == "agent_error":
        parts.append("Agent error")
    else:
        parts.append("Error")

    if model and model != "unknown":
        parts.append("on %s" % model)

    if flags and flags != "none":
        flag_list = flags.split(",")[:2]
        parts.append("(%s)" % ", ".join(flag_list))

    return " ".join(parts)
