# ADR-005: Ed25519 for Agent Identity

**Status:** Accepted  
**Date:** 2026-03-16  
**Decision Makers:** Atlas

## Context

Each ECP agent needs a cryptographic identity for signing records and batches. The identity must be:
- Auto-generated (zero friction for developers)
- Deterministic DID derivation (same key → same DID)
- Fast signing (thousands of records per session)
- Small signatures (stored in every record)

## Decision

**Ed25519 (RFC 8032)** for all agent signing operations.

Identity structure:
```
Private key:  32 bytes (stored in ~/.ecp/identity.json, never transmitted)
Public key:   32 bytes (shared with server on registration)
DID:          did:ecp:{sha256(public_key)[:32]}
Signature:    ed25519:{hex} (64 bytes, stored in record `sig` field)
```

Key generation: `Ed25519PrivateKey.generate()` from `cryptography` library (Python) or `@noble/ed25519` (TypeScript).

Fallback: If `cryptography` is not installed, SDK uses `"unverified"` as sig value. Records are still created and batched, just unsigned.

## Consequences

- **Fast**: Ed25519 signs ~10,000 messages/sec on modern hardware. No bottleneck.
- **Compact**: 64-byte signatures vs 71+ bytes for ECDSA (secp256k1).
- **Deterministic**: Same private key always produces the same DID.
- **No certificate authority**: Self-sovereign identity. Agent owns its key.
- **Trade-off**: Ed25519 is not natively supported by Ethereum/EVM. We use EAS (Ethereum Attestation Service) for on-chain anchoring, which accepts arbitrary data — no EVM signature required.
- **Graceful degradation**: Agents without `cryptography` installed still function (fail-open: unsigned records are valid but flagged).

## Alternatives Considered

1. **secp256k1 (Ethereum native)**: EVM-compatible but slower signing, larger signatures, and we don't need on-chain signature verification (EAS handles attestation).
2. **RSA**: Much larger keys/signatures. Rejected — unnecessary for this use case.
3. **No signing**: Rely purely on Merkle root for integrity. Rejected — signing binds records to a specific agent identity, enabling accountability.
