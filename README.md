# ATLAST ECP — Evidence Chain Protocol

> *At last, trust for the Agent economy.*

**ECP (Evidence Chain Protocol)** is an open standard for **AI agent audit trails** — recording, chaining, and verifying every AI agent action with cryptographic proof. It answers the question enterprises and developers are now asking: *"Can I actually verify what my AI agent did?"*

ECP is the foundational trust layer of **ATLAST Protocol** — the accountability infrastructure for **Web A.0**.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![PyPI](https://img.shields.io/pypi/v/atlast-ecp)](https://pypi.org/project/atlast-ecp/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://pypi.org/project/atlast-ecp/)
[![Tests](https://img.shields.io/badge/Tests-134%20passing-brightgreen)](https://github.com/willau95/atlast-ecp/actions)
[![Status](https://img.shields.io/badge/Status-Alpha-orange)](https://github.com/willau95/atlast-ecp)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-purple)](https://github.com/willau95/atlast-ecp)

---

## The Problem: AI Agents Are Unaccountable

AI agents are increasingly making real decisions — executing code, sending emails, managing files, processing transactions. But today there is no standard way to answer:

- *Did this agent actually do what it claims?*
- *Can I audit my agent's full action history?*
- *Who is accountable when an AI agent makes a mistake?*
- *How do I prove compliance when regulators ask?*

This gap is the **accountability crisis of the Agent economy**. ECP solves it.

---

## Three Ways to Integrate — Pick Your Level

```
Layer 0 — Zero Code (1 line)          Layer 1 — SDK (5 lines)           Layer 2 — OTel Auto (1 line)
──────────────────────────────         ─────────────────────────         ─────────────────────────────
from atlast_ecp import wrap            from atlast_ecp import wrap       from atlast_ecp import init
from anthropic import Anthropic        client = wrap(Anthropic())        init()  # instruments 11 LLM libs
client = wrap(Anthropic())             @track(agent_id="my-agent")      # That's it. Every LLM call
# Done. Every call recorded.           def my_task(): ...                # across all libraries recorded.
```

| Layer | Effort | What You Get |
|-------|--------|-------------|
| **Layer 0** — `wrap(client)` | 1 line | Passive recording of all LLM API calls. Zero agent code changes. |
| **Layer 1** — SDK decorators | 5 lines | Structured tool calls, decision points, custom metadata. |
| **Layer 2** — `init()` OTel | 1 line | Auto-instruments 11 LLM libraries via OpenTelemetry. |

---

## Quick Start

### Install

```bash
pip install atlast-ecp

# With cryptographic signing (recommended)
pip install atlast-ecp[crypto]

# With OpenTelemetry auto-instrumentation
pip install atlast-ecp[otel]

# Everything
pip install atlast-ecp[crypto,otel]
```

### Option A: Wrap Your Client (Most Common)

```python
from atlast_ecp import wrap
from anthropic import Anthropic

client = wrap(Anthropic())
# Every API call is now recorded in a tamper-proof chain

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}]
)
# Record automatically created in .ecp/ with hash chain + signature
```

Works with **Anthropic**, **OpenAI**, **Google Gemini**, and **LiteLLM**.

### Option B: OTel Auto-Instrumentation (Zero Config)

```python
from atlast_ecp import init

init()  # Auto-instruments: openai, anthropic, google-genai, cohere,
        # mistral, ollama, transformers, langchain, crewai, llama-index, bedrock

# Now use ANY supported library normally — all calls recorded automatically
from openai import OpenAI
client = OpenAI()
client.chat.completions.create(...)  # ← Recorded via OTel span exporter
```

### Option C: MCP Server (Claude Desktop / Claude Code)

```bash
atlast-ecp-mcp
```

Add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "atlast-ecp": {
      "command": "atlast-ecp-mcp"
    }
  }
}
```

### CLI

```bash
atlast-ecp init          # Initialize .ecp/ directory
atlast-ecp register      # Register agent with ATLAST backend
atlast-ecp stats         # View local recording statistics
atlast-ecp verify        # Verify chain integrity
atlast-ecp view          # Browse recorded evidence
atlast-ecp export        # Export records as JSON
atlast-ecp flush         # Force batch upload
atlast-ecp did           # Show agent DID
```

---

## Key Properties

| Property | Description |
|----------|-------------|
| 🔒 **Privacy First** | Content never leaves your device. Only cryptographic hashes are transmitted. GDPR-compliant by design (Commit-Reveal pattern). |
| 🔗 **Tamper-Proof Chain** | Every record references the hash of the previous record. Any tampering is immediately detectable. |
| ✅ **Cryptographic Verification** | ed25519 signatures. When a record exists, it is mathematically tamper-proof — not just "trusted". |
| ⚡ **Zero-Overhead** | Async fire-and-forget recording. ECP adds <1ms latency to your agent. |
| 🌐 **On-Chain Anchoring** | Merkle roots anchored to Base via EAS (Ethereum Attestation Service). ~$3/month for unlimited records. |
| 🤖 **Passive Recording** | No self-reporting. No agent cooperation required. Works even if the agent lies. |
| 🔌 **Zero Dependencies** | Core library has zero required dependencies. `[crypto]` and `[otel]` are optional extras. |
| 🛡️ **Fail-Open** | Recording failures **never** affect your agent's operation. |

---

## How It Works

Each ECP record captures a single agent action:

```json
{
  "id": "rec_01HX...",
  "agent": "did:ecp:a3f9c2e1b7d4",
  "ts": 1710000000000,
  "step": {
    "type": "tool_call",
    "in_hash": "sha256:abc123...",
    "out_hash": "sha256:def456...",
    "summary": "(stored locally only — never uploaded)"
  },
  "flags": ["retried"],
  "chain": {
    "prev": "rec_01HW...",
    "hash": "sha256:xyz789..."
  },
  "sig": "ed25519:..."
}
```

Records are stored locally in `.ecp/`. Merkle roots are anchored on-chain periodically. **Content never leaves your device** — only hashes are transmitted.

### Architecture

```
Your Agent (any framework)
    │
    ├── wrap(client)      ← Layer 0: explicit wrapper
    ├── @track            ← Layer 1: SDK decorators  
    └── init()            ← Layer 2: OTel auto-instrumentation
         │
    ┌────┴────────────────────────────┐
    │       ECP Core Engine           │
    │  record() → chain() → sign()   │
    └────┬──────────────┬─────────────┘
         │              │
    .ecp/ (local)    Merkle Batcher
    (full records)   (hashes only)
                         │
                    ┌────┴────────────┐
                    │  ATLAST Backend  │  ← Trust Score + Leaderboard
                    │  api.llachat.com │
                    └────┬────────────┘
                         │
                    ┌────┴────────────┐
                    │  Base / EAS     │  ← On-chain anchoring
                    │  (Merkle Root)  │     ~$3/month
                    └─────────────────┘
```

**Privacy model**: Full records stay local. Only Merkle roots go on-chain. Verifiers can request specific records — you choose what to share.

---

## Supported LLM Libraries

### Via `wrap(client)` (Layer 0/1)

| Library | Usage |
|---------|-------|
| **Anthropic** | `wrap(Anthropic())` |
| **OpenAI** | `wrap(OpenAI())` |
| **Google Gemini** | `wrap(genai.Client())` |
| **LiteLLM** | `wrap(litellm)` |

### Via `init()` OTel Auto-Instrumentation (Layer 2)

Automatically instruments: `openai`, `anthropic`, `google-genai`, `cohere`, `mistralai`, `ollama`, `transformers`, `langchain`, `crewai`, `llama-index`, `bedrock`

---

## ATLAST Trust Score

ECP powers the **ATLAST Trust Score** — a verifiable reputation system for AI Agents.

Built entirely on **passive behavioral signals** (no self-reporting, no LLM-as-Judge):

| Signal | Weight | Source |
|--------|--------|--------|
| 🎯 **Reliability** | 40% | Task completion, error rate, retry rate — from ECP records |
| 🔍 **Transparency** | 30% | Chain integrity, hedge language detection |
| ⚡ **Efficiency** | 20% | Response latency distribution |
| 🏛️ **Authority** | 10% | Verified certificates, third-party validation |

Trust Scores are **portable, verifiable, and public** — agents earn reputation across any platform that integrates ECP.

View live leaderboard: [llachat.com](https://llachat.com)

---

## Compliance & Enterprise

ECP is designed for regulatory compliance from day one:

- **EU AI Act** (effective 2027): Full audit trail for AI agent decisions
- **SOC 2 / ISO 27001**: Cryptographic proof of agent behavior
- **GDPR**: Content never leaves device — only hashes transmitted
- **Insurance**: Verifiable work certificates for agent liability

---

## ATLAST Protocol

ECP is one of four sub-protocols in ATLAST (Agent Trust Layer, Accountability Standards & Transactions):

| Protocol | Full Name | Description |
|----------|-----------|-------------|
| **ECP** | Evidence Chain Protocol | Action recording, chaining & verification — *this repo* |
| **AIP** | Agent Identity Protocol | Decentralized agent identity (DID-based) |
| **ASP** | Agent Security Protocol | 6-layer security architecture for agent systems |
| **ACP** | Agent Certification Protocol | Certification standards & Trust Score issuance |

ATLAST's goal: become the **open standard** for AI agent accountability — the layer every agent platform integrates, the way HTTPS is integrated by every website.

---

## Specification

Full protocol specification: [`ECP-SPEC.md`](./ECP-SPEC.md)

Current status: **Draft v0.1** — feedback welcome via GitHub Issues.

---

## Roadmap

- [x] Core ECP recording (local chain)
- [x] ed25519 cryptographic signing
- [x] Anthropic + OpenAI + Gemini + LiteLLM wrappers
- [x] MCP Server (Claude Desktop / Claude Code)
- [x] CLI tools (init, register, verify, stats, export, flush)
- [x] OpenTelemetry auto-instrumentation (11 LLM libraries)
- [x] 134 tests passing
- [x] PyPI v0.3.0 published
- [x] Trust Score engine (live on backend)
- [ ] On-chain anchoring to Base/EAS — live mode (Q2 2026)
- [ ] Work Certificates — public verification links (Q2 2026)
- [ ] LLaChat public leaderboard launch (Q2 2026)
- [ ] LangChain / CrewAI callback adapters (Q3 2026)

---

## Links

- 🌐 **LLaChat** — Agent leaderboard & ECP explorer: [llachat.com](https://llachat.com)
- 📡 **API**: [api.llachat.com](https://api.llachat.com)
- 📜 **Web A.0 Manifesto**: [weba0.com](https://weba0.com)
- 📋 **Protocol Spec**: [ECP-SPEC.md](./ECP-SPEC.md)
- 🐦 **X/Twitter**: [@atlastprotocol](https://twitter.com/atlastprotocol)

---

## Contributing

ECP is an open protocol. Issues, PRs, and spec feedback are welcome.

```bash
git clone https://github.com/willau95/atlast-ecp.git
cd atlast-ecp/sdk
pip install -e ".[dev,crypto,otel]"
pytest tests/ -v
```

If you're building AI agent infrastructure and want to integrate ECP — open an issue or DM [@atlastprotocol](https://twitter.com/atlastprotocol).

---

## License

MIT — open protocol, open standard.

*Built by the ATLAST Protocol Working Group.*
