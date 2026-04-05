# Phase 5 — ATLAST Protocol: Market-Ready

**版本**: v3.0 (基于 2026-03-21 全面对齐后的状态)  
**起始日期**: 2026-03-22  
**预估周期**: 4 周  
**目标**: Production-Ready → Market-Ready（开源发布前最后一个开发 Phase）

---

## 当前基线状态（Phase 4 完成后）

| 组件 | 版本 | 状态 |
|------|------|------|
| Python SDK | v0.7.0 (PyPI) | 424 tests, 20 模块 |
| TS SDK | v0.1.1 (GitHub only) | 12 tests, 9 模块, npm 未发布 |
| ECP Server | v1.0.0 | 11 endpoints, Railway `api.weba0.com` |
| EAS | Base Sepolia | chain_id: 84532 |
| Monorepo | `atlast-ecp` | `sdk/python/` + `sdk/typescript/` + `sdk/go/` + `server/` |
| Alex 对齐 | ✅ 完成 | 24 题交叉验证通过, 6 bugs 修复 |

### Phase 4 推迟到 Phase 5 的技术债

| 来源 | 问题 | 对应 Task |
|------|------|-----------|
| P4-B7 | Prometheus metrics 未实现（已在 requirements） | D10 |
| P4 审计 | slowapi 在 requirements 但从未 import | D7 |
| P4 审计 | Sentry SDK 在 requirements 但未配置 DSN | D9 |
| P4 审计 | Webhook fire-and-forget，无重试 | D8 |
| P4 审计 | SDK 5 个高级模块未做生产级测试 | H1-H7 |
| P3 遗留 | TS SDK npm 未发布 | E7 |
| P3 遗留 | SDK README 6 个问题未修复 | C6 |

---

## Phase 5 总览：9 Sections / 79 Tasks

```
Section A — Base Mainnet 切换           [ 7 tasks]   BLOCKER: Boss 转 ETH
Section B — Framework Adapters 生产化   [15 tasks]   LangChain/CrewAI/AutoGen
Section C — SDK 质量提升               [12 tasks]   测试/文档/DX/发布
Section D — ECP Server 增强            [12 tasks]   DB/监控/限流/重试
Section E — TS SDK 功能补齐            [ 8 tasks]   对齐 Python SDK
Section F — 开源社区增强               [ 5 tasks]   CI/Roadmap
Section G — Alex 接口收尾              [ 6 tasks]   契约文档/通知
Section H — SDK 高级功能验证           [ 9 tasks]   proxy/MCP/a2a/otel/scanner
Section I — 架构文档与 Spec 更新        [ 7 tasks]   ARCHITECTURE.md/ECP-SPEC v2/清理
                                        ─────────
                                        81 tasks
```

---

## Section A: Base Mainnet 切换 [7 tasks]

> Sepolia testnet → Base mainnet，生产级链上锚定  
> ⚠️ BLOCKER: A2 需要 Boss 转 ~0.01 ETH (Base chain, ~$25)

| ID | Task | 依赖 | 时间 | 说明 |
|----|------|------|------|------|
| A1 | 生成 mainnet 专用钱包 (新 private key) | - | 10m | 不复用 testnet key |
| A2 | Boss 转 0.01 ETH 到 mainnet 钱包 (Base) | A1 | 等Boss | 提供地址 + 转账指南 |
| A3 | Base mainnet 注册 EAS Schema | A2 | 20m | `scripts/register_schema.py` |
| A4 | 测试 mainnet attestation (1 笔) | A3 | 15m | 验证 gas 费 + 成功率 |
| A5 | 更新 ECP Server Railway env vars | A4 | 10m | EAS_CHAIN=base, 新 key + schema |
| A6 | 保留 Sepolia 配置为 fallback 文档化 | A5 | 15m | 开发/测试环境切换说明 |
| A7 | E2E 验证 mainnet 全链路 | A5 | 20m | SDK → LLaChat → anchor → webhook |

**修改范围**: ECP Server env vars only  
**不影响**: SDK 代码 / LLaChat 代码  
**Alex 通知**: A5 完成后通过 G5 同步新 schema UID

---

## Section B: Framework Adapters 生产化 [15 tasks]

> 3 个 adapter 从骨架 → 可用 + 测试 + 文档  
> 当前: `sdk/python/atlast_ecp/adapters/` 有 3 个文件, `test_adapters.py` 有基础测试

### B-I: LangChain [5 tasks]

| ID | Task | 依赖 | 时间 | 说明 |
|----|------|------|------|------|
| B1 | 审计 `langchain.py` vs LangChain v0.3+ API | - | 30m | 检查 BaseCallbackHandler 接口变更 |
| B2 | 修复不兼容 + 完善 ATLASTCallbackHandler | B1 | 45m | on_llm_start/end/error + tool_call |
| B3 | 单元测试 (mock LLM, 验证 ECP record 字段) | B2 | 30m | ≥5 tests |
| B4 | 示例 `examples/langchain_demo.py` | B3 | 30m | 可独立运行的完整示例 |
| B5 | README LangChain 集成指南 | B4 | 20m | 3 步上手 |

### B-II: CrewAI [5 tasks]

| ID | Task | 依赖 | 时间 |
|----|------|------|------|
| B6 | 审计 `crewai.py` vs CrewAI v0.80+ API | - | 30m |
| B7 | 修复不兼容 | B6 | 45m |
| B8 | 单元测试 (mock crew execution) | B7 | 30m |
| B9 | 示例 `examples/crewai_demo.py` | B8 | 30m |
| B10 | README CrewAI 集成指南 | B9 | 20m |

### B-III: AutoGen [5 tasks]

| ID | Task | 依赖 | 时间 |
|----|------|------|------|
| B11 | 审计 `autogen.py` vs AutoGen v0.4+ API | - | 30m |
| B12 | 修复不兼容 | B11 | 45m |
| B13 | 单元测试 (mock agent chat) | B12 | 30m |
| B14 | 示例 `examples/autogen_demo.py` | B13 | 30m |
| B15 | README AutoGen 集成指南 | B14 | 20m |

**修改范围**: `sdk/python/atlast_ecp/adapters/` + `tests/` + `examples/`  
**不影响**: ECP Server / LLaChat / core SDK API  
**逻辑闭环**: adapter 只调已有 `create_record()` / `BatchUploader`，不引入新 API ✅

---

## Section C: SDK 质量提升 [12 tasks]

> SDK 从 "能用" → "专业级开源项目"

| ID | Task | 依赖 | 时间 | 说明 |
|----|------|------|------|------|
| C1 | 测试覆盖率报告 (`pytest --cov`) | - | 15m | 424 tests, 查 coverage % |
| C2 | 补充 edge case 测试到 >90% 覆盖率 | C1 | 45m | 空输入/超大数据/Unicode/并发 |
| C3 | 错误消息改善 (所有 ValueError 加上下文) | - | 30m | |
| C4 | CLI `atlast --help` + `--version` 完善 | - | 20m | |
| C5 | CHANGELOG.md 补全 (v0.1.0 → v0.7.0) | - | 30m | |
| C6 | PyPI README 更新 (long_description) | - | 15m | 修复 P3 遗留的 6 个问题 |
| C7 | GitHub Release v0.7.1 (含 monorepo 重构) | C5 | 10m | |
| C8 | `pip install atlast-ecp` 冷启动测试 (新 venv) | C7 | 15m | 验证无遗漏依赖 |
| C9 | API Reference 文档 (pdoc 或 mkdocs) | - | 45m | 35 个公开函数 |
| C10 | SDK v0.8.0 版本升级 + PyPI 发布 | B,H | 20m | 含 adapter + 高级功能验证 |
| C11 | `signals.py` vs ECP Server 输出对齐检查 | - | 20m | 确保 trust signal 计算一致 |
| C12 | ECP-SPEC.md 更新至 v2.0 | - | 30m | 反映 Phase 4 全部变更 |

**修改范围**: `sdk/python/` + 根目录文档  
**C10 依赖 B+H**: 确保所有 adapter + 高级功能验证后才发版 ✅

---

## Section D: ECP Server 增强 [12 tasks]

> ECP Server 从无状态 proxy → 有自己数据的独立服务 + 生产级运维

| ID | Task | 依赖 | 时间 | 说明 |
|----|------|------|------|------|
| D1 | Railway `atlast-ecp` 项目添加 PostgreSQL | - | 15m | Railway Postgres plugin |
| D2 | 数据模型: attestations 表 (SQLAlchemy) | D1 | 30m | attestation_uid, agent_did, merkle_root, tx_hash, created_at |
| D3 | Alembic migrations 初始化 | D2 | 20m | |
| D4 | anchor 成功后写入本地 DB | D3 | 30m | `_anchor_pending()` 双写 |
| D5 | `GET /v1/attestations` 查本地 DB + 分页 | D4 | 30m | offset/limit, fallback LLaChat |
| D6 | Railway 添加 Redis (缓存 stats) | - | 30m | |
| D7 | **slowapi rate limiting** | - | 25m | 公开 60/min, internal 无限 |
| D8 | **Webhook 重试** (指数退避, 最多 3 次) | - | 30m | 当前 fire-and-forget |
| D9 | **Sentry DSN 配置** | - | 15m | 免费 tier |
| D10 | **Prometheus `/metrics`** | - | 30m | anchor_total, errors, latency |
| D11 | **Anchor 并发保护** (Redis SETNX 锁) | D6 | 30m | 防止多实例竞争 |
| D12 | 部署 + E2E 验证全部增强 | D1-11 | 30m | |

**修改范围**: `server/` only  
**不影响**: SDK / LLaChat  
**D7 修复 P4 遗留**: slowapi 在 requirements 但未用 ✅  
**D8 修复风险**: webhook 丢失 → 重试 ✅  
**D9 修复 P4 遗留**: sentry 在 requirements 但未配 ✅  
**D10 修复 P4-B7 推迟**: prometheus 在 requirements 但未实现 ✅

---

## Section E: TS SDK 功能补齐 [8 tasks]

> TS SDK v0.1.1 → v0.2.0, 与 Python SDK 核心功能对齐

| ID | Task | 依赖 | 时间 | 说明 |
|----|------|------|------|------|
| E1 | 添加 `verify.ts` (签名 + Merkle 验证) | - | 45m | 必须用 Phase 4 验证过的算法 |
| E2 | 添加 `insights.ts` (trust signals) | - | 45m | |
| E3 | 添加 LangChain.js adapter | - | 45m | `adapters/langchain.ts` |
| E4 | 测试 (vitest) | E1-3 | 45m | |
| E5 | **Merkle 三方一致性测试** (TS vs Python vs Server) | E1 | 20m | 关键! |
| E6 | 更新 package.json exports + README | E1-3 | 20m | |
| E7 | **npm publish v0.2.0** | E4-6 | 15m | 需要 npm token |
| E8 | TS SDK E2E test (实际调 api.weba0.com) | E7 | 30m | |

**修改范围**: `sdk/typescript/` only  
**E5 关键**: 防止第三个 Merkle 实现不一致 ✅  
**E7 BLOCKER**: 需要 npm token (Boss 提供或 Alex 协助)

---

## Section F: 开源社区增强 [5 tasks]

> 已有: CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md, issue templates, CI  
> 只做增强, 不重复创建

| ID | Task | 依赖 | 时间 | 说明 |
|----|------|------|------|------|
| F1 | CI 添加 lint (ruff) + type check (mypy) | - | 30m | |
| F2 | CI 添加 coverage 上传 (codecov) | - | 20m | |
| F3 | 公开 Roadmap (GitHub Projects 或 README) | - | 30m | Phase 6-8 方向 |
| F4 | `examples/` 目录整理 + README | B | 20m | |
| F5 | GitHub Discussions 开启 | - | 5m | |

---

## Section G: Alex 接口收尾 [6 tasks]

> 关闭所有 Phase 3-4 遗留对齐项, 输出永久参考文档

| ID | Task | 依赖 | 时间 | 说明 |
|----|------|------|------|------|
| G1 | 通知 Alex: HMAC 验证已在双方实现 | - | 15m | 确认双方都在验证 |
| G2 | 确认 Alex 已支持 in_hash/out_hash 字段 | - | 10m | P3 遗留 |
| G3 | 共享 SDK API Reference 给 Alex | C9 | 15m | |
| G4 | 确认 LLaChat certificate 页面展示正确 | - | 15m | |
| G5 | Mainnet schema UID + chain_id 同步给 Alex | A3 | 10m | Alex 更新 explorer 链接 |
| G6 | **INTERFACE-CONTRACT.md** 最终版 | G1-5 | 30m | 永久参考文档 |

**修改范围**: 文档 + 通知, 不单方面改 LLaChat ✅  
**G6 输出**: Phase 6 合规审计的基础文档

---

## Section H: SDK 高级功能验证 [9 tasks]

> SDK 有 5 个高级模块从未做过生产级测试  
> 原则: 能修的修, 不能修的标记 experimental

| ID | Task | 依赖 | 时间 | 说明 |
|----|------|------|------|------|
| H1 | `proxy.py` E2E 测试 (atlast proxy/run) | - | 45m | Layer 0 核心承诺 |
| H2 | `proxy.py` 修复发现的问题 | H1 | 30m | |
| H3 | `mcp_server.py` 审计 + 基本测试 | - | 45m | MCP tools 注册验证 |
| H4 | `mcp_server.py` 修复或标记 experimental | H3 | 30m | |
| H5 | `a2a.py` 多方验证逻辑测试 | - | 30m | handoff/orphan/blame |
| H6 | `otel_exporter.py` OTel span → ECP record | - | 30m | |
| H7 | `openclaw_scanner.py` session log 扫描测试 | - | 30m | fixture .jsonl |
| H8 | 所有 experimental 模块添加 warning | H1-7 | 20m | `warnings.warn()` |
| H9 | README 标注 stable vs experimental | H8 | 15m | |

**修改范围**: `sdk/python/` only  
**H1-H2 最重要**: proxy 是 Layer 0 ("1 条命令接入") 的核心承诺 ✅

---

## Section I: 架构文档与 Spec 更新 [5 tasks]

> Monorepo 重构后, 需要清晰的架构文档  
> (旧 reference server 已删除, 只有 production server)

| ID | Task | 依赖 | 时间 | 说明 |
|----|------|------|------|------|
| I1 | `ARCHITECTURE.md` — monorepo 结构 + 组件关系 | - | 30m | |
| I2 | `server/README.md` 更新 (部署指南) | I1 | 15m | Railway root directory = server/ |
| I3 | ECP-SERVER-SPEC.md 升级 v2.0 | - | 45m | 反映 Phase 4 全部端点 |
| I4 | Merkle 算法一致性最终验证 (3方) | - | 20m | Python SDK / TS SDK / Server (代码对比+测试向量) |
| I5 | `.well-known/ecp.json` discovery 文档化 | - | 15m | |
| I6 | Archive 旧 `willau95/atlast-ecp-server` repo | - | 5m | 设为 archived, README 指向 monorepo |
| I7 | Railway 清理: 确认无多余 Postgres/Redis 实例 | D12 | 10m | P3 遗留 R9 |

---

## 执行计划 (4 周)

```
Week 1:
├── Day 1-2: A1-A7 (Mainnet) + G1-G2 (Alex 通知)
├── Day 3-4: B1-B5 (LangChain) + H1-H2 (Proxy 验证)
└── Day 5:   B6-B10 (CrewAI) + C1-C2 (覆盖率)

Week 2:
├── Day 1-2: B11-B15 (AutoGen) + H3-H5 (MCP/a2a)
├── Day 3-4: H6-H9 (otel/scanner/标注) + C3-C6 (SDK DX)
└── Day 5:   D1-D3 (Server DB 初始化) + I1-I2 (架构文档)

Week 3:
├── Day 1-2: D4-D8 (Server DB + 重试 + 限流)
├── Day 3-4: D9-D12 (Sentry/Prometheus/并发/E2E) + E1-E3 (TS SDK)
└── Day 5:   E4-E8 (TS 测试 + npm 发布) + C11 (signals 对齐)

Week 4:
├── Day 1-2: C7-C10 (SDK 发布 v0.8.0) + I3-I5 (Spec v2)
├── Day 3-4: F1-F5 (开源增强) + G3-G6 (Alex 收尾)
└── Day 5:   C12 (Spec) + 全局 E2E 验证 + Phase 5 收尾
```

---

## 跨 Section 依赖图

```
A3 ──→ G5 (mainnet schema UID → Alex)
B  ──→ C10 (adapters → SDK v0.8.0 发布)
B  ──→ F4 (adapters → examples 整理)
C1 ──→ C2 (覆盖率报告 → 补测试)
C9 ──→ G3 (API docs → 共享给 Alex)
D1 ──→ D2 → D3 → D4 → D5 (DB 链式依赖)
D6 ──→ D11 (Redis → 分布式锁)
E1 ──→ E5 (TS verify → 三方一致性)
G1-5 → G6 (全部确认 → INTERFACE-CONTRACT.md)
H  ──→ C10 (高级功能验证 → SDK v0.8.0 发布)
I1 ──→ I2 (架构文档 → server README)
```

---

## Phase 5 不做清单 (边界)

| 不做 | 原因 | 计划 Phase |
|------|------|-----------|
| AIP/ASP/ACP 子协议 | Phase 7 范围 | 7 |
| Enterprise Dashboard | Phase 8 范围 | 8 |
| Go SDK 完善 | 骨架已有, 不紧急 | 6+ |
| 多链 (Polygon/ETH mainnet) | Phase 7 范围 | 7 |
| IETF/W3C 标准提交 | Phase 6 范围 | 6 |
| 商业化 / 付费 tier | Phase 8 范围 | 8 |
| LLaChat 平台功能 | Alex 职责 | - |
| EU AI Act 白皮书 | Phase 6 范围 | 6 |
| Insights Layer B/C | Phase 6+ 范围 | 6+ |
| OpenClaw Node.js Plugin 完善 | 已有骨架, 非 P5 优先 | 6 |
| ECP Dashboard MVP | Phase 8 范围 | 8 |
| X/Twitter 验证推文格式 | 营销, 非开发 | 6 |

---

## 跨 Phase 逻辑碰撞检查

### Phase 4 → Phase 5 (无碰撞 ✅)
| P4 完成项 | P5 依赖方式 | 碰撞风险 |
|-----------|-----------|---------|
| ECP Server 11 endpoints | D section 在此基础上增强, 不删除任何端点 | 无 ✅ |
| Merkle 算法 SDK=Server | I4 做四方最终验证 | 无 ✅ |
| api.weba0.com SSL | A/D/E 全部使用此域名 | 无 ✅ |
| INTERNAL_TOKEN 对齐 | G section 文档化, 不再改值 | 无 ✅ |
| Monorepo 重构 | 所有 P5 task 基于新目录结构 | 无 ✅ |

### Phase 5 → Phase 6 (无碰撞 ✅)
| P5 输出 | P6 消费 | 碰撞风险 |
|---------|--------|---------|
| Base Mainnet 锚定 | EU AI Act 合规审计需要 mainnet 数据 | 无, P5 先完成 ✅ |
| ECP-SERVER-SPEC v2.0 | IETF/W3C 标准提交基础 | 无, P5 写完 P6 提交 ✅ |
| INTERFACE-CONTRACT.md | 合规审计引用 | 无 ✅ |
| Framework Adapters | 合规需覆盖主流框架 | 无 ✅ |
| stable/experimental 标注 | 合规只覆盖 stable | 无 ✅ |

### Phase 5 → Phase 7 (无碰撞 ✅)
| P5 输出 | P7 消费 | 碰撞风险 |
|---------|--------|---------|
| a2a.py 验证 (H5) | AIP 子协议基础 | 无, H5 只验证不重写 ✅ |
| ECP Server 自有 DB (D) | ASP 数据存储扩展 | 无, D 建基础 P7 扩展 ✅ |
| Base Mainnet (A) | 多链扩展从 Base 开始 | 无 ✅ |

### Phase 5 内部 Section 碰撞检查 (无碰撞 ✅)
| Section 对 | 修改范围重叠? | 碰撞? |
|-----------|-------------|-------|
| A vs D | A 改 env vars, D 改代码 | 无 ✅ |
| B vs H | B 改 adapters/, H 改高级模块 | 无 ✅ |
| B vs C | B 先完成, C10 再发版 | 顺序正确 ✅ |
| C vs I | C12 改 ECP-SPEC, I3 改 SERVER-SPEC | 不同文件 ✅ |
| D vs A | D 加 DB/限流, A 改链配置 | 无 ✅ |
| E vs B | E 改 TS, B 改 Python | 不同语言 ✅ |
| G vs 全部 | G 只通知+文档 | 无 ✅ |

---

## Boss 决策项

| # | 事项 | Section | 说明 |
|---|------|---------|------|
| 1 | 转 ~0.01 ETH (Base chain) 到 mainnet 钱包 | A2 | BLOCKER, ~$25 |
| 2 | Sentry 账号 (免费 tier OK?) | D9 | 或用其他监控 |
| 3 | npm token | E7 | TS SDK 发布需要 |

---

## 完成标准 (13 项全部为 true)

| # | 标准 | Section |
|---|------|---------|
| 1 | Base Mainnet ≥1 笔成功 attestation | A |
| 2 | LangChain/CrewAI/AutoGen adapter 各 ≥5 tests 通过 | B |
| 3 | SDK 测试覆盖率 >90% | C |
| 4 | `atlast proxy` E2E 测试通过 | H |
| 5 | ECP Server 有自己的 PostgreSQL + attestation 记录 | D |
| 6 | ECP Server 有 rate limiting + webhook 重试 + Sentry | D |
| 7 | TS SDK v0.2.0 发布 (含 verify + insights) | E |
| 8 | CI 有 lint + type check + coverage | F |
| 9 | INTERFACE-CONTRACT.md 已写并与 Alex 确认 | G |
| 10 | ECP-SERVER-SPEC v2.0 发布 | I |
| 11 | 所有 SDK 模块标注 stable / experimental | H |
| 12 | PyPI v0.8.0 + npm v0.2.0 发布 | C+E |
| 13 | Merkle 算法三方一致 (Py SDK / TS SDK / Server) | I |
