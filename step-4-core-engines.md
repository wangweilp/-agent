# 第 4 步：核心引擎 — Agent 循环 + 适配器

> 这一步写 v0.1 的两个核心：Agent 循环（core）和两个适配器（DeepSeek + SQLite）。

## 4.1 `src/adapters/llm.py`
实现 `LLMProvider` 协议，封装 DeepSeek API。

```python
from openai import OpenAI
from src.adapters.config import Settings
from src.core.memory import LLMProvider

class DeepSeekAdapter:
    """DeepSeek API 适配器，实现 LLMProvider 协议"""
    def __init__(self, settings: Settings):
        self._client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url
        )
        self._model = settings.deepseek_model

    def chat(self, messages: list[dict], stream: bool = False, **kwargs):
        return self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            stream=stream,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 2048)
        )

    def get_embedding(self, text: str) -> list[float]:
        # v0.1 不实现，v0.2 升级
        raise NotImplementedError("Embedding will be implemented in v0.2")
```

## 4.2 `src/adapters/sqlite_store.py`
实现 `MemoryStore` 协议，封装 SQLite。

- 初始化时自动建表（notes 表，字段：id TEXT PK, content TEXT, timestamp TEXT, entities TEXT）
- `store(memory) → str`：插入一条记忆，返回 id
- `search_by_keyword(query, limit) → list[Memory]`：用 LIKE 模糊匹配
- `get_by_id(id) → Memory | None`
- `get_recent(limit) → list[Memory]`：按时间倒序

## 4.3 `src/core/agent.py`
实现 Agent 核心循环。

**系统 Prompt**（完整中文模板，放在模块顶部常量 `SYSTEM_PROMPT`）：

```
你是「记忆进化」个人知识助手。你拥有长期记忆，会逐渐了解用户的思维模式。

## 你的能力
- 存储用户分享的知识和想法
- 检索相关历史记忆来回答问题
- 主动发现用户知识体系中的隐藏联系

## 工具使用
你可以调用以下工具（输出 JSON，不要额外文字）：
- remember: 存储一条新记忆。参数: {"content": "记忆内容"}
- recall: 检索相关记忆。参数: {"query": "检索关键词"}

## 行为准则
1. 用户分享新知识时，主动调用 remember 存储
2. 用户提问时，先 recall 再回答
3. 回答要结合记忆，个性化而非通用
4. 发现联系时主动指出
5. 不确定是否该存储时，宁存勿漏
6. 回复用中文，自然、简洁、有温度
```

**Agent 类**：
- 构造函数接收 `LLMProvider`、`MemoryStore`、`max_rounds`、`memory_size`
- `run(user_input: str) → str`：核心循环
  1. 添加用户消息到 short_term_memory
  2. for round in 1..max_rounds:
     - 调用 LLM
     - 检查回复是否包含工具调用 JSON
     - 如果有 → 执行工具 → 结果加入对话 → continue
     - 如果没有 → 返回回复
  3. 超限抛出异常

**JSON 解析逻辑**：
- 扫描回复文本，提取第一个完整 `{...}` JSON 对象
- 检查 `tool` 字段是否为 "remember" 或 "recall"
- 解析失败就当普通回复返回

## 4.4 测试
写 `tests/test_core/test_agent.py`：Mock LLM 和 MemoryStore，测试 Agent 循环。
写 `tests/test_adapters/test_sqlite_store.py`：用临时文件测试 SQLite 适配器。

## 4.5 提交
```bash
git add src/adapters/llm.py src/adapters/sqlite_store.py src/core/agent.py tests/
git commit -m "feat(core): implement Agent loop with DeepSeek and SQLite adapters"
```
