<p align="center">
  <img src="assets/banner.svg" alt="ATLAST Protocol" width="100%">
</p>

<p align="center">
  <a href="https://pypi.org/project/atlast-ecp/"><img src="https://img.shields.io/pypi/v/atlast-ecp?color=1D4ED8&label=PyPI" alt="PyPI"></a>
  <a href="https://www.npmjs.com/package/atlast-ecp-ts"><img src="https://img.shields.io/npm/v/atlast-ecp-ts?color=059669&label=npm" alt="npm"></a>
  <a href="https://github.com/willau95/atlast-ecp/actions"><img src="https://github.com/willau95/atlast-ecp/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT"></a>
  <a href="https://weba0.com"><img src="https://img.shields.io/badge/Web_A.0-Live-1D4ED8" alt="Web A.0"></a>
</p>

<p align="center">
  <a href="https://weba0.com">Website</a> · <a href="ECP-SPEC.md">ECP Spec</a> · <a href="docs/compliance/AI-COMPLIANCE-GUIDE.md">Compliance Guide</a> · <a href="CONTRIBUTING.md">Contributing</a> · <a href="https://pypi.org/project/atlast-ecp/">PyPI</a>
</p>

---

## What is ATLAST Protocol?

**ATLAST** (Agent Layer Trust, Accountability Standards & Transactions) is an open protocol that makes AI agent work **verifiable**.

AI agents are becoming autonomous economic actors — writing code, managing finances, making decisions. But today, there is no way to verify what an agent actually did, whether it acted correctly, or who is accountable when things go wrong.

ATLAST provides the missing trust layer.

```
ATLAST Protocol
  ├── ECP — Evidence Chain Protocol     ← Live (this repo)
  ├── AIP — Agent Identity Protocol     ← Coming Q3 2026
  ├── ASP — Agent Safety Protocol       ← Coming 2027
  └── ACP — Agent Certification Protocol← Coming 2027
```

> **Think of it like this:**
> - HTTPS made websites trustworthy → **ECP makes agent actions trustworthy**
> - DNS gave websites identity → **AIP gives agents identity**
> - SSL certs proved website authenticity → **ACP proves agent competence**

---

## The Problem

The AI agent market is exploding. But **three critical problems** remain unsolved:

### 🔴 No Verifiable Record
Your agent made 500 decisions today. Something went wrong. What did it actually do? Logs exist — but logs are **deletable, editable, never evidence**. There is no immutable audit trail.

### 🔴 No Trust Across Agents
In multi-agent systems (CrewAI, AutoGen, LangGraph), Agent A passes data to Agent B. How do you verify B received exactly what A sent? **Nobody can prove data integrity across agent handoffs.** This is the blind spot of every monitoring tool.

### 🔴 No Universal Standard
LangSmith monitors LangChain agents. Arize monitors ML models. Every tool is siloed. There is **no open standard** that works across all frameworks, all languages, all providers — the way HTTP works for the web.

---

## The Solution: ECP

**ECP (Evidence Chain Protocol)** is the first layer of ATLAST — an open standard for recording, chaining, and verifying AI agent actions.

### Core Design Principles

| Principle | Implementation |
|-----------|---------------|
| **Privacy First** | Only SHA-256 hashes leave the device. Content stays local. |
| **Zero Code** | `atlast run python my_agent.py` — one command, any language |
| **Fail-Open** | Recording failures never crash your agent |
| **Progressive** | Start with 7 fields. Add chain, identity, blockchain as needed |
| **Platform Agnostic** | Not tied to any framework, provider, or platform |
| **Local by Default** | No network calls. Upload is opt-in via `atlast push` |

### How It Works

```
Your Agent                    ECP Layer                     Local Storage
    │                            │                              │
    ├── LLM API call ──────────► │                              │
    │                            ├── SHA-256(input)             │
    │                            ├── SHA-256(output)            │
    │                            ├── Detect behavioral flags    │
    │   ◄── Response (unchanged) ├── Chain to previous record   │
    │                            ├── Save ECP record ──────────►│ ~/.atlast/records.jsonl
    │                            │                              │
    │                            │    Content stays here.       │
    │                            │    Only hashes are recorded.  │
```

### ECP Record (5 Progressive Levels)

```json
// Level 1 — Core (7 fields, any language can generate this)
{
  "ecp": "1.0",
  "id": "rec_a1b2c3d4e5f6a1b2",
  "ts": 1741766400000,
  "agent": "my-agent",
  "action": "llm_call",
  "in_hash": "sha256:2cf24dba...",
  "out_hash": "sha256:486ea462..."
}

// Level 2 — + Metadata (model, latency, tokens, behavioral flags)
// Level 3 — + Chain (tamper-proof linking via prev + chain_hash)
// Level 4 — + Identity (DID + Ed25519 signature)
// Level 5 — + Blockchain Anchor (EAS on Base)
```

📖 **[Full ECP Specification →](ECP-SPEC.md)**

---

## Quick Start

### Zero Code (any language, any framework)

```bash
pip install atlast-ecp[proxy]

# One command — every LLM call is now recorded
atlast run python my_agent.py
atlast log   # View records
```

### Python SDK (one line)

```python
from atlast_ecp import wrap
from anthropic import Anthropic

client = wrap(Anthropic())  # That's it. Everything else stays the same.
response = client.messages.create(model="claude-sonnet-4-6", messages=[...])
# ✓ Every call: recorded · chained · tamper-evident
```

### Framework Adapters

```python
# LangChain
from atlast_ecp.adapters.langchain import ATLASTCallbackHandler
llm = ChatOpenAI(callbacks=[ATLASTCallbackHandler(agent="my-agent")])

# CrewAI
from atlast_ecp.adapters.crewai import ATLASTCrewCallback
crew = Crew(agents=[...], callbacks=[ATLASTCrewCallback(agent="my-crew")])
```

### CLI

```bash
atlast init                         # Initialize + generate DID
atlast record --in "query" --out "response"  # Manual record
atlast log                          # View records
atlast insights                     # Local analytics
atlast verify <record_id>           # Verify chain integrity
atlast verify --a2a a.jsonl b.jsonl # Multi-agent verification
atlast push                         # Upload to ECP server (opt-in)
```

---

## Multi-Agent Verification (A2A)

ECP is the **only protocol** that can verify data integrity across agent handoffs.

```
Agent A                          Agent B
┌─────────────┐                  ┌─────────────┐
│ out_hash: X │──── handoff ────►│ in_hash: X  │  ← Hash match = verified
└─────────────┘                  └─────────────┘
```

```bash
# Verify a multi-agent pipeline
atlast verify --a2a researcher.jsonl analyst.jsonl writer.jsonl

# Output:
#   ✅ VALID — 2 handoffs, 0 gaps
#   Topology: researcher → analyst → writer
```

**Capabilities:**
- ✅ Handoff verification (out_hash == in_hash)
- ✅ Orphan detection (output not consumed by any agent)
- ✅ Blame trace (pinpoint which agent broke the chain)
- ✅ DAG topology (parallel pipelines, not just linear)

📖 **[A2A Documentation →](docs/A2A-VERIFICATION.md)**

---

## Why Not [X]?

| | **ECP** | LangSmith | Arize AI | OpenTelemetry |
|---|---|---|---|---|
| **Purpose** | Trust & compliance audit | Developer debugging | ML monitoring | General observability |
| **Privacy** | Hash-only, content stays local | Stores raw content | Stores raw content | Stores raw content |
| **Multi-agent** | ✅ A2A cross-agent verification | ❌ Single agent trace | ❌ Single model | ❌ No agent concept |
| **Standard** | Open protocol (MIT) | Proprietary SaaS | Proprietary SaaS | Open (but no agent layer) |
| **Self-hostable** | ✅ Reference Server included | ❌ | ❌ | ✅ |
| **Blockchain** | Optional EAS anchoring | ❌ | ❌ | ❌ |
| **Framework** | Any (proxy-based) | LangChain only | ML frameworks | Any |

**ECP doesn't replace these tools.** LangSmith is for debugging. Arize is for monitoring. **ECP is for trust** — proving what happened, not just logging it.

---

## Integration Methods

| Method | Code Change | Language | Best For |
|--------|------------|----------|----------|
| `atlast run <cmd>` | **0 lines** | Any | Quick start, any agent |
| `atlast proxy` | **0 lines** | Any | Long-running services |
| `wrap(client)` | **1 line** | Python/TS | SDK integration |
| Framework adapters | **1 line** | Python | LangChain, CrewAI |
| `record_minimal()` | **1 line** | Python | Custom recording |
| OpenClaw Plugin | **Config** | Any | OpenClaw users |
| MCP Server | **Config** | Any | MCP clients |
| Go SDK | **1 line** | Go | Cloud-native agents |

---

## Ecosystem

```
┌─────────────────────────────────────────────────────┐
│                  ATLAST Protocol                     │
│                                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────┐ ┌───────────┐  │
│  │ Python   │ │ TypeScript│ │ Go   │ │ Reference │  │
│  │ SDK      │ │ SDK      │ │ SDK  │ │ Server    │  │
│  │ PyPI     │ │ npm      │ │      │ │ FastAPI   │  │
│  └──────────┘ └──────────┘ └──────┘ └───────────┘  │
│                                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ CLI      │ │ Proxy    │ │ Adapters │            │
│  │ atlast   │ │ Zero-code│ │ LangChain│            │
│  │          │ │          │ │ CrewAI   │            │
│  └──────────┘ └──────────┘ └──────────┘            │
│                                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ MCP      │ │ OpenClaw │ │ OTel     │            │
│  │ Server   │ │ Plugin   │ │ Exporter │            │
│  └──────────┘ └──────────┘ └──────────┘            │
└─────────────────────────────────────────────────────┘
          │                          │
          ▼                          ▼
   ┌─────────────┐          ┌──────────────┐
   │ Self-hosted │          │  LLaChat.com │
   │ ECP Server  │          │  (optional)  │
   └─────────────┘          └──────────────┘
```

### SDKs
- **[Python SDK](sdk/)** — `pip install atlast-ecp` — 19 modules, 387 tests
- **[TypeScript SDK](sdk-ts/)** — `npm install atlast-ecp-ts` — 12 tests
- **[Go SDK](sdk-go/)** — Pure stdlib, zero dependencies

### Tools
- **[CLI](sdk/atlast_ecp/cli.py)** — `atlast` command with 14 subcommands
- **[Proxy](sdk/atlast_ecp/proxy.py)** — Transparent HTTP proxy for any LLM API
- **[Insights](sdk/atlast_ecp/insights.py)** — Local analytics (`atlast insights`)
- **[MCP Server](sdk/atlast_ecp/mcp_server.py)** — 8 tools for MCP-compatible clients

### Server
- **[Reference Server](server/)** — Open-source FastAPI + SQLite ECP server
- **[ECP Server Spec](ECP-SERVER-SPEC.md)** — Build your own ECP server

### Documentation
- **[ECP Specification](ECP-SPEC.md)** — Full protocol spec (5 levels)
- **[A2A Verification](docs/A2A-VERIFICATION.md)** — Multi-agent verification
- **[Compliance Guide](docs/compliance/AI-COMPLIANCE-GUIDE.md)** — Global AI regulation mapping
- **[Contributing](CONTRIBUTING.md)** — How to contribute

---

## Global AI Compliance

ECP maps to **every major AI regulation** — organized by capability, not by law:

| ECP Capability | EU AI Act | China GenAI | US NIST RMF | APAC |
|---------------|-----------|-------------|-------------|------|
| Audit Trail | Art. 12 ✅ | Art. 17 ✅ | MAP 1.5 ✅ | ✅ |
| Privacy | GDPR Art. 25 ✅ | PIPL Art. 7 ✅ | — | PDPA ✅ |
| Transparency | Art. 52 ✅ | Art. 4 ✅ | GOVERN 1.4 ✅ | ✅ |
| Anomaly Detection | Art. 9 ✅ | Art. 14 ✅ | MEASURE 2.6 ✅ | ✅ |
| Agent Identity | Art. 14 ✅ | — | GOVERN 1.1 ✅ | ✅ |

📖 **[Full Compliance Guide →](docs/compliance/AI-COMPLIANCE-GUIDE.md)**

---

## Reference ECP Server

Run your own ECP server in 5 minutes:

```bash
cd server && pip install -r requirements.txt
cd .. && python -m server.main
# Server running at http://localhost:8900
```

Or with Docker:
```bash
cd server && docker compose up
```

**ECP is to agent trust what Git is to code.** This server is your own GitHub — anyone can host one.

📖 **[Server Documentation →](server/README.md)**

---

## Supported LLM Providers

The ATLAST Proxy auto-detects and records calls to:

| Provider | Format | Status |
|----------|--------|--------|
| OpenAI | OpenAI API | ✅ |
| Anthropic | Anthropic API | ✅ |
| Google Gemini | Gemini API | ✅ |
| Qwen (通义千问) | OpenAI-compatible | ✅ |
| DeepSeek | OpenAI-compatible | ✅ |
| Kimi (月之暗面) | OpenAI-compatible | ✅ |
| MiniMax | MiniMax API | ✅ |
| Yi (零一万物) | OpenAI-compatible | ✅ |
| Groq / Together / etc. | OpenAI-compatible | ✅ |

---

## Open Source Community

ECP is **MIT licensed** and built for the community:

- 🐛 **[Report bugs](.github/ISSUE_TEMPLATE/bug_report.md)** — Structured bug reports
- 💡 **[Request features](.github/ISSUE_TEMPLATE/feature_request.md)** — Share your ideas
- 🔧 **[Contributing guide](CONTRIBUTING.md)** — Dev setup, code conventions, PR process
- 🔒 **[Security policy](SECURITY.md)** — Responsible disclosure
- 📜 **[Code of Conduct](CODE_OF_CONDUCT.md)** — Contributor Covenant v2.1

### How to Contribute

```bash
git clone https://github.com/willau95/atlast-ecp.git
cd atlast-ecp/sdk
pip install -e ".[dev,proxy,adapters]"
pytest -v  # 387 tests, all must pass
```

We especially welcome:
- **New framework adapters** (AutoGen, LangGraph, MetaGPT...)
- **New language SDKs** (Rust, Java, Ruby...)
- **ECP Server implementations** (in any language)
- **Compliance mappings** for additional regulations
- **Documentation translations** (中文, 日本語, 한국어, Español...)

---

## Roadmap

| Phase | Status | Focus |
|-------|--------|-------|
| **ECP v1.0** | ✅ Live | Evidence recording, 3 SDKs, CLI, Proxy |
| **Reference Server** | ✅ Live | Self-hosted ECP server |
| **A2A Verification** | ✅ Live | Multi-agent chain verification |
| **Compliance Guides** | ✅ Live | EU AI Act, China, US, APAC |
| **AIP** | 🔜 Q3 2026 | Decentralized agent identity |
| **ASP** | 📋 2027 | Behavioral safety standard |
| **ACP** | 📋 2027 | Evidence-backed certification |

---

## License

MIT — free for personal and commercial use.

---

<p align="center">
  <b>ATLAST Protocol</b> — At last, trust for the Agent economy.
  <br><br>
  <a href="https://weba0.com">weba0.com</a> · <a href="https://github.com/willau95/atlast-ecp">GitHub</a> · <a href="https://pypi.org/project/atlast-ecp/">PyPI</a> · <a href="https://www.npmjs.com/package/atlast-ecp-ts">npm</a>
</p>
