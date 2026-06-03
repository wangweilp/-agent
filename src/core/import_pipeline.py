"""Import Memory Pipeline — 导入内容 → 五层记忆的全流程管道。

Import → Chunk Reception → Embedding → Concept Extraction → Memory Construction
       → MemoryWriteWorker.enqueue() → Lifecycle → Consolidation

复用已有模块：
    - MemoryWriteWorker / MemoryWriteTask — 异步写入
    - MemoryLifecycleManager — 归档/合并规则
    - DefaultMemoryConsolidator — 三阶段巩固
    - Memory / EmbeddingProvider / MemoryStore / VectorStore / ChatModel — 核心协议
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.core.consolidation import DefaultMemoryConsolidator
from src.core.memory import ChatModel, EmbeddingProvider, MemoryStore, VectorStore
from src.core.memory_lifecycle import MemoryLifecycleManager
from src.core.memory_queue import MemoryWriteTask, MemoryWriteWorker
from src.core.types import Memory

logger = logging.getLogger(__name__)

# ── Concept extraction prompt ──

_CONCEPT_PROMPT = """你是一个知识提取助手。从以下文本块中提取关键实体和概念。

文本：
{combined}

请提取两类信息：
1. 实体 — 人名、组织、地点、产品、技术术语、专有名词
2. 关键概念 — 主题、思想、模式、框架名称

只返回名称，每行一个，不要编号，不要解释。最多返回 30 个。
示例输出格式：
人工智能
机器学习
神经网络
OpenAI"""


# ── 结果数据结构 ──


@dataclass
class ImportPipelineResult:
    """导入管道的完整结果。

    属性：
        source: 导入来源（文件路径或 URL）
        title: 导入标题
        chunks_count: 输入的分块数量
        memories_created: 创建的记忆总数（5 层合计）
        tasks_enqueued: 入队的 MemoryWriteTask 数量
        entities_found: LLM 提取的实体列表
        processing_time_ms: 总耗时（毫秒）
        status: "completed" | "partial" | "failed"
        error: 失败时的错误信息
    """
    source: str
    title: str
    chunks_count: int
    memories_created: int
    tasks_enqueued: int
    entities_found: list[str]
    processing_time_ms: int
    status: str  # "completed" | "partial" | "failed"
    error: str | None = None


# ── 管道实现 ──


class ImportMemoryPipeline:
    """导入内容 → 五层记忆的全流程管道。

    流程：
        1. Chunk Reception    — 接收 parser 输出的 chunk 列表
        2. Embedding Generation — 批量 embedding 所有 chunk
        3. Concept Extraction  — LLM 提取实体和关键概念
        4. Memory Construction — 为每个 chunk 构建 5 层 Memory 对象
        5. MemoryWriteWorker.enqueue() — 异步写入队列
        6. Lifecycle           — 触发归档检查
        7. Consolidation       — 触发三阶段巩固

    不绕过任何已有模块：
        - 写入走 MemoryWriteWorker.enqueue(MemoryWriteTask(...))（与 upload.py 一致）
        - 归档走 lifecycle_manager.archive_old_memories()
        - 巩固走 consolidator.consolidate(memories)
    """

    def __init__(
        self,
        memory_store: MemoryStore,
        vector_store: VectorStore,
        embedding_provider: EmbeddingProvider,
        memory_writer: MemoryWriteWorker,
        lifecycle_manager: MemoryLifecycleManager,
        consolidator: DefaultMemoryConsolidator,
        llm: ChatModel,
    ) -> None:
        self._memory_store = memory_store
        self._vector_store = vector_store
        self._embedding = embedding_provider
        self._writer = memory_writer
        self._lifecycle = lifecycle_manager
        self._consolidator = consolidator
        self._llm = llm

    # ── 公共 API ──

    def process(
        self,
        chunks: list[dict],
        source: str,
        title: str = "",
        tags: list[str] | None = None,
    ) -> ImportPipelineResult:
        """处理解析后的 chunk 列表，走完五层记忆管道。

        Args:
            chunks: parser 输出的 chunk 列表，每个 dict 应有 "content" 或 "text" 字段
            source: 导入来源（文件路径或 URL）
            title: 可读标题
            tags: 标签列表，附加到 semantic 记忆

        Returns:
            ImportPipelineResult，含完整统计。
        """
        t0 = time.monotonic()
        _tags = tags or []

        # ── Handle empty ──
        if not chunks:
            return ImportPipelineResult(
                source=source,
                title=title,
                chunks_count=0,
                memories_created=0,
                tasks_enqueued=0,
                entities_found=[],
                processing_time_ms=int((time.monotonic() - t0) * 1000),
                status="completed",
            )

        partial_failures: list[str] = []

        # ── Phase 1: Chunk Reception — 提取内容文本 ──
        chunk_texts: list[str] = []
        for c in chunks:
            text = (c.get("content") or c.get("text") or "").strip()
            chunk_texts.append(text)

        # ── Phase 2: Embedding Generation — 批量 embedding ──
        embeddings: list[list[float]] = []
        for text in chunk_texts:
            if text:
                try:
                    emb = self._embedding.encode(text)
                except Exception:
                    logger.debug("import_embedding_failed", extra={"text_len": len(text)}, exc_info=True)
                    emb = []
                    partial_failures.append(f"embedding failed for chunk #{len(embeddings)}")
            else:
                emb = []
            embeddings.append(emb)

        # ── Phase 3: Concept Extraction — LLM 提取实体 ──
        all_entities = _extract_concepts(self._llm, chunk_texts)

        # ── Phase 4: Memory Construction — 构建 5 层 Memory ──
        now = datetime.now(timezone.utc)
        all_memories: list[Memory] = []

        for i, chunk in enumerate(chunks):
            text = chunk_texts[i]
            if not text:
                continue

            mems = _build_chunk_memories(
                chunk=chunk,
                content=text,
                index=i,
                total=len(chunks),
                source=source,
                title=title,
                tags=_tags,
                entities=all_entities,
                now=now,
            )
            all_memories.extend(mems)

        # ── Phase 5: MemoryWriteWorker.enqueue() — 异步入队 ──
        tasks_enqueued = 0
        for mem in all_memories:
            self._writer.enqueue(MemoryWriteTask(
                arguments={
                    "content": mem.content,
                    "entities": mem.entities,
                    "importance_override": mem.importance,
                },
                call_id=f"import:{source}",
            ))
            tasks_enqueued += 1

        # ── Phase 6: Lifecycle — 归档旧记忆 ──
        try:
            archived_count = self._lifecycle.archive_old_memories()
            logger.info("import_pipeline_lifecycle_done", extra={"archived": archived_count})
        except Exception:
            logger.debug("import_pipeline_lifecycle_failed", exc_info=True)
            partial_failures.append("lifecycle archive failed")

        # ── Phase 7: Consolidation — 三阶段巩固 ──
        try:
            self._consolidator.consolidate(all_memories)
        except Exception:
            logger.debug("import_pipeline_consolidation_failed", exc_info=True)
            partial_failures.append("consolidation failed")

        # ── Result ──
        processing_ms = int((time.monotonic() - t0) * 1000)

        if partial_failures:
            return ImportPipelineResult(
                source=source,
                title=title,
                chunks_count=len(chunks),
                memories_created=len(all_memories),
                tasks_enqueued=tasks_enqueued,
                entities_found=all_entities,
                processing_time_ms=processing_ms,
                status="partial",
                error="; ".join(partial_failures),
            )

        return ImportPipelineResult(
            source=source,
            title=title,
            chunks_count=len(chunks),
            memories_created=len(all_memories),
            tasks_enqueued=tasks_enqueued,
            entities_found=all_entities,
            processing_time_ms=processing_ms,
            status="completed",
        )


# ── 辅函数 ──


def _extract_concepts(llm: ChatModel, chunk_texts: list[str]) -> list[str]:
    """使用 LLM 从多段文本中提取实体和关键概念。

    最多送前 12 个 chunk，每段截 400 字，控制 token 消耗。
    """
    valid = [t for t in chunk_texts if t.strip()]
    if not valid:
        return []

    snippets = valid[:12]
    combined = "\n\n---\n\n".join(
        f"Chunk {j+1}:\n{t[:400]}" for j, t in enumerate(snippets)
    )

    try:
        response = llm.chat(
            messages=[{"role": "user", "content": _CONCEPT_PROMPT.format(combined=combined)}],
            tools=None,
            tool_choice=None,
            max_tokens=400,
        )
        raw = (response.choices[0].message.content or "").strip()
    except Exception:
        logger.debug("import_concept_extraction_llm_failed", exc_info=True)
        return []

    entities: list[str] = []
    for line in raw.split("\n"):
        name = line.strip().lstrip("-•·0123456789. （) ")
        # 过滤空行和非合理名称（太短、太长、纯数字）
        if not name or len(name) < 2 or len(name) > 80:
            continue
        if name.isdigit():
            continue
        entities.append(name)

    # 去重保序
    return list(dict.fromkeys(entities))


def _build_chunk_memories(
    chunk: dict,
    content: str,
    index: int,
    total: int,
    source: str,
    title: str,
    tags: list[str],
    entities: list[str],
    now: datetime,
) -> list[Memory]:
    """为单个 chunk 构建 5 层 Memory 对象。

    五层：
        1. Working    — chunk 摘要，立即上下文
        2. Episodic   — 来源、时间戳、原始内容
        3. Semantic   — 关键概念、实体、标签
        4. Conceptual — 实体间关系
        5. Reflective — 跨 chunk 模式提示
    """
    source_label = title or source
    chunk_summary = content[:200] + ("..." if len(content) > 200 else "")
    chunk_entities: list[str] = chunk.get("entities", []) or []
    # 合并 chunk 自身实体 + 全局提取实体
    all_entities = list(dict.fromkeys(entities + chunk_entities))

    return [
        # Layer 1: Working Memory — chunk 摘要
        Memory(
            content=f"[工作区·导入] {source_label} (#{index + 1}/{total})\n{chunk_summary}",
            summary=chunk_summary[:100],
            source="agent",
            timestamp=now,
            importance=6,
            entities=all_entities[:10],
            memory_type="working",
        ),
        # Layer 2: Episodic Memory — 来源 + 时间
        Memory(
            content=(
                f"[情景·导入] 来源: {source}\n"
                f"标题: {source_label}\n"
                f"时间: {now.isoformat()}\n"
                f"Chunk: {index + 1}/{total}\n"
                f"内容: {content[:500]}"
            ),
            summary=f"从 {source} 导入 chunk #{index + 1}: {chunk_summary[:80]}",
            source="agent",
            timestamp=now,
            importance=5,
            entities=all_entities[:10],
            memory_type="episodic",
        ),
        # Layer 3: Semantic Memory — 关键概念 + 实体
        Memory(
            content=(
                f"[语义·导入] 来源: {source_label}\n"
                f"关键概念: {'; '.join(all_entities[:10]) if all_entities else '待提取'}\n"
                f"标签: {', '.join(tags[:10]) if tags else '无'}\n"
                f"摘要: {chunk_summary}"
            ),
            summary=f"语义知识: {chunk_summary[:100]}",
            source="agent",
            timestamp=now,
            importance=7,
            entities=all_entities[:15],
            memory_type="semantic",
        ),
        # Layer 4: Conceptual Memory — 实体关系
        Memory(
            content=(
                f"[概念·导入] 来源: {source_label}\n"
                f"实体集: {'; '.join(all_entities[:10]) if all_entities else '待提取'}\n"
                f"位置: chunk #{index + 1}/{total}\n"
                f"上下文: {chunk_summary[:150]}"
            ),
            summary=f"概念关联: {source_label} chunk #{index + 1}",
            source="agent",
            timestamp=now,
            importance=5,
            entities=all_entities[:10],
            memory_type="semantic",
        ),
        # Layer 5: Reflective Memory — 跨 chunk 模式
        Memory(
            content=(
                f"[反思·导入] 导入「{source_label}」(chunk {index + 1}/{total})。"
                f"关键实体: {', '.join(all_entities[:8]) if all_entities else '暂无'}。"
                f"此片段是整体知识的一部分，后续处理应关联已有记忆体系并发现跨片段模式。"
            ),
            summary=f"反思: {source_label} chunk #{index + 1}",
            source="agent",
            timestamp=now,
            importance=4,
            entities=all_entities[:8],
            memory_type="reflect",
        ),
    ]
