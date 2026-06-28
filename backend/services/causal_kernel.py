"""Causal kernel: intent routing + sandbox execution gate.

执行范围：
    - ``route_query``        : mock LLM intent classifier（关键字启发式，待后续替换为真实 LLM）。
    - ``execute_in_sandbox`` : 安全门控的 Python 沙箱执行器。

当 settings.SANDBOX_ENABLED=True 时，execute_in_sandbox 调用
SandboxV2Worker.execute_python_code 进行真实隔离执行（subprocess + tempfile，
AST 扫描 + 子串黑名单双重拦截，超时强制终止）；当 SANDBOX_ENABLED=False 时
回退到 mock 成功响应（simulation-driven，向下兼容）。

公共方法签名稳定，route_query 后续将由真实 LLM 调用替换。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from backend.core.config import settings
from src.open_platform.sandbox_v2.worker import SandboxV2Worker, SecurityViolationError

logger = logging.getLogger(__name__)


class CausalKernel:
    """Decision & execution brain for the Cognitive OS backend.

    route_query 为 mock 关键字分类器；execute_in_sandbox 在 SANDBOX_ENABLED=True
    时执行真实隔离 Python 代码，False 时回退到 mock。
    """

    # Substring blocklist for the sandbox security gate (from settings).
    FORBIDDEN_PATTERNS: List[str] = list(settings.SANDBOX_FORBIDDEN_PATTERNS)

    def __init__(self) -> None:
        # Keyword heuristics standing in for the LLM classifier.
        self._memory_keywords: tuple[str, ...] = (
            "记忆", "回忆", "查找", "搜索", "检索", "记得",
            "recall", "remember", "search", "memory", "lookup", "find",
        )
        self._code_keywords: tuple[str, ...] = (
            "执行", "运行", "跑一下", "代码", "计算",
            "execute", "run", "code", "eval", "python", "script", "compute",
        )

    # ---- intent routing ----------------------------------------------------
    async def route_query(self, query: str) -> str:
        """Mock LLM intent classification.

        Returns one of ``{"MEMORY_SEARCH", "CODE_EXECUTION"}``. The heuristic
        below emulates what a real LLM router would do; replace with an actual
        chat-completion call in a later phase (signature stays the same).
        """
        # Yield control so callers can rely on await semantics even while the
        # classifier is purely local.
        await asyncio.sleep(0)

        q = (query or "").lower()
        if any(kw in q for kw in self._code_keywords):
            intent = "CODE_EXECUTION"
        elif any(kw in q for kw in self._memory_keywords):
            intent = "MEMORY_SEARCH"
        else:
            # Default fallback: treat ambiguous input as a memory recall.
            intent = "MEMORY_SEARCH"

        logger.info("route_query intent=%s query=%r", intent, query)
        return intent

    # ---- sandbox executor --------------------------------------------------
    async def execute_in_sandbox(self, code_string: str) -> Dict[str, Any]:
        """安全门控的 Python 沙箱执行器。

        执行流程：
          Layer 0 — 本地子串黑名单快速预检（FORBIDDEN_PATTERNS）
          Layer 1 — 若 SANDBOX_ENABLED=False，回退 mock 成功响应（向下兼容）
          Layer 2 — SANDBOX_ENABLED=True 时调用 SandboxV2Worker.execute_python_code
                    真实隔离执行（AST 扫描 + 子串黑名单 + subprocess + tempfile）
          Layer 3 — 捕获 SecurityViolationError / 执行器崩溃，转自然语言反馈

        返回契约（保持不变）：
            {
                "status": "SUCCESS" | "INTERCEPTED" | "TIMEOUT" | "FAILED",
                "reason": str | None,   # 自然语言反馈，供 Agent 自我修复
                "result": {"stdout": str, "stderr": str, "exit_code": int, "mock": bool} | None,
                "execution_time_ms": int,
            }
        """
        await asyncio.sleep(0)

        # Layer 0: 本地子串黑名单快速预检（与原行为一致）
        intercepted = self._scan_for_forbidden_patterns(code_string)
        if intercepted is not None:
            logger.warning(
                "execute_in_sandbox INTERCEPTED pattern=%r", intercepted
            )
            return {
                "status": "INTERCEPTED",
                "reason": (
                    f"代码被安全扫描拦截：检测到高危词 '{intercepted}'。"
                    "请移除 os.system / subprocess / rm -rf / shutil.rmtree 等高危调用后重试。"
                ),
                "result": None,
                "execution_time_ms": 0,
            }

        # Layer 1: SANDBOX_ENABLED=False → mock fallback（保持向下兼容）
        if not settings.SANDBOX_ENABLED:
            logger.info(
                "execute_in_sandbox SUCCESS (mock, sandbox disabled) len=%d",
                len(code_string),
            )
            return {
                "status": "SUCCESS",
                "reason": None,
                "result": {
                    "stdout": "",
                    "stderr": "",
                    "exit_code": 0,
                    "mock": True,
                },
                "execution_time_ms": 0,
            }

        # Layer 2: SANDBOX_ENABLED=True → 真实隔离执行
        try:
            result = SandboxV2Worker.execute_python_code(
                code_string=code_string,
                timeout_seconds=settings.SANDBOX_EXECUTION_TIMEOUT_SECONDS,
                max_output_characters=settings.SANDBOX_MAX_OUTPUT_CHARACTERS,
                forbidden_patterns=list(settings.SANDBOX_FORBIDDEN_PATTERNS),
            )
        except SecurityViolationError as e:
            # 安全扫描拦截（AST / 子串黑名单）
            logger.warning("execute_in_sandbox INTERCEPTED security=%s", e)
            return {
                "status": "INTERCEPTED",
                "reason": (
                    f"代码被沙箱安全扫描拦截：{e}。"
                    "请移除高危调用（os.system/subprocess/eval/exec/shutil.rmtree 等）后重试。"
                ),
                "result": None,
                "execution_time_ms": 0,
            }
        except Exception as e:
            # 执行器自身崩溃（非子进程崩溃）
            logger.exception("execute_in_sandbox executor crashed: %s", e)
            return {
                "status": "FAILED",
                "reason": (
                    f"沙箱执行器自身崩溃：{type(e).__name__}: {e}。"
                    "请稍后重试或简化代码。"
                ),
                "result": None,
                "execution_time_ms": 0,
            }

        # Layer 3: 真实执行完成，根据结果状态封装自然语言反馈
        if result.success:
            logger.info(
                "execute_in_sandbox SUCCESS (real) exit=0 ms=%d",
                result.duration_ms,
            )
            stdout_preview = result.stdout[:2000] if result.stdout else ""
            reason = (
                f"代码执行成功。标准输出：\n{stdout_preview}"
                if stdout_preview else None
            )
            return {
                "status": "SUCCESS",
                "reason": reason,
                "result": {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.exit_code,
                    "mock": False,
                },
                "execution_time_ms": result.duration_ms,
            }
        elif result.timed_out:
            logger.warning(
                "execute_in_sandbox TIMEOUT ms=%d", result.duration_ms
            )
            return {
                "status": "TIMEOUT",
                "reason": (
                    f"代码执行超时（{settings.SANDBOX_EXECUTION_TIMEOUT_SECONDS}s 后被强制终止）。"
                    "请检查是否存在死循环、阻塞 I/O 或耗时操作，优化后重试。"
                ),
                "result": {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.exit_code,
                    "mock": False,
                },
                "execution_time_ms": result.duration_ms,
            }
        else:
            logger.warning(
                "execute_in_sandbox FAILED exit=%d", result.exit_code
            )
            stderr_preview = (
                result.stderr[:2000] if result.stderr else "(无错误输出)"
            )
            return {
                "status": "FAILED",
                "reason": (
                    f"代码执行崩溃（exit_code={result.exit_code}）。"
                    f"错误输出：\n{stderr_preview}\n"
                    "请根据报错修复代码后重试。"
                ),
                "result": {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.exit_code,
                    "mock": False,
                },
                "execution_time_ms": result.duration_ms,
            }

    # ---- helpers -----------------------------------------------------------
    def _scan_for_forbidden_patterns(self, code_string: str) -> Optional[str]:
        """Return the first forbidden pattern found, or None."""
        normalized = (code_string or "").lower()
        for pattern in self.FORBIDDEN_PATTERNS:
            if pattern.lower() in normalized:
                return pattern
        return None
