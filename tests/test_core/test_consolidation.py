"""MemoryConsolidator 单元测试。"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, create_autospec

import pytest

from src.core.consolidation import (
    CONCEPT_ENTITY_OVERLAP_MIN,
    CONCEPT_MIN_CLUSTER_SIZE,
    ConsolidationResult,
    DefaultMemoryConsolidator,
    MemoryConsolidator,
)
from src.core.memory import ChatModel, EmbeddingProvider, MemoryStore, VectorStore
from src.core.types import Memory, SearchResult


# ── Fixtures ──

@pytest.fixture
def mock_memory_store():
    return create_autospec(MemoryStore, instance=True)


@pytest.fixture
def mock_vector_store():
    store = create_autospec(VectorStore, instance=True)
    store.search.return_value = []
    return store


@pytest.fixture
def mock_embedding():
    provider = create_autospec(EmbeddingProvider, instance=True)
    provider.encode.return_value = [0.1] * 512
    return provider


@pytest.fixture
def mock_llm():
    return create_autospec(ChatModel, instance=True)


@pytest.fixture
def consolidator(mock_memory_store, mock_vector_store, mock_embedding, mock_llm):
    return DefaultMemoryConsolidator(
        mock_memory_store, mock_vector_store, mock_embedding, mock_llm,
    )


def _make_memory(
    id_: str = "m1",
    content: str = "测试记忆",
    source: str = "user",
    days_ago: int = 10,
    importance: int = 5,
    entities: list[str] | None = None,
    memory_type: str = "episodic",
) -> Memory:
    return Memory(
        id=id_,
        content=content,
        summary=None,
        source=source,
        timestamp=datetime.now(timezone.utc) - timedelta(days=days_ago),
        importance=importance,
        entities=entities or [],
        memory_type=memory_type,
    )


def _make_mock_chat_response(content: str):
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    return resp


# ── Protocol 合规测试 ──

class TestProtocol:
    def test_default_consolidator_implements_protocol(self, consolidator):
        assert isinstance(consolidator, MemoryConsolidator)

    def test_consolidation_result_defaults(self):
        r = ConsolidationResult()
        assert r.merged_count == 0
        assert r.archived_count == 0
        assert r.deleted_count == 0
        assert r.new_memories == []
        assert r.total_affected == 0

    def test_consolidation_result_total_affected(self):
        r = ConsolidationResult(
            merged_count=2, archived_count=1, deleted_count=0,
            new_memories=[_make_memory("new1")],
        )
        assert r.total_affected == 4


# ── Phase 1:  相似记忆聚合 ──

class TestPhase1Merge:
    def test_merges_highly_similar_memories(
        self, consolidator, mock_vector_store, mock_memory_store, mock_embedding,
    ):
        m1 = _make_memory("m1", "用户在学习 LangGraph")
        m2 = _make_memory("m2", "用户今天继续学习 LangGraph")
        mock_vector_store.search.return_value = [
            SearchResult(doc_id="m2", score=0.92, metadata={}),
        ]
        mock_memory_store.get_by_id.return_value = m2

        merged, deleted = consolidator._phase1_merge([m1])

        assert merged == 1
        assert deleted >= 0
        assert "合并自" in m1.content or deleted > 0

    def test_no_merge_when_below_threshold(
        self, consolidator, mock_vector_store, mock_memory_store,
    ):
        m1 = _make_memory("m1", "用户在学习 Python")
        mock_vector_store.search.return_value = [
            SearchResult(doc_id="m2", score=0.60, metadata={}),
        ]

        merged, deleted = consolidator._phase1_merge([m1])

        assert merged == 0
        assert deleted == 0

    def test_no_merge_when_no_candidates(
        self, consolidator, mock_vector_store,
    ):
        m1 = _make_memory("m1", "唯一记忆")
        mock_vector_store.search.return_value = []

        merged, deleted = consolidator._phase1_merge([m1])

        assert merged == 0

    def test_merge_skips_self(
        self, consolidator, mock_vector_store, mock_memory_store,
    ):
        m1 = _make_memory("m1", "自身匹配")
        mock_vector_store.search.return_value = [
            SearchResult(doc_id="m1", score=0.99, metadata={}),
        ]

        merged, deleted = consolidator._phase1_merge([m1])

        assert merged == 0  # 不与自身合并

    def test_merge_skips_deleted_ids(
        self, consolidator, mock_vector_store, mock_memory_store,
    ):
        m1 = _make_memory("m1", "第一条")
        m2 = _make_memory("m2", "第二条")
        mock_vector_store.search.side_effect = [
            [SearchResult(doc_id="m2", score=0.91, metadata={})],
            [SearchResult(doc_id="m1", score=0.91, metadata={})],
        ]
        mock_memory_store.get_by_id.return_value = m2  # Both lookups return m2 -- first merge succeeds, second should find id deleted

        merged, deleted = consolidator._phase1_merge([m1, m2])

        assert merged >= 1

    def test_merge_pair_updates_primary(self):
        primary = _make_memory("p", "主记忆", entities=["AI"])
        secondary = _make_memory("s", "从记忆", entities=["LangGraph"], importance=8)

        DefaultMemoryConsolidator._merge_pair(primary, secondary)

        assert "从记忆" in primary.content
        assert "AI" in primary.entities
        assert "LangGraph" in primary.entities
        assert primary.importance == 8  # max(5, 8)


# ── Phase 2: 时间衰减归档 ──

class TestPhase2Archive:
    def test_archives_old_low_importance_memory(
        self, consolidator, mock_memory_store,
    ):
        old_mem = _make_memory("old", "很久以前的信息", days_ago=100, importance=3)

        count = consolidator._phase2_archive([old_mem])

        assert count == 1
        assert old_mem.content.startswith("[archived]")
        assert old_mem.importance == 1
        mock_memory_store.store.assert_called_once()

    def test_does_not_archive_recent_memory(
        self, consolidator, mock_memory_store,
    ):
        recent = _make_memory("recent", "新信息", days_ago=10, importance=3)

        count = consolidator._phase2_archive([recent])

        assert count == 0

    def test_does_not_archive_high_importance_old_memory(
        self, consolidator, mock_memory_store,
    ):
        important_old = _make_memory("vip", "重要的旧信息", days_ago=100, importance=7)

        count = consolidator._phase2_archive([important_old])

        assert count == 0
        assert not important_old.content.startswith("[archived]")

    def test_skips_already_archived(
        self, consolidator, mock_memory_store,
    ):
        archived = _make_memory("arch", "已归档", days_ago=100, importance=1)
        archived.content = "[archived] 已归档"

        count = consolidator._phase2_archive([archived])

        assert count == 0


# ── Phase 3: 概念提升 ──

class TestPhase3ConceptualElevation:
    def test_elevates_cluster_to_semantic_memory(
        self, consolidator, mock_llm, mock_memory_store, mock_vector_store, mock_embedding,
    ):
        # e1-e2 共享 AI+RAG, e2-e3 共享 AI+向量数据库, e1-e3 共享 AI → ≥2 重叠成立 → 一簇
        memories = [
            _make_memory("e1", "今天学习了 RAG 检索增强生成", entities=["RAG", "AI"], memory_type="episodic"),
            _make_memory("e2", "学习了 RAG 与向量数据库", entities=["RAG", "AI", "向量数据库"], memory_type="episodic"),
            _make_memory("e3", "学习了向量数据库与 Embedding", entities=["向量数据库", "AI"], memory_type="episodic"),
        ]
        mock_llm.chat.return_value = _make_mock_chat_response("用户正在系统学习 AI Agent 技术栈：检索、向量化和嵌入表示。")

        result = consolidator._phase3_conceptual_elevation(memories)

        assert len(result) == 1
        assert result[0].memory_type == "semantic"
        assert result[0].source == "agent"
        assert result[0].importance == 8
        mock_memory_store.store.assert_called_once()
        mock_vector_store.store.assert_called_once()

    def test_no_elevation_for_small_cluster(
        self, consolidator, mock_llm,
    ):
        memories = [
            _make_memory("e1", "学 RAG", entities=["RAG"], memory_type="episodic"),
            _make_memory("e2", "学 Python", entities=["Python"], memory_type="episodic"),
        ]

        result = consolidator._phase3_conceptual_elevation(memories)

        assert len(result) == 0

    def test_no_elevation_for_empty_input(
        self, consolidator,
    ):
        result = consolidator._phase3_conceptual_elevation([])
        assert len(result) == 0

    def test_no_elevation_on_llm_failure(
        self, consolidator, mock_llm,
    ):
        memories = [
            _make_memory("e1", "学 RAG", entities=["RAG", "AI"], memory_type="episodic"),
            _make_memory("e2", "学 ChromaDB", entities=["ChromaDB", "AI"], memory_type="episodic"),
            _make_memory("e3", "学 Embedding", entities=["Embedding", "AI"], memory_type="episodic"),
        ]
        mock_llm.chat.side_effect = RuntimeError("LLM 不可用")

        result = consolidator._phase3_conceptual_elevation(memories)

        assert len(result) == 0  # 降级：不崩溃

    def test_no_elevation_for_empty_llm_response(
        self, consolidator, mock_llm,
    ):
        memories = [
            _make_memory("e1", "学 RAG", entities=["RAG", "AI"], memory_type="episodic"),
            _make_memory("e2", "学 ChromaDB", entities=["ChromaDB", "AI"], memory_type="episodic"),
            _make_memory("e3", "学 Embedding", entities=["Embedding", "AI"], memory_type="episodic"),
        ]
        mock_llm.chat.return_value = _make_mock_chat_response("   ")  # 空白

        result = consolidator._phase3_conceptual_elevation(memories)

        assert len(result) == 0


# ── 聚类工具 ──

class TestClusterByEntityOverlap:
    def test_groups_overlapping_entities(self, consolidator):
        memories = [
            _make_memory("e1", entities=["RAG", "AI", "检索"]),
            _make_memory("e2", entities=["AI", "RAG", "语义"]),
            _make_memory("e3", entities=["Python", "Django"]),
        ]

        clusters = consolidator._cluster_by_entity_overlap(memories)

        assert len(clusters) == 2
        # e1 + e2 share "RAG"+"AI" → >=2 overlap → same cluster
        ids_by_cluster = [{m.id for m in c} for c in clusters]
        assert {"e1", "e2"} in ids_by_cluster or {"e1", "e2"} == ids_by_cluster[0]

    def test_all_separate_when_no_overlap(self, consolidator):
        memories = [
            _make_memory("e1", entities=["A"]),
            _make_memory("e2", entities=["B"]),
        ]

        clusters = consolidator._cluster_by_entity_overlap(memories)

        assert len(clusters) == 2


# ── 端到端整合 ──

class TestEndToEndConsolidation:
    def test_full_consolidation_pipeline(self):
        """三阶段全流程端到端验证 — 逐阶段调用，各阶段独立数据。"""
        from src.core.consolidation import DefaultMemoryConsolidator

        sqlite = _InMemoryStore()
        chroma = _FakeVectorStore()
        emb = _FakeEmbedding()
        llm = _FakeLLM("用户正在系统学习 AI Agent 技术栈核心组件。")
        c = DefaultMemoryConsolidator(sqlite, chroma, emb, llm)

        # ── Phase 1: 合并 ──
        sim1 = _make_memory("sim1", "用户在学习 RAG", entities=["RAG", "AI"])
        sim2 = _make_memory("sim2", "用户继续深入学习 RAG 和检索技术", entities=["RAG", "检索"])
        sqlite._memories = {"sim2": sim2}
        chroma._search_returns = [SearchResult(doc_id="sim2", score=0.90, metadata={})]

        merged, deleted = c._phase1_merge([sim1])
        assert merged == 1
        assert deleted == 1

        # ── Phase 2: 归档 ──
        old = _make_memory("old1", "旧信息", days_ago=100, importance=2)
        archived = c._phase2_archive([old])
        assert archived == 1
        assert old.content.startswith("[archived]")
        assert old.importance == 1

        # ── Phase 3: 概念提升 ──
        e1 = _make_memory("e1", "学 RAG", entities=["RAG", "AI"], memory_type="episodic")
        e2 = _make_memory("e2", "学向量数据库", entities=["向量数据库", "AI", "RAG"], memory_type="episodic")
        e3 = _make_memory("e3", "学语义搜索", entities=["语义搜索", "AI", "RAG"], memory_type="episodic")
        concepts = c._phase3_conceptual_elevation([e1, e2, e3])
        assert len(concepts) >= 1
        assert concepts[0].memory_type == "semantic"

        # ── ConsolidationResult 结构验证 ──
        r = ConsolidationResult(merged_count=1, archived_count=1, deleted_count=1,
                                new_memories=[concepts[0]])
        assert r.total_affected == 4


# ── Fake 适配器（绕过 autospec protocol 签名冲突）──

class _InMemoryStore:
    """最小 MemoryStore 实现 — 用于测试。"""
    def __init__(self):
        self._memories: dict[str, Memory] = {}

    def store(self, memory: Memory) -> str:
        self._memories[memory.id] = memory
        return memory.id

    def delete(self, memory_id: str) -> None:
        self._memories.pop(memory_id, None)

    def search_by_entity(self, entity_name: str) -> list[Memory]:
        return [m for m in self._memories.values() if entity_name in m.entities]

    def get_by_id(self, memory_id: str) -> Memory | None:
        return self._memories.get(memory_id)

    def get_recent(self, limit: int) -> list[Memory]:
        return list(self._memories.values())[:limit]


class _FakeVectorStore:
    """最小 VectorStore 实现。"""
    def __init__(self):
        self._search_returns: list[SearchResult] = []

    def store(self, doc_id: str, embedding, metadata) -> str:
        return doc_id

    def search(self, embedding, k: int) -> list[SearchResult]:
        return self._search_returns


class _FakeEmbedding:
    def encode(self, text: str) -> list[float]:
        return [0.1] * 512


class _FakeLLM:
    def __init__(self, response: str):
        self._response = response

    def chat(self, messages, tools=None, tool_choice=None, stream=False, **kwargs):
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = self._response
        return resp
