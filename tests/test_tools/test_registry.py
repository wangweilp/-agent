"""ToolRegistry 单元测试。"""
from unittest.mock import MagicMock, create_autospec

import pytest

from src.core.memory import ChatModel, EmbeddingProvider, MemoryStore, VectorStore
from src.core.types import ToolResult
from src.tools.registry import DANGEROUS_TOOLS, SAFE_TOOLS, ToolRegistry


@pytest.fixture
def mock_memory_store():
    return create_autospec(MemoryStore, instance=True)


@pytest.fixture
def mock_vector_store():
    store = create_autospec(VectorStore, instance=True)
    store.search.return_value = []  # 默认无已有记忆，避免 autospec MagicMock 触发 merge
    return store


@pytest.fixture
def mock_embedding():
    return create_autospec(EmbeddingProvider, instance=True)


@pytest.fixture
def mock_llm():
    return create_autospec(ChatModel, instance=True)


@pytest.fixture
def registry(mock_memory_store, mock_vector_store, mock_embedding, mock_llm):
    return ToolRegistry(mock_memory_store, mock_vector_store, mock_embedding, mock_llm)


class TestToolRegistryInit:
    def test_registers_default_tools(self, registry):
        names = registry.tool_names
        assert "remember" in names
        assert "recall" in names
        assert "reflect" in names

    def test_returns_schemas_for_all_tools(self, registry):
        schemas = registry.get_schemas()
        assert len(schemas) == 3
        for s in schemas:
            assert s["type"] == "function"
            assert "name" in s["function"]

    def test_each_tool_name_matches_schema(self, registry):
        schemas = registry.get_schemas()
        schema_names = [s["function"]["name"] for s in schemas]
        for name in registry.tool_names:
            assert name in schema_names


class TestExecute:
    def test_execute_safe_tool(self, registry):
        result = registry.execute("remember", {"content": "测试"})
        assert result.success is True
        assert "已存储" in result.content

    def test_execute_dangerous_tool_blocked(self, registry):
        for tool_name in DANGEROUS_TOOLS:
            result = registry.execute(tool_name, {})
            assert result.success is False
            assert "人工确认" in result.error

    def test_execute_unknown_tool(self, registry):
        result = registry.execute("nonexistent_tool", {})
        assert result.success is False
        assert "未知工具" in result.error

    def test_safe_tools_list(self):
        assert "remember" in SAFE_TOOLS
        assert "recall" in SAFE_TOOLS
        assert "reflect" in SAFE_TOOLS

    def test_dangerous_tools_list(self):
        assert "delete_memory" in DANGEROUS_TOOLS
        assert "overwrite_memory" in DANGEROUS_TOOLS


class TestRegister:
    def test_register_custom_tool(self, registry):
        custom = MagicMock()
        custom.name = "custom_tool"
        custom.schema = {"type": "function", "function": {"name": "custom_tool"}}

        registry.register(custom)
        assert "custom_tool" in registry.tool_names

    def test_execute_registered_tool(self, registry):
        custom = MagicMock()
        custom.name = "greet"
        custom.schema = {"type": "function", "function": {"name": "greet"}}
        custom.execute.return_value = ToolResult(
            tool_name="greet", success=True, content="你好"
        )
        registry.register(custom)

        result = registry.execute("greet", {})
        assert result.success is True
        assert result.content == "你好"
        custom.execute.assert_called_once()
