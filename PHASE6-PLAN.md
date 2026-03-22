# Phase 6: Market-Ready Polish + Standardization Prep

> **目标**: 代码零遗留 → 白皮书最终版 → 标准化文件 → 反滥用设计 → 开源发布就绪
> **原则**: 每个任务可独立验证、不引入新依赖、不与其他 section 逻辑冲突
> **生成时间**: 2026-03-22 21:45 MYT

---

## Phase 0-5 遗留任务（必须先清零）

### Section R — Residual Cleanup（8 项）

| # | 任务 | 来源 | 说明 | 验证方式 |
|---|------|------|------|---------|
| R1 | README npm 包名修正 | P5 遗留 | `atlast-ecp-ts` → `@atlast/sdk`，`sdk-ts/` → `sdk/typescript/`，npm badge URL 更新 | grep 确认零旧引用 |
| R2 | README TS SDK test count | P5 遗留 | "12 tests" → "14 tests" | 与实际一致 |
| R3 | CHANGELOG v0.8.0 补充 | P5 遗留 | 补充 TS SDK v0.2.0 npm publish、Sentry、DB integration、E2E 验证、streaming 等 P5 成果 | CHANGELOG 覆盖所有 P5 commit |
| R4 | npm-publish.yml 包名 | P5 遗留 | 检查 CI workflow 是否引用旧包名 | CI workflow 对应 @atlast/sdk |
| R5 | Go SDK import path | P5 遗留 | `sdk-go` → `sdk/go` monorepo 路径 | go.mod 和 README 一致 |
| R6 | Whitepaper Trust Score 更新 | A6 决策 | 添加说明：ATLAST 0-1000 独立标准，平台可作为综合评估维度 | EN+ZH 两版同步 |
| R7 | Whitepaper ecp_version 说明 | 审计发现 | 明确 batch protocol version "0.1" vs record format version "1.0" 区别 | 文档无歧义 |
| R8 | G1-G5 Alex 通知标记完成 | P5 遗留 | 今日对齐已覆盖 G1-G5 所有内容，标记为完成 | memory 确认 |

---

## Phase 6 新任务

### Section A — Whitepaper Final（6 项）

| # | 任务 | 说明 | 验证方式 |
|---|------|------|---------|
| A1 | ZH Whitepaper sync v2.2 内容 | ZH 版缺少 v2.2 新增的商业模式细节、工作证书 mockup、用户旅程等 | diff EN vs ZH 关键章节 |
| A2 | ZH Litepaper sync v2.2 | 同步商业模式 4 层、TAM $19B 等新增内容 | |
| A3 | Trust Score 章节更新 | 添加：ATLAST 0-1000 独立 + 平台可组合说明 + Alex 架构 70/30 示例 | EN+ZH |
| A4 | atlast_score API 字段文档 | 说明将来 API 会暴露独立 ATLAST Score（Alex 确认后） | 白皮书 §7 |
| A5 | 最终逻辑审查 | 全文扫描确保零矛盾、零 placeholder、版本号一致 | 自动化 grep |
| A6 | PDF 生成 + Desktop 备份 | 最终版 PDF + 复制到 Desktop | 文件存在 |

### Section B — Standardization Prep（7 项）

| # | 任务 | 说明 | 验证方式 |
|---|------|------|---------|
| B1 | OpenAPI 3.1 Spec | ECP Server 所有端点的正式 OpenAPI spec（YAML） | swagger-cli validate |
| B2 | JSON Schema — ECP Record | ECP Record v1.0 minimal + v0.1 full 的 JSON Schema | ajv validate 通过 |
| B3 | JSON Schema — Batch Payload | Batch submit payload 的 JSON Schema | ajv validate 通过 |
| B4 | JSON Schema — Webhook Payload | Webhook attestation.anchored 的 JSON Schema | ajv validate 通过 |
| B5 | ECP-SPEC.md v2.1 更新 | 同步 Phase 5 变更：in_hash/out_hash、a2a_delegated flag、ecp_version 说明 | spec 反映实际代码 |
| B6 | IETF I-D 格式评估 | 研究 IETF Internet-Draft 格式要求，写转换计划（不实际转换） | 评估文档 |
| B7 | W3C VC/DID 映射 | ECP ↔ W3C Verifiable Credentials、did:ecp ↔ W3C DID 的对应关系文档 | 映射表 |

### Section C — Anti-Abuse Framework（6 项）

| # | 任务 | 说明 | 验证方式 |
|---|------|------|---------|
| C1 | Rate Limiting 设计文档 | Per-agent、per-IP 的频率限制策略（SDK 端 + Server 端） | 设计文档 |
| C2 | Anomaly Detection 规范 | 异常模式定义：批量垃圾记录、fake records、时间戳造假 | 规范文档 |
| C3 | Trust Score Anti-Gaming | 防操纵设计：sybil attack、flag manipulation、cherry-picking batches | 设计文档 |
| C4 | Self-Deploy Economics | 开源后自部署场景的 gas abuse 防护设计 | 设计文档 |
| C5 | Abuse Detection 代码实现 | Server 端基础异常检测（batch 频率、record_count 异常、时间戳跳跃） | 测试覆盖 |
| C6 | SDK 端 rate limiting | 客户端节流：最小 batch 间隔、最大 records/batch | 测试覆盖 |

### Section D — Code Quality（8 项）

| # | 任务 | 说明 | 验证方式 |
|---|------|------|---------|
| D1 | Coverage → 80% | Python SDK 从 63% 提升到 80%+ | codecov 报告 |
| D2 | Server test 扩展 | 从 16 → 30+ tests：覆盖 cron、discovery、metrics、error paths | pytest 通过 |
| D3 | TS SDK test 扩展 | 从 14 → 25+ tests：覆盖 batch、wrap、track、identity | jest 通过 |
| D4 | Streaming E2E test | Mock streaming response → 验证 _RecordedStream 正确记录 | 测试通过 |
| D5 | Go SDK 基础测试 | 现有 test 能否通过？补充缺失测试 | go test 通过 |
| D6 | Type hints 完善 | Python SDK 所有公开 API 100% type hints | mypy --strict 无 error |
| D7 | Security audit | pip-audit + npm audit + dependency 版本检查 | 零 critical/high |
| D8 | Error messages 国际化准备 | 所有 user-facing error 用常量定义，方便将来 i18n | grep 确认 |

### Section E — Documentation（6 项）

| # | 任务 | 说明 | 验证方式 |
|---|------|------|---------|
| E1 | SDK Quick Start 更新 | 反映 v0.8.0 所有新功能：wrap streaming、adapters、CLI commands | README 准确 |
| E2 | Server API Reference | 所有 endpoint 的请求/响应格式文档（基于 OpenAPI B1） | 文档完整 |
| E3 | Deployment Guide | Railway 部署、环境变量、Postgres/Redis 配置说明 | 新用户可跟随部署 |
| E4 | Architecture Decision Records | 关键架构决策的 ADR（Commit-Reveal、单向 Push、fail-open 等） | ADR 文档 |
| E5 | Migration Guide 0.7→0.8 | Breaking changes、新 API、deprecated API 说明 | 文档 |
| E6 | 中文 README | README.zh-CN.md 同步最新状态 | 链接有效 |

### Section F — Alex 对齐收尾（3 项）

| # | 任务 | 说明 | 验证方式 |
|---|------|------|---------|
| F1 | Trust Score 算法对齐 | 与 Alex 对齐 ATLAST 0-1000 完整算法：α=0.45 behavioral + β=0.35 consistency + γ=0.20 transparency | 双方 memory 一致 |
| F2 | atlast_score API 字段 | 与 Alex 讨论是否在 profile API 暴露独立 ATLAST Score | Boss 决策 |
| F3 | HMAC fail-closed 切换计划 | 与 Alex 约定切换时间点和测试方案 | 计划文档 |

---

## 执行顺序（逻辑依赖图）

```
Phase 1 — 遗留清零（R1-R8）
  ↓ 零遗留状态
Phase 2 — 并行执行
  ├── A1-A6 白皮书最终版（依赖 R6 Trust Score 更新）
  ├── B1-B4 JSON Schema + OpenAPI（独立）
  ├── D1-D8 代码质量（独立）
  └── F1-F3 Alex 对齐（独立）
  ↓
Phase 3 — 依赖上游
  ├── B5-B7 标准化文件（依赖 B1-B4 schema）
  ├── C1-C6 反滥用（依赖 D1-D2 测试基础）
  └── E1-E6 文档（依赖 B1 OpenAPI）
  ↓
Phase 4 — 最终验证
  └── 全局一致性检查 + Alex 互验 + Boss 审阅
```

---

## 优先级排序（建议执行顺序）

### Week 1 — 遗留清零 + 基础
1. **R1-R8**（遗留清零）— 0.5 天
2. **B1-B4**（OpenAPI + JSON Schema）— 1 天
3. **D1-D4**（Coverage + 测试扩展）— 1.5 天
4. **F1**（Trust Score 算法对齐）— 0.5 天

### Week 2 — 白皮书 + 标准化
5. **A1-A6**（白皮书最终版）— 1.5 天
6. **B5-B7**（ECP-SPEC 更新 + IETF/W3C 评估）— 1 天
7. **E1-E6**（文档完善）— 1 天

### Week 3 — 反滥用 + 收尾
8. **C1-C6**（Anti-Abuse Framework）— 2 天
9. **D5-D8**（Go SDK + type hints + audit）— 1 天
10. **F2-F3**（Alex 对齐收尾）— 0.5 天
11. **最终验证** — 0.5 天

---

## 任务总数

| Section | 数量 | 说明 |
|---------|------|------|
| R — 遗留清零 | 8 | Phase 0-5 遗留 |
| A — 白皮书最终版 | 6 | 包含 Trust Score 更新 |
| B — 标准化准备 | 7 | OpenAPI + JSON Schema + IETF/W3C |
| C — 反滥用框架 | 6 | 设计 + 实现 |
| D — 代码质量 | 8 | Coverage + 测试 + 安全 |
| E — 文档 | 6 | 用户文档 + ADR |
| F — Alex 对齐 | 3 | Trust Score + HMAC |
| **合计** | **44** | |

---

## 完成标准

1. ✅ Phase 0-5 遗留任务全部清零（R1-R8）
2. ✅ 白皮书 EN+ZH 最终版，零矛盾零 placeholder
3. ✅ OpenAPI 3.1 + 3 个 JSON Schema 文件
4. ✅ ECP-SPEC v2.1 反映所有实际代码
5. ✅ Python SDK coverage ≥ 80%
6. ✅ Server tests ≥ 30
7. ✅ TS SDK tests ≥ 25
8. ✅ Anti-Abuse 设计文档 + 基础实现
9. ✅ 零 critical/high security vulnerability
10. ✅ 所有文档和 README 准确反映当前状态
11. ✅ Trust Score 0-1000 算法与 Alex 完全对齐
12. ✅ IETF/W3C 提交评估文档完成

---

## 逻辑碰撞检查矩阵

| 任务 | 可能冲突 | 防护措施 |
|------|---------|---------|
| A3 Trust Score 更新 | F1 Alex 算法对齐 | F1 先做 → A3 基于共识写 |
| B1 OpenAPI | 实际 Server 端点 | 从代码自动生成，不手写 |
| B2-B4 JSON Schema | 实际 payload 格式 | 从 INTERFACE-CONTRACT.md 生成 |
| C5 Abuse detection | D2 Server tests | D2 先写基础测试 → C5 加检测逻辑 |
| C6 SDK rate limiting | 现有 batch scheduler | 不修改 batch.py 核心逻辑，只加 throttle 层 |
| R6 Whitepaper 更新 | A3 Trust Score 章节 | R6 只加一句说明，A3 做完整重写 |
| E1 Quick Start | R1 包名修正 | R1 先做 → E1 引用正确包名 |

---

*Version: 1.0 | Created: 2026-03-22 21:45 MYT*
