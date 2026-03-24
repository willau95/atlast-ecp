# ATLAST ECP — Critical Fix Long-Term Architecture Plan

> **创建时间**: 2026-03-24 20:40 MYT  
> **目标**: 3 个 Critical 问题的长期解决方案，确保 50k 用户 Day-1 安全运行  
> **原则**: 用户零维护、ATLAST 后台默默工作、不增加任何用户操作

---

## 设计哲学

ATLAST 的核心体验承诺是：**用户 `atlast init` 一次，之后再也不用管。** 
SDK 在后台静默运行，记录 → 批量 → 上链。用户不需要知道 gas、nonce、EAS、RPC 这些细节。

这意味着我们的容错体系必须做到：
1. **永远不丢数据** — 链上暂时不可用时，数据安全地排队等待
2. **永远不假装成功** — 不存在"静默降级到假数据"的情况
3. **永远不需要用户介入** — 自动重试、自动恢复、自动告警给运维（不是用户）
4. **永远不阻塞用户工作** — ECP 层的任何问题都不影响 agent 的正常 LLM 调用

---

## C1. EAS 锚定可靠性架构（取代 Fail-Open to Stub）

### 问题本质

不是 "Fail-Open vs Fail-Closed" 这么简单。真正的问题是：**当链上不可用时，系统怎么做才能既不丢数据、又不骗用户、又不需要用户介入？**

### 长期方案：三态批次生命周期 + 自动恢复

```
Batch 状态机：

  pending ──→ anchoring ──→ anchored ✅
     │            │
     │            └──→ retry_queued ──→ anchoring (下一个 cron 周期)
     │                      │
     │                      └──→ (超过 max_retries) ──→ anchor_failed ❌
     │
     └──→ (永远不直接跳到 anchored)
```

**核心改动：**

1. **删除 stub fallback 路径** — `eas.py` 不再在 live 失败后回退 stub
2. **新增 `anchoring` 中间态** — 防止 cron 重复处理同一批次
3. **新增 `retry_queued` 状态** — 明确标记等待重试的批次
4. **新增 `anchor_failed` 终态** — 重试 N 次后标记失败，Sentry 告警
5. **保留 stub mode** — 仅用于 `EAS_STUB_MODE=true`（开发/测试），production 永远不触发

**重试策略：**
```
第 1 次失败 → retry_queued, 下个 cron 周期重试 (60min)
第 2 次失败 → retry_queued, backoff 120min
第 3 次失败 → retry_queued, backoff 240min  
第 4 次失败 → anchor_failed + Sentry CRITICAL alert
```

**为什么不影响用户体验：**
- SDK 侧 `upload_merkle_root()` 返回 `batch_id`，不返回 `attestation_uid`（已经是这样）
- 用户的数据已经安全存在 server DB 中，链上锚定是异步后台操作
- SDK 不需要知道 batch 是 pending 还是 anchored — 这是 server 的事
- 即使 EAS 停机 24 小时，用户的 agent 正常工作，数据排队等恢复后自动锚定

**Gas 不足的特殊处理：**
```
检测: eth_getBalance < MIN_BALANCE (0.0005 ETH)
→ 暂停所有锚定尝试（避免浪费 gas 在必然失败的 tx 上）
→ 所有 batch 保持 pending/retry_queued
→ Sentry alert: "ATLAST: Gas critically low, anchoring paused"
→ 恢复条件: 余额 > MIN_BALANCE 时自动恢复
```

**数据结构改动：**
- `Batch` 模型新增 `retry_count` (Integer, default=0)
- `Batch` 模型新增 `last_retry_at` (TIMESTAMP, nullable)
- `Batch` 模型新增 `error_message` (Text, nullable)

---

## C2. 认证体系架构（取代 Fail-Open 无认证）

### 问题本质

不只是"加个 401 reject"这么简单。需要考虑：
- 新用户第一次 `atlast push` 时还没有 API key（先注册后上传有时序依赖）
- SDK auto-registration 可能失败（网络问题）
- 用户"零维护"承诺 = 不能让用户手动 register 然后复制 key

### 长期方案：双层认证 + 自动注册流水线

```
Layer 1: API Key 认证（标准路径）
  SDK atlast init → 自动注册 → 获得 ak_live_xxx → 存入 ~/.atlast/config.json
  后续所有请求带 X-API-Key header → server 验证

Layer 2: DID 签名认证（fallback 路径）
  如果 API key 还没拿到（注册失败 / 首次上传竞争条件）：
  SDK 用 ed25519 私钥签名 request body → X-DID-Signature header
  Server 验证: 查 agents 表的 public_key → 验证签名
  
  如果 DID 还没注册（真正的第一次）：
  → 返回 401 + {"error": "agent_not_registered", "register_url": "/v1/agents/register"}
  → SDK 自动触发注册 → 重试上传（已有此逻辑，只需确保同步）
```

**为什么这样设计：**
1. **99% 的请求走 Layer 1** — API key 在 init 时自动获取，性能最优
2. **Layer 2 覆盖边缘情况** — 首次上传时注册还没完成（网络延迟）
3. **永远不接受匿名请求** — Production 环境下无认证 = 401
4. **不增加用户操作** — `atlast init` 自动搞定一切

**Anti-abuse 防护：**
```
/v1/agents/register:
  - Rate limit: 5/min per IP（防批量注册）
  - 必须提供有效 ed25519 public key
  - Server 验证 DID = sha256(public_key)[:32] 匹配

/v1/batches:
  - 验证 API key 的 agent_did == request body 的 agent_did（已有）
  - Rate limit per agent: free tier 10 batches/hour
  - Max payload size: 10MB（已有）
```

**DID 匹配验证（防冒充）：**
```python
# Server 侧验证 agent_did 与 API key 绑定
# 已有此逻辑，只需从 warning → reject：
if agent_did != req.agent_did:
    raise HTTPException(403, "API key does not match agent_did")
```

---

## C3. 交易并发安全架构（Nonce Manager）

### 问题本质

不是简单加个锁。需要处理：
1. 正常 cron 周期不重叠（锁）
2. 手动 `anchor-now` 和 cron 同时触发（锁）
3. 交易发送后 RPC 超时但交易已上链（nonce 已消耗但我们不知道）
4. 交易 pending 太久被替换（nonce reuse）
5. Railway 部署更新时旧实例和新实例短暂并存（分布式锁）

### 长期方案：单线程锚定 + Nonce Tracker + 交易状态机

```
┌────────────────────────────────────────────────────┐
│              Anchor Coordinator                      │
│                                                      │
│  asyncio.Lock() ← 保证同一进程只有一个锚定在执行    │
│                                                      │
│  DB anchor_lock table ← 保证多实例不冲突            │
│  (distributed lock with TTL)                         │
│                                                      │
│  Nonce Tracker:                                      │
│    1. 从 DB 读上次成功的 nonce                       │
│    2. 与链上 getTransactionCount 取 max              │
│    3. 使用较大值作为下一个 nonce                     │
│    4. 成功后存回 DB                                  │
│                                                      │
│  Transaction State Machine:                          │
│    tx_pending → tx_confirmed (receipt.status=1)      │
│    tx_pending → tx_failed (receipt.status=0)         │
│    tx_pending → tx_timeout (30s no receipt)           │
│      → 检查链上 nonce 是否已消耗                     │
│      → 如已消耗: 尝试获取 receipt (可能 RPC 延迟)   │
│      → 如未消耗: 标记失败, batch 回退到 retry_queued │
└────────────────────────────────────────────────────┘
```

**具体实现：**

```python
# server/app/services/anchor_coordinator.py

import asyncio
from datetime import datetime, timezone

_anchor_lock = asyncio.Lock()

async def acquire_anchor_lock() -> bool:
    """Process-level lock + DB distributed lock."""
    if _anchor_lock.locked():
        return False  # Another anchor is running
    # DB-level: INSERT INTO anchor_locks (id, acquired_at, ttl_seconds)
    # ON CONFLICT DO NOTHING — if row exists and not expired, someone else holds it
    ...

async def get_next_nonce(w3, account_address: str) -> int:
    """Reliable nonce: max(chain_nonce, db_last_nonce + 1)."""
    chain_nonce = await asyncio.to_thread(
        w3.eth.get_transaction_count, account_address
    )
    db_nonce = await _get_db_nonce()  # from anchor_state table
    return max(chain_nonce, db_nonce + 1) if db_nonce is not None else chain_nonce

async def confirm_transaction(w3, tx_hash, timeout=30) -> dict:
    """Wait for receipt with timeout, handle edge cases."""
    try:
        receipt = await asyncio.to_thread(
            w3.eth.wait_for_transaction_receipt, tx_hash, timeout=timeout
        )
        if receipt['status'] == 1:
            await _save_db_nonce(receipt['nonce'])  # track successful nonce
            return {"status": "confirmed", "receipt": receipt}
        else:
            return {"status": "reverted", "receipt": receipt}
    except Exception:
        # Timeout — check if nonce was consumed
        chain_nonce = await asyncio.to_thread(
            w3.eth.get_transaction_count, account_address
        )
        # If chain nonce advanced, tx might have succeeded — need to query by nonce
        return {"status": "timeout", "chain_nonce": chain_nonce}
```

**Railway 多实例防护：**
Railway 部署是 rolling deploy，短暂时间两个实例并存。DB-level lock 防止两个实例同时锚定：

```sql
CREATE TABLE IF NOT EXISTS anchor_lock (
    id VARCHAR(32) PRIMARY KEY DEFAULT 'singleton',
    instance_id VARCHAR(64) NOT NULL,
    acquired_at TIMESTAMPTZ NOT NULL,
    ttl_seconds INTEGER DEFAULT 300
);

-- 获取锁（只在没有锁或锁已过期时成功）
INSERT INTO anchor_lock (id, instance_id, acquired_at)
VALUES ('singleton', $1, NOW())
ON CONFLICT (id) DO UPDATE 
SET instance_id = $1, acquired_at = NOW()
WHERE anchor_lock.acquired_at + (anchor_lock.ttl_seconds || ' seconds')::INTERVAL < NOW();
```

**为什么不影响用户体验：**
- 所有这些都是 server 内部机制，SDK 完全无感知
- 即使锁竞争导致某次 cron 跳过，下一次会处理所有 pending batch
- Nonce 冲突不会导致数据丢失，只是延迟锚定

---

## 三个 Critical 的交叉影响

C1 + C2 + C3 不是独立的，它们形成一个完整的安全链：

```
用户 SDK → [C2: 认证] → Server DB (pending)
                              ↓
                     [C3: Nonce Manager + Lock]
                              ↓
                     [C1: EAS 写入 + 重试]
                              ↓
                     anchored / retry_queued / anchor_failed
```

**统一错误处理原则：**
- SDK → Server 失败: SDK 本地排队，下个周期重试（已有）
- Server → EAS 失败: Server DB 排队，下个 cron 重试（C1 改进）
- EAS nonce 冲突: Coordinator 重算 nonce 重试（C3 改进）
- 恶意请求: 认证拒绝 + rate limit（C2 改进）

**在任何环节，用户的 agent 都不受影响。**

---

## 实现计划

### Phase 1: C1 — EAS 可靠性 (~2h)

```
1. eas.py: 删除 stub fallback，失败直接 raise
2. anchor.py: 捕获 EAS 异常 → batch.retry_count += 1
3. models.py: Batch 新增 retry_count, last_retry_at, error_message
4. database.py: _run_migrations() 添加 ALTER TABLE 
5. anchor.py: 重试逻辑 — retry_count < 4 → retry_queued, ≥ 4 → anchor_failed
6. anchor.py: gas 余额检查 — 低于阈值暂停锚定
7. 测试: 5-6 个新测试覆盖重试/失败/gas不足场景
```

### Phase 2: C2 — 认证强化 (~1.5h)

```
1. batches.py: Production 强制 API key（删除 fail-open）
2. batches.py: 添加 DID 签名 fallback 认证
3. agents.py: /register 加 rate limit 5/min per IP
4. 测试: 无认证 → 401, DID 签名 → 200, 冒充 DID → 403
```

### Phase 3: C3 — 并发安全 (~2h)

```
1. 新建 server/app/services/anchor_coordinator.py
2. asyncio.Lock + DB distributed lock
3. Nonce tracker (DB-backed)
4. eas.py: _send_tx 使用 coordinator 的 nonce
5. anchor.py: 所有锚定通过 coordinator
6. models.py: AnchorState 模型 (nonce tracking)
7. database.py: anchor_lock + anchor_state 表
8. 测试: 并发锚定测试 + nonce 恢复测试
```

### Phase 4: 集成验证 (~30min)

```
1. 全量 server 测试通过
2. SDK 测试不受影响（SDK 不依赖 server 内部改动）
3. commit + push
```

**总预估: 6 小时**

---

## 验证标准

修完后必须满足：

| # | 场景 | 预期行为 |
|---|------|---------|
| 1 | EAS RPC 超时 | batch 保持 pending, 下次 cron 重试 |
| 2 | EAS gas 不足 | 所有 batch 保持 pending, Sentry alert, gas 恢复后自动继续 |
| 3 | EAS 合约升级 | 连续失败 → anchor_failed, Sentry CRITICAL |
| 4 | 无 API key 的 batch 请求 | 401 reject |
| 5 | 冒充他人 DID | 403 reject |
| 6 | 两个 anchor-now 同时触发 | 只有一个执行，另一个跳过 |
| 7 | 部署更新时 cron 正在跑 | DB lock 防止新实例冲突 |
| 8 | 用户 agent 正常使用 | 完全无感知，0 影响 |
