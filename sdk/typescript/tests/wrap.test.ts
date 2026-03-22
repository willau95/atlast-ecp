import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mkdtempSync, rmSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';

vi.mock('../src/storage', () => ({
  storeRecord: vi.fn(),
}));

import { wrap } from '../src/wrap';
import { storeRecord } from '../src/storage';

describe('wrap', () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = mkdtempSync(join(tmpdir(), 'ecp-wrap-'));
    process.env.ATLAST_ECP_DIR = tmpDir;
    vi.clearAllMocks();
  });

  afterEach(() => {
    rmSync(tmpDir, { recursive: true, force: true });
    delete process.env.ATLAST_ECP_DIR;
  });

  it('returns the original result from create()', async () => {
    const expected = { choices: [{ message: { content: 'Hi' } }], usage: { prompt_tokens: 5, completion_tokens: 3 } };
    const client = wrap({ chat: { completions: { create: vi.fn().mockResolvedValue(expected) } } }, { agentId: 'test' });

    const result = await client.chat.completions.create({ model: 'gpt-4', messages: [] });
    expect(result).toEqual(expected);
  });

  it('calls the original create() function once', async () => {
    const mockCreate = vi.fn().mockResolvedValue({ choices: [], usage: {} });
    const client = wrap({ chat: { completions: { create: mockCreate } } }, { agentId: 'test' });

    await client.chat.completions.create({ model: 'gpt-4', messages: [{ role: 'user', content: 'hello' }] });
    expect(mockCreate).toHaveBeenCalledOnce();
  });

  it('stores a record after each LLM call', async () => {
    const client = wrap(
      { chat: { completions: { create: vi.fn().mockResolvedValue({ choices: [], usage: { prompt_tokens: 10, completion_tokens: 5 } }) } } },
      { agentId: 'test' },
    );

    await client.chat.completions.create({ model: 'gpt-4', messages: [] });
    expect(storeRecord).toHaveBeenCalledOnce();
  });

  it('stores record with correct agent_id and step_type llm_call', async () => {
    const client = wrap(
      { chat: { completions: { create: vi.fn().mockResolvedValue({ choices: [], usage: {} }) } } },
      { agentId: 'my-llm-agent' },
    );

    await client.chat.completions.create({ model: 'gpt-4', messages: [] });
    expect(storeRecord).toHaveBeenCalledWith('my-llm-agent', expect.objectContaining({
      agent: 'my-llm-agent',
      action: 'llm_call',
    }));
  });

  it('stores record with error flag and re-throws when create() throws', async () => {
    const client = wrap(
      { chat: { completions: { create: vi.fn().mockRejectedValue(new Error('Rate limit exceeded')) } } },
      { agentId: 'test' },
    );

    await expect(client.chat.completions.create({ model: 'gpt-4', messages: [] })).rejects.toThrow('Rate limit exceeded');
    expect(storeRecord).toHaveBeenCalledOnce();
    const [, record] = vi.mocked(storeRecord).mock.calls[0];
    expect((record as { flags: string[] }).flags).toContain('error');
  });
});
