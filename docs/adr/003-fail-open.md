# ADR-003: Fail-Open Design Principle

**Status:** Accepted  
**Date:** 2026-03-16  
**Decision Makers:** Boss, Atlas

## Context

ECP SDK instruments production AI agents. Any failure in the SDK (network error, disk full, server down) must **never** crash or degrade the agent's primary function. The agent's job is more important than our evidence recording.

## Decision

**Fail-Open everywhere**: All SDK operations are wrapped in try/except. Failures are silently logged, never raised. The agent continues unaffected.

Applies to:
- `wrap()`: If recording fails, the original LLM response is returned unchanged.
- `@track`: If decorator fails, the decorated function executes normally.
- `run_batch()`: If upload fails, batch is queued for retry. Never raises.
- `atlast proxy`: If proxy recording fails, request is forwarded unchanged.
- HMAC verification (server-side): Currently fail-open; will switch to fail-closed after Phase 6.

## Consequences

- **Zero risk to agent operators**: Adopting ATLAST SDK cannot break their agents.
- **Adoption-friendly**: "It can't hurt you" removes the biggest objection to instrumentation.
- **Trade-off**: Silent failures mean evidence gaps. Mitigated by SDK-level `incomplete` flag detection and batch retry queue.
- **Monitoring**: Sentry captures SDK-side errors for our debugging, but never surfaces them to the agent.

## Alternatives Considered

1. **Fail-closed**: Raise exceptions on failure. Rejected — would make SDK adoption risky for production agents.
2. **Configurable**: Let users choose fail-open or fail-closed. Rejected for MVP — adds complexity, and the safe default should be the only default.
