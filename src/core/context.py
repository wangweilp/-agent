"""Context Builder — 动态组装 Agent 上下文，非全量聊天历史。"""
from src.core.constants import MAX_CONTEXT_CHARS, MEMORY_TYPE_LABELS
from src.core.types import Memory, Message


class ContextBuilder:
    """动态组装 LLM 上下文。

    三条铁律：
    1. 只保留最近 N 轮对话（由 context_window 控制，非硬编码）
    2. 记忆文本有硬 token 预算（MAX_CONTEXT_CHARS）
    3. 优先使用 summary，避免长 content 污染上下文
    """

    def __init__(
        self,
        context_window: int = 6,
        max_memory_chars: int = MAX_CONTEXT_CHARS,
    ) -> None:
        self._context_window = context_window
        self._max_memory_chars = max_memory_chars

    def build(
        self,
        system_prompt: str,
        recent_messages: list[Message],
        long_term_memories: list[Memory],
        user_input: str,
    ) -> dict:
        """组装上下文消息列表。

        Returns:
            {"messages": [...], "retrieved_memories": [...]}
        """
        memory_text = self._format_memories(long_term_memories)
        # 硬 token 预算截断
        memory_text = self._apply_token_budget(memory_text)

        return {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "system", "content": f"## 相关长期记忆\n{memory_text}"},
                *[
                    {"role": m.role, "content": m.content}
                    for m in recent_messages[-self._context_window:]
                ],
                {"role": "user", "content": user_input},
            ],
            "retrieved_memories": long_term_memories,
        }

    # ── 记忆格式化 ──

    def _format_memories(self, memories: list[Memory]) -> str:
        """格式化记忆列表，包含类型标签、时间戳、重要性。

        优先使用 summary，summary 为空时才截取 content。
        """
        if not memories:
            return "暂无相关记忆"

        lines: list[str] = []
        for m in memories:
            type_label = MEMORY_TYPE_LABELS.get(m.memory_type, m.memory_type)
            ts = m.timestamp.strftime("%Y-%m-%d %H:%M") if m.timestamp else "未知时间"
            text = m.summary or m.content[:200]
            lines.append(f"- [{type_label}] {ts} (重要性:{m.importance}) {text}")

        return "\n".join(lines)

    def _apply_token_budget(self, memory_text: str) -> str:
        """硬截断记忆文本，防止 token 爆炸。

        简单按字符数控制——不做精确 tokenize，但能在 99% 场景下防住溢出。
        """
        if len(memory_text) <= self._max_memory_chars:
            return memory_text
        # 找到截断点并添加省略标记
        truncated = memory_text[: self._max_memory_chars]
        last_newline = truncated.rfind("\n")
        if last_newline > self._max_memory_chars * 0.8:
            truncated = truncated[:last_newline]
        return truncated + "\n... (记忆已截断，优先展示最相关内容)"
