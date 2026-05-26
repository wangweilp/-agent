"""ChromaDBAdapter 单元测试。"""
import pytest
import chromadb

from src.adapters.config import Settings
from src.adapters.vector_store import ChromaDBAdapter


@pytest.fixture
def settings():
    return Settings(deepseek_api_key="sk-test")


_counter = 0


@pytest.fixture
def chroma_store(settings):
    """使用 EphemeralClient 的内存模式进行测试。"""
    global _counter
    _counter += 1
    client = chromadb.Client()
    store = ChromaDBAdapter(
        settings, client=client, collection_name=f"test_coll_{_counter}"
    )
    yield store
    store.close()


class TestStore:
    def test_returns_doc_id(self, chroma_store):
        doc_id = chroma_store.store(
            "mem_001", [0.1, 0.2, 0.3], {"source": "user", "summary": "测试"}
        )
        assert doc_id == "mem_001"

    def test_upsert_replaces_existing(self, chroma_store):
        chroma_store.store("mem_001", [0.1, 0.2, 0.3], {"version": "v1"})
        chroma_store.store("mem_001", [0.4, 0.5, 0.6], {"version": "v2"})

        assert chroma_store.count() == 1

    def test_empty_embedding_raises_error(self, chroma_store):
        with pytest.raises(ValueError, match="不能为空"):
            chroma_store.store("mem_001", [], {"source": "user"})


class TestSearch:
    def test_returns_results(self, chroma_store):
        chroma_store.store("mem_1", [1.0, 0.0, 0.0], {"text": "苹果"})
        chroma_store.store("mem_2", [0.0, 1.0, 0.0], {"text": "香蕉"})
        chroma_store.store("mem_3", [0.0, 0.0, 1.0], {"text": "橙子"})

        results = chroma_store.search([1.0, 0.1, 0.0], k=2)

        assert len(results) == 2
        assert results[0]["id"] == "mem_1"

    def test_each_result_has_required_keys(self, chroma_store):
        chroma_store.store("mem_1", [1.0, 0.0, 0.0], {"text": "测试"})

        results = chroma_store.search([1.0, 0.0, 0.0], k=1)

        result = results[0]
        assert "id" in result
        assert "metadata" in result
        assert "distance" in result

    def test_k_larger_than_collection_returns_fewer(self, chroma_store):
        chroma_store.store("mem_1", [1.0, 0.0, 0.0], {})

        results = chroma_store.search([1.0, 0.0, 0.0], k=10)
        assert len(results) == 1

    def test_empty_embedding_raises_error(self, chroma_store):
        with pytest.raises(ValueError, match="不能为空"):
            chroma_store.search([], k=5)


class TestDelete:
    def test_delete_removes_document(self, chroma_store):
        chroma_store.store("mem_1", [1.0, 0.0, 0.0], {})
        assert chroma_store.count() == 1

        chroma_store.delete("mem_1")
        assert chroma_store.count() == 0

    def test_delete_nonexistent_does_not_raise(self, chroma_store):
        chroma_store.delete("nonexistent")


class TestCount:
    def test_count_returns_total(self, chroma_store):
        assert chroma_store.count() == 0
        chroma_store.store("mem_1", [1.0, 0.0, 0.0], {})
        chroma_store.store("mem_2", [0.0, 1.0, 0.0], {})
        assert chroma_store.count() == 2


class TestContextManager:
    def test_enter_exit(self, settings):
        client = chromadb.Client()
        with ChromaDBAdapter(settings, client=client) as store:
            store.store("mem_1", [1.0, 0.0, 0.0], {})
            assert store.count() == 1


class TestMetadataSanitization:
    def test_non_string_key_converted(self, chroma_store):
        """ChromaDB 要求 metadata value 为 str|int|float|bool。"""
        chroma_store.store(
            "mem_1", [1.0, 0.0, 0.0], {"count": 5, "active": True, "score": 3.14}
        )
        results = chroma_store.search([1.0, 0.0, 0.0], k=1)
        assert results[0]["metadata"]["count"] == 5
        assert results[0]["metadata"]["active"] is True
        assert results[0]["metadata"]["score"] == 3.14


class TestProtocolCompliance:
    def test_is_vector_store(self, chroma_store):
        from src.core.memory import VectorStore
        assert isinstance(chroma_store, VectorStore)
