# ATLAST ECP Plugin for OpenClaw

**Layer 0 — Zero-code trust recording for any OpenClaw agent.**

## What It Does

This plugin passively captures every LLM interaction as an ECP (Evidence Chain Protocol) record:

1. **Message received** → captures input + timestamp
2. **Message sent** → completes the record with output + latency
3. **Hourly batch** → uploads Merkle-anchored batch to ATLAST API
4. **Agent tool** → `ecp_status` lets the agent check its own trust signals

No code changes needed. Just install and configure.

## Install

```bash
# Link for development
openclaw plugins install -l /path/to/atlast-ecp/integrations/openclaw-plugin

# Restart gateway
openclaw gateway restart
```

## Configure

Add to your `openclaw.json`:

```json
{
  "plugins": {
    "entries": {
      "atlast-ecp": {
        "enabled": true,
        "config": {
          "apiUrl": "https://api.llachat.com/v1",
          "apiKey": "ak_live_xxx"
        }
      }
    },
    "allow": ["atlast-ecp"]
  }
}
```

### Config Options

| Key | Default | Description |
|-----|---------|-------------|
| `apiUrl` | `https://api.llachat.com/v1` | ATLAST API endpoint |
| `apiKey` | — | Agent API key for authenticated uploads |
| `agentName` | — | Display name for this agent |
| `batchIntervalMs` | `3600000` (1h) | Batch upload interval |
| `ecpDir` | `~/.ecp` | Local ECP storage directory |
| `enabled` | `true` | Enable/disable recording |

## Agent Tool

Once installed, agents can call `ecp_status` to check their trust recording:

```
🔗 ATLAST ECP Status
  Agent DID: did:ecp:abc123...
  Total Records: 47
  Storage: /Users/you/.ecp
  API: https://api.llachat.com/v1
  
📊 Recent Records:
  rec_abc123 | 2026-03-17T15:30:00Z | 1200ms | clean
  rec_def456 | 2026-03-17T15:35:00Z | 800ms | hedged
```

## How It Works

```
User message → [message:received hook] → capture input + timestamp
                    ↓
Agent thinks → (normal OpenClaw processing, untouched)
                    ↓
Agent reply  → [message:sent hook] → complete ECP record
                    ↓
              → append to ~/.ecp/records.jsonl
                    ↓
Every hour   → [background service] → build Merkle tree → upload batch
```

**Fail-Open**: Recording failures never affect agent operation. If the ATLAST API is down, records queue locally and upload on the next successful batch.

## Privacy

- **Content stays local.** Only SHA-256 hashes of input/output are included in uploaded records.
- **No raw text leaves the device.** Merkle roots + hashes are uploaded, not conversation content.
- Records are stored in `~/.ecp/records.jsonl` (local only).
