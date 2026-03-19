# ATLAST ECP — Phase 2 详细开发计划

> **目标**：从 "SDK 开发工具" 进化为 "开源协议生态"
> **起始版本**：v0.6.1（PyPI + npm 已发布）
> **预计总工时**：10-12 小时
> **执行顺序**：P2-1 → P2-2 → P2-4 → P2-3 → P2-5
> **v1.1 更新**：P2-3 扩展为全球 AI 合规指南（不绑定单一法规）；P2-4 A2A 优先级提升（multi-agent 是市场现实）

---

## 当前已完成基线（P0 + P1 Summary）

| 阶段 | 状态 | 核心产出 |
|------|------|---------|
| P0 | ✅ 完成 | Bug fixes, core.py, record ID 统一 |
| P1-Infra | ✅ 完成 | PyPI v0.6.1, npm v0.1.0, GitHub CI, OpenClaw Plugin |
| P1-Strategy | ✅ 完成 | ECP v1.0 Spec, Proxy, CLI, 5-Level Record, README 重写 |
| P1-Adapters | ✅ 完成 | LangChain + CrewAI adapters, insights v0.1 |
| P1-Docs | ✅ 完成 | ECP-SPEC.md, ECP-SERVER-SPEC.md, CHANGELOG.md |

**测试**：368 passed, 3 skipped, 0 failed（16 test files）
**SDK 模块**：19 Python + 9 TypeScript + 2 adapters
**Git**：main = origin/main（全部已推）

---

## P2-1: Reference ECP Server（~3-4h）⭐ 最高优先级

### 为什么先做这个？
ECP 协议的独立性取决于是否存在一个**非 LLaChat 的开源 ECP Server 实现**。没有它，ECP 就是 LLaChat 的私有格式。有了它，ECP = Git，LLaChat = GitHub。

### 目录结构

```
server/
├── README.md              # 安装 + 5 分钟启动指南
├── requirements.txt       # FastAPI + uvicorn + 无其他
├── main.py                # FastAPI app + startup/shutdown
├── config.py              # 环境变量 + 默认值
├── database.py            # SQLite async 存储层
├── models.py              # Pydantic request/response models
├── auth.py                # X-Agent-Key 验证
├── routes/
│   ├── __init__.py
│   ├── agents.py          # POST /v1/agents/register + GET /v1/agents/{handle}/profile
│   ├── batches.py         # POST /v1/batches
│   └── leaderboard.py     # GET /v1/leaderboard
├── scoring.py             # Trust score 计算（可替换）
├── merkle.py              # Merkle root 验证
├── Dockerfile             # 单层精简镜像
├── docker-compose.yml     # 一键启动
└── tests/
    ├── conftest.py        # pytest fixtures (TestClient)
    ├── test_agents.py     # 注册 + profile
    ├── test_batches.py    # 上传 + 验证
    ├── test_leaderboard.py# 排行榜
    └── test_scoring.py    # 评分算法
```

### 子任务分解

| ID | 任务 | 依赖 | 验收标准 | 估时 |
|----|------|------|---------|------|
| **2.1.1** | `models.py` — Pydantic schemas | 无 | AgentRegisterRequest/Response, BatchUploadRequest/Response, AgentProfile, LeaderboardEntry 全部定义，含 v0.1+v1.0 record format 兼容 | 20m |
| **2.1.2** | `config.py` — 配置管理 | 无 | 支持 `ECP_DB_PATH`, `ECP_HOST`, `ECP_PORT`, `ECP_LOG_LEVEL` 环境变量，合理默认值 | 10m |
| **2.1.3** | `database.py` — SQLite 存储层 | 2.1.1 | `agents`, `batches`, `record_hashes` 三表；async CRUD；auto-migrate on startup；WAL mode | 30m |
| **2.1.4** | `auth.py` — API Key 验证 | 2.1.3 | `verify_agent_key(key) -> agent_id`；无效 key 返回 401；格式 `atl_` + 32 hex | 15m |
| **2.1.5** | `routes/agents.py` — 注册 + Profile | 2.1.3, 2.1.4 | POST register 返回 201 + api_key；GET profile 返回完整统计；handle 唯一约束；did 唯一约束 | 30m |
| **2.1.6** | `routes/batches.py` — 批量上传 | 2.1.3, 2.1.4 | POST 验证 X-Agent-Key、存储 batch + record_hashes；可选 Merkle root 验证 | 30m |
| **2.1.7** | `merkle.py` — Merkle 验证 | 无 | `verify_merkle_root(hashes, root) -> bool`；与 SDK `build_merkle_root()` 输出一致 | 15m |
| **2.1.8** | `scoring.py` — Trust Score 计算 | 无 | 基于 flag_counts + record_count + latency 计算 4 维信号（Reliability/Transparency/Efficiency/Authority）；权重可配置 | 20m |
| **2.1.9** | `routes/leaderboard.py` — 排行榜 | 2.1.3, 2.1.8 | GET 支持 `period`, `domain`, `limit` 参数；按综合 score 降序 | 20m |
| **2.1.10** | `main.py` — FastAPI 入口 | 2.1.5-2.1.9 | 挂载所有路由；startup 事件初始化 DB；CORS 中间件；`/health` 端点 | 15m |
| **2.1.11** | `tests/` — 全部端点测试 | 2.1.10 | ≥20 个测试；覆盖注册→上传→profile→leaderboard 完整流程；边界情况（重复注册、无效 key、空 batch） | 30m |
| **2.1.12** | `Dockerfile` + `docker-compose.yml` | 2.1.10 | `docker compose up` 一键启动；镜像 <100MB；数据持久化 volume | 15m |
| **2.1.13** | `README.md` — 5 分钟启动指南 | 2.1.12 | pip install + `python main.py` 本地启动；Docker 启动；配置说明；API 示例 curl | 15m |
| **2.1.14** | 集成验证 | 2.1.13 | `atlast push --endpoint http://localhost:8900` 能把 SDK 本地记录推到 Reference Server | 15m |

**逻辑闭环检查**：
- ✅ Reference Server 的 4 个端点与 `ECP-SERVER-SPEC.md` 100% 对齐
- ✅ `scoring.py` 权重与 SDK `signals.py` 的 `compute_trust_signals()` 算法一致
- ✅ `merkle.py` 的 Merkle tree 算法与 SDK `verify.py` 的 `build_merkle_root()` 一致
- ✅ 记录格式同时接受 v0.1（nested）和 v1.0（flat）
- ✅ `atl_` API Key 格式与 `ECP-SERVER-SPEC.md` 和 SDK `cli.py flush` 一致
- ✅ Reference Server 完全独立于 LLaChat（不依赖 PostgreSQL/Redis/EAS）

**不做（与其他模块边界）**：
- ❌ 不做 Owner JWT / 管理 API（那是 LLaChat 的功能）
- ❌ 不做 SSE event stream（MVP 不需要）
- ❌ 不做 on-chain anchoring（EAS 是 LLaChat 后端的功能）
- ❌ 不做 certificate 端点（MVP 暂不需要）
- ❌ 不改 SDK 任何代码（Reference Server 是新增模块，不触碰已有代码）

---

## P2-2: GitHub 社区模板（~1h）

### 为什么做？
开源项目的"门面"。没有 Contributing guide 和 Issue template 的 repo = "个人项目"，有了 = "社区项目"。

### 子任务分解

| ID | 任务 | 依赖 | 验收标准 | 估时 |
|----|------|------|---------|------|
| **2.2.1** | `.github/ISSUE_TEMPLATE/bug_report.md` | 无 | 包含 ECP version、OS、复现步骤、预期行为 | 5m |
| **2.2.2** | `.github/ISSUE_TEMPLATE/feature_request.md` | 无 | 包含 use case、建议方案、ECP level 影响 | 5m |
| **2.2.3** | `.github/PULL_REQUEST_TEMPLATE.md` | 无 | 包含 changes summary、testing done、ECP spec compliance checklist | 5m |
| **2.2.4** | `CONTRIBUTING.md` | 无 | Dev setup、代码规范、PR 流程、测试要求（必须 `pytest` 全通过）、ECP record 格式兼容性声明 | 15m |
| **2.2.5** | `CODE_OF_CONDUCT.md` | 无 | Contributor Covenant v2.1（标准版） | 5m |
| **2.2.6** | `SECURITY.md` | 无 | 安全漏洞报告流程、PGP key（可选）、scope（SDK + Server） | 10m |
| **2.2.7** | `.github/FUNDING.yml` | 无 | GitHub Sponsors（如有）或空 | 5m |

**逻辑闭环检查**：
- ✅ `CONTRIBUTING.md` 的测试要求与现有 CI workflow 一致（`pytest` + `npm test`）
- ✅ `SECURITY.md` scope 包含新增的 Reference Server
- ✅ Issue template 的版本字段包含 v1.0 spec level（L1-L5）
- ✅ 不引入任何代码变更

---

## P2-3: 全球 AI 合规指南（~2.5h）

### 为什么做？
企业客户的"为什么要用 ECP"答案。但我们**不绑定单一法规**——ECP 是全球性的信任协议，合规指南也必须是全球性的。EU AI Act 是最紧迫的（2027 生效），但中国《生成式 AI 管理办法》、美国 NIST AI RMF、新加坡 Model AI Governance 等同样重要。

**核心原则**：ECP 解决的是"AI Agent 行为可验证"这个**普世需求**，不是某一部法律的合规工具。法规会变，ECP 的价值不变。

### 文件路径
```
docs/compliance/
├── AI-COMPLIANCE-GUIDE.md          # 主文档：全球 AI 合规指南
├── mappings/
│   ├── EU-AI-ACT.md                # EU AI Act 详细映射
│   ├── CHINA-AI-REGULATIONS.md     # 中国 AI 法规映射
│   ├── US-NIST-AI-RMF.md          # 美国 NIST AI RMF 映射
│   └── APAC-FRAMEWORKS.md         # 新加坡/日本/韩国/澳洲
└── README.md                       # 合规文档导航
```

### 子任务分解

| ID | 任务 | 依赖 | 验收标准 | 估时 |
|----|------|------|---------|------|
| **2.3.1** | 全球 AI 法规景观扫描 | 无 | 梳理 5 大法规体系的核心要求：EU AI Act、中国 GenAI 办法、US NIST AI RMF、新加坡 MAIGF、ISO/IEC 42001。提取"共同需求清单" | 25m |
| **2.3.2** | ECP → 通用合规能力映射 | 2.3.1 | 不按法规分，按**能力分**：审计追溯、隐私保护、行为透明、异常检测、身份验证。每个能力 → ECP 如何满足 → 哪些法规需要这个能力 | 25m |
| **2.3.3** | EU AI Act 详细映射（最紧迫） | 2.3.2 | Article 14（人类监督）→ ECP confidence + flags；Article 52（透明度）→ ECP hash chain；Article 9（风险管理）→ ECP signals。合规程度：Full/Partial/Roadmap | 20m |
| **2.3.4** | 其他法规简要映射 | 2.3.2 | 中国/美国/APAC 各 1 页，重点突出 ECP 满足的部分，不深入法律细节 | 20m |
| **2.3.5** | 实操指南：3 个跨法规场景 | 2.3.3 | 代码/配置示例：(1) 审计日志导出（EU+中国都需要）、(2) 异常行为检测（全球通用）、(3) Agent 身份追溯（多法规要求） | 20m |
| **2.3.6** | Gap 分析 + Roadmap | 2.3.4 | 诚实列出 ECP 目前不满足的合规点 + 哪个子协议（AIP/ASP/ACP）何时补齐 + 不同法规的 gap 差异 | 15m |
| **2.3.7** | Executive Summary | 2.3.6 | 1 页总结：ECP = 全球 AI Agent 合规基础设施。不是某一部法律的工具，而是**所有法规都需要的底层能力** | 15m |
| **2.3.8** | 交叉校对 | 2.3.7 | 所有引用的 ECP 字段/Level 与 `ECP-SPEC.md` v1.0 一致；法规引用准确；不过度承诺 | 10m |

**逻辑闭环检查**：
- ✅ 按**能力**分类而非按**法规**分类——ECP 不依赖任何单一法规
- ✅ 引用的 ECP 字段/Level 与 `ECP-SPEC.md` v1.0 完全一致
- ✅ 不承诺 ECP 尚未实现的功能（AIP/ASP/ACP 标注为 "Roadmap"）
- ✅ 不涉及 LLaChat 平台功能（合规映射纯粹基于 ECP 协议）
- ✅ Gap 分析诚实——不过度营销
- ✅ 法规会变，但 ECP 的"审计/透明/验证"价值不依赖任何特定法规

---

## P2-4: A2A 多方验证 PoC（~3h）⭐ 差异化核心

### 为什么做？

**市场现实**：2026 年主流 Agent 架构已经是 multi-agent——CrewAI、AutoGen、LangGraph、MetaGPT 都是多 Agent 协作。如果 ECP 只能审计单 Agent，就丢失了市场上最复杂、最需要审计的场景。

**三个核心痛点**：
1. **数据交接验证**：Agent A 把结果传给 Agent B，B 收到的和 A 发出的是同一份吗？（`out_hash` == `in_hash`）
2. **沟通丢失检测**：多 Agent 协作中，某个 Agent 的输出没有被任何下游 Agent 消费——这条信息去哪了？
3. **责任追溯**：最终结果出错了，是哪个 Agent 在哪个环节出的问题？

**ECP 的独有优势**：LangSmith/Arize 只能看单 Agent 的 trace。ECP 的 `in_hash`/`out_hash` 天然支持跨 Agent 验证——这是架构级优势，不是功能级的。

### 文件路径
```
sdk/atlast_ecp/a2a.py        # 核心逻辑
sdk/tests/test_a2a.py        # 测试
docs/A2A-VERIFICATION.md     # 使用文档 + 架构图
```

### 子任务分解

| ID | 任务 | 依赖 | 验收标准 | 估时 |
|----|------|------|---------|------|
| **2.4.1** | A2A 数据模型设计 | 无 | `Handoff`（source_agent, target_agent, out_hash, in_hash, ts）；`A2AChain`（agents, handoffs, gaps, timeline）；`A2AReport`（valid, gap_count, orphan_outputs, blame_trace） | 20m |
| **2.4.2** | `verify_handoff(record_a, record_b)` | 2.4.1 | 验证 record_a.out_hash == record_b.in_hash；返回 match/mismatch/partial（部分 hash 匹配）；支持 v0.1 + v1.0 格式 | 20m |
| **2.4.3** | `discover_handoffs(records)` | 2.4.2 | 输入混合多 agent 的 records → 自动匹配 out_hash/in_hash 对 → 发现所有交接关系 → 返回 handoff 列表 + **orphan outputs**（没被消费的输出） | 30m |
| **2.4.4** | `build_a2a_chain(records)` | 2.4.3 | 构建 DAG（有向无环图）：节点 = record，边 = handoff；检测循环；生成 timeline 视图 | 25m |
| **2.4.5** | `verify_a2a_chain(chain)` | 2.4.4 | 全链验证：(1) 所有 handoff hash 匹配 (2) 无未解释 gap (3) timestamp 因果一致（A 完成时间 < B 开始时间）(4) **blame trace**：如果链断了，定位到具体哪个 Agent 哪个 record | 25m |
| **2.4.6** | `format_a2a_report(chain)` | 2.4.5 | 人类可读报告：参与 agents 列表、handoff 拓扑图（ASCII DAG）、验证结果、gap/orphan 清单、blame trace | 15m |
| **2.4.7** | CLI `atlast verify --a2a` | 2.4.6 | `atlast verify --a2a agent_a.jsonl agent_b.jsonl [agent_c.jsonl ...]` → 加载多 agent records → 跑 A2A 验证 → 输出报告。`--json` 支持机器可读输出 | 20m |
| **2.4.8** | 测试套件 | 2.4.7 | ≥18 个测试：正常 2-agent handoff、3+ agents 链式、gap 检测、orphan output 检测、hash mismatch blame、循环检测、乱序 timestamp、单 agent（无 handoff 退化）、v0.1+v1.0 混合格式、空 records | 30m |
| **2.4.9** | `A2A-VERIFICATION.md` 文档 | 2.4.7 | 概念：为什么 multi-agent 需要证据链。架构图（ASCII DAG）。3 个场景示例：(1) CrewAI 3-agent 流水线 (2) AutoGen 对话式协作 (3) 人类-Agent 混合审批链。CLI 使用。API 参考 | 20m |

**逻辑闭环检查**：
- ✅ `verify_handoff` 使用 ECP v1.0 的 `in_hash`/`out_hash` 字段（与 `ECP-SPEC.md` 一致）
- ✅ 同时支持 v0.1（nested `step.in_hash`）和 v1.0（flat `in_hash`）格式
- ✅ `a2a.py` 依赖 `record.py` 的 `hash_content()` 和 `storage.py` 的 `load_records()`
- ✅ 不修改任何已有模块的公共 API
- ✅ CLI `--a2a` 是 `verify` 子命令的新 flag，不与现有 `atlast verify <record_id>` 冲突
- ✅ A2A 验证是**纯本地**操作——不调用任何网络 API
- ✅ **orphan output 检测**解决"沟通丢失"问题
- ✅ **blame trace**解决"责任追溯"问题
- ✅ DAG 而非线性链——支持并行 Agent 拓扑（如 Agent A 同时分发给 B 和 C）

**与现有代码的关系**：
- 读取：`record.py` (hash_content), `storage.py` (load_records), `verify.py` (verify_signature)
- 新增：`a2a.py` + `test_a2a.py` + CLI flag + docs
- 修改：`cli.py` 新增 `--a2a` flag 到 `verify` 命令（最小改动：~20 行）
- 不碰：其他 16 个模块

---

## P2-5: Go SDK Skeleton（~2h）

### 为什么做？
Go 覆盖云原生/基础设施开发者（Kubernetes operators、微服务、DevOps 工具）。Go 社区的 Agent 框架（如 langchaingo）在增长。骨架先占位，后续社区可贡献。

### 目录结构
```
sdk-go/
├── go.mod                # module: github.com/willau95/atlast-ecp/sdk-go
├── go.sum
├── record.go             # ECP record 创建（v1.0 flat format）
├── record_test.go
├── verify.go             # 签名验证 + Merkle proof
├── verify_test.go
├── storage.go            # JSONL 本地读写
├── storage_test.go
├── hash.go               # SHA-256 hash_content()
├── hash_test.go
├── types.go              # Record, MinimalRecord, Meta 结构体
├── cmd/
│   └── atlast/
│       └── main.go       # CLI 骨架：record, log, verify
└── README.md
```

### 子任务分解

| ID | 任务 | 依赖 | 验收标准 | 估时 |
|----|------|------|---------|------|
| **2.5.1** | `types.go` — 数据结构 | 无 | `Record`, `MinimalRecord`, `Meta`, `HandoffResult` 结构体；JSON tag 与 ECP v1.0 spec 完全一致 | 15m |
| **2.5.2** | `hash.go` — SHA-256 | 无 | `HashContent(input string) string` 返回 `sha256:{hex}`；与 Python `hash_content()` 输出一致 | 10m |
| **2.5.3** | `record.go` — 记录创建 | 2.5.1, 2.5.2 | `NewMinimalRecord(agent, action, input, output)` → v1.0 flat JSON；`rec_` + 16 hex ID | 20m |
| **2.5.4** | `storage.go` — JSONL 存储 | 2.5.1 | `SaveRecord(path, record)`, `LoadRecords(path) []Record`；JSONL 格式与 Python SDK 互通 | 20m |
| **2.5.5** | `verify.go` — 验证 | 2.5.2 | `VerifyChainHash(records)`, `BuildMerkleRoot(hashes)`, `VerifyMerkleProof(hash, proof, root)` | 20m |
| **2.5.6** | `cmd/atlast/main.go` — CLI 骨架 | 2.5.3, 2.5.4, 2.5.5 | `atlast record`, `atlast log`, `atlast verify` 三个子命令可运行 | 15m |
| **2.5.7** | 全部测试 | 2.5.6 | ≥15 个测试；`go test ./...` 通过；cross-validate: Go 创建的 record Python 能读取 | 20m |
| **2.5.8** | `README.md` | 2.5.7 | 安装、Quick Start、API 参考、与 Python SDK 的互通性说明 | 10m |

**逻辑闭环检查**：
- ✅ `rec_` ID 格式与 Python SDK `record.py` 的 `_generate_record_id()` 一致
- ✅ `hash_content()` 输出与 Python `record.py` 的 `hash_content()` **完全一致**（cross-validate 测试）
- ✅ JSONL 格式与 Python `storage.py` 互通——Go 写的文件 Python 能读
- ✅ Merkle root 算法与 Python `verify.py` 的 `build_merkle_root()` 一致
- ✅ 不依赖任何第三方库（纯标准库：`crypto/sha256`, `encoding/json`, `os`）
- ✅ Go module 路径是 `github.com/willau95/atlast-ecp` 的子模块

---

## 全局逻辑一致性检查矩阵

### 跨模块 Hash 一致性

| 操作 | Python SDK | TS SDK | Go SDK | Reference Server |
|------|-----------|--------|--------|-----------------|
| `hash_content("hello")` | `sha256:2cf24...` | `sha256:2cf24...` | `sha256:2cf24...` | N/A (不计算 hash) |
| Record ID 格式 | `rec_` + 16 hex | `rec_` + 16 hex | `rec_` + 16 hex | 接受任何 `rec_*` |
| Merkle root | 排序 → 逐层 SHA-256 | — | 排序 → 逐层 SHA-256 | 同算法验证 |
| JSONL 格式 | `~/.atlast/records.jsonl` | — | 同路径同格式 | N/A (DB 存储) |

### 跨模块 API 一致性

| 端点 | ECP-SERVER-SPEC | Reference Server | LLaChat Backend |
|------|----------------|------------------|-----------------|
| POST /v1/agents/register | ✅ 定义 | ✅ 实现 | ✅ 已有（Alex） |
| POST /v1/batches | ✅ 定义 | ✅ 实现 | ✅ 已有（Alex） |
| GET /v1/agents/{handle}/profile | ✅ 定义 | ✅ 实现 | ✅ 已有（Alex） |
| GET /v1/leaderboard | ✅ 定义 | ✅ 实现 | ✅ 已有（Alex） |
| X-Agent-Key header | ✅ 定义 | ✅ 实现 | ✅ 已有（Alex） |

### Trust Score 算法一致性

| 维度 | SDK `signals.py` | Reference `scoring.py` | LLaChat Backend |
|------|-----------------|----------------------|-----------------|
| Reliability | 40% | 40% | 40% (Alex) |
| Transparency | 30% | 30% | 30% (Alex) |
| Efficiency | 20% | 20% | 20% (Alex) |
| Authority | 10% | 10% | 10% (Alex) |

### A2A 与现有模块关系

| a2a.py 调用 | 被调用模块 | 函数 | 改动? |
|------------|----------|------|-------|
| hash 比对 | `record.py` | `hash_content()` | 无改动 |
| 加载记录 | `storage.py` | `load_records()` | 无改动 |
| 签名验证 | `verify.py` | `verify_signature()` | 无改动 |
| CLI 入口 | `cli.py` | `cmd_verify()` | +15 行（新增 `--a2a` flag） |

---

## 执行规则

### 1. 进度追踪（防失忆铁律）

每完成一个子任务（如 2.1.3）：
```
1. 运行相关测试
2. memory_store("P2进度: 2.1.3 database.py 完成。SQLite 3表 + WAL + auto-migrate。下一步: 2.1.4 auth.py")
3. 如果是阶段性节点（如 P2-1 全部完成）：
   a. git commit + push
   b. 更新 memory/2026-03-19.md
   c. memory_store("P2-1 Reference ECP Server 完成。[具体统计]。下一阶段: P2-2 社区模板")
```

### 2. 质量门禁

| 时机 | 检查 |
|------|------|
| 每个子任务完成后 | 运行该模块的测试 |
| 每个 P2-X 完成后 | `cd /tmp/atlast-ecp/sdk && python -m pytest -x` 全量测试 |
| P2-1 完成后 | Reference Server 独立 `pytest` + 与 SDK `atlast push` 集成验证 |
| P2-4 完成后 | cross-validate: A2A hash 与 record.py hash 一致 |
| P2-5 完成后 | cross-validate: Go hash 输出 == Python hash 输出 |
| P2 全部完成后 | 全局测试 + git tag v0.7.0 + PyPI publish |

### 3. 不做清单（边界防护）

- ❌ 不改 LLaChat 后端代码（Alex 的 repo）
- ❌ 不改已有 SDK 公共 API（仅新增）
- ❌ 不引入 required 三方依赖（Reference Server 除外，它是独立模块）
- ❌ 不做 Auth/Dashboard（Alex 的职责）
- ❌ 不做 EAS on-chain（已在 LLaChat 后端实现）
- ❌ 不在 P2 期间更新 TS SDK（那是 P3 的事）

---

## 版本规划

| 里程碑 | 版本 | 内容 |
|--------|------|------|
| P2-1 完成 | — | Reference Server 独立 repo 或 monorepo 子目录 |
| P2-1 + P2-2 完成 | v0.7.0-rc1 | 社区就绪 |
| P2-4 完成 | v0.7.0-rc2 | A2A 验证 |
| P2 全部完成 | **v0.7.0** | PyPI publish + GitHub Release |

---

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| /tmp 重启被清空 | 中 | 代码丢失 | 每个 P2-X 完成立即 git push |
| Compact/新 session 失忆 | 高 | 进度断层 | 每个子任务 memory_store + memory file |
| Reference Server 与 SDK hash 不一致 | 低 | 信任破裂 | P2-1.14 集成验证 + cross-validate |
| Go SDK hash 与 Python 不一致 | 低 | 跨语言互通失败 | P2-5.7 cross-validate 测试 |
| DNS/网络问题影响 git push | 中 | 部署延迟 | 使用已有的 `--resolve` DNS workaround |
| 合规指南法规引用过时 | 中 | 误导企业客户 | 按"能力"分类而非按"法规"分类，法规细节放子文档 |

---

*P2 Development Plan v1.0 — Atlas, ATLAST Protocol — 2026-03-19*
