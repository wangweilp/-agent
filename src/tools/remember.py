"""Remember 工具 — 计算重要性评分，双写 ChromaDB + SQLite。"""
import logging
from datetime import datetime, timezone

from src.core.memory import EmbeddingProvider, MemoryStore, VectorStore
from src.core.types import Memory, ToolResult

logger = logging.getLogger(__name__)

_IMPORTANCE_KEYWORDS = [
    "重要", "关键", "必须", "记住", "永远", "绝对", "一定",
    "目标", "计划", "决定", "秘密", "密码", "账号",
]

_EMOTION_WORDS = [
    "开心", "难过", "愤怒", "激动", "担心", "害怕", "期待",
    "焦虑", "感动", "兴奋", "喜欢", "讨厌", "爱", "恨",
]


class RememberTool:
    name = "remember"
    description = "存储一条新的长期记忆。当用户分享值得记住的信息时调用此工具。"
    requires_confirmation = False

    def __init__(
        self,
        memory_store: MemoryStore,
        vector_store: VectorStore,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self._memory_store = memory_store
        self._vector_store = vector_store
        self._embedding = embedding_provider

    @property
    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "remember",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "要存储的记忆内容，应包含完整上下文",
                        },
                        "entities": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "记忆涉及的关键实体名称列表",
                        },
                        "importance_override": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10,
                            "description": "手动指定重要性评分，不填则自动计算",
                        },
                    },
                    "required": ["content"],
                },
            },
        }

    def execute(self, arguments: dict) -> ToolResult:
        content = arguments.get("content", "")
        if not content.strip():
            return ToolResult(
                tool_name="remember",
                success=False,
                error="记忆内容不能为空",
            )

        entities = arguments.get("entities", [])
        raw_importance = arguments.get("importance_override")
        if raw_importance is not None:
            importance = min(max(raw_importance, 1), 10)
        else:
            importance = self._calculate_importance(content, entities)

        memory = Memory(
            content=content,
            summary=None,
            source="user",
            timestamp=datetime.now(timezone.utc),
            importance=importance,
            entities=entities,
            memory_type="episodic",
        )

        try:
            embedding = self._embedding.encode(content)
            self._memory_store.store(memory)
            self._vector_store.store(
                doc_id=memory.id,
                embedding=embedding,
                metadata={
                    "source": memory.source,
                    "importance": memory.importance,
                    "memory_type": memory.memory_type,
                    "entities": ",".join(entities),
                },
            )
            logger.info(
                "remember:stored",
                extra={"id": memory.id, "importance": importance, "entities": entities},
            )
            return ToolResult(
                tool_name="remember",
                success=True,
                content=f"已存储记忆（重要性: {importance}/10）",
                metadata={"memory_id": memory.id, "importance": importance},
            )
        except Exception as e:
            logger.error("remember:failed", extra={"error": str(e)})
            return ToolResult(
                tool_name="remember",
                success=False,
                error=f"存储记忆失败: {e}",
            )

    @staticmethod
    def _calculate_importance(content: str, entities: list[str]) -> int:
        score = 5
        score += min(len(entities), 3)
        for kw in _IMPORTANCE_KEYWORDS:
            if kw in content:
                score += 1
        for ew in _EMOTION_WORDS:
            if ew in content:
                score += 1
        return min(score, 10)
