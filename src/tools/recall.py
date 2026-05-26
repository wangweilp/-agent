"""Recall 工具 — 语义搜索 + 实体匹配 → RRF 融合 + 时间衰减 + 重要性加权。"""
import concurrent.futures
import logging
from datetime import datetime, timezone

from src.core.memory import EmbeddingProvider, MemoryStore, VectorStore
from src.core.types import Memory, ToolResult

logger = logging.getLogger(__name__)

_HALF_LIFE_DAYS = 30
_RRF_K = 60


class RecallTool:
    name = "recall"
    description = "检索相关长期记忆。回答用户问题前应先调用此工具查找相关历史信息。"
    requires_confirmation = False
    metadata = {
        "category": "memory",
        "cost": "low",
        "side_effect": False,
    }

    def __init__(
        self,
        memory_store: MemoryStore,
        vector_store: VectorStore,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self._memory_store = memory_store
        self._vector_store = vector_store
        self._embedding = embedding_provider

    @property
    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "recall",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "检索关键词或问题",
                        },
                        "top_k": {
                            "type": "integer",
                            "default": 3,
                            "description": "返回的记忆数量",
                        },
                    },
                    "required": ["query"],
                },
            },
        }

    def execute(self, arguments: dict) -> ToolResult:
        query = arguments.get("query", "")
        top_k = arguments.get("top_k", 3)

        if not query.strip():
            return ToolResult(tool_name="recall", success=False, error="查询不能为空")

        try:
            embedding = self._embedding.encode(query)

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                semantic_future = executor.submit(
                    self._vector_store.search, embedding, top_k * 2
                )
                entity_future = executor.submit(self._entity_match, query)
                semantic_results = semantic_future.result()
                entity_memories = entity_future.result()

            fused_scores: dict[str, float] = {}

            for rank, r in enumerate(semantic_results):
                fused_scores[r.doc_id] = fused_scores.get(r.doc_id, 0) + 1.0 / (_RRF_K + rank + 1)

            for rank, mem in enumerate(entity_memories):
                fused_scores[mem.id] = fused_scores.get(mem.id, 0) + 1.0 / (_RRF_K + rank + 1)

            scored: list[tuple[Memory, float]] = []
            for doc_id, rrf_score in fused_scores.items():
                mem = self._memory_store.get_by_id(doc_id)
                if mem is None:
                    continue
                final_score = self._apply_scoring(mem, rrf_score)
                scored.append((mem, final_score))

            scored.sort(key=lambda x: x[1], reverse=True)
            top_memories = scored[:top_k]

            if not top_memories:
                return ToolResult(
                    tool_name="recall",
                    success=True,
                    content="未找到相关记忆。",
                    metadata={"count": 0},
                )

            formatted = self._format_results([m for m, _ in top_memories])
            return ToolResult(
                tool_name="recall",
                success=True,
                content=formatted,
                metadata={
                    "count": len(top_memories),
                    "scores": [round(s, 4) for _, s in top_memories],
                },
            )
        except Exception as e:
            logger.error(
                "recall:failed",
                extra={"event": "recall_failed", "error_type": type(e).__name__},
            )
            logger.exception("recall:exception")
            return ToolResult(
                tool_name="recall",
                success=False,
                error=f"检索失败: {e}",
            )

    def _entity_match(self, query: str) -> list[Memory]:
        recent = self._memory_store.get_recent(limit=100)
        matched: list[Memory] = []
        for mem in recent:
            for entity in mem.entities:
                if entity and (entity in query or query in entity):
                    matched.append(mem)
                    break
        return matched

    @staticmethod
    def _apply_scoring(memory: Memory, rrf_score: float) -> float:
        age_days = max((datetime.now(timezone.utc) - memory.timestamp).days, 0)
        time_factor = 0.5 ** (age_days / _HALF_LIFE_DAYS)
        importance_factor = memory.importance / 10.0
        access_bonus = min(memory.access_count * 0.05, 0.3)
        return rrf_score * (0.4 * time_factor + 0.4 * importance_factor + 0.2 + access_bonus)

    @staticmethod
    def _format_results(memories: list[Memory]) -> str:
        lines = []
        for i, m in enumerate(memories, 1):
            ts = m.timestamp.strftime("%Y-%m-%d %H:%M")
            text = m.summary or m.content[:200]
            entities_str = f" [{'、'.join(m.entities)}]" if m.entities else ""
            lines.append(f"{i}. ({ts} 重要性:{m.importance}){entities_str} {text}")
        return "\n".join(lines)
