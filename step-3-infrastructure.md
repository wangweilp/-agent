# 第 3 步：基础设施层 — 类型定义 + 配置 + 协议

> 现在开始写代码。记住：先 core/，再 adapters/，后 tools/，最后 api/。每层写完测试再进下一层。

## 3.1 `src/core/types.py`
定义所有数据类，零外部依赖。

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

@dataclass
class Memory:
    id: str
    content: str
    timestamp: datetime
    entities: list[str] = field(default_factory=list)

@dataclass
class Entity:
    id: str
    name: str
    entity_type: str  # "book" | "person" | "concept" | "tool" | "project"
    first_seen: datetime
    mention_count: int = 1

@dataclass
class ToolCall:
    tool: str
    args: dict[str, Any]

@dataclass
class ToolResult:
    tool: str
    success: bool
    data: Any
    error: str | None = None

@dataclass
class Message:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
```

## 3.2 `src/adapters/config.py`
用 pydantic Settings 加载配置。

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    deepseek_api_key: str
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    chroma_persist_dir: str = "./data/chroma_db"
    sqlite_db_path: str = "./data/agent_memory.db"
    agent_max_tool_rounds: int = 5
    agent_short_term_memory_size: int = 20

    class Config:
        env_file = ".env"
```

## 3.3 `src/core/memory.py`
定义记忆相关的 Protocol/ABC — 这是 core 层调用 adapters 的"合同"。

```python
from typing import Protocol, runtime_checkable
from src.core.types import Memory

@runtime_checkable
class MemoryStore(Protocol):
    """协议：任何实现此接口的类都可以作为记忆存储后端"""
    def store(self, memory: Memory) -> str: ...
    def search_by_keyword(self, query: str, limit: int = 5) -> list[Memory]: ...
    def get_by_id(self, memory_id: str) -> Memory | None: ...
    def get_recent(self, limit: int = 20) -> list[Memory]: ...

@runtime_checkable
class VectorStore(Protocol):
    """协议：向量存储后端（v0.2 启用）"""
    def store(self, content: str, embedding: list[float], metadata: dict) -> str: ...
    def search(self, embedding: list[float], k: int = 5) -> list[dict]: ...
    def delete(self, doc_id: str) -> None: ...

@runtime_checkable
class LLMProvider(Protocol):
    """协议：LLM 调用后端"""
    def chat(self, messages: list[dict], stream: bool = False, **kwargs) -> Any: ...
    def get_embedding(self, text: str) -> list[float]: ...
```

## 3.4 提交
```bash
git add src/core/types.py src/adapters/config.py src/core/memory.py
git commit -m "feat(core): define types, protocols, and config infrastructure"
```

## 要求
- `types.py` 只能用 `dataclasses` 和 `datetime`，不引入第三方库
- `config.py` 用 pydantic-settings（如果没装，加到 requirements.txt）
- `memory.py` 只定义 Protocol，不实现
- 写完后用 `python -c "from src.core.types import Memory, Entity, ToolCall, ToolResult; print('types OK')"` 验证
