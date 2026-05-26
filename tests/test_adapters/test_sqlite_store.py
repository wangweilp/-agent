"""SQLiteStoreAdapter 单元测试。"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock

from src.adapters.config import Settings
from src.core.types import Memory, Entity


@pytest.fixture
def settings():
    return Settings(deepseek_api_key="sk-test")


@pytest.fixture
def mock_embedding():
    mock = MagicMock()
    mock.get_embedding.return_value = [0.1, 0.2, 0.3]
    return mock


@pytest.fixture
def mock_vector_store():
    return MagicMock()


@pytest.fixture
def store(settings, mock_embedding, mock_vector_store):
    from src.adapters.sqlite_store import SQLiteStoreAdapter
    store = SQLiteStoreAdapter(
        config=settings,
        embedding_provider=mock_embedding,
        vector_store=mock_vector_store,
        db_path=":memory:",
    )
    yield store
    store.close()


def _make_memory(
    id="mem_001",
    content="这是一条测试记忆",
    summary="测试摘要",
    source="user",
    entities=None,
    relations=None,
    embedding=None,
    timestamp=None,
):
    return Memory(
        id=id,
        content=content,
        summary=summary,
        source=source,
        timestamp=timestamp or datetime(2025, 1, 15, 10, 30, 0),
        importance=7,
        entities=entities or ["测试实体"],
        relations=relations or [{"s": "张三", "p": "认识", "o": "李四"}],
        embedding=embedding,
        memory_type="episodic",
    )


class TestStore:
    def test_store_returns_memory_id(self, store):
        memory = _make_memory()
        result = store.store(memory)
        assert result == "mem_001"

    def test_get_by_id_returns_stored_memory(self, store):
        memory = _make_memory()
        store.store(memory)

        retrieved = store.get_by_id("mem_001")
        assert retrieved is not None
        assert retrieved.id == "mem_001"
        assert retrieved.content == "这是一条测试记忆"
        assert retrieved.importance == 7

    def test_store_with_embedding_calls_vector_store(self, store, mock_vector_store):
        memory = _make_memory(embedding=[0.5, 0.6, 0.7])
        store.store(memory)

        mock_vector_store.store.assert_called_once()
        kwargs = mock_vector_store.store.call_args.kwargs
        assert kwargs["doc_id"] == "mem_001"
        assert kwargs["embedding"] == [0.5, 0.6, 0.7]

    def test_store_without_embedding_computes_it(self, store, mock_embedding, mock_vector_store):
        memory = _make_memory(embedding=None)
        store.store(memory)

        mock_embedding.get_embedding.assert_called_once_with("这是一条测试记忆")
        mock_vector_store.store.assert_called_once()

    def test_entity_upsert_increments_mention_count(self, store):
        mem1 = _make_memory(id="mem_001", entities=["张三"])
        mem2 = _make_memory(id="mem_002", entities=["张三"], content="另一条记忆")

        store.store(mem1)
        store.store(mem2)

        results = store.search_by_entity("张三")
        assert len(results) == 2

    def test_relations_are_stored(self, store):
        memory = _make_memory(
            id="mem_003",
            relations=[{"s": "张三", "p": "工作于", "o": "字节跳动"}],
        )
        store.store(memory)

        retrieved = store.get_by_id("mem_003")
        assert retrieved is not None
        assert retrieved.relations == [{"s": "张三", "p": "工作于", "o": "字节跳动"}]


class TestSearchByEntity:
    def test_returns_only_matching_memories(self, store):
        store.store(_make_memory(id="mem_001", entities=["张三"]))
        store.store(_make_memory(id="mem_002", entities=["李四"]))

        results = store.search_by_entity("张三")
        assert len(results) == 1
        assert results[0].id == "mem_001"

    def test_no_match_returns_empty_list(self, store):
        results = store.search_by_entity("不存在的实体")
        assert results == []


class TestGetRecent:
    def test_returns_memories_in_reverse_timestamp_order(self, store):
        mem1 = _make_memory(
            id="old", timestamp=datetime(2025, 1, 1, 12, 0, 0), entities=[]
        )
        mem2 = _make_memory(
            id="new", timestamp=datetime(2025, 6, 1, 12, 0, 0), entities=[]
        )

        store.store(mem1)
        store.store(mem2)

        recent = store.get_recent(limit=2)
        assert recent[0].id == "new"
        assert recent[1].id == "old"

    def test_limit_respected(self, store):
        for i in range(5):
            store.store(_make_memory(id=f"mem_{i:03d}", entities=[], timestamp=datetime(2025, 1, i + 1)))

        recent = store.get_recent(limit=3)
        assert len(recent) == 3


class TestSearchSemantic:
    def test_embeds_query_and_searches_vector_store(self, store, mock_embedding, mock_vector_store):
        mock_vector_store.search.return_value = [
            {"id": "mem_001", "metadata": {}, "distance": 0.1},
        ]
        store.store(_make_memory(id="mem_001"))

        mock_embedding.get_embedding.reset_mock()
        results = store.search_semantic("查询文本", top_k=5)

        mock_embedding.get_embedding.assert_called_once_with("查询文本")
        mock_vector_store.search.assert_called_once()
        assert len(results) == 1
        assert results[0].id == "mem_001"

    def test_orphan_vector_skipped(self, store, mock_vector_store):
        """ChromaDB 返回了 SQLite 中不存在的 doc_id，应该跳过。"""
        mock_vector_store.search.return_value = [
            {"id": "orphan_id", "metadata": {}, "distance": 0.05},
        ]

        results = store.search_semantic("查询", top_k=5)
        assert results == []

    def test_empty_search_returns_empty(self, store, mock_vector_store):
        mock_vector_store.search.return_value = []
        results = store.search_semantic("查询", top_k=5)
        assert results == []


class TestGetById:
    def test_increments_access_count(self, store):
        store.store(_make_memory(id="mem_001"))
        store.get_by_id("mem_001")
        retrieved = store.get_by_id("mem_001")

        assert retrieved.access_count >= 2

    def test_nonexistent_returns_none(self, store):
        assert store.get_by_id("nonexistent") is None


class TestProtocolCompliance:
    def test_is_memory_store(self, store):
        from src.core.memory import MemoryStore
        assert isinstance(store, MemoryStore)
