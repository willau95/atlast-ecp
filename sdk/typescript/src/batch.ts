/**
 * ATLAST ECP Batch — collect records and upload to backend
 */

import { buildMerkleRoot, signData } from './crypto';
import { collectBatch } from './storage';
import { loadOrCreateIdentity } from './identity';
import type { BatchUploadRequest, BatchUploadResponse, ATLASTConfig, ECPRecord } from './types';

const DEFAULT_API_URL = process.env.ATLAST_API_URL || '';  // User must configure

export async function uploadBatch(config: ATLASTConfig): Promise<BatchUploadResponse> {
  const identity = loadOrCreateIdentity(config.agentId);
  const { records, hashes } = collectBatch(config.agentId, config.batchSize || 100);

  if (records.length === 0) {
    return { batch_id: '', status: 'empty', message: 'No records to upload', attestation_uid: undefined };
  }

  const merkleRoot = buildMerkleRoot(hashes);
  const sig = signData(identity.private_key, merkleRoot);

  // Compute flag counts
  const flagCounts: Record<string, number> = {};
  let totalLatency = 0;
  let latencyCount = 0;
  for (const r of records) {
    for (const f of r.flags) {
      flagCounts[f] = (flagCounts[f] || 0) + 1;
    }
    if (r.latency_ms) {
      totalLatency += r.latency_ms;
      latencyCount++;
    }
  }

  const avgLatency = latencyCount > 0 ? Math.round(totalLatency / latencyCount) : 0;

  const payload: BatchUploadRequest = {
    agent_did: identity.did,
    merkle_root: merkleRoot,
    record_count: records.length,
    avg_latency_ms: avgLatency,
    batch_ts: Date.now(),
    sig,
    ecp_version: '0.5',
    flag_counts: flagCounts,
    record_hashes: records.map((r) => ({
      id: r.id,
      hash: r.chain.hash,
      flags: r.flags,
    })),
  };

  const apiUrl = config.apiUrl || process.env.ATLAST_API_URL || DEFAULT_API_URL;
  const apiKey = config.apiKey || process.env.ATLAST_API_KEY;
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (apiKey) {
    headers['X-Agent-Key'] = apiKey;
  }

  const resp = await fetch(`${apiUrl}/v1/batches`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });

  if (!resp.ok) {
    const errText = await resp.text();
    throw new Error(`Batch upload failed (${resp.status}): ${errText}`);
  }

  return (await resp.json()) as BatchUploadResponse;
}
