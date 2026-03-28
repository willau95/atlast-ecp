/**
 * ATLAST ECP Crypto — hashing, signing, merkle tree
 */

import { createHash, randomBytes, generateKeyPairSync, sign, verify, createPrivateKey, createPublicKey } from 'crypto';

/**
 * Recursively sort all object keys and produce deterministic JSON.
 * Matches Python's json.dumps(obj, sort_keys=True, separators=(",",":")).
 */
function stableStringify(obj: unknown): string {
  if (obj === null || obj === undefined) return 'null';
  if (typeof obj === 'string') return JSON.stringify(obj);
  if (typeof obj === 'number' || typeof obj === 'boolean') return String(obj);
  if (Array.isArray(obj)) return '[' + obj.map(stableStringify).join(',') + ']';
  if (typeof obj === 'object') {
    const keys = Object.keys(obj as Record<string, unknown>).sort();
    return '{' + keys.map(k => JSON.stringify(k) + ':' + stableStringify((obj as Record<string, unknown>)[k])).join(',') + '}';
  }
  return String(obj);
}

export function sha256(data: string): string {
  return 'sha256:' + createHash('sha256').update(data).digest('hex');
}

/** Raw SHA-256 hex (no prefix) — for internal use only (e.g., hashRecord). */
export function sha256Raw(data: string): string {
  return createHash('sha256').update(data).digest('hex');
}

export function hashRecord(record: Record<string, unknown>): string {
  // Zero out chain.hash and sig before hashing
  const clone = JSON.parse(JSON.stringify(record));
  if (clone.chain) clone.chain.hash = '';
  clone.sig = '';
  const canonical = stableStringify(clone);
  return sha256(canonical);
}

export function generateId(prefix: string = 'rec'): string {
  return `${prefix}_${randomBytes(6).toString('hex')}`;
}

export function generateDID(publicKeyHex?: string): string {
  if (publicKeyHex) {
    // Deterministic: sha256(publicKeyHex)[:32] — matches Python/Go SDK
    const hash = createHash('sha256').update(publicKeyHex).digest('hex');
    return `did:ecp:${hash.substring(0, 32)}`;
  }
  // Fallback: random (for cases where public key not yet available)
  const id = randomBytes(16).toString('hex');
  return `did:ecp:${id}`;
}

export function buildMerkleRoot(hashes: string[]): string {
  if (hashes.length === 0) return sha256('empty');
  if (hashes.length === 1) return hashes[0];

  const next: string[] = [];
  for (let i = 0; i < hashes.length; i += 2) {
    const left = hashes[i];
    const right = i + 1 < hashes.length ? hashes[i + 1] : left;
    next.push(sha256(left + right));
  }
  return buildMerkleRoot(next);
}

export interface KeyPair {
  publicKey: string;
  privateKey: string;
}

export function generateKeyPair(): KeyPair {
  const { publicKey, privateKey } = generateKeyPairSync('ed25519', {
    publicKeyEncoding: { type: 'spki', format: 'der' },
    privateKeyEncoding: { type: 'pkcs8', format: 'der' },
  });
  return {
    publicKey: publicKey.toString('hex'),
    privateKey: privateKey.toString('hex'),
  };
}

export function signData(privateKeyHex: string, data: string): string {
  const keyObj = createPrivateKey({
    key: Buffer.from(privateKeyHex, 'hex'),
    format: 'der',
    type: 'pkcs8',
  });
  const signature = sign(null, Buffer.from(data), keyObj);
  return signature.toString('hex');
}

export function verifySignature(publicKeyHex: string, data: string, signatureHex: string): boolean {
  try {
    const keyObj = createPublicKey({
      key: Buffer.from(publicKeyHex, 'hex'),
      format: 'der',
      type: 'spki',
    });
    return verify(null, Buffer.from(data), keyObj, Buffer.from(signatureHex, 'hex'));
  } catch {
    return false;
  }
}
