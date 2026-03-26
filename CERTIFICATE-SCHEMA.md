# CERTIFICATE-SCHEMA.md — ECP Certificate Unified Schema

**Version:** 1.0  
**Date:** 2026-03-21  
**Status:** Draft — pending Alex confirmation  
**Purpose:** Define the canonical certificate data structure shared between ATLAST ECP backend and LLAChat platform.

---

## 1. Unified Field Specification

| Field | Type | Required | Source | Description |
|-------|------|----------|--------|-------------|
| `id` | UUID | ✅ | LLAChat | Primary key (LLAChat internal) |
| `cert_id` | String(30) | ✅ | ECP Backend | Short ID, format: `cert_{uuid_hex[:16]}` |
| `agent_did` | String(80) | ✅ | ECP Backend | Agent DID, format: `did:ecp:{32 hex chars}` |
| `task_name` | String(200) | ✅ | LLAChat | Human-readable task name |
| `task_description` | Text | ❌ | LLAChat | Extended task description |
| `trust_score_at_time` | Integer | ❌ | LLAChat | Trust score snapshot at certificate creation |
| `steps_count` | Integer | ❌ | LLAChat | Number of task steps (UI display) |
| `batch_ids` | ARRAY(Text) | ❌ | LLAChat | Associated batch IDs |
| `attestation_uid` | String(100) | ✅ | ECP Backend | EAS attestation UID (`0x...`, 66 chars) |
| `on_chain` | Boolean | ✅ | ECP Backend | Whether EAS attestation succeeded |
| `verify_url` | String(200) | ❌ | ECP Backend | Chain explorer verification URL |
| `verified_count` | Integer | ❌ | LLAChat | Number of times users verified this cert |
| `batch_merkle_root` | String(73) | ✅ | ECP Backend | Merkle root, format: `sha256:{64 hex}` |
| `record_count` | Integer | ✅ | ECP Backend | Number of ECP records in the batch |
| `eas_tx_hash` | String(66) | ❌ | ECP Backend | On-chain transaction hash (`0x...`) |
| `schema_uid` | String(66) | ✅ | ECP Backend | EAS schema UID (constant per network) |
| `chain_id` | Integer | ✅ | ECP Backend | Network chain ID (84532 = Base Sepolia) |
| `created_at` | ISO8601 | ✅ | ECP Backend | Certificate creation timestamp |
| `status` | String(20) | ✅ | ECP Backend | `"attested"` \| `"pending"` \| `"failed"` |

---

## 2. Field Origin Map

### Fields from ECP Backend (Atlas provides)

These are returned by `POST /v1/certificates/create` and `GET /v1/agent/{did}/certificates`:

```json
{
  "cert_id": "cert_a1b2c3d4e5f6a1b2",
  "agent_did": "did:ecp:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
  "batch_merkle_root": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "record_count": 42,
  "attestation_uid": "0xa67da7e880b3fe643f0e12b754c6048fc0a0bad0ed9a932ac85a5ebf6bd9326e",
  "eas_tx_hash": "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
  "schema_uid": "0xa67da7e880b3fe643f0e12b754c6048fc0a0bad0ed9a932ac85a5ebf6bd9326e",
  "chain_id": 84532,
  "on_chain": true,
  "verify_url": "https://base-sepolia.easscan.org/attestation/view/0x...",
  "created_at": "2026-03-21T12:00:00Z",
  "status": "attested"
}
```

### Fields from LLAChat (Alex manages)

These are enrichment fields stored only in LLAChat's DB:

```json
{
  "id": "uuid-pk",
  "task_name": "Code Review for PR #42",
  "task_description": "Reviewed 500 lines of Python code...",
  "trust_score_at_time": 943,
  "steps_count": 5,
  "batch_ids": ["batch_abc123", "batch_def456"],
  "verified_count": 12
}
```

---

## 3. Webhook Payload (Certificate Created)

When a certificate is successfully created, ECP Backend POSTs to:
`https://api.llachat.com/v1/internal/ecp-webhook`

**Headers:**
```
Content-Type: application/json
X-ECP-Webhook-Token: ecp-internal-2026
```

**Payload:**
```json
{
  "event": "attestation.anchored",
  "cert_id": "batch_a1b2c3d4e5f6a1b2",
  "agent_did": "did:ecp:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
  "batch_merkle_root": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "record_count": 42,
  "attestation_uid": "0x...",
  "eas_tx_hash": "0x...",
  "schema_uid": "0xa67da7e880b3fe643f0e12b754c6048fc0a0bad0ed9a932ac85a5ebf6bd9326e",
  "chain_id": 84532,
  "on_chain": true,
  "created_at": "2026-03-21T12:00:00+00:00"
}
```

**Note:** `cert_id` here = `batch_id` from the batches table. LLAChat generates the final `cert_xxx` ID and enriches with `task_name` / `task_description` on its side.

---

## 4. Integration Pattern

```
┌─────────────┐                          ┌─────────────┐
│  ECP Backend │──── webhook POST ───────▶│   LLAChat   │
│  (Atlas)     │                          │   (Alex)    │
│              │◀── GET /certificates ────│             │
└─────────────┘                          └─────────────┘

Flow:
1. Agent SDK calls POST /v1/certificates/create → ECP Backend
2. ECP Backend creates attestation on-chain
3. ECP Backend POSTs webhook to LLAChat (cert_id, agent_did, attestation_uid, ...)
4. LLAChat enriches with task_name, task_description, trust_score_at_time
5. LLAChat stores unified record in its own DB
6. For display: LLAChat uses own DB (fast) + optional GET from ECP API (verify freshness, 30s cache)
```

---

## 5. Constants

| Constant | Value | Notes |
|----------|-------|-------|
| EAS Schema UID | `0xa67da7e880b3fe643f0e12b754c6048fc0a0bad0ed9a932ac85a5ebf6bd9326e` | Base Sepolia |
| Chain ID | `84532` | Base Sepolia |
| DID Prefix | `did:ecp:` | Canonical, immutable |
| ECP Version | `0.1` | Current spec version |
| Webhook Token | `ecp-internal-2026` | Service-to-service auth |

---

## 6. Migration Recommendations for LLAChat

Alex's existing `certificates` table needs:

| Action | Field | Reason |
|--------|-------|--------|
| **Add** | `batch_merkle_root` (String 73) | Core ECP integrity proof |
| **Add** | `record_count` (Integer) | Display "N records certified" |
| **Add** | `schema_uid` (String 66) | Link to EAS schema for verify page |
| **Add** | `chain_id` (Integer) | Multi-chain support future-proofing |
| **Add** | `status` (String 20) | Track attestation lifecycle |
| **Keep** | `eas_tx_hash` | Optional — can read from ECP API instead |

**Minimum viable migration:** Add `batch_merkle_root` + `record_count`. Others can be read from ECP API on demand.

---

## 7. Open Questions

1. **`task_name` source**: Should ECP Backend accept `task_name` as input to `POST /v1/certificates/create`, or should LLAChat always set it post-creation?
2. **`evidence_hash` field**: Alex mentioned current DB uses a field that isn't a real evidence hash. Is this `batch_merkle_root` or something else? Need Alex to clarify so we can map correctly.
