"""Simulation Runtime Service — Developer Agent 安全仿真。

不执行第三方代码、不联网、不读真实企业数据。
验证 install → permissions → runtime binding → adapter → scope 链路。
返回 deterministic mock simulated_output。

依赖注入：
- marketplace_store: MarketplaceAgent + TenantAgentInstallation 查询
- runtime_store: RuntimeAdapter + Binding + Eligibility 查询
- usage_store: usage event 记录（可选）
- metrics_store: 指标记录（可选，本阶段不强接）
"""

from __future__ import annotations

import logging
import time as _time
from datetime import datetime, timezone
from typing import Any

from src.agents.marketplace import PublisherType
from src.core.usage import UsageEvent, UsageResource, UsageUnit
from src.open_platform.runtime import (
    RuntimeAdapterType,
    RuntimeBindingStatus,
    RuntimeEligibilityCode,
)
from src.open_platform.simulation import (
    SimulationBlockReason,
    SimulationRunRequest,
    SimulationRunResult,
    SimulationRunStatus,
    SimulationStep,
)

logger = logging.getLogger(__name__)


class SimulationRuntimeService:
    """Developer Agent 安全仿真服务。

    不导入 AgentRuntime / AgentRegistry。
    不执行 package_url / entrypoint。
    不联网。
    """

    def __init__(
        self,
        marketplace_store: Any = None,
        runtime_store: Any = None,
        usage_store: Any = None,
        metrics_store: Any = None,
    ) -> None:
        self._marketplace_store = marketplace_store
        self._runtime_store = runtime_store
        self._usage_store = usage_store
        self._metrics_store = metrics_store

    def simulate_agent(
        self,
        request: SimulationRunRequest,
        principal: Any = None,  # DeveloperApiPrincipal | None
    ) -> SimulationRunResult:
        """运行 Developer Agent 安全仿真。

        流程：9 steps，任何一步 blocked 即终止。
        """
        t0 = _time.perf_counter()
        result = SimulationRunResult(
            marketplace_agent_id=request.marketplace_agent_id,
            tenant_id=request.tenant_id,
            developer_id=request.developer_id,
        )

        # ── Step 1: Validate marketplace agent ──
        step1 = self._step_validate_marketplace_agent(request, result)
        result.steps.append(step1)
        if step1.status == "blocked":
            return self._finalize(result, t0)

        # ── Step 2: Validate developer publisher ──
        step2 = self._step_validate_developer_publisher(request, result)
        result.steps.append(step2)
        if step2.status == "blocked":
            return self._finalize(result, t0)

        # ── Step 3: Validate runtime metadata ──
        step3 = self._step_validate_runtime_metadata(request, result)
        result.steps.append(step3)
        if step3.status == "blocked":
            return self._finalize(result, t0)

        # ── Step 4: Validate installation ──
        step4 = self._step_validate_installation(request, result)
        result.steps.append(step4)
        if step4.status == "blocked":
            return self._finalize(result, t0)

        # ── Step 5: Validate permissions ──
        step5 = self._step_validate_permissions(request, result)
        result.steps.append(step5)
        if step5.status == "blocked":
            return self._finalize(result, t0)

        # ── Step 6: Validate runtime binding ──
        step6 = self._step_validate_runtime_binding(request, result)
        result.steps.append(step6)
        if step6.status == "blocked":
            return self._finalize(result, t0)

        # ── Step 7: Validate adapter ──
        step7 = self._step_validate_adapter(request, result)
        result.steps.append(step7)
        if step7.status == "blocked":
            return self._finalize(result, t0)

        # ── Step 8: Validate API key scope ──
        step8 = self._step_validate_scope(request, result, principal)
        result.steps.append(step8)
        if step8.status == "blocked":
            return self._finalize(result, t0)

        # ── Step 9: Generate simulated response ──
        step9 = self._step_generate_simulated_response(request, result)
        result.steps.append(step9)

        # SUCCESS
        result.status = SimulationRunStatus.SUCCESS
        result.blocked_reason = None
        result.message = "Simulation completed successfully without executing external code."

        return self._finalize(result, t0)

    # ────────────────────────────────────────────
    # Steps
    # ────────────────────────────────────────────

    def _step_validate_marketplace_agent(
        self, req: SimulationRunRequest, result: SimulationRunResult,
    ) -> SimulationStep:
        t = _time.perf_counter()
        step = SimulationStep(name="validate_marketplace_agent")
        if self._marketplace_store is None:
            step.status = "blocked"
            step.message = "Marketplace store not available."
            self._block(result, SimulationBlockReason.MARKETPLACE_AGENT_NOT_FOUND, step.message)
        else:
            agent = self._marketplace_store.get_agent(req.marketplace_agent_id)
            if agent is None:
                step.status = "blocked"
                step.message = f"Marketplace agent '{req.marketplace_agent_id}' not found."
                self._block(result, SimulationBlockReason.MARKETPLACE_AGENT_NOT_FOUND, step.message)
            else:
                step.status = "passed"
                step.message = f"Marketplace agent '{req.marketplace_agent_id}' found."
                step.metadata["agent_name"] = getattr(agent, "display_name", "")
        step.duration_ms = (_time.perf_counter() - t) * 1000
        return step

    def _step_validate_developer_publisher(
        self, req: SimulationRunRequest, result: SimulationRunResult,
    ) -> SimulationStep:
        t = _time.perf_counter()
        step = SimulationStep(name="validate_developer_publisher")
        if self._marketplace_store is None:
            step.status = "passed"
            step.message = "Marketplace store not available; skipping publisher check."
            return step

        agent = self._marketplace_store.get_agent(req.marketplace_agent_id)
        if agent is None:
            step.status = "skipped"
            step.message = "Agent not found; already blocked."
            return step

        pub_type = getattr(agent, "publisher_type", "")
        if pub_type != PublisherType.DEVELOPER:
            step.status = "blocked"
            step.message = f"Agent publisher_type is '{pub_type}', not 'developer'."
            self._block(result, SimulationBlockReason.NOT_DEVELOPER_AGENT, step.message)
        else:
            step.status = "passed"
            step.message = "Agent is a developer agent."
        step.duration_ms = (_time.perf_counter() - t) * 1000
        return step

    def _step_validate_runtime_metadata(
        self, req: SimulationRunRequest, result: SimulationRunResult,
    ) -> SimulationStep:
        t = _time.perf_counter()
        step = SimulationStep(name="validate_runtime_metadata")
        # Check package_url not present or handled
        if self._marketplace_store:
            agent = self._marketplace_store.get_agent(req.marketplace_agent_id)
            if agent:
                meta = getattr(agent, "metadata", {}) or {}
                if meta.get("package_url_present"):
                    step.metadata["package_url_warning"] = (
                        "package_url is present in metadata but WILL NOT be executed."
                    )
                step.metadata["runtime_type"] = meta.get("runtime_type", "manifest_only")
                step.metadata["sandbox_level"] = meta.get("sandbox_level", "no_execution")
        step.status = "passed"
        step.message = "Runtime metadata validated. No code execution will occur."
        step.duration_ms = (_time.perf_counter() - t) * 1000
        return step

    def _step_validate_installation(
        self, req: SimulationRunRequest, result: SimulationRunResult,
    ) -> SimulationStep:
        t = _time.perf_counter()
        step = SimulationStep(name="validate_installation")
        if self._marketplace_store is None:
            step.status = "skipped"
            step.message = "Marketplace store not available."
            return step

        try:
            inst = self._marketplace_store.get_installation_by_agent(
                req.marketplace_agent_id, req.tenant_id, req.tenant_id,
            )
        except Exception:
            inst = None

        if inst is None:
            step.status = "blocked"
            step.message = "TenantAgentInstallation not found. Agent must be installed first."
            self._block(result, SimulationBlockReason.INSTALLATION_REQUIRED, step.message)
            return step

        if not getattr(inst, "enabled", False):
            step.status = "blocked"
            step.message = "Installation is not enabled."
            self._block(result, SimulationBlockReason.INSTALLATION_REQUIRED, step.message)
            return step

        inst_status = getattr(inst, "status", "")
        if inst_status not in ("active",):
            step.status = "blocked"
            step.message = f"Installation status is '{inst_status}', not 'active'."
            self._block(result, SimulationBlockReason.INSTALLATION_REQUIRED, step.message)
            return step

        step.status = "passed"
        step.message = "Installation is active and enabled."
        step.metadata["installation_id"] = getattr(inst, "installation_id", "")
        step.metadata["granted_permissions"] = getattr(inst, "permissions_granted", [])
        step.duration_ms = (_time.perf_counter() - t) * 1000
        return step

    def _step_validate_permissions(
        self, req: SimulationRunRequest, result: SimulationRunResult,
    ) -> SimulationStep:
        t = _time.perf_counter()
        step = SimulationStep(name="validate_permissions")
        # Get granted permissions from previous step
        granted = []
        for s in result.steps:
            if s.name == "validate_installation" and s.status == "passed":
                granted = s.metadata.get("granted_permissions", [])
                break

        if self._marketplace_store:
            agent = self._marketplace_store.get_agent(req.marketplace_agent_id)
            if agent:
                required = list(getattr(agent, "required_permissions", []))
                step.metadata["required_permissions"] = required
                step.metadata["granted_permissions"] = granted
                missing = [p for p in required if p not in granted]
                if missing:
                    step.status = "blocked"
                    step.message = f"Required permissions not granted: {missing}"
                    step.metadata["missing_permissions"] = missing
                    self._block(result, SimulationBlockReason.PERMISSIONS_REQUIRED, step.message)
                    step.duration_ms = (_time.perf_counter() - t) * 1000
                    return step

        step.status = "passed"
        step.message = "All required permissions are granted."
        step.duration_ms = (_time.perf_counter() - t) * 1000
        return step

    def _step_validate_runtime_binding(
        self, req: SimulationRunRequest, result: SimulationRunResult,
    ) -> SimulationStep:
        t = _time.perf_counter()
        step = SimulationStep(name="validate_runtime_binding")
        if self._runtime_store is None:
            step.status = "blocked"
            step.message = "Runtime store not available."
            self._block(result, SimulationBlockReason.RUNTIME_BINDING_REQUIRED, step.message)
            step.duration_ms = (_time.perf_counter() - t) * 1000
            return step

        eligibility = self._runtime_store.get_runtime_eligibility(
            req.marketplace_agent_id, req.tenant_id,
        )
        step.metadata["eligibility_code"] = eligibility.code
        step.metadata["eligibility_message"] = eligibility.message

        if not eligibility.eligible:
            code = eligibility.code
            if code == RuntimeEligibilityCode.NO_BINDING:
                self._block(result, SimulationBlockReason.RUNTIME_BINDING_REQUIRED, eligibility.message)
            elif code == RuntimeEligibilityCode.BINDING_DISABLED:
                self._block(result, SimulationBlockReason.RUNTIME_BINDING_DISABLED, eligibility.message)
            elif code == RuntimeEligibilityCode.ADAPTER_DISABLED:
                self._block(result, SimulationBlockReason.ADAPTER_NOT_AVAILABLE, eligibility.message)
            elif code == RuntimeEligibilityCode.ADAPTER_NOT_ALLOWED:
                self._block(result, SimulationBlockReason.ADAPTER_NOT_SIMULATION, eligibility.message)
            else:
                self._block(result, SimulationBlockReason.RUNTIME_BINDING_REQUIRED, eligibility.message)
            step.status = "blocked"
            step.message = eligibility.message
        else:
            step.status = "passed"
            step.message = eligibility.message
            result.binding_id = eligibility.binding_id
            result.adapter_id = eligibility.adapter_id

        step.duration_ms = (_time.perf_counter() - t) * 1000
        return step

    def _step_validate_adapter(
        self, req: SimulationRunRequest, result: SimulationRunResult,
    ) -> SimulationStep:
        t = _time.perf_counter()
        step = SimulationStep(name="validate_adapter")
        if self._runtime_store is None or result.adapter_id is None:
            step.status = "skipped"
            step.message = "No adapter to validate."
            step.duration_ms = (_time.perf_counter() - t) * 1000
            return step

        adapter = self._runtime_store.get_adapter(result.adapter_id)
        if adapter is None:
            step.status = "blocked"
            step.message = "Runtime adapter not found."
            self._block(result, SimulationBlockReason.ADAPTER_NOT_AVAILABLE, step.message)
            step.duration_ms = (_time.perf_counter() - t) * 1000
            return step

        if adapter.adapter_type != RuntimeAdapterType.SIMULATION:
            step.status = "blocked"
            step.message = (
                f"Adapter type is '{adapter.adapter_type}', "
                f"only '{RuntimeAdapterType.SIMULATION}' is supported for simulation."
            )
            self._block(result, SimulationBlockReason.ADAPTER_NOT_SIMULATION, step.message)
            step.duration_ms = (_time.perf_counter() - t) * 1000
            return step

        if not adapter.is_active():
            step.status = "blocked"
            step.message = f"Adapter status is '{adapter.status}'."
            self._block(result, SimulationBlockReason.ADAPTER_NOT_AVAILABLE, step.message)
            step.duration_ms = (_time.perf_counter() - t) * 1000
            return step

        step.status = "passed"
        step.message = f"Simulation adapter '{adapter.name}' is active."
        step.duration_ms = (_time.perf_counter() - t) * 1000
        return step

    def _step_validate_scope(
        self, req: SimulationRunRequest, result: SimulationRunResult,
        principal: Any = None,
    ) -> SimulationStep:
        t = _time.perf_counter()
        step = SimulationStep(name="validate_scope")
        # JWT → allow (scope check not applicable)
        if req.auth_type == "jwt":
            step.status = "passed"
            step.message = "JWT auth — scope check not applicable."
            step.duration_ms = (_time.perf_counter() - t) * 1000
            return step

        # API Key → must have simulation scope
        scopes = req.api_key_scopes
        if not scopes:
            if principal and hasattr(principal, "scopes"):
                scopes = principal.scopes

        allowed_sim_scopes = {"agent:simulate", "agent:execute:simulation"}
        has_sim_scope = bool(set(scopes) & allowed_sim_scopes)

        if not has_sim_scope:
            step.status = "blocked"
            step.message = (
                "API Key does not have agent:simulate or agent:execute:simulation scope."
            )
            step.metadata["required_scopes"] = list(allowed_sim_scopes)
            self._block(result, SimulationBlockReason.INSUFFICIENT_API_KEY_SCOPE, step.message)
        else:
            step.status = "passed"
            step.message = "API Key has required simulation scope."

        step.duration_ms = (_time.perf_counter() - t) * 1000
        return step

    def _step_generate_simulated_response(
        self, req: SimulationRunRequest, result: SimulationRunResult,
    ) -> SimulationStep:
        t = _time.perf_counter()
        step = SimulationStep(name="generate_simulated_response")

        agent_name = ""
        agent_caps: list[str] = []
        agent_perms: list[str] = []
        if self._marketplace_store:
            agent = self._marketplace_store.get_agent(req.marketplace_agent_id)
            if agent:
                agent_name = getattr(agent, "display_name", "")
                agent_caps = list(getattr(agent, "capabilities", []))
                agent_perms = list(getattr(agent, "required_permissions", []))

        result.simulated_output = {
            "mode": "simulation",
            "agent_name": agent_name,
            "agent_id": req.marketplace_agent_id,
            "input_preview": (req.input_text or "")[:200],
            "capabilities_checked": agent_caps,
            "permissions_checked": agent_perms,
            "permissions_granted": True,
            "message": (
                "Simulation completed without executing external code. "
                "No package_url was downloaded or executed. "
                "No network calls were made. "
                "No real enterprise data was accessed. "
                "This is a deterministic mock response."
            ),
            "no_remote_code_execution": True,
        }

        step.status = "passed"
        step.message = "Simulated response generated (deterministic mock)."
        step.duration_ms = (_time.perf_counter() - t) * 1000
        return step

    # ────────────────────────────────────────────
    # Helpers
    # ────────────────────────────────────────────

    def _block(self, result: SimulationRunResult, reason: str, message: str) -> None:
        result.status = SimulationRunStatus.BLOCKED
        result.blocked_reason = reason
        result.message = message

    def _finalize(
        self, result: SimulationRunResult, t0: float,
    ) -> SimulationRunResult:
        result.completed_at = datetime.now(timezone.utc)
        result.duration_ms = round((_time.perf_counter() - t0) * 1000, 1)

        # Record usage (best-effort for success; blocked also recorded with status)
        self._try_record_usage(result)

        return result

    def _try_record_usage(self, result: SimulationRunResult) -> None:
        if self._usage_store is None:
            return
        try:
            self._usage_store.record_event(UsageEvent(
                tenant_id=result.tenant_id,
                user_id=result.developer_id or "",
                workspace_id=result.tenant_id,
                resource=UsageResource.AGENT_SIMULATION_RUN,
                quantity=1,
                unit=UsageUnit.COUNT,
                metadata={
                    "run_id": result.run_id,
                    "marketplace_agent_id": result.marketplace_agent_id,
                    "developer_id": result.developer_id,
                    "tenant_id": result.tenant_id,
                    "adapter_id": result.adapter_id,
                    "binding_id": result.binding_id,
                    "simulation_status": result.status,
                    "blocked_reason": result.blocked_reason,
                    "duration_ms": result.duration_ms,
                    "simulation_only": True,
                    "no_remote_code_execution": True,
                },
            ))
            result.usage_recorded = True
        except Exception:
            logger.warning("simulation_usage_record_failed", exc_info=True,
                          extra={"run_id": result.run_id})
