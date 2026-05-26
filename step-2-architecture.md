# 第 2 步：基础设施 — 类型定义 + 协议 + 配置

> ⚠️ 开始前先读 `CLAUDE.md` §1-2。

## 2.1 `src/core/types.py` — 丰富数据模型

```python
@dataclass
class Memory:
    id: str; content: str; summary: str | None
    source: str  # "user" | "agent" | "reflect"
    timestamp: datetime
    importance: int = 5           # 1-10
    entities: list[str] = []
    relations: list[dict] = []    # [{s:"", p:"", o:""}]
    embedding: list[float] | None = None
    memory_type: str = "episodic"
    access_count: int = 0
    last_accessed: datetime | None = None

@dataclass
class Entity: id, name, entity_type, first_seen, mention_count

@dataclass
class ToolCall: tool_name, arguments, call_id

@dataclass
class ToolResult: tool_name, success, data, error=None

@dataclass
class Message: role, content, tool_call_id=None, tool_calls=None
```

## 2.2 `src/adapters/config.py` — pydantic Settings

```python
class Settings(BaseSettings):
    deepseek_api_key: str
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    chroma_persist_dir: str = "./data/chroma_db"
    sqlite_db_path: str = "./data/agent_memory.db"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    agent_max_tool_rounds: int = 5
    agent_short_term_size: int = 20
    agent_context_window: int = 6  # Context Builder 保留最近 N 轮
    class Config: env_file = ".env"
```

## 2.3 `src/core/memory.py` — Protocol 定义

```python
@runtime_checkable
class MemoryStore(Protocol):
    def store(self, memory: Memory) -> str: ...
    def search_semantic(self, query: str, top_k: int) -> list[Memory]: ...  # ← 不是 keyword
    def search_by_entity(self, entity_name: str) -> list[Memory]: ...
    def get_by_id(self, memory_id: str) -> Memory | None: ...
    def get_recent(self, limit: int) -> list[Memory]: ...

@runtime_checkable
class VectorStore(Protocol):
    def store(self, doc_id: str, embedding: list[float], metadata: dict) -> str: ...
    def search(self, embedding: list[float], k: int) -> list[dict]: ...

@runtime_checkable
class LLMProvider(Protocol):
    def chat(self, messages, tools=None, tool_choice=None, stream=False, **kwargs) -> Any: ...
    def get_embedding(self, text: str) -> list[float]: ...
```

## 2.4 提交
```bash
git add src/core/types.py src/core/memory.py src/adapters/config.py
git commit -m "feat(core): define rich types, protocols, and config"
```
