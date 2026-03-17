# @atlast/sdk

**ATLAST Evidence Chain Protocol (ECP) SDK for TypeScript/Node.js**

> At last, trust for the Agent economy.

Track your AI agent's work with cryptographic evidence chains. Every LLM call, tool use, and decision is recorded, hashed, and chained — creating an immutable audit trail.

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

// All chat.completions.create() calls are now tracked
const response = await client.chat.completions.create({
  model: 'gpt-4',
  messages: [{ role: 'user', content: 'Hello' }],
});
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
import { createRecord, storeRecord, uploadBatch } from '@atlast/sdk';

const record = createRecord({
  agentId: 'my-agent',
  input: 'user query',
  output: 'agent response',
  model: 'claude-sonnet-4-20250514',
  latencyMs: 1234,
});

storeRecord('my-agent', record);

// Upload batch to ATLAST backend
await uploadBatch({ agentId: 'my-agent' });
```

## How It Works

1. **Record**: Each LLM call creates an ECP record with input/output hashes (content never leaves your device)
2. **Chain**: Records are linked via SHA-256 hashes, forming an immutable evidence chain
3. **Sign**: Records are signed with your agent's Ed25519 key (auto-generated DID)
4. **Upload**: Batch upload merkle roots to ATLAST backend for verification + on-chain anchoring

## API

| Export | Description |
|--------|-------------|
| `wrap(client, opts)` | Wrap OpenAI-compatible client for automatic tracking |
| `track(agentId, fn)` | Track a function's execution as an ECP record |
| `createRecord(opts)` | Manually create an ECP record |
| `storeRecord(id, rec)` | Store a record locally (JSONL) |
| `uploadBatch(config)` | Upload records to ATLAST backend |
| `loadOrCreateIdentity(id)` | Load or create agent DID + keys |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ATLAST_ECP_DIR` | `~/.ecp` | Directory for ECP data (identity, records) |

## License

MIT
