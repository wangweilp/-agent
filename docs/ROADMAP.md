# Roadmap: 记忆进化型个人知识助手

## 版本策略
- 每个版本独立可交付，有明确验收标准
- 优先级分为三级：P0（必须）、P1（重要）、P2（高级）
- 任何架构变更必须先写 ADR
- **防回归约束**：升级到新版时，旧版的全部测试必须仍然通过

---

## P0 — 第一优先级（当前必须）

### v0.1 — 真 Agent（真 Tool Calling + 真 Embedding + Context Builder）

**目标**：一个真正的 Agent，不是伪 Agent。

**验收**：
- [ ] 使用 OpenAI Tool Calling API（非 JSON 字符串解析）
- [ ] 本地 bge-small-zh-v1.5 embedding
- [ ] ChromaDB + SQLite 双写
- [ ] Context Builder（动态组装，非全量历史）
- [ ] recall 语义搜索（非 LIKE）
- [ ] 终端 CLI 交互
- [ ] 流式输出

**提交清单**：
```
[ ] feat(core): define rich Memory model (importance, memory_type, etc.)
[ ] feat(core): define MemoryStore, VectorStore, LLMProvider protocols
[ ] feat(core): implement Tool Calling agent loop
[ ] feat(core): implement Context Builder
[ ] feat(core): add System Prompt with safety guardrails
[ ] feat(adapters): implement DeepSeek adapter with tool calling support
[ ] feat(adapters): implement local embedding (bge-small-zh-v1.5)
[ ] feat(adapters): implement ChromaDB vector store
[ ] feat(adapters): implement SQLite store (rich schema)
[ ] feat(tools): implement remember tool (with importance scoring)
[ ] feat(tools): implement recall tool (semantic search + RRF)
[ ] feat(tools): implement tool registry with permission layer
[ ] feat(api): implement /chat endpoint with SSE streaming
[ ] feat(tools): implement CLI interface
[ ] test: all core and adapter tests
```

**不包含**：Web UI、周报、知识图谱、Memory Consolidation

---

## P1 — 第二优先级（下一步）

### v0.2 — Memory Consolidation + Reflection

**目标**：Agent 能自我反思和重组知识。

**验收**：
- [ ] reflect 工具可用，Agent 能自我检查矛盾
- [ ] Memory Consolidation 每日检查，发现认知模式
- [ ] 自动提示：「你正在形成『XX』认知模型」
- [ ] 记忆衰减（旧记忆 importance 自动降低）

**提交清单**：
```
[ ] feat(core): implement consolidation.py
[ ] feat(core): implement importance decay logic
[ ] feat(tools): implement reflect tool
[ ] feat(tools): implement consolidate trigger
[ ] test: consolidation and reflection tests
[ ] docs: ADR for consolidation algorithm
```

---

### v0.3 — 知识图谱 + 实体关系

**目标**：提取实体关系，构建知识图谱。

**验收**：
- [ ] 存储记忆时自动提取实体（DeepSeek few-shot）
- [ ] 实体→记忆可追溯
- [ ] Agent 能主动指出跨领域联系
- [ ] SQLite 三表模拟图谱结构

---

### v0.4 — 认知周报

**目标**：每周生成认知分析报告。

**验收**：
- [ ] 5 板块周报（概览/聚焦/联系/盲点/建议）
- [ ] 自动触发（Windows 任务计划）
- [ ] Markdown 输出

---

### v0.5 — Web 前端

**目标**：可用 Web 界面。

**验收**：
- [ ] 单页对话 + 流式显示
- [ ] 记忆侧边栏
- [ ] 周报浏览
- [ ] 零框架依赖

---

## P2 — 第三优先级（高级）

### v1.0 — 稳定版
- 测试覆盖率 ≥ 85%
- 完整 API 文档
- 数据迁移方案

### v2.0 — 认知操作系统
- [ ] Procedural Memory（用户习惯/偏好）
- [ ] Multi-Agent（反思 Agent 独立运行）
- [ ] 知识导出（Markdown 知识库）
- [ ] 飞书/微信 Webhook
- [ ] 本地 LLM 完全离线

---

## 版本切换规则

1. 开发在 `feature/vX.Y` 分支
2. 完成 checklist → 合并到 develop
3. develop 稳定 → tag → 合并 master
4. tag 命名：`v0.1.0`, `v0.2.0`...
