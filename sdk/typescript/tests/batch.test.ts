import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { generateKeyPair, generateDID } from '../src/crypto';

vi.mock('../src/storage', () => ({
  collectBatch: vi.fn(),
}));

vi.mock('../src/identity', () => ({
  loadOrCreateIdentity: vi.fn(),
}));

import { uploadBatch } from '../src/batch';
import { collectBatch } from '../src/storage';
import { loadOrCreateIdentity } from '../src/identity';

const HASH_A = 'sha256:' + 'a'.repeat(64);
const HASH_B = 'sha256:' + 'b'.repeat(64);

function makeRecord(id: string, flags: string[], latencyMs: number, hash = HASH_A) {
  return { id, flags, latency_ms: latencyMs, chain: { hash, prev: 'genesis' } };
}

describe('batch upload', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    const kp = generateKeyPair();
    vi.mocked(loadOrCreateIdentity).mockReturnValue({
      did: generateDID(),
      agent_id: 'test-agent',
      public_key: kp.publicKey,
      private_key: kp.privateKey,
      created_at: new Date().toISOString(),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns empty status when no records exist', async () => {
    vi.mocked(collectBatch).mockReturnValue({ records: [], hashes: [] });

    const result = await uploadBatch({ agentId: 'test-agent', apiUrl: 'http://localhost:3000' });
    expect(result.status).toBe('empty');
    expect(result.message).toBeTruthy();
  });

  it('posts to the correct URL', async () => {
    const r = makeRecord('rec_1', [], 100);
    vi.mocked(collectBatch).mockReturnValue({ records: [r], hashes: [r.chain.hash] });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ batch_id: 'b1', status: 'accepted', attestation_uid: 'u1' }),
    }));

    await uploadBatch({ agentId: 'test-agent', apiUrl: 'http://api.example.com' });

    const [url] = vi.mocked(fetch).mock.calls[0] as [string, ...unknown[]];
    expect(url).toBe('http://api.example.com/v1/batches');
  });

  it('builds payload with correct fields', async () => {
    const r1 = makeRecord('rec_1', ['high_latency'], 6000, HASH_A);
    const r2 = makeRecord('rec_2', [], 200, HASH_B);
    vi.mocked(collectBatch).mockReturnValue({ records: [r1, r2], hashes: [r1.chain.hash, r2.chain.hash] });
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ batch_id: 'b1', status: 'accepted', attestation_uid: 'u1' }),
    });
    vi.stubGlobal('fetch', mockFetch);

    await uploadBatch({ agentId: 'test-agent', apiUrl: 'http://localhost:3000', apiKey: 'k' });

    const body = JSON.parse((mockFetch.mock.calls[0] as [string, RequestInit])[1].body as string);
    expect(body.record_count).toBe(2);
    expect(body.merkle_root).toMatch(/^sha256:[a-f0-9]{64}$/);
    expect(body.ecp_version).toBe('0.1');
    expect(body.flag_counts).toEqual({ high_latency: 1 });
    expect(body.avg_latency_ms).toBe(3100);
    expect(body.record_hashes).toHaveLength(2);
  });

  it('includes X-Agent-Key header when API key is provided', async () => {
    const r = makeRecord('rec_1', [], 100);
    vi.mocked(collectBatch).mockReturnValue({ records: [r], hashes: [r.chain.hash] });
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ batch_id: 'b1', status: 'accepted', attestation_uid: 'u1' }),
    });
    vi.stubGlobal('fetch', mockFetch);

    await uploadBatch({ agentId: 'test-agent', apiUrl: 'http://localhost:3000', apiKey: 'secret-key' });

    const init = (mockFetch.mock.calls[0] as [string, RequestInit])[1];
    expect((init.headers as Record<string, string>)['X-Agent-Key']).toBe('secret-key');
  });

  it('throws on HTTP error response', async () => {
    const r = makeRecord('rec_1', [], 100);
    vi.mocked(collectBatch).mockReturnValue({ records: [r], hashes: [r.chain.hash] });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      text: () => Promise.resolve('Unauthorized'),
    }));

    await expect(
      uploadBatch({ agentId: 'test-agent', apiUrl: 'http://localhost:3000' })
    ).rejects.toThrow('401');
  });
});
