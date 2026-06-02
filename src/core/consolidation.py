"""Memory Consolidation Engine — 长期记忆巩固系统。

三阶段算法：
    1. 相似记忆聚合 — embedding 聚类 → 合并重复/高度相似记忆
    2. 时间衰减归档 — 90 天以上且 importance < 4 的记忆自动归档
    3. 概念提升 — 多个 episodic 记忆 → LLM 提炼 semantic 记忆

复用已有协议（EmbeddingProvider / MemoryStore / VectorStore / ChatModel），
不重新实现向量检索或存储逻辑。
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from src.core.memory import ChatModel, EmbeddingProvider, MemoryStore, VectorStore
from src.core.types import Memory

logger = logging.getLogger(__name__)

# ── 阈值 ──

MERGE_SIMILARITY_THRESHOLD = 0.88   # similarity >= 此值触发合并
MERGE_SEARCH_K = 5                  # 每条记忆搜索的候选数
ARCHIVE_AGE_DAYS = 90               # 超过此天数考虑归档
ARCHIVE_MAX_IMPORTANCE = 3          # importance <= 此值才归档
CONCEPT_MIN_CLUSTER_SIZE = 3        # 形成概念簇的最小 episodic 记忆数
CONCEPT_ENTITY_OVERLAP_MIN = 2      # 共享实体数 >= 此值才聚簇

# LLM prompt：从多条 episodic 记忆提炼 semantic 概念
_CONCEPT_ELEVATION_PROMPT = """你是一个知识提炼助手。以下是用户的多条相关情景记忆：

{memories}

请从这些记忆中发现共同主题，生成一条概念级摘要（semantic memory）。
摘要要求：
- ≤150 字
- 描述用户在这方面的整体认知模式或知识积累
- 提取 3-5 个关键实体
- 不要简单重复原文，而是提炼出更高层次的理解

仅输出摘要文本，不需要 JSON 或其他格式。"""


# ── 数据结构 ──

@dataclass
class ConsolidationResult:
    """单次巩固运行的结果。

    merged_count: 合并的记忆对数（每对计数为 1，被合并方算 1）
    archived_count: 归档的记忆条数
    deleted_count: 物理删除的记忆条数（重复内容删除）
    new_memories: 新生成的语义记忆列表
    """
    merged_count: int = 0
    archived_count: int = 0
    deleted_count: int = 0
    new_memories: list[Memory] = field(default_factory=list)

    @property
    def total_affected(self) -> int:
        return self.merged_count + self.archived_count + self.deleted_count + len(self.new_memories)


# ── 协议 ──

@runtime_checkable
class MemoryConsolidator(Protocol):
    """记忆巩固器协议 — 可插拔的巩固策略。"""

    def consolidate(self, memories: list[Memory]) -> ConsolidationResult:
        """对一批记忆执行巩固，返回结果统计。

        不修改传入的 memories 列表，而是通过 MemoryStore 读写。
        """
        ...


# ── 默认实现 ──

class DefaultMemoryConsolidator:
    """默认记忆巩固器，实现三阶段巩固流程。

    所有阶段幂等——重复执行不会产生不同结果。
    reuse 已有 Embedding / VectorStore / MemoryStore / ChatModel。
    """

    def __init__(
        self,
        memory_store: MemoryStore,
        vector_store: VectorStore,
        embedding_provider: EmbeddingProvider,
        llm: ChatModel,
        *,
        merge_threshold: float = MERGE_SIMILARITY_THRESHOLD,
        archive_age_days: int = ARCHIVE_AGE_DAYS,
        archive_max_importance: int = ARCHIVE_MAX_IMPORTANCE,
        concept_min_cluster: int = CONCEPT_MIN_CLUSTER_SIZE,
    ) -> None:
        self._memory_store = memory_store
        self._vector_store = vector_store
        self._embedding = embedding_provider
        self._llm = llm
        self._merge_threshold = merge_threshold
        self._archive_age_days = archive_age_days
        self._archive_max_importance = archive_max_importance
        self._concept_min_cluster = concept_min_cluster

    # ── 公共 API ──

    def consolidate(self, memories: list[Memory]) -> ConsolidationResult:
        """执行完整的三阶段巩固。"""
        if not memories:
            return ConsolidationResult()

        result = ConsolidationResult()

        # Phase 1: 相似记忆聚合
        merged, deleted = self._phase1_merge(memories)
        result.merged_count = merged
        result.deleted_count = deleted

        # Phase 2: 时间衰减归档
        result.archived_count = self._phase2_archive(memories)

        # Phase 3: 概念提升
        result.new_memories = self._phase3_conceptual_elevation(memories)

        logger.info(
            "consolidation_complete",
            extra={
                "total_input": len(memories),
                "merged": result.merged_count,
                "archived": result.archived_count,
                "deleted": result.deleted_count,
                "new_concepts": len(result.new_memories),
            },
        )
        return result

    # ── Phase 1: 相似记忆聚合 ──

    def _phase1_merge(self, memories: list[Memory]) -> tuple[int, int]:
        """相似记忆合并。

        对每条记忆做 embedding → 搜索相似记忆 → 相似度 >= 阈值则合并。

        Returns:
            (merged_count, deleted_count)
        """
        merged = 0
        deleted_ids: set[str] = set()

        for mem in memories:
            if mem.id in deleted_ids:
                continue

            try:
                embedding = self._embedding.encode(mem.content)
                candidates = self._vector_store.search(embedding, k=MERGE_SEARCH_K)
            except Exception:
                logger.debug("consolidation_merge_search_failed", exc_info=True)
                continue

            for c in candidates:
                if c.doc_id == mem.id or c.doc_id in deleted_ids:
                    continue
                if c.score < self._merge_threshold:
                    continue

                # 获取候选记忆，合并
                other = self._memory_store.get_by_id(c.doc_id)
                if other is None:
                    continue

                self._merge_pair(primary=mem, secondary=other)
                deleted_ids.add(other.id)
                merged += 1
                logger.info(
                    "consolidation_merged_pair",
                    extra={
                        "primary_id": mem.id,
                        "secondary_id": other.id,
                        "similarity": round(c.score, 4),
                    },
                )

        # 物理删除被合并方
        delete_count = 0
        for did in deleted_ids:
            try:
                self._memory_store.delete(did)
                delete_count += 1
            except Exception:
                logger.debug("consolidation_delete_failed", extra={"id": did}, exc_info=True)

        return merged, delete_count

    @staticmethod
    def _merge_pair(primary: Memory, secondary: Memory) -> None:
        """将 secondary 合并到 primary（仅修改 primary 对象，不写库）。"""
        primary.content = f"{primary.content}\n[合并自 {secondary.id[:8]}] {secondary.content}"
        primary.entities = list(set(primary.entities + secondary.entities))
        primary.access_count += secondary.access_count
        primary.importance = max(primary.importance, secondary.importance)

    # ── Phase 2: 时间衰减归档 ──

    def _phase2_archive(self, memories: list[Memory]) -> int:
        """归档老旧低价值记忆。

        条件：timestamp 超过 archive_age_days 且 importance <= archive_max_importance。
        归档方式：importance 设为 1，content 前缀加 [archived]，保留可检索。
        """
        now = datetime.now(timezone.utc)
        count = 0

        for mem in memories:
            age_days = (now - mem.timestamp).days
            if age_days < self._archive_age_days:
                continue
            if mem.importance > self._archive_max_importance:
                continue
            # 已归档跳过
            if mem.content.startswith("[archived]"):
                continue

            mem.content = f"[archived] {mem.content}"
            mem.importance = 1
            try:
                self._memory_store.store(mem)
                count += 1
            except Exception:
                logger.debug("consolidation_archive_failed", extra={"id": mem.id}, exc_info=True)

        if count > 0:
            logger.info("consolidation_archived", extra={"count": count})
        return count

    # ── Phase 3: 概念提升 ──

    def _phase3_conceptual_elevation(self, memories: list[Memory]) -> list[Memory]:
        """从多条 episodic 记忆提炼 semantic 概念。

        算法：
        1. 按共享实体聚类（重叠 >= CONCEPT_ENTITY_OVERLAP_MIN）
        2. 每簇 >= CONCEPT_MIN_CLUSTER_SIZE 条 → LLM 提炼
        3. 生成 semantic 记忆写入 MemoryStore
        """
        episodic = [m for m in memories if m.memory_type == "episodic"]
        if len(episodic) < self._concept_min_cluster:
            return []

        clusters = self._cluster_by_entity_overlap(episodic)
        new_memories: list[Memory] = []

        for cluster in clusters:
            if len(cluster) < self._concept_min_cluster:
                continue

            memory_text = self._format_memories_for_prompt(cluster)
            prompt = _CONCEPT_ELEVATION_PROMPT.format(memories=memory_text)

            try:
                response = self._llm.chat(
                    messages=[{"role": "user", "content": prompt}],
                    tools=None,
                    tool_choice=None,
                    max_tokens=300,
                )
                summary = (response.choices[0].message.content or "").strip()
            except Exception:
                logger.debug("consolidation_elevation_llm_failed", exc_info=True)
                continue

            if not summary or len(summary) < 10:
                continue

            # 收集簇内所有实体
            all_entities: list[str] = []
            for m in cluster:
                all_entities.extend(m.entities)
            unique_entities = list(dict.fromkeys(all_entities))

            concept_memory = Memory(
                content=f"[概念提升] {summary}",
                summary=summary[:200],
                source="agent",
                timestamp=datetime.now(timezone.utc),
                importance=8,
                entities=unique_entities[:10],
                memory_type="semantic",
            )

            try:
                self._memory_store.store(concept_memory)
                # 写入向量库
                embedding = self._embedding.encode(concept_memory.content)
                self._vector_store.store(
                    doc_id=concept_memory.id,
                    embedding=embedding,
                    metadata={
                        "source": "agent",
                        "importance": 8,
                        "memory_type": "semantic",
                        "consolidation": "concept_elevation",
                    },
                )
            except Exception:
                logger.debug("consolidation_elevation_store_failed", exc_info=True)
                continue

            new_memories.append(concept_memory)
            logger.info(
                "consolidation_concept_elevated",
                extra={
                    "concept_id": concept_memory.id,
                    "source_count": len(cluster),
                    "summary": summary[:100],
                },
            )

        return new_memories

    # ── 聚类工具 ──

    @staticmethod
    def _cluster_by_entity_overlap(memories: list[Memory]) -> list[list[Memory]]:
        """贪心聚类：共享实体数 >= CONCEPT_ENTITY_OVERLAP_MIN 的归为一簇。

        每两条记忆若共享 >= 2 个实体，合并到同一簇。
        """
        parent = list(range(len(memories)))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for i in range(len(memories)):
            for j in range(i + 1, len(memories)):
                overlap = len(set(memories[i].entities) & set(memories[j].entities))
                if overlap >= CONCEPT_ENTITY_OVERLAP_MIN:
                    union(i, j)

        groups: dict[int, list[Memory]] = {}
        for idx, mem in enumerate(memories):
            root = find(idx)
            groups.setdefault(root, []).append(mem)

        return list(groups.values())

    @staticmethod
    def _format_memories_for_prompt(memories: list[Memory]) -> str:
        lines: list[str] = []
        for m in memories:
            ts = m.timestamp.strftime("%Y-%m-%d")
            content = m.summary or m.content[:200]
            lines.append(f"- [{ts}] {content}")
        return "\n".join(lines)
