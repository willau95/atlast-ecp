<p align="center">
  <img src="assets/banner.svg" alt="ATLAST Protocol" width="100%">
</p>

<p align="center">
  <a href="https://pypi.org/project/atlast-ecp/"><img src="https://img.shields.io/pypi/v/atlast-ecp?color=1D4ED8&label=PyPI" alt="PyPI"></a>
  <a href="https://www.npmjs.com/package/atlast-ecp-ts"><img src="https://img.shields.io/npm/v/atlast-ecp-ts?color=059669&label=npm" alt="npm"></a>
  <a href="https://github.com/willau95/atlast-ecp/actions"><img src="https://github.com/willau95/atlast-ecp/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT"></a>
  <a href="https://weba0.com"><img src="https://img.shields.io/badge/Web_A.0-Live-1D4ED8" alt="Web A.0"></a>
  <a href="https://llachat.com"><img src="https://img.shields.io/badge/LLaChat-Marketplace-8B5CF6" alt="LLaChat"></a>
</p>

<p align="center">
  <a href="https://weba0.com">Website</a> · <a href="https://llachat.com">LLaChat</a> · <a href="ECP-SPEC.md">ECP Spec</a> · <a href="docs/compliance/AI-COMPLIANCE-GUIDE.md">Compliance Guide</a> · <a href="CONTRIBUTING.md">Contributing</a> · <a href="https://pypi.org/project/atlast-ecp/">PyPI</a> · <a href="README.zh-CN.md">中文文档</a>
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

AI agents are no longer tools you click — they are **autonomous actors** that write code, manage money, negotiate contracts, and make decisions on your behalf. The agent economy is here. But ask yourself:

### 🔴 Problem 1: Your Agent Works in the Dark

Your agent made 500 decisions today. A client complains. A transaction fails. A contract is wrong.

**What did your agent actually do?**

You check the logs. But logs are deletable. Editable. Written by the same system that made the mistake. **Logs are not evidence.** In court, in compliance, in any dispute — your agent's work history is worth nothing. It's as if your employee worked an entire year with no records, no receipts, no paper trail.

> *Would you trust an employee who refuses to keep records of their work?*
> *Then why do you trust an agent that can't?*

### 🔴 Problem 2: Multi-Agent = Multi-Risk, Zero Accountability

You deploy a CrewAI pipeline: Researcher → Analyst → Writer. The final report contains fabricated data. **Which agent is responsible?**

Today, you cannot answer this question. Agent A says it sent the right data. Agent B says it received garbage. There is **no way to verify who is telling the truth** — because there is no cryptographic proof of what was passed between them.

In a world moving toward 10-agent, 50-agent, 100-agent orchestrations, this is not a minor inconvenience. **This is the single biggest barrier to enterprise adoption of multi-agent systems.**

> *Every supply chain has receipts. Every bank transfer has a record. But when Agent A hands off to Agent B — nothing. The most critical handoff in AI has zero verification.*

### 🔴 Problem 3: Your Agent's Reputation Belongs to Someone Else

Your agent completed 10,000 tasks flawlessly over 6 months. That track record is worth something — it's proof of competence, reliability, trust.

But where does that reputation live? **On someone else's platform.** When they change their terms, shut down, or get acquired — your agent's entire proof of work **disappears**. You built it. They own it.

There is no portable, verifiable, agent-owned proof of work. No "résumé" that belongs to the agent itself.

> *Imagine if your LinkedIn profile was deleted every time you changed jobs. That's the reality for every AI agent today.*

### 🔴 Problem 4: Regulators Are Coming, and You Have No Answer

The EU AI Act takes effect in 2027. China's GenAI regulations are already enforced. Every major economy is writing AI accountability laws.

They will ask: **"Show me what your AI agent did, when, and why."**

Today, you have nothing to show them. No standard format. No verifiable chain. No audit trail that a regulator would accept. You are running autonomous AI systems with **zero compliance infrastructure**.

> *HTTP didn't wait for governments to mandate web security. HTTPS became the standard because the market needed trust. The agent economy needs the same thing — now, before the mandates arrive.*

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

<p align="center">
  <img src="assets/how-it-works.svg" alt="How ECP Works" width="100%">
</p>

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

### For Claude Code / AI Coding Agents

Copy this and paste it to your AI agent:

> Install ATLAST ECP on this machine to create a tamper-proof evidence chain of all your work. ATLAST ECP is an open-source protocol that records every action with cryptographic proof — so I can verify what you did, track your reliability, and have a complete audit trail.
>
> Step 1 — Install:
> ```
> pip3 install atlast-ecp
> ```
>
> Step 2 — Initialize (generates your unique identity + local storage):
> ```
> python3 -m atlast_ecp.cli init
> ```
>
> Step 3 — Verify everything is working:
> ```
> python3 -m atlast_ecp.cli doctor
> ```
>
> Tell me the output of each step.

That's it. Your agent handles the rest.

### Zero Code (any language, any framework)

```bash
pip install atlast-ecp

# One command — every LLM call is now recorded
atlast run python my_agent.py
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
atlast log                          # View records
atlast verify <record_id>           # Verify chain integrity
atlast push                         # Upload to ECP server (opt-in)
atlast flush                        # Immediate batch upload
atlast proxy --port 8340            # Start transparent proxy
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

<p align="center">
  <img src="assets/ecosystem.svg" alt="ATLAST Ecosystem" width="100%">
</p>

### SDKs
- **[Python SDK](sdk/)** — `pip install atlast-ecp` — 19 modules, 387 tests
- **[TypeScript SDK](sdk/typescript/)** — `npm install atlast-ecp-ts` — 43 tests
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
pytest -v  # 680+ tests, all must pass
```

We especially welcome:
- **New framework adapters** (AutoGen, LangGraph, MetaGPT...)
- **New language SDKs** (Rust, Java, Ruby...)
- **ECP Server implementations** (in any language)
- **Compliance mappings** for additional regulations
- **Documentation translations** (中文, 日本語, 한국어, Español...)

---

## LLaChat — The Agent Marketplace Powered by ATLAST

ATLAST Protocol provides the trust infrastructure; **[LLaChat](https://llachat.com)** is the marketplace where that trust is consumed.

- 🏆 **Agent Leaderboard** — AI agents ranked by verified Trust Score (0–1000)
- 📊 **Evidence-backed profiles** — Every agent's track record is cryptographically verifiable via ECP
- 🔍 **Agent discovery** — Find the best agent for any task, backed by proof of performance

> *If ATLAST is the credit score system, LLaChat is the marketplace where that score matters.*

→ **[Visit LLaChat](https://llachat.com)** · [AI Agent Trust Score explained](https://weba0.com/resources/ai-agent-trust-score.html)

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

---

### Learn More

- [What is ATLAST Protocol?](https://weba0.com/what-is/atlast-protocol.html) — Full overview of the trust infrastructure
- [What is Web A.0?](https://weba0.com/what-is/web-a0.html) — The agent era of the internet
- [Evidence Chain Protocol (ECP)](https://weba0.com/protocol/evidence-chain-protocol-ecp.html) — How tamper-proof audit trails work
- [AI Agent Trust Score](https://weba0.com/resources/ai-agent-trust-score.html) — 0–1000 rating system for agent reliability
- [EU AI Act Compliance](https://weba0.com/use-cases/ai-agent-compliance-eu-ai-act.html) — How ATLAST satisfies 2027 regulations
- [AI Agent Monitoring & Observability](https://weba0.com/use-cases/ai-agent-monitoring-observability.html) — Beyond traditional monitoring
- [AI Agent Identity & Verification](https://weba0.com/use-cases/ai-agent-identity-verification.html) — DID-based agent identity
