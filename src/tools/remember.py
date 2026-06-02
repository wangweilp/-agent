"""Remember 工具 — 重要性评分 + 新颖度检测，双写 ChromaDB + SQLite。

新颖度检测防止记忆污染："今天学X → 继续学X → 还在学X" 不会被全部写入。
高相似度 → 合并更新；中等相似度 → 降权存储；低相似度 → 正常写入。

v2 重构（2026-06）：
    - 统一语义：全程使用 similarity（0.0~1.0，越高越相似），消除 score/distance 混用
    - 一次 embedding：normal path 只 encode 一次，_check_novelty 复用
    - 消除递归：_merge_memory 失败回退到 _store_new_memory()，不再调 execute()
    - 显式阈值：>= 0.85 merge, >= 0.70 downgrade, < 0.70 store
    - 结构化日志：每条 novelty 决策记录 similarity + action + memory_id
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from src.core.events import emit, EventType
from src.core.memory import EmbeddingProvider, MemoryStore, VectorStore
from src.core.types import Memory, ToolResult

logger = logging.getLogger(__name__)

# ── 重要性关键词 ──

_IMPORTANCE_KEYWORDS = [
    "重要", "关键", "必须", "记住", "永远", "绝对", "一定",
    "目标", "计划", "决定", "秘密", "密码", "账号",
    "important", "critical", "must", "remember", "forever", "always",
    "never forget", "goal", "plan", "decision", "secret", "password",
]

_EMOTION_WORDS = [
    "开心", "难过", "愤怒", "激动", "担心", "害怕", "期待",
    "焦虑", "感动", "兴奋", "喜欢", "讨厌", "爱", "恨",
    "happy", "sad", "angry", "excited", "worried", "afraid",
    "anxious", "moved", "love", "hate",
]

# ── 新颖度阈值（基于 cosine_similarity，0.0~1.0，越高越相似）──

# similarity >= 此值 → 与已有记忆合并
DEFAULT_MERGE_THRESHOLD = 0.85
# merge > similarity >= 此值 → 降权写入
DEFAULT_DOWNGRADE_THRESHOLD = 0.70
# 向量搜索返回的最大候选数
NOVELTY_SEARCH_K = 3


# ── NoveltyResult ──

@dataclass
class NoveltyResult:
    """新颖度检测结果，action 决定后续处理路径。

    统一语义：所有 similarity 字段表示 cosine_similarity（0.0~1.0）。
    ChromaDB 底层返回的 distance 已在上游 VectorStore.search() 中
    转换为 similarity（即 score 字段即为 similarity）。
    """
    action: Literal["store", "downgrade", "merge"]
    top_similarity: float | None         # 最近邻的 similarity，无结果时为 None
    existing_id: str | None = None       # merge 目标 memory_id


# ── RememberTool ──

class RememberTool:
    """记忆存储工具。

    新颖度检测分三档（阈值可在构造时覆盖）：
        similarity >= merge_threshold        → 合并更新已有记忆
        merge_threshold > similarity >= downgrade_threshold → 降权 2 写入
        similarity < downgrade_threshold     → 正常写入

    embedding 只计算一次：_check_novelty 复用 execute 中已计算的向量。
    """

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
        *,
        merge_threshold: float = DEFAULT_MERGE_THRESHOLD,
        downgrade_threshold: float = DEFAULT_DOWNGRADE_THRESHOLD,
    ) -> None:
        self._memory_store = memory_store
        self._vector_store = vector_store
        self._embedding = embedding_provider
        self._merge_threshold = merge_threshold
        self._downgrade_threshold = downgrade_threshold

    # ── Schema ──

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

    # ── 主入口 ──

    def execute(self, arguments: dict) -> ToolResult:
        content = arguments.get("content", "")
        if not content.strip():
            return ToolResult(
                tool_name="remember",
                success=False,
                error="记忆内容不能为空",
                user_message="记忆内容不能为空。",
            )

        entities = arguments.get("entities", [])
        raw_importance = arguments.get("importance_override")
        if raw_importance is not None:
            importance = min(max(raw_importance, 1), 10)
        else:
            importance = self._calculate_importance(content, entities)

        # ★ 一次 embedding — 后续 _check_novelty + _store_new_memory 共用
        try:
            embedding = self._embedding.encode(content)
        except Exception:
            logger.exception("remember:embedding_failed")
            return ToolResult(
                tool_name="remember",
                success=False,
                error="embedding 计算失败",
                user_message="这部分暂时没有保存成功。",
            )

        # 新颖度检测
        novelty = self._check_novelty(embedding)

        # 路径分发 — 无递归
        if novelty.action == "merge":
            return self._merge_memory(
                novelty=novelty,
                new_content=content,
                entities=entities,
                new_embedding=embedding,  # 用于回退时跳过二次 encode
            )
        elif novelty.action == "downgrade":
            importance = max(importance - 2, 1)
            logger.info(
                "novelty_downgrade",
                extra={
                    "similarity": novelty.top_similarity,
                    "new_importance": importance,
                    "content_preview": content[:80],
                },
            )

        return self._store_new_memory(
            content=content,
            entities=entities,
            importance=importance,
            embedding=embedding,
            novelty=novelty,
        )

    # ── 新颖度检测 ──

    def _check_novelty(self, embedding: list[float]) -> NoveltyResult:
        """基于余弦相似度判定新内容的新颖度。

        Args:
            embedding: 已在 execute() 中计算好的向量，避免二次 encode。

        Returns:
            NoveltyResult，action ∈ {store, downgrade, merge}。

        阈值语义（统一用 similarity，越大越相似）：
            similarity >= merge_threshold       → merge
            merge_threshold > similarity >= downgrade_threshold → downgrade
            similarity < downgrade_threshold    → store
        """
        try:
            results = self._vector_store.search(embedding, k=NOVELTY_SEARCH_K)
        except Exception:
            logger.debug("novelty_vector_search_failed", exc_info=True)
            return NoveltyResult(action="store", top_similarity=None)

        if not results:
            return NoveltyResult(action="store", top_similarity=None)

        # 统一语义：results[0].score 即为 cosine_similarity
        top_similarity = float(results[0].score)

        if top_similarity >= self._merge_threshold:
            action: Literal["store", "downgrade", "merge"] = "merge"
            existing_id = results[0].doc_id
        elif top_similarity >= self._downgrade_threshold:
            action = "downgrade"
            existing_id = None
        else:
            action = "store"
            existing_id = None

        logger.info(
            "novelty_detected",
            extra={
                "similarity": round(top_similarity, 4),
                "action": action,
                "existing_id": existing_id or "",
                "threshold_merge": self._merge_threshold,
                "threshold_downgrade": self._downgrade_threshold,
            },
        )

        return NoveltyResult(
            action=action,
            top_similarity=round(top_similarity, 4),
            existing_id=existing_id,
        )

    # ── 路径：合并已有记忆 ──

    def _merge_memory(
        self,
        novelty: NoveltyResult,
        new_content: str,
        entities: list[str],
        new_embedding: list[float],
    ) -> ToolResult:
        """合并到已有记忆。失败或目标不存在时回退到 _store_new_memory。"""
        existing_id = novelty.existing_id
        if not existing_id:
            # 防御：不应到达，但安全回退
            return self._store_new_memory(
                content=new_content,
                entities=entities,
                importance=5,
                embedding=new_embedding,
                novelty=novelty,
            )

        existing = self._memory_store.get_by_id(existing_id)
        if existing is None:
            logger.warning(
                "novelty_merge_target_gone",
                extra={"missing_id": existing_id, "similarity": novelty.top_similarity},
            )
            # ★ 回退到正常存储，不复用 embedding（内容不同）
            return self._store_new_memory(
                content=new_content,
                entities=entities,
                importance=5,
                embedding=new_embedding,
                novelty=novelty,
            )

        merged_content = f"{existing.content}\n\n[更新] {new_content}"
        existing.content = merged_content
        existing.timestamp = datetime.now(timezone.utc)
        existing.entities = list(set(existing.entities + entities))
        existing.access_count += 1

        # 合并后的内容需要新的 embedding（内容已变，无法复用）
        try:
            merged_embedding = self._embedding.encode(merged_content)
        except Exception:
            logger.exception("remember:merge_embedding_failed")
            return ToolResult(
                tool_name="remember",
                success=False,
                error="embedding 计算失败",
                user_message="这部分暂时没有保存成功。",
            )

        try:
            self._memory_store.store(existing)
            try:
                self._vector_store.store(
                    doc_id=existing.id,
                    embedding=merged_embedding,
                    metadata={
                        "source": existing.source,
                        "importance": existing.importance,
                        "memory_type": existing.memory_type,
                        "entities": ",".join(existing.entities),
                    },
                )
            except Exception as ve:
                logger.warning(
                    "remember:merge_vector_failed",
                    extra={"memory_id": existing.id, "error": str(ve)[:200]},
                )
                # 向量写入失败不影响 SQLite 已生效的合并

            emit(
                EventType.MEMORY_MERGED,
                memory_id=existing.id,
                existing_id=existing_id,
                similarity=novelty.top_similarity,
                source=existing.source,
            )
            logger.info(
                "remember:merged",
                extra={
                    "existing_id": existing_id,
                    "similarity": novelty.top_similarity,
                    "merged_content_len": len(merged_content),
                },
            )
            return ToolResult(
                tool_name="remember",
                success=True,
                content=f"已合并更新已有记忆（相似度: {novelty.top_similarity:.3f}），无需重复存储。",
                user_message="已更新已有记忆。",
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
                extra={
                    "event": "remember_merge_failed",
                    "existing_id": existing_id,
                    "error_type": type(e).__name__,
                    "detail": str(e)[:200],
                },
            )
            return ToolResult(
                tool_name="remember",
                success=False,
                error=str(e),
                user_message="这部分暂时没有保存成功。",
            )

    # ── 路径：正常存储 ──

    def _store_new_memory(
        self,
        content: str,
        entities: list[str],
        importance: int,
        embedding: list[float],
        novelty: NoveltyResult | None = None,
        *,
        memory_type: str = "episodic",
        source: str = "user",
    ) -> ToolResult:
        """创建新记忆并双写 ChromaDB + SQLite。

        Args:
            embedding: 已在 execute() 中计算好，避免二次 encode。
            novelty: 可选，用于 metadata 透传。
        """
        memory = Memory(
            content=content,
            summary=None,
            source=source,
            timestamp=datetime.now(timezone.utc),
            importance=importance,
            entities=entities,
            memory_type=memory_type,
        )

        try:
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
                # 失败补偿：回滚 SQLite 写入
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
                    "similarity": novelty.top_similarity if novelty else None,
                },
            )
            return ToolResult(
                tool_name="remember",
                success=True,
                content=f"已存储记忆（重要性: {importance}/10）",
                user_message="已接受处理。",
                metadata={
                    "memory_id": memory.id,
                    "importance": importance,
                    "novelty": (
                        {"action": novelty.action, "similarity": novelty.top_similarity}
                        if novelty else None
                    ),
                },
            )
        except Exception as e:
            logger.error(
                "remember:failed",
                extra={
                    "event": "remember_failed",
                    "error_type": type(e).__name__,
                    "detail": str(e)[:200],
                },
            )
            return ToolResult(
                tool_name="remember",
                success=False,
                error=str(e),
                user_message="这部分暂时没有保存成功。",
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
