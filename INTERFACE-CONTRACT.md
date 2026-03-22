# ATLAST ↔ LLaChat Interface Contract v1.0

> Canonical reference for all API interactions between ATLAST ECP (Atlas) and LLaChat Platform (Alex).  
> Last updated: 2026-03-21 | Status: **ALIGNED** (V1-V12 verified)

---

## 1. Data Flow (Unidirectional Push)

```
SDK → LLaChat (batch submit) → ATLAST ECP Server (anchor) → LLaChat (webhook notification)
```

- **Alex never calls Atlas API.** All communication is Atlas → Alex.
- Push events: batch-anchored notification, attestation webhook.

---

## 2. Authentication Tokens

| Token | Purpose | Location | Format |
|-------|---------|----------|--------|
| **X-Agent-Key** | SDK → LLaChat batch submit | HTTP header | `ak_live_{40hex}` |
| **LLACHAT_INTERNAL_TOKEN** | Atlas → LLaChat internal APIs | HTTP header `X-Internal-Token` | UUID `4b141c34-d8e1-4e7a-b1a1-e7a29231bf4a` |
| **ECP_WEBHOOK_TOKEN** | HMAC signing for webhooks | Shared secret | `b84ca16a14f920c99586697d964a28d0e71e6cd939478d2a22f5cc860435dffd` |

---

## 3. Endpoints

### 3.1 SDK → LLaChat

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/v1/batches` (or `/v1/batch`) | `X-Agent-Key` | Submit ECP batch (Merkle root + records) |

- Both `/v1/batch` and `/v1/batches` are valid (alias exists).
- SDK uses `/batches` (plural) — confirmed working.

### 3.2 Atlas → LLaChat (Internal)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/v1/internal/pending-batches` | `X-Internal-Token` | Fetch batches awaiting anchoring |
| POST | `/v1/internal/batch-anchored` | `X-Internal-Token` | Notify batch anchored on-chain |
| POST | `/v1/internal/ecp-webhook` | `X-ECP-Webhook-Token` + `X-ECP-Signature` | Full attestation event + cert creation |

### 3.3 ATLAST ECP Server (Public)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health`, `/v1/health` | Health check |
| GET | `/.well-known/ecp.json` | Service discovery |
| GET | `/v1/stats` | Global anchoring statistics |
| POST | `/v1/verify/merkle` | Verify Merkle tree integrity |
| GET | `/v1/verify/{uid}` | Check EAS attestation |
| GET | `/v1/attestations` | List attestations |
| GET | `/v1/attestations/{id}` | Get attestation detail |
| GET | `/metrics` | Prometheus metrics |

---

## 4. HMAC Webhook Signature

```
Algorithm:  HMAC-SHA256
Key:        ECP_WEBHOOK_TOKEN (shared secret)
Message:    Raw HTTP body bytes (compact JSON, sorted keys)
Header:     X-ECP-Signature: sha256={hex_digest}
```

**Critical**: HMAC is computed on the exact bytes sent as HTTP body. No re-serialization.

---

## 5. Data Formats

### 5.1 ECP Record (v1.0 Minimal)

```json
{
  "ecp": "1.0",
  "id": "rec_{uuid_hex[:16]}",
  "ts": "2026-03-21T12:00:00Z",
  "agent": "my-agent",
  "action": "llm_call",
  "in_hash": "sha256:{64hex}",
  "out_hash": "sha256:{64hex}"
}
```

### 5.2 Batch Submit Payload (SDK → LLaChat `/v1/batches`)

```json
{
  "agent_did": "did:ecp:{hex}",
  "merkle_root": "sha256:{64hex}",
  "sig": "ed25519:{hex}",
  "record_count": 42,
  "avg_latency_ms": 150,
  "batch_ts": 1711036800123,
  "ecp_version": "0.1",
  "record_hashes": [
    {"id": "rec_{hex}", "hash": "sha256:{hex}", "flags": ["hedged"], "in_hash": "sha256:{hex}", "out_hash": "sha256:{hex}"}
  ],
  "flag_counts": {"hedged": 1, "retried": 0}
}
```

- `batch_ts`: int (Unix milliseconds). NOT float, NOT seconds.
- `merkle_root`: always has `sha256:` prefix.
- `sig`: `ed25519:{hex}` or `"unverified"` (when cryptography package not installed).
- `record_hashes`: optional. Each entry has `id`, `hash`, `flags` (required), plus `in_hash`/`out_hash` (optional, v0.8.0+).
- `flag_counts`: optional. Aggregated flag counts across all records.
- `ecp_version`: currently `"0.1"` (batch protocol version, distinct from ECP record version `"1.0"`).

### 5.3 Webhook Payload (attestation.anchored)

```json
{
  "event": "attestation.anchored",
  "cert_id": "{batch_id}",
  "agent_did": "did:ecp:{hex}",
  "task_name": "ECP Certification: N records anchored on-chain",
  "batch_merkle_root": "sha256:{64hex}",
  "record_count": 42,
  "attestation_uid": "0x{hex}",
  "eas_tx_hash": "0x{hex}",
  "schema_uid": "0xa67da7e...",
  "chain_id": 84532,
  "on_chain": true,
  "created_at": "2026-03-21T12:00:00+00:00"
}
```

### 5.4 Anchor Flow (Sequential per batch)

```
1. Atlas GET /v1/internal/pending-batches → list of pending batches
2. For each batch:
   a. write_attestation() → EAS on-chain
   b. POST /v1/internal/batch-anchored {batch_id, attestation_uid, eas_tx_hash}
   c. POST /v1/internal/ecp-webhook {full payload + HMAC signature}
3. Alex receives webhook → verify HMAC → find agent → idempotent cert creation → feed event
```

---

## 6. EAS (Ethereum Attestation Service)

| Field | Value |
|-------|-------|
| Chain | Base Sepolia (testnet) |
| Chain ID | 84532 |
| Schema UID | `0xa67da7e880b3fe643f0e12b754c6048fc0a0bad0ed9a932ac85a5ebf6bd9326e` |
| Wallet | `0xd03E4c20501C59897FF50FC2141BA789b56213E6` |

---

## 7. Trust Score

- **Atlas provides raw data only** (records, attestations, Merkle proofs).
- **Trust Score algorithm is Alex-private** — not exposed in any Atlas API.
- Trust Score computation stays entirely within LLaChat platform.

### 7.1 ATLAST Protocol → LLaChat Dimension Mapping (F1 aligned 2026-03-22)

```
Protocol dimensions (ATLAST 0-1000):
  α (behavioral, 0.45) → LLaChat: Reliability + Efficiency
  β (consistency, 0.35) → LLaChat: Authority
  γ (transparency, 0.20) → LLaChat: Transparency

LLaChat composite formula:
  trust_score = (raw × 700) + identity_score(0–300)    // 0-1000
  raw = Reliability×0.40 + Transparency×0.30 + Efficiency×0.20 + Authority×0.10

Batch fields consumed for trust calculation:
  flag_counts.{retried, error, incomplete, hedged, a2a_delegated}
  avg_latency_ms, record_count, batch_ts

Note: chain_integrity = 1.0 constant in Phase 1 (Atlas does not send this value).
      Phase 7+ will introduce live chain_integrity signals.
```

---

## 8. Infrastructure

| Component | URL | Owner |
|-----------|-----|-------|
| ECP Server | `https://api.weba0.com` | Atlas (Railway) |
| LLaChat API | `https://api.llachat.com` | Alex (Railway) |
| SDK | PyPI `atlast-ecp` v0.8.0 | Atlas |
| Monorepo | `github.com/willau95/atlast-ecp` | Shared |

---

## 9. Change Protocol

1. Breaking changes: **48h advance notice** via bridge communication
2. New fields: additive only (backward compatible)
3. Token rotation: coordinated, both sides update simultaneously
4. Any interface change: align → Boss approval → implement → verify
