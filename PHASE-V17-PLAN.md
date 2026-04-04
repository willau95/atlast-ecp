# ATLAST v0.17.0 — Scoring Architecture Overhaul

## 目标
将 ATLAST SDK 从"客户端评分"架构升级为"客户端采集 + 服务端评分"架构。
确保上亿 agent 用户无需任何操作即可享受规则更新。

## 设计原则
1. **SDK 只采集，不评判** — flag 只描述事实，不做主观分类
2. **服务端规则引擎** — 所有评分/分类逻辑在服务端，改规则即时生效
3. **向后兼容** — v0.16 的 raw records 在新架构下完全可用
4. **Fail-Open 不变** — 任何新增逻辑失败都不影响 agent 运行
5. **零回归** — 每个任务完成后全量测试，813+ tests 不能减少

## 影响分析（改哪些文件）

| 文件 | 改动类型 | 风险 |
|------|---------|------|
| proxy.py | 改 flag 系统 + tool_use 检测 | 🟡 中（核心采集路径）|
| signals.py | 改 detect_flags 为事实性 flag | 🟡 中（影响所有记录）|
| core.py | record_minimal_v2 传递新 flag | 🟢 低 |
| query.py | 读 scoring_rules + 分类引擎 | 🟡 中（影响 stats/dashboard）|
| cli.py | stats 命令适配新分类 | 🟢 低 |
| storage.py | vault_extra 新增字段 | 🟢 低 |
| dashboard_server.py | API 返回新分类数据 | 🟢 低 |

### 不动的文件（确认安全）
- identity.py — DID/签名，不涉及
- batch.py — Merkle/上传，不涉及
- verify.py — 验证逻辑，不涉及
- wrap.py — wrap(client) 接口，不涉及
- record.py / proof.py / mcp_server.py — 不涉及

---

## 任务拆分

### Section A: SDK Flag 系统重构（事实性 Flag）
**目标**：把 signals.py 的主观判断 flag 改为客观事实 flag

- [ ] A1: 新增事实性 flag 常量定义
  - 文件: signals.py
  - 新增: `FLAG_HTTP_4XX`, `FLAG_HTTP_5XX`, `FLAG_STREAMING`, `FLAG_HAS_TOOL_CALLS`, `FLAG_TOOL_CONTINUATION`, `FLAG_EMPTY_OUTPUT`, `FLAG_EMPTY_INPUT`
  - 保留旧 flag 作为别名（向后兼容）
  
- [ ] A2: proxy.py 打事实性 flag
  - 文件: proxy.py `_record_ecp()`
  - 改动: 根据 HTTP status/response 内容打事实 flag
  - 新增: 检测 tool_use stop_reason → `has_tool_calls`
  - 新增: 检测 request 包含 tool_result → `tool_continuation`
  - 新增: 检测 response body 是 error JSON → `provider_error`
  - 测试: test_proxy_flags.py 新增 10+ 测试

- [ ] A3: proxy.py 检测 streaming tool_use
  - 文件: proxy.py `_handle_streaming()` + `_reconstruct_sse_content()`
  - 改动: 从 SSE stream 中提取 stop_reason/finish_reason
  - 返回: `(content, stop_reason)` 而非仅 `content`
  - 测试: test_proxy_streaming.py

- [ ] A4: proxy.py 提取 tool_call 内容到 vault
  - 文件: proxy.py `_reconstruct_sse_content()`
  - 改动: 除了 text content，也提取 tool_use name/input
  - vault 新增: `tool_calls: [{name, input}]`
  - 这样 tool_call 轮的 output 不再为空

- [ ] A5: 全量回归测试
  - 运行 813 tests，确保零 failure
  - 特别验证: signals.py 旧 flag 名仍然兼容

### Section B: Heartbeat 检测（Proxy 层）
**目标**：在 proxy 层自动识别 heartbeat 并打 flag

- [ ] B1: heartbeat 检测逻辑
  - 文件: proxy.py `_record_ecp()`
  - 逻辑: input 包含 "HEARTBEAT" 且 output 长度 < 100 → flag `heartbeat`
  - 也检测: output 是 "HEARTBEAT_OK" → flag `heartbeat`
  - 测试: test_heartbeat_detection.py

- [ ] B2: query.py stats 排除 heartbeat
  - 文件: query.py `list_agents()` + `daily_stats()`
  - 改动: WHERE 条件增加 `flags NOT LIKE '%heartbeat%'` (用于 interaction 统计)
  - 新增: 返回 `heartbeat_count` 字段
  - 测试: test_query_heartbeat.py

- [ ] B3: CLI stats 显示 heartbeat 统计
  - 文件: cli.py `stats` 命令
  - 改动: 显示 "Heartbeats: 48 (excluded from scoring)"
  - 测试: 手动验证

- [ ] B4: 全量回归测试

### Section C: Error 分类扩展（Proxy 层）
**目标**：覆盖更多 "不是 agent 的错" 的场景

- [ ] C1: 扩展 provider_error 检测
  - 文件: proxy.py
  - 新增检测: Anthropic billing error, quota exceeded, API key invalid
  - 新增 flag: `provider_error` (事实性，不做分类)
  - 保留 vault_extra: `error_body` 存原始错误 JSON
  - 测试: test_provider_errors.py

- [ ] C2: 扩展 HTTP status 覆盖
  - 文件: proxy.py `INFRA_STATUSES`
  - 新增: 401 → `http_401`, 403 → `http_403`
  - 不再用 `infra_error` 这种分类名，改用事实: `http_429`, `http_500` 等
  - 测试: test_http_status_flags.py

- [ ] C3: 全量回归测试

### Section D: 服务端 Scoring Rules 引擎
**目标**：在 ECP Server 实现规则引擎，所有分类/评分逻辑在此

- [ ] D1: 定义 scoring_rules.json schema
  - 文件: 新建 `sdk/python/atlast_ecp/scoring_rules.py`
  - 内容: DEFAULT_RULES dict（内置默认规则）
  - 规则格式: exclude_flags, not_agent_fault patterns, scoring formula

- [ ] D2: 实现 classify_record() 函数
  - 文件: scoring_rules.py
  - 输入: raw record (flags, input, output, http_status)
  - 输出: classification (heartbeat|system_error|infra_error|tool_intermediate|interaction)
  - 逻辑: 遍历规则，匹配 flag/pattern → 返回分类
  - 测试: test_scoring_rules.py 30+ 测试覆盖所有分类场景

- [ ] D3: 实现 calculate_score() 函数
  - 文件: scoring_rules.py
  - 输入: list of classified records
  - 输出: {reliability, hedge_rate, avg_latency, interaction_count, excluded_count}
  - 排除: classification != "interaction" 的记录不参与评分
  - 测试: test_scoring_calculation.py

- [ ] D4: query.py 接入 scoring_rules
  - 文件: query.py
  - 改动: list_agents() 和 daily_stats() 使用 classify_record()
  - 确保: 旧的 `is_infra` 逻辑被新的 classification 取代
  - 向后兼容: is_infra 字段仍然存在，值从 classification 派生

- [ ] D5: 本地规则缓存（从服务端拉取）
  - 文件: scoring_rules.py
  - 逻辑: `get_rules()` → 先查本地缓存 → 过期则从 api.weba0.com 拉取 → fallback 到内置默认
  - 缓存文件: `~/.ecp/scoring_rules_cache.json`
  - 缓存有效期: 24 小时
  - Fail-Open: 拉取失败用内置默认，不影响任何功能

- [ ] D6: ECP Server 新增 `/v1/scoring/rules` API
  - 文件: server 端（需要更新 Railway 部署）
  - 返回: 当前生效的 scoring_rules JSON
  - 认证: 无需认证（公开规则）

- [ ] D7: 全量回归测试 + 交叉验证
  - 用 Elena 的 9 条记录验证分类结果
  - 用 Stress Test v3 的 4480 条记录验证分数不退化

### Section E: Tool Use Interaction 聚合
**目标**：同一个 tool chain 的多次 API call 聚合为一个 interaction

- [ ] E1: proxy.py 检测 tool chain
  - 文件: proxy.py
  - 新增: `_pending_chains: dict[session_id, PendingChain]`
  - 逻辑: stop_reason == "tool_use" → 暂存，标记 `tool_chain_id`
  - 下一个请求 contains tool_result + same session → 继续链
  - stop_reason == "end_turn" → 链结束，写入最终记录
  - 安全: 超时 5 分钟自动 flush（防止永远 pending）

- [ ] E2: vault 聚合格式
  - 文件: storage.py `save_vault_v2()`
  - 新增字段:
    ```json
    {
      "interaction_id": "int_xxx",
      "tool_steps": [
        {"step": 1, "tool": "read_file", "input": "...", "output_preview": "..."},
        {"step": 2, "tool": "write_file", "input": "..."}
      ],
      "total_api_calls": 3,
      "total_latency_ms": 86000,
      "raw_record_ids": ["rec_001", "rec_002", "rec_003"]
    }
    ```
  - raw records 仍然独立存在（审计完整性）

- [ ] E3: query.py interaction 视图
  - 文件: query.py
  - 新增: `list_interactions()` — 聚合同一 tool_chain_id 的记录
  - stats 计算基于 interaction 而非 raw record
  - 向后兼容: 无 tool_chain_id 的旧记录 = 独立 interaction

- [ ] E4: Dashboard interaction 展示
  - 文件: dashboard_server.py
  - 改动: /api/timeline 返回 interaction 级别数据
  - 展开: 每个 interaction 可展开查看 tool_steps

- [ ] E5: 全量回归测试
  - 确保无 tool_use 的普通对话不受影响
  - 测试 edge case: 单步无 tool / 20 步长链 / 并发 session

### Section F: 部署 + Mac Mini 验证
**目标**：部署到 Mac Mini，用 Elena 验证端到端

- [ ] F1: PyPI 发布 v0.17.0
  - GitHub Release + Trusted Publishing
  
- [ ] F2: Mac Mini 升级
  - fleet-ssh 1 "pipx upgrade atlast-ecp"
  
- [ ] F3: Elena 端到端验证
  - 和 Elena 聊 3 轮（含 tool use）
  - 检查: heartbeat 被标记、tool chain 被聚合、score 正确

- [ ] F4: 存最终状态到 memory

---

## 执行顺序（依赖关系）

```
A1 → A2 → A3 → A4 → A5(回归)
       ↓
B1 → B2 → B3 → B4(回归)
       ↓
C1 → C2 → C3(回归)
       ↓
D1 → D2 → D3 → D4 → D5 → D6 → D7(回归+交叉验证)
                              ↓
E1 → E2 → E3 → E4 → E5(回归)
                         ↓
F1 → F2 → F3 → F4
```

A→B→C 可以连续做（都是 proxy 层改动）
D 依赖 A（需要事实性 flag）
E 依赖 A3（需要 tool_use 检测）
F 依赖全部

预估时间: A(2h) + B(1h) + C(1h) + D(3h) + E(3h) + F(1h) = ~11h
