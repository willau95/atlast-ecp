/**
 * @atlast/sdk — ATLAST Evidence Chain Protocol SDK for TypeScript/Node.js
 * 
 * Layer 1 integration: 5 lines of code to track your AI agent's work.
 * 
 * Quick Start:
 *   import { wrap } from '@atlast/sdk';
 *   import OpenAI from 'openai';
 *   
 *   const client = wrap(new OpenAI(), { agentId: 'my-agent' });
 *   // All LLM calls are now tracked with evidence chains
 */

// Core types
export type { ECPRecord, ECPIdentity, BatchUploadRequest, BatchUploadResponse, ATLASTConfig } from './types';

// Identity (DID management)
export { loadOrCreateIdentity, getIdentity } from './identity';

// Record creation
export { createRecord, setChainHead, getChainHead } from './record';
export type { CreateRecordOptions } from './record';

// Storage
export { storeRecord, loadRecords, collectBatch } from './storage';

// Batch upload
export { uploadBatch } from './batch';

// Wrap (Layer 1 — transparent client wrapper)
export { wrap } from './wrap';
export type { WrapOptions } from './wrap';

// Track (decorator-style function tracking)
export { track } from './track';
export type { TrackOptions } from './track';

// Crypto utilities
export { sha256, hashRecord, buildMerkleRoot, generateDID, verifySignature } from './crypto';

// Re-export LocalConfig type
export type { LocalConfig } from './types';
