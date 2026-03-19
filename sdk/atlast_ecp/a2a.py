"""
ATLAST ECP A2A — Agent-to-Agent Multi-Party Verification

Verifies data integrity across multi-agent workflows:
- Handoff verification: Agent A's out_hash == Agent B's in_hash
- Orphan detection: outputs not consumed by any downstream agent
- Blame trace: pinpoint which agent/record broke the chain
- DAG topology: supports parallel agent pipelines, not just linear chains

Usage:
    from atlast_ecp.a2a import discover_handoffs, build_a2a_chain, verify_a2a_chain

    records = load_records("agent_a.jsonl") + load_records("agent_b.jsonl")
    chain = build_a2a_chain(records)
    result = verify_a2a_chain(chain)
    print(format_a2a_report(result))

Privacy: runs entirely locally. No data leaves your device.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ─── Data Models ───


@dataclass
class Handoff:
    """A verified data handoff between two agents."""
    source_agent: str
    source_record_id: str
    target_agent: str
    target_record_id: str
    hash_value: str  # the matching out_hash/in_hash
    source_ts: int
    target_ts: int
    valid: bool = True  # hash match
    causal_valid: bool = True  # source_ts <= target_ts


@dataclass
class A2AChain:
    """DAG of agent interactions discovered from ECP records."""
    agents: list[str] = field(default_factory=list)
    handoffs: list[Handoff] = field(default_factory=list)
    orphan_outputs: list[dict] = field(default_factory=list)  # outputs not consumed
    unconsumed_inputs: list[dict] = field(default_factory=list)  # inputs with no source
    records: list[dict] = field(default_factory=list)
    record_count: int = 0


@dataclass
class A2AReport:
    """Verification result for an A2A chain."""
    valid: bool = True
    total_handoffs: int = 0
    valid_handoffs: int = 0
    invalid_handoffs: int = 0
    causal_violations: int = 0
    orphan_count: int = 0
    agents: list[str] = field(default_factory=list)
    blame_trace: list[dict] = field(default_factory=list)
    chain: Optional[A2AChain] = None


# ─── Field Extraction (v0.1 + v1.0 compat) ───


def _get_in_hash(record: dict) -> Optional[str]:
    """Extract in_hash from v0.1 or v1.0 record."""
    if "in_hash" in record:
        return record["in_hash"]
    step = record.get("step", {})
    if isinstance(step, dict) and "in_hash" in step:
        return step["in_hash"]
    return None


def _get_out_hash(record: dict) -> Optional[str]:
    """Extract out_hash from v0.1 or v1.0 record."""
    if "out_hash" in record:
        return record["out_hash"]
    step = record.get("step", {})
    if isinstance(step, dict) and "out_hash" in step:
        return step["out_hash"]
    return None


def _get_agent(record: dict) -> str:
    """Extract agent identifier from v0.1 or v1.0 record."""
    return record.get("agent") or record.get("agent_did") or "unknown"


def _get_ts(record: dict) -> int:
    """Extract timestamp."""
    return record.get("ts", 0)


def _get_id(record: dict) -> str:
    """Extract record ID."""
    return record.get("id", "unknown")


# ─── Core Functions ───


def verify_handoff(record_a: dict, record_b: dict) -> Handoff:
    """
    Verify a single handoff: record_a.out_hash should equal record_b.in_hash.

    Returns a Handoff with valid=True if hashes match, valid=False otherwise.
    Also checks causal consistency (source timestamp <= target timestamp).
    """
    out_hash = _get_out_hash(record_a)
    in_hash = _get_in_hash(record_b)
    ts_a = _get_ts(record_a)
    ts_b = _get_ts(record_b)

    hash_match = out_hash is not None and in_hash is not None and out_hash == in_hash

    return Handoff(
        source_agent=_get_agent(record_a),
        source_record_id=_get_id(record_a),
        target_agent=_get_agent(record_b),
        target_record_id=_get_id(record_b),
        hash_value=out_hash or "",
        source_ts=ts_a,
        target_ts=ts_b,
        valid=hash_match,
        causal_valid=ts_a <= ts_b if (ts_a and ts_b) else True,
    )


def discover_handoffs(records: list[dict]) -> A2AChain:
    """
    Discover all handoff relationships in a mixed set of multi-agent records.

    Algorithm:
    1. Index all in_hash values → record mapping
    2. For each record's out_hash, find matching in_hash in a different agent
    3. Build handoff list + identify orphan outputs (unmatched out_hash)

    Supports parallel topologies (A → B, A → C).
    """
    if not records:
        return A2AChain()

    # Index: in_hash → list of records that consume it
    in_hash_index: dict[str, list[dict]] = {}
    for r in records:
        ih = _get_in_hash(r)
        if ih:
            in_hash_index.setdefault(ih, []).append(r)

    # Index: out_hash → list of records that produce it
    out_hash_index: dict[str, list[dict]] = {}
    for r in records:
        oh = _get_out_hash(r)
        if oh:
            out_hash_index.setdefault(oh, []).append(r)

    handoffs: list[Handoff] = []
    matched_out_hashes: set[str] = set()  # track which outputs were consumed
    matched_in_records: set[str] = set()  # track which inputs have a source

    for r in records:
        oh = _get_out_hash(r)
        if not oh:
            continue
        agent_a = _get_agent(r)

        # Find all records that consume this output
        consumers = in_hash_index.get(oh, [])
        for consumer in consumers:
            agent_b = _get_agent(consumer)
            if agent_b == agent_a and _get_id(consumer) == _get_id(r):
                continue  # skip self-match

            handoff = verify_handoff(r, consumer)
            handoffs.append(handoff)
            matched_out_hashes.add(oh + ":" + _get_id(r))
            matched_in_records.add(_get_id(consumer))

    # Find orphan outputs (produced but never consumed by another agent)
    orphans = []
    for r in records:
        oh = _get_out_hash(r)
        if oh and (oh + ":" + _get_id(r)) not in matched_out_hashes:
            orphans.append({
                "agent": _get_agent(r),
                "record_id": _get_id(r),
                "out_hash": oh,
                "ts": _get_ts(r),
            })

    # Find unconsumed inputs (consumed but no known source)
    unconsumed = []
    for r in records:
        ih = _get_in_hash(r)
        if ih and _get_id(r) not in matched_in_records:
            # Check if any record produces this hash
            producers = out_hash_index.get(ih, [])
            has_external_producer = any(
                _get_agent(p) != _get_agent(r) or _get_id(p) != _get_id(r)
                for p in producers
            )
            if not has_external_producer:
                unconsumed.append({
                    "agent": _get_agent(r),
                    "record_id": _get_id(r),
                    "in_hash": ih,
                    "ts": _get_ts(r),
                })

    agents = sorted(set(_get_agent(r) for r in records))

    return A2AChain(
        agents=agents,
        handoffs=handoffs,
        orphan_outputs=orphans,
        unconsumed_inputs=unconsumed,
        records=records,
        record_count=len(records),
    )


def build_a2a_chain(records: list[dict]) -> A2AChain:
    """
    Build an A2A chain from mixed multi-agent records.
    Alias for discover_handoffs with sorted records.
    """
    sorted_records = sorted(records, key=lambda r: _get_ts(r))
    return discover_handoffs(sorted_records)


def verify_a2a_chain(chain: A2AChain) -> A2AReport:
    """
    Verify the entire A2A chain:
    1. All handoff hashes match
    2. Causal consistency (source_ts <= target_ts)
    3. Identify blame trace for failures
    """
    blame: list[dict] = []

    valid_count = 0
    invalid_count = 0
    causal_violations = 0

    for h in chain.handoffs:
        if h.valid:
            valid_count += 1
        else:
            invalid_count += 1
            blame.append({
                "type": "hash_mismatch",
                "source_agent": h.source_agent,
                "source_record": h.source_record_id,
                "target_agent": h.target_agent,
                "target_record": h.target_record_id,
                "detail": f"out_hash from {h.source_agent} does not match in_hash at {h.target_agent}",
            })

        if not h.causal_valid:
            causal_violations += 1
            blame.append({
                "type": "causal_violation",
                "source_agent": h.source_agent,
                "source_record": h.source_record_id,
                "source_ts": h.source_ts,
                "target_agent": h.target_agent,
                "target_record": h.target_record_id,
                "target_ts": h.target_ts,
                "detail": f"{h.target_agent} received data before {h.source_agent} produced it",
            })

    overall_valid = invalid_count == 0 and causal_violations == 0

    return A2AReport(
        valid=overall_valid,
        total_handoffs=len(chain.handoffs),
        valid_handoffs=valid_count,
        invalid_handoffs=invalid_count,
        causal_violations=causal_violations,
        orphan_count=len(chain.orphan_outputs),
        agents=chain.agents,
        blame_trace=blame,
        chain=chain,
    )


def format_a2a_report(report: A2AReport) -> str:
    """Format A2A verification result as human-readable text with ASCII DAG."""
    lines = []
    lines.append("=" * 60)
    lines.append("  ECP A2A Multi-Agent Verification Report")
    lines.append("=" * 60)
    lines.append("")

    # Status
    status = "✅ VALID" if report.valid else "❌ INVALID"
    lines.append(f"  Status: {status}")
    lines.append(f"  Agents: {', '.join(report.agents)}")
    lines.append(f"  Handoffs: {report.total_handoffs} ({report.valid_handoffs} valid, {report.invalid_handoffs} invalid)")
    if report.causal_violations:
        lines.append(f"  ⚠️  Causal violations: {report.causal_violations}")
    if report.orphan_count:
        lines.append(f"  ⚠️  Orphan outputs: {report.orphan_count}")
    lines.append("")

    # Topology (ASCII DAG)
    if report.chain and report.chain.handoffs:
        lines.append("  Topology:")
        seen_edges = set()
        for h in report.chain.handoffs:
            edge = f"{h.source_agent} → {h.target_agent}"
            if edge not in seen_edges:
                symbol = "✅" if h.valid else "❌"
                lines.append(f"    {symbol} {edge}")
                seen_edges.add(edge)
        lines.append("")

    # Blame trace
    if report.blame_trace:
        lines.append("  Blame Trace:")
        for b in report.blame_trace:
            lines.append(f"    ❌ [{b['type']}] {b['detail']}")
            lines.append(f"       Source: {b['source_agent']}#{b['source_record']}")
            lines.append(f"       Target: {b['target_agent']}#{b['target_record']}")
        lines.append("")

    # Orphans
    if report.chain and report.chain.orphan_outputs:
        lines.append("  Orphan Outputs (not consumed by any downstream agent):")
        for o in report.chain.orphan_outputs[:10]:  # limit display
            lines.append(f"    ⚠️  {o['agent']}#{o['record_id']} → {o['out_hash'][:30]}...")
        if len(report.chain.orphan_outputs) > 10:
            lines.append(f"    ... and {len(report.chain.orphan_outputs) - 10} more")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)
