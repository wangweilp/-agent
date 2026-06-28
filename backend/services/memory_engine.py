"""Multi-layer memory engine.

Architecture:
    - ChromaDB (PersistentClient) is the local vector store; one collection per
      MemoryScope, isolating episodic from semantic memory physically.
    - LlamaIndex wraps the retrieval logic: each scope owns a VectorStoreIndex
      backed by a ChromaVectorStore and a shared embed model.
    - All synchronous Chroma/LlamaIndex I/O is dispatched to a worker thread
      via ``asyncio.to_thread`` so the public API stays fully async.

Embedding strategy:
    - When ``OPENAI_API_KEY`` is set, the engine uses ``OpenAIEmbedding``.
    - Otherwise it falls back to a deterministic ``_MockEmbedder`` so the
      backend remains runnable in local dev without external API access
      (consistent with the simulation-driven nature of this phase).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import struct
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import chromadb
from chromadb.config import Settings as ChromaSettings
from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.core.embeddings import BaseEmbedding
from llama_index.core.schema import NodeWithScore
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore

from backend.core.config import settings
from backend.models.memory import MemoryScope

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mock embedder (local-dev fallback)
# ---------------------------------------------------------------------------
class _MockEmbedder(BaseEmbedding):
    """Deterministic SHA-256 based embedder.

    Used only when no ``OPENAI_API_KEY`` is configured. Produces normalized
    256-dim vectors so cosine similarity is meaningful enough for local
    testing. NOT suitable for production recall quality.
    """

    def _hash_to_vector(self, text: str) -> List[float]:
        embed_dim = 256
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        needed = embed_dim * 4  # 4 bytes per float32
        buffer = (digest * ((needed // len(digest)) + 1))[:needed]
        floats = list(struct.unpack(f"<{embed_dim}f", buffer))
        norm = sum(f * f for f in floats) ** 0.5 or 1.0
        return [f / norm for f in floats]

    def _get_query_embedding(self, query: str) -> List[float]:
        return self._hash_to_vector(query)

    def _get_text_embedding(self, text: str) -> List[float]:
        return self._hash_to_vector(text)

    def _get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        return [self._hash_to_vector(t) for t in texts]

    async def _aget_query_embedding(self, query: str) -> List[float]:
        return self._hash_to_vector(query)

    async def _aget_text_embedding(self, text: str) -> List[float]:
        return self._hash_to_vector(text)

    async def _aget_text_embeddings(
        self, texts: List[str]
    ) -> List[List[float]]:
        return [self._hash_to_vector(t) for t in texts]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class ZhiweiMemoryEngine:
    """Multi-layer memory engine backed by ChromaDB + LlamaIndex.

    One Chroma collection per ``MemoryScope``; one LlamaIndex
    ``VectorStoreIndex`` per collection. The engine lazily initializes its
    clients on first use so importing the module has no side effects.
    """

    def __init__(self) -> None:
        self._client: Optional[chromadb.api.ClientAPI] = None
        self._embed_model: Optional[BaseEmbedding] = None
        self._collections: Dict[MemoryScope, Any] = {}
        self._indices: Dict[MemoryScope, VectorStoreIndex] = {}
        self._initialized: bool = False
        self._init_lock: Optional[asyncio.Lock] = None

    # ---- lifecycle ---------------------------------------------------------
    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        # Lock must be created inside the running loop (Python 3.11 safety).
        if self._init_lock is None:
            self._init_lock = asyncio.Lock()
        async with self._init_lock:
            if self._initialized:  # double-check after acquiring the lock
                return
            await self._initialize()
            self._initialized = True

    async def _initialize(self) -> None:
        settings.CHROMA_DB_DIR.mkdir(parents=True, exist_ok=True)
        self._client = await asyncio.to_thread(
            chromadb.PersistentClient,
            path=str(settings.CHROMA_DB_DIR),
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=False),
        )
        self._embed_model = self._build_embed_model()
        for scope in MemoryScope:
            collection = await asyncio.to_thread(
                self._client.get_or_create_collection,
                name=self._collection_name(scope),
                metadata={"scope": scope.value},
                # LlamaIndex supplies embeddings explicitly via
                # ChromaVectorStore (add(embeddings=...) / query(query_embeddings=...)),
                # so Chroma's own embedding function is never invoked.
                embedding_function=None,
            )
            self._collections[scope] = collection
            vector_store = ChromaVectorStore(chroma_collection=collection)
            storage_context = StorageContext.from_defaults(vector_store=vector_store)
            index = await asyncio.to_thread(
                VectorStoreIndex,
                nodes=[],
                storage_context=storage_context,
                embed_model=self._embed_model,
                show_progress=False,
            )
            self._indices[scope] = index
        logger.info(
            "ZhiweiMemoryEngine initialized: scopes=%s embed_model=%s db=%s",
            [s.value for s in MemoryScope],
            type(self._embed_model).__name__,
            settings.CHROMA_DB_DIR,
        )

    def _build_embed_model(self) -> BaseEmbedding:
        if settings.openai_api_key_value:
            kwargs: Dict[str, Any] = {"model": settings.OPENAI_EMBEDDING_MODEL}
            if settings.OPENAI_BASE_URL:
                kwargs["api_base"] = settings.OPENAI_BASE_URL
            return OpenAIEmbedding(
                api_key=settings.openai_api_key_value, **kwargs
            )
        logger.warning(
            "OPENAI_API_KEY is empty; falling back to _MockEmbedder. "
            "Set the key in your environment for production embeddings."
        )
        return _MockEmbedder()

    def _collection_name(self, scope: MemoryScope) -> str:
        return (
            settings.CHROMA_COLLECTION_EPISODIC
            if scope is MemoryScope.EPISODIC
            else settings.CHROMA_COLLECTION_SEMANTIC
        )

    # ---- public API --------------------------------------------------------
    async def write_memory(
        self,
        content: str,
        scope: MemoryScope,
        importance: float = 1.0,
    ) -> Dict[str, Any]:
        """Vectorize ``content`` and persist it with metadata to the scoped collection.

        Returns a dict shaped like ``MemoryWriteResponse`` (the caller maps it
        to the Pydantic model).
        """
        await self._ensure_initialized()
        importance = max(0.0, min(1.0, float(importance)))
        timestamp = datetime.now(timezone.utc)

        document = Document(
            text=content,
            metadata={
                "scope": scope.value,
                "importance": importance,
                "timestamp": timestamp.isoformat(),
            },
            excluded_embed_metadata_keys=["timestamp"],
            excluded_llm_metadata_keys=["timestamp"],
        )
        index = self._indices[scope]
        # index.insert() embeds the document via self._embed_model and writes
        # through ChromaVectorStore -> Chroma (embeddings supplied explicitly).
        await asyncio.to_thread(index.insert, document)

        memory_id = document.id_ or document.node_id
        logger.info(
            "write_memory scope=%s importance=%.3f id=%s len=%d",
            scope.value, importance, memory_id, len(content),
        )
        return {
            "id": memory_id,
            "scope": scope,
            "importance": importance,
            "timestamp": timestamp,
            "status": "stored",
        }

    async def search_memory(
        self,
        query: str,
        top_k: int = 5,
        rerank: bool = False,
        scope: Optional[MemoryScope] = None,
    ) -> Dict[str, Any]:
        """Cosine-similarity vector recall across one or all memory layers.

        When ``rerank=True``, candidates are over-fetched and reordered by a
        mock scorer (similarity * 0.7 + importance * 0.3). Replace
        ``_mock_rerank`` with a real reranker in a later phase; the signature
        is stable.
        """
        await self._ensure_initialized()
        top_k = max(1, int(top_k))
        candidate_k = (
            top_k * settings.MEMORY_RERANK_CANDIDATE_MULTIPLIER
            if rerank
            else top_k
        )
        scopes: Sequence[MemoryScope] = (
            [scope] if scope is not None else list(MemoryScope)
        )

        raw_hits: List[Tuple[MemoryScope, NodeWithScore]] = []
        for s in scopes:
            index = self._indices[s]
            retriever = await asyncio.to_thread(
                index.as_retriever,
                similarity_top_k=candidate_k,
            )
            nodes: List[NodeWithScore] = await asyncio.to_thread(
                retriever.retrieve, query
            )
            raw_hits.extend((s, node) for node in nodes)

        if rerank:
            raw_hits = self._mock_rerank(raw_hits)

        top_hits = raw_hits[:top_k]

        hits: List[Dict[str, Any]] = []
        for s, node in top_hits:
            metadata = node.metadata or {}
            ts_raw = metadata.get("timestamp")
            try:
                ts = (
                    datetime.fromisoformat(ts_raw)
                    if ts_raw
                    else datetime.now(timezone.utc)
                )
            except ValueError:
                ts = datetime.now(timezone.utc)
            hits.append({
                "id": node.node_id,
                "content": node.text or "",
                "scope": s,
                "importance": float(metadata.get("importance", 1.0)),
                "timestamp": ts,
                "score": float(node.score or 0.0),
            })

        logger.info(
            "search_memory query=%r top_k=%d rerank=%s hits=%d",
            query, top_k, rerank, len(hits),
        )
        return {
            "query": query,
            "hits": hits,
            "total": len(hits),
            "reranked": rerank,
        }

    # ---- rerank placeholder ------------------------------------------------
    @staticmethod
    def _mock_rerank(
        hits: List[Tuple[MemoryScope, NodeWithScore]],
    ) -> List[Tuple[MemoryScope, NodeWithScore]]:
        """Mock reranker placeholder.

        Combines cosine similarity (0.7) with stored importance (0.3) and
        re-sorts descending. Swap this for a cross-encoder / LLM reranker in
        a later phase; the signature is stable.
        """

        def _score(item: Tuple[MemoryScope, NodeWithScore]) -> float:
            _, node = item
            metadata = node.metadata or {}
            similarity = float(node.score or 0.0)
            importance = float(metadata.get("importance", 0.5))
            return 0.7 * similarity + 0.3 * importance

        return sorted(hits, key=_score, reverse=True)
