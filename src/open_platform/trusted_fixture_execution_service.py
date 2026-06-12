"""Trusted Fixture Execution Service — built-in fixtures only, no third-party/package/entrypoint code."""
from __future__ import annotations
import logging
from hashlib import sha256
from datetime import datetime, timezone
from typing import Any
from .trusted_fixture_execution import *

logger = logging.getLogger(__name__)

class TrustedFixtureExecutionService:
    def __init__(self, store=None, registry=None, execution_store=None, queue_store=None, enforcement_store=None, usage_store=None):
        self._store = store; self._registry = registry; self._usage_store = usage_store

    def create_fixture_request(self, fixture_id: str, tenant_id: str, *,
        input_metadata=None, execution_record=None, queue_record=None,
        enforcement_request=None, requested_by=None) -> TrustedFixtureExecutionRequest:
        if self._store is None: raise ValueError("store not available")
        if self._registry is None: raise ValueError("registry not available")
        fdef = self._registry.get_fixture(fixture_id)
        if fdef is None:
            return self._store.create_request(TrustedFixtureExecutionRequest(
                fixture_id=fixture_id, tenant_id=tenant_id, requested_by=requested_by,
                request_status=TrustedFixtureExecutionStatus.BLOCKED,
                decision=TrustedFixtureExecutionDecision.FAIL_CLOSED,
                safety_level=TrustedFixtureSafetyLevel.BLOCKED_UNSAFE))
        if not self._registry.is_fixture_allowed(fixture_id):
            return self._store.create_request(TrustedFixtureExecutionRequest(
                fixture_id=fixture_id, tenant_id=tenant_id, requested_by=requested_by,
                request_status=TrustedFixtureExecutionStatus.BLOCKED,
                decision=TrustedFixtureExecutionDecision.FAIL_CLOSED,
                safety_level=TrustedFixtureSafetyLevel.BLOCKED_UNSAFE))

        safe_meta = self._sanitize(input_metadata, fdef)
        req = TrustedFixtureExecutionRequest(
            fixture_id=fixture_id, tenant_id=tenant_id, requested_by=requested_by,
            execution_id=getattr(execution_record,"execution_id",None) if execution_record else None,
            queue_record_id=getattr(queue_record,"queue_record_id",None) if queue_record else None,
            enforcement_proof_request_id=getattr(enforcement_request,"request_id",None) if enforcement_request else None,
            input_payload_hash=sha256(str(safe_meta).encode()).hexdigest(),
            input_metadata=safe_meta,
            fixture_snapshot=fdef.to_dict(),
            execution_snapshot=self._snap(execution_record),
            queue_snapshot=self._snap(queue_record),
            enforcement_snapshot=self._snap(enforcement_request),
            request_status=TrustedFixtureExecutionStatus.REQUESTED,
            decision=TrustedFixtureExecutionDecision.ALLOW_TRUSTED_FIXTURE_ONLY,
            safety_level=fdef.safety_level,
        )
        created = self._store.create_request(req)
        self._try_usage(created, requested_by, "create")
        return created

    def run_trusted_fixture_request(self, request_id: str) -> TrustedFixtureExecutionResult:
        if self._store is None: raise ValueError("store not available")
        if self._registry is None: raise ValueError("registry not available")
        req = self._store.get_request(request_id)
        if req is None: raise TrustedFixtureNotFoundError(f"Not found: {request_id}")
        if not self._registry.is_fixture_allowed(req.fixture_id):
            return TrustedFixtureExecutionResult(request_id=request_id, fixture_id=req.fixture_id,
                tenant_id=req.tenant_id, result_status=TrustedFixtureResultStatus.BLOCKED)

        t0 = datetime.now(timezone.utc)
        output = self._registry.run_trusted_fixture(req.fixture_id, req.input_metadata)
        duration = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)

        result = TrustedFixtureExecutionResult(
            request_id=request_id, fixture_id=req.fixture_id, tenant_id=req.tenant_id,
            result_status=TrustedFixtureResultStatus.TRUSTED_FIXTURE_COMPLETED if output.get("ok") else TrustedFixtureResultStatus.BLOCKED,
            output_metadata=output, output_payload_hash=sha256(str(output).encode()).hexdigest(),
            duration_ms=duration, trusted_fixture_executed=output.get("ok", False),
            third_party_code_executed=False, package_executed=False, entrypoint_executed=False,
            dynamic_import_used=False, eval_exec_used=False, network_used=False,
            filesystem_used=False, secrets_used=False, subprocess_used=False, container_used=False,
            worker_queue_used=False, job_dispatched=False)
        if self._store:
            self._store.create_result(result)
            self._store.set_request_status(request_id, TrustedFixtureExecutionStatus.EXECUTED_TRUSTED_FIXTURE,
                                           req.requested_by, "Trusted fixture executed.")
        self._try_usage(req, req.requested_by, "run")
        return result

    def cancel_request(self, rid, actor=None): return self._store.cancel_request(rid, actor) if self._store else None
    def expire_request(self, rid, actor=None): return self._store.expire_request(rid, actor) if self._store else None

    def _sanitize(self, meta, fdef):
        if meta is None: return {}
        allowed = set(fdef.allowed_input_keys)
        if "*" in allowed: return {k: str(v)[:200] for k,v in meta.items() if not (isinstance(v,(dict,list)) and len(str(v))>500)}
        return {k: str(v)[:200] for k,v in meta.items() if k in allowed}

    def _snap(self, obj):
        if obj is None: return {}
        if isinstance(obj, dict): return dict(obj)
        if hasattr(obj,"to_dict") and callable(obj.to_dict): return obj.to_dict()
        return {}

    def _try_usage(self, req, actor_id, action):
        if self._usage_store is None: return
        try:
            from src.core.usage import UsageEvent, UsageResource, UsageUnit
            resource = UsageResource.TRUSTED_FIXTURE_RUN if action == "run" else UsageResource.TRUSTED_FIXTURE_REQUEST_CREATE
            self._usage_store.record_event(UsageEvent(tenant_id=req.tenant_id, user_id=actor_id or "", workspace_id=req.tenant_id,
                resource=resource, quantity=1, unit=UsageUnit.COUNT,
                metadata={"request_id":req.request_id,"fixture_id":req.fixture_id,"tenant_id":req.tenant_id,
                "request_status":req.request_status,"decision":req.decision,"safety_level":req.safety_level,
                "no_third_party_code_executed":True,"no_package_executed":True,"no_entrypoint_executed":True,
                "no_dynamic_import_used":True,"no_eval_exec_used":True,"no_network_used":True,
                "no_filesystem_used":True,"no_secret_read":True,"no_subprocess_used":True,
                "no_container_used":True,"no_worker_queue_used":True,"no_job_dispatched":True}))
        except Exception: logger.warning("tfix_usage_failed", exc_info=True)
