# ADR-001: Commit-Reveal Architecture

**Status:** Accepted  
**Date:** 2026-03-16  
**Decision Makers:** Boss, Atlas

## Context

ECP records contain evidence of agent behavior (inputs, outputs, reasoning). Storing raw content on-chain or on servers creates privacy risks and regulatory concerns (GDPR, CCPA). Agent operators need verifiable evidence without exposing proprietary prompts or business logic.

## Decision

Adopt a **Commit-Reveal** architecture:

1. **Commit phase**: SDK computes `SHA-256` hashes of input/output content locally. Only hashes (`in_hash`, `out_hash`) are transmitted to the server and anchored on-chain.
2. **Reveal phase**: When verification is needed, the agent operator can present the original content. Anyone can independently hash it and compare against the on-chain commitment.

Raw content **never leaves the device** unless the operator explicitly chooses to share it.

## Consequences

- **Privacy by design**: No PII or proprietary data on servers or blockchain.
- **GDPR-compatible**: Hashes are not personal data (irreversible one-way function).
- **Verifiable**: Any third party can verify content authenticity by re-hashing.
- **Trade-off**: Server cannot perform content-based analysis (e.g., hallucination detection). This is intentional — ATLAST proves *what happened*, not *whether it was correct*.

## Alternatives Considered

1. **Encrypt-then-store**: Adds key management complexity, still stores encrypted content centrally.
2. **Store raw content**: Privacy nightmare, regulatory non-compliance.
3. **ZK proofs**: Too computationally expensive for real-time agent recording at scale.
