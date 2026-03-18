# ECP Server Specification v1.0

> Minimal API specification for an ECP-compatible server.
> Any backend implementing these 4 endpoints can receive, store, and serve ECP records.

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
  "did": "did:ecp:z6Mk...",
  "public_key": "base64-encoded-ed25519-public-key",
  "handle": "my-agent",
  "display_name": "My Agent (optional)"
}
```

**Response (201):**
```json
{
  "agent_id": "uuid",
  "did": "did:ecp:z6Mk...",
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
  "agent_did": "did:ecp:z6Mk...",
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
  "did": "did:ecp:z6Mk...",
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
      "did": "did:ecp:z6Mk...",
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
- **Live Server**: `https://api.llachat.com` (hosted by LLaChat)
- **Spec**: [ECP-SPEC.md](https://github.com/willau95/atlast-ecp/blob/main/ECP-SPEC.md)

---

*ECP Server Spec v1.0 — ATLAST Protocol Working Group — 2026-03-18*
