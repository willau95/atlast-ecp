# ATLAST Protocol — Platform Integration Guide

> How to integrate ATLAST Trust Scores into your platform.

## Overview

ATLAST provides verifiable trust scores for AI agents. As a platform, you can:
1. **Display trust scores** for agents registered on your platform
2. **Receive real-time updates** when agents submit new evidence batches
3. **Detect unhealthy agents** that haven't submitted data recently

## Architecture

```
Agent (user's machine)                     Your Platform
  |                                             |
  | pip install atlast-ecp                      |
  | atlast init                                 |
  |                                             |
  | Agent runs → LLM API calls intercepted      |
  | Records stored locally (~/.ecp/)            |
  |                                             |
  | Batch upload (auto: >=1000 records OR 7d)   |
  |          ↓                                  |
  |    api.weba0.com (ATLAST Server)            |
  |          |                                  |
  |          |--- webhook push ------>  POST /your-webhook
  |          |                                  |
  |          |<-- score pull ---------  GET /v1/scores?agent_did=xxx
  |          |<-- bulk pull ----------  POST /v1/scores/batch
```

## Step 1: Pull Trust Scores

### Single Agent
```
GET https://api.weba0.com/v1/scores?agent_did={DID}
```

Response:
```json
{
  "agent_did": "did:ecp:38db07b90612e76a997b00ccc7cc53b9",
  "trust_score": 742,
  "version": 2,
  "record_count": 1560,
  "total_batches": 12,
  "last_batch_at": "2026-04-16T12:00:00Z",
  "layers": {
    "operational_reliability": 0.95,
    "evidence_completeness": 0.88,
    "behavioral_consistency": 0.70,
    "operational_maturity": 0.30,
    "data_integrity": 0.92
  },
  "meta": {
    "records_analyzed": 1560,
    "interactions_scored": 1400,
    "history_days": 45.2,
    "active_days": 38,
    "models_used": 3
  },
  "ecp_version": "0.29.0"
}
```

### Bulk Lookup (up to 100 agents)
```
POST https://api.weba0.com/v1/scores/batch
Content-Type: application/json

{"agent_dids": ["did:ecp:xxx", "did:ecp:yyy", ...]}
```

Response:
```json
{
  "scores": [
    {"agent_did": "did:ecp:xxx", "trust_score": 742, ...},
    {"agent_did": "did:ecp:yyy", "trust_score": 150, ...}
  ],
  "total": 2
}
```

Agents not found return `trust_score: 150` (identity-only default).

## Step 2: Receive Webhook Notifications (Optional)

Configure your webhook URL and token in the ATLAST server environment.

### Event: `batch.uploaded`
Fired when an agent uploads a new batch of evidence records.

```
POST https://your-platform.com/webhook
X-ECP-Signature: sha256={HMAC-SHA256(body, shared_secret)}
Content-Type: application/json

{
  "event": "batch.uploaded",
  "agent_did": "did:ecp:xxx",
  "batch_id": "batch_xxx",
  "merkle_root": "sha256:xxx",
  "record_count": 48,
  "avg_latency_ms": 1200,
  "batch_ts": 1776275220373,
  "sig": "ed25519:xxx",
  "on_chain": false
}
```

### Verifying the Signature
```python
import hmac, hashlib

def verify_webhook(body: bytes, signature: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

## Step 3: Agent Health Detection

Use `last_batch_at` from the score response:

| `last_batch_at` | Meaning | Suggested Action |
|---|---|---|
| `null` | Never submitted data | Show: "Install ATLAST SDK" |
| `> 24h ago` | SDK may not be running | Show: "Agent offline" warning |
| `< 24h ago` | Healthy | Normal display |

## Step 4: Guide Users to Install ATLAST

Direct your users to install the SDK on their agent:

```bash
pip3 install atlast-ecp
atlast init
```

After installation, all LLM API calls are automatically recorded. No code changes needed.

## Trust Score v2 — Dimensions

| Dimension | Weight | What it measures |
|---|---|---|
| Operational Reliability | 35% | Time-weighted agent error-free rate |
| Evidence Completeness | 25% | Chain integrity + record field completeness |
| Behavioral Consistency | 20% | Stability of daily performance |
| Operational Maturity | 10% | History length + recent activity |
| Data Integrity | 10% | Anti-gaming (duplicate/burst detection) |

**Score ranges:**
- 900+: Exceptional (~5% of agents)
- 700-899: Good (~30%)
- 500-699: Normal (~45%)
- 300-499: Needs improvement (~15%)
- <300: Problematic (~5%)
- 150: Identity-only (no data yet)

**Volume floor:** <10 interactions = max 600, <30 = max 750, <100 = max 900.

## Fallback: Local Calculation

If the ATLAST server is unreachable, you can compute scores locally using the same formula. See [Trust Score v2 Specification](../ECP-SPEC.md) for the full algorithm.

## SDK Version

Current: **v0.29.0** on [PyPI](https://pypi.org/project/atlast-ecp/).

Check latest: `GET https://pypi.org/pypi/atlast-ecp/json` → `info.version`
