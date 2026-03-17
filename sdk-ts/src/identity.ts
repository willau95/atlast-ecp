/**
 * ATLAST ECP Identity — DID management and key storage
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs';
import { join } from 'path';
import { generateDID, generateKeyPair } from './crypto';
import type { ECPIdentity } from './types';

const DEFAULT_ECP_DIR = join(process.env.HOME || '~', '.ecp');

export function getECPDir(): string {
  return process.env.ATLAST_ECP_DIR || DEFAULT_ECP_DIR;
}

function identityPath(agentId: string): string {
  const dir = join(getECPDir(), 'agents', agentId);
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
  return join(dir, 'identity.json');
}

export function loadOrCreateIdentity(agentId: string): ECPIdentity {
  const path = identityPath(agentId);

  if (existsSync(path)) {
    const data = JSON.parse(readFileSync(path, 'utf-8'));
    return data as ECPIdentity;
  }

  const keyPair = generateKeyPair();
  const identity: ECPIdentity = {
    did: generateDID(),
    agent_id: agentId,
    public_key: keyPair.publicKey,
    private_key: keyPair.privateKey,
    created_at: new Date().toISOString(),
  };

  writeFileSync(path, JSON.stringify(identity, null, 2));
  return identity;
}

export function getIdentity(agentId: string): ECPIdentity | null {
  const path = identityPath(agentId);
  if (!existsSync(path)) return null;
  return JSON.parse(readFileSync(path, 'utf-8')) as ECPIdentity;
}
