# ATLAST ECP Dashboard — 完整用户测试指南

> 两个真实场景，一步一步带你走完全流程。
> 每一步告诉你：做什么、会看到什么、看到的代表什么。

---

## 准备工作（1 分钟）

```bash
cd /tmp/atlast-ecp
source .venv/bin/activate

# Step 1: 生成 demo 数据（两个 agent，60 天，450+ 条记录）
atlast demo --days 60

# Step 2: 建立搜索索引
atlast index

# Step 3: 启动 dashboard
atlast dashboard
```

浏览器会自动打开 `http://127.0.0.1:3827`。

---

## 场景 A：Research Agent 出了问题 — 找到根因

### 背景故事
你有一个 **Research Agent**（`demo_research_agent`），每天自动搜集半导体行业数据、分析趋势、写报告。它已经稳定运行了 25 天。但你注意到最近报告质量下降了——你要找出原因。

---

### Step 1：打开 Dashboard → 看 Overview

**做什么**：打开 http://127.0.0.1:3827，默认就在 Overview 页面。

**你会看到**：

1. **顶部 6 个数字卡片**：
   - `450` Total Records — 60 天共记录了 450 次 agent 操作
   - `13` Errors — 其中 13 次出了错
   - `2.9%` Error Rate — 总体错误率（绿色=健康）
   - `353ms` Avg Latency — 平均响应时间
   - `120` Sessions — 共 120 个工作会话
   - `60` Active Days — 60 天都有活动

2. **🔍 Detected Issues 区块**（最重要！）：
   - 你会看到 **4 个红色/黄色问题卡片**
   - 每个都是一个 **Error Spike**（错误率飙升）
   - 日期集中在 **2 月 24-27 日**
   - 例如：`🔴 Error Spike · 2026-02-25 — Error rate 57% (4/7)`

**这代表什么**：
> 你的 Research Agent 在 2 月 24-27 日出了严重问题——一天内超过一半的操作都失败了。这 4 天就是问题集中爆发期。

3. **📅 Activity Timeline**：
   - 一个绿色+红色的条形图
   - 大部分日子是纯绿色（正常）
   - 2 月 24-27 日那段会看到明显的 **红色条**
   - 红色越长 = 那天错误越多

**这代表什么**：
> 时间线让你一眼看出"哪段时间出了问题"——绿色=正常，红色=错误。2 月下旬有一段明显的红色集中区。

---

### Step 2：点击问题卡片 → 看那天的详情

**做什么**：点击 `Error rate 57% (4/7)` 那个问题卡片。

**你会看到**：自动跳转到 **Search** tab，搜索 `2026-02-25`。

**你会看到**：

- 该天的所有 7 条记录
- 每条记录显示：
  - `❌` 或 `✅` — 成功还是失败
  - `web_search` / `data_query` / `trend_analysis` — agent 做了什么操作
  - `gpt-4o` — 用了什么模型
  - `confidence: 0.42` — agent 自己有多确定
  - 时间戳

- 失败的记录带红色 `ERROR` 标签

**这代表什么**：
> 你能看到那天 agent 做了什么，哪些成功哪些失败。注意 confidence 数字——正常应该 0.8+，这里很多掉到 0.4-0.5，说明 agent 自己也知道输出不可靠。

---

### Step 3：展开一条错误记录 → 看 agent 实际说了什么

**做什么**：点击一条带 `❌ web_search` 的错误记录。

**你会看到**：记录展开，显示 **📥 Input** 和 **📤 Output**：

```
📥 Input:
Search: semiconductor industry news March 2026

📤 Output:
ERROR: HTTP 401 Unauthorized — API key expired. SerpAPI returned: 
'Invalid API key. Please renew your subscription.' 
Falling back to cached results from 2026-02-28.
```

**这代表什么**：
> 真相大白！agent 的搜索 API key 过期了。SerpAPI 返回 401 错误。agent 被迫使用过期的缓存数据。这就是为什么后续的分析和报告质量都下降了——数据源断了。

---

### Step 4：Trace 证据链 → 追踪问题的完整传播路径

**做什么**：在展开的记录底部，点击 `🔗 Trace evidence chain`。

**你会看到**：跳转到 **Trace** tab，显示一条 **可视化证据链**：

```
● ❌ tool_call:web_search  gpt-4o  287ms  conf:0.42
  📥 Search: semiconductor industry news March 2026
  📤 ERROR: HTTP 401 Unauthorized — API key expired...
  
  ← ❌ tool_call:data_query  gpt-4o  315ms  conf:0.38
    📥 Query: SELECT * FROM market_data WHERE date > '2026-02-01'
    📤 ERROR: Connection refused — data provider endpoint returned HTTP 403...
    
    ← ❌ llm_call:trend_analysis  gpt-4o  445ms  conf:0.35
      📥 Attempt trend analysis with whatever data is available
      📤 ERROR: Cannot perform meaningful trend analysis. Both primary 
         (SerpAPI) and secondary (market data DB) sources are unavailable...
      
      ← ✅ llm_call:summarize  gpt-4o  380ms  conf:0.51
        📥 Generate status report explaining data access failures
        📤 Status Report — Data Access Failure: Multiple data sources 
           are currently inaccessible: 1. SerpAPI: 401 Unauthorized...
```

**这代表什么**：
> 证据链清楚展示了问题的 **因果关系**：
> 1. 最初：API key 过期 → web_search 失败
> 2. 连锁：数据库也断了 → data_query 失败  
> 3. 结果：没有数据 → trend_analysis 无法分析
> 4. 最终：agent 自动生成了一份故障报告
> 
> 每一步都有 agent 的原始输入和输出作为**证据**——不是人编的，是 agent 当时实际产生的数据。

---

### Step 5：看恢复过程

**做什么**：回到 Search tab，搜索 `API access restored`。

**你会看到**：

```
✅ tool_call:web_search  gpt-4o  conf:0.89
📥 Search: semiconductor market news March 2026 (testing restored API access)
📤 ✅ API access restored. Found 15 results. Top: 'Global Chip Sales Hit 
   $180B in Q1 2026' (SIA, 2026-03-10). Data feeds operational.
```

**这代表什么**：
> API key 被续费后，agent 恢复正常。搜索结果重新出现，confidence 回到 0.89。问题从发生到修复的完整生命周期都被 ECP 记录下来了。

---

## 场景 B：Code Review Agent 模型切换 — 发现质量下降

### 背景故事
你有一个 **Code Review Agent**（`demo_code_review_agent`），自动审查 PR。为了省成本，你把模型从 gpt-4o 切换到 gpt-4o-mini。过了几天你想检查：质量有没有下降？

---

### Step 1：在 Activity tab 筛选 agent

**做什么**：点击 **📋 Activity** tab，从左边下拉框选择 `demo_code_review_agent`，点 Refresh。

**你会看到**：只显示 Code Review Agent 的记录。

**注意观察**：
- 大部分记录是 `✅ analyze_code`、`✅ generate_review`
- 但某几天（约 Day 21-25）的记录 model 列变成了 `gpt-4o-mini`
- 那几天的 **confidence 明显更低**（0.55-0.70 vs 正常的 0.85+）

---

### Step 2：搜索 gpt-4o-mini 的审查记录

**做什么**：点击 **🔍 Search** tab，搜索 `gpt-4o-mini`。

**你会看到**：模型切换期间的所有记录。

**展开一条 `generate_review` 记录**：

```
📥 Input:
Generate PR review for #503

📤 Output:
## PR Review: #503 — Payment webhook handler

**Verdict: ✅ Approve**

Implementation looks good overall.
- Webhook signature verification present
- Basic error handling
- Tests included

Minor: Consider adding idempotency key check.

**Approved.**
```

**这代表什么**：
> gpt-4o-mini 批准了这个 PR，但审查很浅——只说了"looks good"。没有深入分析安全问题。

### Step 3：对比正常模型的审查

**做什么**：搜索 `SQL injection`。

**你会看到**：gpt-4o 的审查记录：

```
📥 Input:
Review auth_middleware.py for security vulnerabilities...

📤 Output:
Security Review — auth_middleware.py:

🔴 CRITICAL (1):
- Line 45: db.execute(f"SELECT * FROM users WHERE token='{token}'") 
  — SQL injection vulnerability. Token is user-supplied and not parameterized.

🟡 WARNING (2):
- Line 23: JWT secret loaded from env but no fallback validation...
- Line 67: Session timeout 30 days — unusually long...

✅ GOOD:
- CSRF protection properly implemented
- Password hashing uses bcrypt with cost=12
```

**这代表什么**：
> 同样是代码审查，gpt-4o 能发现 SQL 注入这种 **关键安全漏洞**，给出具体行号和修复建议。gpt-4o-mini 的审查则太浅，可能放过严重 bug。
>
> **ECP 的价值**：你不需要人工对比——通过 confidence 分数 + 实际输出，就能量化"模型降级"带来的质量损失。

---

### Step 4：用 Audit 确认全局影响

**做什么**：回到 **🏠 Overview**，看 Detected Issues。

**你会看到**：4 个 error spike 问题，都集中在 Research Agent 的数据源故障期。Code Review Agent 的模型切换**没有触发 error spike**（因为没有报错，只是质量下降）。

**这代表什么**：
> Audit 能自动发现"硬错误"（API 报错、连接断开），但"软问题"（模型质量下降）需要你主动搜索和对比。这就是为什么 Search + 证据链 trace 是必要的——Audit 告诉你明显的问题，Search/Trace 帮你调查隐性问题。

---

## 功能总结：你实际能做什么

| 功能 | 对应 Dashboard 操作 | 回答什么问题 |
|------|---------------------|-------------|
| **Audit** | Overview → Detected Issues | "我的 agent 有明显问题吗？" |
| **Timeline** | Overview → Activity Timeline | "问题发生在什么时间段？" |
| **Search** | Search tab → 输入关键词 | "找到所有跟 X 相关的记录" |
| **Trace** | Trace tab / 点击 🔗 链接 | "这个错误是怎么传播的？根因是什么？" |
| **Vault** | 点击任意记录展开 | "agent 当时实际输入/输出了什么？" |
| **Filter** | Activity tab → 选 agent/errors only | "只看某个 agent / 只看错误" |

---

## CLI 等效命令

Dashboard 的每个功能在 CLI 都有对应命令：

```bash
# 等效于 Overview → Detected Issues
atlast audit --days 60

# 等效于 Timeline
atlast timeline --days 30

# 等效于 Search
atlast search "SQL injection"
atlast search "error" --errors-only
atlast search "" --agent did:ecp:demo_research_agent

# 等效于 Trace（需要 record ID）
atlast trace rec_a585f735be5e4313 --direction back

# 所有命令加 --json 输出 JSON（给其他程序/agent 消费）
atlast audit --days 60 --json
```
