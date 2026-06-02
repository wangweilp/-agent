from typing import Any, Protocol, runtime_checkable

from src.core.types import Memory, SearchResult, ToolResult


@runtime_checkable
class MemoryStore(Protocol):
    def store(self, memory: Memory) -> str:
        """存储一条记忆，返回 memory_id。"""
        ...

    def delete(self, memory_id: str) -> None:
        """删除一条记忆（用于双写失败补偿）。"""
        ...

    def search_by_entity(self, entity_name: str) -> list[Memory]:
        """按实体名称检索关联记忆。"""
        ...

    def get_by_id(self, memory_id: str) -> Memory | None:
        """按 ID 获取单条记忆。"""
        ...

    def get_recent(self, limit: int) -> list[Memory]:
        """获取最近 N 条记忆。"""
        ...


@runtime_checkable
class VectorStore(Protocol):
    def store(self, doc_id: str, embedding: list[float], metadata: dict) -> str:
        """存储向量及元数据，返回 doc_id。"""
        ...

    def search(self, embedding: list[float], k: int) -> list[SearchResult]:
        """返回 top-k 相似结果。"""
        ...


@runtime_checkable
class ChatModel(Protocol):
    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Any:
        """调用 LLM 聊天接口，返回 OpenAI 兼容响应。"""
        ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    def encode(self, text: str) -> list[float]:
        """对文本生成 embedding 向量。"""
        ...


@runtime_checkable
class Tool(Protocol):
    """工具协议 — 所有工具必须实现此接口。"""
    name: str
    description: str
    requires_confirmation: bool

    @property
    def schema(self) -> dict[str, Any]:
        """返回 OpenAI 兼容的 function schema。"""
        ...

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """执行工具逻辑。"""
        ...
