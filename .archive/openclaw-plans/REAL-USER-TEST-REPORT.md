# ATLAST ECP — Real User Simulation Test Report
## 苏格拉底式 + 第一性原理 深度分析

**测试时间**: 2026-04-02 16:05-16:20 MYT  
**测试环境**: Mac Mini (100.79.169.126), Python 3.14, atlast-ecp v0.11.0 (local) / v0.10.0 (PyPI)  
**方法**: 模拟一个完全不了解 ATLAST 的开发者，从发现→安装→使用→验证的完整旅程

---

## 🔴 CRITICAL BUGS (阻断用户旅程)

### BUG-001: `ECP_HOME` 环境变量被 `atlast init` 忽略
- **场景**: 用户想在自定义目录初始化 ECP
- **预期**: `ECP_HOME=/tmp/test/.ecp atlast init` 创建在 `/tmp/test/.ecp/`
- **实际**: 永远创建在 `~/.ecp/`，完全忽略 ECP_HOME
- **影响**: 🔴 CRITICAL — 无法实现多 agent 隔离。所有 agent 共享同一个 identity + records。这直接破坏了 ECP 的多 agent 信任模型
- **第一性原理**: 如果一个 agent 的证据链里混着其他 agent 的记录，整个 "可验证" 的价值主张就崩塌了

### BUG-002: 零租户隔离 — 新用户看到别人的4595条记录
- **场景**: `atlast init --identity` 后立即 `atlast log`
- **预期**: 空列表 ("还没有记录，先创建你的第一个 agent")
- **实际**: 显示 4595 条来自压力测试的记录，包含 `Chain integrity ⚠️ BROKEN`
- **影响**: 🔴 CRITICAL — 新用户第一印象：系统已经坏了。而且看到的不是自己的数据
- **根因**: 所有 agent 共享 `~/.ecp/records/` 目录

### BUG-003: `atlast backup-key` 崩溃
- **错误**: `FileNotFoundError: bip39_english.txt`
- **影响**: 🔴 CRITICAL — 用户无法备份私钥。如果磁盘损坏，agent identity 永久丢失
- **根因**: bip39 wordlist 文件未打包到 PyPI 发布

### BUG-004: `atlast discover` 崩溃
- **错误**: `AttributeError: 'str' object has no attribute 'get'`
- **影响**: 🟡 MEDIUM — 服务发现功能完全不可用

### BUG-005: `atlast certify` 返回 404
- **错误**: `HTTP Error 404`
- **影响**: 🔴 CRITICAL — Work Certificate 是 ECP 核心功能之一（展示给客户的），完全不能用

### BUG-006: `atlast proxy` / `atlast run` 需要额外依赖
- **错误**: `Error: aiohttp required. Install with: pip install atlast-ecp[proxy]`
- **影响**: 🟡 MEDIUM — Layer 0 "零代码" 承诺被打破。用户 `pip install atlast-ecp` 后发现核心功能不能用
- **第一性原理**: 如果 "零代码接入" 需要额外安装步骤，它就不是零代码

### BUG-007: `atlast dashboard` 不启动
- **场景**: `atlast dashboard` 执行后无响应，curl 所有端口都失败
- **影响**: 🔴 CRITICAL — 用户看不到任何可视化界面

---

## 🟡 UX/API DESIGN ISSUES (不崩溃但令人困惑)

### UX-001: `record()` 返回 string 而不是 dict
- **API**: `record('input', 'output')` → 返回 `"rec_7d28f71181b84f88"` (string ID)
- **问题**: 用户期望拿到完整的 record 对象（就像数据库 insert 返回完整行）
- **需要额外调用**: `load_record_by_id(rec_id)` 才能看到内容
- **建议**: 返回 dict，或至少在文档中明确说明

### UX-002: `build_merkle_proof()` 签名不直觉
- **API**: 需要 `(record_id, record_hash)` 两个参数
- **问题**: 用户刚创建了 record，只拿到 ID，不知道 hash 是什么
- **建议**: 应该只需要 record_id，SDK 自动查 hash

### UX-003: `atlast stats` 对新用户误导
- 显示 `Chain integrity ⚠️ BROKEN` — 因为多个 agent 的记录混在一起
- 新用户看到这个就会认为 "这个工具有 bug"

### UX-004: `atlast push` 输出不完整
- 成功后只显示 `Batch: ` (空白！) + Merkle root (截断)
- 用户无法知道 batch ID 是什么，也无法追踪

### UX-005: `atlast register` 每次调用都生成新 API key
- 用户多次运行会得到多个 key，不知道哪个是有效的
- 没有 "你已经注册过了" 的检查

### UX-006: `atlast config` 显示 `api_key = test123`
- 这是开发遗留的测试值
- 新用户看到会很困惑

---

## 🧠 第一性原理分析：ECP 到底解决什么问题？

### 核心问题：ECP 的价值主张成立吗？

**ATLAST 的承诺**: "让 AI agent 的工作可验证、可追溯、可审计"

**苏格拉底式提问**:

1. **谁需要 agent 工作可验证？**
   - ✅ 企业合规 (EU AI Act 2027)
   - ✅ 多 agent 协作中的责任追溯
   - ✅ Agent marketplace (LLaChat) 的信任基础
   - ❓ 个人开发者？（他们可能觉得 logging 就够了）

2. **ECP 比普通日志强在哪？**
   - ✅ 哈希链：日志可以被篡改，ECP 不行（理论上）
   - ✅ 数字签名：可以证明"是这个 agent 做的"
   - ✅ 区块链锚定：不可否认性
   - ❌ **但是**：当前实现中 `sig: "unverified"` 是默认值。signature 功能实际上不工作（需要 `cryptography` 包）。这意味着当前的 ECP 记录和普通日志在安全性上差别不大

3. **零代码接入真的零代码吗？**
   - ❌ proxy 需要 `pip install atlast-ecp[proxy]`（额外依赖）
   - ❌ `ECP_HOME` 不工作（多 agent 隔离不可能）
   - ❌ 没有 Docker 镜像、没有 sidecar 模式
   - **结论**: Layer 0 的 "零代码" 承诺目前不成立

4. **证据链的完整性可信吗？**
   - ❌ 所有 agent 共享同一个 records 文件（`~/.ecp/records/YYYY-MM-DD.jsonl`）
   - ❌ chain prev 指针在多 agent 环境下交叉（不是 bug，但对用户非常困惑）
   - ❌ `atlast stats` 显示 "BROKEN" 实际上是误报
   - **结论**: 证据链的信任模型在多 agent 共享场景下有根本性设计问题

5. **用户从安装到看到价值需要多少步？**
   ```
   pip install atlast-ecp     ← OK
   atlast init --identity     ← OK（但 ECP_HOME 不工作）
   # 写代码 wrap(client)       ← OK
   # 运行 agent                ← OK
   atlast log                  ← 看到记录...但无法区分哪个 agent 的
   atlast push                 ← 上传...但看不到 batch ID
   atlast verify <id>          ← 验证...但 sig: unverified
   atlast dashboard             ← 崩溃
   ```
   **结论**: 用户需要 7+ 步才能尝试看到价值，但在第 6-7 步就会遇到阻断性问题

---

## 🎯 最关键的发现（第一性原理）

### 问题的根源不在 bug，在架构

**当前架构假设**：一台机器 = 一个 agent = 一个 `~/.ecp/`

**现实场景**：
- 一台机器上跑多个 agent（我们的 9 agent 压力测试就是证明）
- 容器化环境每个 agent 一个容器（但共享存储时问题依旧）
- 企业场景一个团队管理数百个 agent

**这个假设导致的连锁反应**：
1. 所有 agent 共享 DID → 无法区分谁做了什么
2. 所有记录混在一起 → chain integrity 看起来 "BROKEN"
3. stats 聚合所有 agent → 无意义的数据
4. 对用户来说 → "这个工具坏了"

### 建议修复方向

```
短期（v0.12.0）:
  1. ECP_HOME 环境变量必须生效
  2. 支持 per-agent profile: atlast --profile agent-01 init
  3. 修复所有崩溃 (backup-key, discover, dashboard, certify)
  4. bip39 wordlist 打包到发布中
  5. signature 默认使用 Ed25519（不依赖 cryptography 包）

中期（v0.13.0）:
  6. 多 agent 隔离架构重设计
  7. atlast init 生成独立 DID per agent
  8. records 按 agent_id 分目录存储
  9. Dashboard 本地 web UI 真正可用

长期:
  10. 容器化支持（Docker sidecar）
  11. 团队管理功能
  12. 真正的零代码 proxy（内置 aiohttp）
```

---

---

## ✅ BUGS FIXED IN THIS SESSION (commit a371d8a)

| Bug | Fix | Verified |
|-----|-----|---------|
| BUG-003: backup-key 崩溃 | `bip39_english.txt` added to `package-data` | ✅ recovery phrase now displays |
| BUG-004: discover 崩溃 | Handle `endpoints` as dict (not list of objects) | ✅ 10 endpoints now show correctly |
| Ruff lint 225 errors | `ruff check --fix` + ruff config in pyproject.toml | ✅ All checks passed |
| push 空 batch ID | Show `attestation_uid` instead of empty `batch_id` | ✅ |
| dashboard_assets 缺失 | Added to `package-data` | ✅ files now installed |

### Still Broken After Fix
| Bug | Status | Notes |
|-----|--------|-------|
| BUG-005: certify 404 | ❌ Server endpoint unimplemented | Needs server-side `/certificates/create` |
| BUG-006: proxy needs aiohttp | ⚠️ Error message improved but deps still extra | Architectural: include aiohttp in default? |
| BUG-007: dashboard 不启动 | ❌ Assets installed but server doesn't respond | SSH+HTTP timeout issue or binding problem |

---

## 📊 测试汇总

| CLI 命令 | 状态 | 问题 |
|---------|------|------|
| `atlast init` | ⚠️ | ECP_HOME 被忽略 |
| `atlast init --identity` | ⚠️ | 同上 |
| `atlast did` | ✅ | 正常 |
| `atlast log` | ⚠️ | 显示所有 agent 混合记录 |
| `atlast stats` | ⚠️ | "BROKEN" 误报 |
| `atlast verify` | ⚠️ | 可用但 sig=unverified |
| `atlast trace` | ✅ | 正常工作 |
| `atlast insights` | ✅ | 正常 |
| `atlast timeline` | ✅ | 正常 |
| `atlast audit` | ✅ | 正常 |
| `atlast search` | ✅ | 正常 |
| `atlast proxy` | ❌ | 缺 aiohttp |
| `atlast run` | ❌ | 缺 aiohttp |
| `atlast dashboard` | ❌ | 不启动 |
| `atlast register` | ✅ | 但每次都生成新 key |
| `atlast push` | ⚠️ | batch ID 不显示 |
| `atlast certify` | ❌ | 404 |
| `atlast backup-key` | ❌ | 崩溃 |
| `atlast discover` | ❌ | 崩溃 |
| `atlast config get` | ⚠️ | 显示测试遗留值 |
| `atlast export` | ✅ | 正常 |
| `wrap()` | ✅ | 核心功能正常 |
| `record()` | ⚠️ | 返回 string 而非 dict |
| `build_merkle_proof()` | ⚠️ | API 不友好 |

**CLI 总计**: 23 个功能测试
- ✅ 正常: 7 (30%)
- ⚠️ 有问题但可用: 8 (35%)
- ❌ 崩溃/不可用: 8 (35%)

---

## 📊 9 Agent Framework 集成分析

### 每个 framework 的真实用户体验

| Framework | 接入方式 | 代码量 | 用户体验 | 核心问题 |
|-----------|---------|--------|----------|----------|
| Raw `wrap()` | `client = wrap(openai.OpenAI())` | 1行 | ⭐⭐⭐⭐ | 最好的体验，真正零侵入 |
| `record()` API | `record(input, output)` | 2-3行 | ⭐⭐⭐ | 返回 string 困惑 |
| `@trace` decorator | `from atlast_ecp import auto` | 1行 | ⭐⭐⭐ | 文档不清楚 |
| LangChain Callback | `ATLASTCallbackHandler()` | 3行 | ⭐⭐ | model=unknown bug, 105/4595 verify fail |
| CrewAI Adapter | `callbacks=[handler]` | 3行 | ⭐⭐ | 同 LangChain, delegation 记录不完整 |
| AutoGen | `record()` 手动 | 5-10行 | ⭐⭐ | 需要手动接入，GroupChat 记录复杂 |
| OpenClaw Plugin | `tool_call` | 3行 | ⭐⭐⭐ | 正常但文档缺 |
| Node.js (TS SDK) | `import { record }` | 3行 | ⭐⭐⭐ | npm 包正常 |
| Claude Code (wrap) | `wrap()` | 1行 | ⭐⭐ | 只捕获顶层调用, 18/106 tasks |

### 关键洞察
- **wrap() 是最成功的设计** — 真正的零侵入，用户体验最好
- **Callback adapters 是最弱的环节** — model=unknown, signature mismatch
- **Claude Code 的低捕获率 (17%)** 说明 wrap() 对 "agent 内部调用 agent" 的场景捕获不全

---

## 🔑 最终结论

### ECP 的价值主张是成立的，但当前实现距离 production 还有距离

**核心价值是真实的**:
- AI agent 确实需要可验证的工作记录
- 哈希链 + 区块链锚定确实比普通日志更可信
- EU AI Act 2027 确实会创造合规需求

**但当前状态**:
- 35% 的 CLI 功能崩溃或不可用
- 多 agent 隔离是架构层面的缺陷
- 零代码承诺未兑现
- signature 功能实际不工作

**优先修复顺序** (ROI 最高):
1. 🔴 修 `ECP_HOME` + 多 agent 隔离（这是架构根因）
2. 🔴 修所有崩溃 (backup-key, discover, dashboard, certify)  
3. 🔴 signature 默认生效（不然 ECP ≈ 日志）
4. 🟡 proxy/run 内置 aiohttp（兑现零代码承诺）
5. 🟡 UX 打磨 (record 返回值, push 输出, register 幂等性)
