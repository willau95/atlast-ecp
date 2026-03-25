# ATLAST ECP — Architecture

## Monorepo Structure

```
atlast-ecp/
├── sdk/
│   ├── python/          # Python SDK (PyPI: atlast-ecp)
│   │   ├── atlast_ecp/
│   │   │   ├── core.py          # record_minimal() — the fundamental API
│   │   │   ├── record.py        # ECP record creation (v1.0 spec)
│   │   │   ├── batch.py         # Merkle tree + batch upload
│   │   │   ├── verify.py        # Signature + Merkle proof verification
│   │   │   ├── wrap.py          # wrap(client) — OpenAI/Anthropic/Gemini
│   │   │   ├── proxy.py         # Transparent HTTP proxy (Layer 0)
│   │   │   ├── identity.py      # DID + Ed25519 key management
│   │   │   ├── storage.py       # Local ~/.ecp/ file storage
│   │   │   ├── signals.py       # Trust signal computation
│   │   │   ├── insights.py      # Performance analytics
│   │   │   ├── webhook.py       # HMAC-signed webhook delivery
│   │   │   ├── cli.py           # `atlast` CLI entry point
│   │   │   ├── config.py        # Environment/config management
│   │   │   ├── a2a.py           # Agent-to-Agent handoff tracking
│   │   │   ├── auto.py          # OpenTelemetry auto-instrumentation
│   │   │   ├── otel_exporter.py # OTel span → ECP record exporter
│   │   │   ├── mcp_server.py    # MCP (Model Context Protocol) server
│   │   │   ├── openclaw_scanner.py # OpenClaw session log scanner
│   │   │   └── adapters/
│   │   │       ├── langchain.py   # LangChain callback handler
│   │   │       ├── crewai.py      # CrewAI callback
│   │   │       └── autogen.py     # AutoGen middleware
│   │   └── tests/               # 440+ tests
│   ├── typescript/      # TypeScript SDK (npm: @atlast/ecp)
│   └── go/              # Go SDK (skeleton)
├── server/              # ECP Server (FastAPI, Railway)
│   ├── app/
│   │   ├── main.py              # FastAPI app + CORS + security headers
│   │   ├── config.py            # Railway env vars
│   │   ├── routes/
│   │   │   ├── anchor.py        # Cron anchor + manual trigger
│   │   │   ├── verify.py        # Merkle + attestation verification
│   │   │   ├── attestations.py  # Attestation listing
│   │   │   ├── discovery.py     # .well-known/ecp.json
│   │   │   ├── health.py        # Health checks
│   │   │   └── cron.py          # Cron status
│   │   └── services/
│   │       ├── eas.py           # EAS on-chain attestation (Base)
│   │       ├── webhook.py       # HMAC-signed webhook to LLaChat
│   │       └── llachat_client.py # LLaChat internal API client
│   └── tests/
├── examples/            # Runnable demos (no API key needed)
└── docs/                # ECP-SPEC, certificates schema
```

## Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│ Developer's Agent (Python/TS/Go)                            │
│                                                              │
│  Option A: wrap(client)     — 1 line, wraps OpenAI/etc      │
│  Option B: @track decorator — 5 lines, SDK integration      │
│  Option C: atlast run cmd   — 0 lines, transparent proxy    │
│  Option D: Adapter callback — 1 line, LangChain/CrewAI/etc  │
└───────────────────┬─────────────────────────────────────────┘
                    │
                    ▼
           ┌────────────────┐
           │  Local Storage  │  ~/.ecp/records/*.jsonl
           │  (SHA-256 only) │  Content never leaves device
           └───────┬────────┘
                   │ atlast flush / SDK batch upload
                   ▼
           ┌────────────────┐
           │  LLaChat API   │  POST /v1/batches
           │  (Alex's side) │  X-Agent-Key: ak_live_xxx
           └───────┬────────┘
                   │ marks batch as "pending"
                   ▼
           ┌────────────────┐
           │  ECP Server    │  api.weba0.com (Atlas's side)
           │  Cron (60min)  │  GET /v1/internal/pending-batches
           └───────┬────────┘
                   │
            ┌──────┴──────┐
            ▼             ▼
    ┌──────────────┐  ┌──────────────┐
    │ EAS On-Chain │  │ LLaChat      │
    │ (Base)       │  │ Webhook      │
    │ attestation  │  │ HMAC-signed  │
    └──────────────┘  └──────────────┘
```

## Three Integration Layers

| Layer | Effort | Method | What's Captured |
|-------|--------|--------|----------------|
| **0** | 0 lines | `atlast run python my_agent.py` | All LLM API calls (transparent proxy) |
| **1** | 1-5 lines | `wrap(client)` or `@track` | LLM calls + custom metadata |
| **2** | 1 line | Framework adapter callback | LLM + tools + agent steps + handoffs |

## Security Model

- **Privacy**: Only SHA-256 hashes stored, raw content never transmitted
- **Fail-Open**: SDK/proxy errors never crash the host agent
- **HMAC-SHA256**: All webhook payloads signed with `X-ECP-Signature`
- **Token separation**: Agent key (public API), Internal token (server-to-server), Webhook token (HMAC)
- **On-chain integrity**: Merkle root + attestation UID anchored to Base via EAS

## ECP Record (v1.0 Minimal)

```json
{
  "ecp": "1.0",
  "id": "rec_a1b2c3d4e5f67890",
  "ts": "2026-03-21T12:00:00Z",
  "agent": "my-agent",
  "action": "llm_call",
  "in_hash": "sha256:abc...",
  "out_hash": "sha256:def..."
}
```

## Key Design Decisions

1. **Spec-first, SDK-second**: ECP is a protocol standard, not just a library
2. **Local-first**: All data stays on device by default; publishing is opt-in
3. **Provider-independent**: Works with any LLM (OpenAI, Anthropic, Gemini, local)
4. **Hash-only transmission**: Raw content never leaves the developer's machine
5. **Unidirectional push**: SDK → LLaChat → ECP Server (never reverse)
