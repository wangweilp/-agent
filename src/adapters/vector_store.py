"""ChromaDB 向量存储适配器 — 实现 VectorStore 协议。"""
import logging
from typing import Any

import chromadb
from chromadb.api import ClientAPI

from src.adapters.config import Settings

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "memory_embeddings"
_ALLOWED_METADATA_TYPES = (str, int, float, bool)


class VectorStoreError(Exception):
    """向量存储错误。"""


class ChromaDBAdapter:
    """基于 ChromaDB 持久化存储的 VectorStore 实现。

    可通过 `client` 参数注入 EphemeralClient 用于测试。
    """

    def __init__(
        self,
        config: Settings,
        client: ClientAPI | None = None,
        collection_name: str = _COLLECTION_NAME,
    ) -> None:
        if client is not None:
            self._client = client
        else:
            self._client = chromadb.PersistentClient(
                path=config.chroma_persist_dir,
            )
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
        )

    def store(self, doc_id: str, embedding: list[float], metadata: dict[str, Any]) -> str:
        if not embedding:
            raise ValueError("embedding 不能为空")

        sanitized = self._sanitize_metadata(metadata)
        self._collection.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            metadatas=[sanitized if sanitized else None],
        )
        return doc_id

    def search(self, embedding: list[float], k: int) -> list[dict[str, Any]]:
        if not embedding:
            raise ValueError("embedding 不能为空")

        result = self._collection.query(
            query_embeddings=[embedding],
            n_results=k,
            include=["metadatas", "distances"],
        )

        hits: list[dict[str, Any]] = []
        ids = result.get("ids", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        for i, doc_id in enumerate(ids):
            hits.append({
                "id": doc_id,
                "metadata": metadatas[i] if metadatas else {},
                "distance": distances[i] if distances else 0.0,
            })
        return hits

    def delete(self, doc_id: str) -> None:
        self._collection.delete(ids=[doc_id])

    def count(self) -> int:
        return self._collection.count()

    def close(self) -> None:
        pass

    def __enter__(self) -> "ChromaDBAdapter":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    @staticmethod
    def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, str | int | float | bool]:
        sanitized: dict[str, str | int | float | bool] = {}
        for key, value in metadata.items():
            if isinstance(value, _ALLOWED_METADATA_TYPES):
                sanitized[key] = value
            else:
                sanitized[key] = str(value)
        return sanitized
