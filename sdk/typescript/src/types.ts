/**
 * ATLAST ECP Types — Evidence Chain Protocol data structures
 */

export interface ECPRecord {
  id: string;
  ts: number;
  agent_id: string;
  step_type: 'llm_call' | 'tool_call' | 'decision' | 'custom';
  model?: string;
  input_hash: string;
  output_hash: string;
  tokens_in?: number;
  tokens_out?: number;
  latency_ms?: number;
  flags: string[];
  metadata?: Record<string, unknown>;
  chain: {
    prev: string;
    hash: string;
  };
  sig?: string;
}

export interface ECPIdentity {
  did: string;
  agent_id: string;
  public_key: string;
  private_key: string;
  created_at: string;
}

export interface BatchUploadRequest {
  agent_did: string;
  merkle_root: string;
  record_count: number;
  avg_latency_ms: number;
  batch_ts: number;
  sig: string;
  ecp_version: string;
  flag_counts?: Record<string, number>;
  record_hashes?: Array<{
    id: string;
    hash: string;
    flags?: string[];
  }>;
}

export interface BatchUploadResponse {
  batch_id: string;
  attestation_uid?: string;
  eas_url?: string;
  status: string;
  message: string;
}

export interface ATLASTConfig {
  apiUrl?: string;
  apiKey?: string;
  ecpDir?: string;
  agentId: string;
  autoUpload?: boolean;
  batchSize?: number;
  flushIntervalMs?: number;
}

export interface LocalConfig {
  agent_did?: string;
  agent_api_key?: string;
  endpoint?: string;
}
