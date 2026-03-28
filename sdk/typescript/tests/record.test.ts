import { describe, it, expect, beforeEach } from 'vitest';
import { createRecord, setChainHead, getChainHead } from '../src/record';

describe('record', () => {
  beforeEach(() => {
    setChainHead('genesis');
  });

  it('creates a record with chain hash', () => {
    const r = createRecord({
      agentId: 'test-agent',
      input: 'hello',
      output: 'world',
    });

    expect(r.id).toMatch(/^rec_/);
    expect(r.agent).toBe('test-agent');
    expect(r.in_hash).toMatch(/^sha256:[a-f0-9]{64}$/);
    expect(r.out_hash).toMatch(/^sha256:[a-f0-9]{64}$/);
    expect(r.chain.prev).toBe('genesis');
    expect(r.chain.hash).toMatch(/^sha256:[a-f0-9]{64}$/);
    expect(r.action).toBe('llm_call');
  });

  it('chains records correctly', () => {
    const r1 = createRecord({ agentId: 'test', input: 'a', output: 'b' });
    const r2 = createRecord({ agentId: 'test', input: 'c', output: 'd' });

    expect(r2.chain.prev).toBe(r1.id);
    expect(getChainHead()).toBe(r2.id);
  });

  it('detects high latency', () => {
    const r = createRecord({
      agentId: 'test',
      input: 'a',
      output: 'b',
      latencyMs: 10000,
    });

    expect(r.flags).toContain('high_latency');
  });

  it('input/output are hashed, not stored raw', () => {
    const r = createRecord({
      agentId: 'test',
      input: 'secret input',
      output: 'secret output',
    });

    // Record should NOT contain raw input/output
    const json = JSON.stringify(r);
    expect(json).not.toContain('secret input');
    expect(json).not.toContain('secret output');
    // But should contain hashes with sha256: prefix
    expect(r.in_hash).toMatch(/^sha256:[a-f0-9]{64}$/);
    expect(r.out_hash).toMatch(/^sha256:[a-f0-9]{64}$/);
  });
});
