# ECP Server API Reference

**Base URL:** `https://api.weba0.com`  
**OpenAPI Spec:** [docs/api/openapi.yaml](api/openapi.yaml)

---

## Public Endpoints

### `GET /health`
Health check. Returns server status and version.

**Response:** `200 OK`
```json
{"status": "ok", "version": "1.0.0", "chain": "sepolia"}
```

### `GET /.well-known/ecp.json`
ECP service discovery. Returns server capabilities, supported endpoints, and schema information.

**Response:** `200 OK`
```json
{
  "protocol": "ecp",
  "version": "1.0.0",
  "endpoints": ["health", "stats", "verify", "attestations", "discovery"],
  "chain": "sepolia",
  "schema_uid": "0xa67da7e..."
}
```

### `GET /v1/stats`
Global anchoring statistics — total attestations, batches processed, agents registered.

**Response:** `200 OK`
```json
{
  "total_attestations": 42,
  "total_batches_processed": 156,
  "total_agents": 12,
  "chain": "sepolia"
}
```

### `GET /metrics`
Prometheus-format metrics for monitoring.

**Response:** `200 OK` (text/plain, Prometheus exposition format)

---

## Verification Endpoints

### `POST /v1/verify/merkle`
Verify Merkle tree integrity — checks that a record hash is included in a Merkle root.

**Request:**
```json
{
  "merkle_root": "sha256:...",
  "record_hash": "sha256:...",
  "proof": [["sha256:...", "sha256:..."], ...]
}
```

**Response:** `200 OK`
```json
{"valid": true, "merkle_root": "sha256:..."}
```

### `GET /v1/verify/{attestation_uid}`
Check an EAS attestation by UID. Returns attestation details and verification status.

**Response:** `200 OK`
```json
{
  "attestation_uid": "0x...",
  "verified": true,
  "merkle_root": "sha256:...",
  "tx_hash": "0x...",
  "chain": "sepolia"
}
```

---

## Attestation Endpoints

### `GET /v1/attestations`
List all anchored attestations. Supports pagination.

**Query params:** `limit` (default 50), `offset` (default 0)

**Response:** `200 OK`
```json
{
  "attestations": [
    {
      "batch_id": "batch_...",
      "attestation_uid": "0x...",
      "merkle_root": "sha256:...",
      "record_count": 15,
      "agent_did": "did:ecp:...",
      "created_at": "2026-03-23T00:00:00Z"
    }
  ],
  "total": 42
}
```

### `GET /v1/attestations/{batch_id}`
Get attestation details for a specific batch.

**Response:** `200 OK` or `404 Not Found`

---

## Internal Endpoints (require authentication)

### `POST /v1/internal/anchor-now`
Manually trigger the anchoring process. Fetches pending batches and creates EAS attestations.

**Auth:** `X-Internal-Token` header (UUID)

**Response:** `200 OK`
```json
{"status": "ok", "anchored": 3, "failed": 0}
```

### `GET /v1/internal/anchor-status`
Check the anchor service status — last run time, pending count, health.

**Auth:** `X-Internal-Token` header

### `GET /v1/internal/cron-status`
Cron scheduler status — interval, last run, next scheduled run.

**Auth:** `X-Internal-Token` header

---

## Authentication

| Endpoint Type | Auth Method | Header |
|---|---|---|
| Public (`/health`, `/stats`, `/verify/*`, `/attestations`) | None | — |
| Internal (`/v1/internal/*`) | Token | `X-Internal-Token: {uuid}` |
| SDK batch upload | API Key | `X-Agent-Key: ak_live_{key}` |

---

## Error Responses

All errors follow this format:
```json
{"detail": "Error description"}
```

| Code | Meaning |
|---|---|
| 400 | Bad request (invalid payload) |
| 401 | Unauthorized (missing/invalid token) |
| 404 | Resource not found |
| 429 | Rate limited (100 req/min) |
| 500 | Internal server error |
