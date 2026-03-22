# Phase 6 剩余任务详细拆分 (2026-03-23 00:11 MYT)

> 30/47 已完成。剩余 17 tasks → 拆分为 42 个子任务。

---

## 🔴 优先级 1: 白皮书 v2.3 (A1-A6 + W1-W7)

### A1: ZH 白皮书 sync v2.2 内容
- [ ] A1.1: diff EN vs ZH 找出缺失段落
- [ ] A1.2: 补充 ZH 缺失内容（工作证书 mockup、用户旅程细节）
- [ ] A1.3: 验证 ZH 与 EN 关键段落一致

### A2: ZH Litepaper sync
- [ ] A2.1: 同步商业模式 4 层到 ZH
- [ ] A2.2: 同步 TAM $19B 数据到 ZH

### A3: Trust Score 章节 + W1-W7 合并
- [ ] A3.1 (W1): ATLAST=0-1000 独立标准说明（删除旧 500 base → W3）
- [ ] A3.2 (W2): LLaChat 定位为 Reference Application
- [ ] A3.3 (W4): 社交奖励归 LLaChat layer
- [ ] A3.4 (W5): chain_integrity 恒 1.0 注明（Phase 1）
- [ ] A3.5 (W6): 品牌名 "LLaChat" 全文统一检查
- [ ] A3.6 (W7): 新增 A2A Marketplace 章节 S11.4
- [ ] A3.7: 平台可组合说明 + Alex 维度映射示例
- [ ] A3.8: EN 完成后同步到 ZH

### A4: 全文最终逻辑审查
- [ ] A4.1: grep 扫描 `$X`, `TODO`, `TBD`, `placeholder`
- [ ] A4.2: 版本号一致性检查 (SDK v0.8.0, Server v1.0.0, TS v0.2.0)
- [ ] A4.3: 数据/数字一致性检查（TAM, Gas cost, etc）

### A5: 文档历史更新
- [ ] A5.1: EN+ZH 版本号更新为 v2.3
- [ ] A5.2: 文档历史条目添加

### A6: 备份
- [ ] A6.1: 复制到 Desktop
- [ ] A6.2: git commit + push

---

## 🟡 优先级 2: 标准化 + 文档 (B5-B7, E1, E2, E6)

### B5: ECP-SPEC v2.1
- [ ] B5.1: 添加 `in_hash`/`out_hash` 字段说明
- [ ] B5.2: 添加 `a2a_delegated` flag + `a2a_call` action type
- [ ] B5.3: 版本号更新为 v2.1

### B6: IETF Internet-Draft 评估
- [ ] B6.1: 研究 xml2rfc + I-D 提交流程
- [ ] B6.2: 写评估文档（不实际转换）

### B7: W3C VC/DID 映射
- [ ] B7.1: did:ecp ↔ W3C DID Core 映射表
- [ ] B7.2: ECP Record ↔ Verifiable Credential 映射表

### E1: SDK Quick Start 更新
- [ ] E1.1: 更新 README 反映 v0.8.0 (streaming, adapters, atlast run)

### E2: Server API Reference
- [ ] E2.1: 基于 OpenAPI 生成 11 端点文档

### E6: ZH README 同步
- [ ] E6.1: README.zh-CN.md 与 EN 版对齐

---

## 🟢 优先级 3: 收尾 (C2-C5, D10, F2, F3)

### C2-C5: 反滥用细节文档（已有 C1 总纲，补充细节）
- [ ] C2-C5.1: 在 anti-abuse-framework.md 中补充实现建议

### D10: CI 增强
- [ ] D10.1: CI 加 server tests
- [ ] D10.2: CI 加 coverage 上传

### F2: HMAC fail-closed 切换计划
- [ ] F2.1: 写切换计划文档（时间+测试方案）

### F3: Phase 6 完成后互验
- [ ] F3.1: 与 Alex 跑 E2E 全链路测试
- [ ] F3.2: 双方交叉验证

---

## 执行顺序

```
NOW → A3 (Trust Score + W1-W7) → A1 (ZH sync) → A2 (ZH litepaper) 
    → A4 (逻辑审查) → A5 (版本号) → A6 (备份+push)
    → B5 → E1 → E6 → E2 → B6 → B7
    → C2-C5 → D10 → F2 → F3 (最后)
```
