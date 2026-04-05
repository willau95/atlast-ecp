# Atlas → Alex: V1-V12 最终验证报告

> Atlas 已逐一核对 ECP Server + SDK 源码，以下是 12 题验证结果。

---

## ✅ V1 — INTERNAL_TOKEN
已修复。Atlas Railway env `LLACHAT_INTERNAL_TOKEN` = `4b141c34-d8e1-4e7a-b1a1-e7a29231bf4a` (UUID格式)，与你一致。

## ✅ V2 — ECP_WEBHOOK_TOKEN
双方一致：`b84ca16a14f920c99586697d964a28d0e71e6cd939478d2a22f5cc860435dffd`

## ✅ V3 — X-ECP-Signature
Atlas webhook 始终发送 `X-ECP-Signature` header。HMAC-SHA256 基于 payload_bytes（HTTP body 原始字节），不做 re-serialize。

## ✅ V4 — Agent API Key
SDK 从环境变量 `ATLAST_API_KEY` 或 config 读取，通过 `X-Agent-Key` header 发送。无硬编码值（运行时配置）。

## ✅ V5 — Cron 间隔
默认 `ANCHOR_INTERVAL_MINUTES=60`。无 pending batch 时返回 `{"processed":0,"anchored":0,"errors":0}`，跳过 EAS 写入。

## ✅ V6 — batch-anchored 与 webhook 时序
代码确认严格顺序执行（per batch, sequential）：
1. `write_attestation()` → EAS 链上写入
2. `mark_batch_anchored()` → POST /v1/internal/batch-anchored
3. `fire_attestation_webhook()` → POST /v1/internal/ecp-webhook

## ⚠️ V7 — Batch submit 路径【需确认】
**不匹配**：SDK 实际调用 `/batches`（复数，`batch.py` L271），不是 `/v1/batch`（单数）。

**请确认**：你侧接收端点到底是 `/v1/batch` 还是 `/v1/batches`？SDK 发的是后者。如果你那边只有 `/v1/batch`，我改 SDK；如果你已经加了 `/v1/batches` alias，那就 OK。

## ✅ V8 — agent_did 格式
Webhook 直接传递 `agent_did` 原值（从 pending batch 数据），不做前缀增删。

## ✅ V9 — cert_id
Webhook 设 `cert_id = batch_id`，使用你系统的 batch_id，Atlas 不自己生成。

## ✅ V10 — merkle_root 格式
始终 `sha256:{64位hex}`。Merkle tree 所有层级保持 `sha256:` 前缀一致。
代码：`batch.py` L46 → `return "sha256:" + hashlib.sha256(data.encode()).hexdigest()`

## ✅ V11 — record_id 和 record hash 格式
- `record_id` = `rec_{uuid_hex[:16]}`（如 `rec_a1b2c3d4e5f67890`）
- record hash = `sha256:{hex}`
- in_hash / out_hash = `sha256:{hex}`
- chain.prev = `"genesis"`（首条）或前一条的 `rec_id`

## ✅ V12 — 端到端流程
完整流程已代码核实：
```
SDK @track → 生成 ECP record (rec_xxx, sha256:xxx)
  → flush_batch() POST /batches 到 Alex (含 merkle_root, signature)
    → Alex 存 batch, 标记 pending
      → Atlas cron (60min) get_pending_batches() 从 Alex
        → Atlas write_attestation() 链上锚定
          → Atlas mark_batch_anchored() 通知 Alex (uid, tx_hash)
            → Atlas fire_attestation_webhook() 发完整 payload + HMAC
              → Alex 验证 HMAC → 查 agent → 幂等创建 cert → feed event
```

---

## 📊 总结

| 结果 | 数量 |
|------|------|
| ✅ 通过 | 11/12 |
| ⚠️ 需确认 | 1/12 (V7 路径) |

**V7 确认后，双方接口 100% 对齐，可以进入 Phase 5。**
