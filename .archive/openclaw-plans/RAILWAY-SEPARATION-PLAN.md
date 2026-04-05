# Railway 分离计划 — ATLAST ECP Server 独立部署

**日期**: 2026-03-20
**状态**: ✅ COMPLETED (2026-03-21)
**风险等级**: 中（涉及 EAS worker 迁移 + webhook 路由变更）
**预计时间**: 2-3 小时（含测试）

---

## 1. 当前架构（分离前）

```
Railway Project: "atlast-ecp-backend" (7c7ebca5)
├── Service: llachat-backend (62c993ac)
│   ├── FastAPI app (Alex 的 LLaChat 路由 + ECP 混合路由)
│   ├── ARQ Worker (trust score + leaderboard + EAS anchor)
│   ├── services/eas.py (EAS 链上锚定)
│   ├── services/ecp_webhook.py (webhook 发送器)
│   ├── services/crypto.py (Ed25519 + Merkle)
│   ├── routes/internal.py (webhook 接收端)
│   ├── routes/batches.py (batch CRUD)
│   └── workers/tasks.py (anchor_pending_batches cron)
├── PostgreSQL: llachat DB (metro.proxy.rlwy.net:31329)
└── Redis: llachat cache (shortline.proxy.rlwy.net:47214)

域名: api.llachat.com → llachat-backend service
```

**关键发现**：EAS/ECP 代码全部混在 Alex 的 llachat-backend 里，没有独立服务。

---

## 2. 目标架构（分离后）

```
Railway Project A: "llachat" (原 project，改名)
├── Service: llachat-backend (原 service，不动)
│   ├── FastAPI app (纯 LLaChat 路由)
│   ├── ARQ Worker (trust score + leaderboard 只)
│   ├── routes/internal.py (webhook 接收端，不变)
│   └── 移除: services/eas.py, services/ecp_webhook.py, workers/anchor_pending_batches
├── PostgreSQL: llachat DB (不动)
└── Redis: llachat cache (不动)

域名: api.llachat.com → llachat-backend (不变)

Railway Project B: "atlast-ecp" (新建)
├── Service: ecp-server
│   ├── ECP Reference Server (FastAPI, 从 /tmp/atlast-ecp/server/)
│   ├── EAS 锚定 Worker (anchor_pending_batches)
│   ├── Webhook 发送器 (fire_attestation_webhook)
│   ├── .well-known/ecp.json discovery endpoint
│   └── 未来: ATLAST Proxy, Enterprise features
├── PostgreSQL: ecp DB (新建，独立)
└── Redis: ecp cache (新建，独立)

域名: ecp.atlast.io 或 api.atlast.io → ecp-server (新域名)
```

---

## 3. 需要迁移的代码清单

### 从 Alex backend 移出到 Atlas ECP Server

| 文件 | 功能 | 影响 |
|------|------|------|
| `services/eas.py` | EAS 链上锚定（write_attestation） | **核心移出** |
| `services/ecp_webhook.py` | Webhook 发送（fire_attestation_webhook） | **核心移出** |
| `services/crypto.py` | Ed25519 签名验证 + Merkle proof | **保留副本在 Alex**（他需要验签） |
| `workers/tasks.py` 的 `anchor_pending_batches` | 每小时 EAS 锚定 cron | **移出** |
| `scripts/register_eas_schema.py` | EAS schema 注册脚本 | **移出** |
| `config.py` 的 EAS_* / ECP_* 设置 | EAS 配置 | **移出** |

### 保留在 Alex backend（不动）

| 文件 | 功能 | 原因 |
|------|------|------|
| `routes/internal.py` | Webhook 接收端 | **LLaChat 需要接收 webhook 来创建 cert + feed** |
| `routes/batches.py` | Batch CRUD | **LLaChat 展示用**（读 DB） |
| `routes/agents.py` | Agent 注册/查询 | **LLaChat 核心功能** |
| `routes/certificate.py` | Certificate 查询 | **LLaChat 展示用** |
| `routes/verify.py` | 公开验证页 | **LLaChat 前端用** |
| `services/trust_score.py` | Trust Score 计算 | **Alex 私有算法** |
| `services/crypto.py` | 签名验证 | **batch upload 验签需要** |
| `workers/tasks.py` 的 `recalculate_trust_score` | 定时算分 | **Alex 的 worker** |
| `workers/tasks.py` 的 `refresh_leaderboard` | 刷新排行榜 | **Alex 的 worker** |
| `workers/tasks.py` 的 `take_score_snapshot` | 每日快照 | **Alex 的 worker** |

---

## 4. 数据库分离策略

### 方案：共享 DB（读），独立 DB（写）

**Atlas ECP Server 需要读取 Alex DB 的表：**
- `batches`（读取 pending batches 做锚定）
- `agents`（读取 agent DID + public_key）

**Atlas ECP Server 需要写入 Alex DB 的表：**
- `batches`（更新 attestation_uid, eas_tx_hash, upload_status）

**⚠️ 关键问题**：anchor_pending_batches 直接读写 Alex 的 `batches` 表。

### 解决方案（两个选项）

**选项 A：Atlas 直连 Alex DB（简单但耦合）**
- Atlas ECP Server 用只读+写 `batches` 的权限连 Alex DB
- 优点：零数据迁移，立即可用
- 缺点：两个服务共享一个 DB，不够干净

**选项 B：API 驱动（干净但需要新端点）**
- Atlas ECP Server 调 Alex API 获取 pending batches：`GET /v1/internal/pending-batches`
- 锚定后调 Alex API 更新状态：`POST /v1/internal/batch-anchored`
- 优点：完全解耦，各管各的 DB
- 缺点：Alex 要加 2 个内部端点

**🔴 推荐选项 B（API 驱动）**：长期正确，虽然多 2 个端点但架构干净。

---

## 5. Webhook 流向变更

### 当前流向（自己调自己）
```
Alex backend (anchor cron) 
→ EAS 链上成功 
→ fire_webhook → POST https://api.llachat.com/v1/internal/ecp-webhook
→ Alex backend (internal.py) 接收 → 创建 cert + feed
```

### 新流向（Atlas 调 Alex）
```
Atlas ECP Server (anchor cron)
→ 调 Alex API: GET /v1/internal/pending-batches
→ EAS 链上成功
→ 调 Alex API: POST /v1/internal/batch-anchored (更新 batch 状态)
→ fire_webhook → POST https://api.llachat.com/v1/internal/ecp-webhook
→ Alex backend (internal.py) 接收 → 创建 cert + feed (不变)
```

---

## 6. 详细执行步骤

### Phase A：准备（Atlas 做，不影响线上）

| 步骤 | 内容 | 预计 |
|------|------|------|
| A1 | 在 Railway 新建 project "atlast-ecp" | 5min |
| A2 | 新建 PostgreSQL + Redis 服务 | 5min |
| A3 | 基于 `/tmp/atlast-ecp/server/` 改造 ECP Server，加入 EAS worker + webhook sender | 1h |
| A4 | 加入 `anchor_pending_batches` cron（调 Alex API 而非直连 DB） | 30min |
| A5 | 新建 `.well-known/ecp.json` endpoint | 10min |
| A6 | 配置域名 `api.atlast.io` 或 `ecp.atlast.io` | 15min |
| A7 | 设置 env vars: `EAS_PRIVATE_KEY`, `EAS_SCHEMA_UID`, `EAS_CHAIN`, `ECP_WEBHOOK_URL`, `ECP_WEBHOOK_TOKEN`, `LLACHAT_API_URL`, `LLACHAT_INTERNAL_TOKEN` | 10min |

### Phase B：Alex 配合（Alex 做）

| 步骤 | 内容 | 预计 |
|------|------|------|
| B1 | 新增 `GET /v1/internal/pending-batches`（返回 pending batches，auth: internal token） | 30min |
| B2 | 新增 `POST /v1/internal/batch-anchored`（更新 batch 状态，auth: internal token） | 30min |
| B3 | 从 `workers/tasks.py` 移除 `anchor_pending_batches` cron | 10min |
| B4 | 移除 `services/eas.py` 和 `services/ecp_webhook.py`（Atlas 不再需要这些） | 10min |
| B5 | 保留 `services/crypto.py`（Alex 继续用于验签） | 0min |
| B6 | 保留 `config.py` 的 `ECP_WEBHOOK_TOKEN`（接收端不变） | 0min |
| B7 | Railway project 改名："atlast-ecp-backend" → "llachat" | 5min |
| B8 | 移除不再需要的 env vars: `EAS_PRIVATE_KEY`, `EAS_SCHEMA_UID`, `EAS_CHAIN`, `ECP_WEBHOOK_URL` | 5min |

### Phase C：切换（同时做）

| 步骤 | 内容 | 预计 |
|------|------|------|
| C1 | Atlas deploy ECP Server 到新 Railway project | 10min |
| C2 | 验证 ECP Server health | 5min |
| C3 | Alex deploy 移除 anchor cron 的版本 | 10min |
| C4 | 手动触发一次 anchor cron（Atlas 侧），验证完整链路 | 10min |

### Phase D：验证（全面测试）

| 步骤 | 测试 | 预期 |
|------|------|------|
| D1 | Alex `GET /v1/health` | ✅ 正常 |
| D2 | Atlas `GET /health` (ecp server) | ✅ 正常 |
| D3 | SDK `atlast run` → batch upload → api.llachat.com | ✅ batch 存入 |
| D4 | Atlas anchor cron → EAS 链上 → webhook → Alex cert 创建 | ✅ 完整链路 |
| D5 | LLaChat 前端 leaderboard | ✅ 显示正常 |
| D6 | LLaChat 前端 agent profile | ✅ 显示正常 |
| D7 | LLaChat 前端 feed | ✅ 显示正常 |
| D8 | LLaChat 前端 verify cert | ✅ 可验证 |
| D9 | SDK 签名验证（用新 crypto_pub_key） | ✅ 通过 |
| D10 | Alex `/v1/internal/ecp-webhook` 接收 | ✅ 创建 cert + draft |
| D11 | Atlas `.well-known/ecp.json` | ✅ 返回 discovery info |

---

## 7. 深度影响分析 — 可能的"后遗症"

### 🔴 HIGH RISK

| # | 风险 | 影响 | 防护 |
|---|------|------|------|
| H1 | EAS_PRIVATE_KEY 迁移 | 链上签名用的钱包私钥，必须从 Alex env 拷贝到 Atlas env，不能同时存在两处 | 先 Atlas 设好 → 测试通过 → 再从 Alex 删除 |
| H2 | Anchor cron 重叠 | 切换期间如果两边都有 anchor cron，同一个 batch 可能被锚定两次（链上重复，浪费 gas） | 先 Alex 停 cron → 再 Atlas 启动 cron |
| H3 | SDK `ATLAST_API_URL` 硬编码 `api.llachat.com` | SDK 的 batch upload 直接打到 Alex backend。分离后 batch 仍然存在 Alex DB，anchor worker 在 Atlas 侧需要读到 | 选项 B 方案解决：Atlas 通过 API 读 Alex pending batches |

### 🟡 MEDIUM RISK

| # | 风险 | 影响 | 防护 |
|---|------|------|------|
| M1 | Webhook token 不匹配 | 如果 Atlas 的 `ECP_WEBHOOK_TOKEN` 和 Alex 的接收端 `settings.ECP_WEBHOOK_TOKEN` 不一致 → 401 | 分离时同步换成随机 token |
| M2 | Network latency | 之前 webhook 是 localhost 自调，分离后是跨 Railway project HTTP 调用 | Railway 内网很快（<10ms），可接受 |
| M3 | Redis 缓存 key 冲突 | Alex 用 Redis 缓存 leaderboard 等。Atlas 用独立 Redis，无冲突 | 独立 Redis 实例 |
| M4 | DB 表 `batches` 的归属 | Batch 数据在 Alex DB，但 anchor worker 在 Atlas。Atlas 需要读写 batch 状态 | 选项 B：API 端点解耦 |

### 🟢 LOW RISK

| # | 风险 | 影响 | 防护 |
|---|------|------|------|
| L1 | `.well-known/ecp.json` 域名 | Discovery endpoint 需要新域名。SDK 文档/README 需要更新 | 新增，不影响现有 |
| L2 | GitHub Actions CI | atlast-ecp repo 的 CI 测试不受影响（独立的） | 无需改 |
| L3 | PyPI/npm 包 | SDK 包不受影响。`ATLAST_API_URL` 仍然指向 `api.llachat.com` | SDK 保持不变 |

---

## 8. SDK 侧需要的改动

**重点：SDK 不需要改。**

- `ATLAST_API_URL` 仍然指向 `api.llachat.com`（batch upload 打到 Alex backend）
- Agent 注册仍然在 Alex backend
- Cert 验证仍然在 Alex backend
- Atlas ECP Server 是**后台服务**，SDK 不直接调它

**唯一变化**：如果未来 SDK 要调 Atlas 的 `.well-known/ecp.json` 或独立 API，再加新 env var。

---

## 9. 环境变量清单

### Atlas ECP Server（新）
```env
# Database
DATABASE_URL=postgresql+asyncpg://...  (新 Railway Postgres)
REDIS_URL=redis://...  (新 Railway Redis)

# EAS (从 Alex env 迁移)
EAS_PRIVATE_KEY=0x...  (链上签名私钥)
EAS_SCHEMA_UID=0xa67da7e880b3fe643f0e12b754c6048fc0a0bad0ed9a932ac85a5ebf6bd9326e
EAS_CHAIN=sepolia  (后续改 mainnet)
EAS_STUB_MODE=false

# Webhook (Atlas 发 → Alex 收)
ECP_WEBHOOK_URL=https://api.llachat.com/v1/internal/ecp-webhook
ECP_WEBHOOK_TOKEN=<新随机 token，替换 ecp-internal-2026>

# LLaChat Internal API (新，用于读 pending batches)
LLACHAT_API_URL=https://api.llachat.com
LLACHAT_INTERNAL_TOKEN=<新 service-to-service token>
```

### Alex backend（修改）
```env
# 新增
INTERNAL_TOKEN=<同上 LLACHAT_INTERNAL_TOKEN>

# 修改
ECP_WEBHOOK_TOKEN=<新随机 token，与 Atlas 同步>

# 删除
EAS_PRIVATE_KEY  (不再需要)
EAS_SCHEMA_UID   (不再需要)
EAS_CHAIN        (不再需要)
EAS_STUB_MODE    (不再需要)
ECP_WEBHOOK_URL  (不再需要，Atlas 会调 Alex，不是 Alex 调自己)
```

---

## 10. 回滚方案

如果分离后出现问题，30 秒回滚：

1. Alex 恢复 `anchor_pending_batches` cron（git revert + deploy）
2. Alex 恢复 EAS env vars
3. Atlas ECP Server 停止 cron

**不需要数据回滚**（两边都操作的是 Alex DB 的 batch 数据，通过 API 操作没有破坏性）

---

## 11. 需要 Alex 配合的 Checklist

- [ ] 新增 `GET /v1/internal/pending-batches` 端点
- [ ] 新增 `POST /v1/internal/batch-anchored` 端点
- [ ] 从 `workers/tasks.py` 移除 `anchor_pending_batches`
- [ ] 删除 `services/eas.py` 和 `services/ecp_webhook.py`
- [ ] 更新 `ECP_WEBHOOK_TOKEN` 为新随机值
- [ ] 新增 `INTERNAL_TOKEN` env var
- [ ] Railway project 改名
- [ ] 移除旧 EAS env vars
- [ ] 配合完整链路测试

---

## 12. 需要 Boss 决定的事项

1. **域名选择**：`api.atlast.io` 还是 `ecp.atlast.io`？（需要 DNS 设置）
2. **DB 方案确认**：选项 B（API 驱动）可以吗？
3. **执行时间**：今晚做还是明天白天做？（建议低峰期）
4. **EAS_PRIVATE_KEY**：钱包私钥目前在 Alex 的 Railway env 里，需要拷贝给我。你有这个值吗？

---

## 13. 深度检查结论

经过逐文件检查 Alex 的 llachat-platform backend，确认：

- ✅ `services/crypto.py` Alex 需要保留（batch 验签用）
- ✅ `routes/internal.py` Alex 需要保留（webhook 接收端）
- ✅ `routes/batches.py` Alex 需要保留（前端展示）
- ✅ `services/trust_score.py` 完全是 Alex 的，不受影响
- ✅ `workers/tasks.py` 的其他 3 个 cron 不受影响
- ✅ SDK 不需要任何改动
- ✅ 前端不需要任何改动
- ⚠️ `EAS_PRIVATE_KEY` 必须安全迁移
- ⚠️ Anchor cron 切换必须原子化（先停旧 → 再启新）
- ⚠️ Webhook token 必须同步更换
