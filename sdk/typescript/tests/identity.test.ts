import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { mkdtempSync, rmSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';
import { loadOrCreateIdentity, getIdentity } from '../src/identity';

describe('identity', () => {
  let tmpDir: string;
  let originalEcpDir: string | undefined;

  beforeEach(() => {
    tmpDir = mkdtempSync(join(tmpdir(), 'ecp-identity-'));
    originalEcpDir = process.env.ATLAST_ECP_DIR;
    process.env.ATLAST_ECP_DIR = tmpDir;
  });

  afterEach(() => {
    rmSync(tmpDir, { recursive: true, force: true });
    if (originalEcpDir !== undefined) {
      process.env.ATLAST_ECP_DIR = originalEcpDir;
    } else {
      delete process.env.ATLAST_ECP_DIR;
    }
  });

  it('creates a new identity with valid DID format', () => {
    const identity = loadOrCreateIdentity('agent-1');
    expect(identity.did).toMatch(/^did:ecp:[a-f0-9]{32}$/);
  });

  it('creates identity with all required fields', () => {
    const identity = loadOrCreateIdentity('agent-2');
    expect(identity.agent_id).toBe('agent-2');
    expect(identity.public_key).toBeTruthy();
    expect(identity.private_key).toBeTruthy();
    expect(identity.created_at).toBeTruthy();
  });

  it('persists identity — same keys returned on reload', () => {
    const first = loadOrCreateIdentity('agent-persist');
    const second = loadOrCreateIdentity('agent-persist');
    expect(second.did).toBe(first.did);
    expect(second.public_key).toBe(first.public_key);
    expect(second.private_key).toBe(first.private_key);
  });

  it('creates distinct identities for different agent IDs', () => {
    const a = loadOrCreateIdentity('agent-a');
    const b = loadOrCreateIdentity('agent-b');
    expect(a.did).not.toBe(b.did);
    expect(a.public_key).not.toBe(b.public_key);
  });

  it('getIdentity returns null for unknown agent', () => {
    expect(getIdentity('no-such-agent')).toBeNull();
  });

  it('getIdentity returns stored identity after creation', () => {
    const created = loadOrCreateIdentity('agent-get');
    const loaded = getIdentity('agent-get');
    expect(loaded).not.toBeNull();
    expect(loaded!.did).toBe(created.did);
  });
});
