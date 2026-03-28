# ECP — Evidence Chain Protocol

**Version:** 2.1  
**Status:** Draft  
**Part of:** [ATLAST Protocol](https://github.com/willau95/atlast-ecp)  
**License:** MIT  

---

## Abstract

ECP (Evidence Chain Protocol) is an open standard for recording, chaining, and verifying AI Agent actions. It provides cryptographic proof that a specific agent performed a specific action at a specific time, without revealing the content of that action.

**Content never leaves the device. Only SHA-256 hashes are transmitted.**

---

## 1. Design Principles

| Principle | Description |
|-----------|-------------|
| **Privacy First** | Only cryptographic hashes leave the device. Content stays local. |
| **Verifiable When Recorded** | A record exists → it is tamper-proof. Gaps are visible. |
| **Platform Agnostic** | ECP is a data format. Any language, any framework can implement it. |
| **Progressive Complexity** | Start with 6 fields. Add chain, identity, blockchain as needed. |
| **Fail-Open** | Recording failures must NEVER crash the agent. |

---

## 2. Record Format

### 2.1 Core Record (Required — Level 1)

The minimum valid ECP record. Any implementation MUST support this.

```json
{
  "ecp": "1.0",
  "id": "rec_a1b2c3d4e5f6a1b2",
  "ts": 1741766400000,
  "agent": "my-agent",
  "action": "llm_call",
  "in_hash": "sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
  "out_hash": "sha256:486ea46224d1bb4fb680f34f7c9ad96a8f24ec88be73ea8e5a6c65260e9cb8a7"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `ecp` | string | ✅ | Protocol version. `"1.0"` |
| `id` | string | ✅ | Unique record ID. Format: `rec_` + 16 hex chars |
| `ts` | integer | ✅ | Unix timestamp in milliseconds (UTC) |
| `agent` | string | ✅ | Agent identifier. Any string (or DID — see §4) |
| `action` | string | ✅ | Action type: `llm_call`, `tool_call`, `message`, `a2a_call` |
| `in_hash` | string | ✅ | SHA-256 hash of input. Format: `sha256:{hex}` |
| `out_hash` | string | ✅ | SHA-256 hash of output. Format: `sha256:{hex}` |

### 2.2 Metadata Extension (Optional — Level 2)

```json
{
  "ecp": "1.0",
  "id": "rec_a1b2c3d4e5f6a1b2",
  "ts": 1741766400000,
  "agent": "my-agent",
  "action": "llm_call",
  "in_hash": "sha256:...",
  "out_hash": "sha256:...",
  "meta": {
    "model": "claude-sonnet-4-6",
    "tokens_in": 500,
    "tokens_out": 200,
    "latency_ms": 1200,
    "flags": ["hedged"],
    "cost_usd": 0.003
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `meta.model` | string | LLM model name |
| `meta.tokens_in` | integer | Input token count |
| `meta.tokens_out` | integer | Output token count |
| `meta.latency_ms` | integer | Response time in milliseconds |
| `meta.flags` | string[] | Behavioral flags (see §3) |
| `meta.cost_usd` | float | Estimated cost in USD |
| `meta.session_id` | string | Groups records from the same task/session |
| `meta.delegation_id` | string | Links parent's `a2a_call` record to sub-agent chain |
| `meta.delegation_depth` | integer | Nesting level: 0=root agent, 1=sub-agent, 2=sub-sub-agent |
| `meta.parent_agent` | string | DID or identifier of the delegating agent |

### 2.3 Chain Extension (Optional — Level 3)

Adds tamper-proof chaining. Modifying any record breaks the chain.

```json
{
  "ecp": "1.0",
  "id": "rec_a1b2c3d4e5f6a1b2",
  "ts": 1741766400000,
  "agent": "my-agent",
  "action": "llm_call",
  "in_hash": "sha256:...",
  "out_hash": "sha256:...",
  "chain": {
    "prev": "rec_previous_record1",
    "hash": "sha256:..."
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `chain.prev` | string | ID of previous record. `"genesis"` for first. |
| `chain.hash` | string | SHA-256 of canonical JSON (with `chain.hash` and `sig` zeroed) |

### 2.4 Identity Extension (Optional — Level 4)

Adds cryptographic identity and signature verification.

```json
{
  "ecp": "1.0",
  "id": "rec_a1b2c3d4e5f6a1b2",
  "ts": 1741766400000,
  "agent": "did:ecp:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
  "action": "llm_call",
  "in_hash": "sha256:...",
  "out_hash": "sha256:...",
  "sig": "ed25519:aabbccddeeff..."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `agent` | DID string | `did:ecp:{sha256(pubkey)[:32]}` |
| `sig` | string | Ed25519 signature over `chain.hash`. Format: `ed25519:{hex}` |

### 2.5 Anchor Extension (Optional — Level 5)

Blockchain anchoring for maximum verifiability.

```json
{
  "anchor": {
    "chain": "base-sepolia",
    "tx": "0xaabb...",
    "batch": "batch_01HX...",
    "ts": 1741766400000
  }
}
```

---

## 3. Behavioral Flags

Flags are boolean signals derived from **passive behavior analysis**. They are computed locally by rule engines, never by LLM-as-Judge. The agent cannot control or self-report flags.

| Flag | Signal | Description |
|------|--------|-------------|
| `retried` | Negative | Agent was asked to redo this task |
| `hedged` | Neutral | Output contained uncertainty language |
| `incomplete` | Negative | Conversation ended without resolution |
| `high_latency` | Neutral | Response time > 2× agent's median |
| `error` | Negative | Agent returned an error state |
| `human_review` | Positive | Agent requested human verification |
| `a2a_delegated` | Neutral | Task delegated to sub-agent |
| `speed_anomaly` | Neutral | Output suspiciously fast for its length (>500 chars in <100ms, or <10% of median latency) |

---

## 4. Agent Identity (DID)

Optional. When used, agents are identified by a Decentralized Identifier.

```
Format: did:ecp:{identifier}
Where:  identifier = sha256(ed25519_public_key_hex)[:32]
Example: did:ecp:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4
```

Key generation: Ed25519 (RFC 8032). Private key stays local. Public key is shareable.

---

## 5. Hashing Rules

All content is hashed with SHA-256 before being stored in ECP records.

| Content Type | Hashing Method |
|-------------|---------------|
| String | `sha256(utf8_bytes(content))` |
| Object/Array | `sha256(utf8_bytes(canonical_json(content)))` |

**Canonical JSON:** `json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",",":"))`

This ensures identical content always produces the same hash, regardless of implementation language.

---

## 6. Action Types

| Action | Description | Typical Source |
|--------|-------------|----------------|
| `llm_call` | LLM API call (prompt → response) | SDK wrap, Proxy |
| `tool_call` | Tool/function execution | Framework adapters |
| `message` | Conversation turn (user → agent) | Chat platforms |
| `a2a_call` | Agent-to-Agent delegation | Multi-agent systems |

---

## 7. Version Compatibility

### 7.1 ECP Record Version (`ecp` field)

| Version | Format | Status |
|---------|--------|--------|
| `0.1` | Nested (`step.type`, `step.in_hash`, `chain.prev`, `chain.hash`) | Legacy, still valid |
| `1.0` | Flat (`action`, `in_hash`, `chain.prev`, `chain.hash`) | Current |

Readers MUST accept both v0.1 and v1.0 records. Writers SHOULD produce v1.0.

### 7.2 Batch Protocol Version (`ecp_version` in batch payload)

The `ecp_version` field in batch upload payloads identifies the batch protocol version, which is distinct from the ECP record format version above. Current batch protocol version is `"0.1"`. This field is written into on-chain EAS attestation data for provenance tracking.

---

## 8. Integration Methods

ECP is integration-agnostic. Reference implementations exist for:

| Method | Code Change | Coverage | Example |
|--------|-------------|----------|---------|
| **Proxy** | Zero | All languages | `atlast run python my_agent.py` |
| **SDK wrap** | 1 line | Python, TypeScript | `client = wrap(Anthropic())` |
| **CLI** | Zero | Any | `echo '{"in":"...","out":"..."}' \| atlast record` |
| **Framework Adapter** | 1 line | LangChain, CrewAI | `callbacks=[ECPCallback()]` |
| **Platform Plugin** | Config | OpenClaw, etc. | Plugin config |

---

## References

- [ATLAST Protocol](https://github.com/willau95/atlast-ecp) — Reference implementation
- [EAS (Ethereum Attestation Service)](https://attest.sh) — On-chain anchoring
- [RFC 8032](https://tools.ietf.org/html/rfc8032) — Ed25519 signatures
- [W3C DID](https://www.w3.org/TR/did-core/) — Decentralized Identifiers
