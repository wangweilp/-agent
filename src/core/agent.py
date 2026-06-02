"""Cognitive Agent — 真 Tool Calling + Reflective 循环 + 安全护栏。
Think → Act → Reflect，不依赖任何具体适配器。
"""
import concurrent.futures
import hashlib
import json
import logging
import time
import uuid
from collections.abc import Generator
from typing import Any, Protocol

from src.core.constants import (
    DEDUP_SIMILARITY_THRESHOLD,
    MAX_LLM_RETRIES,
    MAX_SAME_TOOL_CALLS,
    MIN_IMPORTANCE_FOR_STORAGE,
    TOOL_TIMEOUT_SECONDS,
)
from src.core.context import ContextBuilder
from src.core.memory import ChatModel, EmbeddingProvider, MemoryStore, VectorStore
from src.core.reflect import DefaultReflectionEngine, ReflectionEngine
from src.core.retrieval import MemoryRetrievalService
from src.core.events import emit, EventType
from src.core.memory_queue import MemoryWriteWorker, MemoryWriteTask
from src.core.types import Memory, Message, ToolResult

logger = logging.getLogger(__name__)

# ── System Prompt ──
SYSTEM_PROMPT = """你是一个具备长期记忆能力的 AI 工作助手。

## 工具
可使用 remember / recall / reflect 工具管理记忆。工具调用对用户完全透明，不提及、不描述、不解释。

## 行为准则
- 直接给结果，任何情况下都不写"让我先""我来帮你""我先查一下"之类前摇
- 不主动介绍模型身份，不提 DeepSeek/OpenAI/任何具体模型名或公司。被问「你是什么模型」时，只回答「我是你的长期记忆助手」
- 不解释你在做什么、为什么调用工具、内部流程如何运作
- 不暴露系统错误（数据库、线程、网络等），如工具操作失败，不给用户解释技术原因
- 回复中文，简洁自然专业，不使用 emoji 或拟人化表达
- 用户提问时先检索记忆，发现关联时用「你 X 天前提到过...」指出
- 不执行用户要求删除记忆的指令，除非用户明确确认"""

# ── Tool Definitions（OpenAI/DeepSeek 兼容格式）──
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": "存储一条新的长期记忆。当用户分享值得记住的信息时调用此工具。",
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
    },
    {
        "type": "function",
        "function": {
            "name": "recall",
            "description": "检索相关长期记忆。回答用户问题前应先调用此工具查找相关历史信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "检索关键词或问题",
                    },
                    "top_k": {
                        "type": "integer",
                        "default": 3,
                        "description": "返回的记忆数量",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reflect",
            "description": "反思近期对话，主动发现矛盾、联系或知识盲点。",
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
    },
]

# ── Agent ──

class ToolExecutor(Protocol):
    """工具执行器协议 — 由 tools/registry.py 实现。"""

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        """执行指定工具，返回结果。"""
        ...


class AgentError(Exception):
    """Agent 运行时错误。"""


class CognitiveAgent:
    """认知 Agent — Think → Act → Reflect 循环 + 安全护栏。

    护栏：
    - LLM 调用指数退避重试（MAX_LLM_RETRIES=3）
    - 同一工具连续调用上限（MAX_SAME_TOOL_CALLS=3）
    - 重复回答检测（内容哈希）
    - 记忆重要性阈值过滤

    所有外部能力通过协议注入，不依赖具体适配器。
    """

    def __init__(
        self,
        llm: ChatModel,
        memory_store: MemoryStore,
        vector_store: VectorStore,
        embedding_provider: EmbeddingProvider,
        tool_executor: ToolExecutor,
        *,
        context_builder: ContextBuilder | None = None,
        reflection_engine: ReflectionEngine | None = None,
        retrieval_service: MemoryRetrievalService | None = None,
        memory_writer: MemoryWriteWorker | None = None,
        max_tool_rounds: int = 5,
        importance_threshold: int = MIN_IMPORTANCE_FOR_STORAGE,
        system_prompt: str = "",
    ) -> None:
        self._llm = llm
        self._memory_store = memory_store
        self._vector_store = vector_store
        self._embedding = embedding_provider
        self._tool_executor = tool_executor
        self._context_builder = context_builder or ContextBuilder()
        self._reflection = reflection_engine or DefaultReflectionEngine()
        self._retrieval_service = retrieval_service or MemoryRetrievalService(
            memory_store, vector_store, embedding_provider,
        )
        self._memory_writer = memory_writer
        self._max_tool_rounds = max_tool_rounds
        self._importance_threshold = importance_threshold
        self._system_prompt = system_prompt or SYSTEM_PROMPT
        self._short_term: list[Message] = []
        self._current_trace_id: str = ""

    # ── 公共 API ──

    def run(self, user_input: str) -> str:
        """处理单轮用户输入，返回最终回复。"""
        t_start = time.monotonic()
        self._current_trace_id = str(uuid.uuid4())
        emit(
            EventType.AGENT_START,
            trace_id=self._current_trace_id,
            input=user_input[:200],
        )
        logger.info(
            "agent_run_start",
            extra={
                "trace_id": self._current_trace_id,
                "user_input": user_input[:100],
            },
        )

        memories = self._retrieve_memories(user_input)
        context = self._context_builder.build(
            system_prompt=self._system_prompt,
            recent_messages=self._short_term,
            long_term_memories=memories,
            user_input=user_input,
        )
        messages: list[dict[str, Any]] = context["messages"]

        # 安全护栏状态
        consecutive_same_tool = 0
        last_tool_signature = ""
        seen_responses: set[str] = set()
        tool_call_count = 0

        for round_idx in range(self._max_tool_rounds):
            t_llm_start = time.monotonic()
            response = self._retry_llm_call(
                messages=messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
            )
            msg = response.choices[0].message
            logger.info(
                "llm_response",
                extra={
                    "trace_id": self._current_trace_id,
                    "round": round_idx,
                    "has_tool_calls": bool(msg.tool_calls),
                    "content_len": len(msg.content or ""),
                    "duration_ms": int((time.monotonic() - t_llm_start) * 1000),
                },
            )

            # ── 有 tool_calls → 执行工具 ──
            if msg.tool_calls:
                messages.append(self._format_assistant_message(msg))

                for tc in msg.tool_calls:
                    tool_name = tc.function.name
                    arguments = self._parse_arguments(tc.function.arguments)

                    # 停止条件检查：同一工具重复调用
                    tool_sig = f"{tool_name}:{json.dumps(arguments, sort_keys=True)}"
                    if tool_sig == last_tool_signature:
                        consecutive_same_tool += 1
                    else:
                        consecutive_same_tool = 1
                        last_tool_signature = tool_sig

                    if consecutive_same_tool >= MAX_SAME_TOOL_CALLS:
                        logger.warning(
                            "stop_condition:same_tool_repeated",
                            extra={
                                "trace_id": self._current_trace_id,
                                "tool": tool_name,
                                "count": consecutive_same_tool,
                            },
                        )
                        messages.append({
                            "role": "user",
                            "content": f"注意：{tool_name} 已多次调用无新结果，请基于现有信息直接回答。",
                        })
                        break

                    # 重要性阈值过滤（同步，无 I/O）
                    if tool_name == "remember" and not self._should_remember(arguments):
                        logger.info(
                            "tool_skip:low_importance",
                            extra={"arguments": arguments},
                        )
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": "已跳过：信息价值较低。",
                        })
                        continue

                    # remember → 异步写入（有Worker）或同步降级（无Worker）
                    if tool_name == "remember":
                        tool_msg = self._fire_and_forget_remember(tc.id, arguments)
                        tool_call_count += 1
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": tool_msg,
                        })
                        continue

                    tool_result = self._execute_tool_call(tool_name, arguments)
                    tool_call_count += 1
                    tool_content = tool_result.user_message
                    if not tool_result.success:
                        logger.warning(
                            "tool_error_silenced",
                            extra={"tool": tool_name, "error": tool_result.error},
                        )
                        # 失败时把错误信息喂给 LLM，避免静默吞掉
                        if tool_result.error and tool_result.error not in (tool_content or ""):
                            tool_content = f"{tool_content}（错误: {tool_result.error}）"
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_content,
                    })
                else:
                    continue
                continue

            # ── 无 tool_calls → 获得回答 ──
            final_answer = msg.content or ""

            # 重复回答检测
            answer_hash = hashlib.md5(final_answer.encode()).hexdigest()
            if answer_hash in seen_responses and round_idx > 0:
                logger.warning(
                    "stop_condition:duplicate_response",
                    extra={"trace_id": self._current_trace_id, "round": round_idx},
                )
                self._commit_to_short_term(user_input, final_answer)
                return final_answer
            seen_responses.add(answer_hash)

            # Reflection 自检（最后一轮不检）
            if round_idx < self._max_tool_rounds - 1:
                t_ref_start = time.monotonic()
                needs_fix, correction = self._reflection.reflect(
                    final_answer, user_input, self._llm
                )
                logger.info(
                    "reflection_check",
                    extra={
                        "trace_id": self._current_trace_id,
                        "needs_fix": needs_fix,
                        "duration_ms": int((time.monotonic() - t_ref_start) * 1000),
                    },
                )
                if needs_fix:
                    messages.append({
                        "role": "user",
                        "content": correction,
                    })
                    continue

            self._commit_to_short_term(user_input, final_answer)
            emit(
                EventType.AGENT_DONE,
                trace_id=self._current_trace_id,
                rounds=round_idx + 1,
                tool_calls=tool_call_count,
            )
            logger.info(
                "agent_run_done",
                extra={
                    "trace_id": self._current_trace_id,
                    "rounds": round_idx + 1,
                    "tool_calls": tool_call_count,
                    "total_ms": int((time.monotonic() - t_start) * 1000),
                },
            )
            return final_answer

        # 超过最大轮数
        logger.warning("agent_max_rounds_exceeded", extra={"rounds": self._max_tool_rounds})
        return self._best_effort(messages)

    def run_stream(self, user_input: str) -> Generator[str, None, None]:
        """流式版本 — 逐 token 返回，不等待完整响应。

        与 run() 逻辑相同，但 LLM 调用使用 stream=True，
        每收到一个 token 就 yield 出去，消除首字节延迟。
        """
        t_start = time.monotonic()
        self._current_trace_id = str(uuid.uuid4())
        t_setup = time.monotonic()
        logger.info(
            "agent_run_stream_start",
            extra={"trace_id": self._current_trace_id, "user_input": user_input[:100]},
        )

        # ── Phase 1: 记忆检索 ──
        t_retrieve_start = time.monotonic()
        logger.info("phase1_retrieve_start", extra={"trace_id": self._current_trace_id})
        memories = self._retrieve_memories(user_input)
        t_retrieve_ms = int((time.monotonic() - t_retrieve_start) * 1000)
        logger.info("phase1_retrieve_done", extra={"trace_id": self._current_trace_id, "ms": t_retrieve_ms, "count": len(memories)})

        context = self._context_builder.build(
            system_prompt=self._system_prompt,
            recent_messages=self._short_term,
            long_term_memories=memories,
            user_input=user_input,
        )
        messages: list[dict[str, Any]] = context["messages"]

        consecutive_same_tool = 0
        last_tool_signature = ""
        seen_responses: set[str] = set()
        tool_call_count = 0

        for round_idx in range(self._max_tool_rounds):
            t_llm_start = time.monotonic()
            logger.info("phase2_llm_stream_start", extra={"trace_id": self._current_trace_id, "round": round_idx, "msg_count": len(messages)})
            try:
                stream = self._llm.chat(
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                    stream=True,
                )
            except Exception:
                logger.warning("stream_llm_failed", exc_info=True)
                return

            content_parts: list[str] = []
            tool_call_buffers: dict[int, dict[str, Any]] = {}
            first_chunk = True

            for chunk in stream:
                if first_chunk:
                    t_first_token_ms = int((time.monotonic() - t_llm_start) * 1000)
                    logger.info("phase2_first_chunk", extra={"trace_id": self._current_trace_id, "ttft_ms": t_first_token_ms})
                    first_chunk = False
                delta = chunk.choices[0].delta
                if delta.content:
                    content_parts.append(delta.content)
                    yield delta.content
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_call_buffers:
                            tool_call_buffers[idx] = {
                                "id": "",
                                "function": {"name": "", "arguments": ""},
                            }
                        buf = tool_call_buffers[idx]
                        if tc_delta.id:
                            buf["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                if not buf["function"]["name"]:
                                    buf["function"]["name"] = tc_delta.function.name
                            if tc_delta.function.arguments:
                                buf["function"]["arguments"] += tc_delta.function.arguments

            content = "".join(content_parts)
            t_llm_ms = int((time.monotonic() - t_llm_start) * 1000)

            # ── 有 tool_calls → 执行工具 ──
            if tool_call_buffers:
                messages.append({
                    "role": "assistant",
                    "content": content or "",
                    "tool_calls": [
                        {
                            "id": buf["id"],
                            "type": "function",
                            "function": {
                                "name": buf["function"]["name"],
                                "arguments": buf["function"]["arguments"],
                            },
                        }
                        for buf in tool_call_buffers.values()
                    ],
                })

                for buf in tool_call_buffers.values():
                    tool_name = buf["function"]["name"]
                    arguments = self._parse_arguments(buf["function"]["arguments"])

                    # 停止条件
                    tool_sig = f"{tool_name}:{json.dumps(arguments, sort_keys=True)}"
                    if tool_sig == last_tool_signature:
                        consecutive_same_tool += 1
                    else:
                        consecutive_same_tool = 1
                        last_tool_signature = tool_sig

                    if consecutive_same_tool >= MAX_SAME_TOOL_CALLS:
                        messages.append({
                            "role": "user",
                            "content": f"注意：{tool_name} 已多次调用无新结果，请基于现有信息直接回答。",
                        })
                        break

                    # 重要性阈值过滤（同步，无 I/O）
                    if tool_name == "remember":
                        if not self._should_remember(arguments):
                            messages.append({
                                "role": "tool",
                                "tool_call_id": buf["id"],
                                "content": "已跳过：信息价值较低。",
                            })
                            continue

                    # remember → 异步写入（有Worker）或同步降级（无Worker）
                    if tool_name == "remember":
                        tool_msg = self._fire_and_forget_remember(buf["id"], arguments)
                        tool_call_count += 1
                        messages.append({
                            "role": "tool",
                            "tool_call_id": buf["id"],
                            "content": tool_msg,
                        })
                        continue

                    tool_result = self._execute_tool_call(tool_name, arguments)
                    tool_call_count += 1
                    tool_content = tool_result.user_message
                    if not tool_result.success:
                        logger.warning(
                            "tool_error_silenced",
                            extra={"tool": tool_name, "error": tool_result.error},
                        )
                        if tool_result.error and tool_result.error not in (tool_content or ""):
                            tool_content = f"{tool_content}（错误: {tool_result.error}）"
                    messages.append({
                        "role": "tool",
                        "tool_call_id": buf["id"],
                        "content": tool_content,
                    })
                else:
                    continue
                continue

            # ── 无 tool_calls → 获得回答 ──
            if not content.strip():
                continue

            answer_hash = hashlib.md5(content.encode()).hexdigest()
            if answer_hash in seen_responses and round_idx > 0:
                self._commit_to_short_term(user_input, content)
                return

            seen_responses.add(answer_hash)

            t_total_ms = int((time.monotonic() - t_start) * 1000)
            self._commit_to_short_term(user_input, content)
            logger.info(
                "agent_run_stream_done",
                extra={
                    "trace_id": self._current_trace_id,
                    "rounds": round_idx + 1,
                    "tool_calls": tool_call_count,
                    "retrieve_ms": t_retrieve_ms,
                    "last_llm_ms": t_llm_ms,
                    "total_ms": t_total_ms,
                },
            )
            return

        # 超过最大轮数
        logger.warning("agent_max_rounds_exceeded", extra={"rounds": self._max_tool_rounds})
        fallback = self._best_effort(messages)
        yield fallback

    def reset(self) -> None:
        """重置短期记忆（新会话开始时调用）。"""
        self._short_term.clear()

    @property
    def short_term_size(self) -> int:
        return len(self._short_term)

    @property
    def trace_id(self) -> str:
        return self._current_trace_id

    # ── LLM 调用 + 重试 ──

    def _retry_llm_call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
    ) -> Any:
        """带指数退避的 LLM 调用。"""
        last_error: Exception | None = None
        msg_count = len(messages)
        for attempt in range(MAX_LLM_RETRIES):
            try:
                return self._llm.chat(
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                )
            except Exception as e:
                last_error = e
                if attempt == MAX_LLM_RETRIES - 1:
                    break
                wait = 2 ** attempt
                logger.warning(
                    "llm_retry",
                    extra={
                        "attempt": attempt + 1,
                        "max_retries": MAX_LLM_RETRIES,
                        "error": str(e)[:200],
                        "wait_s": wait,
                        "msg_count": msg_count,
                    },
                )
                time.sleep(wait)

        raise AgentError(f"LLM 调用失败，已重试 {MAX_LLM_RETRIES} 次: {last_error}")

    # ── 记忆检索 ──

    def _retrieve_memories(self, user_input: str) -> list[Memory]:
        """检索相关长期记忆，统一使用 MemoryRetrievalService。"""
        return self._retrieval_service.retrieve(user_input, top_k=5)

    # ── 工具执行 ──

    def _parse_arguments(self, arguments: str) -> dict[str, Any]:
        """安全解析 JSON 参数。"""
        try:
            return json.loads(arguments)
        except json.JSONDecodeError:
            logger.warning("工具参数 JSON 解析失败: %s", arguments[:100])
            return {}

    def _should_remember(self, arguments: dict[str, Any]) -> bool:
        """重要性阈值过滤：低价值信息不存储。"""
        override = arguments.get("importance_override")
        if override is not None and override < self._importance_threshold:
            return False
        return True

    def _is_duplicate(self, arguments: dict[str, Any]) -> bool:
        """记忆去重：检查是否已存在高度相似记忆。

        对新内容做 embedding → 向量搜索 → 相似度 > 阈值则拒绝。
        """
        content = arguments.get("content", "")
        if not content:
            return False
        try:
            embedding = self._embedding.encode(content)
            results = self._vector_store.search(embedding, k=3)
            for r in results:
                # vector_store.search 已返回 cosine_similarity (0~1)，直接比较
                if r.score > DEDUP_SIMILARITY_THRESHOLD:
                    logger.info(
                        "memory_dedup_hit",
                        extra={
                            "new_content": content[:100],
                            "existing_doc": r.doc_id,
                            "similarity": round(r.score, 4),
                        },
                    )
                    return True
        except Exception:
            logger.debug("memory_dedup_check_failed", exc_info=True)
        return False

    def _execute_tool_call(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        """执行工具调用，带超时保护。"""
        t_start = time.monotonic()
        emit(
            EventType.TOOL_CALL_START,
            trace_id=self._current_trace_id,
            tool=tool_name,
        )
        logger.info(
            "tool_call_start",
            extra={
                "trace_id": self._current_trace_id,
                "tool": tool_name,
                "args_summary": str(arguments)[:200],
            },
        )

        def _run() -> ToolResult:
            try:
                return self._tool_executor.execute(tool_name, arguments)
            except Exception as e:
                return ToolResult(
                    tool_name=tool_name,
                    success=False,
                    error=str(e),
                )

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_run)
                result = future.result(timeout=TOOL_TIMEOUT_SECONDS)
        except concurrent.futures.TimeoutError:
            elapsed = int((time.monotonic() - t_start) * 1000)
            logger.error(
                "tool_timeout",
                extra={"tool": tool_name, "elapsed_ms": elapsed},
            )
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"工具执行超时（{TOOL_TIMEOUT_SECONDS}s）",
            )

        elapsed = int((time.monotonic() - t_start) * 1000)
        emit(
            EventType.TOOL_CALL_DONE,
            trace_id=self._current_trace_id,
            tool=tool_name,
            success=result.success,
            elapsed_ms=elapsed,
        )
        logger.info(
            "tool_call_done",
            extra={
                "trace_id": self._current_trace_id,
                "tool": tool_name,
                "success": result.success,
                "elapsed_ms": elapsed,
            },
        )
        return result

    # ── 兜底 ──

    def _best_effort(self, messages: list[dict[str, Any]]) -> str:
        """工具循环超限后，请求 LLM 给出当前最佳回复。"""
        try:
            messages.append({
                "role": "user",
                "content": "请基于当前所有信息，给出你最好的回答。",
            })
            response = self._llm.chat(messages=messages, tools=None, tool_choice=None)
            return response.choices[0].message.content or "抱歉，我暂时无法回答这个问题。"
        except Exception:
            logger.exception("best_effort 调用失败")
            return "抱歉，处理过程中出现问题，请稍后重试。"

    # ── 图片上下文构建 ──

    def build_image_context(self, user_input: str = "") -> dict:
        """构建图片分析所需的对话上下文和历史记忆。"""
        # 对话上下文：最近短期记忆
        parts = []
        for msg in self._short_term[-4:]:
            role = "用户" if msg.role == "user" else "助手"
            parts.append(f"[{role}]: {msg.content[:150]}")
        conversation_context = "\n".join(parts) if parts else "暂无对话"

        # 历史记忆检索
        query = user_input or " ".join(
            m.content[:50] for m in self._short_term[-2:] if m.role == "user"
        )
        memories: list = []
        if query.strip():
            memories = self._retrieval_service.retrieve(query, top_k=5)
        memories_text = self._retrieval_service.format_results(memories) if memories else "暂无"

        return {
            "conversation_context": conversation_context,
            "historical_memories": memories_text,
            "memories": memories,
        }

    # ── 短期记忆管理 ──

    def _commit_to_short_term(self, user_input: str, answer: str) -> None:
        """将本轮对话存入短期记忆并裁剪。"""
        self._short_term.append(Message(role="user", content=user_input))
        self._short_term.append(Message(role="assistant", content=answer))
        if len(self._short_term) > 20:
            self._short_term = self._short_term[-20:]

    @staticmethod
    def _format_assistant_message(msg: Any) -> dict[str, Any]:
        """将 OpenAI message 对象转为 dict 格式。"""
        return {
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ],
        }

    # ── 异步记忆写入 ──

    def _fire_and_forget_remember(self, call_id: str, arguments: dict[str, Any]) -> str:
        """异步写入记忆，返回 tool response 中应填入的内容。

        有 MemoryWriteWorker → 异步入队，立即返回"已接受处理。"。
        无 MemoryWriteWorker → 同步执行，返回真实结果（成功/失败）。
        """
        # 主路径：异步入队，不阻塞 LLM
        if self._memory_writer is not None:
            self._memory_writer.enqueue(MemoryWriteTask(arguments=arguments, call_id=call_id))
            return "已接受处理。"

        # 降级路径：无 Worker 时同步执行，保证测试/CLI模式记忆不丢失
        logger.warning(
            "remember_fallback_sync",
            extra={"call_id": call_id, "reason": "MemoryWriteWorker 未配置，回退同步写入"},
        )
        try:
            result = self._tool_executor.execute("remember", arguments)
        except Exception:
            logger.exception("remember_fallback_crashed")
            return "写入失败，请稍后重试。"

        if result.success:
            logger.info(
                "remember_fallback_sync_ok",
                extra={"call_id": call_id, "memory_id": result.metadata.get("memory_id", "")},
            )
        else:
            logger.warning(
                "remember_fallback_sync_failed",
                extra={"call_id": call_id, "error": result.error},
            )
        return result.user_message

    def shutdown(self) -> None:
        """关闭 MemoryWriteWorker，等待未完成的写入刷盘。"""
        if self._memory_writer is not None:
            self._memory_writer.shutdown()
