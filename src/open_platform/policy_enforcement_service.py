"""Policy Enforcement Service — metadata-only, no execution. All decisions = deny."""
from __future__ import annotations
import logging
from .policy_enforcement import *

logger = logging.getLogger(__name__)


class PolicyEnforcementService:
    def __init__(self, store=None, usage_store=None):
        self._store = store; self._usage_store = usage_store

    def evaluate(self, request_type, capability_name="", tenant_id=None, actor_id=None) -> PolicyDecision:
        if self._store is None: raise ValueError("store not available")
        req = PermissionRequest(request_type=request_type, capability_name=capability_name,
                                tenant_id=tenant_id, actor_id=actor_id)
        engine = PolicyEnforcementEngine()
        decision = engine.evaluate(req)
        created = self._store.create_decision(decision)
        self._try_usage(created, "evaluate")
        return created

    def evaluate_all(self) -> list[PolicyDecision]:
        if self._store is None: raise ValueError("store not available")
        engine = PolicyEnforcementEngine()
        decisions = engine.evaluate_all()
        saved = []
        for d in decisions: saved.append(self._store.create_decision(d))
        return saved

    def get_decision(self, decision_id):
        if self._store is None: raise ValueError("store not available")
        d = self._store.get_decision(decision_id)
        if d is None: raise PolicyDecisionNotFoundError(f"Not found: {decision_id}")
        return d

    def list_decisions(self, *, request_type=""):
        if self._store is None: raise ValueError("store not available")
        return self._store.list_decisions(request_type=request_type)

    def export_decisions(self):
        if self._store is None: raise ValueError("store not available")
        return self._store.export_decisions()

    def run_audit(self) -> dict[str, Any]:
        agent = PolicyEnforcementAuditSubAgent()
        return agent.run_audit()

    def _try_usage(self, dec, action):
        if self._usage_store is None: return
        try:
            from src.core.usage import UsageEvent, UsageResource, UsageUnit
            self._usage_store.record_event(UsageEvent(
                tenant_id=dec.tenant_id or "", user_id="system", workspace_id=dec.tenant_id or "",
                resource=UsageResource.POLICY_ENFORCEMENT_DECISION, quantity=1, unit=UsageUnit.COUNT,
                metadata={"action": action, "allowed": dec.allowed, "execution_allowed": False,
                          "runtime_enabled": False, "metadata_only": True}))
        except Exception: logger.warning("penf_usage_failed", exc_info=True)
