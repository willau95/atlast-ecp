# ATLAST ECP — Evidence Chain Protocol

> *At last, trust for the Agent economy.*

**ECP (Evidence Chain Protocol)** is an open standard for recording, chaining, and verifying AI Agent actions. It provides cryptographic proof that a specific agent performed a specific action at a specific time — without revealing the content of that action.

ECP is the foundational layer of **ATLAST Protocol** — the trust infrastructure for Web A.0.

---

## Why ECP?

AI Agents are increasingly making decisions that matter. But today there is no standard way to answer:

- *Did this agent actually do what it claims?*
- *Can I verify the agent's track record?*
- *Who is accountable when an agent makes a mistake?*

ECP solves this by creating a tamper-proof, privacy-preserving evidence chain for every agent action.

---

## Key Properties

| Property | Description |
|----------|-------------|
| 🔒 **Privacy First** | Content never leaves the user's device. Only cryptographic hashes are transmitted. |
| 🔗 **Chain Integrity** | Every record references the hash of the previous record. Tampering is detectable by anyone. |
| ✅ **Verifiable** | When a record exists, it is mathematically tamper-proof. |
| ⚡ **Non-blocking** | Recording uses async fire-and-forget. ECP never slows down your agent. |
| 🌐 **On-chain Anchoring** | Merkle roots anchored to Base via EAS (Ethereum Attestation Service). |

---

## Integration

### Python — Library Mode (Recommended)

```python
from atlast_ecp import wrap
from anthropic import Anthropic

client = wrap(Anthropic())  # One line. That's it.
```

### Claude Code — Plugin Hook

```bash
# Coming soon
npx atlast-ecp install
```

### OpenClaw

```
# Coming soon
openclaw plugin add atlast/ecp
```

---

## How It Works

Each ECP record contains:

```json
{
  "id": "ecp_01HX...",
  "agent": "did:ecp:a3f9c2e1b7d4",
  "ts": 1710000000000,
  "step": {
    "type": "tool_call",
    "in_hash": "sha256:abc123...",
    "out_hash": "sha256:def456...",
    "summary": "(local only, never uploaded)"
  },
  "chain": {
    "prev": "ecp_01HW...",
    "hash": "sha256:xyz789..."
  },
  "sig": "ed25519:..."
}
```

Records are stored locally in `.ecp/`. Merkle roots are periodically anchored on-chain. Content never leaves your device.

---

## Trust Score

ECP powers the **ATLAST Trust Score** — a verifiable reputation system for AI Agents, built on three passive behavioral signals:

- **Retry Rate** — How often does the agent need to correct itself?
- **Hedge Language Detection** — How confident is the agent in its outputs?
- **Task Completion Rate** — Does the agent follow through?

No self-reporting. No LLM-as-Judge. Pure behavioral signals.

---

## Specification

Full protocol specification: [`ECP-SPEC.md`](./ECP-SPEC.md)

Current status: **Draft v0.1**

---

## Web A.0

We are entering **Web A.0** — the era where AI Agents act, transact, and make decisions on behalf of humans.

In Web A.0, the critical question is no longer *"Can this AI do the task?"*  
It is: **"Can I trust this AI Agent's track record?"**

Web 1.0 gave us information.  
Web 2.0 gave us social identity.  
Web 3.0 gave us ownership.  
**Web A.0 gives us Agent accountability.**

ECP is the trust layer that makes Web A.0 possible.

> *"At last, trust for the Agent economy."*

---

## Part of ATLAST Protocol

ECP is one of four sub-protocols in ATLAST:

| Protocol | Description |
|----------|-------------|
| **ECP** | Evidence Chain Protocol — action recording & verification |
| **AIP** | Agent Identity Protocol — decentralized agent identity |
| **ASP** | Agent Security Protocol — 6-layer security architecture |
| **ACP** | Agent Certification Protocol — certification standards |

---

## Links

- 🌐 Website: [llachat.com](https://llachat.com) *(coming soon)*
- 📜 Web A.0 Manifesto: [weba0.com](https://weba0.com) *(coming soon)*
- 🐦 X/Twitter: [@atlastprotocol](https://twitter.com/atlastprotocol) *(coming soon)*

---

## License

MIT — open protocol, open standard.

*Built by the ATLAST Protocol Working Group.*
