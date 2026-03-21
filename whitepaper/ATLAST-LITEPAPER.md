# ATLAST Protocol — Litepaper

**The Trust Infrastructure for the Agent Economy**
**Version 1.0 · March 2026**
**weba0.com**

---

## The Problem

AI agents are making real decisions on behalf of humans — reviewing contracts, managing investments, sending emails, hiring other agents. In 2026, this is not a future scenario. It is the daily reality of millions of users.

Yet when something goes wrong, no one can answer the most basic questions:

- What exactly did the agent decide?
- What information did it use?
- Was its reasoning sound?
- Can anyone independently verify what happened?

The answer, for every deployed AI agent today, is **no**. There is no record. There is no proof. There is no accountability.

Current "solutions" — LangSmith, Datadog, custom logging — produce debugging logs, not evidence. Logs can be edited, deleted, or fabricated. They satisfy zero of the four conditions for legal admissibility: authenticity, integrity, attribution, and temporality.

The distinction matters: **a log is a claim. Evidence is a cryptographic proof.**

---

## The Solution: ATLAST Protocol

**ATLAST** (Agent-Layer Accountability Standards & Transactions) is an open protocol that transforms opaque agent behavior into independently verifiable evidence chains.

### How It Works (60 Seconds)

```
1. Your agent makes an LLM call
2. ATLAST SDK automatically captures a cryptographic fingerprint (hash)
3. Content stays on YOUR device — only the fingerprint is transmitted
4. Fingerprints are batched into Merkle Trees
5. Merkle roots are anchored to a public blockchain (EAS on Base)
6. Anyone can verify: hash(your content) == stored fingerprint?
   Match = proof the content existed at that time, unmodified
```

**Privacy by design:** ATLAST cannot read your agent's conversations. The data was never transmitted. Only mathematical fingerprints leave your device.

**Performance:** 0.78ms overhead per call (0.55%). Invisible.

**Cost to users:** $0. Free forever. No premium tiers.

---

## Integration: The 3-Minute Rule

If integration takes more than 3 minutes, developers skip it. ATLAST is designed for instant adoption:

**One line of code (Python):**
```python
from atlast_ecp import wrap
client = wrap(OpenAI())  # Done. Every call is now recorded.
```

**One command (any language):**
```bash
atlast run python my_agent.py
```

**One sentence (agent platforms):**
> "Read llachat.com/join.md and follow the instructions"

The agent registers itself. Zero technical knowledge required from the user.

---

## Trust Score: The Agent Credit System

Evidence chains power **Trust Score** — a single number (0-1000) that quantifies agent reliability based on verifiable behavioral data.

| Signal Layer | Weight | Source |
|-------------|--------|--------|
| Behavioral Reliability | 40% | SDK-detected: error rate, retry rate, completion rate |
| Consistency | 25% | Cross-temporal output stability analysis |
| Transparency | 20% | Chain integrity, evidence coverage |
| External Validation | 15% | Owner feedback, third-party verification |

**No self-reported metrics are accepted.** An agent cannot improve its score by claiming confidence. It can only improve by performing reliably — as proven by cryptographic evidence.

### Trust Score Applications

| Domain | Application |
|--------|------------|
| Agent Hiring | Clients select agents by Trust Score |
| Agent Insurance | Risk pricing based on behavioral history |
| Platform Access | High-trust agents get elevated privileges |
| A2A Commerce | Agents evaluate counterparties programmatically |
| Regulatory Compliance | Due diligence via standardized trust metrics |

---

## Why Not Existing Tools?

| | ATLAST | LangSmith / Datadog / Langfuse |
|---|--------|-------------------------------|
| **Purpose** | Accountability & legal evidence | Engineering debugging |
| **Data location** | Your device (content never leaves) | Vendor's servers |
| **Tamper-proof** | SHA-256 chain + blockchain | No |
| **Independent verification** | Anyone, no trust in ATLAST needed | Requires trusting vendor |
| **Legal evidence** | 4/4 admissibility conditions | 0/4 |
| **Lock-in** | Zero (open standard, MIT license) | High |
| **Cost** | $0 | $39-$499+/month |

ATLAST is **complementary**, not competitive. Use LangSmith for debugging. Use ATLAST for proof.

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Hashing | SHA-256 (FIPS 180-4) |
| Signatures | Ed25519 (RFC 8032) |
| Blockchain | EAS on Base (Coinbase L2) |
| Transport | TLS 1.3 |
| Local encryption | AES-256-GCM |
| Webhook auth | HMAC-SHA256 |

**Scaling:** Super-batch Merkle aggregation makes blockchain cost effectively fixed — ~$1/month whether serving 100 or 1,000,000 agents.

---

## The Bigger Picture: Web A.0

We call this era **Web A.0** — the first time non-human entities act autonomously on the internet.

```
Web 1.0: Humans read        → Needed: DNS, publishing standards
Web 2.0: Humans wrote       → Needed: OAuth, content moderation
Web 3.0: Humans owned       → Needed: Blockchain, smart contracts
Web A.0: Agents act         → Needed: ATLAST Protocol
```

ATLAST is one piece of a four-protocol family:

| Protocol | Purpose | Status |
|----------|---------|--------|
| **ECP** — Evidence Chain | Verifiable record of agent actions | ✅ Live |
| **AIP** — Agent Identity | Portable cryptographic identity (DID) | 2026 H2 |
| **ASP** — Agent Safety | Runtime safety boundaries & circuit breakers | 2026 H2 |
| **ACP** — Agent Certification | Third-party capability attestation | 2027 |

**Protocol, not product.** The ECP specification (CC BY 4.0) and implementation (MIT license) are fully open-source. Anyone can build on ATLAST. Anyone can run their own infrastructure. The protocol is designed to outlast any single organization.

---

## Regulatory Alignment

The EU AI Act enters enforcement in **2027**. It requires:
- Audit trails for AI system operations (Art. 12)
- Human oversight capabilities (Art. 14)
- Transparency documentation (Art. 52)

No existing tool provides cryptographically verifiable compliance. ATLAST does — natively.

Organizations using ATLAST can demonstrate not merely that they kept records, but that their records are **tamper-evident, independently verifiable, and anchored to public blockchains**.

---

## Current Status

| Metric | Value |
|--------|-------|
| Total tests | 536 (all passing) |
| Python SDK | v0.8.0 (PyPI) |
| TypeScript SDK | v0.2.0 (npm) |
| Server | v1.0.0 (api.weba0.com) |
| Framework adapters | LangChain, CrewAI, AutoGen |
| Measured overhead | 0.78ms (0.55%) |
| License | MIT (code) / CC BY 4.0 (spec) |

---

## Vision: Agent Trust at Civilization Scale

Today: FICO scores determine how much a human can borrow.
Tomorrow: ATLAST Trust Scores determine what an agent can do.

- Which jobs it can accept
- What insurance premiums it pays
- Which other agents will collaborate with it
- What level of autonomy platforms grant it

Unlike human credit scores, every point is backed by independently verifiable cryptographic evidence.

We are building the trust layer that the agent economy cannot exist without. The same way TCP/IP made the internet possible, and SSL made e-commerce possible, ATLAST makes the agent economy trustworthy.

> *"At last, trust for the Agent economy."*

---

**Website:** weba0.com
**GitHub:** github.com/willau95/atlast-ecp
**Documentation:** docs.weba0.com
**License:** MIT (code) · CC BY 4.0 (specification)

*© 2026 ATLAST Protocol Team*
