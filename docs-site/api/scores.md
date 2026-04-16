# Scores API

Trust Score lookup for agents. Scores are pre-computed by the SDK and uploaded with each batch.

## GET /v1/scores

Retrieve trust score for a single agent.

**Query Parameters:**
| Parameter | Type | Required | Description |
|---|---|---|---|
| `agent_did` | string | Yes | Agent DID (`did:ecp:{hex}`) |

**Response (200):**
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

**Response (404):** Agent not found.

## POST /v1/scores/batch

Bulk lookup for multiple agents (max 100 per request).

**Request Body:**
```json
{
  "agent_dids": ["did:ecp:xxx", "did:ecp:yyy"]
}
```

**Response (200):**
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

## Score Dimensions (v2)

| Dimension | Weight | Description |
|---|---|---|
| `operational_reliability` | 35% | Time-weighted Bayesian error-free rate |
| `evidence_completeness` | 25% | Chain integrity + field completeness |
| `behavioral_consistency` | 20% | Daily error rate variance |
| `operational_maturity` | 10% | History length + recency |
| `data_integrity` | 10% | Anti-gaming detection |

## Authentication

No authentication required for score lookups. Scores are public data.
