"""Enterprise AI Agent Platform — 让企业知识变成企业行动力。

Agent Runtime → Registry → Workflow → Department → API
"""

from src.agents.runtime import Agent, AgentContext, AgentTask, AgentResult, AgentStatus
from src.agents.registry import AgentRegistry, AgentRegistration
from src.agents.workflow import Workflow, WorkflowEngine, WorkflowNode, WorkflowExecution, WorkflowStatus, NodeType
from src.agents.department import (
    DepartmentAgent,
    RDAgent,
    ProductAgent,
    OperationsAgent,
    SalesDeptAgent,
    HRAgent,
    CustomerServiceAgent,
)

# 向后兼容别名
SalesAgent = SalesDeptAgent

__all__ = [
    "Agent",
    "AgentContext",
    "AgentTask",
    "AgentResult",
    "AgentStatus",
    "AgentRegistry",
    "AgentRegistration",
    "Workflow",
    "WorkflowEngine",
    "WorkflowNode",
    "WorkflowExecution",
    "WorkflowStatus",
    "NodeType",
    "DepartmentAgent",
    "RDAgent",
    "ProductAgent",
    "OperationsAgent",
    "SalesAgent",
    "HRAgent",
    "CustomerServiceAgent",
]
