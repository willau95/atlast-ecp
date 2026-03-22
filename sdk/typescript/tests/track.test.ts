import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mkdtempSync, rmSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';

vi.mock('../src/storage', () => ({
  storeRecord: vi.fn(),
}));

import { track } from '../src/track';
import { storeRecord } from '../src/storage';

describe('track', () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = mkdtempSync(join(tmpdir(), 'ecp-track-'));
    process.env.ATLAST_ECP_DIR = tmpDir;
    vi.clearAllMocks();
  });

  afterEach(() => {
    rmSync(tmpDir, { recursive: true, force: true });
    delete process.env.ATLAST_ECP_DIR;
  });

  it('returns the wrapped function result', async () => {
    const fn = track('test-agent', async (x: number) => x * 2);
    expect(await fn(5)).toBe(10);
  });

  it('passes all arguments to the wrapped function', async () => {
    const inner = vi.fn().mockResolvedValue('ok');
    const fn = track('test-agent', inner as (...args: unknown[]) => Promise<string>);
    await fn('arg1', 'arg2');
    expect(inner).toHaveBeenCalledWith('arg1', 'arg2');
  });

  it('stores a record after a successful call', async () => {
    const fn = track('test-agent', async (s: string) => s.toUpperCase());
    await fn('hello');
    expect(storeRecord).toHaveBeenCalledOnce();
  });

  it('stores record with the correct agent_id', async () => {
    const fn = track('my-agent', async () => 'result');
    await fn();
    expect(storeRecord).toHaveBeenCalledWith('my-agent', expect.objectContaining({ agent: 'my-agent' }));
  });

  it('re-throws errors from the wrapped function', async () => {
    const fn = track('test-agent', async () => { throw new Error('boom'); });
    await expect(fn()).rejects.toThrow('boom');
  });

  it('stores record with error flag when function throws', async () => {
    const fn = track('test-agent', async () => { throw new Error('oops'); });
    await fn().catch(() => {});
    expect(storeRecord).toHaveBeenCalledOnce();
    const [, record] = vi.mocked(storeRecord).mock.calls[0];
    expect((record as { flags: string[] }).flags).toContain('error');
  });

  it('uses custom stepType from TrackOptions', async () => {
    const fn = track({ agentId: 'test-agent', action: 'tool_call' }, async () => 'ok');
    await fn();
    const [, record] = vi.mocked(storeRecord).mock.calls[0];
    expect((record as { action: string }).action).toBe('tool_call');
  });

  it('includes metadata from TrackOptions in the stored record', async () => {
    const fn = track({ agentId: 'test-agent', metadata: { env: 'test', version: 2 } }, async () => 'ok');
    await fn();
    const [, record] = vi.mocked(storeRecord).mock.calls[0];
    expect((record as { metadata: unknown }).metadata).toEqual({ env: 'test', version: 2 });
  });

  it('defaults step_type to custom when using string agentId', async () => {
    const fn = track('test-agent', async () => 'ok');
    await fn();
    const [, record] = vi.mocked(storeRecord).mock.calls[0];
    expect((record as { action: string }).action).toBe('custom');
  });
});
