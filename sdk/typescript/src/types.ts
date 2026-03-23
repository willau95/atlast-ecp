/**
 * ATLAST ECP Types — Evidence Chain Protocol data structures
 */

export interface ECPRecord {
  id: string;
  ts: number;
  agent: string;
  action: 'llm_call' | 'tool_call' | 'a2a_call' | 'message' | 'decision' | 'custom';
  in_hash: string;
  out_hash: string;
  model?: string;
  tokens_in?: number;
  tokens_out?: number;
  latency_ms?: number;
  flags: string[];
  cost_usd?: number;
  parent_agent?: string;
  session_id?: string;
  delegation_id?: string;
  delegation_depth?: number;
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
  maxRetries?: number;  // Upload retry attempts (default: 3)
}

export interface LocalConfig {
  agent_did?: string;
  agent_api_key?: string;
  endpoint?: string;
}
