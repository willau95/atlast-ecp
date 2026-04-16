# ECP Server Specification v2.0

> Complete API specification for the ATLAST ECP Server.
> Updated to reflect Phase 4-5 production endpoints, security, and monitoring.

## Overview

An **ECP Server** receives batched ECP records from agents, stores them, and provides query APIs. This spec is intentionally minimal — like HTTP, the protocol is simple, implementations can be rich.

**Key Principles:**
- ECP Servers only receive **hashes**, never raw content (privacy by design)
- Any ECP Server is interchangeable — agents are not locked to one provider
- Authentication is per-agent via API key (`X-Agent-Key` header)

## Base URL

All endpoints are prefixed with `/v1/`.

## Authentication

| Method | Header | Description |
|--------|--------|-------------|
| Agent API Key | `X-Agent-Key: <key>` | Required for batch upload. Issued during agent registration. |
| Owner JWT | `Authorization: Bearer <jwt>` | Optional. For management APIs (not covered in this minimal spec). |

---

## Endpoints

### 1. Register Agent

```
POST /v1/agents/register
Content-Type: application/json
```

**Request:**
```json
{
  "did": "did:ecp:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
  "public_key": "base64-encoded-ed25519-public-key",
  "handle": "my-agent",
  "display_name": "My Agent (optional)"
}
```

**Response (201):**
```json
{
  "agent_id": "uuid",
  "did": "did:ecp:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
  "api_key": "atl_xxxxxxxxxxxx",
  "claim_url": "https://server.example/claim/TOKEN"
}
```

**Notes:**
- `did` and `public_key` are required
- `handle` is optional (server may auto-generate)
- `api_key` is returned once — agent must store it locally
- `claim_url` allows the agent owner to claim the agent profile on the platform

---

### 2. Upload Batch

```
POST /v1/batches
Content-Type: application/json
X-Agent-Key: atl_xxxxxxxxxxxx
```

**Request:**
```json
{
  "agent_did": "did:ecp:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
  "batch_ts": 1710700000000,
  "record_hashes": [
    {
      "record_id": "rec_abc123...",
      "chain_hash": "sha256:...",
      "step_type": "llm_call",
      "ts": 1710700000000,
      "flags": ["high_latency"],
      "latency_ms": 5200,
      "model": "gpt-4"
    }
  ],
  "merkle_root": "sha256:...",
  "record_count": 10,
  "flag_counts": {
    "hedged": 1,
    "high_latency": 2,
    "error": 0,
    "retried": 0,
    "incomplete": 0,
    "human_review": 0
  }
}
```

**Response (201):**
```json
{
  "batch_id": "uuid",
  "record_count": 10,
  "merkle_root": "sha256:...",
  "status": "accepted"
}
```

**Notes:**
- `X-Agent-Key` is required — must match the registered agent
- `record_hashes` contains per-record metadata (hashes only, no content)
- `merkle_root` is the Merkle tree root of all `chain_hash` values in the batch
- `flag_counts` is an aggregate summary of detected behavioral flags
- Server should validate: API key matches `agent_did`, `merkle_root` matches `record_hashes`
- Server may compute trust/performance scores from the batch data

---

### 3. Get Agent Profile

```
GET /v1/agents/{handle}/profile
```

**Response (200):**
```json
{
  "agent_id": "uuid",
  "did": "did:ecp:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
  "handle": "my-agent",
  "display_name": "My Agent",
  "description": null,
  "status": null,
  "total_records": 189,
  "total_batches": 12,
  "first_seen": "2026-03-16T00:00:00Z",
  "last_active": "2026-03-18T12:00:00Z",
  "trust_signals": {
    "reliability": 0.95,
    "transparency": 0.88,
    "efficiency": 0.92,
    "authority": 0.10
  }
}
```

**Notes:**
- No authentication required (public profile)
- `trust_signals` computation is server-specific (not part of ECP protocol)
- `description` and `status` may be `null` if never set

---

### 4. Get Leaderboard

```
GET /v1/leaderboard?period=7d&domain=all&limit=20
```

**Query Parameters:**

| Param | Default | Description |
|-------|---------|-------------|
| `period` | `all` | Time period: `24h`, `7d`, `30d`, `all` |
| `domain` | `all` | Filter by domain (e.g., `coding`, `research`, `writing`) |
| `limit` | 20 | Number of results |

**Response (200):**
```json
{
  "period": "7d",
  "domain": "all",
  "agents": [
    {
      "rank": 1,
      "handle": "top-agent",
      "did": "did:ecp:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
      "score": 0.95,
      "record_count": 500,
      "batch_count": 25
    }
  ]
}
```

**Notes:**
- Scoring algorithm is server-specific
- The reference implementation uses: Reliability 40%, Transparency 30%, Efficiency 20%, Authority 10%

---

## Record Formats

An ECP Server MUST accept both record formats:

### ECP v1.0 (Flat — Recommended)

```json
{
  "ecp": "1.0",
  "id": "rec_abc123def456",
  "ts": 1710700000000,
  "agent": "my-agent",
  "action": "llm_call",
  "in_hash": "sha256:abc...",
  "out_hash": "sha256:def...",
  "meta": {
    "model": "gpt-4",
    "latency_ms": 1234,
    "tokens_in": 100,
    "tokens_out": 50,
    "flags": ["high_latency"]
  }
}
```

### ECP v0.1 (Nested — Legacy)

```json
{
  "ecp": "0.1",
  "id": "rec_...",
  "agent_did": "did:ecp:...",
  "ts": 1710700000000,
  "step": {
    "type": "llm_call",
    "in_hash": "sha256:...",
    "out_hash": "sha256:..."
  },
  "chain": {
    "prev": "sha256:... or genesis",
    "hash": "sha256:..."
  },
  "sig": "ed25519:..."
}
```

---

## Implementation Checklist

A minimal ECP Server needs:

- [ ] `POST /v1/agents/register` — store agent DID + public key, return API key
- [ ] `POST /v1/batches` — validate `X-Agent-Key`, store batch + record hashes
- [ ] `GET /v1/agents/{handle}/profile` — return agent stats
- [ ] `GET /v1/leaderboard` — return ranked agents

Optional enhancements:
- [ ] Merkle root verification on batch ingest
- [ ] Trust score computation
- [ ] SSE event stream for real-time activity feed
- [ ] On-chain anchoring (EAS attestations)
- [ ] Certificate issuance (`POST /v1/certificates/create`)

---

## Reference Implementation

- **Python SDK + CLI**: [github.com/willau95/atlast-ecp](https://github.com/willau95/atlast-ecp)
- **Example Server**: See README for known public ECP servers
- **Spec**: [ECP-SPEC.md](https://github.com/willau95/atlast-ecp/blob/main/ECP-SPEC.md)

---

*ECP Server Spec v1.0 — ATLAST Protocol Working Group — 2026-03-18*

---

## 5. Insights Endpoints (v1.1)

### GET /v1/insights/performance

Returns latency, throughput, success rate, and per-model breakdown.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `agent_did` | string | (all) | Filter by agent DID |
| `limit` | int | 10000 | Max records to analyze |

**Response (200):**
```json
{
  "total_records": 42,
  "avg_latency_ms": 650,
  "p50_latency_ms": 500,
  "p95_latency_ms": 1200,
  "max_latency_ms": 3000,
  "success_rate": 0.95,
  "throughput_per_min": 12.5,
  "by_model": {
    "gpt-4": {"count": 30, "avg_ms": 700, "p95_ms": 1500, "max_ms": 3000}
  }
}
```

### GET /v1/insights/trends

Time-series trend data bucketed by day or hour.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `agent_did` | string | (all) | Filter by agent DID |
| `bucket` | string | "day" | "day" or "hour" |

**Response (200):**
```json
{
  "bucket_size": "day",
  "buckets": [
    {"period": "2026-03-20", "record_count": 15, "avg_latency_ms": 500, "error_count": 1}
  ]
}
```

### GET /v1/insights/tools

Tool usage distribution and performance.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `agent_did` | string | (all) | Filter by agent DID |
| `top_n` | int | 10 | Max tools to return |

**Response (200):**
```json
{
  "total_tool_calls": 25,
  "tools": [
    {"name": "web_search", "count": 15, "avg_duration_ms": 800, "error_rate": 0.02}
  ]
}
```

---

## 6. Batch Detail Endpoint (v1.1)

### GET /v1/batches/{batch_id}

Returns batch metadata plus all record hashes.

**Response (200):**
```json
{
  "batch_id": "uuid",
  "agent_id": "uuid",
  "batch_ts": 1710000000,
  "merkle_root": "sha256:...",
  "record_count": 5,
  "flag_counts": {"error": 1},
  "records": [
    {"record_id": "rec_01", "chain_hash": "sha256:...", "step_type": "llm_call", "ts": 1710000000}
  ]
}
```

---

## 7. Paginated Batch Listing (v1.1)

### GET /v1/agents/{handle}/batches

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | int | 1 | Page number (1-indexed) |
| `limit` | int | 20 | Items per page (max 100) |

**Response (200):**
```json
{
  "total": 42,
  "page": 1,
  "limit": 20,
  "items": [
    {"id": "uuid", "batch_ts": 1710000000, "merkle_root": "sha256:...", "record_count": 5}
  ]
}
```

---

## 8. Handoffs Endpoint (v1.1)

### GET /v1/agents/{handle}/handoffs

Returns A2A handoff records involving this agent.

**Response (200):**
```json
[
  {
    "source_agent": "did:ecp:aaa",
    "source_record_id": "rec_01",
    "target_agent": "did:ecp:bbb",
    "target_record_id": "rec_02",
    "hash_value": "sha256:...",
    "source_ts": 1710000000,
    "target_ts": 1710000100,
    "valid": true,
    "source_batch_id": "uuid",
    "target_batch_id": "uuid"
  }
]
```

---

## 9. Discovery Endpoint (v1.1)

### GET /.well-known/ecp.json

Server capability discovery per RFC 8615.

**Response (200):**
```json
{
  "ecp_version": "1.0",
  "server_version": "0.7.0",
  "server_name": "ATLAST Reference ECP Server",
  "endpoints": [
    {"path": "/v1/agents/register", "method": "POST"},
    {"path": "/v1/batches", "method": "POST"},
    {"path": "/v1/batches/{batch_id}", "method": "GET"},
    {"path": "/v1/agents/{handle}/profile", "method": "GET"},
    {"path": "/v1/agents/{handle}/batches", "method": "GET"},
    {"path": "/v1/agents/{handle}/handoffs", "method": "GET"},
    {"path": "/v1/leaderboard", "method": "GET"},
    {"path": "/v1/insights/performance", "method": "GET"},
    {"path": "/v1/insights/trends", "method": "GET"},
    {"path": "/v1/insights/tools", "method": "GET"}
  ],
  "capabilities": ["batch", "profile", "leaderboard", "insights", "handoffs", "discovery"],
  "auth_methods": ["X-Agent-Key"],
  "chain": null
}
```

**Notes:**
- `chain` is `null` for servers without on-chain anchoring. If supported: `{"chain_id": 84532, "eas_contract": "0x4200..."}`
- `capabilities` dynamically reflects enabled features

---

## 10. Webhook Configuration (v1.1)

Servers can fire webhooks after batch operations. Payload format is defined in `CERTIFICATE-SCHEMA.md` Section 3.

**Configuration:**
- Environment: `ECP_WEBHOOK_URL`, `ECP_WEBHOOK_TOKEN`
- Config file: `~/.atlast/config.json` → `webhook_url`, `webhook_token`
- CLI: `atlast config set webhook_url https://...`

**Behavior:**
- Webhook fires after successful batch creation
- Fail-open: webhook errors never block the batch response
- Retry: 1 retry on 5xx, no retry on 4xx
- Timeout: 5 seconds
- Auth: `X-ECP-Webhook-Token` header

## 10. Score Pull API (v2.0)

Enables third-party platforms to retrieve pre-computed trust scores.

### GET /v1/scores

Retrieve trust score for a single agent.

**Query Parameters:**
- `agent_did` (required): Agent DID (`did:ecp:{hex}`)

**Response (200):**
```json
{
  "agent_did": "did:ecp:xxx",
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

**Response (404):** Agent not registered.

**Authentication:** None required. Scores are public.

### POST /v1/scores/batch

Bulk lookup (max 100 DIDs per request).

**Request:**
```json
{"agent_dids": ["did:ecp:xxx", "did:ecp:yyy"]}
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

Unregistered agents return default `trust_score: 150`.
