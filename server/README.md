# ATLAST ECP Server

> Evidence Chain Protocol — EAS on-chain anchoring, verification, and webhook dispatch.

Part of the [ATLAST Protocol](https://github.com/willau95/atlast-ecp) — trust infrastructure for the Agent economy.

## What It Does

- **EAS Anchoring**: Automatically anchors agent evidence batches to Ethereum Attestation Service (Base chain)
- **Webhook Dispatch**: Notifies LLaChat when batches are anchored (HMAC-SHA256 signed)
- **Merkle Verification**: Public endpoint to verify Merkle tree integrity
- **Discovery**: `.well-known/ecp.json` endpoint for protocol discovery

## API Endpoints

### Public (no auth)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/v1/health` | Health check (aliased) |
| GET | `/.well-known/ecp.json` | ECP discovery |
| GET | `/v1/stats` | Anchoring statistics |
| POST | `/v1/verify/merkle` | Verify Merkle tree |
| GET | `/v1/verify/{uid}` | Attestation lookup |
| GET | `/v1/attestations/{batch_id}` | Batch attestation details |
| GET | `/v1/attestations` | List attestations |

### Internal (X-Internal-Token required)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/internal/anchor-now` | Manual anchor trigger |
| GET | `/v1/internal/anchor-status` | Anchor service config |
| GET | `/v1/internal/cron-status` | Cron health + schedule |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `EAS_PRIVATE_KEY` | ✅ | Ethereum private key for EAS attestations |
| `EAS_SCHEMA_UID` | ✅ | EAS schema identifier |
| `EAS_CHAIN` | ✅ | `sepolia` or `base` |
| `EAS_STUB_MODE` | ✅ | `true` for dev, `false` for production |
| `ECP_WEBHOOK_URL` | ✅ | LLaChat webhook endpoint |
| `ECP_WEBHOOK_TOKEN` | ✅ | Webhook auth token |
| `LLACHAT_API_URL` | ✅ | LLaChat API base URL |
| `LLACHAT_INTERNAL_TOKEN` | ✅ | Service-to-service auth token |
| `ANCHOR_INTERVAL_MINUTES` | ❌ | Cron interval (default: 60) |
| `SENTRY_DSN` | ❌ | Sentry error tracking |
| `CORS_ORIGINS` | ❌ | Comma-separated allowed origins |
| `PORT` | ❌ | Server port (default: 8080) |

## Deployment

Deployed on Railway: `ecp-server-production.up.railway.app`
Custom domain: `api.weba0.com` (when SSL ready)

```bash
# Local development
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

## Architecture

```
SDK (atlast-ecp) → LLaChat Backend → [pending batches]
                                           ↓
                    ECP Server (this) ← pulls pending batches (hourly cron)
                         ↓
                    EAS on Base chain (attestation)
                         ↓
                    Webhook → LLaChat (certificate + feed)
```

## Security

- All `/internal/*` endpoints require `X-Internal-Token` header
- Webhook payloads signed with HMAC-SHA256 (`X-ECP-Signature` header)
- Security headers: HSTS, X-Frame-Options, X-Content-Type-Options
- Timing-safe token comparison (`secrets.compare_digest`)
- Request body size limit: 10MB

## License

MIT — see [ATLAST Protocol](https://github.com/willau95/atlast-ecp/blob/main/LICENSE)
