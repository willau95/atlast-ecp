/**
 * ATLAST ECP Record — create and chain evidence records
 */

import { sha256, hashRecord, generateId, signData } from './crypto';
import type { ECPRecord, ECPIdentity } from './types';

let lastId = 'genesis';

export function setChainHead(id: string): void {
  lastId = id;
}

export function getChainHead(): string {
  return lastId;
}

export interface CreateRecordOptions {
  agentId: string;
  action?: ECPRecord['action'];
  model?: string;
  input: string;
  output: string;
  tokensIn?: number;
  tokensOut?: number;
  latencyMs?: number;
  flags?: string[];
  costUsd?: number;
  parentAgent?: string;
  sessionId?: string;
  delegationId?: string;
  delegationDepth?: number;
  metadata?: Record<string, unknown>;
  identity?: ECPIdentity;
}

export function createRecord(opts: CreateRecordOptions): ECPRecord {
  const record: ECPRecord = {
    id: generateId('rec'),
    ts: Date.now(),
    agent: opts.agentId,
    action: opts.action || 'llm_call',
    in_hash: sha256(opts.input),
    out_hash: sha256(opts.output),
    model: opts.model,
    tokens_in: opts.tokensIn,
    tokens_out: opts.tokensOut,
    latency_ms: opts.latencyMs,
    flags: opts.flags || [],
    cost_usd: opts.costUsd,
    parent_agent: opts.parentAgent,
    session_id: opts.sessionId,
    delegation_id: opts.delegationId,
    delegation_depth: opts.delegationDepth,
    metadata: opts.metadata,
    chain: {
      prev: lastId,
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

  lastId = record.id;
  return record;
}
