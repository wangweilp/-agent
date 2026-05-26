"""工具注册表 — 统一注册、权限分级、统一调度。"""
import logging
from typing import Any

from src.core.memory import ChatModel, EmbeddingProvider, MemoryStore, Tool, VectorStore
from src.core.types import ToolResult

logger = logging.getLogger(__name__)

SAFE_TOOLS = ["remember", "recall", "reflect"]
DANGEROUS_TOOLS = ["delete_memory", "overwrite_memory"]


class ToolRegistry:
    """工具注册表，实现 ToolExecutor 协议。

    权限分级：
    - SAFE_TOOLS: 无需确认，直接执行
    - DANGEROUS_TOOLS: 需要人工确认才能执行
    """

    def __init__(
        self,
        memory_store: MemoryStore,
        vector_store: VectorStore,
        embedding_provider: EmbeddingProvider,
        llm: ChatModel,
    ) -> None:
        self._tools: dict[str, Tool] = {}
        self._memory_store = memory_store
        self._vector_store = vector_store
        self._embedding = embedding_provider
        self._llm = llm
        self._register_defaults()

    def _register_defaults(self) -> None:
        from src.tools.remember import RememberTool
        from src.tools.recall import RecallTool
        from src.tools.reflect import ReflectTool

        self.register(RememberTool(
            self._memory_store, self._vector_store, self._embedding
        ))
        self.register(RecallTool(
            self._memory_store, self._vector_store, self._embedding
        ))
        self.register(ReflectTool(
            self._memory_store, self._vector_store, self._embedding, self._llm
        ))

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        logger.info("tool_registered", extra={"name": tool.name})

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        if tool_name in DANGEROUS_TOOLS:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error="需要人工确认才能执行此操作",
            )

        tool = self._tools.get(tool_name)
        if tool is None:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"未知工具: {tool_name}",
            )

        return tool.execute(arguments)

    def get_schemas(self) -> list[dict[str, Any]]:
        return [tool.schema for tool in self._tools.values()]

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())
