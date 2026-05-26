# 第 5 步：工具层 + API + CLI

## 5.1 `src/tools/registry.py` — 工具注册表 + 权限分级

```python
SAFE_TOOLS = ["remember", "recall", "reflect"]
DANGEROUS_TOOLS = ["delete_memory", "overwrite_memory"]

class ToolRegistry:
    def __init__(self, memory_store, llm_provider, embedding_provider):
        self._tools = {}
        self._register("remember", remember_fn)
        self._register("recall", recall_fn)
        self._register("reflect", reflect_fn)

    def execute(self, tool_name, arguments):
        if tool_name in DANGEROUS_TOOLS:
            return ToolResult(success=False, error="需要人工确认")
        return self._dispatch(tool_name, arguments)
```

## 5.2 `src/tools/remember.py`
- 输入 content + entities（可选）+ importance_override（可选）
- 计算 importance 评分（base 5 + 实体频次 + 目标关键词 + 情绪词）
- 生成 embedding → 双写（ChromaDB + SQLite）
- 返回 ToolResult

## 5.3 `src/tools/recall.py`
- 输入 query + top_k
- query embedding → ChromaDB 语义搜索（top_k*2）
- SQLite 实体匹配（并行）
- RRF 融合 + 时间衰减 + 重要性加权 → 返回 top_k

## 5.4 `src/tools/reflect.py`
- 输入 topic + recent_n
- 检索相关记忆 + 最近 N 轮对话
- Prompt：「检查以下内容是否存在矛盾、遗漏、可建立的新联系」
- 如有发现 → 存入一条 source="reflect" 的记忆

## 5.5 `src/api/routes.py` + `src/api/schemas.py`
- `POST /chat`：接收 `{"content": "..."}` → 调用 Agent → SSE 流式返回
- ChatRequest / ChatResponse pydantic 模型

## 5.6 `src/tools/cli.py`
- 循环 input → agent.run() → print
- Ctrl+C 退出

## 5.7 `main.py`
- 加载 Settings
- 创建所有 adapter 实例
- 创建 Agent（注入 adapter）
- 创建 FastAPI app

## 5.8 提交
```bash
git add src/tools/ src/api/ main.py tests/
git commit -m "feat(tools): implement registry, remember, recall, and reflect tools"
git commit -m "feat(api): add /chat endpoint with streaming"
```
