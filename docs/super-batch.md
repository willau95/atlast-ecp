# Super-Batch Aggregation

**Status:** Design  
**Phase:** 7  

## Problem

Each agent uploads its own batch → 1 EAS attestation per agent per hour.
At 1,000 agents: 1,000 tx/hour × ~$0.001 = $24/day = **$720/month**.

## Solution: Super-Batch

Aggregate multiple agents' Merkle roots into a **single** on-chain attestation.

```
Agent A → merkle_root_a ─┐
Agent B → merkle_root_b ──┤
Agent C → merkle_root_c ──┤→ Super Merkle Root → 1 EAS attestation
...                        │
Agent N → merkle_root_n ─┘
```

### Cost at Scale

| Agents | Without Super-Batch | With Super-Batch | Savings |
|--------|-------------------|-----------------|---------|
| 100 | $72/mo | $3/mo | 96% |
| 1,000 | $720/mo | $3/mo | 99.6% |
| 10,000 | $7,200/mo | $3-10/mo | 99.9% |

## Architecture

### 1. Batch Collection (existing)

Each agent uploads its batch to ATLAST API as usual:
```
POST /v1/batches
{merkle_root, agent_did, record_count, ...}
```

No change needed on the SDK side.

### 2. Super-Batch Assembly (Server-side, new)

The anchor cron (currently per-batch) groups pending batches:

```python
# Pseudo-code
pending = get_pending_batches()  # Returns all pending agent batches
if len(pending) == 0:
    return

# Build super Merkle tree from individual batch Merkle roots
roots = [b["merkle_root"] for b in pending]
super_root, layers = build_merkle_tree(roots)

# Single EAS attestation for ALL agents
attestation = write_attestation(
    merkle_root=super_root,
    agent_did="did:ecp:atlast-server",  # Server signs the super-batch
    record_count=sum(b["record_count"] for b in pending),
    ...
)
```

### 3. Per-Agent Proof (new field in webhook)

Each agent's batch gets a **Merkle proof** showing its root is included in the super-batch:

```json
{
  "event": "attestation.anchored",
  "batch_id": "batch_abc",
  "agent_did": "did:ecp:agent-1",
  "super_batch_id": "super_abc",
  "super_merkle_root": "sha256:...",
  "inclusion_proof": [
    {"hash": "sha256:...", "position": "right"},
    {"hash": "sha256:...", "position": "left"}
  ],
  "attestation_uid": "0x..."
}
```

### 4. Verification

Anyone can verify:
1. Agent's `merkle_root` → via `inclusion_proof` → equals `super_merkle_root`
2. `super_merkle_root` → on-chain EAS attestation → immutable

## Server Changes Required

1. **New table**: `super_batches` (id, super_merkle_root, attestation_uid, batch_count, created_at)
2. **Modified anchor cron**: Group pending → build super tree → single EAS tx → individual webhooks with proofs
3. **New endpoint**: `GET /v1/super-batches/{id}` — public verification
4. **Config**: `SUPER_BATCH_MIN_SIZE` (default: 5) — minimum batches before super-batching

## SDK Changes Required

None. Super-batching is fully server-side. SDK batch upload is unchanged.

## Migration

- When `SUPER_BATCH_MIN_SIZE=1`: equivalent to current behavior (one batch per tx)
- Gradual rollout: start with MIN_SIZE=5, increase as agent count grows
- Backward compatible: individual `/v1/verify/{uid}` still works

## Timeline

- Phase 7: Design doc (this) + server implementation
- Phase 8: Enable by default with MIN_SIZE=10
