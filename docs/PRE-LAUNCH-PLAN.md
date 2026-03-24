# Pre-Launch Plan — C1-C8 详细任务拆解

> 创建时间: 2026-03-24 18:50 MYT
> 状态: 执行中
> 约束: C6 需 Boss 授权才开始

---

## 总览

| ID | 任务 | 子任务数 | 预估 | 状态 |
|----|------|---------|------|------|
| C2 | CI Smoke Test | 6 | 1h | 🔲 |
| C1 | Sentry Alert Coverage | 8 | 45min | 🔲 |
| C4 | Onboarding E2E Test | 10 | 2h | 🔲 |
| C8 | PR Template + Issue Templates | 4 | 15min | 🔲 |
| C3 | Dashboard Enhancement | 7 | 2h | 🔲 |
| C5 | Multi-Agent Stress Test | 8 | 2h | 🔲 |
| C7 | Issue #1 Behavioral Drift | 9 | 3h | 🔲 |
| C6 | 24h Production Monitor | — | 24h | ⏸️ 等Boss授权 |

**总计: 52 子任务, ~11h 开发**

---

## C2. CI Smoke Test (GitHub Actions)

**目的**: 每次 push + 每日定时自动验证 production 健康

| # | 子任务 | 状态 |
|---|--------|------|
| C2.1 | 创建 `.github/workflows/smoke.yml` — trigger: push to main + schedule cron daily 08:00 UTC | 🔲 |
| C2.2 | Job 1: `health-check` — curl /v1/health, 验证 200 + `status: healthy` | 🔲 |
| C2.3 | Job 2: `discovery-check` — curl /.well-known/ecp.json, 验证 schema_uid 一致 | 🔲 |
| C2.4 | Job 3: `stats-check` — curl /v1/stats, 验证 200 + JSON 结构正确 | 🔲 |
| C2.5 | Job 4: `sdk-unit-tests` — pip install + pytest sdk/python, npm ci + jest sdk/typescript | 🔲 |
| C2.6 | 本地验证 workflow 语法正确 (act 或 push 观察), commit | 🔲 |

**产出**: `.github/workflows/smoke.yml`
**验证**: push 后 GitHub Actions 绿色

---

## C1. Sentry Alert Coverage

**目的**: production 所有关键路径报错都被 Sentry 捕获 + 告警

**现状审计**:
- ✅ Sentry init 在 main.py (SENTRY_DSN 环境变量)
- ⚠️ 只有 cron 3次连续失败才 capture — 覆盖不够
- ❌ anchor.py 无 capture
- ❌ webhook.py 无 capture
- ❌ EAS write_attestation 失败无 capture
- ❌ DB 操作失败无 capture

| # | 子任务 | 状态 |
|---|--------|------|
| C1.1 | 创建 `server/app/services/monitoring.py` — 封装 `capture_error(e, context={})` helper | 🔲 |
| C1.2 | `anchor.py` — _anchor_pending() 和 _anchor_super_batch() 的 except 块加 capture | 🔲 |
| C1.3 | `webhook.py` — fire_attestation_webhook() 失败加 capture | 🔲 |
| C1.4 | `eas.py` — write_attestation() 失败加 capture (链上交易失败是最关键的) | 🔲 |
| C1.5 | `database.py` — DB session 异常加 capture | 🔲 |
| C1.6 | `main.py` — 全局 exception handler 加 capture (FastAPI middleware) | 🔲 |
| C1.7 | 写测试: mock sentry_sdk.capture_exception 被调用 | 🔲 |
| C1.8 | 验证: 部署后手动触发一个错误, 确认 Sentry Dashboard 收到 | 🔲 |

**产出**: 新文件 `monitoring.py`, 修改 4 个文件, 新测试
**验证**: 所有关键路径都有 try/except + capture

---

## C4. Onboarding E2E Test

**目的**: 模拟新用户从 pip install 到链上验证的完整旅程

| # | 子任务 | 状态 |
|---|--------|------|
| C4.1 | 创建 `server/tests/test_e2e_onboarding.py` 骨架 | 🔲 |
| C4.2 | Test 1: `test_sdk_install` — 验证 `import atlast` 成功, 版本 = 0.9.0 | 🔲 |
| C4.3 | Test 2: `test_init_creates_config` — `atlast.init()` 创建 config + 密钥对 | 🔲 |
| C4.4 | Test 3: `test_register_agent` — POST /v1/agents/register → 获得 ak_live_xxx | 🔲 |
| C4.5 | Test 4: `test_record_entries` — 用 SDK record() 记录 5 条, 验证本地 .jsonl | 🔲 |
| C4.6 | Test 5: `test_upload_batch` — upload 到 server, 验证 201 + batch_id 返回 | 🔲 |
| C4.7 | Test 6: `test_anchor_trigger` — POST /v1/anchor/now, 验证 batch 被锚定 | 🔲 |
| C4.8 | Test 7: `test_verify_attestation` — GET /v1/attestations/, 验证新 attestation 存在 | 🔲 |
| C4.9 | Test 8: `test_stats_incremented` — GET /v1/stats, 数字正确递增 | 🔲 |
| C4.10 | 集成到 CI: 可选 flag `--e2e` 跑完整流程 (不在普通 pytest 中自动触发) | 🔲 |

**产出**: `server/tests/test_e2e_onboarding.py`
**验证**: `pytest server/tests/test_e2e_onboarding.py -v` 全绿
**注意**: E2E 测试用 stub mode 或 test server, 不消耗 mainnet gas

---

## C8. PR Template + Issue Templates

**目的**: 开源 contributor 标准化

| # | 子任务 | 状态 |
|---|--------|------|
| C8.1 | 创建 `.github/PULL_REQUEST_TEMPLATE.md` | 🔲 |
| C8.2 | 创建 `.github/ISSUE_TEMPLATE/bug_report.md` | 🔲 |
| C8.3 | 创建 `.github/ISSUE_TEMPLATE/feature_request.md` | 🔲 |
| C8.4 | Commit + push | 🔲 |

**产出**: 3 个模板文件
**验证**: GitHub 上新建 Issue/PR 时看到模板

---

## C3. Dashboard Enhancement

**目的**: 完善 Dashboard 功能 + 加入 Super-batch 展示

**现状审计**:
- ✅ Dashboard 已用真实 API (`api.weba0.com/v1`)
- ✅ 有 Overview / Records / Batches / Chain / Settings 页面
- ❌ 无 Super-batch 展示
- ❌ 无 error handling UI (loading/empty/error states 不完善)
- ❌ 无自动刷新

| # | 子任务 | 状态 |
|---|--------|------|
| C3.1 | 审计 dashboard/app.js 所有 API 调用, 列出缺失端点 | 🔲 |
| C3.2 | 新增 Super-batch 页面: `loadSuperBatches()` — 调 GET /v1/super-batches/ 列表 | 🔲 |
| C3.3 | Super-batch 详情: 点击展开 → 显示 batch 列表 + merkle tree 可视化 | 🔲 |
| C3.4 | Overview 页加 "Super-batches" 卡片 (数量 + 最近一条) | 🔲 |
| C3.5 | 改善 error states: API 失败显示友好错误 + retry 按钮 | 🔲 |
| C3.6 | 加 auto-refresh: Overview 每 30s 刷新一次 (可在 Settings 关闭) | 🔲 |
| C3.7 | 测试: 手动验证所有页面正常渲染 + commit | 🔲 |

**产出**: 更新 `dashboard/app.js` + `dashboard/index.html`
**验证**: 本地打开 Dashboard, 所有页面正常, Super-batch 页面可用

---

## C5. Multi-Agent Stress Test

**目的**: 证明 50k 用户 Day-1 的 server 承载力

| # | 子任务 | 状态 |
|---|--------|------|
| C5.1 | 创建 `server/tests/test_stress_multi_agent.py` 骨架 | 🔲 |
| C5.2 | ST-A: 注册 10 个 agent, 每个 record 50 条, 并发 upload (asyncio) | 🔲 |
| C5.3 | ST-B: 10 agent 同时 upload → 触发 super-batch (≥5 batches) | 🔲 |
| C5.4 | ST-C: 验证 super-batch merkle tree — 每个 batch 的 inclusion_proof 可独立验证 | 🔲 |
| C5.5 | ST-D: 验证所有 webhook 发出 (mock webhook endpoint, 检查收到数量) | 🔲 |
| C5.6 | ST-E: 连续 3 轮, 检查 DB 无泄漏/无重复 attestation | 🔲 |
| C5.7 | 性能指标收集: 并发响应时间/super-batch耗时/吞吐量 records/s | 🔲 |
| C5.8 | Pass 标准验证 + 结果写入 `docs/stress-test-results.md` | 🔲 |

**产出**: 测试脚本 + 结果文档
**验证**: 全部 ST-A 到 ST-E 通过, 性能指标达标

---

## C7. Issue #1 — Behavioral Drift Detection

**目的**: 检测 agent 行为模式随时间漂移

| # | 子任务 | 状态 |
|---|--------|------|
| C7.1 | 读 GitHub Issue #1 完整描述, 确认需求范围 | 🔲 |
| C7.2 | 设计 drift 算法: 对比 agent 最近 N 个 batch 的特征向量 (token_count 均值/方差, tool_call 分布, confidence 均值) | 🔲 |
| C7.3 | 创建 `server/app/services/drift.py` — `compute_drift_score(agent_id) → DriftResult` | 🔲 |
| C7.4 | DriftResult: `{ drift_score: float 0-1, drift_detected: bool, changed_dimensions: [...], baseline_window: int, current_window: int }` | 🔲 |
| C7.5 | 在 `GET /v1/agents/{agent_id}` 响应中加 `drift_status` 字段 | 🔲 |
| C7.6 | 新端点: `GET /v1/agents/{agent_id}/drift` — 返回完整 drift 分析 | 🔲 |
| C7.7 | 在 ECP record 的 `confidence.uncertain_parts` 中标记 drift 相关异常 | 🔲 |
| C7.8 | 写测试: test_drift_detection.py — 正常 agent 无 drift / 异常 agent 有 drift | 🔲 |
| C7.9 | 更新 API docs + Close Issue #1 | 🔲 |

**产出**: `drift.py` + 新端点 + 测试 + Issue closed
**验证**: drift 检测逻辑正确, 测试通过

---

## C6. 24h Production Monitor ⏸️

> **需 Boss 授权后才开始**
> 依赖: C1-C5, C7, C8 全部完成后
> 执行: 24h 每 6h 检查一次

---

## 执行顺序

```
Phase A (并行, ~2h):
  ├── C2 CI Smoke Test
  ├── C8 PR + Issue Templates  
  └── C1 Sentry Coverage

Phase B (串行, ~4h):
  ├── C4 Onboarding E2E
  └── C3 Dashboard Enhancement

Phase C (串行, ~5h):
  ├── C5 Multi-Agent Stress Test
  └── C7 Behavioral Drift

Phase D (等Boss授权):
  └── C6 24h Monitor
```

**记忆更新规则**: 每个 C 任务完成后立即 memory_store 进度。
