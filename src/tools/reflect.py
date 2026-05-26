"""Reflect 工具 — 反思近期对话，发现矛盾、联系或知识盲点。

防自激机制：
- source="reflect" 的记忆不参与后续 reflect（避免反思链爆炸）
- 最近 20 条记忆中若有 >=3 条 reflect 记忆，拒绝本次反思
"""
import logging
from datetime import datetime, timezone

from src.core.memory import ChatModel, EmbeddingProvider, MemoryStore, VectorStore
from src.core.types import Memory, ToolResult

logger = logging.getLogger(__name__)

_MAX_REFLECTION_IN_RECENT = 3  # 近期记忆中 reflect 占比超过此值则拒绝
_RECENT_CHECK_WINDOW = 20

_REFLECT_PROMPT = """你是一个知识管理反思助手。请检查以下内容是否存在矛盾、遗漏或可建立的新联系。

## 反思主题
{topic}

## 相关记忆
{memories}

## 分析要求
1. 是否存在事实矛盾？不同时间的记忆是否有冲突？
2. 是否有重要信息被遗漏？
3. 是否可以建立新的知识联系或洞察？
4. 是否存在需要进一步澄清的模糊点？

如果发现有意义的问题或联系，请用简洁的语言描述你的发现。
如果没有值得记录的内容，请回复 "NOTHING_TO_RECORD"。
"""


class ReflectTool:
    name = "reflect"
    description = "反思近期对话，主动发现矛盾、联系或知识盲点。"
    requires_confirmation = False
    metadata = {
        "category": "cognition",
        "cost": "high",
        "side_effect": True,
    }

    def __init__(
        self,
        memory_store: MemoryStore,
        vector_store: VectorStore,
        embedding_provider: EmbeddingProvider,
        llm: ChatModel,
    ) -> None:
        self._memory_store = memory_store
        self._vector_store = vector_store
        self._embedding = embedding_provider
        self._llm = llm

    @property
    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "reflect",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "要反思的主题",
                        },
                        "recent_n": {
                            "type": "integer",
                            "default": 10,
                            "description": "检查最近 N 条记忆",
                        },
                    },
                    "required": ["topic"],
                },
            },
        }

    def execute(self, arguments: dict) -> ToolResult:
        topic = arguments.get("topic", "")
        recent_n = arguments.get("recent_n", 10)

        if not topic.strip():
            return ToolResult(tool_name="reflect", success=False, error="反思主题不能为空")

        # 防自激：检查近期 reflect 密度
        if self._too_many_reflections():
            return ToolResult(
                tool_name="reflect",
                success=True,
                content="近期已有足够多的反思，暂不新增，避免反思自激。",
                metadata={"checked": 0, "skipped": "anti_loop"},
            )

        try:
            embedding = self._embedding.encode(topic)
            semantic_results = self._vector_store.search(embedding, k=5)
            related_memories: list[Memory] = []
            for r in semantic_results:
                mem = self._memory_store.get_by_id(r.doc_id)
                # 防自激：source=reflect 的记忆不参与反思
                if mem and mem.source != "reflect":
                    related_memories.append(mem)

            recent = self._memory_store.get_recent(recent_n)
            seen_ids = {m.id for m in related_memories}
            for m in recent:
                # 同样跳过 reflect 来源
                if m.id not in seen_ids and m.source != "reflect":
                    related_memories.append(m)
                    seen_ids.add(m.id)

            if not related_memories:
                return ToolResult(
                    tool_name="reflect",
                    success=True,
                    content="没有足够的相关记忆来反思。",
                    metadata={"checked": 0},
                )

            memory_text = self._format_for_prompt(related_memories[:recent_n])
            prompt = _REFLECT_PROMPT.format(topic=topic, memories=memory_text)

            response = self._llm.chat(
                messages=[{"role": "user", "content": prompt}],
                tools=None,
                tool_choice=None,
            )
            finding = response.choices[0].message.content or ""

            if "NOTHING_TO_RECORD" in finding.upper():
                return ToolResult(
                    tool_name="reflect",
                    success=True,
                    content="反思完成，未发现需要记录的新见解。",
                    metadata={"checked": len(related_memories)},
                )

            reflect_memory = Memory(
                content=f"反思主题: {topic}\n\n发现: {finding}",
                summary=finding[:200],
                source="reflect",
                timestamp=datetime.now(timezone.utc),
                importance=7,
                entities=[topic],
                memory_type="reflect",
            )

            self._memory_store.store(reflect_memory)
            ref_embedding = self._embedding.encode(reflect_memory.content)
            self._vector_store.store(
                doc_id=reflect_memory.id,
                embedding=ref_embedding,
                metadata={
                    "source": "reflect",
                    "importance": 7,
                    "memory_type": "reflect",
                    "topic": topic,
                },
            )

            logger.info(
                "reflect:insight_stored",
                extra={"topic": topic, "finding": finding[:200]},
            )
            return ToolResult(
                tool_name="reflect",
                success=True,
                content=f"反思完成，发现以下洞察:\n{finding}",
                metadata={
                    "checked": len(related_memories),
                    "insight_stored": True,
                    "memory_id": reflect_memory.id,
                },
            )
        except Exception as e:
            logger.error(
                "reflect:failed",
                extra={"event": "reflect_failed", "error_type": type(e).__name__},
            )
            logger.exception("reflect:exception")
            return ToolResult(
                tool_name="reflect",
                success=False,
                error=f"反思失败: {e}",
            )

    def _too_many_reflections(self) -> bool:
        """检查近期是否已有过多 reflect 记忆。"""
        try:
            recent = self._memory_store.get_recent(_RECENT_CHECK_WINDOW)
            reflect_count = sum(1 for m in recent if m.source == "reflect")
            if reflect_count >= _MAX_REFLECTION_IN_RECENT:
                logger.info(
                    "reflect:anti_loop_triggered",
                    extra={"reflect_count": reflect_count, "window": _RECENT_CHECK_WINDOW},
                )
                return True
        except Exception:
            logger.debug("reflect:anti_loop_check_failed", exc_info=True)
        return False

    @staticmethod
    def _format_for_prompt(memories: list[Memory]) -> str:
        lines = []
        for m in memories:
            ts = m.timestamp.strftime("%Y-%m-%d %H:%M")
            text = m.summary or m.content[:200]
            lines.append(f"- [{ts}] (重要性:{m.importance}) {text}")
        return "\n".join(lines)
