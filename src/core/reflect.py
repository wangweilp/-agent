"""Reflection Engine — 可插拔的回答质量自检机制。

协议定义：
    ReflectionEngine — 调用方只需依赖此协议，不依赖任何具体 LLM 实现。

默认实现：
    DefaultReflectionEngine — 通过 ChatModel 协议调用 LLM 做 CORRECTION/OK 判断。

使用示例（协议注入）：
    from src.core.reflect import ReflectionEngine, DefaultReflectionEngine

    agent = CognitiveAgent(
        ...,
        reflection_engine=CustomReflectionEngine(),  # 必须符合 ReflectionEngine 协议
    )
"""
import logging
from typing import Protocol, runtime_checkable

from src.core.memory import ChatModel

logger = logging.getLogger(__name__)

# ── Reflection 检查 prompt ──
_REFLECTION_PROMPT = """请检查以下回答是否存在问题：

用户问题：{user_input}
回答：{answer}

如果回答存在事实矛盾、遗漏关键记忆、或逻辑不自洽，请回复 "CORRECTION: <具体修正建议>"。
如果回答没有问题，请回复 "OK"。"""


# ── 协议 ──

@runtime_checkable
class ReflectionEngine(Protocol):
    """反思引擎协议 — 可插拔的反思检查。

    任何实现了此协议的对象都可以注入 CognitiveAgent。
    ChatModel 参数通过 reflect() 方法注入，而非构造时，保证了：
    - 调用方（CognitiveAgent）拥有 ChatModel 实例并传递
    - 协议实现方不持有 LLM 引用，避免生命周期耦合
    """

    def reflect(
        self, answer: str, user_input: str, llm: ChatModel
    ) -> tuple[bool, str]:
        """检查回答质量。

        Args:
            answer: Agent 生成的回答。
            user_input: 用户原始输入。
            llm: ChatModel 协议实例，用于调用 LLM 做判断。

        Returns:
            (需要修正, 修正建议)。不需要修正时返回 (False, "")。
        """
        ...


# ── 默认实现 ──

class DefaultReflectionEngine:
    """默认反思引擎 — 通过 ChatModel 协议调用 LLM 自检回答质量。

    实现 ReflectionEngine 协议，可被替换为更复杂的检查逻辑
    （如基于规则引擎、多模型投票、外部审阅服务等）。

    核心逻辑：
    1. 格式化检查 prompt（含用户问题 + Agent 回答）
    2. 调用 LLM 判断
    3. 解析 CORRECTION / OK
    """

    def reflect(
        self, answer: str, user_input: str, llm: ChatModel
    ) -> tuple[bool, str]:
        """检查回答质量。"""
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
