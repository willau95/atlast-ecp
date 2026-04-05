# Phase 5 — ATLAST Protocol: Market-Ready 详细规划

**起始日期**: 2026-03-21 (待 Phase 4 SSL 收尾)
**目标**: 从 Production-Ready 进入 Market-Ready 状态（完成度 85% → 95%）
**前置条件**: Phase 0-4 ✅

---

## Phase 5 总览

```
Phase 5 = 9 个 Section (A-I)

A. Base Mainnet 切换              [7 tasks]    ← Sepolia → Base 主网
B. Framework Adapters 生产化      [15 tasks]   ← LangChain/CrewAI/AutoGen
C. SDK 质量提升                   [12 tasks]   ← 测试覆盖 + 文档 + DX
D. ECP Server 增强                [12 tasks]   ← DB + Redis + 监控 + 重试 + 限流
E. TS SDK 功能补齐                [8 tasks]    ← 对齐 Python SDK
F. 开源社区准备                   [5 tasks]    ← CI增强 + Roadmap（已有模板）
G. Alex 接口收尾                  [6 tasks]    ← 遗留对齐 + 契约文档
H. SDK 高级功能验证               [9 tasks]    ← proxy/MCP/a2a/otel/scanner
I. Reference Server 与 Production Server 对齐  [5 tasks]
                                   ─────────
                                   79 tasks total
```

---

## 深度审查发现的问题（Phase 5 必须解决）

### 1. Phase 4 遗留债务
- **slowapi** 在 requirements.txt 但从未 import/使用 → 要么实现限流，要么删除
- **SENTRY_DSN** env var 未在 Railway 设置 → 无错误监控
- **Webhook 无重试逻辑** → fire-and-forget，如果 LLaChat 短暂宕机就丢失通知

### 2. SDK 中大量功能模块未被 Phase 5 覆盖
- `proxy.py` — Layer 0 透明代理（`atlast proxy` / `atlast run`）→ 从未做过生产级测试
- `mcp_server.py` — MCP Server（query/record/upload tools）→ 未完成
- `a2a.py` — Agent-to-Agent 多方验证 → 有代码但未测试
- `otel_exporter.py` — OpenTelemetry bridge → 有代码但未测试
- `openclaw_scanner.py` — OpenClaw session log scanner → 有代码但未测试
- `signals.py` — trust signal computation → 需确认与 ECP Server 一致

### 3. Reference Server（SDK repo）与 Production Server（ECP Server repo）关系不清
- Reference Server 有 agents/batches/leaderboard/insights 路由
- Production Server 有 anchor/verify/attestations/cron 路由
- **完全不同的功能集**，但都叫"ECP Server"→ 需要明确定位

### 4. Go SDK 已有骨架代码（`sdk-go/`）但 Phase 5 未包含

### 5. 社区文件已存在
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md` ✅ 已有
- `.github/ISSUE_TEMPLATE/` (bug_report + feature_request) ✅ 已有
- `.github/PULL_REQUEST_TEMPLATE.md` ✅ 已有
- `.github/workflows/` (ci.yml, publish.yml, npm-publish.yml) ✅ 已有
- **原 Phase 5 F section 大部分是重复工作**

### 6. ECP-SERVER-SPEC.md 需要更新
- v1.1 写于 Phase 3，Phase 4 新增了 anchor/verify/attestations/cron 等端点
- 需要升级为 v2.0 反映 Production Server 架构

---

## Section A: Base Mainnet 切换 (7 tasks)

> 目标: Sepolia testnet → Base mainnet，生产级链上锚定
>
> **前提**: 需要 Boss 给 mainnet 钱包转约 0.01 ETH on Base（约 $25，够锚定上千次）
> **风险**: 低（合约地址相同，只换 RPC + chain_id）

| ID | Task | 依赖 | 预估 | 说明 |
|----|------|------|------|------|
| A1 | 生成 mainnet EAS 钱包（新 private key） | 无 | 10min | 不复用 testnet key |
| A2 | Boss 转 0.01 ETH 到 mainnet 钱包（Base chain） | A1 | 等 Boss | 提供钱包地址 + 转账指南 |
| A3 | 在 Base mainnet 注册 EAS Schema | A2 | 20min | `scripts/register_eas_schema.py` |
| A4 | 测试 mainnet attestation（1 笔） | A3 | 15min | 验证 gas 费 + 成功率 |
| A5 | 更新 ECP Server env vars | A4 | 10min | `EAS_CHAIN=base`, 新 key + schema |
| A6 | 保留 Sepolia 配置为 fallback | A5 | 15min | 环境变量文档化 |
| A7 | E2E 验证 mainnet anchor 全链路 | A5 | 20min | SDK upload → anchor → webhook |

**⚠️ BLOCKER**: A2 需要 Boss 手动转 ETH

**逻辑闭环**:
- A1 新 key 与 testnet key 完全隔离 ✅
- A6 保留 Sepolia 配置方便开发/测试环境切换 ✅
- Testnet 历史数据保留在 Sepolia，不受影响 ✅
- Alex 需要知道新 mainnet schema UID → G5 处理 ✅

---

## Section B: Framework Adapters 生产化 (15 tasks)

> 目标: LangChain/CrewAI/AutoGen adapters 从骨架变成可用 + 有测试 + 有文档
>
> **当前状态**: 3 个 adapter 文件 + 1 个 `test_adapters.py`

### B-I: LangChain Adapter (5 tasks)

| ID | Task | 依赖 | 预估 |
|----|------|------|------|
| B1 | 审计 `langchain.py` 与 LangChain v0.3+ 兼容性 | 无 | 30min |
| B2 | 修复不兼容项 + 完善 callback handler | B1 | 45min |
| B3 | 单元测试（mock LLM，验证 record 字段正确性） | B2 | 30min |
| B4 | 示例 `examples/langchain_demo.py` | B3 | 30min |
| B5 | SDK README: LangChain 集成指南 | B4 | 20min |

### B-II: CrewAI Adapter (5 tasks)

| ID | Task | 依赖 | 预估 |
|----|------|------|------|
| B6 | 审计 `crewai.py` 与 CrewAI v0.80+ 兼容性 | 无 | 30min |
| B7 | 修复不兼容项 | B6 | 45min |
| B8 | 单元测试（mock crew execution） | B7 | 30min |
| B9 | 示例 `examples/crewai_demo.py` | B8 | 30min |
| B10 | SDK README: CrewAI 集成指南 | B9 | 20min |

### B-III: AutoGen Adapter (5 tasks)

| ID | Task | 依赖 | 预估 |
|----|------|------|------|
| B11 | 审计 `autogen.py` 与 AutoGen v0.4+ 兼容性 | 无 | 30min |
| B12 | 修复不兼容项 | B11 | 45min |
| B13 | 单元测试（mock agent chat） | B12 | 30min |
| B14 | 示例 `examples/autogen_demo.py` | B13 | 30min |
| B15 | SDK README: AutoGen 集成指南 | B14 | 20min |

**逻辑闭环**:
- B 只修改 SDK repo `adapters/` 目录 + tests + examples ✅
- Adapter 调用已有的 `create_record()` / `BatchUploader`，不引入新 core API ✅
- 测试用 mock，不需要真实 LLM API key ✅
- 不影响 ECP Server 或 LLaChat ✅

---

## Section C: SDK 质量提升 (12 tasks)

> 目标: SDK 从 "能用" 到 "专业级"

| ID | Task | 依赖 | 预估 | 说明 |
|----|------|------|------|------|
| C1 | 测试覆盖率报告（`pytest --cov`） | 无 | 15min | 当前 422+ tests，查 coverage % |
| C2 | 补充 edge case 测试 | C1 | 45min | 空输入/超大数据/Unicode/并发 |
| C3 | 错误消息改善（所有 ValueError 加上下文） | 无 | 30min | |
| C4 | `atlast` CLI 帮助文本 + `--version` 完善 | 无 | 20min | |
| C5 | CHANGELOG.md 补全（v0.1.0→v0.7.0） | 无 | 30min | |
| C6 | PyPI README 更新（long_description） | 无 | 15min | |
| C7 | GitHub Release v0.7.0 正式发布 | C5 | 10min | |
| C8 | `pip install atlast-ecp` 冷启动测试（新 venv） | C7 | 15min | 验证无遗漏依赖 |
| C9 | API Reference 文档生成（pdoc/mkdocs） | 无 | 45min | 35 个公开函数 |
| C10 | SDK v0.8.0 版本升级 + PyPI 发布 | B+H | 20min | 含 adapter 修复 + 高级功能验证 |
| C11 | `signals.py` 与 ECP Server `/v1/stats` 输出对齐检查 | 无 | 20min | 确保一致 |
| C12 | ECP-SPEC.md 更新至 v2.0（反映 Phase 4 变更） | 无 | 30min | |

**逻辑闭环**:
- C10 是 B + H 完成后的集成发布 ✅
- C11 确保 SDK 和 Server 的 trust signal 计算一致 ✅
- C12 规范文档与实际代码保持同步 ✅

---

## Section D: ECP Server 增强 (12 tasks)

> 目标: 从无状态 proxy 进化为有自己数据的独立服务 + 生产级监控

| ID | Task | 依赖 | 预估 | 说明 |
|----|------|------|------|------|
| D1 | 添加 PostgreSQL 到 Railway `atlast-ecp` 项目 | 无 | 15min | Railway Postgres plugin（不是手动 Docker） |
| D2 | 定义数据模型（attestations 表） | D1 | 30min | SQLAlchemy + Alembic |
| D3 | Alembic migrations 初始化 | D2 | 20min | |
| D4 | 每次 anchor 成功后写入本地 DB | D3 | 30min | 在 `_anchor_pending()` 后双写 |
| D5 | `GET /v1/attestations` 改为查本地 DB | D4 | 30min | 真正分页，fallback LLaChat API |
| D6 | 添加 Redis 到 Railway（缓存 stats + 热门查询） | 无 | 30min | |
| D7 | **实现 slowapi rate limiting**（已在 requirements 但未用） | 无 | 25min | 公开端点 60/min，internal 无限 |
| D8 | **Webhook 重试逻辑**（指数退避，最多 3 次） | 无 | 30min | 当前 fire-and-forget |
| D9 | **设置 Sentry DSN** 到 Railway env var | 无 | 15min | 或用免费 tier |
| D10 | Prometheus `/metrics` endpoint | 无 | 30min | anchor_total, errors, webhook_sent, latency |
| D11 | **Anchor 并发保护**（分布式锁或 DB flag） | D6 | 30min | 防止多实例同时 anchor 同一批 batch |
| D12 | 部署 + E2E 验证 | D1-D11 | 30min | |

**逻辑闭环**:
- D1 在 Atlas 项目加 Postgres，不动 LLaChat DB ✅
- D4 双写：先通知 LLaChat（已有），再写本地 DB（新增）✅
- D5 fallback 保证 DB 迁移期间不中断 ✅
- D7 修复 Phase 4 遗漏（slowapi 在 requirements 但未实现）✅
- D8 修复 webhook 丢失风险 ✅
- D11 防止多实例竞争 → 用 Redis SETNX 或 DB advisory lock ✅

---

## Section E: TS SDK 功能补齐 (8 tasks)

> 目标: `atlast-ecp-ts` v0.2.0 与 Python SDK 核心功能对齐

| ID | Task | 依赖 | 预估 | 说明 |
|----|------|------|------|------|
| E1 | 添加 `verify.ts`（签名 + Merkle 验证） | 无 | 45min | 必须用 Phase 4 验证过的算法 |
| E2 | 添加 `insights.ts`（trust signals 计算） | 无 | 45min | |
| E3 | 添加 LangChain.js adapter | 无 | 45min | `adapters/langchain.ts` |
| E4 | 添加 test suite（vitest） | E1-E3 | 45min | |
| E5 | Merkle 算法一致性测试（TS vs Python vs Server） | E1 | 20min | **关键：三方必须一致** |
| E6 | 更新 `package.json` exports + README | E1-E3 | 20min | |
| E7 | npm publish v0.2.0 | E4-E6 | 15min | |
| E8 | TS SDK E2E test（实际调 ECP Server） | E7 | 30min | |

**逻辑闭环**:
- E1 Merkle 算法已在 Phase 4 验证 Python SDK = ECP Server ✅
- E5 确保 TS SDK 也一致（三方校验）✅
- E7 不 break v0.1.x（新增 exports，不删除旧 API）✅

---

## Section F: 开源社区增强 (5 tasks)

> **注意**: 审查发现 SDK repo 已有 CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md,
> issue templates, PR template, CI workflows。原计划大部分是重复工作。
> 只做增强项。

| ID | Task | 依赖 | 预估 | 说明 |
|----|------|------|------|------|
| F1 | CI 增强：添加 lint（ruff）+ type check（mypy） | 无 | 30min | 现有 ci.yml 只跑 pytest |
| F2 | CI 增强：添加 coverage 上传（codecov） | 无 | 20min | |
| F3 | 公开 Roadmap（GitHub Projects 或 README section） | 无 | 30min | 展示 Phase 6-8 方向 |
| F4 | `examples/` 目录整理（README + 目录结构） | B | 20min | |
| F5 | GitHub Discussions 开启 | 无 | 5min | |

**逻辑闭环**:
- F1-F2 增强现有 CI，不替换 ✅
- F4 依赖 B section 的示例代码 ✅

---

## Section G: Alex 接口收尾 (6 tasks)

> 目标: 关闭所有 Phase 3-4 遗留的对齐项

| ID | Task | 依赖 | 预估 | 说明 |
|----|------|------|------|------|
| G1 | 通知 Alex: webhook 新增 `X-ECP-Signature` HMAC 头 | 无 | 15min | Alex 端可选验证 |
| G2 | 确认 Alex 已运行 `alembic upgrade head`（in_hash/out_hash） | 无 | 10min | Phase 3 遗留 |
| G3 | 共享 SDK API Reference 给 Alex | C9 | 15min | |
| G4 | 确认 LLaChat certificate 页面展示正确 | 无 | 15min | |
| G5 | Mainnet schema UID 同步给 Alex | A3 | 10min | Alex 更新 explorer 链接 |
| G6 | 最终接口契约文档 `INTERFACE-CONTRACT.md` | G1-G5 | 30min | 永久参考 |

**逻辑闭环**:
- G1-G5 是通知/确认，不单方面改 LLaChat ✅
- G6 文档化所有接口，防止未来认知偏差 ✅
- G5 依赖 A3 (mainnet schema)，正确的依赖链 ✅

---

## Section H: SDK 高级功能验证 (9 tasks) — **新增**

> 目标: SDK 里有大量高级模块（proxy, MCP, a2a, otel, scanner）都是骨架代码，
> 从未做过生产级测试。Phase 5 必须验证或标记为 experimental。
>
> **原则**: 能修的修，不能修的标记 `experimental`，不让用户踩坑。

| ID | Task | 依赖 | 预估 | 说明 |
|----|------|------|------|------|
| H1 | `proxy.py` — `atlast proxy` 端到端测试 | 无 | 45min | 启动 proxy → 发 OpenAI 请求 → 验证 record 生成 |
| H2 | `proxy.py` — 修复发现的问题 | H1 | 30min | |
| H3 | `mcp_server.py` — 功能审计 + 基本测试 | 无 | 45min | 验证 MCP tools 是否正确注册 |
| H4 | `mcp_server.py` — 修复或标记 experimental | H3 | 30min | |
| H5 | `a2a.py` — 多方验证逻辑测试 | 无 | 30min | handoff/orphan/blame 测试 |
| H6 | `otel_exporter.py` — OTel span → ECP record 测试 | 无 | 30min | 需要 opentelemetry SDK |
| H7 | `openclaw_scanner.py` — session log 扫描测试 | 无 | 30min | 用 fixture .jsonl 文件 |
| H8 | 为所有 experimental 模块添加 warning | H1-H7 | 20min | `import warnings; warnings.warn("experimental")` |
| H9 | README 更新：标注哪些是 stable / experimental | H8 | 15min | |

**逻辑闭环**:
- H 只修改 SDK repo，不影响 ECP Server 或 LLaChat ✅
- H8 确保用户知道哪些功能可以信任 ✅
- H1-H2 proxy 是 Layer 0 核心承诺，必须验证 ✅

---

## Section I: Reference Server 与 Production Server 对齐 (5 tasks) — **新增**

> 目标: 明确两个 server 的定位，消除混淆
>
> **Reference Server** (`atlast-ecp/server/`):
>   - 开源参考实现，开发者自建用
>   - 有 agents/batches/leaderboard/insights 路由
>   - 不含 EAS 锚定（那是 Production 的事）
>
> **Production Server** (`atlast-ecp-server/`):
>   - 我们的生产部署
>   - 有 anchor/verify/attestations/cron 路由
>   - 含 EAS 锚定 + LLaChat 对接

| ID | Task | 依赖 | 预估 | 说明 |
|----|------|------|------|------|
| I1 | 文档明确定位：`ARCHITECTURE.md` | 无 | 30min | 两个 server 的职责边界 |
| I2 | Reference Server README 更新 | I1 | 15min | 说明与 Production Server 的关系 |
| I3 | Production Server README 更新 | I1 | 15min | 同上 |
| I4 | ECP-SERVER-SPEC.md 升级为 v2.0 | 无 | 45min | 反映 Phase 4 新增端点 |
| I5 | Reference Server Merkle 算法对齐检查 | 无 | 20min | 确保 `server/merkle.py` 与 SDK 一致 |

**逻辑闭环**:
- I5 防止第三个 Merkle 实现不一致（Phase 4 修了 Server，但 Reference Server 没查）✅
- I4 规范文档是 Phase 6 合规审计的基础 ✅

---

## 执行顺序 + 依赖关系图

```
Week 1 (Day 1-3):
  A1 → A2(等Boss) → A3 → A4 → A5 → A6 → A7    [Mainnet]
  B1 → B2 → B3 → B4 → B5                        [LangChain, 并行]
  H1 → H2                                         [Proxy 验证, 并行]
  C1 → C2                                         [覆盖率, 并行]
  G1, G2                                           [Alex 通知, 并行]

Week 1 (Day 4-5):
  B6 → B7 → B8 → B9 → B10                        [CrewAI]
  H3 → H4                                         [MCP 验证, 并行]
  H5                                               [a2a 验证, 并行]

Week 2 (Day 1-3):
  B11 → B12 → B13 → B14 → B15                    [AutoGen]
  H6, H7                                           [otel + scanner, 并行]
  C3, C4, C5, C11                                  [SDK DX, 并行]
  I4, I5                                           [Spec + Merkle 对齐]

Week 2 (Day 4-5):
  H8 → H9                                         [experimental 标注]
  D1 → D2 → D3 → D7                              [Server DB 开始]
  I1 → I2, I3                                      [架构文档]

Week 3 (Day 1-3):
  D4 → D5 → D6 → D8 → D9 → D10 → D11 → D12    [Server DB 完成]
  E1 → E2 → E3 → E4 → E5                         [TS SDK, 并行]

Week 3 (Day 4-5):
  E6 → E7 → E8                                    [TS 发布]
  C6 → C7 → C8 → C9 → C10                        [SDK 发布]

Week 4 (Day 1-3):
  F1 → F2 → F3 → F4 → F5                         [开源增强]
  G3 → G4 → G5 → G6                               [Alex 收尾]
  C12                                              [Spec 更新]
```

---

## 跨 Phase 逻辑闭环检查

### Phase 4 → Phase 5 依赖
| Phase 4 输出 | Phase 5 消费方 | 状态 |
|-------------|---------------|------|
| ECP Server 11 endpoints | D 在此基础上增强 | ✅ 无冲突 |
| Merkle 算法 SDK=Server | E5 三方一致性验证, I5 Reference Server 检查 | ✅ |
| HMAC webhook 签名 | G1 通知 Alex | ✅ |
| Railway 分离完成 | D1 在 Atlas 项目加 Postgres | ✅ 不动 LLaChat |
| api.weba0.com CNAME | SSL 签发后所有公开 API | ⏳ 等待中 |
| slowapi 在 requirements | D7 实现限流 | ✅ 修复遗漏 |
| Sentry 代码已写 | D9 配置 DSN | ✅ 修复遗漏 |
| Webhook fire-and-forget | D8 添加重试 | ✅ 修复风险 |

### Phase 5 → Phase 6 输出
| Phase 5 完成后 | Phase 6 需要 |
|---------------|-------------|
| Base Mainnet 锚定 | EU AI Act 合规审计基础 |
| Framework Adapters | 合规框架必须覆盖主流 agent 框架 |
| ECP-SERVER-SPEC v2.0 | IETF/W3C 标准提交基础文档 |
| INTERFACE-CONTRACT.md | 合规审计引用 |
| 开源社区 + CI | 标准委员会需要社区支持 |
| SDK stable/experimental 标注 | 合规只覆盖 stable 模块 |

### Phase 5 → Phase 7 输出
| Phase 5 完成后 | Phase 7 需要 |
|---------------|-------------|
| a2a.py 验证 | AIP 子协议基础 |
| ECP Server 自有 DB | ASP 子协议数据存储 |
| Mainnet 锚定成功 | 多链扩展基础 |

### Phase 5 内部无冲突确认
| Section | 修改范围 | 与其他 Section 冲突？ |
|---------|----------|---------------------|
| A (Mainnet) | ECP Server env vars | 无（D 改代码，A 改配置）✅ |
| B (Adapters) | SDK `adapters/` | 无 ✅ |
| C (SDK质量) | SDK tests/docs | C10 依赖 B+H → 正确顺序 ✅ |
| D (Server) | ECP Server 代码+infra | 无（不动 SDK）✅ |
| E (TS SDK) | `sdk-ts/` | E5 验证与 Python 一致 ✅ |
| F (开源) | meta 文件 | F4 依赖 B → 正确顺序 ✅ |
| G (Alex) | 通知+文档 | G3 依赖 C9, G5 依赖 A3 → 正确顺序 ✅ |
| H (高级功能) | SDK 高级模块 | 无 ✅ |
| I (Server对齐) | 文档+检查 | I5 可能发现 Merkle bug → 修复不影响其他 ✅ |

---

## 需 Boss 决策

| 事项 | Section | 说明 |
|------|---------|------|
| Mainnet 钱包 funding | A2 | 转约 0.01 ETH (Base chain) |
| Sentry 账号 | D9 | 免费 tier 或用其他监控？ |
| Go SDK 是否加入 | - | 已有骨架代码，Phase 5 不含，Phase 6+？ |

---

## 不做清单（Phase 5 边界）

- ❌ AIP/ASP/ACP 子协议 → Phase 7
- ❌ Enterprise Dashboard → Phase 8
- ❌ Go SDK 完善 → Phase 6+（骨架已有，不紧急）
- ❌ 多链支持（Polygon/Ethereum mainnet）→ Phase 7
- ❌ IETF/W3C 标准提交 → Phase 6
- ❌ 商业化 / 付费 tier → Phase 8
- ❌ Gateway 合并（agentToAgent 跨 gateway）→ Phase 7

---

## 完成标准

Phase 5 完成 = 以下全部为 true:
1. ✅ Base Mainnet ≥1 笔成功 attestation
2. ✅ LangChain / CrewAI / AutoGen adapter 各有 ≥5 个测试通过
3. ✅ SDK 测试覆盖率 >90%
4. ✅ `atlast proxy` 端到端测试通过
5. ✅ ECP Server 有自己的 PostgreSQL + attestation 记录
6. ✅ ECP Server 有 rate limiting + webhook 重试 + Sentry
7. ✅ TS SDK v0.2.0 发布（含 verify + insights）
8. ✅ CI 有 lint + type check + coverage
9. ✅ 接口契约文档 `INTERFACE-CONTRACT.md` 已写并与 Alex 确认
10. ✅ ECP-SERVER-SPEC v2.0 发布
11. ✅ 所有 SDK 模块标注 stable / experimental
12. ✅ PyPI v0.8.0 + npm v0.2.0 发布
13. ✅ Merkle 算法三方一致（Python SDK = TS SDK = ECP Server = Reference Server）
