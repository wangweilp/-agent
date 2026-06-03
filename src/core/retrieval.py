"""统一记忆检索服务 — 所有记忆检索入口的唯一实现。

消除 agent._retrieve_memories 和 RecallTool 之间的逻辑分裂，
所有入口（agent context、recall tool、reflection）统一走此服务。
"""
import logging
from datetime import datetime, timezone
from typing import Any

from src.core.memory import EmbeddingProvider, MemoryStore, VectorStore
from src.core.types import Memory, SearchResult

logger = logging.getLogger(__name__)

_HALF_LIFE_DAYS = 30
_RRF_K = 60


class MemoryRetrievalService:
    """统一记忆检索服务。

    检索策略：
    1. 语义搜索（向量相似度）
    2. 实体匹配（字符串子串匹配）
    3. RRF 融合
    4. 时间衰减 + 重要性加权
    """

    def __init__(
        self,
        memory_store: MemoryStore,
        vector_store: VectorStore,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self._memory_store = memory_store
        self._vector_store = vector_store
        self._embedding = embedding_provider

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        *,
        entity_match_window: int = 100,
        with_breakdown: bool = False,
        raise_on_error: bool = False,
        include_archived: bool = False,
    ) -> list[dict] | list[Memory]:
        """检索与 query 最相关的长期记忆。

        Args:
            query: 检索查询（用户输入或反思主题）。
            top_k: 返回的记忆数量。
            entity_match_window: 实体匹配时检查的最近记忆数。
            with_breakdown: 是否返回详细分步 score（供 Retrieval Inspector 使用）。
            raise_on_error: True 时传播异常供调用方做 success=False 判断；
                           False 时静默返回 []（Agent 上下文构建降级策略）。
            include_archived: 是否包含已归档记忆。默认 False，只检索 ACTIVE 状态。

        Returns:
            with_breakdown=False: 按最终得分降序排列的记忆列表。
            with_breakdown=True: [{"memory": Memory, "vector_score": float, "rrf_score": float,
                                  "time_factor": float, "importance_factor": float, "final_score": float}]

        Raises:
            Exception: 仅当 raise_on_error=True 且底层（embedding/向量搜索/SQLite）失败时抛出。
        """
        if not query.strip():
            return []

        try:
            embedding = self._embedding.encode(query)

            # 1. 语义搜索
            semantic_results = self._vector_store.search(embedding, k=max(top_k * 2, 5))

            # 2. 实体匹配（lightweight，仅做子串匹配）
            entity_memories = self._entity_match(query, entity_match_window)

            # 3. RRF 融合
            fused_scores: dict[str, float] = {}
            for rank, r in enumerate(semantic_results):
                fused_scores[r.doc_id] = fused_scores.get(r.doc_id, 0) + 1.0 / (_RRF_K + rank + 1)

            for rank, mem in enumerate(entity_memories):
                fused_scores[mem.id] = fused_scores.get(mem.id, 0) + 1.0 / (_RRF_K + rank + 1)

            # 4. 最终评分（时间衰减 + 重要性加权）
            scored: list[dict] = []
            for doc_id, rrf_score in fused_scores.items():
                mem = self._memory_store.get_by_id(doc_id)
                if mem is None:
                    continue

                # 生命周期过滤：默认只搜索 ACTIVE，除非显式指定 include_archived
                if not include_archived and mem.status != "active":
                    continue
                if mem.status in ("deleted", "merged"):
                    continue

                time_factor, importance_factor, access_bonus = self._score_breakdown(mem)
                final_score = self._apply_scoring(mem, rrf_score)
                scored.append({
                    "memory": mem,
                    "vector_score": 0.0,  # 由 caller 计算
                    "rrf_score": round(rrf_score, 4),
                    "time_factor": round(time_factor, 4),
                    "importance_factor": round(importance_factor, 4),
                    "access_bonus": round(access_bonus, 4),
                    "final_score": round(final_score, 4),
                })

            scored.sort(key=lambda x: x["final_score"], reverse=True)
            top = scored[:top_k]

            if with_breakdown:
                return top
            return [item["memory"] for item in top]

        except Exception:
            logger.warning("memory_retrieval_failed", exc_info=True)
            if raise_on_error:
                raise
            return []

    @staticmethod
    def _score_breakdown(memory: Memory) -> tuple[float, float, float]:
        """分解评分因子，供 debug 用。"""
        age_days = max((datetime.now(timezone.utc) - memory.timestamp).days, 0)
        time_factor = 0.5 ** (age_days / _HALF_LIFE_DAYS)
        importance_factor = memory.importance / 10.0
        access_bonus = min(memory.access_count * 0.05, 0.3)
        return time_factor, importance_factor, access_bonus

    def _entity_match(self, query: str, limit: int = 100) -> list[Memory]:
        """实体子串匹配：在最近 limit 条记忆中检查 entity 是否匹配查询。"""
        try:
            recent = self._memory_store.get_recent(limit=limit)
        except Exception:
            return []
        matched: list[Memory] = []
        for mem in recent:
            for entity in mem.entities:
                if entity and (entity in query or query in entity):
                    matched.append(mem)
                    break
        return matched

    @staticmethod
    def _apply_scoring(memory: Memory, rrf_score: float) -> float:
        """应用时间衰减 + 重要性加权 + 访问奖励。"""
        age_days = max((datetime.now(timezone.utc) - memory.timestamp).days, 0)
        time_factor = 0.5 ** (age_days / _HALF_LIFE_DAYS)
        importance_factor = memory.importance / 10.0
        access_bonus = min(memory.access_count * 0.05, 0.3)
        return rrf_score * (0.4 * time_factor + 0.4 * importance_factor + 0.2 + access_bonus)

    @staticmethod
    def format_results(memories: list[Memory]) -> str:
        """格式化记忆列表为可读字符串。"""
        lines = []
        for i, m in enumerate(memories, 1):
            ts = m.timestamp.strftime("%Y-%m-%d %H:%M")
            text = m.summary or m.content[:200]
            entities_str = f" [{'、'.join(m.entities)}]" if m.entities else ""
            lines.append(f"{i}. ({ts} 重要性:{m.importance}){entities_str} {text}")
        return "\n".join(lines)