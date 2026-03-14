# ATLAST ECP — Evidence Chain Protocol

> *At last, trust for the Agent economy.*

**ECP (Evidence Chain Protocol)** is an open standard for **AI agent audit trails** — recording, chaining, and verifying every AI agent action with cryptographic proof. It answers the question enterprises and developers are now asking: *"Can I actually verify what my AI agent did?"*

ECP is the foundational trust layer of **ATLAST Protocol** — the accountability infrastructure for **Web A.0**.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://pypi.org/project/atlast-ecp/)
[![Tests](https://img.shields.io/badge/Tests-85%20passing-brightgreen)](https://github.com/willau95/atlast-ecp/actions)
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

## Quick Start

### One line. That's it.

```python
from atlast_ecp import wrap
from anthropic import Anthropic

client = wrap(Anthropic())  # Every API call is now recorded in a tamper-proof chain
```

ECP records every agent action **passively** — zero code changes to your agent logic. Fail-open by design: if recording fails, your agent continues uninterrupted.

### Install

```bash
pip install atlast-ecp

# With cryptographic signing (recommended for production)
pip install atlast-ecp[crypto]
```

### MCP Server (Claude Desktop / Claude Code)

```bash
# Install and run as MCP server
pip install atlast-ecp
atlast-ecp-mcp
```

Add to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "atlast-ecp": {
      "command": "atlast-ecp-mcp"
    }
  }
}
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
| 🔌 **Zero Dependencies** | Core library has zero required dependencies. Works anywhere Python runs. |

---

## How AI Agent Audit Trails Work

Each ECP record captures a single agent action:

```json
{
  "id": "ecp_01HX...",
  "agent": "did:ecp:a3f9c2e1b7d4",
  "ts": 1710000000000,
  "step": {
    "type": "tool_call",
    "in_hash": "sha256:abc123...",
    "out_hash": "sha256:def456...",
    "summary": "(stored locally only — never uploaded)"
  },
  "chain": {
    "prev": "ecp_01HW...",
    "hash": "sha256:xyz789..."
  },
  "sig": "ed25519:..."
}
```

Records are stored locally in `.ecp/`. Merkle roots are anchored on-chain periodically. **Content never leaves your device** — only hashes are transmitted.

This gives you a complete, verifiable **AI agent audit trail** that satisfies:
- Internal compliance requirements
- EU AI Act accountability obligations (effective 2027)
- Enterprise vendor due diligence
- Insurance and liability documentation

---

## ATLAST Trust Score

ECP powers the **ATLAST Trust Score** — a verifiable reputation system for AI Agents.

Built on three **passive behavioral signals** (no self-reporting, no LLM-as-Judge):

| Signal | Weight | Description |
|--------|--------|-------------|
| 🎯 **Task Completion Rate** | 40% | Standardized benchmark tasks across model types |
| 🔄 **Retry Rate** | 35% | How often does the agent need to self-correct? |
| 🗣️ **Hedge Language Score** | 25% | Passive NLP classifier — local, no API calls |

Trust Scores are **portable, verifiable, and public** — agents earn reputation across any platform that integrates ECP.

---

## Integrations

| Platform | Status | Notes |
|----------|--------|-------|
| **Anthropic Claude** (`anthropic`) | ✅ Ready | `wrap(Anthropic())` |
| **OpenAI** (`openai`) | ✅ Ready | `wrap(OpenAI())` |
| **LangChain** | 🔄 Coming Soon | Callback handler |
| **Claude Desktop (MCP)** | ✅ Ready | `atlast-ecp-mcp` |
| **Claude Code (MCP)** | ✅ Ready | MCP stdio server |
| **OpenClaw** | 🔄 Coming Soon | `openclaw plugin add atlast/ecp` |

---

## Architecture

```
Your Agent
    │
    ▼
┌─────────────────────────────────────┐
│         ECP Wrapper Layer           │  ← Zero-overhead async recording
│   (Intercepts every LLM API call)   │
└─────────────┬───────────────────────┘
              │
    ┌─────────┴─────────┐
    ▼                   ▼
.ecp/ (local)     Merkle Batcher
(full records)    (hashes only)
                        │
                        ▼
              ┌─────────────────┐
              │  Base / EAS     │  ← On-chain anchoring
              │  (Merkle Root)  │     ~$3/month
              └─────────────────┘
```

**Privacy model**: Full records stay local. Only Merkle roots go on-chain. Verifiers can request specific records — you choose what to share.

---

## Web A.0: Why This Matters Now

We are entering **Web A.0** — the era where AI Agents act, transact, and make decisions on behalf of humans at scale.

Web 1.0 → Information  
Web 2.0 → Social Identity  
Web 3.0 → Ownership  
**Web A.0 → Agent Accountability**

In Web A.0, the critical question shifts from *"Can this AI do the task?"* to **"Can I trust this AI Agent's track record?"**

ECP is the **TCP/IP of agent trust** — the foundational protocol that makes Web A.0 possible.

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
- [x] Anthropic + OpenAI wrappers
- [x] MCP Server (Claude Desktop / Claude Code)
- [x] 85 tests passing
- [ ] On-chain anchoring to Base/EAS (Q2 2026)
- [ ] Trust Score computation engine (Q2 2026)
- [ ] LLaChat public leaderboard (Q2 2026)
- [ ] ECP Verifier CLI (`atlast verify <record-id>`) (Q3 2026)
- [ ] LangChain / LlamaIndex integrations (Q3 2026)

---

## Links

- 🌐 **LLaChat** — Agent leaderboard & ECP explorer: [llachat.com](https://llachat.com)
- 📜 **Web A.0 Manifesto**: [weba0.com](https://weba0.com)
- 📋 **Protocol Spec**: [ECP-SPEC.md](./ECP-SPEC.md)
- 🐦 **X/Twitter**: [@atlastprotocol](https://twitter.com/atlastprotocol)

---

## Contributing

ECP is an open protocol. Issues, PRs, and spec feedback are welcome.

If you're building AI agent infrastructure and want to integrate ECP — open an issue or DM [@atlastprotocol](https://twitter.com/atlastprotocol).

---

## License

MIT — open protocol, open standard.

*Built by the ATLAST Protocol Working Group.*

---

*Keywords: AI agent audit trail, AI agent accountability, Evidence Chain Protocol, ATLAST Protocol, agent trust score, AI agent verification, MCP server, Claude agent recording, LLM audit log, Web A.0, agent compliance, EU AI Act compliance*
