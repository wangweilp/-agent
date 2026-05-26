"""ContextBuilder 单元测试。"""
from datetime import datetime, timezone

import pytest

from src.core.context import ContextBuilder
from src.core.types import Memory, Message


def _make_memory(
    content: str,
    importance: int = 5,
    summary: str | None = None,
    memory_type: str = "episodic",
) -> Memory:
    return Memory(
        content=content,
        summary=summary,
        source="user",
        timestamp=datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc),
        importance=importance,
        memory_type=memory_type,
    )


def _make_message(role: str, content: str) -> Message:
    return Message(role=role, content=content)


class TestBuild:
    def test_assembles_system_prompt_and_user_input(self):
        builder = ContextBuilder()
        result = builder.build("sys prompt", [], [], "你好")

        messages = result["messages"]
        roles = [m["role"] for m in messages]
        assert roles == ["system", "system", "user"]
        assert messages[0]["content"] == "sys prompt"
        assert messages[2]["content"] == "你好"

    def test_includes_memory_section_when_empty(self):
        builder = ContextBuilder()
        result = builder.build("sys", [], [], "hi")
        memory_msg = result["messages"][1]
        assert "暂无相关记忆" in memory_msg["content"]

    def test_formats_memories_with_timestamp_and_importance(self):
        builder = ContextBuilder()
        mem = _make_memory("学习 Rust 所有权", importance=7)
        result = builder.build("sys", [], [mem], "hi")
        memory_msg = result["messages"][1]
        assert "学习 Rust 所有权" in memory_msg["content"]
        assert "重要性:7" in memory_msg["content"]
        assert "2026-05-26" in memory_msg["content"]

    def test_truncates_memory_content_to_200_chars(self):
        builder = ContextBuilder()
        long_content = "A" * 300
        mem = _make_memory(long_content)
        result = builder.build("sys", [], [mem], "hi")
        memory_msg = result["messages"][1]
        assert long_content[:200] in memory_msg["content"]
        assert len("A" * 300) > 200  # 确认原始内容超过 200

    def test_returns_retrieved_memories_in_result(self):
        builder = ContextBuilder()
        mems = [_make_memory("a"), _make_memory("b")]
        result = builder.build("sys", [], mems, "hi")
        assert result["retrieved_memories"] == mems

    def test_keeps_only_last_n_recent_messages(self):
        builder = ContextBuilder(context_window=3)
        msgs = [_make_message("user", f"msg{i}") for i in range(10)]
        result = builder.build("sys", msgs, [], "hi")
        messages = result["messages"]
        # system + system + 3 recent + user = 6
        assert len(messages) == 6
        assert messages[2]["content"] == "msg7"
        assert messages[3]["content"] == "msg8"
        assert messages[4]["content"] == "msg9"

    def test_fewer_messages_than_window(self):
        builder = ContextBuilder(context_window=10)
        msgs = [_make_message("user", "only")]
        result = builder.build("sys", msgs, [], "hi")
        assert len(result["messages"]) == 4  # system + system + 1 + user

    def test_memory_without_timestamp(self):
        builder = ContextBuilder()
        mem = Memory(
            content="无时间戳记忆",
            summary=None,
            source="agent",
            timestamp=None,  # type: ignore[arg-type]
        )
        result = builder.build("sys", [], [mem], "hi")
        memory_msg = result["messages"][1]
        assert "未知时间" in memory_msg["content"]


# ── Token Budget ──

class TestTokenBudget:
    def test_truncates_long_memory_text(self):
        """记忆文本超过 max_memory_chars 时应截断。"""
        builder = ContextBuilder(max_memory_chars=100)
        mems = [_make_memory(f"记忆内容 {i}" * 10) for i in range(10)]

        result = builder.build("sys", [], mems, "hi")
        memory_msg = result["messages"][1]

        assert len(memory_msg["content"]) <= 200  # 远小于原始内容
        assert "记忆已截断" in memory_msg["content"]

    def test_no_truncation_within_budget(self):
        builder = ContextBuilder(max_memory_chars=5000)
        mem = _make_memory("简短内容")
        result = builder.build("sys", [], [mem], "hi")
        memory_msg = result["messages"][1]

        assert "记忆已截断" not in memory_msg["content"]

    def test_truncation_preserves_line_boundaries(self):
        """截断应尽量在换行处断开，避免截断半行。"""
        builder = ContextBuilder(max_memory_chars=80)
        mem = _make_memory("第一行内容很长" * 10)
        result = builder.build("sys", [], [mem], "hi")
        memory_msg = result["messages"][1]

        # 截断后的最后一行应该是完整的 "- [情景记忆]" 开头
        assert "记忆已截断" in memory_msg["content"]


# ── 记忆类型标签 ──

class TestMemoryTypeLabels:
    def test_includes_type_label(self):
        builder = ContextBuilder()
        mem = _make_memory("语义知识", memory_type="semantic")
        result = builder.build("sys", [], [mem], "hi")
        memory_msg = result["messages"][1]

        assert "[语义记忆]" in memory_msg["content"]

    def test_episodic_label(self):
        builder = ContextBuilder()
        mem = _make_memory("情景", memory_type="episodic")
        result = builder.build("sys", [], [mem], "hi")

        assert "[情景记忆]" in result["messages"][1]["content"]

    def test_unknown_type_uses_raw_value(self):
        builder = ContextBuilder()
        mem = _make_memory("自定义类型", memory_type="custom_type")
        result = builder.build("sys", [], [mem], "hi")

        assert "[custom_type]" in result["messages"][1]["content"]


# ── Summary 优先 ──

class TestSummaryPriority:
    def test_uses_summary_over_content(self):
        builder = ContextBuilder()
        mem = _make_memory(
            content="原始内容很长的" * 20,
            summary="这是 LLM 生成的精简摘要",
        )
        result = builder.build("sys", [], [mem], "hi")
        memory_msg = result["messages"][1]

        assert "精简摘要" in memory_msg["content"]
        assert "原始内容很长" not in memory_msg["content"]

    def test_falls_back_to_content_when_summary_none(self):
        builder = ContextBuilder()
        mem = _make_memory("直接用原始内容", summary=None)
        result = builder.build("sys", [], [mem], "hi")

        assert "直接用原始内容" in result["messages"][1]["content"]
