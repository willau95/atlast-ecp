import { describe, it, expect } from 'vitest';
import { sha256, hashRecord, buildMerkleRoot, generateDID, generateKeyPair, signData, verifySignature } from '../src/crypto';

describe('crypto', () => {
  it('sha256 produces consistent hashes with sha256: prefix', () => {
    const h1 = sha256('hello');
    const h2 = sha256('hello');
    expect(h1).toBe(h2);
    expect(h1).toMatch(/^sha256:[a-f0-9]{64}$/);
    expect(h1).toHaveLength(7 + 64); // "sha256:" + 64 hex chars
  });

  it('sha256 different inputs produce different hashes', () => {
    expect(sha256('hello')).not.toBe(sha256('world'));
  });

  it('sha256 matches Python SDK format', () => {
    // Python: hashlib.sha256(b"hello").hexdigest() = "2cf24dba5fb0a30e..."
    const h = sha256('hello');
    expect(h).toBe('sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824');
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
    expect(h).toMatch(/^sha256:[a-f0-9]{64}$/);

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
    expect(root).toMatch(/^sha256:[a-f0-9]{64}$/);
  });

  it('buildMerkleRoot handles single', () => {
    const root = buildMerkleRoot(['sha256:' + 'a'.repeat(64)]);
    expect(root).toBe('sha256:' + 'a'.repeat(64));
  });

  it('buildMerkleRoot handles multiple with sha256: prefix', () => {
    const hashes = [
      'sha256:' + 'a'.repeat(64),
      'sha256:' + 'b'.repeat(64),
      'sha256:' + 'c'.repeat(64),
    ];
    const root = buildMerkleRoot(hashes);
    expect(root).toMatch(/^sha256:[a-f0-9]{64}$/);
  });

  it('buildMerkleRoot matches Python SDK for 4 hashes', () => {
    // Cross-verified with Python SDK build_merkle_tree()
    const hashes = [
      'sha256:' + 'a'.repeat(64),
      'sha256:' + 'b'.repeat(64),
      'sha256:' + 'c'.repeat(64),
      'sha256:' + 'd'.repeat(64),
    ];
    const root = buildMerkleRoot(hashes);
    // This value was computed by Python SDK and verified
    expect(root).toBe('sha256:11e2d886a0a4e03b80fd00abbe0345a5b0d87b58168b43ba42863d82d9d93790');
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
