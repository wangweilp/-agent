# CLAUDE.md — 记忆进化型个人知识助手

> 本文件在每次对话启动时由 Claude Code 自动加载。
> 规则按优先级排列。编号越小，优先级越高。冲突时以低编号为准。

---

## 1. 绝对红线

### 1.1 架构隔离（最高优先级）
```
src/core/       → 只能使用标准库 + 自身定义的 Protocol/ABC
                  禁止: import openai / chromadb / sqlite_utils / fastapi
                  禁止: import src.adapters / src.api
src/adapters/   → 实现 core 定义的协议，封装所有外部 I/O
                  禁止: 包含业务判断逻辑（if-else 业务规则放 core）
src/tools/      → 纯函数，输入→输出，无副作用
                  禁止: 持有状态、直接调用外部 API（通过 adapter 协议）
src/api/        → 请求解析 + 响应格式化
                  禁止: 业务逻辑、直接访问数据库
```

- 所有跨层依赖通过 `main.py` 的依赖注入完成，模块内部不 `new` 具体实现。
- 检查命令：`rg -n "from openai|from chromadb|from sqlite_utils|from fastapi" src/core/`

### 1.2 修改隔离
- **每次只改一个模块**。`core/` 和 `adapters/` 同时改时，先完成一个再动下一个。
- 修改前 `rg` 搜索该符号所有引用，确认影响面。
- 修改后立即跑测试。

### 1.3 Git 纪律
- 从 `develop` 切 `feature/xxx` 分支开发。
- 每完成一个独立功能点立即提交，不攒着一堆文件一次交。
- 提交格式：`type(scope): subject`（`feat(core): ...` / `fix(adapters): ...` / `docs: ...`）
- scope 必须是: `core` `adapters` `api` `tools` `docs` `config` `tests`
- 不提交 `.env`、`*.db`、`data/`、`chroma_db/`。

### 1.4 禁止沉默破坏
- 发现现有代码问题：**先报告，后修改**。不静默重写。
- 破坏性变更标注 `BREAKING CHANGE:` 并写入 `docs/adr/`。

---

## 2. 开发流程

### 2.1 开始任何功能前（5 分钟检视）
```
1. 读 docs/ROADMAP.md → 确认当前版本目标 (当前: v0.1 MVP)
2. 读 docs/ARCHITECTURE.md 相关模块边界
3. git status → 确认分支和未提交改动
4. 新功能从 develop 切 feature/xxx 分支
```

### 2.2 v0.1 当前任务（按顺序执行）
```
[ ] core/types.py           — Memory, Entity, ToolCall, ToolResult 数据类
[ ] core/memory.py          — 记忆管理抽象（协议定义）
[ ] core/agent.py           — Agent 循环 Think→Act→Observe
[ ] adapters/llm.py         — DeepSeek chat adapter
[ ] adapters/sqlite_store.py — SQLite 适配器（notes 表）
[ ] tools/remember.py       — 记忆存储工具
[ ] tools/recall.py         — 记忆检索工具（关键词）
[ ] tools/registry.py       — 工具注册表 + JSON 解析
[ ] api/routes.py           — /chat 端点 + SSE 流式
[ ] tools/cli.py            — 终端交互入口
[ ] tests/                  — 对应测试
```

**v0.1 验收标准**：
- 终端能与 Agent 对话
- Agent 能判断何时调用 remember / recall
- 记忆存入 SQLite，能关键词检索
- 对话上下文保留最近 20 轮
- 流式输出

**v0.1 不做的**：向量存储、Web UI、周报、知识图谱

### 2.3 编写代码时
- **先写类型签名，再写实现**。所有公共函数必须有 type hints。
- Google 风格 docstring，至少一行描述。
- 函数不超过 50 行，缩进不超过 3 层。
- 不引入新依赖，除非在 commit body 中说明理由。

### 2.4 编写测试时
- 镜像路径：`src/core/memory.py` → `tests/test_core/test_memory.py`
- 覆盖：正常路径 + 边界值 + 异常路径
- 命名：`test_<方法>_<条件>_<期望>`

### 2.5 提交前自查
```
[ ] python -m pytest tests/ -v 全部通过
[ ] rg "from openai|from chromadb|from sqlite_utils" src/core/ 无输出
[ ] rg "print\(" src/ 无输出
[ ] 提交信息符合 Conventional Commits
[ ] 无敏感信息泄露
```

---

## 3. 领域知识速查

### 3.1 记忆系统（详见 DESIGN.md §1）
```
Working Memory   → list[Message]，当前对话，最多 20 轮
Semantic Memory  → ChromaDB 向量库，语义检索 (v0.2)
Episodic Memory  → SQLite notes 表，原始文本+时间戳
Conceptual Memory → SQLite entities/relations 表 (v0.3)
```

v0.1 只用 Working Memory + Episodic Memory (SQLite)。

### 3.2 Agent 循环（详见 DESIGN.md §2）
```
用户输入 → Agent.run()
  for round in 1..5:
    LLM 生成回复
    若有工具调用 JSON → 执行工具 → 结果喂回 LLM → 继续
    若无工具调用 → 返回最终回复
```

工具调用协议：`{"tool": "remember", "args": {...}}`
解析：扫描回复中第一个完整 JSON → 校验 tool 名 → 校验 args schema。

### 3.3 System Prompt 位置
统一在 `src/core/agent.py` 中定义为常量 `SYSTEM_PROMPT`。

### 3.4 数据模型（详见 DESIGN.md §5）
```python
Memory:    {id, content, timestamp, entities}
Entity:    {id, name, entity_type, first_seen, mention_count}
ToolCall:  {tool, args}
ToolResult:{tool, success, data, error}
```

### 3.5 错误处理
| 错误 | 处理 |
|------|------|
| DeepSeek API 不可用 | 返回友好提示，不崩溃，记日志 |
| SQLite 写失败 | 记日志，返回错误 |
| JSON 解析失败 | 当普通回复，不调工具 |
| Agent 循环超限 | 返回当前最佳回复 |

### 3.6 关键决策
- Agent 循环上限：5 轮
- 短对话窗口：20 条
- LLM：DeepSeek V3 (`deepseek-chat`)
- Embedding：v0.1 不引入，用 SQLite LIKE 关键词匹配
- 前端：v0.1 终端 CLI，不做 Web UI

---

## 4. 不确定时

### 4.1 技术选型
不要自己拍板。搜索业界最佳实践，给 2-3 个方案对比让用户决策。记录到 `docs/adr/`。

### 4.2 产品方向
- 发现自己在做用户没要求的功能 → 立即停止确认。
- 每个 milestone 完成 50% 时停下来让用户验收。

### 4.3 Bug
- 先写复现测试，再修。
- 修复后检查同类问题在代码库其他位置是否存在。

---

## 5. 对话行为

- 回复前先完成文件操作和测试验证。
- 状态更新用「已完成 X / 总数 Y」格式。
- 不过度解释代码。解释写在 docstring 里。
- 遇到权限/环境问题直接说明，不绕过。

---

## 6. 技术约束

- Schema 变更写在 `adapters/sqlite_store.py` migration 段落。
- Prompt 模板集中在 `core/agent.py` 和 `core/report.py`。
- 日志用 `logging.getLogger(__name__)`，不用 `print`。
- 配置统一在 `adapters/config.py` 的 pydantic `Settings` 类。

---

## 7. 快速命令

```bash
# 运行测试
python -m pytest tests/ -v --tb=short

# 检查 core 层违规导入
rg -n "from openai|from chromadb|from sqlite_utils|from fastapi|from src\.adapters|from src\.api" src/core/

# 检查 print 残留
rg -n "print\(" src/

# 检查 git 状态
git status; git log --oneline -5
```

---

## 8. 项目文件索引

| 文件 | 内容 |
|------|------|
| `CLAUDE.md` | 本文档，开发规则 |
| `docs/ARCHITECTURE.md` | 架构图、模块依赖、数据流 |
| `docs/DESIGN.md` | 记忆系统、Agent 循环、RAG、周报详细设计 |
| `docs/ROADMAP.md` | 版本路线图、每版验收标准 |
| `docs/DEV_GUIDE.md` | Git 规范、代码风格、测试规范、检查清单 |
| `config/.env.template` | 环境变量模板 |
| `requirements.txt` | Python 依赖 |
