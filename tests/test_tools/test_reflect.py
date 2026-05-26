"""ReflectTool 单元测试。"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, create_autospec

import pytest

from src.core.memory import ChatModel, EmbeddingProvider, MemoryStore, VectorStore
from src.core.types import Memory, SearchResult
from src.tools.reflect import ReflectTool


@pytest.fixture
def sample_memory():
    return Memory(
        id="mem_1",
        content="用户计划今年学会 Rust 编程",
        summary=None,
        source="user",
        timestamp=datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc),
        importance=7,
        entities=["Rust"],
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
    ]
    return store


@pytest.fixture
def mock_embedding():
    provider = create_autospec(EmbeddingProvider, instance=True)
    provider.encode.return_value = [0.1] * 512
    return provider


@pytest.fixture
def mock_llm():
    llm = create_autospec(ChatModel, instance=True)
    return llm


@pytest.fixture
def tool(mock_memory_store, mock_vector_store, mock_embedding, mock_llm):
    return ReflectTool(mock_memory_store, mock_vector_store, mock_embedding, mock_llm)


class TestReflectToolProtocol:
    def test_has_name(self, tool):
        assert tool.name == "reflect"

    def test_has_description(self, tool):
        assert len(tool.description) > 0

    def test_no_confirmation_required(self, tool):
        assert tool.requires_confirmation is False

    def test_schema_is_valid(self, tool):
        s = tool.schema
        assert s["type"] == "function"
        props = s["function"]["parameters"]["properties"]
        assert "topic" in props
        assert "recent_n" in props


class TestReflectExecute:
    def test_stores_insight_when_llm_finds_something(self, tool, mock_llm, mock_memory_store, mock_vector_store):
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = "发现用户同时在学习 Rust 和 C++，建议对比学习"
        mock_llm.chat.return_value = response

        result = tool.execute({"topic": "编程学习"})

        assert result.success is True
        assert "发现" in result.content
        assert result.metadata["insight_stored"] is True
        # 应该存储了反思记忆
        assert mock_memory_store.store.call_count >= 1

    def test_no_record_when_nothing_found(self, tool, mock_llm, mock_memory_store):
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = "NOTHING_TO_RECORD"
        mock_llm.chat.return_value = response

        # 重置 store 计数（构造时会调用 get_recent/get_by_id）
        mock_memory_store.store.reset_mock()

        result = tool.execute({"topic": "编程学习"})

        assert result.success is True
        assert "未发现" in result.content
        mock_memory_store.store.assert_not_called()

    def test_empty_topic_returns_error(self, tool):
        result = tool.execute({"topic": ""})
        assert result.success is False

    def test_no_memories_returns_gracefully(self, tool, mock_vector_store, mock_memory_store):
        mock_vector_store.search.return_value = []
        mock_memory_store.get_recent.return_value = []

        result = tool.execute({"topic": "不存在的主题"})
        assert result.success is True
        assert result.metadata["checked"] == 0


class TestReflectAntiLoop:
    def test_too_many_reflections_skips(self, tool, mock_memory_store):
        """近期 reflect 过多 → 跳过本次反思。"""
        reflect_memories = []
        for i in range(5):
            reflect_memories.append(Memory(
                id=f"ref_{i}",
                content=f"反思内容 {i}",
                summary=None,
                source="reflect",
                timestamp=datetime(2026, 5, 26, tzinfo=timezone.utc),
                memory_type="reflect",
            ))
        mock_memory_store.get_recent.return_value = reflect_memories

        result = tool.execute({"topic": "测试主题"})
        assert result.success is True
        assert result.metadata["skipped"] == "anti_loop"

    def test_normal_when_few_reflections(self, tool, mock_memory_store, mock_llm):
        """少量 reflect → 正常执行。"""
        mock_memory_store.get_recent.return_value = []  # 没有 reflect 记忆
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = "NOTHING_TO_RECORD"
        mock_llm.chat.return_value = response

        result = tool.execute({"topic": "测试主题"})
        assert result.success is True
        assert "未发现" in result.content

    def test_excludes_reflect_source_from_search(self, tool, mock_memory_store, mock_llm):
        """source=reflect 的记忆不参与反思。"""
        reflect_mem = Memory(
            id="ref_1",
            content="反思记忆",
            summary=None,
            source="reflect",
            timestamp=datetime(2026, 5, 26, tzinfo=timezone.utc),
            memory_type="reflect",
        )
        normal_mem = Memory(
            id="norm_1",
            content="普通记忆",
            summary=None,
            source="user",
            timestamp=datetime(2026, 5, 26, tzinfo=timezone.utc),
        )
        # get_by_id 返回 reflect 记忆，但应被过滤
        mock_memory_store.get_by_id.return_value = reflect_mem
        mock_memory_store.get_recent.return_value = [normal_mem]
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = "NOTHING_TO_RECORD"
        mock_llm.chat.return_value = response

        result = tool.execute({"topic": "测试"})
        assert result.success is True


class TestReflectErrorHandling:
    def test_llm_failure_returns_error(self, tool, mock_llm):
        mock_llm.chat.side_effect = RuntimeError("LLM 崩溃")

        result = tool.execute({"topic": "测试"})
        assert result.success is False
