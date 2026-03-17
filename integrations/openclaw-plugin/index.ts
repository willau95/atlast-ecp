/**
 * ATLAST ECP Plugin for OpenClaw
 *
 * Passive trust recording: captures every LLM interaction as an ECP record,
 * builds Merkle trees, and uploads batches to the ATLAST API.
 *
 * Install:
 *   openclaw plugins install -l /path/to/atlast-ecp/integrations/openclaw-plugin
 *
 * Config (openclaw.json):
 *   "plugins": {
 *     "entries": {
 *       "atlast-ecp": {
 *         "enabled": true,
 *         "config": {
 *           "apiUrl": "https://api.llachat.com/v1",
 *           "apiKey": "ak_live_xxx"
 *         }
 *       }
 *     }
 *   }
 */

import { createHash, randomBytes } from "crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync, appendFileSync } from "fs";
import { join } from "path";
import { homedir } from "os";

// ─── Types ───────────────────────────────────────────────────────────────────

interface PluginConfig {
  apiUrl?: string;
  apiKey?: string;
  agentName?: string;
  batchIntervalMs?: number;
  ecpDir?: string;
  enabled?: boolean;
}

interface ECPRecord {
  ecp: string;
  id: string;
  agent: string;
  ts: number;
  step: {
    type: string;
    in_hash: string;
    out_hash: string;
    latency_ms: number;
    flags: string[];
    model?: string;
    tokens_in?: number;
    tokens_out?: number;
  };
  chain: {
    prev: string;
    hash: string;
  };
  sig: string;
}

interface PendingInteraction {
  receivedAt: number;
  from: string;
  content: string;
  channelId: string;
  sessionKey: string;
}

// ─── Crypto Helpers ──────────────────────────────────────────────────────────

function sha256(data: string): string {
  return "sha256:" + createHash("sha256").update(data).digest("hex");
}

function hashContent(content: string | object): string {
  const raw = typeof content === "string" ? content : JSON.stringify(content);
  return sha256(raw);
}

function generateRecordId(): string {
  return `rec_${randomBytes(8).toString("hex")}`;
}

// ─── ECP Record Builder ─────────────────────────────────────────────────────

class ECPRecorder {
  private ecpDir: string;
  private recordsFile: string;
  private stateFile: string;
  private prevRecordId: string = "genesis";
  private recordCount: number = 0;
  private agentDid: string = "";

  constructor(ecpDir: string) {
    this.ecpDir = ecpDir;
    this.recordsFile = join(ecpDir, "records.jsonl");
    this.stateFile = join(ecpDir, "plugin_state.json");
    mkdirSync(ecpDir, { recursive: true });
    this.loadState();
  }

  private loadState() {
    try {
      if (existsSync(this.stateFile)) {
        const state = JSON.parse(readFileSync(this.stateFile, "utf-8"));
        this.prevRecordId = state.prevRecordId || "genesis";
        this.recordCount = state.recordCount || 0;
        this.agentDid = state.agentDid || "";
      }
    } catch {
      // Start fresh
    }

    if (!this.agentDid) {
      // Generate a DID from random bytes
      const id = randomBytes(16).toString("hex");
      this.agentDid = `did:ecp:${id}`;
      this.saveState();
    }
  }

  private saveState() {
    writeFileSync(
      this.stateFile,
      JSON.stringify(
        {
          prevRecordId: this.prevRecordId,
          recordCount: this.recordCount,
          agentDid: this.agentDid,
        },
        null,
        2
      )
    );
  }

  getDid(): string {
    return this.agentDid;
  }

  getRecordCount(): number {
    return this.recordCount;
  }

  createRecord(
    input: string,
    output: string,
    latencyMs: number,
    model?: string,
    tokensIn?: number,
    tokensOut?: number
  ): ECPRecord {
    const id = generateRecordId();
    const ts = Date.now();
    const inHash = hashContent(input);
    const outHash = hashContent(output);

    // Detect behavioral flags
    const flags: string[] = [];
    if (latencyMs > 30000) flags.push("slow");
    if (output.length < 10) flags.push("short_response");
    if (output.toLowerCase().includes("i'm not sure") || output.toLowerCase().includes("i don't know"))
      flags.push("hedged");

    const record: ECPRecord = {
      ecp: "0.1",
      id,
      agent: this.agentDid,
      ts,
      step: {
        type: "llm_call",
        in_hash: inHash,
        out_hash: outHash,
        latency_ms: latencyMs,
        flags,
        ...(model && { model }),
        ...(tokensIn !== undefined && { tokens_in: tokensIn }),
        ...(tokensOut !== undefined && { tokens_out: tokensOut }),
      },
      chain: {
        prev: this.prevRecordId,
        hash: "", // computed below
      },
      sig: "unverified", // No Ed25519 in plugin — use SDK for signing
    };

    // Compute chain hash
    const forHash = { ...record, chain: { ...record.chain, hash: "" }, sig: "" };
    record.chain.hash = sha256(JSON.stringify(forHash, Object.keys(forHash).sort()));

    // Persist
    appendFileSync(this.recordsFile, JSON.stringify(record) + "\n");

    this.prevRecordId = id;
    this.recordCount++;
    this.saveState();

    return record;
  }

  getRecentRecords(limit: number = 100): ECPRecord[] {
    try {
      if (!existsSync(this.recordsFile)) return [];
      const lines = readFileSync(this.recordsFile, "utf-8").trim().split("\n");
      return lines
        .slice(-limit)
        .map((l) => {
          try {
            return JSON.parse(l);
          } catch {
            return null;
          }
        })
        .filter(Boolean) as ECPRecord[];
    } catch {
      return [];
    }
  }

  getRecordHashes(limit: number = 1000): string[] {
    return this.getRecentRecords(limit).map((r) => r.chain.hash);
  }
}

// ─── Batch Uploader ─────────────────────────────────────────────────────────

class BatchUploader {
  private apiUrl: string;
  private apiKey: string | undefined;
  private recorder: ECPRecorder;
  private lastBatchTs: number = 0;
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor(recorder: ECPRecorder, apiUrl: string, apiKey?: string) {
    this.recorder = recorder;
    this.apiUrl = apiUrl;
    this.apiKey = apiKey;
  }

  start(intervalMs: number = 3600000) {
    this.timer = setInterval(() => this.upload(), intervalMs);
    // Also upload on start if there are pending records
    setTimeout(() => this.upload(), 5000);
  }

  stop() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  async upload(): Promise<void> {
    try {
      const records = this.recorder.getRecentRecords(1000);
      const recentRecords = records.filter((r) => r.ts > this.lastBatchTs);

      if (recentRecords.length === 0) return;

      const hashes = recentRecords.map((r) => r.chain.hash);
      const merkleRoot = this.buildMerkleRoot(hashes);

      // Compute stats
      const latencies = recentRecords.map((r) => r.step.latency_ms).filter((l) => l > 0);
      const avgLatency = latencies.length > 0 ? Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length) : 0;

      // Aggregate flags
      const flagCounts: Record<string, number> = {};
      for (const r of recentRecords) {
        for (const f of r.step.flags) {
          flagCounts[f] = (flagCounts[f] || 0) + 1;
        }
      }

      const payload = {
        agent_did: this.recorder.getDid(),
        merkle_root: merkleRoot,
        record_count: recentRecords.length,
        avg_latency_ms: avgLatency,
        batch_ts: Date.now(),
        sig: "unverified",
        ecp_version: "0.1",
        flag_counts: flagCounts,
        record_hashes: recentRecords.map((r) => ({
          id: r.id,
          hash: r.chain.hash,
          flags: r.step.flags,
        })),
      };

      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (this.apiKey) {
        headers["X-Agent-Key"] = this.apiKey;
      }

      const resp = await fetch(`${this.apiUrl}/batches`, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      });

      if (resp.ok) {
        this.lastBatchTs = Date.now();
      }
    } catch {
      // Fail-Open: batch failure never affects agent operation
    }
  }

  private buildMerkleRoot(hashes: string[]): string {
    if (hashes.length === 0) return sha256("empty");
    if (hashes.length === 1) return hashes[0];

    const next: string[] = [];
    for (let i = 0; i < hashes.length; i += 2) {
      const left = hashes[i];
      const right = i + 1 < hashes.length ? hashes[i + 1] : left;
      next.push(sha256(left + right));
    }
    return this.buildMerkleRoot(next);
  }
}

// ─── Plugin Entry Point ─────────────────────────────────────────────────────

export default function register(api: any) {
  const config: PluginConfig = api.config?.plugins?.entries?.["atlast-ecp"]?.config ?? {};

  if (config.enabled === false) {
    api.logger?.info?.("[atlast-ecp] Plugin disabled via config");
    return;
  }

  const apiUrl = config.apiUrl || process.env.ATLAST_API_URL || "https://api.llachat.com/v1";
  const apiKey = config.apiKey || process.env.ATLAST_API_KEY;
  const ecpDir = config.ecpDir || process.env.ATLAST_ECP_DIR || join(homedir(), ".ecp");
  const batchInterval = config.batchIntervalMs || 3600000; // 1 hour

  const recorder = new ECPRecorder(ecpDir);
  const uploader = new BatchUploader(recorder, apiUrl, apiKey);

  api.logger?.info?.(`[atlast-ecp] Recording to ${ecpDir} | Agent: ${recorder.getDid()}`);

  // ─── Message Hooks (passive LLM interaction capture) ────────────────────

  let pendingInteraction: PendingInteraction | null = null;

  api.registerHook(
    "message:received",
    async (event: any) => {
      try {
        pendingInteraction = {
          receivedAt: Date.now(),
          from: event.context?.from || "unknown",
          content: event.context?.content || "",
          channelId: event.context?.channelId || "unknown",
          sessionKey: event.sessionKey || "unknown",
        };
      } catch {
        // Fail-Open
      }
    },
    { name: "atlast-ecp.message-received", description: "Capture inbound message for ECP" }
  );

  api.registerHook(
    "message:sent",
    async (event: any) => {
      try {
        if (!pendingInteraction) return;

        const latencyMs = Date.now() - pendingInteraction.receivedAt;
        const input = pendingInteraction.content;
        const output = event.context?.content || "";

        if (!input || !output) {
          pendingInteraction = null;
          return;
        }

        recorder.createRecord(input, output, latencyMs);
        pendingInteraction = null;
      } catch {
        pendingInteraction = null;
        // Fail-Open
      }
    },
    { name: "atlast-ecp.message-sent", description: "Complete ECP record on response" }
  );

  // ─── Agent Tool: ecp_status ─────────────────────────────────────────────

  api.registerTool(
    {
      name: "ecp_status",
      description:
        "Show this agent's ATLAST ECP trust recording status: DID, record count, and recent activity.",
      parameters: { type: "object", properties: {}, additionalProperties: false },
      async execute() {
        const records = recorder.getRecentRecords(10);
        const totalRecords = recorder.getRecordCount();
        const did = recorder.getDid();

        const recentSummary = records
          .slice(-5)
          .map((r) => `  ${r.id} | ${new Date(r.ts).toISOString()} | ${r.step.latency_ms}ms | ${r.step.flags.join(",") || "clean"}`)
          .join("\n");

        const text = [
          `🔗 ATLAST ECP Status`,
          `  Agent DID: ${did}`,
          `  Total Records: ${totalRecords}`,
          `  Storage: ${ecpDir}`,
          `  API: ${apiUrl}`,
          `  API Key: ${apiKey ? "configured" : "not set"}`,
          ``,
          `📊 Recent Records:`,
          recentSummary || "  (no records yet)",
          ``,
          `🌐 Profile: https://llachat.com/agent/${did}`,
        ].join("\n");

        return { content: [{ type: "text", text }] };
      },
    },
    { optional: true }
  );

  // ─── Background Service (batch uploader) ────────────────────────────────

  api.registerService({
    id: "atlast-ecp-uploader",
    start: () => {
      uploader.start(batchInterval);
      api.logger?.info?.(`[atlast-ecp] Batch uploader started (interval: ${batchInterval}ms)`);
    },
    stop: () => {
      uploader.stop();
      api.logger?.info?.("[atlast-ecp] Batch uploader stopped");
    },
  });
}
