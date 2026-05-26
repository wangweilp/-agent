# 第 5 步：工具层 + API + CLI

## 5.1 `src/tools/registry.py`
工具注册表。维护 `{"remember": remember_fn, "recall": recall_fn}` 映射。
提供 `execute(tool_name, args) → ToolResult` 方法。

## 5.2 `src/tools/remember.py`
实现 remember 工具函数。
- 接收 `content: str` 和 `MemoryStore` 协议
- 生成 UUID，创建 `Memory` 对象，调用 `store`
- 返回 `ToolResult`

## 5.3 `src/tools/recall.py`
实现 recall 工具函数。
- 接收 `query: str` 和 `MemoryStore` 协议
- 调用 `search_by_keyword`
- 返回 `ToolResult`

## 5.4 `src/api/routes.py`
FastAPI 路由。
- `POST /chat`：接收 `{"content": "..."}`，调用 Agent，返回 `{"reply": "..."}`
- 支持 SSE 流式输出（用 `StreamingResponse`）

## 5.5 `src/api/schemas.py`
Pydantic 请求/响应模型。

```python
class ChatRequest(BaseModel):
    content: str

class ChatResponse(BaseModel):
    reply: str
```

## 5.6 `src/tools/cli.py`
终端交互入口。
- 循环读取 `input("你: ")`
- 调用 `agent.run(user_input)` 并打印
- Ctrl+C 退出

## 5.7 `main.py`
组装所有依赖。
- 加载 Settings
- 创建 DeepSeekAdapter、SQLiteMemoryStore
- 创建 Agent
- 创建 FastAPI app

## 5.8 提交
```bash
git add src/tools/ src/api/ src/tools/cli.py main.py tests/
git commit -m "feat(tools): add tool registry, remember, recall, and CLI entry"
git commit -m "feat(api): add /chat endpoint with streaming SSE"
```

提交后验证：运行 `python main.py` 或 `python -m src.tools.cli`，确保能启动。
