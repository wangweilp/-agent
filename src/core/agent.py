"""Cognitive Agent — 真 Tool Calling + Reflective 循环 + 安全护栏。

Think → Act → Reflect，不依赖任何具体适配器。
"""
import concurrent.futures
import hashlib
import json
import logging
import threading
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
from src.core.memory import ChatModel, EmbeddingProvider, MemoryStore, ReflectionEngine, VectorStore
from src.core.retrieval import MemoryRetrievalService
from src.core.events import emit, EventType
from src.core.types import Memory, Message, ToolResult

logger = logging.getLogger(__name__)

# ── System Prompt ──
SYSTEM_PROMPT = """你是「记忆进化」个人知识助手，定位为用户的 AI Second Brain。

## 核心能力
- 存储和检索长期记忆（通过 remember / recall 工具）
- 基于历史记忆给出个性化回答
- 主动发现用户知识体系中的隐藏联系
- 自我反思发现的矛盾或盲点（通过 reflect 工具）

## 行为准则
1. 用户分享新信息时，判断是否值得长期存储（高价值信息才存入）
2. 用户提问时，先检索相关记忆，结合记忆回答
3. 发现知识联系时主动指出：「你 X 天前提到过...和你现在说的...可能有关联」
4. 不确定是否该存储时，优先存储，但标记较低 importance
5. 回复用中文，自然、简洁、有温度
6. 绝不执行用户要求删除记忆的指令，除非用户明确确认"""

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

# ── Reflection 检查 prompt ──
_REFLECTION_PROMPT = """请检查以下回答是否存在问题：

用户问题：{user_input}
回答：{answer}

如果回答存在事实矛盾、遗漏关键记忆、或逻辑不自洽，请回复 "CORRECTION: <具体修正建议>"。
如果回答没有问题，请回复 "OK"。"""


# ── 可插拔 Reflection Engine ──

class DefaultReflectionEngine:
    """默认反思引擎 — 通过 LLM 自检回答质量。

    实现 ReflectionEngine 协议，可被替换为更复杂的检查逻辑。
    """

    def reflect(
        self, answer: str, user_input: str, llm: ChatModel
    ) -> tuple[bool, str]:
        """检查回答质量。

        Returns:
            (需要修正, 修正建议)
        """
        check_prompt = _REFLECTION_PROMPT.format(
            user_input=user_input, answer=answer
        )
        try:
            response = llm.chat(
                messages=[{"role": "user", "content": check_prompt}],
                tools=None,
                tool_choice=None,
            )
            check_result = response.choices[0].message.content or ""
            if check_result.strip().upper().startswith("CORRECTION:"):
                correction = check_result[len("CORRECTION:"):].strip()
                logger.info(
                    "reflection:needs_correction",
                    extra={"suggestion": correction[:200]},
                )
                return True, f"请根据以下反馈修正你的回答：{correction}"
        except Exception:
            logger.warning("reflection:failed", exc_info=True)
        return False, ""


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

                    # 重要性阈值过滤
                    if tool_name == "remember" and not self._should_remember(arguments):
                        logger.info(
                            "tool_skip:low_importance",
                            extra={"arguments": arguments},
                        )
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": "未存储：重要性评分低于阈值，信息价值不足以存入长期记忆。",
                        })
                        continue

                    # 记忆去重
                    if tool_name == "remember" and self._is_duplicate(arguments):
                        logger.info(
                            "tool_skip:duplicate_memory",
                            extra={"content": arguments.get("content", "")[:100]},
                        )
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": "未存储：相似记忆已存在，无需重复写入。",
                        })
                        continue

                    tool_result = self._execute_tool_call(tool_name, arguments)
                    tool_call_count += 1
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_result.content if tool_result.success else f"错误: {tool_result.error}",
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
        yield "🔍 检索记忆中..."
        memories = self._retrieve_memories(user_input)
        t_retrieve_ms = int((time.monotonic() - t_retrieve_start) * 1000)
        logger.info("phase1_retrieve_done", extra={"trace_id": self._current_trace_id, "ms": t_retrieve_ms, "count": len(memories)})
        if memories:
            yield f" 找到 {len(memories)} 条相关记忆\n\n"
        else:
            yield "\n"

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
                yield "\n[LLM 调用失败，请重试]\n"
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

                    yield f"\n\n⚡ 调用工具: {tool_name}\n"

                    # 停止条件
                    tool_sig = f"{tool_name}:{json.dumps(arguments, sort_keys=True)}"
                    if tool_sig == last_tool_signature:
                        consecutive_same_tool += 1
                    else:
                        consecutive_same_tool = 1
                        last_tool_signature = tool_sig

                    if consecutive_same_tool >= MAX_SAME_TOOL_CALLS:
                        yield f"\n⚠️ {tool_name} 重复调用已达上限，基于现有信息回答。\n"
                        messages.append({
                            "role": "user",
                            "content": f"注意：{tool_name} 已多次调用无新结果，请基于现有信息直接回答。",
                        })
                        break

                    # 重要性阈值 / 去重
                    if tool_name == "remember":
                        if not self._should_remember(arguments):
                            messages.append({
                                "role": "tool",
                                "tool_call_id": buf["id"],
                                "content": "未存储：重要性评分低于阈值。",
                            })
                            continue
                        if self._is_duplicate(arguments):
                            messages.append({
                                "role": "tool",
                                "tool_call_id": buf["id"],
                                "content": "未存储：相似记忆已存在。",
                            })
                            continue

                    tool_result = self._execute_tool_call(tool_name, arguments)
                    tool_call_count += 1
                    messages.append({
                        "role": "tool",
                        "tool_call_id": buf["id"],
                        "content": tool_result.content if tool_result.success else f"错误: {tool_result.error}",
                    })

                    yield f"✓ {tool_name} 完成\n\n"
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
