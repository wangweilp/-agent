# 第 2 步：架构文档先行

> ⚠️ 在写任何代码之前，先把设计文档定好。这是项目最重要的步骤。

## 任务
请在 `docs/` 下创建以下 4 个文档：

---

### 2.1 `docs/ARCHITECTURE.md`
写出项目的模块依赖图、数据流、层级职责边界。

**必须包含**：
- 设计哲学：每一层都有边界，每个模块都有职责，每次调用都是可预期的
- 六边形架构（Ports & Adapters）说明
- 目录结构与职责边界表
- ASCII 模块依赖图（谁可以依赖谁）
- 数据流图（用户输入 → api → core → adapters → 外部系统）
- 关键设计决策表（双层记忆、Agent 循环上限 5 轮、短对话窗口 20 条、工具调用用 JSON 解析、CLI 优先于 Web UI）
- 分层测试策略（core 单元测试 100%，adapters 集成测试，api E2E）

**核心约束**：
- `src/core/` 不能导入 `src/adapters/`、`src/api/`，也不能导入任何第三方库
- `src/core/` 只定义 Protocol/ABC 抽象
- `src/adapters/` 实现 core 定义的协议
- 所有跨层依赖通过 `main.py` 依赖注入

---

### 2.2 `docs/DEV_GUIDE.md`
开发规范和协作纪律。

**必须包含**：
- Git 分支模型（master ← develop ← feature/xxx、fix/xxx、refactor/xxx）
- Conventional Commits 规范（type 列表：feat/fix/refactor/docs/test/chore/style/perf，scope 限定为 core/adapters/api/tools/docs/config/tests）
- Python 代码风格（PEP 8、type hints、Google docstring、行宽 100、导入顺序）
- Protocol/ABC 使用示例
- 测试文件镜像路径规则、命名规范、覆盖率基线
- 开发工作流（切分支 → 开发 → 测试 → 提交 → 合并）
- PR 检查清单
- ADR（架构决策记录）模板
- 禁止事项清单

---

### 2.3 `docs/ROADMAP.md`
版本路线图，每个版本独立可交付。

**必须包含**：
- v0.1 MVP：终端对话 + remember/recall 工具 + SQLite 关键词检索 + 20 轮上下文 + 流式输出
- v0.2 向量记忆：ChromaDB + 本地 embedding + hybrid search
- v0.3 知识图谱：实体提取 + 关系图谱 + 跳转联想
- v0.4 认知周报：每周日自动生成 Markdown 周报
- v0.5 Web 前端：单页 HTML + JS 对话界面
- v1.0 稳定版
- v2.0 扩展方向

每个版本要有明确的验收标准和提交清单。

---

### 2.4 `docs/DESIGN.md`
系统详细设计。

**必须包含**：
- 记忆分层模型（Working / Semantic / Episodic / Conceptual Memory）
- 记忆存储流程（用户输入 → 实体提取 → embedding → ChromaDB + SQLite 双写）
- 记忆检索流程（Hybrid Search：语义搜索 + 关键词/实体匹配 → RRF 融合）
- Agent 循环伪代码
- 工具调用 JSON 协议
- System Prompt 完整模板
- RAG Pipeline（Query Rewriting → Retrieval → Reranking → Context Assembly → Generation）
- RRF Reranking 算法（带时间衰减）
- 周报生成设计（数据源 SQL、Prompt 模板、输出文件格式）
- 所有数据模型定义（Memory、Entity、ToolCall、ToolResult、AgentTurn）
- SQLite 表结构（notes、entities、memory_entities、relations）
- 错误处理策略表
- 安全隐私说明

## 要求
- 每个文档写完后 git commit
- 提交信息用 `docs: add ARCHITECTURE.md` 等格式
- 文档使用中文
