"""内置 Agent 实现。

- Knowledge Agent — 知识管理
- Meeting Agent   — 会议处理
- Research Agent  — 深度研究
- Sales Agent     — 销售支持
- Support Agent   — 客户支持
- Training Agent  — 培训辅助
"""

from __future__ import annotations

from src.agents.runtime import (
    Agent,
    AgentContext,
    AgentResult,
    AgentTask,
    BaseAgent,
    KnowledgeGraphProvider,
    MemoryProvider,
    ToolProvider,
)
