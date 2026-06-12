"""Sandbox Enforcement Proof Service — metadata-only proof, no real enforcement."""
from __future__ import annotations
import logging
from typing import Any
from .sandbox_enforcement_proof import *

logger = logging.getLogger(__name__)

class SandboxEnforcementProofService:
    def __init__(self, store=None, usage_store=None):
        self._store = store; self._usage_store = usage_store

    def create_proof_request(self, tenant_id: str, *, execution_record=None, queue_record=None,
        policy_config_snapshot=None, adapter_descriptor_snapshot=None,
        network_rule=None, filesystem_rule=None, secret_rule=None,
        requested_by=None, scope=EnforcementScope.COMBINED) -> EnforcementProofRequest:
        if self._store is None: raise ValueError("store not available")
        req = EnforcementProofRequest(
            tenant_id=tenant_id,
            execution_id=getattr(execution_record, "execution_id", None) if execution_record else None,
            queue_record_id=getattr(queue_record, "queue_record_id", None) if queue_record else None,
            requested_by=requested_by, scope=scope,
            network_rule=network_rule or build_default_deny_network_rule(),
            filesystem_rule=filesystem_rule or build_default_deny_filesystem_rule(),
            secret_rule=secret_rule or build_default_deny_secret_rule(),
            policy_config_snapshot=policy_config_snapshot or {},
            adapter_descriptor_snapshot=adapter_descriptor_snapshot or {},
            execution_snapshot=self._snap(execution_record),
            queue_snapshot=self._snap(queue_record),
            proof_status=EnforcementProofStatus.REQUESTED,
            decision=EnforcementProofDecision.REVIEW_REQUIRED,
        )
        created = self._store.create_request(req)
        self._try_usage(created, requested_by)
        return created

    def evaluate_proof(self, request_id: str) -> EnforcementProofResult:
        if self._store is None: raise ValueError("store not available")
        req = self._store.get_request(request_id)
        if req is None: raise EnforcementProofRequestNotFoundError(f"Not found: {request_id}")
        result = EnforcementProofResult(request_id=request_id, tenant_id=req.tenant_id)
        # safety gates
        result.add_check(EnforcementCheck(request_id=request_id, check_type=EnforcementCheckType.NO_NETWORK_ENFORCEMENT_APPLIED, status=EnforcementCheckStatus.PASSED, severity=EnforcementSeverity.INFO, message="No network enforcement was applied."))
        result.add_check(EnforcementCheck(request_id=request_id, check_type=EnforcementCheckType.NO_FILESYSTEM_ENFORCEMENT_APPLIED, status=EnforcementCheckStatus.PASSED, severity=EnforcementSeverity.INFO, message="No filesystem enforcement was applied."))
        result.add_check(EnforcementCheck(request_id=request_id, check_type=EnforcementCheckType.NO_SECRET_READ_PERFORMED, status=EnforcementCheckStatus.PASSED, severity=EnforcementSeverity.INFO, message="No secret read was performed."))
        result.add_check(EnforcementCheck(request_id=request_id, check_type=EnforcementCheckType.NO_RUNTIME_STARTED, status=EnforcementCheckStatus.PASSED, severity=EnforcementSeverity.INFO, message="No runtime was started."))
        # network checks
        nw = req.network_rule
        result.add_check(EnforcementCheck(request_id=request_id, check_type=EnforcementCheckType.DEFAULT_DENY_NETWORK, status=EnforcementCheckStatus.PASSED if not nw.allow_network else EnforcementCheckStatus.BLOCKED, severity=EnforcementSeverity.INFO if not nw.allow_network else EnforcementSeverity.BLOCKER, message=f"Network: {'DENY_ALL' if not nw.allow_network else 'ALLOWED (unsupported)'}"))
        result.add_check(EnforcementCheck(request_id=request_id, check_type=EnforcementCheckType.NETWORK_METADATA_IP_BLOCKED, status=EnforcementCheckStatus.PASSED if nw.block_metadata_ip else EnforcementCheckStatus.FAILED, severity=EnforcementSeverity.INFO, message="Metadata IP blocked."))
        result.add_check(EnforcementCheck(request_id=request_id, check_type=EnforcementCheckType.NETWORK_LOCALHOST_BLOCKED, status=EnforcementCheckStatus.PASSED if nw.block_localhost else EnforcementCheckStatus.FAILED, severity=EnforcementSeverity.INFO, message="Localhost blocked."))
        result.add_check(EnforcementCheck(request_id=request_id, check_type=EnforcementCheckType.NETWORK_PRIVATE_IP_BLOCKED, status=EnforcementCheckStatus.PASSED if nw.block_private_ranges else EnforcementCheckStatus.FAILED, severity=EnforcementSeverity.INFO, message="Private IP ranges blocked."))
        result.add_check(EnforcementCheck(request_id=request_id, check_type=EnforcementCheckType.NETWORK_RAW_SOCKET_BLOCKED, status=EnforcementCheckStatus.PASSED if nw.block_raw_sockets else EnforcementCheckStatus.WARNING, severity=EnforcementSeverity.INFO, message="Raw sockets blocked."))
        # filesystem checks
        fs = req.filesystem_rule
        result.add_check(EnforcementCheck(request_id=request_id, check_type=EnforcementCheckType.FILESYSTEM_HOST_MOUNT_BLOCKED, status=EnforcementCheckStatus.PASSED if not fs.host_mount_allowed else EnforcementCheckStatus.BLOCKED, severity=EnforcementSeverity.BLOCKER if fs.host_mount_allowed else EnforcementSeverity.INFO, message="Host mount blocked."))
        result.add_check(EnforcementCheck(request_id=request_id, check_type=EnforcementCheckType.FILESYSTEM_DOCKER_SOCKET_BLOCKED, status=EnforcementCheckStatus.PASSED if not fs.docker_socket_allowed else EnforcementCheckStatus.BLOCKED, severity=EnforcementSeverity.BLOCKER if fs.docker_socket_allowed else EnforcementSeverity.INFO, message="Docker socket blocked."))
        result.add_check(EnforcementCheck(request_id=request_id, check_type=EnforcementCheckType.FILESYSTEM_WRITE_BLOCKED, status=EnforcementCheckStatus.PASSED if not fs.allow_write else EnforcementCheckStatus.BLOCKED, severity=EnforcementSeverity.BLOCKER if fs.allow_write else EnforcementSeverity.INFO, message="Write blocked."))
        # secrets checks
        sc = req.secret_rule
        result.add_check(EnforcementCheck(request_id=request_id, check_type=EnforcementCheckType.SECRETS_RAW_ENV_INJECTION_BLOCKED, status=EnforcementCheckStatus.PASSED if not sc.raw_env_injection_allowed else EnforcementCheckStatus.BLOCKED, severity=EnforcementSeverity.BLOCKER if sc.raw_env_injection_allowed else EnforcementSeverity.INFO, message="Raw env injection blocked."))
        result.add_check(EnforcementCheck(request_id=request_id, check_type=EnforcementCheckType.SECRETS_DIRECT_READ_BLOCKED, status=EnforcementCheckStatus.PASSED if not sc.direct_secret_read_allowed else EnforcementCheckStatus.BLOCKED, severity=EnforcementSeverity.BLOCKER if sc.direct_secret_read_allowed else EnforcementSeverity.INFO, message="Direct secret read blocked."))
        result.calculate_status()
        if self._store: self._store.create_result(result)
        return result

    def cancel_request(self, rid, actor=None):
        if self._store is None: raise ValueError("store not available")
        return self._store.cancel_request(rid, actor)
    def expire_request(self, rid, actor=None):
        if self._store is None: raise ValueError("store not available")
        return self._store.expire_request(rid, actor)

    def _snap(self, obj):
        if obj is None: return {}
        if isinstance(obj, dict): return dict(obj)
        if hasattr(obj, "to_dict") and callable(obj.to_dict): return obj.to_dict()
        return {}

    def _try_usage(self, req, actor_id):
        if self._usage_store is None: return
        try:
            from src.core.usage import UsageEvent, UsageResource, UsageUnit
            self._usage_store.record_event(UsageEvent(tenant_id=req.tenant_id, user_id=actor_id or "", workspace_id=req.tenant_id,
                resource=UsageResource.SANDBOX_ENFORCEMENT_PROOF_REQUEST_CREATE, quantity=1, unit=UsageUnit.COUNT,
                metadata={"request_id":req.request_id,"tenant_id":req.tenant_id,"execution_id":req.execution_id,
                "scope":req.scope,"proof_status":req.proof_status,"decision":req.decision,"risk_level":req.risk_level,
                "no_network_enforcement_applied":True,"no_filesystem_enforcement_applied":True,
                "no_secret_read_performed":True,"no_runtime_started":True,"no_execution_performed":True}))
        except Exception: logger.warning("enfproof_usage_failed", exc_info=True)
