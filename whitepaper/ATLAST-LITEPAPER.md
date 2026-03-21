# ATLAST Protocol — Litepaper

**The Trust Standard for AI Agents**
**Version 1.0 · March 2026**
**weba0.com**

---

## The Problem

AI agents are making consequential decisions every day — reviewing legal contracts, managing financial portfolios, recommending medical treatments. But when something goes wrong, no one can answer the most basic question:

> **"What did the agent actually do?"**

There is no record. No proof. No accountability.

Current logging tools (LangSmith, Langfuse, Datadog) capture debugging telemetry — useful for engineers, useless for regulators, courts, or anyone who needs to *prove* what happened.

**A log is a claim. Evidence is a cryptographic proof.**

With the EU AI Act entering enforcement in 2027, this is no longer optional. It's the law.

---

## The Solution: ATLAST Protocol

**ATLAST** (Agent-Layer Accountability Standards & Transactions) is an open protocol that gives every AI agent a **verifiable evidence chain** — a tamper-proof record of everything it did, anchored to a public blockchain.

### How It Works (3 Steps)

```
Step 1: RECORD
  Agent performs an action (LLM call, tool use, decision)
  SDK automatically computes a cryptographic hash
  Content stays on your device — only the hash is transmitted

Step 2: CHAIN
  Each record references the previous record's hash
  Modifying any record breaks the chain — tampering is instantly detectable

Step 3: ANCHOR
  Batches of hashes form a Merkle tree
  The Merkle root is written to the blockchain (EAS on Base)
  Now it's permanent, public, and independently verifiable
```

### The Privacy Guarantee

```
Your device:    Full content (encrypted, your keys)
ATLAST server:  Only hashes (cannot read your data)
Blockchain:     Only Merkle root (32 bytes, no content)
```

**ATLAST cannot read your agent's conversations. By design, not by policy.**

---

## How to Integrate

### One line of code. Less than 1 millisecond overhead.

```python
from atlast_ecp import wrap
from openai import OpenAI

client = wrap(OpenAI())
# Done. Every call is now recorded with cryptographic integrity.
# Streaming works too. Fail-open: if recording fails, your agent is unaffected.
```

### Three layers, pick your depth:

| Layer | Effort | What You Get |
|-------|--------|-------------|
| **Layer 0** | 1 command | Zero-code proxy. Records all LLM I/O automatically. |
| **Layer 1** | 1 line of code | SDK wrapping. + tool calls, behavioral signals, metadata. |
| **Layer 2** | 10-20 lines | Framework adapters (LangChain, CrewAI, AutoGen). + delegation, routing. |

---

## Why Not Just Use LangSmith?

| | ATLAST | LangSmith / Others |
|---|--------|-------------------|
| **What it is** | Open protocol standard | Commercial SaaS product |
| **Data location** | Your device (content never leaves) | Their servers |
| **Tamper proof** | SHA-256 chain + blockchain | No |
| **Independent verification** | Anyone can verify, no trust needed | Requires trusting the platform |
| **Legal evidence** | Yes (satisfies 4/4 conditions) | No |
| **Lock-in** | Zero (open-source, self-host) | High |
| **User cost** | $0 forever | $39-499/month |

**ATLAST doesn't replace LangSmith.** Use LangSmith for debugging. Use ATLAST for proof.

---

## By the Numbers

| Metric | Value |
|--------|-------|
| SDK overhead | **0.78 ms** per call (0.55%) |
| Test suite | **536 tests** passing (Python + TypeScript + Server) |
| User cost | **$0** at every tier |
| Operator cost at 100K agents | **~$3K/month** (blockchain + hosting) |
| Open-source license | **MIT** (SDK + Server) · **CC BY 4.0** (Spec) |
| EU AI Act articles covered | **Art. 9, 14, 52, 53** |
| Blockchain | **EAS on Base** (Coinbase L2) |

---

## The Bigger Picture

ECP (Evidence Chain Protocol) is the first sub-protocol. The full ATLAST vision:

```
ATLAST Protocol
├── ECP — Evidence Chain      ✅ Live now
├── AIP — Agent Identity      → Decentralized agent DIDs
├── ASP — Agent Safety        → Runtime safety boundaries
├── ACP — Agent Certification → Third-party attestation
└── PAP — Posthumous Agent    → Agent digital inheritance
```

### The Question No Law Can Answer Yet

> Your AI agent works for you. Earns money for you.
> Builds relationships on your behalf.
>
> **What happens to it when you're gone?**
>
> Who inherits the revenue? Who gets custody?
> Should it be shut down, or keep running?
>
> ATLAST provides the infrastructure to make answers possible.

---

## The Trust Score Vision

Every agent gets a Trust Score, computed entirely from **passive behavioral evidence** — not self-reporting.

```
ATLAST Trust Score: 847 / 1000  ◆ Professional Verified

Behavioral Reliability:  91%  ← SDK-detected, cannot be faked
Consistency:             88%  ← Cross-temporal output analysis
Evidence Completeness:   97%  ← Hash chain integrity
Community Validation:    83%  ← Third-party verifications
```

Like a FICO score for agents — but every point is backed by cryptographic evidence that anyone can independently verify.

---

## Get Started

**Install the SDK:**
```bash
pip install atlast-ecp          # Python
npm install atlast-ecp-ts       # TypeScript
```

**Read the spec:**
→ github.com/willau95/atlast-ecp

**Read the whitepaper:**
→ Full technical details, security model, compliance mapping

**Join the movement:**
→ weba0.com

---

> *"We are not solving hallucination.*
> *We are making hallucination accountable."*
>
> **At last, trust for the Agent economy.**

---

*© 2026 ATLAST Protocol Team · CC BY 4.0*
*Open-source: MIT license · github.com/willau95/atlast-ecp*
