# Phase 4 — ATLAST Protocol: Production-Ready 详细规划

**起始日期**: 2026-03-21
**目标**: 从 MVP 进入 Production-Ready 状态（完成度 60% → 85%）
**前置条件**: Phase 0-3 ✅, Railway 分离 ✅

---

## Phase 4 总览

```
Phase 4 = 6 个 Section (A-F)

A. Railway 分离收尾          [3 tasks]     ← 今天完成
B. ECP Server 功能补全       [12 tasks]    ← 核心开发
C. Anchor Cron 自动化        [5 tasks]     ← 让锚定真正跑起来
D. 安全加固                  [8 tasks]     ← 生产环境必须
E. Base Mainnet 切换         [6 tasks]     ← Sepolia → Base
F. E2E 集成测试              [7 tasks]     ← 质量保障
                              ─────────
                              41 tasks total
```

---

## Section A: Railway 分离收尾 (3 tasks)

> 目标: 确保分离后的遗留问题全部关闭

| ID | Task | 依赖 | 预估 |
|----|------|------|------|
| A1 | `api.weba0.com` SSL 证书确认生效 | 无 | 5min |
| A2 | 更新 RAILWAY-SEPARATION-PLAN.md 状态为 COMPLETED | A1 | 5min |
| A3 | 更新 memory + AGENTS.md 中所有 Railway 引用（项目名 `llachat` 替代 `atlast-ecp-backend`） | A2 | 10min |

**逻辑闭环**: A 完成后，所有文档/记忆/代码中不再有旧项目名引用。

---

## Section B: ECP Server 功能补全 (12 tasks)

> 目标: 把 ECP Server 从"只有 anchor + webhook"的骨架变成完整的 ECP 参考服务器
> 
> **重要**: SDK repo (`atlast-ecp`) 里已有一个 Reference Server (`/server/`)，包含 agents/batches/insights/leaderboard 路由。
> ECP Server (`atlast-ecp-server`) 是 Railway 生产服务。两者关系：
> - Reference Server = 开源参考实现（开发者自建用）
> - ECP Server = 我们的生产部署（含 EAS 锚定 + LLaChat 对接）
> 
> **原则**: ECP Server 只做 EAS 锚定 + Webhook + Discovery + 公开 API。
> 不做 agent 注册/batch CRUD（那是 LLaChat 或 Reference Server 的事）。

| ID | Task | 依赖 | 预估 | 说明 |
|----|------|------|------|------|
| B1 | 添加 `GET /v1/attestations/{batch_id}` | 无 | 30min | 查询单个 batch 的链上证明（从 LLaChat API 拉取 + 缓存） |
| B2 | 添加 `GET /v1/attestations` (列表) | B1 | 30min | 查询所有已锚定 attestation（分页） |
| B3 | 添加 `GET /v1/verify/{attestation_uid}` | 无 | 45min | 链上验证：给一个 UID，返回 EAS 链上数据是否匹配 |
| B4 | 添加 `POST /v1/verify/merkle` | 无 | 30min | 离线验证：给 merkle_root + records，验证 Merkle 树 |
| B5 | 添加 structlog JSON 格式化 | 无 | 15min | 生产日志结构化 |
| B6 | 添加 Sentry 集成 | B5 | 20min | 错误监控 |
| B7 | 添加 `/metrics` Prometheus endpoint | 无 | 30min | anchor 成功/失败/延迟指标 |
| B8 | 添加 CORS 配置（只允许 `llachat.com` + `weba0.com`） | 无 | 10min | 当前是 `allow_origins=["*"]`，需收紧 |
| B9 | 添加 rate limiting（slowapi） | 无 | 20min | 公开端点限流 |
| B10 | 添加 `GET /v1/stats` | 无 | 20min | 统计：总锚定数、24h 锚定数、平均延迟 |
| B11 | README.md 完善 | B1-B4 | 20min | API 文档 + 部署指南 |
| B12 | OpenAPI schema 导出 + 验证 | B1-B4 | 15min | FastAPI 自动生成，确认准确 |

**逻辑闭环检查**:
- B1-B2 只读 LLaChat API → 不会写入 LLaChat DB ✅
- B3-B4 是纯验证，不涉及任何写操作 ✅
- B8 收紧 CORS 不影响 internal endpoints（internal 用 token 认证不走 CORS）✅
- B9 rate limit 只加在公开端点，不影响 `/v1/internal/*` ✅

---

## Section C: Anchor Cron 自动化 (5 tasks)

> 目标: 让 EAS 锚定真正自动运行，不再需要手动触发
> 
> **当前状态**: `/v1/internal/anchor-now` 存在但没有定时调用。
> **方案选择**:
> - 方案 1: Railway Cron Job（单独 service，定时 HTTP 调用）
> - 方案 2: 内置 APScheduler（进程内定时）
> - 方案 3: Railway Cron Service + curl
> 
> **选择方案 2**（APScheduler），原因：
> - 不需要额外 Railway service（省钱）
> - 进程内调度，无网络延迟
> - 失败重试逻辑更灵活

| ID | Task | 依赖 | 预估 | 说明 |
|----|------|------|------|------|
| C1 | 添加 APScheduler 依赖 | 无 | 10min | `requirements.txt` 加 `apscheduler>=3.10` |
| C2 | 实现 anchor cron job（每小时整点） | C1 | 30min | 在 `lifespan` 中启动 scheduler，调用 `_anchor_pending()` |
| C3 | 添加 cron 配置化（`ANCHOR_INTERVAL_MINUTES` env var） | C2 | 15min | 默认 60min，可调整 |
| C4 | 添加 cron 执行日志 + 失败告警 | C2 | 20min | 连续 3 次失败 → Sentry alert |
| C5 | 添加 `/v1/internal/cron-status` endpoint | C2 | 15min | 返回：上次执行时间、结果、下次执行时间 |

**逻辑闭环检查**:
- C2 调用的是已有的 `_anchor_pending()`，复用 B 的所有逻辑 ✅
- C3 env var 不与任何现有 env var 冲突（检查过 Atlas + LLaChat 所有 vars）✅
- C5 是只读端点，不触发 anchor ✅
- Cron 在 server 启动时自动开始，Railway restart 后自动恢复 ✅

---

## Section D: 安全加固 (8 tasks)

> 目标: 生产环境安全基线

| ID | Task | 依赖 | 预估 | 说明 |
|----|------|------|------|------|
| D1 | `/v1/internal/*` 所有端点统一 token 认证 | 无 | 20min | 当前 `anchor-status` 无认证，需加上 |
| D2 | HTTPS 强制（redirect HTTP → HTTPS） | A1 | 10min | Railway 默认支持，确认配置 |
| D3 | Request body size limit（10MB） | 无 | 10min | 防止大 payload 攻击 |
| D4 | 敏感 env var 审计 | 无 | 15min | 确认 `EAS_PRIVATE_KEY` 不在日志/响应中泄露 |
| D5 | 添加 `X-Request-ID` header（请求追踪） | 无 | 15min | 每个请求生成唯一 ID，写入日志 |
| D6 | 添加 security headers（CSP, HSTS, X-Frame-Options） | 无 | 15min | FastAPI middleware |
| D7 | Webhook payload 签名验证（HMAC-SHA256） | 无 | 30min | Atlas → LLaChat webhook 加 `X-ECP-Signature` header |
| D8 | 依赖安全扫描（`pip-audit`） | 无 | 15min | 检查已知 CVE |

**逻辑闭环检查**:
- D1 不影响公开端点（`/health`, `/.well-known/ecp.json`）✅
- D7 需要 Alex 在 LLaChat 端也加验证逻辑 → **标记为需对齐** ✅
- D4 确保 `write_attestation()` 的 private key 不 log ✅
- D6 security headers 不影响 API JSON 响应 ✅

---

## Section E: Base Mainnet 切换 (6 tasks)

> 目标: 从 Sepolia testnet 迁移到 Base mainnet
> 
> **前提**: EAS 在 Base mainnet 合约地址相同（`0x4200000000000000000000000000000000000021`）
> **风险**: mainnet 需要真实 ETH 付 gas（约 $0.001/attestation on Base）
> **决策点**: 需要 Boss 确认 mainnet 钱包的 funding

| ID | Task | 依赖 | 预估 | 说明 |
|----|------|------|------|------|
| E1 | 生成 mainnet EAS 钱包（新 private key） | 无 | 10min | 不复用 testnet key |
| E2 | 在 Base mainnet 注册 EAS Schema | E1 | 20min | 用 `scripts/register_eas_schema.py` |
| E3 | 测试 mainnet attestation（1 笔） | E2 | 15min | 确认 gas 费用 + 成功率 |
| E4 | 更新 ECP Server env vars（切换 chain） | E3 | 10min | `EAS_CHAIN=base`, 新 key + schema UID |
| E5 | 更新 `.well-known/ecp.json` 响应 | E4 | 10min | chain_id 从 84532 → 8453 |
| E6 | 更新 SDK 默认链配置 | E4 | 15min | `atlast-ecp` SDK 的 EAS 验证默认指向 mainnet |

**逻辑闭环检查**:
- E1 新 key 不影响 testnet 历史数据 ✅
- E2 新 schema UID 需同步给 Alex（更新 LLaChat 的 EAS 显示链接）→ **标记为需对齐** ✅
- E4 切换后旧 testnet attestation 仍可通过 Sepolia explorer 验证 ✅
- E6 SDK 更新不 break 旧版本（向后兼容）✅
- **⚠️ BLOCKER**: 需要 Boss 给 mainnet 钱包转 ETH（约 0.01 ETH 够用很久）

---

## Section F: E2E 集成测试 (7 tasks)

> 目标: 验证完整链路——从 SDK 上传 batch 到链上锚定再到 LLaChat 展示
> 
> **测试环境**: 生产环境（Sepolia 或 Base，取决于 E 是否完成）

| ID | Task | 依赖 | 预估 | 说明 |
|----|------|------|------|------|
| F1 | SDK → LLaChat: 上传 batch 测试 | 无 | 30min | 用 `atlast-ecp` SDK 创建并上传 batch |
| F2 | LLaChat → Atlas: pending-batches 拉取测试 | F1 | 15min | 确认 F1 的 batch 出现在 pending list |
| F3 | Atlas: anchor 执行测试 | F2 | 20min | 手动触发 `/v1/internal/anchor-now`，确认 EAS 成功 |
| F4 | Atlas → LLaChat: batch-anchored 回调测试 | F3 | 15min | 确认 batch 状态变为 `anchored` |
| F5 | Atlas → LLaChat: webhook 触发测试 | F3 | 15min | 确认 LLaChat 创建 WorkCertificate + feed |
| F6 | LLaChat 前端: certificate 展示验证 | F5 | 15min | 浏览器检查 agent profile 页面 |
| F7 | 全链路自动化测试脚本 | F1-F6 | 45min | `test_e2e_full_chain.py` 一键跑完 F1-F5 |

**逻辑闭环检查**:
- F1-F6 是线性依赖链，每一步都验证上一步的输出 ✅
- F7 不修改任何代码，只是将 F1-F6 串联成脚本 ✅
- F3 调用 anchor 时用 `INTERNAL_TOKEN` 认证，和生产 cron 路径一致 ✅
- F5 webhook 用 `ECP_WEBHOOK_TOKEN`，和生产路径一致 ✅

---

## 执行顺序 + 依赖关系图

```
Week 1 (Day 1-2):
  A1 → A2 → A3                    [收尾，今天完成]
  B5 → B6                         [日志+监控先行]
  B8, B9                          [安全基础]
  C1 → C2 → C3 → C4 → C5         [cron 上线]

Week 1 (Day 3-4):
  B1 → B2                         [attestation 查询]
  B3, B4                          [验证端点]
  D1, D3, D4, D5, D6              [安全加固]
  D8                              [依赖扫描]

Week 1 (Day 5):
  B7, B10                         [metrics + stats]
  D2, D7                          [HTTPS + webhook 签名]
  B11, B12                        [文档]

Week 2 (Day 1-2):
  E1 → E2 → E3 → E4 → E5 → E6   [Base Mainnet, 需 Boss 确认]

Week 2 (Day 3-5):
  F1 → F2 → F3 → F4 → F5 → F6 → F7  [E2E 测试]
```

---

## 需与 Alex 对齐的事项（Phase 4 中）

| 事项 | Section | 紧急度 |
|------|---------|--------|
| D7: webhook 加 HMAC 签名 → Alex 需要加验证逻辑 | D7 | 低（可后续补） |
| E2: mainnet schema UID → Alex 更新 EAS explorer 链接 | E2 | 切换时 |
| F6: 前端展示验证 → 需 Alex 确认 certificate 页面正常 | F6 | 测试时 |

---

## 不做清单（避免范围蔓延）

以下明确 **不在 Phase 4**:
- ❌ Framework Adapters（LangChain/CrewAI/AutoGen）→ Phase 5
- ❌ AIP/ASP/ACP 子协议 → Phase 7
- ❌ Enterprise Dashboard → Phase 8
- ❌ 区块链锚定去中心化（多链）→ Phase 7
- ❌ Go SDK → Phase 5
- ❌ Reference Server 功能补全 → Phase 5（SDK repo 里的 server/）
- ❌ IETF/W3C 标准提交 → Phase 6

---

## 完成标准

Phase 4 完成 = 以下全部为 true:
1. ✅ `api.weba0.com` 可访问（SSL 生效）
2. ✅ Anchor cron 每小时自动执行
3. ✅ 安全加固 8 项全部完成
4. ✅ Base Mainnet 上线（或 Boss 决定延后）
5. ✅ E2E 全链路测试通过
6. ✅ 所有 Alex 对齐事项关闭
7. ✅ README + API docs 完善
