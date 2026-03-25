# ATLAST ECP Server

FastAPI backend for the Evidence Chain Protocol — EAS on-chain anchoring, verification, and webhook dispatch.

**Live**: https://api.weba0.com

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health`, `/v1/health` | — | Health check |
| GET | `/.well-known/ecp.json` | — | Service discovery |
| GET | `/v1/stats` | — | Global anchoring statistics |
| POST | `/v1/verify/merkle` | — | Verify Merkle tree integrity |
| GET | `/v1/verify/{uid}` | — | Check EAS attestation |
| GET | `/v1/attestations` | — | List attestations |
| GET | `/v1/attestations/{id}` | — | Attestation detail |
| GET | `/metrics` | — | Prometheus metrics |
| POST | `/v1/internal/anchor-now` | `X-Internal-Token` | Manual anchor trigger |
| GET | `/v1/internal/anchor-status` | `X-Internal-Token` | Anchor service status |
| GET | `/v1/internal/cron-status` | `X-Internal-Token` | Cron job status |

## Deployment (Railway)

This server runs on [Railway](https://railway.app) from the `server/` directory of the monorepo.

### Setup

1. Link Railway project: `cd server && railway link`
2. Set Root Directory to `server` in Railway Dashboard → Settings
3. Deploy: `railway up` (or auto-deploy from GitHub push)

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `EAS_PRIVATE_KEY` | EAS signer wallet private key | `0x...` |
| `EAS_SCHEMA_UID` | EAS schema UID | `0xa67da7e...` |
| `EAS_CHAIN` | `sepolia` or `base` | `sepolia` |
| `LLACHAT_API_URL` | LLaChat API base URL | `https://api.llachat.com` |
| `LLACHAT_INTERNAL_TOKEN` | Internal auth token (UUID) | `4b141c34-...` |
| `ECP_WEBHOOK_URL` | Webhook delivery URL | `https://api.llachat.com/v1/internal/ecp-webhook` |
| `ECP_WEBHOOK_TOKEN` | HMAC signing secret | `b84ca16a...` |
| `ENVIRONMENT` | `development` or `production` | `production` |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `ANCHOR_INTERVAL_MINUTES` | `60` | Cron anchor interval |
| `EAS_STUB_MODE` | `false` | Skip real EAS (for testing) |
| `SENTRY_DSN` | — | Sentry error tracking |
| `PORT` | `8000` | HTTP port |

## Development

```bash
cd server
pip install -r requirements.txt
cp .env.example .env  # Edit with your values
uvicorn app.main:app --reload --port 8000
```

## Architecture

See [ARCHITECTURE.md](../ARCHITECTURE.md) and [INTERFACE-CONTRACT.md](../INTERFACE-CONTRACT.md).
