/**
 * ATLAST ECP Storage — local record storage (JSONL)
 */

import { existsSync, mkdirSync, appendFileSync, readFileSync } from 'fs';
import { join } from 'path';
import { getECPDir } from './identity';
import type { ECPRecord } from './types';

function recordsPath(agentId: string): string {
  const dir = join(getECPDir(), 'agents', agentId);
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
  return join(dir, 'records.jsonl');
}

export function storeRecord(agentId: string, record: ECPRecord): void {
  const path = recordsPath(agentId);
  appendFileSync(path, JSON.stringify(record) + '\n');
}

export function loadRecords(agentId: string): ECPRecord[] {
  const path = recordsPath(agentId);
  if (!existsSync(path)) return [];

  return readFileSync(path, 'utf-8')
    .trim()
    .split('\n')
    .filter(Boolean)
    .map((line: string) => JSON.parse(line) as ECPRecord);
}

export function collectBatch(agentId: string, maxRecords: number = 100): { records: ECPRecord[]; hashes: string[] } {
  const records = loadRecords(agentId).slice(-maxRecords);
  const hashes = records.map((r) => r.chain.hash);
  return { records, hashes };
}
