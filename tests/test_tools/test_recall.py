"""RecallTool 单元测试。"""
from datetime import datetime, timezone
from unittest.mock import create_autospec

import pytest

from src.core.memory import EmbeddingProvider, MemoryStore, VectorStore
from src.core.types import Memory, SearchResult
from src.tools.recall import RecallTool


@pytest.fixture
def sample_memory():
    return Memory(
        id="mem_1",
        content="用户喜欢喝咖啡，每天两杯",
        summary=None,
        source="user",
        timestamp=datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc),
        importance=7,
        entities=["咖啡"],
    )


@pytest.fixture
def mock_memory_store(sample_memory):
    store = create_autospec(MemoryStore, instance=True)
    store.get_by_id.return_value = sample_memory
    store.get_recent.return_value = [sample_memory]
    return store


@pytest.fixture
def mock_vector_store():
    store = create_autospec(VectorStore, instance=True)
    store.search.return_value = [
        SearchResult(doc_id="mem_1", score=0.15, metadata={"source": "user"}),
        SearchResult(doc_id="mem_2", score=0.25, metadata={"source": "user"}),
    ]
    return store


@pytest.fixture
def mock_embedding():
    provider = create_autospec(EmbeddingProvider, instance=True)
    provider.encode.return_value = [0.1] * 512
    return provider


@pytest.fixture
def tool(mock_memory_store, mock_vector_store, mock_embedding):
    return RecallTool(mock_memory_store, mock_vector_store, mock_embedding)


class TestRecallToolProtocol:
    def test_has_name(self, tool):
        assert tool.name == "recall"

    def test_has_description(self, tool):
        assert len(tool.description) > 0

    def test_no_confirmation_required(self, tool):
        assert tool.requires_confirmation is False

    def test_schema_is_valid(self, tool):
        s = tool.schema
        assert s["type"] == "function"
        props = s["function"]["parameters"]["properties"]
        assert "query" in props
        assert "top_k" in props


class TestRecallExecute:
    def test_search_returns_formatted_results(self, tool):
        result = tool.execute({"query": "咖啡"})

        assert result.success is True
        assert result.metadata["count"] >= 1

    def test_empty_query_returns_error(self, tool):
        result = tool.execute({"query": ""})
        assert result.success is False

    def test_no_results(self, tool, mock_vector_store, mock_memory_store):
        mock_vector_store.search.return_value = []
        mock_memory_store.get_recent.return_value = []

        result = tool.execute({"query": "不存在的主题xyz"})
        assert result.success is True
        assert "未找到" in result.content
        assert result.metadata["count"] == 0

    def test_respects_top_k(self, tool):
        result = tool.execute({"query": "测试", "top_k": 1})
        assert result.success is True
        assert result.metadata["count"] <= 1


class TestRecallErrorHandling:
    def test_embedding_failure_returns_error(self, tool, mock_embedding):
        mock_embedding.encode.side_effect = RuntimeError("模型崩溃")

        result = tool.execute({"query": "测试"})
        assert result.success is False

    def test_vector_search_failure_returns_error(self, tool, mock_vector_store):
        mock_vector_store.search.side_effect = RuntimeError("ChromaDB 崩溃")

        result = tool.execute({"query": "测试"})
        assert result.success is False
