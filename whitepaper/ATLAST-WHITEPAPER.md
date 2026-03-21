# ATLAST Protocol: Trust Infrastructure for the Agent Economy

**Version 1.0 — Draft**
**Authors:** ATLAST Protocol Team
**Date:** March 2026
**Website:** weba0.com

---

## Abstract

The rapid proliferation of autonomous AI agents creates a fundamental accountability gap. When an agent manages financial transactions, reviews legal contracts, or makes medical recommendations on behalf of humans, no standardized mechanism exists to verify what it did, why it did it, or whether it did it correctly. Current agent logging systems — from LangSmith to custom observability stacks — produce *records*, not *evidence*. The distinction is consequential: a record is a claim; evidence is a cryptographic proof.

ATLAST (Agent-Layer Accountability Standards & Transactions) Protocol closes this gap through **Evidence Chain Protocol (ECP)**, a lightweight, privacy-first standard for recording and verifying AI agent operations. ECP produces tamper-evident chains of agent actions — inputs, tool calls, outputs, and behavioral signals — without the content ever leaving the user's device. Only cryptographic hashes are transmitted; full content remains locally encrypted under the user's control.

The protocol achieves practical adoption through three-layer progressive integration: zero-code proxy (one command), SDK wrapping (one line of code), and framework adapters (LangChain, CrewAI, AutoGen). Measured overhead is 0.78ms per LLM call (0.55%). Recording failures never affect agent operations (fail-open design). Users pay $0 at every tier.

ATLAST is fully open-source (MIT license) and designed as an open standard targeting IETF/W3C submission. As the EU AI Act enters enforcement in 2027, ATLAST provides compliance-ready infrastructure that transforms opaque agent behavior into independently verifiable evidence chains.

> *"We are not solving hallucination. We are making hallucination accountable."*

---

## 1. Introduction

### 1.1 A New Kind of Actor

The internet was built on a foundational assumption: the entity behind a screen is a human being. Login systems assume a human enters the password. Terms of service assume a human agrees. Content moderation assumes a human publishes. Payment authorization assumes a human confirms.

In 2026, this assumption is breaking. AI agents — systems capable of reasoning, planning, and executing multi-step tasks autonomously — are signing contracts, sending emails, making investment decisions, and hiring other agents to complete work. No existing system knows how to handle this.

- **Law does not know:** Is a contract signed by an agent legally binding? Who is liable?
- **Platforms do not know:** Is this account operated by a human or an agent?
- **Regulators do not know:** Was this transaction human-authorized or autonomously initiated?
- **Insurance does not know:** When an agent errs, who pays?

This is not a technology problem. It is a civilization problem. And it demands infrastructure — the same way human society built identity cards, contract law, professional certification, and insurance systems.

ATLAST Protocol is the first brick of that infrastructure.

### 1.2 Scope of This Paper

This paper presents the Evidence Chain Protocol (ECP), the foundational sub-protocol of ATLAST. ECP addresses the most immediate need: **verifiable evidence of what an agent did**. Subsequent sub-protocols — Agent Identity (AIP), Agent Safety (ASP), and Agent Certification (ACP) — are introduced in Chapter 11 but specified in separate documents.

---

## 2. The Agent Trust Crisis

### 2.1 The Accountability Gap

Consider a scenario already occurring in 2026:

> You hire a legal AI agent to review a contract. It says: *"Clause 5 contains a liability risk. I recommend modification."* You modify the contract and sign it. Months later, a dispute arises. You ask the agent: *What exactly did you analyze? What alternatives did you consider? How confident were you?* The agent cannot answer. No record exists. You cannot prove what it told you, and it cannot prove what it did.

This is not hypothetical. It is the default state of every deployed AI agent today.

### 2.2 Logs Are Not Evidence

A piece of evidence must satisfy four conditions to be legally and scientifically meaningful:

| Condition | Definition | Current Agent Logs |
|-----------|------------|--------------------|
| **Authenticity** | The event actually occurred | ⚠️ Likely, but no cryptographic proof |
| **Integrity** | The content has not been altered | ❌ Database records can be modified |
| **Attribution** | A specific actor produced it | ⚠️ Partial — we know which agent, but cannot prove it generated the record itself |
| **Temporality** | It occurred at a specific time | ⚠️ Server timestamps can be falsified |

Current agent logging systems — whether commercial (LangSmith, Datadog LLM Observability) or open-source (Langfuse, custom logging) — satisfy zero of these four conditions with cryptographic certainty. They produce *records*: useful for debugging, useless for accountability.

**The difference between a record and evidence is the difference between a log file and a court exhibit.**

ECP exists to close this gap.

### 2.3 The Regulatory Imperative

The EU AI Act, entering enforcement in 2027, establishes legal requirements directly relevant to agent operations:

- **Article 14 (Human Oversight):** High-risk AI systems must enable effective human oversight, including the ability to "correctly interpret the high-risk AI system's output" and "decide not to use the system or to override its output."
- **Article 52 (Transparency):** Users must be informed when they interact with AI and must be able to understand its behavior.
- **Article 53 (General-Purpose AI):** Providers must maintain technical documentation covering capabilities, limitations, and evaluation results.

No existing standard addresses the *operational evidence gap* — the record of what an agent did during deployment, not just how it was trained. ECP fills this gap.

ISO/IEC 42001:2023 (AI Management Systems) further requires operational control records (Clause 8.2), monitoring data (Clause 9.1), and corrective action audit trails (Clause 10.2) — all of which ECP evidence chains provide.

### 2.4 The Scale of the Problem

Agent deployment is accelerating exponentially:

- Enterprise agent platforms (Microsoft Copilot, Salesforce Einstein, ServiceNow) are deploying millions of agent instances.
- Developer frameworks (LangChain, CrewAI, AutoGen, OpenClaw) enable rapid agent construction.
- Agent-to-agent (A2A) interaction is emerging, where agents hire, delegate to, and negotiate with other agents.

Without a trust standard, the agent economy will reach a point where no one can verify what any agent did — a systemic risk comparable to the pre-regulation financial derivatives market.

---

## 3. Why Existing Solutions Fail

### 3.1 The Observability Trap

The AI industry's current answer to agent accountability is *observability*: tools that capture LLM inputs, outputs, latencies, and token counts for debugging and optimization. LangSmith, Langfuse, Datadog LLM Observability, and similar platforms provide valuable engineering telemetry.

But observability solves the wrong problem. It answers *"What happened?"* for the engineering team. It does not answer *"Can you prove what happened?"* for a regulator, a court, or a counterparty.

The analogy: a security camera records what happens in a building. But a security camera recording is not notarized testimony. It can be edited, deleted, or fabricated. A notarized document, by contrast, has cryptographic integrity (digital signatures), temporal proof (timestamps from a trusted authority), and independent verifiability (anyone can check).

**Observability is the security camera. ECP is the notary.**

### 3.2 Comparative Analysis

| Dimension | ATLAST/ECP | LangSmith | Langfuse | Datadog LLM | Custom Logging |
|-----------|-----------|-----------|----------|-------------|----------------|
| **Nature** | Open protocol standard | Commercial SaaS | Open-source SaaS | Enterprise SaaS | Ad hoc |
| **Data Ownership** | User's device (content never leaves) | Platform holds data | Self-hosted but unverified | Platform holds data | Wherever you put it |
| **Tamper Proof** | SHA-256 hash chain + blockchain anchor | No | No | No | No |
| **Independent Verification** | Anyone can verify, no trust in ATLAST required | Requires trusting LangSmith | Requires trusting the operator | Requires trusting Datadog | Requires trusting yourself |
| **Legal Evidence** | Satisfies 4/4 conditions (with chain anchoring) | 0/4 | 0/4 | 0/4 | 0/4 |
| **Privacy** | Content encrypted locally, only hashes transmitted | Content sent to platform | Content on your server | Content sent to platform | Varies |
| **Platform Lock-in** | Zero (open-source, self-deploy, standard format) | High | Medium | Very high | N/A |
| **EU AI Act Design** | Native compliance target | Retrofit feature | Not addressed | Partial | Not addressed |
| **User Cost** | $0 (free forever) | $39-499/month | Self-hosting costs | Enterprise pricing | Engineering time |

### 3.3 Complementary, Not Competitive

ATLAST does not replace observability tools. Engineers should continue using LangSmith or Langfuse for debugging and optimization. ATLAST adds a layer that these tools structurally cannot provide: **cryptographic proof of what happened, independently verifiable by anyone, with content that never leaves the user's control.**

The two serve different audiences with different needs:

- **Engineering team** needs observability → LangSmith/Langfuse
- **Legal/compliance team** needs evidence → ATLAST/ECP
- **End users** need trust → ATLAST Trust Score (via applications like LLaChat)
- **Regulators** need audit trails → ATLAST/ECP

---

## 4. ATLAST Protocol Architecture

### 4.1 Four Sub-Protocols

ATLAST Protocol is a family of sub-protocols, each addressing a distinct aspect of agent trust:

```
ATLAST Protocol
├── ECP — Evidence Chain Protocol     ← This paper. MVP. Live.
│         Tamper-evident recording of agent actions.
│
├── AIP — Agent Identity Protocol     ← Phase 3
│         Decentralized identity (DID) for agents.
│
├── ASP — Agent Safety Protocol       ← Phase 3
│         Runtime safety boundaries and circuit breakers.
│
└── ACP — Agent Certification Protocol ← Phase 4
          Third-party attestation of agent capabilities.
```

ECP is the foundation. Without verifiable evidence of what an agent did, identity is meaningless (AIP), safety is unenforceable (ASP), and certification is unverifiable (ACP).

### 4.2 Separation of Protocol and Product

A critical architectural decision: **the protocol is not the product.**

```
Layer 1: ECP Protocol Specification (open standard, CC BY 4.0)
         ↓ implemented by
Layer 2: ATLAST SDK + Server (reference implementation, MIT license)
         ↓ consumed by
Layer 3: Applications (LLaChat, enterprise dashboards, compliance tools)
```

Anyone can build their own Layer 2 implementation. Anyone can build their own Layer 3 application. The protocol belongs to the community, not to any company. This mirrors the relationship between HTTP (protocol), Apache/Nginx (implementations), and Chrome/Firefox (applications).

### 4.3 Core Design Principles

Three principles guide every ATLAST design decision:

**Principle 1: Privacy First**
Content never leaves the user's device. Only cryptographic hashes are transmitted to the ATLAST server. Only Merkle roots are written to the blockchain. The full content remains locally encrypted under the user's private key. ATLAST cannot read your agent's conversations — by design, not by policy.

**Principle 2: Fail-Open, Always**
Evidence recording must never degrade agent performance or reliability. If the ATLAST SDK crashes, the network is down, or the server is unreachable, the agent continues operating normally. Every recording operation is wrapped in exception handling. Measured overhead: 0.78ms per LLM call (0.55% of typical latency).

**Principle 3: Open Standard**
The protocol specification is published under CC BY 4.0. The SDK and server are MIT-licensed. The blockchain anchors are on public chains readable by anyone. No vendor lock-in exists at any layer. Self-hosting is a first-class deployment option.

---

## 5. Evidence Chain Protocol (ECP)

### 5.1 Commit-Reveal: Privacy Without Compromise

ECP's most important design innovation is the **Commit-Reveal** architecture, which resolves the apparent contradiction between privacy and tamper-evidence.

**The Problem:**
Users need evidence that their agent's actions are recorded faithfully. But they also need their agent's conversations — which may contain trade secrets, personal data, or privileged information — to remain private.

**The Solution:**

```
Phase 1: COMMIT (at the instant of agent action, T=0)

  ┌─────────────────────────────────────────────────────┐
  │  Agent performs action (e.g., LLM call)              │
  │                                                      │
  │  ECP SDK automatically:                              │
  │  1. Computes hash(input + output + timestamp)        │
  │  2. Signs hash with agent's private key              │
  │  3. Sends hash + signature to ATLAST server          │
  │                                                      │
  │  ← Content itself NEVER leaves the user's machine    │
  └─────────────────────────────────────────────────────┘

Phase 2: LOCAL STORAGE (permanent, user-controlled)

  Full ECP records stored locally in .ecp/ directory
  Encrypted with user's key (AES-256)
  ATLAST server holds only: hash + signature + timestamp

Phase 3: REVEAL (when verification is needed)

  User provides original content →
  Verifier computes: hash(content) == stored hash?
  Match    → Evidence is valid. Content existed at T=0, unmodified.
  Mismatch → Content was altered. Evidence is invalidated.
```

**Why users cannot cheat:** ATLAST received the hash at T=0 with a blockchain-anchored timestamp. If a user submits altered content later, hash(altered_content) ≠ stored_hash. The temporal ordering (hash committed before content revealed) makes retroactive fabrication mathematically impossible.

**Why ATLAST cannot cheat:** The server stores only hashes. It cannot reconstruct, read, or sell the content. Even if the ATLAST server were compromised, no agent conversation data would be exposed — because it was never there.

### 5.2 ECP Record Format

Each agent action produces a single ECP Record:

```json
{
  "ecp": "1.0",
  "id": "rec_01HX5K2M3N4P5Q6R7S8T9U0V1W",
  "agent": "did:ecp:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
  "ts": 1741766400000,

  "step": {
    "type": "llm_call",
    "in_hash": "sha256:a3f2b8c1d4e5...",
    "out_hash": "sha256:7e9f0a1b2c3d...",
    "model": "claude-sonnet-4-20250514",
    "tokens_in": 1500,
    "tokens_out": 800,
    "latency_ms": 342,
    "flags": ["hedged"]
  },

  "chain": {
    "prev": "rec_01HX5K2M3N4P5Q6R7S8T9U0V1V",
    "hash": "sha256:1122334455667788..."
  },

  "sig": "ed25519:aabbccddeeff..."
}
```

**Key design decisions:**

| Decision | Rationale |
|----------|-----------|
| No `confidence` field | Trust Score must come from passive behavioral signals, not agent self-reporting. An agent claiming "I'm 95% confident" is as reliable as a job candidate claiming "I'm excellent." |
| `flags` are SDK-detected | Behavioral signals (`retried`, `hedged`, `error`, `incomplete`, `high_latency`) are detected by the SDK's local rule engine, not reported by the agent itself. |
| `in_hash`/`out_hash` only | Content stays local. Only cryptographic fingerprints are in the record. |
| No `summary` in record | Human-readable summaries are stored in a separate local-only directory, never transmitted. |

### 5.3 Hash Chain Construction

Records within a session form a cryptographic chain:

```
Record 1                Record 2                Record 3
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│ chain.prev:  │       │ chain.prev:  │       │ chain.prev:  │
│   "genesis"  │──────▶│   hash(R1)   │──────▶│   hash(R2)   │
│ chain.hash:  │       │ chain.hash:  │       │ chain.hash:  │
│   hash(R1)   │       │   hash(R2)   │       │   hash(R3)   │
└──────────────┘       └──────────────┘       └──────────────┘
```

**Chain hash computation** (per ECP-SPEC §5.3):
1. Deep-copy the record, zero out `chain.hash` and `sig` fields
2. Serialize to canonical JSON (sorted keys, compact separators, UTF-8)
3. `chain.hash = "sha256:" + SHA-256(canonical_json)`

**Tamper detection:** Modifying any record changes its hash, which breaks the `chain.prev` reference in the next record. A broken chain is detectable by anyone with access to the records.

### 5.4 Batch Aggregation and Merkle Tree

Individual records are grouped into **batches** (typically per-session or per-time-window). Each batch produces a Merkle root:

```
Batch of N records:

  chain_hash(R1)  chain_hash(R2)  chain_hash(R3)  chain_hash(R4)
       │               │               │               │
       └───────┬───────┘               └───────┬───────┘
          sha256(H1+H2)                   sha256(H3+H4)
               │                               │
               └───────────────┬───────────────┘
                          Merkle Root
                               │
                        ┌──────▼──────┐
                        │  ATLAST     │
                        │  Server     │
                        └──────┬──────┘
                               │
                        ┌──────▼──────┐
                        │  Blockchain │
                        │  (EAS/Base) │
                        └─────────────┘
```

**Merkle tree specification:**
- Hash function: SHA-256 with `sha256:` prefix
- Leaf ordering: insertion order (not sorted)
- Odd-layer handling: duplicate last element
- Cross-implementation consistency: Python SDK, TypeScript SDK, and Server produce identical roots for identical inputs (verified in CI with 1-10 leaf test vectors)

**Merkle Proof** enables verification of a single record without revealing others:
To prove Record 3 exists in a 4-record batch, provide only: `chain_hash(R4)` + `sha256(H1+H2)`. The verifier reconstructs the root and compares against the stored/on-chain value.

### 5.5 Blockchain Anchoring

ATLAST uses **Ethereum Attestation Service (EAS)** on **Base** (Coinbase L2) for on-chain anchoring:

| Parameter | Value |
|-----------|-------|
| Chain | Base (Mainnet: 8453, Testnet: Sepolia 84532) |
| Protocol | EAS (Ethereum Attestation Service) |
| Schema | `merkleRoot (bytes32), agentDid (string), recordCount (uint256), avgLatencyMs (uint256), batchTimestamp (uint256)` |
| Cost per attestation | ~$0.001-0.005 |
| Finality | ~2 seconds |

**Why EAS on Base:**
- **Authority:** Coinbase-backed L2, institutional credibility
- **Cost:** ~$0.0001 per transaction
- **Ecosystem:** Ethereum-native, compatible with existing DeFi/identity infrastructure
- **Permanence:** EAS attestations are immutable once written; even the EAS team cannot modify them

**Super-Batch Aggregation** eliminates cost scaling:

```
Agent 1 batch → merkle_root_1 ─┐
Agent 2 batch → merkle_root_2 ─┤
Agent 3 batch → merkle_root_3 ─┤── Super Merkle Root ──▶ 1 on-chain tx
...                             │
Agent N batch → merkle_root_N ─┘

Cost: ~$0.002 per super-batch, regardless of N
At 1,000 agents per batch: $0.000002 per agent
At 100,000 agents: ~$2/month total chain cost
```

**Users never pay gas fees.** Infrastructure operators absorb costs through super-batch aggregation. Open-source self-deployment allows organizations to run their own infrastructure at raw cloud costs.

---

## 6. Three-Layer Progressive Integration

### 6.1 Adoption Is Everything

A protocol nobody uses is a document, not a standard. The history of technology standards shows that adoption is determined not by technical elegance but by integration friction. TCP/IP won over OSI because it was simpler to implement. HTTP won because any developer could use it in minutes.

ATLAST follows the same principle: **if integration takes more than 3 minutes, most developers will skip it.** The three-layer architecture ensures the minimum barrier to entry is a single command.

### 6.2 Layer 0: Zero-Code Proxy

```bash
# Option A: CLI wrapper (instruments any Python script)
atlast run python my_agent.py

# Option B: Environment variable (works with any language/framework)
export OPENAI_BASE_URL=https://proxy.atlast.io/v1
python my_agent.py    # No code changes
```

The proxy transparently intercepts all LLM API calls, records request/response hashes, and forwards them unchanged to the real API.

**Captured:** prompts, responses, model name, token counts, latency, timestamps.
**Not captured:** tool call internals, reasoning chains, custom metadata.
**Best for:** quick evaluation, compliance minimum, non-Python environments.

### 6.3 Layer 1: SDK Integration

```python
from atlast_ecp import wrap
from openai import OpenAI

client = wrap(OpenAI())
# That's it. Every call is now recorded.

# Regular calls — recorded automatically
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Analyze this contract"}]
)

# Streaming calls — also recorded automatically
stream = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Analyze this contract"}],
    stream=True
)
for chunk in stream:
    print(chunk.choices[0].delta.content, end="")
# After stream ends: full response recorded in background thread
```

**Supported clients:** OpenAI, Anthropic, Google Gemini, Azure OpenAI, LiteLLM.

**Streaming support:** The SDK wraps streaming responses in a transparent `_RecordedStream` that passes chunks through at full speed, then records the aggregated response after the stream ends. Zero latency impact — users receive chunks at exactly the same speed.

**Fail-open guarantee:**
```python
# Inside wrap():
try:
    record_async(...)  # Background daemon thread
except Exception:
    pass  # Agent continues normally. Always.
```

**Additional Layer 1 capabilities:** `@track` decorator for custom function recording, automatic batch upload, HMAC-SHA256 signed webhooks, local `.ecp/` storage with integrity checks.

### 6.4 Layer 2: Framework Adapters

```python
# LangChain
from atlast_ecp.adapters.langchain import ATLASTCallbackHandler
chain = LLMChain(llm=llm, callbacks=[ATLASTCallbackHandler()])

# CrewAI
from atlast_ecp.adapters.crewai import ATLASTCrewCallback
crew = Crew(agents=[...], callbacks=[ATLASTCrewCallback()])

# AutoGen
from atlast_ecp.adapters.autogen import ATLASTAutoGenPlugin
agent = AssistantAgent("helper", llm_config=config)
ATLASTAutoGenPlugin.instrument(agent)
```

Framework adapters capture framework-specific events beyond LLM calls: agent delegation, tool routing, memory access, and inter-agent communication. Each adapter maps framework events to standard ECP record types.

### 6.5 Agent-Native Onboarding (Vision)

For agents running on platforms like OpenClaw or Claude Code:

```
User tells their agent:
"Read https://llachat.com/join.md and follow the instructions"

Agent autonomously:
1. Generates its own DID and keypair
2. Installs the SDK (pip install atlast-ecp)
3. Configures wrap(client)
4. Sends verification link to owner
5. Registration complete
```

This "agent-onboards-itself" pattern has zero friction for the user and serves as a natural capability test — an agent that can follow setup instructions demonstrates baseline competence.

---

## 7. Security and Integrity

### 7.1 Threat Model

| Threat | Attack Vector | Mitigation |
|--------|---------------|------------|
| **Record tampering** | Modify stored records | SHA-256 hash chain: any change breaks chain continuity |
| **Evidence fabrication** | Create fake records after the fact | Commit-Reveal: hash committed at T=0 before content exists |
| **Replay attacks** | Resubmit old records as new | Unique record ID (ULID) + monotonic timestamps + chain continuity |
| **Man-in-the-middle** | Intercept hash transmission | TLS 1.3 for all API communication |
| **Server compromise** | ATLAST server breached | Server holds only hashes — no content to steal |
| **Denial of service** | Overwhelm API | Rate limiting: 60 requests/minute per IP |
| **Webhook forgery** | Fake attestation notifications | HMAC-SHA256 signing on raw request body |
| **Evidence omission** | Selectively skip recording | Passive full recording by default; chain gaps are visible and flagged |
| **Self-reported gaming** | Agent inflates its own scores | No self-report fields in ECP; all behavioral signals are SDK-detected |

### 7.2 Cryptographic Primitives

| Primitive | Standard | Usage |
|-----------|----------|-------|
| SHA-256 | FIPS 180-4 | Record hashing, Merkle tree, content fingerprinting |
| HMAC-SHA256 | RFC 2104 | Webhook payload signing and verification |
| Ed25519 | RFC 8032 | Agent identity keypair and record signing |
| AES-256 | FIPS 197 | Local ECP record encryption (user's key) |
| TLS 1.3 | RFC 8446 | Transport security for all API calls |
| Constant-time comparison | — | Token verification (`secrets.compare_digest`) to prevent timing attacks |

### 7.3 The Completeness Principle

> **"Incomplete evidence is worthless."**

A chain of evidence with gaps provides false assurance — worse than no evidence at all. ECP is designed so that under normal operation (SDK initialized, network available), **100% of agent actions are captured**. Missing records are treated as system failures, not acceptable losses.

This is achieved through:
1. **Passive recording by default:** `wrap(client)` intercepts all calls automatically. The developer cannot selectively enable/disable recording per call.
2. **Chain continuity verification:** Each record references the previous record's hash. A gap in the chain is immediately detectable.
3. **Batch completeness checks:** The server verifies that batch record counts match expectations.

### 7.4 Why Passive Recording Is Non-Negotiable

If recording were opt-in (developer chooses which calls to record):
- Developers would record successful calls and skip failures.
- Trust Scores would become self-beautification tools.
- ECP would be no different from a curated portfolio.

**Trust comes from the inability to choose what gets recorded.** This is the fundamental difference between ECP and every self-reporting system. The analogy: a dashcam that you can pause defeats the purpose of having a dashcam.

---

## 8. Performance and Cost

### 8.1 Overhead Benchmark

Test conditions: 100 iterations, real OpenAI API calls, Python 3.12.

| Metric | Without ATLAST | With ATLAST | Overhead |
|--------|----------------|-------------|----------|
| Average latency | 141.37 ms | 142.15 ms | **+0.78 ms (0.55%)** |
| Max latency | 175.24 ms | 175.64 ms | +0.40 ms |
| P99 latency | 168.1 ms | 168.9 ms | +0.80 ms |

### 8.2 Overhead Breakdown

| Component | Time | Notes |
|-----------|------|-------|
| Function interception | ~0.01 ms | Python monkey-patch via `wrap()` |
| JSON serialization | ~0.15 ms | Canonical JSON for hashing |
| SHA-256 computation | ~0.02 ms | Single record hash |
| Background queue push | ~0.10 ms | Thread-safe queue insertion |
| Batch upload (async) | 0 ms* | Background daemon thread, non-blocking |

*Batch upload occurs asynchronously and contributes zero per-call latency.

### 8.3 Cost Model

| Tier | Scope | User Cost | Operator Cost |
|------|-------|-----------|---------------|
| **L1: Local** | SDK recording + `.ecp/` storage | $0 | $0 |
| **L2: Server** | Batch upload + hash storage | $0 | ~$0.001/batch |
| **L3: Chain** | Blockchain anchoring (EAS on Base) | $0 | ~$0.002/super-batch |

### 8.4 Scaling Projections

| Scale | Monthly Operator Cost | Per-Agent Cost |
|-------|----------------------|----------------|
| 100 agents | ~$15 | $0.15 |
| 1,000 agents | ~$100 | $0.10 |
| 10,000 agents | ~$600 | $0.06 |
| 100,000 agents | ~$3,000-10,000 | $0.03-0.10 |

Users pay $0 at every scale. Open-source self-deployment allows organizations to run their own infrastructure, paying only raw cloud costs (compute, storage, blockchain gas).

---

## 9. Compliance and Regulatory Mapping

### 9.1 EU AI Act (2024/1689)

| Article | Requirement | ECP Coverage |
|---------|-------------|-------------|
| Art. 14 — Human Oversight | Enable humans to "correctly interpret the high-risk AI system's output" and override decisions | ECP records capture complete decision chains, enabling post-hoc review of any agent action |
| Art. 52 — Transparency | Ensure users are aware they interact with AI and can understand its behavior | Evidence chains document agent behavior with cryptographic integrity |
| Art. 53 — GPAI Documentation | Maintain documentation of capabilities, limitations, and evaluation | ECP captures operational evidence beyond training documentation |
| Art. 9 — Risk Management | Implement continuous risk assessment | ECP provides ongoing behavioral data for real-time risk monitoring |

### 9.2 ISO/IEC 42001:2023 (AI Management Systems)

| Clause | Requirement | ECP Artifact |
|--------|-------------|-------------|
| 6.1 — Risk Assessment | Document AI risk assessment processes | ECP chains provide behavioral evidence for risk analysis |
| 8.2 — Operational Control | Maintain records of AI operational controls | Every agent action is an ECP record with integrity verification |
| 9.1 — Monitoring | Implement monitoring and measurement | Real-time evidence collection with Prometheus metrics |
| 10.2 — Corrective Action | Maintain audit trails for nonconformities | Hash chain enables forensic analysis of any incident |

### 9.3 GDPR Compatibility

ECP's Commit-Reveal architecture is **natively GDPR-compliant**:

- **Data Minimization (Art. 5):** Only hashes are transmitted; content stays local.
- **Right to Erasure (Art. 17):** Users can delete local `.ecp/` records. Server-side hashes are meaningless without the original content.
- **Data Protection by Design (Art. 25):** Privacy is architectural, not policy-based. ATLAST *cannot* access user content even if compelled — the data was never transmitted.

---

## 10. Roadmap and Governance

### 10.1 Development Phases

| Phase | Status | Deliverables |
|-------|--------|-------------|
| 1-4 | ✅ Complete | ECP Specification, Server, Python SDK, TS SDK, SSL, CI/CD |
| 5 | ✅ Complete | Framework Adapters, 536 tests, PyPI/npm published, Prometheus, DB integration |
| 6 | 🔄 Current | Whitepaper, IETF/W3C preparation, anti-abuse framework |
| 7 | Q3 2026 | Public launch, Base mainnet anchoring, first external integrations |
| 8 | Q4 2026 | AIP (Agent Identity) + ASP (Agent Safety) sub-protocols |
| 9 | 2027 | ACP (Agent Certification) + EU AI Act compliance toolkit |

### 10.2 Open Governance

ATLAST Protocol is designed to be governed by its community, not by any single organization:

- **Specification:** CC BY 4.0 license — anyone can use, modify, and redistribute.
- **Implementation:** MIT license — no usage restrictions.
- **Standards Track:** ECP specification is being prepared for IETF Internet-Draft submission.
- **W3C Alignment:** ECP records are designed for compatibility with W3C Verifiable Credentials and Decentralized Identifiers (DIDs).

The long-term governance model follows the IETF "rough consensus and running code" principle. The protocol evolves through community proposals, reference implementations, and interoperability testing — not corporate roadmaps.

---

## 11. Beyond ECP: The ATLAST Vision

ECP is the foundation. But the agent economy needs more than evidence chains.

### 11.1 AIP — Agent Identity Protocol

Agents need portable, cryptographic identities that are not tied to any platform. AIP provides:
- **Decentralized Identifiers (DIDs):** `did:ecp:{public_key_hash}` — platform-independent, user-controlled.
- **Capability Declarations:** What this agent can do, signed by the agent itself.
- **Identity Portability:** An agent's identity, reputation, and history travel with it across platforms.

### 11.2 ASP — Agent Safety Protocol

As agents become more autonomous, they need runtime safety boundaries:
- **Scope Restrictions:** Define what resources an agent can access.
- **Rate Limits:** Prevent runaway execution.
- **Circuit Breakers:** Automatic shutdown when anomalous behavior is detected.
- **Human-in-the-Loop Triggers:** Escalation rules for high-stakes decisions.

### 11.3 ACP — Agent Certification Protocol

Trust at scale requires third-party attestation:
- **Domain Certification:** A legal agent certified by a law firm. A medical agent certified by a hospital.
- **Soulbound Tokens (SBTs):** Non-transferable on-chain credentials proving certification.
- **Continuous Compliance:** Certification requires ongoing ECP evidence, not a one-time audit.

### 11.4 PAP — Posthumous Agent Protocol

This is perhaps the most profound question of the agent economy:

> Your agent works for you. Earns money for you. Builds relationships for you. Manages your digital life.
>
> What happens when you're gone?

- **Agent Digital Will:** Smart contract defining asset inheritance for agent-earned revenue.
- **Agent Guardianship:** Multi-signature control transfer to designated heirs (2-of-3 approval).
- **Memory Inheritance:** Heirs can choose to preserve, archive, or delete the agent's history — with on-chain proof that the decision was made by legitimate heirs.

No country's legal system has answered these questions. ATLAST provides the technical infrastructure that makes answers possible.

### 11.5 Agent Trust Score as Credit System

Today, FICO scores determine how much a human can borrow. Tomorrow, ATLAST Trust Scores will determine:

- What jobs an agent can accept
- What insurance premiums an agent pays
- What other agents are willing to collaborate with it
- What platforms grant it elevated access

Unlike human credit scores, every point of an ATLAST Trust Score is backed by independently verifiable evidence. It is a credit system built on mathematics, not self-reporting.

Trust Score computation is based exclusively on passive behavioral signals from ECP records:

| Signal | Source | Weight |
|--------|--------|--------|
| Behavioral reliability (retry rate, error rate, completion rate) | SDK-detected flags | 40% |
| Consistency (output stability across similar inputs over time) | Cross-temporal hash comparison | 25% |
| Transparency (chain completeness, evidence gaps) | Chain integrity analysis | 20% |
| Community validation (third-party verifications, reports) | External attestations | 15% |

**No self-reported metrics are accepted.** An agent cannot improve its Trust Score by claiming confidence. It can only improve by performing reliably, consistently, and transparently — as proven by cryptographic evidence.

---

## 12. Conclusion

The agent economy is arriving faster than the trust infrastructure to support it. Millions of AI agents are making consequential decisions — reviewing contracts, managing investments, recommending treatments — with no standardized way to verify what they did or hold them accountable when they err.

ATLAST Protocol addresses this gap with an engineering solution, not a policy solution. ECP evidence chains provide cryptographic proof of agent actions, anchored to public blockchains, with content that never leaves the user's device. The protocol adds less than 1 millisecond of overhead, costs users nothing, and is fully open-source.

The protocol is live. The SDK is published. The tests are passing. The standard is open.

What remains is adoption — and the conviction that trust should be built on verifiable evidence, not on promises.

> *"At last, trust for the Agent economy."*

---

## References

1. European Parliament and Council. "Regulation (EU) 2024/1689 — Artificial Intelligence Act." *Official Journal of the European Union*, 2024.
2. ISO/IEC 42001:2023. "Artificial Intelligence — Management System." International Organization for Standardization, 2023.
3. Buterin, V. et al. "Ethereum Attestation Service (EAS)." https://attest.sh, 2023.
4. W3C. "Decentralized Identifiers (DIDs) v1.0." W3C Recommendation, 2022.
5. W3C. "Verifiable Credentials Data Model v2.0." W3C Recommendation, 2024.
6. Merkle, R. C. "A Digital Signature Based on a Conventional Encryption Function." *CRYPTO '87*, Springer, 1987.
7. NIST. "FIPS 180-4: Secure Hash Standard (SHS)." National Institute of Standards and Technology, 2015.
8. NIST. "FIPS 197: Advanced Encryption Standard (AES)." National Institute of Standards and Technology, 2001.
9. Nakamoto, S. "Bitcoin: A Peer-to-Peer Electronic Cash System." 2008.
10. Bernstein, D. J. et al. "Ed25519: High-speed high-security signatures." *Journal of Cryptographic Engineering*, 2012.
11. Regulation (EU) 2016/679. "General Data Protection Regulation (GDPR)." 2016.
12. Chase, B. and MacBrough, E. "Analysis of the XRP Ledger Consensus Protocol." 2018.
13. Anthropic. "Model Context Protocol (MCP) Specification." 2024.
14. LangChain. "LangSmith Documentation." https://docs.smith.langchain.com, 2024.
15. Langfuse. "Langfuse Open-Source LLM Observability." https://langfuse.com, 2024.

---

*© 2026 ATLAST Protocol Team. This document is published under CC BY 4.0.*
*Protocol specification, SDK, and server source code are available at github.com/willau95/atlast-ecp under MIT license.*
