# ECP Reference Server

> Your own Evidence Chain Protocol server in 5 minutes.

An open-source, minimal ECP-compatible server. Implements [ECP Server Spec v1.0](../ECP-SERVER-SPEC.md).

**ECP = Git (open protocol). This server = your own GitHub.**

## Quick Start

### Option 1: pip (local)

```bash
cd server
pip install -r requirements.txt
cd .. && python -m server.main
# Server running at http://localhost:8900
```

### Option 2: Docker

```bash
cd server
docker compose up
# Server running at http://localhost:8900
```

### Option 3: uvicorn (development)

```bash
cd /path/to/atlast-ecp
uvicorn server.main:app --reload --port 8900
```

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/v1/agents/register` | — | Register an agent |
| `POST` | `/v1/batches` | `X-Agent-Key` | Upload ECP batch |
| `GET` | `/v1/agents/{handle}/profile` | — | Get agent profile |
| `GET` | `/v1/leaderboard` | — | Get ranked agents |
| `GET` | `/health` | — | Health check |

## Usage with ATLAST SDK

```bash
# 1. Register your agent
curl -X POST http://localhost:8900/v1/agents/register \
  -H "Content-Type: application/json" \
  -d '{"did": "did:ecp:my-agent", "public_key": "base64key", "handle": "my-agent"}'
# → Returns api_key

# 2. Configure SDK to push here
atlast init
# Edit ~/.atlast/config.json:
#   "endpoint": "http://localhost:8900"
#   "api_key": "atl_..."

# 3. Record & push
atlast run python my_agent.py
atlast push --endpoint http://localhost:8900 --key atl_...
```

## Configuration

All via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `ECP_DB_PATH` | `ecp_server.db` | SQLite database path |
| `ECP_HOST` | `0.0.0.0` | Bind host |
| `ECP_PORT` | `8900` | Bind port |
| `ECP_LOG_LEVEL` | `info` | Log level |
| `ECP_CORS_ORIGINS` | `*` | Allowed CORS origins |
| `ECP_WEIGHT_RELIABILITY` | `0.4` | Trust score weight |
| `ECP_WEIGHT_TRANSPARENCY` | `0.3` | Trust score weight |
| `ECP_WEIGHT_EFFICIENCY` | `0.2` | Trust score weight |
| `ECP_WEIGHT_AUTHORITY` | `0.1` | Trust score weight |

## Architecture

```
SQLite (WAL mode)
  ├── agents          — registered agents + hashed API keys
  ├── batches         — uploaded batch metadata
  └── record_hashes   — per-record hash metadata

FastAPI
  ├── /v1/agents/*    — registration + profile
  ├── /v1/batches     — batch upload + Merkle verification
  └── /v1/leaderboard — ranked agents by trust score
```

- **Zero external dependencies**: SQLite only, no PostgreSQL/Redis needed
- **Merkle verification**: Validates batch integrity on upload
- **Trust scoring**: Configurable weights (Reliability/Transparency/Efficiency/Authority)
- **Privacy by design**: Only receives hashes, never raw content

## Tests

```bash
cd /path/to/atlast-ecp
python -m pytest server/tests/ -v
```

## License

MIT — same as the ATLAST ECP SDK.
