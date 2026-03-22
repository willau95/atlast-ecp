# ATLAST Anti-Abuse Framework

**Version:** 1.0  
**Date:** 2026-03-22

## 1. Attack Surface Analysis

### 1.1 Threat Model

| Threat | Vector | Impact | Severity |
|--------|--------|--------|----------|
| Batch Spam | Flood server with empty/duplicate batches | DoS, storage waste, Gas waste | High |
| Timestamp Forgery | Fake `batch_ts` to manipulate freshness/ordering | Trust Score gaming | Medium |
| Sybil Attack | Create many agent identities to inflate leaderboard | Leaderboard pollution | Medium |
| Flag Manipulation | Under-report `error`/`retried` flags | Artificially high Trust Score | Medium |
| Cherry-Pick Batches | Only submit successful runs, skip failures | Survivorship bias in Trust Score | High |
| Gas Abuse (Self-Deploy) | Open-source deployer anchors excessive transactions | Gas cost drain | Medium |
| Replay Attack | Re-submit old batches to inflate volume | Volume gaming | Low |

### 1.2 Defense Layers

```
Layer 1 — SDK-side (client)
  ├── Minimum batch interval (default 60s)
  ├── Maximum records per batch (default 1000)
  └── Automatic flag detection (SDK-observed, not self-reported)

Layer 2 — Server-side (API)
  ├── Rate limiting (slowapi: 100 req/min per agent)
  ├── Timestamp drift detection (reject if |batch_ts - server_ts| > 5 min)
  ├── Duplicate Merkle root rejection (same root = same batch)
  └── HMAC webhook verification

Layer 3 — Protocol-level (Trust Score)
  ├── Passive behavioral signals only (no self-reporting)
  ├── Consistency checks (batch frequency, record count variance)
  └── Chain integrity verification (Phase 7+)
```

## 2. Batch Spam Detection (C2)

### Rules

1. **Same agent, same minute**: Max 1 batch per agent per 60 seconds.
2. **Empty batches**: Reject batches with `record_count = 0`.
3. **Duplicate Merkle root**: If `merkle_root` already exists for this agent, reject (idempotency key).

### Implementation

Server-side middleware in `batch.py`:
```python
# Check: same agent submitted within last 60s?
last_batch = await db.get_last_batch(agent_did)
if last_batch and (now - last_batch.ts) < 60_000:
    raise HTTPException(429, "Rate limit: max 1 batch per 60 seconds per agent")

# Check: duplicate merkle root?
existing = await db.get_batch_by_merkle(agent_did, merkle_root)
if existing:
    return {"status": "duplicate", "batch_id": existing.id}  # Idempotent
```

## 3. Timestamp Forgery Prevention (C3)

### Rules

1. **Server-side validation**: `|batch_ts - server_ts| ≤ 300_000ms` (5 minutes).
2. **Batches outside window**: Accepted but flagged with `timestamp_drift: true`.
3. **Extreme drift (>1 hour)**: Rejected outright.

### Implementation

```python
drift_ms = abs(batch_ts - int(time.time() * 1000))
if drift_ms > 3_600_000:  # 1 hour
    raise HTTPException(400, "batch_ts too far from server time")
if drift_ms > 300_000:  # 5 minutes
    batch.flags["timestamp_drift"] = True
```

## 4. Trust Score Anti-Gaming (C4)

### Design Principles

1. **No self-reported metrics in Trust Score**: Trust derives only from SDK-detected behavioral signals (`detect_flags()` in signals.py). Agents cannot influence their own scores by reporting favorable data.

2. **Consistency dimension (β=0.35)**: Rewards agents that submit batches **regularly** over time, not agents that cherry-pick good runs. Measured by:
   - `active_days / total_days` ratio
   - Batch frequency variance (low variance = more consistent)
   - Total evidence volume (long track record)

3. **Cherry-pick detection**: If an agent's `error` rate suddenly drops to 0% after a history of ~5%, this is anomalous. β consistency dimension captures this via variance analysis.

4. **Sybil resistance**: New agents start at score 0 (not mid-range). Building a high score requires sustained, consistent evidence over time. Creating new identities resets the score — there's no advantage.

## 5. Self-Deploy Gas Abuse Prevention (C5)

### Scenario

ATLAST is open-source. Anyone can deploy their own ECP Server. If they use the same EAS schema, they anchor attestations on our schema — potentially exhausting gas from the shared wallet.

### Mitigations

1. **EAS wallet is server-private**: The private key is never in SDK code or public repos.
2. **Super-batch aggregation**: Server batches 1000+ agent batches into a single EAS attestation. Even high-volume self-deployers produce minimal chain transactions.
3. **Schema separation**: Self-deployers must create their own EAS schema. ATLAST schema UID is hardcoded on our server only.
4. **Future: API key quotas**: Rate limit anchoring per API key (Phase 7+).

## 6. SDK-Side Throttling (C6)

### Default Limits

| Parameter | Default | Configurable |
|-----------|---------|-------------|
| `min_batch_interval_s` | 60 | Yes (`ATLAST_BATCH_INTERVAL`) |
| `max_records_per_batch` | 1000 | Yes (`ATLAST_MAX_BATCH_SIZE`) |
| `max_retry_queue_size` | 100 | Yes |
| `batch_upload_timeout_s` | 10 | Yes |

### Enforcement

```python
# In batch.py run_batch():
if (time.time() * 1000 - state.get("last_batch_ts", 0)) < min_interval_ms:
    return {"status": "throttled"}
```
