"""Remember 工具 — 重要性评分 + 新颖度检测，双写 ChromaDB + SQLite。

新颖度检测防止记忆污染："今天学X → 继续学X → 还在学X" 不会被全部写入。
高相似度 → 合并更新；中等相似度 → 降权存储；低相似度 → 正常写入。
"""
import logging
from datetime import datetime, timezone

from src.core.memory import EmbeddingProvider, MemoryStore, VectorStore
from src.core.types import Memory, ToolResult
from src.core.events import emit, EventType

logger = logging.getLogger(__name__)

_IMPORTANCE_KEYWORDS = [
    # 中文
    "重要", "关键", "必须", "记住", "永远", "绝对", "一定",
    "目标", "计划", "决定", "秘密", "密码", "账号",
    # English
    "important", "critical", "must", "remember", "forever", "always",
    "never forget", "goal", "plan", "decision", "secret", "password",
]

_EMOTION_WORDS = [
    # 中文
    "开心", "难过", "愤怒", "激动", "担心", "害怕", "期待",
    "焦虑", "感动", "兴奋", "喜欢", "讨厌", "爱", "恨",
    # English
    "happy", "sad", "angry", "excited", "worried", "afraid",
    "anxious", "moved", "love", "hate",
]

# 新颖度阈值（基于 cosine_similarity，越大越相似）
_NOVELTY_MERGE_THRESHOLD = 0.85    # similarity > 0.85 → 合并更新，不新建
_NOVELTY_DOWNGRADE_THRESHOLD = 0.70  # similarity > 0.70 → 降权存储
_NOVELTY_SEARCH_K = 3


class RememberTool:
    name = "remember"
    description = "存储一条新的长期记忆。当用户分享值得记住的信息时调用此工具。"
    requires_confirmation = False
    metadata = {
        "category": "memory",
        "cost": "low",
        "side_effect": True,
    }

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

        # 新颖度检测
        novelty_result = self._check_novelty(content)
        if novelty_result["action"] == "merge":
            return self._merge_memory(novelty_result, content, entities)
        elif novelty_result["action"] == "downgrade":
            importance = max(importance - 2, 1)
            logger.info(
                "remember:novelty_downgrade",
                extra={"content": content[:100], "new_importance": importance},
            )

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
            try:
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
            except Exception as ve:
                # 失败补偿：回滚 SQLite 写入，保持最终一致性
                logger.warning(
                    "remember:vector_write_failed_rolling_back",
                    extra={"memory_id": memory.id, "error": str(ve)[:200]},
                )
                self._memory_store.delete(memory.id)
                raise
            emit(
                EventType.MEMORY_CREATED,
                memory_id=memory.id,
                source=memory.source,
                importance=importance,
                entities=entities,
                memory_type=memory.memory_type,
            )
            logger.info(
                "remember:stored",
                extra={
                    "event": "memory_stored",
                    "memory_id": memory.id,
                    "importance": importance,
                    "entities": entities,
                },
            )
            return ToolResult(
                tool_name="remember",
                success=True,
                content=f"已存储记忆（重要性: {importance}/10）",
                metadata={
                    "memory_id": memory.id,
                    "importance": importance,
                    "novelty": novelty_result,
                },
            )
        except Exception as e:
            logger.error(
                "remember:failed",
                extra={"event": "remember_failed", "error_type": type(e).__name__},
            )
            logger.exception("remember:exception")
            return ToolResult(
                tool_name="remember",
                success=False,
                error=f"存储记忆失败: {e}",
            )

    # ── 新颖度检测 ──

    def _check_novelty(self, content: str) -> dict:
        """检查新内容与已有记忆的新颖度。

        Returns:
            {"action": "store"|"downgrade"|"merge", "existing_id": ..., "distance": ...}
        """
        try:
            embedding = self._embedding.encode(content)
            results = self._vector_store.search(embedding, k=_NOVELTY_SEARCH_K)
            if not results:
                return {"action": "store", "similarity": None}
            min_similarity = results[0].score
            if min_similarity > _NOVELTY_MERGE_THRESHOLD:
                return {"action": "merge", "existing_id": results[0].doc_id, "similarity": min_similarity}
            elif min_similarity > _NOVELTY_DOWNGRADE_THRESHOLD:
                return {"action": "downgrade", "similarity": min_similarity}
            return {"action": "store", "similarity": min_similarity}
        except Exception:
            logger.debug("novelty_check_failed", exc_info=True)
            return {"action": "store", "similarity": None}

    def _merge_memory(self, novelty: dict, new_content: str, entities: list[str]) -> ToolResult:
        """合并更新已有记忆，而非创建重复记忆。"""
        existing_id = novelty["existing_id"]
        existing = self._memory_store.get_by_id(existing_id)
        if existing is None:
            # 已有记忆不存在，回退到正常存储
            logger.warning(
            "remember:merge_target_missing",
            extra={"event": "merge_target_missing", "memory_id": existing_id},
        )
            return self.execute({"content": new_content, "entities": entities})

        merged_content = f"{existing.content}\n\n[更新] {new_content}"
        existing.content = merged_content
        existing.timestamp = datetime.now(timezone.utc)
        existing.entities = list(set(existing.entities + entities))
        existing.access_count += 1

        try:
            embedding = self._embedding.encode(merged_content)
            self._memory_store.store(existing)
            try:
                self._vector_store.store(
                    doc_id=existing.id,
                    embedding=embedding,
                    metadata={
                        "source": existing.source,
                        "importance": existing.importance,
                        "memory_type": existing.memory_type,
                        "entities": ",".join(existing.entities),
                    },
                )
            except Exception as ve:
                logger.warning(
                    "remember:merge_vector_write_failed",
                    extra={"memory_id": existing.id, "error": str(ve)[:200]},
                )
                # 向量写入失败不影响已有记忆的合并结果
            emit(
                EventType.MEMORY_MERGED,
                memory_id=existing.id,
                existing_id=existing_id,
                similarity=novelty["similarity"],
                source=existing.source,
            )
            logger.info(
                "remember:merged",
                extra={"existing_id": existing_id, "similarity": novelty["similarity"]},
            )
            return ToolResult(
                tool_name="remember",
                success=True,
                content=f"已合并更新已有记忆（相似度: {novelty['similarity']:.3f}），无需重复存储。",
                metadata={
                    "memory_id": existing.id,
                    "importance": existing.importance,
                    "merged": True,
                    "existing_id": existing_id,
                },
            )
        except Exception as e:
            logger.error(
                "remember:merge_failed",
                extra={"event": "remember_merge_failed", "existing_id": novelty.get("existing_id", ""), "error_type": type(e).__name__},
            )
            logger.exception("remember:merge_exception")
            return ToolResult(
                tool_name="remember",
                success=False,
                error=f"合并记忆失败: {e}",
            )

    # ── 重要性计算 ──

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
