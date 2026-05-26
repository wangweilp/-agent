"""DeepSeekAdapter 单元测试。"""
import pytest
from unittest.mock import MagicMock

from src.adapters.config import Settings
from src.adapters.llm import DeepSeekAdapter


@pytest.fixture
def settings():
    return Settings(
        deepseek_api_key="sk-test-key",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-chat",
    )


class TestDeepSeekAdapterInit:
    def test_creates_openai_client(self, settings):
        adapter = DeepSeekAdapter(settings)
        assert adapter._model == "deepseek-chat"
        assert adapter._client is not None

    def test_context_manager(self, settings):
        with DeepSeekAdapter(settings) as adapter:
            assert adapter._client is not None


class TestChat:
    def test_passes_messages_and_model(self, settings):
        adapter = DeepSeekAdapter(settings)
        adapter._client = MagicMock()
        mock_create = MagicMock()
        adapter._client.chat.completions.create = mock_create

        messages = [{"role": "user", "content": "你好"}]
        adapter.chat(messages)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["model"] == "deepseek-chat"
        assert call_kwargs["messages"] == messages
        assert call_kwargs["stream"] is False

    def test_passes_tools_and_tool_choice(self, settings):
        adapter = DeepSeekAdapter(settings)
        adapter._client = MagicMock()
        mock_create = MagicMock()
        adapter._client.chat.completions.create = mock_create

        tools = [{"type": "function", "function": {"name": "search"}}]
        adapter.chat(
            [{"role": "user", "content": "搜索"}],
            tools=tools,
            tool_choice="auto",
        )

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["tools"] == tools
        assert call_kwargs["tool_choice"] == "auto"

    def test_stream_mode_returns_raw_stream(self, settings):
        adapter = DeepSeekAdapter(settings)
        adapter._client = MagicMock()
        mock_stream = MagicMock()
        adapter._client.chat.completions.create.return_value = mock_stream

        result = adapter.chat(
            [{"role": "user", "content": "你好"}],
            stream=True,
        )

        call_kwargs = adapter._client.chat.completions.create.call_args.kwargs
        assert call_kwargs["stream"] is True
        assert result is mock_stream

    def test_passes_extra_kwargs(self, settings):
        adapter = DeepSeekAdapter(settings)
        adapter._client = MagicMock()
        mock_create = MagicMock()
        adapter._client.chat.completions.create = mock_create

        adapter.chat(
            [{"role": "user", "content": "你好"}],
            temperature=0.3,
            max_tokens=100,
        )

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["temperature"] == 0.3
        assert call_kwargs["max_tokens"] == 100


class TestProtocolCompliance:
    def test_is_chat_model(self, settings):
        from src.core.memory import ChatModel
        adapter = DeepSeekAdapter(settings)
        assert isinstance(adapter, ChatModel)
