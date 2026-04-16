# API Reference

**Base URL:** `https://api.weba0.com`

## Authentication

Two authentication methods:

| Method | Header | Usage |
|--------|--------|-------|
| API Key | `X-API-Key: ak_live_xxx` | SDK → Server (user-facing) |
| Internal Token | `X-Internal-Token: xxx` | Service-to-service |

## Endpoints

### Public (No Auth)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/.well-known/ecp.json` | Service discovery |
| `GET` | `/v1/stats` | Global anchoring statistics |
| `GET` | `/v1/verify/{attestation_uid}` | Verify on-chain attestation |
| `POST` | `/v1/verify/merkle` | Verify Merkle tree integrity |
| `GET` | `/v1/scores` | [Trust score for an agent](scores.md) |
| `POST` | `/v1/scores/batch` | [Bulk trust score lookup](scores.md) |
| `GET` | `/v1/attestations` | List EAS attestations |

### Authenticated

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/agents/register` | Register agent, get API key |
| `POST` | `/v1/batches` | Upload batch for anchoring |
| `GET` | `/v1/batches/{batch_id}` | Get batch status |
| `GET` | `/v1/auth/me` | Current agent info |
| `POST` | `/v1/auth/rotate-key` | Rotate API key |

---

## POST /v1/agents/register

Register a new agent and receive an API key.

**Request:**
```json
{
  "did": "did:ecp:abc123...",
  "public_key": "hex_encoded_ed25519_public_key",
  "ecp_version": "0.1"
}
```

**Response:** `200 OK`
```json
{
  "agent_did": "did:ecp:abc123...",
  "agent_api_key": "ak_live_xxxxxxxxxxxxxxxx",
  "message": "Agent registered. Save your API key."
}
```

---

## POST /v1/batches

Upload a Merkle batch for EAS anchoring.

**Headers:** `X-API-Key: ak_live_xxx` (recommended) or `X-Agent-Key: ak_live_xxx`

**Request:**
```json
{
  "merkle_root": "sha256:abc123...",
  "agent_did": "did:ecp:abc123...",
  "record_count": 50,
  "avg_latency_ms": 1200,
  "batch_ts": 1711180800000,
  "sig": "ed25519:signature_hex",
  "ecp_version": "0.1",
  "record_hashes": [
    {"id": "rec_001", "hash": "sha256:...", "flags": ["retried"]}
  ],
  "flag_counts": {"retried": 3, "error": 1},
  "chain_integrity": 0.95
}
```

**Response:** `200 OK`
```json
{
  "batch_id": "batch_abc123",
  "status": "pending",
  "message": "Batch accepted. 50 records queued for EAS anchoring."
}
```

---

## GET /v1/verify/{attestation_uid}

Verify an on-chain attestation.

**Response:** `200 OK`
```json
{
  "valid": true,
  "attestation_uid": "0xabc...",
  "merkle_root": "sha256:...",
  "agent_did": "did:ecp:...",
  "on_chain": true,
  "chain_id": 8453
}
```

---

## POST /v1/verify/merkle

Verify Merkle tree integrity.

**Request:**
```json
{
  "record_hashes": ["sha256:a", "sha256:b", "sha256:c"],
  "expected_root": "sha256:root..."
}
```

**Response:** `200 OK`
```json
{
  "valid": true,
  "computed_root": "sha256:root...",
  "record_count": 3
}
```

---

## Rate Limits

- Default: **60 requests/minute** per IP
- `POST /v1/batches`: **10 requests/minute** per IP
- `429 Too Many Requests` returned when exceeded
