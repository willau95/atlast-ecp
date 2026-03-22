# Migration Guide: v0.7.x → v0.8.0

## Python SDK

### Package Name (unchanged)
```bash
pip install atlast-ecp  # same as before
```

### Breaking Changes

1. **Batch payload field renames** (affects custom integrations only):
   - `signature` → `sig`
   - `records` → `record_hashes`
   - `batch_ts` format: float seconds → **int milliseconds**
   
2. **`ecp_version` field meaning**:
   - In records: `"0.1"` = record format version (unchanged)
   - In batch payloads: `"0.1"` = batch protocol version (new distinction)

### New Features

- **Streaming support**: `wrap(client)` now records streaming responses via `_RecordedStream`
- **7 behavioral flags**: `retried`, `hedged`, `incomplete`, `high_latency`, `error`, `human_review`, `a2a_delegated`
- **`flag_counts` in batch**: Aggregated flag statistics sent with each batch
- **Webhook retry**: Server retries failed webhooks 3× with exponential backoff
- **Framework adapters**: LangChain, CrewAI, AutoGen callback handlers

### Migration Steps

If you use the SDK normally (`wrap()`, `@track`, `atlast run`), **no changes needed**. The SDK handles all field formatting internally.

If you build custom batch payloads:
```python
# Old (v0.7)
payload = {"signature": sig, "records": [...], "batch_ts": 1711234567.89}

# New (v0.8)
payload = {"sig": sig, "record_hashes": [...], "batch_ts": 1711234567890}
```

## TypeScript SDK

### Package Name Change
```bash
# Old
npm install atlast-ecp-ts

# New
npm install @atlast/sdk
```

### Import Change
```typescript
// Old
import { wrap, track } from 'atlast-ecp-ts';

// New
import { wrap, track } from '@atlast/sdk';
```

### API (unchanged)
All functions (`wrap`, `track`, `createRecord`, `buildMerkleTree`) have the same signatures.
