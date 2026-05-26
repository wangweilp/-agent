# Roadmap: 记忆进化型个人知识助手

## 版本策略
- 每个版本独立可交付，有自己的验收标准
- 版本间的架构演进必须在 ARCHITECTURE.md 中提前规划
- 任何涉及架构变更的 feature，先写 ADR

---

## v0.1 — MVP: 能对话、能记、能查

**目标**：最简可运行 Agent，验证核心链路。

**验收**：
- [ ] 终端里能和 Agent 对话
- [ ] Agent 能判断何时调用 remember / recall 工具
- [ ] 记忆存入 SQLite，能通过关键词检索
- [ ] 对话上下文保留最近 20 轮
- [ ] 流式输出回复内容

**提交清单**：
```
[ ] feat(core): define Memory, Entity, ToolCall types
[ ] feat(core): implement Agent loop (think → act → observe)
[ ] feat(core): implement in-memory short-term memory buffer
[ ] feat(adapters): implement DeepSeek chat adapter
[ ] feat(adapters): implement SQLite store adapter
[ ] feat(tools): implement remember tool
[ ] feat(tools): implement recall tool (keyword fallback)
[ ] feat(tools): implement tool registry with JSON parser
[ ] feat(api): implement /chat endpoint with streaming SSE
[ ] feat(tools): implement CLI interactive mode
[ ] test(core): agent loop unit tests
[ ] test(tools): tool invocation tests
[ ] docs: v0.1 changelog
```

**不包含**（刻意延迟）：
- 向量存储（先用 SQLite keyword match）
- Web UI
- 周报
- 知识图谱

---

## v0.2 — 向量记忆

**目标**：引入真正的语义检索，把 SQLite keyword match 替换为向量相似度搜索。

**验收**：
- [ ] 记忆同时写入 ChromaDB 向量库 + SQLite 结构化库
- [ ] 添加 memory 时自动生成 embedding
- [ ] recall 先走 ChromaDB 语义搜索，再读 SQLite 取完整内容
- [ ] 搜索结果按相似度排序，支持 top_k 控制

**关键决策**：
- Embedding 方案选型（详见 ADR-002）
  - 方案 A：本地 `BAAI/bge-small-zh-v1.5`（免费，需额外安装）
  - 方案 B：DeepSeek embedding API（如果有）
  - MVP 先用方案 A

**提交清单**：
```
[ ] feat(adapters): implement local embedding with sentence-transformers
[ ] feat(adapters): implement ChromaDB vector store adapter
[ ] refactor(core): update recall tool to use hybrid search
[ ] feat(core): implement memory dual-write (vector + structured)
[ ] test(adapters): ChromaDB adapter tests
[ ] test(core): hybrid search integration tests
```

---

## v0.3 — 知识图谱 & 实体关系

**目标**：从记忆内容中提取实体和关系，构建知识图谱，实现"跳转联想"。

**验收**：
- [ ] 每条记忆存储时自动提取实体（DeepSeek 完成）
- [ ] 实体关系存入 SQLite（模拟图谱结构）
- [ ] 查询时能按实体追溯到相关记忆
- [ ] Agent 能主动指出用户不同知识点的联系

**核心模型**：
```
Entity: {id, name, type, first_seen, count}
Relation: {source_entity_id, target_entity_id, relation_type, weight}
Memory-Entity link: {memory_id, entity_id}
```

**关键决策**（ADR-003）：
- 先用 SQLite 三表模拟图谱
- 当实体数 > 1000 或查询变慢时，迁移至 Neo4j
- DeepSeek 做实体抽取（Few-shot prompt）

---

## v0.4 — 认知周报

**目标**：每周日自动生成认知周报。

**验收**：
- [ ] 从 SQLite 读取本周所有记忆
- [ ] 组装 prompt，让 DeepSeek 分析：主题聚类、隐藏联系、矛盾点、推荐阅读
- [ ] 输出 Markdown 格式周报文件 `data/reports/report_YYYYWW.md`
- [ ] 提供脚本手动触发 + 可配合 Windows 任务计划程序自动执行

**周报 prompt 结构**（固定模板，保证输出一致性）：
```
1. 本周概览（记忆数量、活跃日期、前3大主题）
2. 领域聚焦（每个领域的核心进展和关键洞察）
3. 隐藏联系（跨领域的模式识别）
4. 盲点提示（你可能忽略的角度）
5. 下周建议（基于当前轨迹的推荐方向）
```

---

## v0.5 — Web 前端

**目标**：可用的 Web 界面，不再是终端。

**验收**：
- [ ] 单页 HTML + JS 对话界面
- [ ] 流式显示 AI 回复
- [ ] 侧边栏显示最近记忆卡片
- [ ] 记忆搜索框
- [ ] 周报浏览页

**设计约束**：
- 零框架依赖（Pure HTML/CSS/JS），不加 React
- 不超过 3 个 HTML 页面
- 风格：安静、文本优先、类 Notion 排版

---

## v1.0 — 稳定版

**目标**：生产可用，长期稳定运行。

**验收**：
- [ ] 所有 v0.x 功能稳定，无明显 bug
- [ ] 测试覆盖率 ≥ 85%
- [ ] 完整的 API 文档（FastAPI 自动生成 Swagger）
- [ ] 数据迁移方案（版本升级不丢数据）
- [ ] 完整的用户操作文档

---

## v2.0 — 扩展

**方向预览**（届时开 ADR 讨论优先级）：

- [ ] 多模态记忆（图片、PDF 解析）
- [ ] 飞书 / 微信 Webhook 接入
- [ ] 记忆自动总结与压缩（超过阈值时压缩旧记忆）
- [ ] 多 Agent 协作（反思 Agent 检查记忆矛盾）
- [ ] 知识导出（生成 Notion 页面 / Markdown 知识库）

---

## 版本切换规则

1. 每个版本开发在 `feature/vX.Y` 分支
2. 完成所有 checklist 后合并到 `develop`
3. `develop` 稳定后打 tag 合并到 `master`
4. tag 命名：`v0.1.0`, `v0.2.0`...
