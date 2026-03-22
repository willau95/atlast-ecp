/**
 * ATLAST ECP Track — decorator-style tracking for agent functions
 * 
 * Usage:
 *   import { track } from '@atlast/sdk';
 *   
 *   const myFunction = track('my-agent', async (input: string) => {
 *     // ... agent logic
 *     return result;
 *   });
 */

import { createRecord } from './record';
import { storeRecord } from './storage';
import { loadOrCreateIdentity } from './identity';
import { sha256 } from './crypto';

export interface TrackOptions {
  agentId: string;
  action?: 'llm_call' | 'tool_call' | 'a2a_call' | 'message' | 'decision' | 'custom';
  sessionId?: string;
  metadata?: Record<string, unknown>;
}

/**
 * Track a function's execution as an ECP record.
 */
export function track<TArgs extends unknown[], TResult>(
  agentIdOrOpts: string | TrackOptions,
  fn: (...args: TArgs) => Promise<TResult>,
): (...args: TArgs) => Promise<TResult> {
  const opts: TrackOptions =
    typeof agentIdOrOpts === 'string' ? { agentId: agentIdOrOpts } : agentIdOrOpts;

  const identity = loadOrCreateIdentity(opts.agentId);

  return async function tracked(...args: TArgs): Promise<TResult> {
    const startTime = Date.now();
    const inputStr = JSON.stringify(args);
    const flags: string[] = [];
    let result: TResult;

    try {
      result = await fn(...args);
    } catch (e) {
      flags.push('error');
      const record = createRecord({
        agentId: opts.agentId,
        action: opts.action || 'custom',
        input: inputStr,
        output: `error: ${(e as Error).message}`,
        latencyMs: Date.now() - startTime,
        flags,
        metadata: opts.metadata,
        identity,
      });
      storeRecord(opts.agentId, record);
      throw e;
    }

    const record = createRecord({
      agentId: opts.agentId,
      action: opts.action || 'custom',
      input: inputStr,
      output: JSON.stringify(result),
      latencyMs: Date.now() - startTime,
      flags,
      metadata: opts.metadata,
      identity,
    });
    storeRecord(opts.agentId, record);

    return result;
  };
}
