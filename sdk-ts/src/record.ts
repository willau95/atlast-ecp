/**
 * ATLAST ECP Record — create and chain evidence records
 */

import { sha256, hashRecord, generateId, signData } from './crypto';
import type { ECPRecord, ECPIdentity } from './types';

let lastHash = 'genesis';

export function setChainHead(hash: string): void {
  lastHash = hash;
}

export function getChainHead(): string {
  return lastHash;
}

export interface CreateRecordOptions {
  agentId: string;
  stepType?: ECPRecord['step_type'];
  model?: string;
  input: string;
  output: string;
  tokensIn?: number;
  tokensOut?: number;
  latencyMs?: number;
  flags?: string[];
  metadata?: Record<string, unknown>;
  identity?: ECPIdentity;
}

export function createRecord(opts: CreateRecordOptions): ECPRecord {
  const record: ECPRecord = {
    id: generateId('rec'),
    ts: Date.now(),
    agent_id: opts.agentId,
    step_type: opts.stepType || 'llm_call',
    model: opts.model,
    input_hash: sha256(opts.input),
    output_hash: sha256(opts.output),
    tokens_in: opts.tokensIn,
    tokens_out: opts.tokensOut,
    latency_ms: opts.latencyMs,
    flags: opts.flags || [],
    metadata: opts.metadata,
    chain: {
      prev: lastHash,
      hash: '',
    },
  };

  // Detect signals
  if (opts.latencyMs && opts.latencyMs > 5000) {
    record.flags.push('high_latency');
  }

  // Compute chain hash
  record.chain.hash = hashRecord(record as unknown as Record<string, unknown>);

  // Sign if identity provided
  if (opts.identity) {
    record.sig = signData(opts.identity.private_key, record.chain.hash);
  }

  lastHash = record.chain.hash;
  return record;
}
