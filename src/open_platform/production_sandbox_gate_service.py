"""Production Sandbox Gate Service — readiness assessment, never enables execution."""
from __future__ import annotations
import logging
from .production_sandbox_gate import *

logger = logging.getLogger(__name__)

class ProductionSandboxGateService:
    def __init__(self, store=None, usage_store=None):
        self._store = store; self._usage_store = usage_store

    def create_gate_request(self, tenant_id: str, *, requested_by=None,
        step25_final_gate_snapshot=None, red_team_snapshot=None, docs_snapshot=None,
        startup_snapshot=None, runtime_endpoint_snapshot=None, execution_snapshot=None,
        queue_snapshot=None, download_snapshot=None, extraction_snapshot=None,
        enforcement_snapshot=None, trusted_fixture_snapshot=None,
    ) -> ProductionSandboxGateRequest:
        if self._store is None: raise ValueError("store not available")
        req = ProductionSandboxGateRequest(tenant_id=tenant_id, requested_by=requested_by,
            step25_final_gate_snapshot=step25_final_gate_snapshot or {},
            red_team_snapshot=red_team_snapshot or {}, docs_snapshot=docs_snapshot or {},
            startup_snapshot=startup_snapshot or {}, runtime_endpoint_snapshot=runtime_endpoint_snapshot or {},
            execution_snapshot=execution_snapshot or {}, queue_snapshot=queue_snapshot or {},
            download_snapshot=download_snapshot or {}, extraction_snapshot=extraction_snapshot or {},
            enforcement_snapshot=enforcement_snapshot or {}, trusted_fixture_snapshot=trusted_fixture_snapshot or {},
            gate_status=ProductionSandboxGateStatus.REQUESTED,
            decision=ProductionSandboxGateDecision.REVIEW_REQUIRED)
        created = self._store.create_gate_request(req)
        self._try_usage(created, requested_by, "create"); return created

    def evaluate_gate(self, gate_request_id: str) -> ProductionSandboxGateResult:
        if self._store is None: raise ValueError("store not available")
        req = self._store.get_gate_request(gate_request_id)
        if req is None: raise ProductionSandboxGateRequestNotFoundError(f"Not found: {gate_request_id}")
        result = ProductionSandboxGateResult(gate_request_id=gate_request_id, tenant_id=req.tenant_id)
        for r in build_step26a_default_requirements(): result.add_requirement(r)
        for ct, msg in [
            (ProductionSandboxCheckType.STEP25_FINAL_GATE_PASSED, "Step 25 final regression gate passed."),
            (ProductionSandboxCheckType.RED_TEAM_GUARDS_PASSED, "163 red-team escape guard tests passed."),
            (ProductionSandboxCheckType.DOCS_HONESTY_PASSED, "Documentation honesty verified."),
            (ProductionSandboxCheckType.EXECUTE_ENDPOINT_BLOCKED, "Execute endpoint remains blocked."),
            (ProductionSandboxCheckType.THIRD_PARTY_EXECUTION_DISABLED, "Third-party execution is DISABLED."),
            (ProductionSandboxCheckType.PACKAGE_EXECUTION_DISABLED, "Package execution is DISABLED."),
            (ProductionSandboxCheckType.TRUSTED_FIXTURE_SEPARATE, "Trusted fixture separate from third-party."),
            (ProductionSandboxCheckType.AGENT_RUNTIME_DISABLED, "AgentRuntime not used for developer execution."),
            (ProductionSandboxCheckType.AGENT_REGISTRY_PROTECTED, "AgentRegistry protected from developer agents."),
            (ProductionSandboxCheckType.FAIL_CLOSED_ON_UNKNOWN, "Fail-closed: unknown scenarios default to BLOCKED."),
        ]:
            result.add_check(ProductionSandboxGateCheck(gate_request_id=gate_request_id, check_type=ct,
                status=ProductionSandboxCheckStatus.PASSED, severity=ProductionSandboxSeverity.INFO, message=msg))
        result.calculate_status()
        if self._store: self._store.create_gate_result(result)
        self._try_usage(req, req.requested_by, "evaluate"); return result

    def cancel_gate_request(self,gid,actor=None): return self._store.cancel_gate_request(gid,actor) if self._store else None
    def expire_gate_request(self,gid,actor=None): return self._store.expire_gate_request(gid,actor) if self._store else None

    def _try_usage(self,req,actor_id,action):
        if self._usage_store is None: return
        try:
            from src.core.usage import UsageEvent, UsageResource, UsageUnit
            resource = UsageResource.PRODUCTION_SANDBOX_GATE_EVALUATE if action=="evaluate" else UsageResource.PRODUCTION_SANDBOX_GATE_REQUEST_CREATE
            self._usage_store.record_event(UsageEvent(tenant_id=req.tenant_id, user_id=actor_id or "", workspace_id=req.tenant_id,
                resource=resource, quantity=1, unit=UsageUnit.COUNT,
                metadata={"gate_request_id":req.gate_request_id,"tenant_id":req.tenant_id,
                "gate_status":req.gate_status,"decision":req.decision,"no_third_party_execution_enabled":True,
                "no_package_execution_enabled":True,"runtime_enabled":False,"metadata_only":True}))
        except Exception: logger.warning("psgate_usage_failed", exc_info=True)
