from typing import Any, Protocol, runtime_checkable

from src.core.types import Memory


@runtime_checkable
class MemoryStore(Protocol):
    def store(self, memory: Memory) -> str:
        """存储一条记忆，返回 memory_id。"""
        ...

    def search_semantic(self, query: str, top_k: int) -> list[Memory]:
        """语义搜索（不是 keyword 搜索）。"""
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

    def search(self, embedding: list[float], k: int) -> list[dict]:
        """返回 top-k 相似结果，每条为 {doc_id, score, metadata}。"""
        ...


@runtime_checkable
class LLMProvider(Protocol):
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

    def get_embedding(self, text: str) -> list[float]:
        """对文本生成 embedding 向量。"""
        ...
