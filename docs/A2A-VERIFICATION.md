# ECP A2A — Agent-to-Agent Multi-Party Verification

> Verify data integrity across multi-agent workflows. No competitor can do this.

## Why A2A Matters

In multi-agent systems (CrewAI, AutoGen, LangGraph, MetaGPT), agents pass data to each other. Three things can go wrong:

1. **Data corruption**: Agent A sends X, but Agent B receives Y
2. **Data loss**: Agent A produces output, but no downstream agent ever consumes it
3. **Blame ambiguity**: The final result is wrong — which agent broke the chain?

ECP's `in_hash` / `out_hash` design solves all three — **without exposing any content**.

## How It Works

```
Agent A                          Agent B
┌─────────────┐                  ┌─────────────┐
│ in_hash: h1 │                  │ in_hash: h3 │ ← must equal Agent A's out_hash
│ out_hash: h3│──── handoff ────▶│ out_hash: h4│
└─────────────┘                  └─────────────┘

Verification: Agent A's out_hash == Agent B's in_hash
If they match → data integrity confirmed (without seeing the data)
```

## Quick Start

### Python API

```python
from atlast_ecp.a2a import build_a2a_chain, verify_a2a_chain, format_a2a_report
from atlast_ecp.storage import load_records

# Load records from multiple agents
records_a = load_records("~/.atlast/agent-a/records.jsonl")
records_b = load_records("~/.atlast/agent-b/records.jsonl")

# Build and verify
chain = build_a2a_chain(records_a + records_b)
report = verify_a2a_chain(chain)
print(format_a2a_report(report))
```

### CLI

```bash
# Verify across multiple agent record files
atlast verify --a2a agent_a.jsonl agent_b.jsonl agent_c.jsonl

# Machine-readable output
atlast verify --a2a agent_a.jsonl agent_b.jsonl --json
```

## API Reference

### `verify_handoff(record_a, record_b) → Handoff`

Verify a single data handoff between two records.

| Field | Type | Description |
|-------|------|-------------|
| `valid` | bool | True if `out_hash == in_hash` |
| `causal_valid` | bool | True if source timestamp ≤ target timestamp |
| `source_agent` | str | Agent that produced the output |
| `target_agent` | str | Agent that consumed the input |

### `discover_handoffs(records) → A2AChain`

Auto-discover all handoff relationships in a mixed set of records.

Returns:
- `handoffs`: List of verified handoffs
- `orphan_outputs`: Outputs not consumed by any downstream agent
- `unconsumed_inputs`: Inputs with no known source
- `agents`: All agents involved

### `build_a2a_chain(records) → A2AChain`

Same as `discover_handoffs` but sorts records by timestamp first.

### `verify_a2a_chain(chain) → A2AReport`

Full chain verification:
- All handoff hashes match
- Causal consistency (no time-travel)
- Blame trace for failures

### `format_a2a_report(report) → str`

Human-readable report with ASCII topology diagram.

## Scenarios

### 1. CrewAI 3-Agent Pipeline

```
Researcher → Analyst → Writer

researcher.jsonl:
  {"agent": "researcher", "in_hash": "sha256:aa...", "out_hash": "sha256:bb...", ...}

analyst.jsonl:
  {"agent": "analyst", "in_hash": "sha256:bb...", "out_hash": "sha256:cc...", ...}

writer.jsonl:
  {"agent": "writer", "in_hash": "sha256:cc...", "out_hash": "sha256:dd...", ...}

$ atlast verify --a2a researcher.jsonl analyst.jsonl writer.jsonl
  ✅ VALID — 2 handoffs, 0 gaps
```

### 2. Parallel Fanout (A → B + C)

```
Coordinator → [Coder, Tester]

coordinator produces out_hash:xx
coder consumes in_hash:xx → different branch
tester consumes in_hash:xx → different branch

$ atlast verify --a2a coordinator.jsonl coder.jsonl tester.jsonl
  ✅ VALID — 2 handoffs (fanout detected)
```

### 3. Broken Chain (Blame Trace)

```
Agent A produces out_hash:xx
Agent B consumes in_hash:yy (MISMATCH!)

$ atlast verify --a2a a.jsonl b.jsonl
  ❌ INVALID
  Blame Trace:
    [hash_mismatch] out_hash from agent-a does not match in_hash at agent-b
```

## Format Compatibility

A2A verification works with both ECP record formats:

- **v1.0 (flat)**: `in_hash` and `out_hash` at top level
- **v0.1 (nested)**: `step.in_hash` and `step.out_hash`

You can mix formats in the same verification — records from different SDK versions work together.

## Privacy

A2A verification is **100% local**. It compares hashes — no content is ever accessed or transmitted.
