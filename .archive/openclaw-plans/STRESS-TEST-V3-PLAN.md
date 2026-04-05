# ATLAST ECP Stress Test v3 — 真实用户模拟规划

> **核心原则：每一步都是真实用户会做的操作，你 SSH 到 Mac Mini 能看到一切。**

---

## Mad Mac Mini 当前状态

| 项目 | 状态 |
|------|------|
| OpenClaw | ✅ 已安装 (v2026.3.23) |
| 现有 Agents | 10 个 (elena, felix, kaito, marco, matrix-dev, nadia, sportbot, ziwei 等) |
| Gateway | ✅ running (port 54001, PID 92905) |
| Python | ✅ 3.14.3 (homebrew) |
| Node.js | ✅ v24.13.0 |
| atlast-ecp | ❌ 未安装 |

---

## 8 个真实 Agent（你在 Mac Mini 看得到的）

### Agent 1: OpenClaw Agent + ATLAST Plugin
```
位置: ~/.openclaw-atlast-test-1/
类型: 真实 OpenClaw agent，安装 ATLAST ECP plugin
用户操作:
  1. openclaw agent create atlast-test-1
  2. pip install atlast-ecp
  3. 在 agent workspace 加 ATLAST plugin 配置
  4. 正常使用 agent（对话、tool calling、file ops）
  
你看到的: 一个完整的 OpenClaw agent 目录，有 IDENTITY.md, SOUL.md, workspace/
ECP 数据: ~/.ecp/ 下面自动产生 records + vault
```

### Agent 2: LangChain RAG Agent
```
位置: ~/agents/langchain-rag/
类型: 独立 Python 进程，用 LangChain + ATLASTCallbackHandler
用户操作:
  1. mkdir ~/agents/langchain-rag && cd $_
  2. pip install atlast-ecp langchain-openai
  3. 写 agent.py（真实 LangChain agent with RAG chain）
  4. python agent.py 启动，可以交互

你看到的: 一个 Python 项目目录，有 agent.py, requirements.txt, data/ 
进程: python agent.py (独立进程，有 PID)
```

### Agent 3: CrewAI 多 Agent 团队
```
位置: ~/agents/crewai-team/
类型: 独立 Python 进程，用 CrewAI + ATLASTCrewCallback
用户操作:
  1. mkdir ~/agents/crewai-team && cd $_
  2. pip install atlast-ecp crewai
  3. 写 crew.py（3 个 agent: researcher, writer, reviewer）
  4. python crew.py 启动团队协作
  
你看到的: 项目目录有 crew.py, 3 个 agent 定义
```

### Agent 4: AutoGen 辩论 Agent
```
位置: ~/agents/autogen-debate/
类型: 独立 Python 进程，用 AutoGen + register_atlast
用户操作:
  1. mkdir ~/agents/autogen-debate && cd $_
  2. pip install atlast-ecp pyautogen
  3. 写 debate.py（analyst vs critic 辩论）
  4. python debate.py 启动辩论
  
你看到的: 项目目录有 debate.py, 多 agent 对话记录
```

### Agent 5: wrap() 被动录制 Agent
```
位置: ~/agents/code-reviewer/
类型: 独立 Python 脚本，用 wrap(OpenAI()) 一行接入
用户操作:
  1. mkdir ~/agents/code-reviewer && cd $_
  2. pip install atlast-ecp openai
  3. 写 reviewer.py — 只加一行 client = wrap(OpenAI(...))
  4. python reviewer.py 启动代码审查 agent

你看到的: 最简单的 agent, 一个 .py 文件
```

### Agent 6: @track 装饰器 Agent
```
位置: ~/agents/data-analyst/
类型: 独立 Python 脚本，用 @track 装饰器
用户操作:
  1. mkdir ~/agents/data-analyst && cd $_
  2. pip install atlast-ecp openai
  3. 写 analyst.py — 用 record() 手动记录每步
  4. python analyst.py 启动数据分析 agent

你看到的: 结构化的多步骤 agent
```

### Agent 7: atlast proxy (零代码 Agent)
```
位置: ~/agents/vanilla-bot/
类型: 一个完全不知道 ATLAST 存在的普通 Python 脚本
用户操作:
  1. mkdir ~/agents/vanilla-bot && cd $_
  2. pip install atlast-ecp openai
  3. 写 bot.py — 纯 OpenAI 调用，零 ATLAST 代码
  4. atlast run python bot.py   ← 零代码接入！

你看到的: bot.py 里面没有任何 ATLAST 代码，但 ECP 在透明录制
```

### Agent 8: TS SDK Agent (Node.js)
```
位置: ~/agents/ts-assistant/
类型: TypeScript/Node.js agent，用 atlast-ecp-ts SDK
用户操作:
  1. mkdir ~/agents/ts-assistant && cd $_
  2. npm install atlast-ecp-ts openai
  3. 写 assistant.ts — 用 wrap() 或 track()
  4. npx tsx assistant.ts 启动
  
你看到的: Node.js 项目, package.json, assistant.ts
```

---

## 你在 Mac Mini 看到的目录结构

```
~/
├── agents/                          ← 7 个独立 agent 项目
│   ├── langchain-rag/
│   │   ├── agent.py
│   │   ├── requirements.txt
│   │   └── data/
│   ├── crewai-team/
│   │   └── crew.py
│   ├── autogen-debate/
│   │   └── debate.py
│   ├── code-reviewer/
│   │   └── reviewer.py
│   ├── data-analyst/
│   │   └── analyst.py
│   ├── vanilla-bot/
│   │   └── bot.py                   ← 零 ATLAST 代码
│   └── ts-assistant/
│       ├── package.json
│       └── assistant.ts
│
├── .openclaw-atlast-test-1/         ← OpenClaw agent（第 8 个）
│   └── workspace/
│       ├── IDENTITY.md
│       └── SOUL.md
│
└── .ecp/                            ← ATLAST ECP 数据（所有 agent 共用）
    ├── identity.json                ← Agent DID
    ├── records/
    │   └── 2026-04-01.jsonl         ← ECP records
    └── vault/
        ├── rec_xxx.json             ← 原文（input/output hash 可验证）
        └── ...
```

---

## 每个 Agent 的任务分配

每个 Agent **100+ 完整工作链**，每个工作链 = 真实的 multi-step 操作：

| Agent | 任务类型 | 每任务步骤 |
|-------|---------|-----------|
| OpenClaw | 对话 + tool calling (read/write/exec/search) | 3-8 steps |
| LangChain | RAG 检索 → 分析 → 回答 | 3-5 steps |
| CrewAI | researcher → writer → reviewer 协作 | 3-6 steps |
| AutoGen | analyst vs critic 多轮辩论 | 4-10 steps |
| wrap() | 代码审查 + bug 修复 + 重构 | 2-4 steps |
| @track | 数据分析 → SQL → 报告 | 2-5 steps |
| proxy | 通用问答（零代码，透明录制）| 1-3 steps |
| TS SDK | 多轮助手对话 | 2-4 steps |

**故障场景分散在各 agent 中**（约 15% 的任务是故障注入）

---

## 执行流程（Phase 0 + Phase 1）

### Phase 0: 我在 Mac Mini 上做的（你可以 SSH 进来看）

```
Step 0.1: pip install atlast-ecp openai（全局或 venv）
Step 0.2: 创建 ~/agents/ 目录结构
Step 0.3: 写每个 agent 的代码文件
Step 0.4: 对于 OpenClaw agent: 创建 agent + 安装 plugin
Step 0.5: 验证每个 agent 能跑 1 个任务
```

**Phase 0 结束后我停下来，给你完整报告，你 SSH 进去检查。**

### Phase 1: 启动测试（你确认后）

```
Step 1.1: 启动 orchestrator（它会依次调用每个 agent 的入口）
Step 1.2: 每个 agent 在自己的目录下运行
Step 1.3: 你随时可以 SSH 进去：
          - 看进程: ps aux | grep python
          - 看 ECP 数据: ls ~/.ecp/vault/ | wc -l
          - 看单个 agent: cat ~/agents/langchain-rag/agent.py
          - 看日志: tail -f ~/agents/test-log.jsonl
```

---

## 关键区别 vs 上次（v2 的错误）

| v2（错的） | v3（对的） |
|-----------|-----------|
| 1 个 Python 脚本假装 8 个 agent | 8 个独立的真实 agent 项目 |
| 后台 nohup 你看不到 | 每个 agent 有自己的目录和代码 |
| 模拟 SDK 调用 | 真的 `pip install` + 真的 `import` |
| 没有真实 OpenClaw agent | 真的用 Mac Mini 上的 OpenClaw |
| Phase 0 结束直接跑了 | Phase 0 结束停下等你确认 |

---

## 预算估算

- 全用免费模型 (gemma-3-4b:free, gemma-3-12b:free) 为主
- gpt-4o-mini 用于 tool calling 场景
- 预估 800 tasks × avg 500 tokens = ~$2-4
- Gas: 2-4 笔 super-batch TX ≈ 0.00006-0.00012 ETH

---

## 待你确认

1. 这 8 个 agent 的定义可以吗？
2. 要不要复用 Mac Mini 上现有的 OpenClaw agents（elena, kaito 等），还是新建？
3. 确认后我开始 Phase 0（只准备，不启动测试）
