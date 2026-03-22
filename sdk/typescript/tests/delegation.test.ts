import { describe, it, expect } from 'vitest';
import { createRecord, setChainHead } from '../src/record';
import { hashRecord } from '../src/crypto';

describe('delegation fields', () => {
  it('creates record with delegation fields', () => {
    setChainHead('genesis');
    const r = createRecord({
      agentId: 'parent-agent',
      action: 'a2a_call',
      input: 'delegate task',
      output: 'sub-agent result',
      sessionId: 'sess_001',
      delegationId: 'del_abc',
      delegationDepth: 1,
    });
    expect(r.session_id).toBe('sess_001');
    expect(r.delegation_id).toBe('del_abc');
    expect(r.delegation_depth).toBe(1);
    expect(r.action).toBe('a2a_call');
  });

  it('record without delegation has undefined fields', () => {
    setChainHead('genesis');
    const r = createRecord({
      agentId: 'test',
      input: 'x',
      output: 'y',
    });
    expect(r.session_id).toBeUndefined();
    expect(r.delegation_id).toBeUndefined();
    expect(r.delegation_depth).toBeUndefined();
  });

  it('chain hash is self-consistent with delegation', () => {
    setChainHead('genesis');
    const r = createRecord({
      agentId: 'test',
      input: 'x',
      output: 'y',
      sessionId: 'sess_1',
      delegationDepth: 0,
    });
    // Recompute hash — should match
    const recomputed = hashRecord(r as unknown as Record<string, unknown>);
    expect(recomputed).toBe(r.chain.hash);
  });

  it('delegation_depth=0 is meaningful (root agent)', () => {
    setChainHead('genesis');
    const r = createRecord({
      agentId: 'root',
      input: 'x',
      output: 'y',
      delegationDepth: 0,
    });
    expect(r.delegation_depth).toBe(0);
  });
});
