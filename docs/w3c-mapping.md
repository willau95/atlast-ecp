# W3C DID/VC ↔ ECP Mapping

**Date:** 2026-03-23  
**Status:** Reference document

## 1. DID Mapping: `did:ecp` ↔ W3C DID Core

### ECP Agent Identity → DID Document

| ECP Field | W3C DID Core | Notes |
|---|---|---|
| `did:ecp:{hash}` | `id` | DID subject identifier |
| Ed25519 public key | `verificationMethod[0]` | Type: `Ed25519VerificationKey2020` |
| Agent name | `service[0].serviceEndpoint` | Optional metadata |
| — | `authentication` | References `verificationMethod[0]` |

### Example DID Document

```json
{
  "@context": ["https://www.w3.org/ns/did/v1", "https://w3id.org/security/suites/ed2519-2020/v1"],
  "id": "did:ecp:6cda81f65ae50c8b148ab57d3e3743da",
  "verificationMethod": [{
    "id": "did:ecp:6cda81f65ae50c8b148ab57d3e3743da#key-1",
    "type": "Ed25519VerificationKey2020",
    "controller": "did:ecp:6cda81f65ae50c8b148ab57d3e3743da",
    "publicKeyMultibase": "z6Mkf5rGMoatrSj1f4CyvuHBeXJELe9RPdzo2PKGNCKVtZxP"
  }],
  "authentication": ["did:ecp:6cda81f65ae50c8b148ab57d3e3743da#key-1"]
}
```

### DID Method Specification Requirements

| Requirement | Status |
|---|---|
| Create | ✅ `get_or_create_identity()` — deterministic from keypair |
| Read/Resolve | ⏳ No DID resolver yet (Phase 7+) |
| Update | ✅ Key rotation via `/v1/agent/{did}/rekey` |
| Deactivate | ⏳ Not implemented |

## 2. ECP Record ↔ Verifiable Credential

| ECP Record Field | VC Data Model 2.0 | Notes |
|---|---|---|
| `id` (rec_xxx) | `id` | Credential identifier |
| `agent` (did:ecp:...) | `issuer` | The agent that created the record |
| `ts` | `issuanceDate` | ISO 8601 from Unix ms |
| `action` | `credentialSubject.action` | What was done |
| `in_hash` | `credentialSubject.inputHash` | SHA-256 of input |
| `out_hash` | `credentialSubject.outputHash` | SHA-256 of output |
| `sig` (ed25519:...) | `proof.proofValue` | Digital signature |
| `chain_hash` | `credentialSubject.chainHash` | Evidence chain link |
| `prev` | `credentialSubject.previousRecord` | Chain continuity |
| Behavioral flags | `credentialSubject.flags` | Array of flag strings |
| EAS attestation | `credentialStatus` | On-chain anchor reference |

### Example: ECP Record as Verifiable Credential

```json
{
  "@context": ["https://www.w3.org/ns/credentials/v2"],
  "type": ["VerifiableCredential", "ECPEvidenceRecord"],
  "issuer": "did:ecp:6cda81f65ae50c8b148ab57d3e3743da",
  "issuanceDate": "2026-03-23T00:00:00Z",
  "credentialSubject": {
    "action": "llm_call",
    "inputHash": "sha256:2cf24dba...",
    "outputHash": "sha256:486ea462...",
    "flags": [],
    "chainHash": "sha256:...",
    "previousRecord": "rec_abc123"
  },
  "proof": {
    "type": "Ed25519Signature2020",
    "verificationMethod": "did:ecp:6cda81f65ae50c8b148ab57d3e3743da#key-1",
    "proofValue": "z3FXQqF..."
  }
}
```

## 3. Gap Analysis

| Feature | ECP Status | W3C Standard Gap |
|---|---|---|
| DID Resolution | Not implemented | Need `did:ecp` method spec + resolver |
| VC Issuance | Conceptual mapping only | Need VC envelope wrapper in SDK |
| Revocation | Not needed (evidence is immutable) | N/A |
| Presentation | Not implemented | Need VP format for sharing proofs |
| JSON-LD context | Not implemented | Need `https://atlast.io/ns/ecp/v1` |

## Recommendation

ECP's data model maps cleanly to W3C VC/DID standards. Phase 7+ should:
1. Register `did:ecp` method at W3C DID Method Registry
2. Publish JSON-LD context for ECP credentials
3. Add optional VC envelope output to SDK (`record.toVC()`)
