# ATLAST Protocol — Platform Integration Guide

> For platforms, marketplaces, and products that want to integrate ATLAST ECP.
> 
> Examples: AI agent marketplaces, monitoring dashboards, compliance tools, enterprise agent platforms.

---

## What You Get

By integrating ATLAST, your platform gets:

| Feature | What It Does |
|---------|-------------|
| **Trust Score (0-1000)** | Quantified reliability for every agent on your platform |
| **Evidence Chain** | Tamper-proof record of every agent action |
| **Behavioral Signals** | Error rates, completion rates, response patterns |
| **On-Chain Verification** | Blockchain-anchored proof (EAS on Base) |
| **Agent Identity (DID)** | Unique cryptographic identity per agent |

You do NOT need to run any ATLAST infrastructure. The protocol is fully decentralized — agents record locally, push hashes to chain, and send data to your platform via webhook.

---

## Architecture

```
Your User's Agent
      │
      ├── ATLAST ECP (installed on agent's machine)
      │       ├── Records every LLM call locally
      │       ├── Chains records with SHA-256
      │       ├── Computes Trust Score
      │       └── Pushes batches to chain (EAS)
      │
      └── Webhook ──→ Your Platform Backend
                       ├── Receives ECP data
                       ├── Stores Trust Score
                       ├── Displays on your UI
                       └── Uses for your features
```

---

## Integration Steps

### Step 1: Set Up Your Webhook Endpoint (Your Backend)

Create a POST endpoint that receives ECP batch data:

```python
# FastAPI example
@app.post("/v1/internal/ecp-webhook")
async def receive_ecp(request: Request):
    body = await request.body()
    
    # Verify HMAC signature
    signature = request.headers.get("X-ECP-Signature", "")
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(403, "Invalid signature")
    
    data = await request.json()
    
    # Data you receive:
    # {
    #   "agent_did": "did:ecp:abc123...",
    #   "merkle_root": "sha256:...",
    #   "record_count": 50,
    #   "trust_score": 880,
    #   "reliability": 1.0,
    #   "chain_integrity": 0.97,
    #   "avg_latency_ms": 15000,
    #   "attestation_uid": "0x...",
    #   "record_hashes": ["sha256:...", ...],
    #   "flag_counts": {"streaming": 40, "has_tool_calls": 25},
    #   "signature": "ed25519:..."
    # }
    
    # Store in your database
    await update_agent_trust_score(data["agent_did"], data["trust_score"])
    
    return {"status": "ok"}
```

### Step 2: Write Your Quick Start (For Your Users)

Add this to your platform's documentation or onboarding flow:

---

#### For Your Users — One-Time Setup

**Terminal (not through AI agent):**

```bash
pip3 install atlast-ecp
atlast init
```

That's it. Your agent's work is now being recorded with tamper-proof evidence.

**Verify it's working:**
```bash
atlast doctor
```

**View your evidence chain:**
```bash
atlast dashboard
```

---

You can customize this message for your platform. The key points:
1. `pip3 install atlast-ecp` — one package, no dependencies on your platform
2. `atlast init` — generates DID, sets up storage, auto-detects agent type
3. Works with: OpenClaw, Claude Code, LangChain, CrewAI, AutoGen, any Python agent, any OpenAI/Anthropic/Gemini/Ollama API

### Step 3: Display Trust Score on Your Platform (Your Frontend)

After receiving webhook data, show Trust Score in your UI:

```
Agent: Elena
Trust Score: 880/1000
├── Proven Reliability: 92% (based on 56 verified interactions)
├── Evidence Integrity: 97% (chain verified)
└── Activity Confidence: 58% (building history)

[View Evidence Chain] [Verify On-Chain]
```

### Step 4: Link to On-Chain Verification (Optional)

Each batch is anchored on Base blockchain via EAS. Link to verification:

```
https://base-sepolia.easscan.org/attestation/view/{attestation_uid}
```

---

## API Reference (What Your Webhook Receives)

### Batch Webhook Payload

```json
{
  "agent_did": "did:ecp:d6386cfb1b6e25e849ea862610cad34f",
  "agent_name": "elena",
  "ecp_version": "1.0",
  "batch_ts": 1775495299082,
  "merkle_root": "sha256:7a07b66f2f455f44...",
  "record_count": 50,
  "record_hashes": [
    "sha256:abc123...",
    "sha256:def456..."
  ],
  "trust_score": 880,
  "reliability": 1.0,
  "error_rate": 0.0,
  "chain_integrity": 0.97,
  "avg_latency_ms": 15000,
  "flag_counts": {
    "streaming": 40,
    "has_tool_calls": 25,
    "high_latency": 5
  },
  "attestation_uid": "batch_2353000730996101",
  "signature": "ed25519:...",
  "public_key": "a1b2c3d4..."
}
```

### Verification

To verify a batch independently:

```python
# 1. Verify HMAC (webhook authenticity)
import hmac, hashlib
expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
assert hmac.compare_digest(request_signature, expected)

# 2. Verify Ed25519 signature (agent identity)
from nacl.signing import VerifyKey
vk = VerifyKey(bytes.fromhex(public_key))
vk.verify(merkle_root.encode(), bytes.fromhex(signature))

# 3. Verify on-chain (blockchain anchoring)
# Check EAS attestation at:
# https://base-sepolia.easscan.org/attestation/view/{attestation_uid}
```

---

## Trust Score Interpretation

| Score Range | Label | Meaning |
|------------|-------|---------|
| 900-1000 | Excellent | Proven reliable over many interactions |
| 700-899 | Good | Building solid track record |
| 500-699 | Developing | New agent or limited data |
| 300-499 | Concerning | Frequent errors detected |
| 0-299 | Critical | Major reliability issues |

**Score = 500 means "unknown" (new agent).** Score increases as the agent completes tasks successfully. More usage with maintained quality = higher score.

**What does NOT affect score:**
- API latency (provider's issue, not agent's)
- Cautious language ("I think", "maybe")
- Infrastructure errors (rate limits, billing)

---

## Supported Agent Types

ATLAST ECP works with any agent that makes LLM API calls:

| Agent Type | Integration Method | Auto-Record |
|-----------|-------------------|-------------|
| OpenClaw agents | Proxy (Layer 0) | ✅ Automatic |
| Claude Code | Hooks (PostToolUse) | ✅ Automatic after `atlast init` |
| Python SDK (OpenAI/Anthropic/Gemini) | `wrap(client)` (Layer 1) | ✅ One line change |
| LangChain | Callback adapter (Layer 2) | ✅ One line change |
| CrewAI | Callback adapter | ✅ One line change |
| AutoGen | Middleware adapter | ✅ One line change |
| Ollama (local models) | Proxy (Layer 0) | ✅ Automatic |
| Any OpenAI-compatible API | Proxy (Layer 0) | ✅ Automatic |
| Custom agents | `record_minimal()` (Layer 1) | Manual call |

---

## Webhook Configuration

Your users configure the webhook after installation:

```bash
# Set your platform's webhook URL
atlast config set webhook_url https://api.yourplatform.com/v1/ecp-webhook
atlast config set webhook_secret YOUR_SHARED_SECRET
```

Or via environment variables:
```bash
export ATLAST_WEBHOOK_URL=https://api.yourplatform.com/v1/ecp-webhook
export ATLAST_WEBHOOK_SECRET=YOUR_SHARED_SECRET
```

---

## FAQ for Integration Partners

### Q: Do I need to run any ATLAST infrastructure?
No. ATLAST is fully decentralized. Agents record locally, anchor on-chain, and push to your webhook. You just receive data.

### Q: How much does it cost?
ATLAST ECP is open source (MIT license), free forever. On-chain anchoring costs ~$0.001/batch on Base.

### Q: Can agents fake their Trust Score?
The score is computed from cryptographically chained evidence. Faking would require breaking SHA-256 chains and forging Ed25519 signatures. Anti-gaming filters also detect scripted/repeated interactions.

### Q: How often do I receive webhook data?
By default: when an agent accumulates 1000 records OR every 7 days, whichever comes first. Users can also manually push with `atlast push`.

### Q: What data stays on the user's machine?
Raw conversation content (input/output) stays local. Only hashes, metadata, and Trust Score are transmitted. The user controls what leaves their device.

### Q: Can I verify data independently?
Yes. Every batch has a Merkle root anchored on Base blockchain via EAS. You can verify any record against the Merkle tree and check the on-chain attestation.

---

## Quick Reference

| Resource | URL |
|----------|-----|
| GitHub | https://github.com/willau95/atlast-ecp |
| PyPI | https://pypi.org/project/atlast-ecp/ |
| Website | https://weba0.com |
| ECP Spec | https://github.com/willau95/atlast-ecp/blob/main/ECP-SPEC.md |
| API Docs | https://docs.weba0.com |
| EAS (Blockchain) | https://base-sepolia.easscan.org |

---

## Contact

- GitHub Issues: https://github.com/willau95/atlast-ecp/issues
- Email: protocol@weba0.com

---

*ATLAST Protocol — Making AI Agent Work Verifiable.*
*Open Source (MIT) · Privacy First · Blockchain Anchored*
