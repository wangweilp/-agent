"""RememberTool 单元测试。"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, create_autospec

import pytest

from src.core.memory import EmbeddingProvider, MemoryStore, VectorStore
from src.core.types import Memory, SearchResult
from src.tools.remember import RememberTool


@pytest.fixture
def mock_memory_store():
    return create_autospec(MemoryStore, instance=True)


@pytest.fixture
def mock_vector_store():
    return create_autospec(VectorStore, instance=True)


@pytest.fixture
def mock_embedding():
    provider = create_autospec(EmbeddingProvider, instance=True)
    provider.encode.return_value = [0.1] * 512
    return provider


@pytest.fixture
def tool(mock_memory_store, mock_vector_store, mock_embedding):
    return RememberTool(mock_memory_store, mock_vector_store, mock_embedding)


class TestRememberToolProtocol:
    def test_has_name(self, tool):
        assert tool.name == "remember"

    def test_has_description(self, tool):
        assert len(tool.description) > 0

    def test_no_confirmation_required(self, tool):
        assert tool.requires_confirmation is False

    def test_schema_is_valid_function_schema(self, tool):
        s = tool.schema
        assert s["type"] == "function"
        assert s["function"]["name"] == "remember"
        assert "parameters" in s["function"]
        assert "content" in s["function"]["parameters"]["properties"]
        assert "content" in s["function"]["parameters"]["required"]


class TestRememberExecute:
    def test_stores_memory_and_returns_success(self, tool, mock_memory_store, mock_vector_store, mock_embedding):
        result = tool.execute({"content": "用户喜欢喝咖啡", "entities": ["咖啡"]})

        assert result.success is True
        assert "已存储记忆" in result.content
        mock_memory_store.store.assert_called_once()
        mock_vector_store.store.assert_called_once()
        # encode 被调用两次：新颖度检测 + 实际存储
        assert mock_embedding.encode.call_count == 2

    def test_stores_memory_id_in_metadata(self, tool, mock_memory_store):
        result = tool.execute({"content": "测试记忆"})

        assert "memory_id" in result.metadata
        mock_memory_store.store.assert_called_once()
        stored_memory = mock_memory_store.store.call_args[0][0]
        assert stored_memory.id == result.metadata["memory_id"]

    def test_stores_entities(self, tool, mock_memory_store):
        tool.execute({"content": "内容", "entities": ["实体A", "实体B"]})

        stored_memory = mock_memory_store.store.call_args[0][0]
        assert "实体A" in stored_memory.entities
        assert "实体B" in stored_memory.entities

    def test_vector_store_metadata_includes_source(self, tool, mock_vector_store):
        tool.execute({"content": "内容"})

        call_kwargs = mock_vector_store.store.call_args.kwargs
        assert call_kwargs["metadata"]["source"] == "user"

    def test_empty_content_returns_error(self, tool):
        result = tool.execute({"content": ""})

        assert result.success is False
        assert "不能为空" in result.error

    def test_empty_content_whitespace_only(self, tool):
        result = tool.execute({"content": "   "})

        assert result.success is False


class TestImportanceCalculation:
    def test_base_score_is_5(self, tool):
        result = tool.execute({"content": "普通信息"})
        assert result.metadata["importance"] == 5

    def test_entity_bonus(self, tool):
        result = tool.execute({"content": "信息", "entities": ["A", "B", "C", "D"]})
        assert result.metadata["importance"] >= 7  # 5 + min(4,3) = 8

    def test_keyword_bonus(self, tool):
        result = tool.execute({"content": "这是一个很重要的信息，必须记住"})
        assert result.metadata["importance"] >= 7  # 5 + "重要" + "必须" + "记住" = 8

    def test_emotion_bonus(self, tool):
        result = tool.execute({"content": "今天很开心也很感动"})
        assert result.metadata["importance"] >= 7  # 5 + "开心" + "感动" = 7

    def test_capped_at_10(self, tool):
        result = tool.execute({
            "content": "重要 关键 必须 记住 永远 绝对 一定 目标 计划 决定 秘密 密码 账号 开心 难过",
            "entities": ["A", "B", "C", "D", "E"],
        })
        assert result.metadata["importance"] <= 10

    def test_importance_override(self, tool):
        result = tool.execute({"content": "普通内容", "importance_override": 9})
        assert result.metadata["importance"] == 9

    def test_override_clamped_to_10(self, tool):
        result = tool.execute({"content": "内容", "importance_override": 99})
        assert result.metadata["importance"] == 10

    def test_override_clamped_to_1(self, tool):
        result = tool.execute({"content": "内容", "importance_override": -5})
        assert result.metadata["importance"] == 1


class TestRememberErrorHandling:
    def test_embedding_failure_returns_error(self, tool, mock_embedding):
        mock_embedding.encode.side_effect = RuntimeError("模型崩溃")

        result = tool.execute({"content": "内容"})
        assert result.success is False
        assert "失败" in result.error

    def test_memory_store_failure_returns_error(self, tool, mock_memory_store):
        mock_memory_store.store.side_effect = RuntimeError("数据库崩溃")

        result = tool.execute({"content": "内容"})
        assert result.success is False


class TestNoveltyScoring:
    def test_merge_when_highly_similar(self, tool, mock_vector_store, mock_memory_store):
        """高相似度 → 合并更新已有记忆。"""
        existing = Memory(
            id="existing_1",
            content="用户在学习 LangGraph",
            summary=None,
            source="user",
            timestamp=datetime(2026, 5, 25, tzinfo=timezone.utc),
        )
        mock_vector_store.search.return_value = [
            SearchResult(doc_id="existing_1", score=0.10, metadata={}),
        ]
        mock_memory_store.get_by_id.return_value = existing

        result = tool.execute({"content": "用户今天继续学习 LangGraph"})

        assert result.success is True
        assert result.metadata["merged"] is True
        assert result.metadata["existing_id"] == "existing_1"

    def test_downgrade_when_moderately_similar(self, tool, mock_vector_store):
        """中等相似度 → 降权存储。"""
        mock_vector_store.search.return_value = [
            SearchResult(doc_id="existing_1", score=0.20, metadata={}),
        ]
        # 基础分 5，降权 -2 = 3
        result = tool.execute({"content": "普通信息"})
        assert result.success is True
        assert "merged" not in result.metadata
        assert result.metadata["importance"] == 3  # 5 - 2

    def test_normal_store_when_novel(self, tool, mock_vector_store):
        """低相似度 → 正常存储。"""
        mock_vector_store.search.return_value = [
            SearchResult(doc_id="existing_1", score=0.50, metadata={}),
        ]
        result = tool.execute({"content": "全新信息"})
        assert result.success is True
        assert result.metadata["novelty"]["action"] == "store"


