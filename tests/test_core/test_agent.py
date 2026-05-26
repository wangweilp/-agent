"""CognitiveAgent 单元测试。"""
import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, create_autospec

import pytest

from src.core.agent import (
    SYSTEM_PROMPT,
    TOOL_DEFINITIONS,
    CognitiveAgent,
    ContextBuilder,
    DefaultReflectionEngine,
)
from src.core.memory import ChatModel, EmbeddingProvider, MemoryStore, ReflectionEngine, VectorStore
from src.core.types import Memory, Message, ToolResult


# ── 测试辅助 ──

def _make_mock_response(content: str = "", tool_calls: list | None = None) -> Any:
    """构造 OpenAI 兼容的 mock 响应对象。"""
    response = MagicMock()
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls
    response.choices = [MagicMock()]
    response.choices[0].message = message
    return response


def _make_tool_call(name: str, arguments: dict, call_id: str = "call_1") -> Any:
    """构造 mock tool_call 对象。"""
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    return tc


def _make_memory(content: str = "test memory") -> Memory:
    return Memory(
        content=content,
        summary=None,
        source="user",
        timestamp=datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc),
    )


# ── Fixtures ──

@pytest.fixture
def mock_llm():
    return create_autospec(ChatModel, instance=True)


@pytest.fixture
def mock_memory_store():
    return create_autospec(MemoryStore, instance=True)


@pytest.fixture
def mock_vector_store():
    return create_autospec(VectorStore, instance=True)


@pytest.fixture
def mock_embedding():
    return create_autospec(EmbeddingProvider, instance=True)


@pytest.fixture
def mock_tool_executor():
    executor = MagicMock()
    executor.execute.return_value = ToolResult(
        tool_name="",
        success=True,
        content="工具执行成功",
    )
    return executor


@pytest.fixture
def agent(mock_llm, mock_memory_store, mock_vector_store, mock_embedding, mock_tool_executor):
    return CognitiveAgent(
        llm=mock_llm,
        memory_store=mock_memory_store,
        vector_store=mock_vector_store,
        embedding_provider=mock_embedding,
        tool_executor=mock_tool_executor,
    )


# ── 初始化 ──

class TestInit:
    def test_default_system_prompt(self, agent):
        assert agent._system_prompt == SYSTEM_PROMPT

    def test_custom_system_prompt(self, mock_llm, mock_memory_store, mock_vector_store, mock_embedding, mock_tool_executor):
        a = CognitiveAgent(
            llm=mock_llm,
            memory_store=mock_memory_store,
            vector_store=mock_vector_store,
            embedding_provider=mock_embedding,
            tool_executor=mock_tool_executor,
            system_prompt="自定义 prompt",
        )
        assert a._system_prompt == "自定义 prompt"

    def test_default_max_rounds(self, agent):
        assert agent._max_tool_rounds == 5

    def test_custom_context_builder(self, mock_llm, mock_memory_store, mock_vector_store, mock_embedding, mock_tool_executor):
        cb = ContextBuilder(context_window=3)
        a = CognitiveAgent(
            llm=mock_llm,
            memory_store=mock_memory_store,
            vector_store=mock_vector_store,
            embedding_provider=mock_embedding,
            tool_executor=mock_tool_executor,
            context_builder=cb,
        )
        assert a._context_builder is cb


# ── 基本对话（无工具调用）──

class TestBasicChat:
    def test_returns_llm_response(self, agent, mock_llm, mock_embedding, mock_vector_store):
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        mock_llm.chat.return_value = _make_mock_response(content="你好！有什么可以帮助你的？")

        result = agent.run("你好")

        assert result == "你好！有什么可以帮助你的？"

    def test_builds_context_correctly(self, agent, mock_llm, mock_embedding, mock_vector_store):
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        # 第一次为主对话，第二次为 reflection 检查（返回 OK）
        mock_llm.chat.side_effect = [
            _make_mock_response(content="回复"),
            _make_mock_response(content="OK"),
        ]

        agent.run("测试输入")

        messages = mock_llm.chat.call_args_list[0].kwargs["messages"]
        # 第一轮调用：system + system(memory) + user
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "测试输入"

    def test_passes_tool_definitions(self, agent, mock_llm, mock_embedding, mock_vector_store):
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        mock_llm.chat.side_effect = [
            _make_mock_response(content="回复"),
            _make_mock_response(content="OK"),
        ]

        agent.run("hi")

        first_call = mock_llm.chat.call_args_list[0].kwargs
        assert first_call["tools"] == TOOL_DEFINITIONS
        assert first_call["tool_choice"] == "auto"


# ── 工具调用 ──

class TestToolCalling:
    def test_executes_tool_and_continues_loop(self, agent, mock_llm, mock_embedding, mock_vector_store, mock_tool_executor):
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        # 第1次: tool_call → 第2次: 最终回复 → 第3次: reflection 检查
        mock_llm.chat.side_effect = [
            _make_mock_response(
                tool_calls=[_make_tool_call("remember", {"content": "用户叫小明"})],
            ),
            _make_mock_response(content="已记住！"),
            _make_mock_response(content="OK"),
        ]

        result = agent.run("我叫小明")

        assert result == "已记住！"
        mock_tool_executor.execute.assert_called_once_with(
            "remember", {"content": "用户叫小明"}
        )
        # 3 次: 主对话(tool_call) + 主对话(最终) + reflection(OK)
        assert mock_llm.chat.call_count == 3

    def test_passes_tool_result_to_next_round(self, agent, mock_llm, mock_embedding, mock_vector_store, mock_tool_executor):
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        mock_tool_executor.execute.return_value = ToolResult(
            tool_name="recall", success=True, content="找到 3 条相关记忆"
        )
        mock_llm.chat.side_effect = [
            _make_mock_response(
                tool_calls=[_make_tool_call("recall", {"query": "小明"})],
            ),
            _make_mock_response(content="根据记忆，小明喜欢编程。"),
            _make_mock_response(content="OK"),
        ]

        agent.run("小明喜欢什么？")

        # 第二轮调用的 messages 应包含 tool result
        second_call_messages = mock_llm.chat.call_args_list[1].kwargs["messages"]
        tool_messages = [m for m in second_call_messages if m["role"] == "tool"]
        assert len(tool_messages) == 1
        assert "找到 3 条相关记忆" in tool_messages[0]["content"]

    def test_multiple_tool_calls_in_one_response(self, agent, mock_llm, mock_embedding, mock_vector_store, mock_tool_executor):
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        mock_llm.chat.side_effect = [
            _make_mock_response(
                tool_calls=[
                    _make_tool_call("remember", {"content": "a"}, call_id="call_a"),
                    _make_tool_call("remember", {"content": "b"}, call_id="call_b"),
                ],
            ),
            _make_mock_response(content="已存储两条记忆"),
            _make_mock_response(content="OK"),
        ]

        result = agent.run("记住 a 和 b")

        assert result == "已存储两条记忆"
        assert mock_tool_executor.execute.call_count == 2

    def test_tool_execution_error(self, agent, mock_llm, mock_embedding, mock_vector_store, mock_tool_executor):
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        mock_tool_executor.execute.return_value = ToolResult(
            tool_name="recall", success=False, error="向量库不可用"
        )
        mock_llm.chat.side_effect = [
            _make_mock_response(
                tool_calls=[_make_tool_call("recall", {"query": "test"})],
            ),
            _make_mock_response(content="检索失败，但我尽力回答。"),
            _make_mock_response(content="OK"),
        ]

        result = agent.run("test")

        assert result == "检索失败，但我尽力回答。"
        second_call_messages = mock_llm.chat.call_args_list[1].kwargs["messages"]
        tool_msg = [m for m in second_call_messages if m["role"] == "tool"][0]
        assert "向量库不可用" in tool_msg["content"]

    def test_invalid_json_arguments(self, agent, mock_llm, mock_embedding, mock_vector_store):
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        tc = MagicMock()
        tc.id = "bad_call"
        tc.function.name = "recall"
        tc.function.arguments = "not valid json {{{"
        mock_llm.chat.side_effect = [
            _make_mock_response(tool_calls=[tc]),
            _make_mock_response(content="参数解析失败，但我继续回答。"),
            _make_mock_response(content="OK"),
        ]

        result = agent.run("test")

        assert result == "参数解析失败，但我继续回答。"


# ── Reflection 自检 ──

class TestReflection:
    def test_corrects_when_reflection_finds_issue(self, agent, mock_llm, mock_embedding, mock_vector_store):
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        mock_llm.chat.side_effect = [
            # 第1次: 直接回答（无 tool_call）
            _make_mock_response(content="答案是 42"),
            # 第2次: reflection 检查返回 CORRECTION
            _make_mock_response(content="CORRECTION: 遗漏了用户之前的上下文，应该结合记忆回答"),
            # 第3次: 修正后的回答
            _make_mock_response(content="结合你之前的记忆，答案应该是 43"),
            # 第4次: 对修正后回答的 reflection（返回 OK）
            _make_mock_response(content="OK"),
        ]

        result = agent.run("答案是什么？")

        assert "43" in result
        # 4 次: 回答 + reflection(CORRECTION) + 修正 + reflection(OK)
        assert mock_llm.chat.call_count == 4

    def test_returns_when_reflection_says_ok(self, agent, mock_llm, mock_embedding, mock_vector_store):
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        mock_llm.chat.side_effect = [
            _make_mock_response(content="今天天气不错"),
            _make_mock_response(content="OK"),
        ]

        result = agent.run("天气如何？")

        assert result == "今天天气不错"
        assert mock_llm.chat.call_count == 2

    def test_skips_reflection_on_last_round(self, agent, mock_llm, mock_embedding, mock_vector_store):
        """最后一轮不触发 reflection，直接返回。"""
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        agent._max_tool_rounds = 2
        # 第 1 轮返回 tool_call，第 2 轮（最后一轮）返回最终回答
        mock_llm.chat.side_effect = [
            _make_mock_response(
                tool_calls=[_make_tool_call("recall", {"query": "test"})],
            ),
            _make_mock_response(content="最终回答"),
        ]

        result = agent.run("test")

        assert result == "最终回答"
        # 只有 2 次调用（最后一轮不触发 reflection）
        assert mock_llm.chat.call_count == 2

    def test_reflection_failure_skips_gracefully(self, agent, mock_llm, mock_embedding, mock_vector_store):
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        # 第一次返回无 tool_call 的回复，触发 reflection
        # reflection 调用抛出异常，应跳过 reflection 直接返回
        mock_llm.chat.side_effect = [
            _make_mock_response(content="正常回答"),
            Exception("Reflection API 不可用"),
        ]

        result = agent.run("hello")

        # 应降级返回第一轮的回复
        assert result == "正常回答"

    def test_reflection_with_empty_tool_call_content(self, agent, mock_llm, mock_embedding, mock_vector_store):
        """当 LLM 返回空 content 但有 CORRECTION 时应正确处理。"""
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        mock_llm.chat.side_effect = [
            _make_mock_response(content="初步回答"),
            _make_mock_response(content="CORRECTION: 回答不够完整"),
            _make_mock_response(content="修正后的完整回答"),
        ]

        result = agent.run("问题")

        assert result == "修正后的完整回答"


# ── 超限处理 ──

class TestMaxRounds:
    def test_best_effort_when_exceeded(self, agent, mock_llm, mock_embedding, mock_vector_store, mock_tool_executor):
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        agent._max_tool_rounds = 2
        # 两轮都返回 tool_call，耗尽所有轮数
        mock_llm.chat.side_effect = [
            _make_mock_response(
                tool_calls=[_make_tool_call("remember", {"content": "a"})],
            ),
            _make_mock_response(
                tool_calls=[_make_tool_call("remember", {"content": "b"})],
            ),
            # best_effort 调用
            _make_mock_response(content="尽力了，这是我最好的回答"),
        ]

        result = agent.run("多轮工具")

        assert result == "尽力了，这是我最好的回答"

    def test_best_effort_handles_llm_failure(self, agent, mock_llm, mock_embedding, mock_vector_store):
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        agent._max_tool_rounds = 1
        mock_llm.chat.side_effect = [
            _make_mock_response(tool_calls=[_make_tool_call("recall", {"query": "x"})]),
            Exception("best_effort 也失败了"),
        ]

        result = agent.run("x")

        assert "抱歉" in result  # 降级消息


# ── 短期记忆 ──

class TestShortTermMemory:
    def test_stores_conversation_after_run(self, agent, mock_llm, mock_embedding, mock_vector_store):
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        mock_llm.chat.return_value = _make_mock_response(content="回复")

        agent.run("你好")

        assert len(agent._short_term) == 2
        assert agent._short_term[0].role == "user"
        assert agent._short_term[0].content == "你好"
        assert agent._short_term[1].role == "assistant"
        assert agent._short_term[1].content == "回复"

    def test_reset_clears_short_term(self, agent, mock_llm, mock_embedding, mock_vector_store):
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        mock_llm.chat.return_value = _make_mock_response(content="回复")

        agent.run("hello")
        assert agent.short_term_size > 0

        agent.reset()
        assert agent.short_term_size == 0

    def test_prunes_when_exceeds_20_messages(self, agent, mock_llm, mock_embedding, mock_vector_store):
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        mock_llm.chat.return_value = _make_mock_response(content="回复")

        for i in range(15):
            agent.run(f"消息{i}")

        assert agent.short_term_size <= 20


# ── 记忆检索 ──

class TestMemoryRetrieval:
    def test_retrieves_and_includes_memories(self, agent, mock_llm, mock_embedding, mock_vector_store, mock_memory_store):
        mock_embedding.encode.return_value = [0.1] * 512
        mem = _make_memory("用户喜欢 Python")
        mock_memory_store.get_by_id.return_value = mem

        from src.core.types import SearchResult
        mock_vector_store.search.return_value = [
            SearchResult(doc_id="mem_1", score=0.9, metadata={}),
        ]
        mock_llm.chat.return_value = _make_mock_response(content="你之前提到喜欢 Python！")

        result = agent.run("我喜欢什么编程语言？")

        assert "Python" in result
        # 记忆应出现在上下文中
        first_call_messages = mock_llm.chat.call_args_list[0].kwargs["messages"]
        memory_msg = first_call_messages[1]["content"]
        assert "用户喜欢 Python" in memory_msg

    def test_retrieval_failure_graceful_degradation(self, agent, mock_llm, mock_embedding):
        mock_embedding.encode.side_effect = Exception("Embedding 模型加载失败")
        mock_llm.chat.return_value = _make_mock_response(content="我没有找到相关记忆，但可以回答你的问题。")

        result = agent.run("hello")

        assert result == "我没有找到相关记忆，但可以回答你的问题。"


# ── 工具 definitions 结构验证 ──

class TestToolDefinitions:
    def test_all_tools_have_required_fields(self):
        required_tools = {"remember", "recall", "reflect"}
        names = {t["function"]["name"] for t in TOOL_DEFINITIONS}
        assert names == required_tools

    def test_tools_have_valid_schema(self):
        for tool in TOOL_DEFINITIONS:
            assert tool["type"] == "function"
            assert "name" in tool["function"]
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]
            params = tool["function"]["parameters"]
            assert params["type"] == "object"


# ── LLM 重试/退避 ──

class TestRetryBackoff:
    def test_retries_on_failure_then_succeeds(self, agent, mock_llm, mock_embedding, mock_vector_store):
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        # 前 2 次失败，第 3 次成功 + reflection OK
        mock_llm.chat.side_effect = [
            Exception("timeout"),
            Exception("timeout"),
            _make_mock_response(content="重试后成功"),
            _make_mock_response(content="OK"),
        ]

        result = agent.run("hello")

        assert result == "重试后成功"
        assert mock_llm.chat.call_count == 4  # 2 失败 + 1 成功 + 1 reflection

    def test_raises_after_max_retries(self, agent, mock_llm, mock_embedding, mock_vector_store):
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        mock_llm.chat.side_effect = Exception("持续失败")

        with pytest.raises(Exception):
            agent.run("hello")


# ── 停止条件 ──

class TestStopConditions:
    def test_stops_after_same_tool_called_3_times(self, agent, mock_llm, mock_embedding, mock_vector_store, mock_tool_executor):
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        agent._max_tool_rounds = 5
        # 3 次相同的 recall，触发停止 → LLM 收到提示后给出最终回复
        mock_llm.chat.side_effect = [
            _make_mock_response(
                tool_calls=[_make_tool_call("recall", {"query": "test"})],
            ),
            _make_mock_response(
                tool_calls=[_make_tool_call("recall", {"query": "test"})],
            ),
            _make_mock_response(
                tool_calls=[_make_tool_call("recall", {"query": "test"})],
            ),
            _make_mock_response(content="多次检索无新结果，这是我能给出的最佳回答。"),
            _make_mock_response(content="OK"),
        ]

        result = agent.run("test")

        assert "最佳回答" in result
        # 3 次 recall 执行 + 1 次最终回答 + 1 次 reflection
        assert mock_llm.chat.call_count == 5

    def test_different_tool_calls_reset_counter(self, agent, mock_llm, mock_embedding, mock_vector_store, mock_tool_executor):
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        agent._max_tool_rounds = 5
        # 不同工具调用 → 计数器应重置，不会触发停止
        mock_llm.chat.side_effect = [
            _make_mock_response(
                tool_calls=[_make_tool_call("recall", {"query": "test"})],
            ),
            _make_mock_response(
                tool_calls=[_make_tool_call("remember", {"content": "不同工具"})],
            ),
            _make_mock_response(content="正常回答"),
            _make_mock_response(content="OK"),
        ]

        result = agent.run("test")

        assert result == "正常回答"  # 未触发停止条件


# ── 重要性阈值 ──

class TestImportanceThreshold:
    def test_filters_low_importance_remember(self, agent, mock_llm, mock_embedding, mock_vector_store, mock_tool_executor):
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        agent._importance_threshold = 7
        # LLM 调用 remember（importance_override=3，低于阈值）→ 被过滤
        mock_llm.chat.side_effect = [
            _make_mock_response(
                tool_calls=[_make_tool_call("remember", {"content": "低价值信息", "importance_override": 3})],
            ),
            _make_mock_response(content="已处理"),
            _make_mock_response(content="OK"),
        ]

        agent.run("低价值内容")

        # 工具不应被执行（被阈值过滤）
        mock_tool_executor.execute.assert_not_called()

    def test_allows_high_importance_remember(self, agent, mock_llm, mock_embedding, mock_vector_store, mock_tool_executor):
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        agent._importance_threshold = 7
        mock_llm.chat.side_effect = [
            _make_mock_response(
                tool_calls=[_make_tool_call("remember", {"content": "关键信息", "importance_override": 9})],
            ),
            _make_mock_response(content="已存储"),
            _make_mock_response(content="OK"),
        ]

        agent.run("重要内容")

        mock_tool_executor.execute.assert_called_once()

    def test_no_override_allows_default_importance(self, agent, mock_llm, mock_embedding, mock_vector_store, mock_tool_executor):
        """未指定 importance_override 时，不触发阈值过滤（交由工具自身评分）。"""
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        agent._importance_threshold = 7
        mock_llm.chat.side_effect = [
            _make_mock_response(
                tool_calls=[_make_tool_call("remember", {"content": "无评分的记忆"})],
            ),
            _make_mock_response(content="已存储"),
            _make_mock_response(content="OK"),
        ]

        agent.run("某些内容")

        mock_tool_executor.execute.assert_called_once()


# ── 可插拔 Reflection Engine ──

class TestCustomReflectionEngine:
    def test_uses_custom_reflection_engine(self, mock_llm, mock_memory_store, mock_vector_store, mock_embedding, mock_tool_executor):
        """注入自定义 ReflectionEngine 应被正确调用。"""
        custom_engine = MagicMock(spec=ReflectionEngine)
        # 第一次 reflect 返回修正，第二次返回 OK
        custom_engine.reflect.side_effect = [
            (True, "自定义修正建议"),
            (False, ""),
        ]

        agent = CognitiveAgent(
            llm=mock_llm,
            memory_store=mock_memory_store,
            vector_store=mock_vector_store,
            embedding_provider=mock_embedding,
            tool_executor=mock_tool_executor,
            reflection_engine=custom_engine,
        )
        mock_embedding.encode.return_value = [0.1] * 512
        mock_vector_store.search.return_value = []
        mock_llm.chat.side_effect = [
            _make_mock_response(content="原始回答"),
            _make_mock_response(content="修正后回答"),
        ]

        agent.run("test")

        assert custom_engine.reflect.call_count == 2  # 两次回答各检查一次
        # 确认自定义引擎返回的修正建议被注入到下一轮
        second_call_messages = mock_llm.chat.call_args_list[1].kwargs["messages"]
        assert any("自定义修正建议" in str(m.get("content", "")) for m in second_call_messages)


class TestDefaultReflectionEngine:
    def test_returns_correction_when_found(self, mock_llm):
        engine = DefaultReflectionEngine()
        mock_llm.chat.return_value = _make_mock_response(
            content="CORRECTION: 需要改进的地方"
        )

        needs_fix, correction = engine.reflect("回答", "问题", mock_llm)

        assert needs_fix is True
        assert "需要改进的地方" in correction

    def test_returns_ok_when_no_issue(self, mock_llm):
        engine = DefaultReflectionEngine()
        mock_llm.chat.return_value = _make_mock_response(content="OK")

        needs_fix, correction = engine.reflect("回答", "问题", mock_llm)

        assert needs_fix is False
        assert correction == ""

    def test_handles_llm_exception(self, mock_llm):
        engine = DefaultReflectionEngine()
        mock_llm.chat.side_effect = Exception("LLM 不可用")

        needs_fix, correction = engine.reflect("回答", "问题", mock_llm)

        assert needs_fix is False  # 降级：不修正
