import { describe, it, expect } from 'vitest';
import { sha256, hashRecord, buildMerkleRoot, generateDID, generateKeyPair, signData, verifySignature } from '../src/crypto';

describe('crypto', () => {
  it('sha256 produces consistent hashes', () => {
    const h1 = sha256('hello');
    const h2 = sha256('hello');
    expect(h1).toBe(h2);
    expect(h1).toHaveLength(64);
  });

  it('sha256 different inputs produce different hashes', () => {
    expect(sha256('hello')).not.toBe(sha256('world'));
  });

  it('hashRecord zeroes chain.hash and sig', () => {
    const record = {
      id: 'rec_test',
      ts: 1000,
      agent_id: 'test',
      chain: { prev: 'genesis', hash: 'should-be-zeroed' },
      sig: 'should-be-removed',
    };
    const h = hashRecord(record);
    expect(h).toHaveLength(64);

    // Same record without chain.hash and sig should produce same hash
    const record2 = { ...record, chain: { prev: 'genesis', hash: 'different' }, sig: 'different' };
    expect(hashRecord(record2)).toBe(h);
  });

  it('generateDID produces valid format', () => {
    const did = generateDID();
    expect(did).toMatch(/^did:ecp:[a-f0-9]{32}$/);
  });

  it('buildMerkleRoot handles empty', () => {
    const root = buildMerkleRoot([]);
    expect(root).toHaveLength(64);
  });

  it('buildMerkleRoot handles single', () => {
    const root = buildMerkleRoot(['abc123']);
    expect(root).toBe('abc123');
  });

  it('buildMerkleRoot handles multiple', () => {
    const root = buildMerkleRoot(['a', 'b', 'c']);
    expect(root).toHaveLength(64);
  });

  it('key generation and signing', () => {
    const kp = generateKeyPair();
    expect(kp.publicKey).toBeTruthy();
    expect(kp.privateKey).toBeTruthy();

    const data = 'test message';
    const sig = signData(kp.privateKey, data);
    expect(sig).toBeTruthy();

    expect(verifySignature(kp.publicKey, data, sig)).toBe(true);
    expect(verifySignature(kp.publicKey, 'wrong', sig)).toBe(false);
  });
});
