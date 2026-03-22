# ECP Server Deployment Guide

## Railway (Recommended)

The ECP Server is deployed on [Railway](https://railway.app) with auto-deploy from `main` branch.

### Prerequisites

- Railway account
- PostgreSQL database (Railway add-on)
- EAS private key (for blockchain anchoring)

### Environment Variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `DATABASE_URL` | ✅ | PostgreSQL connection string | `postgresql://user:pass@host:5432/db` |
| `EAS_PRIVATE_KEY` | ✅ | Ethereum wallet private key for EAS | `0x...` (64 hex chars) |
| `EAS_SCHEMA_UID` | ✅ | EAS schema UID | `0xa67da7e...` |
| `EAS_CHAIN` | ✅ | `sepolia` or `base` | `sepolia` |
| `EAS_STUB_MODE` | ❌ | `true` to skip real anchoring | `false` |
| `ECP_WEBHOOK_URL` | ❌ | Webhook endpoint for attestation events | `https://api.llachat.com/v1/internal/ecp-webhook` |
| `ECP_WEBHOOK_TOKEN` | ❌ | HMAC shared secret for webhook | `b84ca16a...` |
| `LLACHAT_API_URL` | ❌ | LLaChat API base URL | `https://api.llachat.com` |
| `LLACHAT_INTERNAL_TOKEN` | ❌ | Internal API token | UUID |
| `SENTRY_DSN` | ❌ | Sentry error tracking | `https://...@sentry.io/...` |
| `PORT` | ❌ | Server port (default: 8080) | `8080` |
| `ANCHOR_INTERVAL_MINUTES` | ❌ | Cron interval (default: 60) | `60` |
| `CORS_ORIGINS` | ❌ | Allowed origins (comma-separated) | `https://llachat.com,https://weba0.com` |

### Railway Setup

```bash
# 1. Install Railway CLI
npm install -g @railway/cli

# 2. Login and link project
railway login
railway link

# 3. Set root directory to server/
# In Railway dashboard: Settings → Root Directory → server

# 4. Add PostgreSQL
# Railway dashboard → New → Database → PostgreSQL

# 5. Set environment variables
railway variables set EAS_PRIVATE_KEY=0x...
railway variables set EAS_SCHEMA_UID=0xa67da7e...
railway variables set EAS_CHAIN=sepolia
railway variables set EAS_STUB_MODE=false

# 6. Deploy
railway up  # or push to main for auto-deploy
```

### Custom Domain

```bash
# Add CNAME record: api.weba0.com → <railway-domain>.up.railway.app
# Railway auto-provisions SSL via Let's Encrypt
```

## Docker (Self-Hosted)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server/ .
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

```bash
docker build -t ecp-server .
docker run -p 8080:8080 \
  -e DATABASE_URL=postgresql://... \
  -e EAS_PRIVATE_KEY=0x... \
  -e EAS_SCHEMA_UID=0xa67da7e... \
  -e EAS_CHAIN=sepolia \
  ecp-server
```

## Health Check

```bash
curl https://api.weba0.com/health
# {"status": "ok", "version": "1.0.0", "chain": "sepolia"}
```

## Monitoring

- **Sentry**: Automatic error capture (set `SENTRY_DSN`)
- **Prometheus**: Metrics at `/metrics` (batch count, latency, error rates)
- **Health**: `/health` endpoint for uptime monitoring
- **Alerting**: 3-consecutive-failure threshold configured in Sentry
