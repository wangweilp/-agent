"""Enterprise Agent API — /agents 端点。

端点：
- POST /agents/run     — 执行 Agent 任务
- GET  /agents         — 列出所有注册 Agent
- GET  /agents/{id}    — 获取 Agent 详情
- POST /agents/{id}/enable  — 启用
- POST /agents/{id}/disable — 停用
- PUT  /agents/{id}/config  — 更新配置
- POST /workflows      — 创建工作流
- GET  /workflows      — 列出工作流
- GET  /workflows/{id} — 获取工作流详情
- POST /workflows/{id}/execute — 执行工作流
- GET  /executions     — 列出执行记录
- GET  /executions/{id} — 获取执行详情
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.errors import MSG_INTERNAL_ERROR
from src.agents.registry import AgentRegistry
from src.agents.runtime import AgentTask, TaskPriority
from src.agents.workflow import (
    NodeType,
    Workflow,
    WorkflowEngine,
    WorkflowNode,
    WorkflowStatus,
    create_meeting_to_training_workflow,
    create_research_to_report_workflow,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# 请求 / 响应模型
# ═══════════════════════════════════════════


class AgentRunRequest(BaseModel):
    agent_id: str = Field(..., description="Agent ID")
    title: str = Field(default="", description="任务标题")
    description: str = Field(default="", description="任务描述")
    input_data: dict[str, Any] = Field(default_factory=dict, description="任务输入")
    priority: str = Field(default="medium", description="优先级: low/medium/high/critical")


class AgentRunResponse(BaseModel):
    task_id: str
    agent_id: str
    agent_name: str
    success: bool
    output: str
    error: str | None = None
    plan: list[str] = []
    observations: list[str] = []
    reflections: list[str] = []
    tool_calls_count: int = 0
    memory_calls_count: int = 0
    kg_calls_count: int = 0
    duration_ms: float = 0.0


class AgentSummary(BaseModel):
    agent_id: str
    name: str
    description: str
    version: str
    enabled: bool
    tags: list[str] = []
    usage_count: int = 0
    success_rate: float = 1.0
    avg_duration_ms: float = 0.0


class AgentListResponse(BaseModel):
    total: int
    enabled: int
    agents: list[AgentSummary]


class ConfigUpdateRequest(BaseModel):
    config: dict[str, Any] = Field(..., description="配置键值对")


class WorkflowCreateRequest(BaseModel):
    name: str = Field(..., description="工作流名称")
    description: str = Field(default="", description="工作流描述")
    nodes: list[dict[str, Any]] = Field(default_factory=list, description="节点列表")
    start_node_id: str = Field(default="", description="起始节点 ID")
    tags: list[str] = Field(default_factory=list)


class WorkflowExecuteRequest(BaseModel):
    input_data: dict[str, Any] = Field(default_factory=dict)


class WorkflowResumeRequest(BaseModel):
    human_inputs: dict[str, str] = Field(default_factory=dict, description="人工输入: node_id → input")


# ═══════════════════════════════════════════
# Router
# ═══════════════════════════════════════════


def create_agent_router(
    registry: AgentRegistry,
    workflow_engine: WorkflowEngine,
) -> APIRouter:
    """创建 Agent API 路由。

    注意：路由顺序很重要 — 必须在 /{agent_id} 之前注册 /workflows 和 /executions，
    否则 FastAPI 会把 "workflows" 当作 agent_id 匹配。
    """
    router = APIRouter(prefix="/agents", tags=["agents"])

    # ── Agent 执行 ──

    @router.post("/run", response_model=AgentRunResponse)
    async def run_agent(request: AgentRunRequest) -> AgentRunResponse:
        """执行 Agent 任务。"""
        try:
            priority_map = {
                "low": TaskPriority.LOW,
                "medium": TaskPriority.MEDIUM,
                "high": TaskPriority.HIGH,
                "critical": TaskPriority.CRITICAL,
            }
            task = AgentTask(
                title=request.title,
                description=request.description,
                input_data=request.input_data,
                priority=priority_map.get(request.priority, TaskPriority.MEDIUM),
            )

            result = registry.run(request.agent_id, task)
            if result is None:
                raise HTTPException(status_code=404, detail=f"Agent {request.agent_id} 不存在或已停用")

            return AgentRunResponse(
                task_id=result.task_id,
                agent_id=result.agent_id,
                agent_name=result.agent_name,
                success=result.success,
                output=result.output,
                error=result.error,
                plan=result.plan,
                observations=result.observations,
                reflections=result.reflections,
                tool_calls_count=result.tool_calls_count,
                memory_calls_count=result.memory_calls_count,
                kg_calls_count=result.kg_calls_count,
                duration_ms=result.duration_ms,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("agent_run_endpoint_error")
            logger.exception("agent_endpoint_error"); raise HTTPException(status_code=500, detail=MSG_INTERNAL_ERROR)

    # ── Agent 列表 ──

    @router.get("", response_model=AgentListResponse)
    async def list_agents(
        tag: str = Query(default="", description="按 tag 过滤"),
        enabled_only: bool = Query(default=False, description="仅已启用"),
    ) -> AgentListResponse:
        """列出所有注册 Agent。"""
        if tag:
            registrations = registry.list_by_tag(tag)
        elif enabled_only:
            registrations = registry.list_enabled()
        else:
            registrations = registry.list_all()

        agents = [
            AgentSummary(
                agent_id=r.agent_id,
                name=r.name,
                description=r.description,
                version=r.version,
                enabled=r.enabled,
                tags=r.tags,
                usage_count=r.usage_count,
                success_rate=round(r.success_rate, 4),
                avg_duration_ms=round(r.avg_duration_ms, 1),
            )
            for r in registrations
        ]
        return AgentListResponse(
            total=len(agents),
            enabled=sum(1 for a in agents if a.enabled),
            agents=agents,
        )

    # ── 统计（必须在 /{agent_id} 之前）──

    @router.get("/stats/overview")
    async def get_stats() -> dict[str, Any]:
        return registry.get_stats()

    # ── 工作流（必须在 /{agent_id} 之前）──

    @router.post("/workflows")
    async def create_workflow(request: WorkflowCreateRequest) -> dict[str, Any]:
        """创建/注册工作流。"""
        wf = Workflow(name=request.name, description=request.description, tags=request.tags)
        for node_data in request.nodes:
            node = WorkflowNode(
                name=node_data.get("name", ""),
                node_type=NodeType(node_data.get("node_type", "agent")),
                agent_id=node_data.get("agent_id", ""),
                description=node_data.get("description", ""),
            )
            wf.add_node(node)
            if node_data.get("is_start"):
                wf.set_start(node.node_id)
        if request.start_node_id:
            wf.set_start(request.start_node_id)

        try:
            workflow_engine.register_workflow(wf)
        except ValueError as e:
            logger.exception("workflow_endpoint_error"); raise HTTPException(status_code=400, detail="工作流操作失败")

        return wf.to_dict()

    @router.get("/workflows")
    async def list_workflows() -> list[dict[str, Any]]:
        return [wf.to_dict() for wf in workflow_engine.list_workflows()]

    @router.get("/workflows/{workflow_id}")
    async def get_workflow(workflow_id: str) -> dict[str, Any]:
        wf = workflow_engine.get_workflow(workflow_id)
        if wf is None:
            raise HTTPException(status_code=404, detail="工作流不存在")
        return wf.to_dict()

    @router.post("/workflows/{workflow_id}/execute")
    async def execute_workflow(workflow_id: str, request: WorkflowExecuteRequest = WorkflowExecuteRequest()) -> dict[str, Any]:
        """执行工作流。"""
        try:
            execution = workflow_engine.execute(workflow_id, request.input_data)
            return execution.to_dict()
        except ValueError:
            raise HTTPException(status_code=404, detail="工作流不存在")

    @router.post("/executions/{execution_id}/resume")
    async def resume_execution(execution_id: str, request: WorkflowResumeRequest) -> dict[str, Any]:
        """恢复暂停的工作流。"""
        try:
            execution = workflow_engine.resume(execution_id, request.human_inputs)
            return execution.to_dict()
        except ValueError as e:
            logger.exception("workflow_endpoint_error"); raise HTTPException(status_code=400, detail="工作流操作失败")

    # ── 执行记录（必须在 /{agent_id} 之前）──

    @router.get("/executions")
    async def list_executions(
        workflow_id: str = Query(default="", description="按工作流过滤"),
    ) -> list[dict[str, Any]]:
        """列出执行记录。"""
        wf_id = workflow_id if workflow_id else None
        return [e.to_dict() for e in workflow_engine.list_executions(wf_id)]

    @router.get("/executions/{execution_id}")
    async def get_execution(execution_id: str) -> dict[str, Any]:
        """获取执行详情。"""
        execution = workflow_engine.get_execution(execution_id)
        if execution is None:
            raise HTTPException(status_code=404, detail="执行记录不存在")
        return execution.to_dict()

    # ═══════════════════════════════════════════
    # 以下路由带 {agent_id} 参数，必须放在最后
    # ═══════════════════════════════════════════

    # ── Agent 详情 ──

    @router.get("/{agent_id}")
    async def get_agent(agent_id: str) -> dict[str, Any]:
        """获取 Agent 详情。"""
        reg = registry.get_registration(agent_id)
        if reg is None:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} 不存在")
        agent = registry.get(agent_id)
        return {
            **reg.to_dict(),
            "status": agent.status.value if agent else "unknown",
            "metrics": agent.metrics if agent else {},
        }

    # ── 启用/停用 ──

    @router.post("/{agent_id}/enable")
    async def enable_agent(agent_id: str) -> dict[str, Any]:
        if not registry.enable(agent_id):
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} 不存在")
        return {"status": "ok", "agent_id": agent_id, "enabled": True}

    @router.post("/{agent_id}/disable")
    async def disable_agent(agent_id: str) -> dict[str, Any]:
        if not registry.disable(agent_id):
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} 不存在")
        return {"status": "ok", "agent_id": agent_id, "enabled": False}

    # ── 配置更新 ──

    @router.put("/{agent_id}/config")
    async def update_agent_config(agent_id: str, request: ConfigUpdateRequest) -> dict[str, Any]:
        if not registry.update_config(agent_id, request.config):
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} 不存在")
        return {"status": "ok", "agent_id": agent_id, "config": registry.get_config(agent_id)}

    return router
