# ATLAST Protocol — Evidence Chain Protocol (ECP)

> **Trust infrastructure for the Agent economy.**  
> Like HTTPS for websites, ECP makes AI agent actions verifiable.

[![PyPI](https://img.shields.io/pypi/v/atlast-ecp)](https://pypi.org/project/atlast-ecp/)
[![Tests](https://github.com/willau95/atlast-ecp/actions/workflows/ci.yml/badge.svg)](https://github.com/willau95/atlast-ecp/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## What is ECP?

ECP is an open standard for recording what AI agents do — with cryptographic proof. When your agent makes an API call, uses a tool, or sends a message, ECP creates a tamper-proof evidence record.

**Your content never leaves your device.** Only SHA-256 hashes are recorded.

---

## Quick Start

### Option A: Zero Code (recommended)

```bash
pip install atlast-ecp[proxy]
atlast run python my_agent.py
atlast log
```

That's it. Every LLM API call your agent makes is now recorded as ECP evidence.

### Option B: One-Line SDK

```python
from atlast_ecp import wrap
from anthropic import Anthropic

client = wrap(Anthropic())  # Everything else stays the same
response = client.messages.create(model="claude-sonnet-4-6", messages=[...])

# ECP records are silently saved to ~/.ecp/records/
```

### Option C: CLI

```bash
# Record manually
echo '{"in":"What is 2+2?","out":"4"}' | atlast record

# Or with flags
atlast record --in "What is 2+2?" --out "4" --agent my-math-agent

# View records
atlast log
```

---

## How It Works

```
Your Agent                    ATLAST                      Local Storage
    │                            │                             │
    ├── LLM API call ──────────► │                             │
    │                            ├── SHA-256(input)            │
    │                            ├── SHA-256(output)           │
    │                            ├── Detect behavioral flags   │
    │   ◄── Response (unchanged) ├── Save ECP record ─────────►│ ~/.ecp/records/
    │                            │                             │
    │                            │    Content stays here.      │
    │                            │    Only hashes are recorded. │
```

**Privacy:** Your prompts and responses never leave your device. ECP records contain only hashes.

**Fail-Open:** If recording fails, your agent keeps running normally. ECP never crashes your agent.

---

## ECP Record Format

ECP uses a progressive format — start simple, add complexity as needed:

### Level 1: Core (6 fields)
```json
{
  "ecp": "1.0",
  "id": "rec_a1b2c3d4e5f6a1b2",
  "ts": 1741766400000,
  "agent": "my-agent",
  "action": "llm_call",
  "in_hash": "sha256:2cf24dba5fb0a30e...",
  "out_hash": "sha256:486ea46224d1bb4f..."
}
```

### Level 2: + Metadata
```json
{
  "...core fields...",
  "meta": {
    "model": "claude-sonnet-4-6",
    "tokens_in": 500,
    "tokens_out": 200,
    "latency_ms": 1200,
    "flags": ["hedged"]
  }
}
```

### Level 3: + Chain (tamper-proof linking)
```json
{ "...": "...", "prev": "rec_previous_id", "chain_hash": "sha256:..." }
```

### Level 4: + Identity (cryptographic DID + signature)
```json
{ "...": "...", "agent": "did:ecp:a1b2c3d4...", "sig": "ed25519:aabb..." }
```

### Level 5: + Blockchain Anchor
```json
{ "...": "...", "anchor": { "chain": "base", "tx": "0x...", "batch": "batch_..." } }
```

See [ECP-SPEC.md](ECP-SPEC.md) for the full specification.

---

## Behavioral Flags

ECP passively detects behavioral patterns. Agents cannot fake these — they're computed by rule engines, not self-reported.

| Flag | Signal | Meaning |
|------|--------|---------|
| `retried` | ⚠️ | Agent was asked to redo this task |
| `hedged` | ℹ️ | Output contained uncertainty language |
| `error` | ⚠️ | Agent returned an error |
| `human_review` | ✅ | Agent requested human verification |
| `incomplete` | ⚠️ | Task ended without resolution |

---

## CLI Reference

```bash
# Setup
atlast init                    # Initialize ~/.ecp/ + generate DID
atlast init --minimal          # Initialize without DID

# Recording
atlast record                  # Create record from stdin JSON or --in/--out flags
atlast record --full           # Create full record with chain + signature
atlast run <command>           # Run any command with auto-recording proxy

# Viewing
atlast log                     # View latest records
atlast log --limit 20          # View more
atlast stats                   # Show trust signal summary
atlast verify <record_id>      # Verify chain integrity

# Publishing (optional)
atlast push                    # Upload to ECP server (e.g., LLaChat)
atlast register                # Register agent DID
atlast certify "Task name"     # Issue work certificate

# Proxy
atlast proxy --port 8340       # Start standalone proxy
```

---

## ATLAST Proxy

The proxy intercepts LLM API calls transparently. Zero code changes required.

```bash
# Standalone
atlast proxy --port 8340
OPENAI_BASE_URL=http://localhost:8340 python my_agent.py

# All-in-one (recommended)
atlast run python my_agent.py
```

**Supported providers** (auto-detected):

| Provider | Format |
|----------|--------|
| OpenAI | OpenAI API |
| Anthropic | Anthropic API |
| Google Gemini | Gemini API |
| Qwen (通义千问) | OpenAI-compatible |
| Kimi (月之暗面) | OpenAI-compatible |
| DeepSeek | OpenAI-compatible |
| MiniMax | MiniMax API |
| Yi (零一万物) | OpenAI-compatible |
| Groq, Together, etc. | OpenAI-compatible |

Install proxy support: `pip install atlast-ecp[proxy]`

---

## Python SDK

```python
from atlast_ecp import wrap, record_minimal

# Option 1: Wrap your LLM client (automatic recording)
from anthropic import Anthropic
client = wrap(Anthropic())

# Option 2: Record manually (minimal — no DID needed)
record_minimal("user prompt", "agent response", agent="my-agent")

# Option 3: Full recording with chain + signature
from atlast_ecp import record
record(input_content="prompt", output_content="response", model="gpt-4")
```

Supported clients for `wrap()`: Anthropic, OpenAI, Google Gemini, LiteLLM.

---

## TypeScript SDK

```bash
npm install @atlast/ecp   # (coming soon — available in sdk-ts/)
```

```typescript
import { wrap } from '@atlast/ecp';
import OpenAI from 'openai';

const client = wrap(new OpenAI());
```

---

## Publishing to LLaChat (Optional)

ECP records are local by default. To publish your agent's trust profile:

```bash
# 1. Register your agent
atlast register --name "My Coding Agent"

# 2. Push records
atlast push --endpoint https://api.llachat.com --key YOUR_API_KEY

# 3. View your profile
# https://llachat.com/agent/did:ecp:your_did
```

**LLaChat** is to ECP what GitHub is to Git — an optional platform for showcasing your agent's verified work history.

---

## Integration Methods

| Method | Lines of Code | Language | Best For |
|--------|--------------|----------|----------|
| `atlast run` | 0 | Any | Quick start, any existing agent |
| `atlast proxy` | 0 | Any | Long-running agents, custom setup |
| `wrap(client)` | 1 | Python/TS | Python/TS projects |
| `record_minimal()` | 1 | Python | Custom recording points |
| CLI `atlast record` | 0 | Any | Scripts, pipelines |
| OpenClaw Plugin | Config | Any | OpenClaw users |
| MCP Server | Config | Any | MCP-compatible clients |

---

## Privacy & Security

- **Content never leaves your device** — only SHA-256 hashes are stored in ECP records
- **Local-first** — all records saved to `~/.ecp/records/`, no network calls by default
- **Publishing is opt-in** — you explicitly choose to `atlast push`
- **Private keys stay local** — Ed25519 keys in `~/.ecp/identity.json` are never transmitted
- **Fail-Open** — recording failures never affect your agent's operation

---

## Architecture

```
ECP Protocol (open standard)
├── Specification (ECP-SPEC.md)
├── Python SDK (pip install atlast-ecp)
├── TypeScript SDK (sdk-ts/)
├── CLI (atlast command)
├── Proxy (atlast proxy / atlast run)
├── MCP Server (for MCP-compatible clients)
└── OpenClaw Plugin (integrations/)

LLaChat Platform (optional consumer)
├── Trust Score computation
├── Agent Profiles & Leaderboard
├── Work Certificates
└── On-chain anchoring (EAS / Base)
```

---

## Contributing

ECP is open source (MIT). Contributions welcome!

```bash
git clone https://github.com/willau95/atlast-ecp.git
cd atlast-ecp/sdk
pip install -e ".[dev]"
pytest tests/
```

---

## License

MIT — free for personal and commercial use.

---

*ATLAST Protocol — At last, trust for the Agent economy.*
