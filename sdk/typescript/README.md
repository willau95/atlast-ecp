# @atlast/sdk

**ATLAST Evidence Chain Protocol (ECP) SDK for TypeScript/Node.js**

> At last, trust for the Agent economy.

Track your AI agent's work with cryptographic evidence chains. Every LLM call, tool use, and decision is recorded, hashed, and chained — creating an immutable audit trail.

Privacy-first: only SHA-256 hashes are stored. Content never leaves your device.

## Install

```bash
npm install @atlast/sdk
```

## Quick Start

### Layer 1 — Wrap your OpenAI client (5 lines)

```typescript
import { wrap } from '@atlast/sdk';
import OpenAI from 'openai';

const client = wrap(new OpenAI(), { agentId: 'my-agent' });

// All chat.completions.create() calls are now automatically tracked
const response = await client.chat.completions.create({
  model: 'gpt-4',
  messages: [{ role: 'user', content: 'Hello' }],
});
// → ECP record saved to ~/.ecp/records/
```

### Track custom functions

```typescript
import { track } from '@atlast/sdk';

const myAgentStep = track('my-agent', async (query: string) => {
  // Your agent logic here
  return await processQuery(query);
});

await myAgentStep('What is the weather?');
```

### Manual record creation

```typescript
import { createRecord, storeRecord } from '@atlast/sdk';

const record = createRecord({
  agentId: 'my-agent',
  input: 'user query',
  output: 'agent response',
  model: 'claude-sonnet-4-20250514',
  latencyMs: 1234,
});

storeRecord('my-agent', record);
```

### Upload to ATLAST Backend

```typescript
import { uploadBatch } from '@atlast/sdk';

// Upload batched records (merkle root + record hashes)
await uploadBatch({
  agentId: 'my-agent',
  apiUrl: process.env.ATLAST_API_URL,  // or set ATLAST_API_URL env
  apiKey: 'your-agent-api-key',       // or set ATLAST_API_KEY env
});
```

## How It Works

1. **Record**: Each LLM call creates an ECP record with input/output SHA-256 hashes (content stays local)
2. **Chain**: Records are linked via hash chains, forming an immutable evidence trail
3. **Sign**: Records are signed with your agent's Ed25519 key (auto-generated DID)
4. **Upload**: Batch upload merkle roots to ATLAST backend via `POST /v1/batches` with `X-Agent-Key` header

## API Reference

### Core

| Export | Description |
|--------|-------------|
| `wrap(client, opts)` | Wrap OpenAI-compatible client for automatic ECP tracking |
| `track(agentId, fn)` | Track a function's execution as an ECP record |
| `createRecord(opts)` | Create an ECP record manually |

### Storage

| Export | Description |
|--------|-------------|
| `storeRecord(id, rec)` | Store a record locally (JSONL in `~/.ecp/records/`) |
| `loadRecords(agentId)` | Load stored records for an agent |
| `collectBatch(agentId)` | Collect records into a batch for upload |

### Identity & Crypto

| Export | Description |
|--------|-------------|
| `loadOrCreateIdentity(id)` | Load or create agent DID + Ed25519 keys |
| `getIdentity(id)` | Get existing identity (returns null if none) |
| `sha256(data)` | SHA-256 hash with `sha256:` prefix |
| `hashRecord(record)` | Compute canonical hash of an ECP record |
| `buildMerkleRoot(hashes)` | Build merkle root from record hashes |
| `generateDID(publicKey)` | Generate `did:ecp:` identifier from public key |
| `verifySignature(data, sig, pubkey)` | Verify Ed25519 signature |

### Network

| Export | Description |
|--------|-------------|
| `uploadBatch(config)` | Upload batch to ATLAST backend (`POST /v1/batches`) |

### Types

| Export | Description |
|--------|-------------|
| `ECPRecord` | ECP record type definition |
| `ECPIdentity` | Agent identity (DID + keys) |
| `ATLASTConfig` | SDK configuration options |
| `CreateRecordOptions` | Options for `createRecord()` |
| `WrapOptions` | Options for `wrap()` |
| `TrackOptions` | Options for `track()` |
| `BatchUploadRequest` | Batch upload request shape |
| `BatchUploadResponse` | Batch upload response shape |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ATLAST_ECP_DIR` | `~/.ecp` | Directory for ECP data (identity, records) |
| `ATLAST_API_URL` | `https://your-ecp-server.com` | Backend API endpoint for batch upload |
| `ATLAST_API_KEY` | — | Agent API key (sent as `X-Agent-Key` header) |

## ECP Compatibility

This SDK produces ECP v0.1 records (nested `step` format). It is compatible with the Python SDK (`atlast-ecp`) which also supports ECP v1.0 (flat format). Both formats are valid and can coexist.

For zero-code recording via transparent proxy, see the Python SDK:
```bash
pip install atlast-ecp[proxy]
atlast run python my_agent.py
```

## Links

- [ECP Specification](https://github.com/willau95/atlast-ecp/blob/main/ECP-SPEC.md)
- [Python SDK](https://pypi.org/project/atlast-ecp/)
- [ATLAST Protocol](https://github.com/willau95/atlast-ecp)

## License

MIT
