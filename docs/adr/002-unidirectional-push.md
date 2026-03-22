# ADR-002: Unidirectional Push Architecture

**Status:** Accepted  
**Date:** 2026-03-20  
**Decision Makers:** Boss, Atlas, Alex

## Context

ATLAST Protocol (Atlas) produces ECP evidence data. LLaChat (Alex) consumes it for display, trust scoring, and leaderboards. The question: should Alex pull from Atlas, or should Atlas push to Alex?

## Decision

**Atlas pushes to Alex. Alex never calls Atlas API.**

Data flow:
```
SDK → Atlas Server (batch upload)
Atlas Server → Blockchain (EAS attestation)
Atlas Server → Alex (webhook: attestation.anchored)
```

Alex receives all data via two channels:
1. **Batch upload** (`POST /batches`): SDK sends directly to Atlas, Atlas forwards to Alex via `/v1/internal/ecp-webhook`.
2. **Webhook** (`attestation.anchored`): After on-chain anchoring, Atlas notifies Alex with `attestation_uid`, `tx_hash`, `merkle_root`.

## Consequences

- **Simplicity**: Alex has zero dependency on Atlas API availability. If Atlas is down, Alex still functions with cached data.
- **Decoupling**: Atlas can change internal APIs without breaking Alex.
- **Reliability**: Webhook retry (3 attempts, exponential backoff) ensures delivery.
- **Trade-off**: Alex cannot query Atlas for historical data on-demand. All needed data must be included in push payloads.

## Alternatives Considered

1. **Bidirectional API**: Alex polls Atlas for updates. Rejected — adds coupling, requires Atlas to maintain consumer-facing query APIs.
2. **Shared database**: Both read/write same DB. Rejected — tight coupling, scaling nightmare.
3. **Message queue (Kafka/RabbitMQ)**: Overkill for two-party communication at current scale.
