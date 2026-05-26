# Development Guide: 记忆进化型个人知识助手

## 1. Git 分支策略

### 分支模型
```
master ← develop ← feature/xxx / fix/xxx / refactor/xxx
```

### 提交规范 — Conventional Commits
```
type(scope): subject
```
- type: feat | fix | refactor | docs | test | chore | style | perf
- scope: core | adapters | api | tools | docs | config | tests
- subject: 英文祈使语气，首字母小写，≤ 72 字符

---

## 2. 代码风格

- PEP 8。type hints 所有公共接口。行宽 100。
- Google docstring。
- 导入顺序：标准库 → 第三方 → 项目内部（`from src.`）

---

## 3. 安全规范（必读）

### 3.1 Tool Permission Layer
```python
SAFE_TOOLS = ["remember", "recall", "reflect"]
DANGEROUS_TOOLS = ["delete_memory", "overwrite_memory", "clear_all_memories"]
```
- 危险工具执行前 **必须** 人工确认。
- 工具描述中加入安全提示。

### 3.2 Prompt Injection 防护
- System Prompt 含防护指令
- 用结构化 Tool Calling API，不用 JSON 字符串解析
- 用户输入不能覆盖系统规则

### 3.3 数据安全
- API Key 只在 `.env`
- 本地存储
- DeepSeek API 只传必要上下文

---

## 4. 测试规范

- 镜像路径：`src/core/agent.py` → `tests/test_core/test_agent.py`
- 命名：`test_<方法>_<条件>_<期望>`
- 覆盖率：core 95%+，tools 90%+，总 ≥ 80%

---

## 5. 禁止事项

- 🚫 JSON 字符串解析 tool call（用 true Tool Calling API）
- 🚫 SQLite LIKE 做语义搜索（用 embedding）
- 🚫 core/ 导入第三方库或 adapters/api
- 🚫 全量历史塞入 LLM（用 Context Builder）
- 🚫 所有记忆同级（必须有 importance）
- 🚫 print — 用 logging
- 🚫 循环导入
- 🚫 无测试合并
- 🚫 敏感信息提交
