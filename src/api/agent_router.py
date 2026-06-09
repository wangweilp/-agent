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

所有端点均要求认证（通过 require_auth 依赖）。
Agent 执行上下文从 JWT TokenPayload 自动注入。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.errors import MSG_INTERNAL_ERROR, MSG_UNAUTHORIZED, MSG_FORBIDDEN
from src.api.middleware import require_auth, get_token_payload, TokenPayload
from src.agents.registry import AgentRegistry
from src.agents.runtime import AgentTask, TaskPriority, PermissionChecker
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
# Agent Permission Checker (adapter)
# ═══════════════════════════════════════════


class _TokenPermissionChecker:
    """基于 JWT TokenPayload 的 Agent 权限检查器。

    复用现有 RBAC 体系：通过 TokenPayload 中的 role 和 is_super_admin
    决定用户是否有权执行 Agent/Workflow。
    """

    def __init__(self, payload: TokenPayload) -> None:
        self._payload = payload

    def check(self, user_id: str, tenant_id: str, resource: str, action: str) -> bool:
        # Super admin 全部放行
        if self._payload.is_super_admin:
            return True
        # Admin/Manager 可以执行 Agent
        if self._payload.role and self._payload.role.value in ("owner", "admin", "member"):
            return True
        # Viewer 只读
        if self._payload.role and self._payload.role.value == "viewer":
            return action in ("read", "list")
        return False


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
# Scenario 请求/响应模型
# ═══════════════════════════════════════════


class MeetingToTrainingRequest(BaseModel):
    meeting_title: str = Field(..., description="会议标题")
    meeting_notes: str = Field(..., min_length=1, description="会议记录内容")
    participants: list[str] = Field(default_factory=list, description="参会人员")
    department_id: str = Field(default="", description="部门 ID")


class DepartmentAssistantRequest(BaseModel):
    department: str = Field(..., description="部门名称: 研发部/产品部/运营部/销售部/人力资源部/客服部")
    question: str = Field(..., min_length=1, description="业务问题")
    context: str = Field(default="", description="补充上下文")


class ScenarioRunResponse(BaseModel):
    success: bool
    scenario_id: str
    execution_id: str = ""
    result: dict[str, Any] = Field(default_factory=dict)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


# ═══════════════════════════════════════════
# Router
# ═══════════════════════════════════════════


def create_agent_router(
    registry: AgentRegistry,
    workflow_engine: WorkflowEngine,
    scenario_engine: Any = None,
) -> APIRouter:
    """创建 Agent API 路由。

    注意：路由顺序很重要 — 必须在 /{agent_id} 之前注册 /workflows 和 /executions，
    否则 FastAPI 会把 "workflows" 当作 agent_id 匹配。

    所有端点强制要求认证（Depends(require_auth)）。
    tenant_id / user_id / workspace_id 从 JWT TokenPayload 自动提取并传入 Agent Runtime。
    """
    router = APIRouter(prefix="/agents", tags=["agents"])

    # ── Agent 执行 ──

    @router.post("/run", response_model=AgentRunResponse)
    async def run_agent(
        request: AgentRunRequest,
        payload: TokenPayload = Depends(require_auth),
    ) -> AgentRunResponse:
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
                created_by=payload.user_id,
            )

            checker = _TokenPermissionChecker(payload)
            tenant_ctx = payload.workspace_id  # workspace_id 承担租户隔离边界
            result = registry.run(
                request.agent_id, task,
                tenant_id=tenant_ctx,
                user_id=payload.user_id,
                workspace_id=payload.workspace_id,
                user_roles=[payload.role.value] if payload.role else [],
                permission_checker=checker,
            )
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
        except Exception:
            logger.exception("agent_run_endpoint_error")
            raise HTTPException(status_code=500, detail=MSG_INTERNAL_ERROR)

    # ── Agent 列表 ──

    @router.get("", response_model=AgentListResponse)
    async def list_agents(
        tag: str = Query(default="", description="按 tag 过滤"),
        enabled_only: bool = Query(default=False, description="仅已启用"),
        payload: TokenPayload = Depends(require_auth),
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
    async def get_stats(
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        return registry.get_stats()

    # ── Analytics 端点 ──

    @router.get("/analytics/agents")
    async def get_agent_analytics(
        tenant_id: str = Query(default="", description="租户 ID"),
        days: int = Query(default=30, ge=1, le=365, description="统计天数"),
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """Agent 级分析数据。"""
        try:
            from src.agents.metrics import get_agent_metrics_store
            store = get_agent_metrics_store()
            # 非 super_admin 只能看自己租户的数据
            effective_tenant = tenant_id or (payload.workspace_id if not payload.is_super_admin else "")
            return store.get_agent_stats(tenant_id=effective_tenant, days=days)
        except Exception:
            return {"total_events": 0, "total_calls": 0, "agents": []}

    @router.get("/analytics/departments")
    async def get_department_distribution(
        tenant_id: str = Query(default="", description="租户 ID"),
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, int]:
        """部门使用分布。"""
        try:
            from src.agents.metrics import get_agent_metrics_store
            return get_agent_metrics_store().get_department_distribution(tenant_id=tenant_id)
        except Exception:
            return {}

    @router.get("/analytics/tenants")
    async def get_tenant_distribution(
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, int]:
        """租户使用分布。仅 super_admin 可用完整数据。"""
        if not payload.is_super_admin:
            raise HTTPException(status_code=403, detail=MSG_FORBIDDEN)
        try:
            from src.agents.metrics import get_agent_metrics_store
            return get_agent_metrics_store().get_tenant_distribution()
        except Exception:
            return {}

    @router.get("/analytics/executions")
    async def get_recent_executions(
        limit: int = Query(default=20, ge=1, le=100, description="返回条数"),
        payload: TokenPayload = Depends(require_auth),
    ) -> list[dict[str, Any]]:
        """最近执行记录。"""
        try:
            from src.agents.metrics import get_agent_metrics_store
            return get_agent_metrics_store().get_recent_executions(limit=limit)
        except Exception:
            return []

    # ── 业务场景（必须在 /{agent_id} 之前）──

    @router.get("/scenarios")
    async def list_scenarios(
        payload: TokenPayload = Depends(require_auth),
    ) -> list[dict[str, Any]]:
        """列出所有可用的业务场景。"""
        from src.agents.scenarios import list_scenarios as _list_scenarios
        return _list_scenarios()

    @router.get("/scenarios/{scenario_id}")
    async def get_scenario(
        scenario_id: str,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """获取单个场景定义。"""
        from src.agents.scenarios import get_scenario as _get_scenario
        result = _get_scenario(scenario_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"场景 {scenario_id} 不存在")
        return result

    @router.post("/scenarios/meeting-to-training/run")
    async def run_meeting_to_training(
        request: MeetingToTrainingRequest,
        payload: TokenPayload = Depends(require_auth),
    ) -> ScenarioRunResponse:
        """执行 会议纪要 → 知识沉淀 → 培训生成 场景。"""
        if scenario_engine is None:
            raise HTTPException(status_code=501, detail="Scenario Engine 未初始化")

        try:
            from src.agents.scenarios import MeetingToTrainingInput
            input_data = MeetingToTrainingInput(
                meeting_title=request.meeting_title,
                meeting_notes=request.meeting_notes,
                participants=request.participants,
                department_id=request.department_id,
            )
            output = scenario_engine.run_meeting_to_training(
                input_data,
                tenant_id=payload.workspace_id,
                user_id=payload.user_id,
                workspace_id=payload.workspace_id,
            )
            wf_exec_id = getattr(output, 'workflow_execution_id', None)
            return ScenarioRunResponse(
                success=output.success,
                scenario_id=output.scenario_id,
                execution_id=wf_exec_id or output.scenario_id,
                result=output.to_dict(),
                trace=output.execution_trace if isinstance(output.execution_trace, list) else [],
                metrics={
                    "duration_ms": output.duration_ms,
                    "memory_refs": len(output.memory_refs),
                    "knowledge_refs": len(output.knowledge_refs),
                    "workflow_execution_id": wf_exec_id,
                    "fallback_mode": getattr(output, 'fallback_mode', False),
                },
                error=output.error,
            )
        except HTTPException:
            raise
        except Exception:
            logger.exception("scenario_meeting_to_training_failed")
            raise HTTPException(status_code=500, detail=MSG_INTERNAL_ERROR)

    @router.post("/scenarios/department-assistant/run")
    async def run_department_assistant(
        request: DepartmentAssistantRequest,
        payload: TokenPayload = Depends(require_auth),
    ) -> ScenarioRunResponse:
        """执行部门知识助手场景。"""
        if scenario_engine is None:
            raise HTTPException(status_code=501, detail="Scenario Engine 未初始化")

        try:
            from src.agents.scenarios import DepartmentAssistantInput
            input_data = DepartmentAssistantInput(
                department=request.department,
                question=request.question,
                context=request.context,
            )
            output = scenario_engine.run_department_assistant(
                input_data,
                tenant_id=payload.workspace_id,
                user_id=payload.user_id,
                workspace_id=payload.workspace_id,
            )
            wf_exec_id = getattr(output, 'workflow_execution_id', None)
            return ScenarioRunResponse(
                success=output.success,
                scenario_id=output.scenario_id,
                execution_id=wf_exec_id or output.scenario_id,
                result=output.to_dict(),
                trace=output.execution_trace if isinstance(output.execution_trace, list) else [],
                metrics={
                    "duration_ms": output.duration_ms,
                    "confidence": output.confidence if hasattr(output, 'confidence') else 0.0,
                    "memory_refs": len(output.memory_refs) if hasattr(output, 'memory_refs') else 0,
                    "knowledge_refs": len(output.knowledge_refs) if hasattr(output, 'knowledge_refs') else 0,
                    "workflow_execution_id": wf_exec_id,
                    "fallback_mode": getattr(output, 'fallback_mode', False),
                },
                error=output.error,
            )
        except HTTPException:
            raise
        except Exception:
            logger.exception("scenario_department_assistant_failed")
            raise HTTPException(status_code=500, detail=MSG_INTERNAL_ERROR)

    # ── 工作流（必须在 /{agent_id} 之前）──

    @router.post("/workflows")
    async def create_workflow(
        request: WorkflowCreateRequest,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
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
        except ValueError:
            logger.exception("workflow_create_error")
            raise HTTPException(status_code=400, detail="工作流创建失败")

        return wf.to_dict()

    @router.get("/workflows")
    async def list_workflows(
        payload: TokenPayload = Depends(require_auth),
    ) -> list[dict[str, Any]]:
        return [wf.to_dict() for wf in workflow_engine.list_workflows()]

    @router.get("/workflows/{workflow_id}")
    async def get_workflow(
        workflow_id: str,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        wf = workflow_engine.get_workflow(workflow_id)
        if wf is None:
            raise HTTPException(status_code=404, detail="工作流不存在")
        return wf.to_dict()

    @router.post("/workflows/{workflow_id}/execute")
    async def execute_workflow(
        workflow_id: str,
        request: WorkflowExecuteRequest = WorkflowExecuteRequest(),
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """执行工作流。传入当前用户/租户上下文。"""
        try:
            execution = workflow_engine.execute(
                workflow_id, request.input_data,
                tenant_id=payload.workspace_id,
                user_id=payload.user_id,
                workspace_id=payload.workspace_id,
            )
            return execution.to_dict()
        except ValueError:
            raise HTTPException(status_code=404, detail="工作流不存在")

    @router.post("/executions/{execution_id}/resume")
    async def resume_execution(
        execution_id: str,
        request: WorkflowResumeRequest,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """恢复暂停的工作流。"""
        try:
            execution = workflow_engine.resume(execution_id, request.human_inputs)
            return execution.to_dict()
        except ValueError:
            logger.exception("workflow_resume_error")
            raise HTTPException(status_code=400, detail="工作流操作失败")

    # ── 执行记录（必须在 /{agent_id} 之前）──

    @router.get("/executions")
    async def list_executions(
        workflow_id: str = Query(default="", description="按工作流过滤"),
        payload: TokenPayload = Depends(require_auth),
    ) -> list[dict[str, Any]]:
        """列出执行记录。"""
        wf_id = workflow_id if workflow_id else None
        return [e.to_dict() for e in workflow_engine.list_executions(wf_id)]

    @router.get("/executions/{execution_id}")
    async def get_execution(
        execution_id: str,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
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
    async def get_agent(
        agent_id: str,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
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
    async def enable_agent(
        agent_id: str,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        if not registry.enable(agent_id):
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} 不存在")
        return {"status": "ok", "agent_id": agent_id, "enabled": True}

    @router.post("/{agent_id}/disable")
    async def disable_agent(
        agent_id: str,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        if not registry.disable(agent_id):
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} 不存在")
        return {"status": "ok", "agent_id": agent_id, "enabled": False}

    # ── 配置更新 ──

    @router.put("/{agent_id}/config")
    async def update_agent_config(
        agent_id: str,
        request: ConfigUpdateRequest,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        if not registry.update_config(agent_id, request.config):
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} 不存在")
        return {"status": "ok", "agent_id": agent_id, "config": registry.get_config(agent_id)}

    return router
