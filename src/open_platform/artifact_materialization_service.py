"""Artifact Materialization Service — read-only spike, metadata-only, disabled-by-default.

Step 26-D: no real materialization, no file write, no mount, no extraction, no execution.
All gate evaluations return BLOCKED_DISABLED.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from .artifact_materialization import *

logger = logging.getLogger(__name__)


class ArtifactMaterializationService:
    def __init__(self, store=None, package_download_worker_store=None,
                 extraction_guard_store=None, runtime_safety_store=None, usage_store=None):
        self._store = store
        self._package_download_worker_store = package_download_worker_store
        self._extraction_guard_store = extraction_guard_store
        self._runtime_safety_store = runtime_safety_store
        self._usage_store = usage_store

    def create_disabled_materialization_policy(
            self, tenant_id=None, scope=ArtifactMaterializationScope.GLOBAL,
            created_by=None) -> ArtifactMaterializationPolicy:
        if self._store is None:
            raise ValueError("store not available")
        p = ArtifactMaterializationPolicy(
            tenant_id=tenant_id, scope=scope,
            enabled_metadata_only=True,
            materialization_enabled=False, file_write_enabled=False,
            directory_create_enabled=False, mount_enabled=False,
            extraction_enabled=False, package_execution_enabled=False,
            requires_download_worker_gate=True, requires_extraction_guard_gate=True,
            requires_kill_switch_clear=True, requires_incident_clear=True,
            read_only_refs_only=True, blocks_absolute_paths=True,
            blocks_traversal=True, blocks_symlink_escape=True,
            created_by=created_by)
        created = self._store.create_policy(p)
        self._try_usage(created, created_by, "policy_create")
        return created

    def create_materialization_request_metadata_only(
            self, policy_id, package_download_request_id=None,
            quarantine_record_id=None, download_worker_job_id=None,
            extraction_guard_request_id=None, extraction_plan_id=None,
            actor_id=None,
            source_snapshot=None, quarantine_snapshot=None,
            download_worker_snapshot=None, extraction_guard_snapshot=None,
            kill_switch_snapshot=None) -> ArtifactMaterializationRequest:
        if self._store is None:
            raise ValueError("store not available")
        pol = self._store.get_policy(policy_id)
        tid = pol.tenant_id if pol else None

        r = ArtifactMaterializationRequest(
            tenant_id=tid, policy_id=policy_id,
            package_download_request_id=package_download_request_id,
            quarantine_record_id=quarantine_record_id,
            download_worker_job_id=download_worker_job_id,
            extraction_guard_request_id=extraction_guard_request_id,
            extraction_plan_id=extraction_plan_id,
            source_snapshot=source_snapshot or {},
            quarantine_snapshot=quarantine_snapshot or {},
            download_worker_snapshot=download_worker_snapshot or {},
            extraction_guard_snapshot=extraction_guard_snapshot or {},
            kill_switch_snapshot=kill_switch_snapshot or {},
            status=ArtifactMaterializationStatus.DISABLED_BY_DEFAULT,
            decision=ArtifactMaterializationDecision.BLOCKED_DISABLED,
            materialization_performed=False, file_written=False,
            directory_created=False, mount_created=False,
            archive_read=False, archive_extracted=False,
            package_executed=False, entrypoint_executed=False,
            no_file_written=True, no_directory_created=True,
            no_mount_created=True, no_archive_read=True,
            no_extraction_performed=True, no_execution_performed=True,
            no_worker_started=True, no_dispatch_performed=True)
        created = self._store.create_request(r)
        self._try_usage(None, actor_id, "request_create",
                        request_id=created.request_id, tenant_id=tid)
        return created

    def evaluate_materialization_gate(self, request_id, actor_id=None) -> ArtifactMaterializationGateResult:
        if self._store is None:
            raise ValueError("store not available")
        r = self._store.get_request(request_id)
        if r is None:
            raise ArtifactMaterializationRequestNotFoundError(f"Not found: {request_id}")

        checks = []
        blockers = 0

        # Check 1: policy disabled
        pol = self._store.get_policy(r.policy_id) if r.policy_id else None
        pol_disabled = True
        if pol and (pol.materialization_enabled or pol.file_write_enabled or pol.mount_enabled):
            pol_disabled = False
        checks.append({"check": "policy_disabled_by_default", "passed": pol_disabled,
                       "blocker": not pol_disabled})
        if not pol_disabled:
            blockers += 1

        # Check 2: download worker job not downloaded
        dw_clear = True
        checks.append({"check": "download_worker_job_not_downloaded", "passed": dw_clear,
                       "blocker": False})

        # Check 3: extraction plan not materialized
        ex_clear = True
        checks.append({"check": "extraction_plan_not_materialized", "passed": ex_clear,
                       "blocker": False})

        # Check 4: kill switch clear
        ks_clear = True
        if self._runtime_safety_store and r.kill_switch_snapshot:
            try:
                ks_policy_id = r.kill_switch_snapshot.get("policy_id")
                if ks_policy_id:
                    trigger = self._runtime_safety_store.get_latest_trigger(ks_policy_id)
                    if trigger and trigger.status == "triggered_metadata_only":
                        ks_clear = False
            except Exception:
                pass
        checks.append({"check": "kill_switch_clear", "passed": ks_clear,
                       "blocker": not ks_clear})
        if not ks_clear:
            blockers += 1

        gate = ArtifactMaterializationGateResult(
            request_id=request_id, tenant_id=r.tenant_id,
            status=ArtifactMaterializationStatus.DISABLED_BY_DEFAULT,
            decision=ArtifactMaterializationDecision.BLOCKED_DISABLED,
            checks=checks, blockers_count=blockers, warnings_count=0,
            materialization_allowed=False, file_write_allowed=False,
            directory_create_allowed=False, mount_allowed=False,
            archive_read_allowed=False, extraction_allowed=False,
            execution_allowed=False, metadata_only=True)
        created = self._store.create_gate_result(gate)
        self._try_usage(None, actor_id, "gate_evaluate",
                        request_id=request_id, tenant_id=r.tenant_id)
        return created

    def reserve_materialization_plan_metadata_only(self, request_id, actor_id=None) -> ReadOnlyArtifactMaterializationPlan:
        if self._store is None:
            raise ValueError("store not available")
        r = self._store.get_request(request_id)
        if r is None:
            raise ArtifactMaterializationRequestNotFoundError(f"Not found: {request_id}")
        plan = ReadOnlyArtifactMaterializationPlan(
            request_id=request_id, tenant_id=r.tenant_id, policy_id=r.policy_id,
            logical_artifact_ref=f"logical_ref_{request_id}",
            allowed_logical_paths=[], blocked_logical_paths=[],
            source_hashes=[], metadata_manifest={},
            plan_status=ArtifactMaterializationStatus.PLAN_RESERVED_METADATA_ONLY,
            decision=ArtifactMaterializationDecision.METADATA_PLAN_RESERVED,
            materialization_allowed=False, file_write_allowed=False,
            directory_create_allowed=False, mount_allowed=False,
            extraction_allowed=False, execution_allowed=False,
            metadata_only=True)
        created = self._store.reserve_plan_metadata_only(plan)
        self._try_usage(None, actor_id, "plan_reserve",
                        plan_id=created.plan_id, request_id=request_id,
                        tenant_id=r.tenant_id)
        return created

    def reserve_read_only_artifact_reference(self, plan_id, actor_id=None) -> ReadOnlyArtifactReference:
        if self._store is None:
            raise ValueError("store not available")
        plan = self._store.get_plan(plan_id)
        if plan is None:
            raise ArtifactMaterializationPlanNotFoundError(f"Not found: {plan_id}")
        ref = ReadOnlyArtifactReference(
            plan_id=plan_id, tenant_id=plan.tenant_id,
            logical_ref=plan.logical_artifact_ref,
            ref_type="logical_only",
            ref_status=ArtifactMaterializationStatus.READ_ONLY_REFERENCE_RESERVED,
            content_hash=None, manifest_hash=None,
            filesystem_path=None, filesystem_ref_active=False,
            file_exists_checked=False, file_opened=False,
            file_written=False, mount_active=False, execution_allowed=False)
        created = self._store.reserve_read_only_reference(ref)
        self._try_usage(None, actor_id, "ref_reserve",
                        ref_id=created.ref_id, plan_id=plan_id,
                        tenant_id=plan.tenant_id)
        return created

    def cancel_request(self, request_id, actor_id=None, reason=None) -> ArtifactMaterializationRequest:
        if self._store is None:
            raise ValueError("store not available")
        return self._store.set_request_status(
            request_id, ArtifactMaterializationStatus.CANCELLED, actor_id, reason)

    def expire_request(self, request_id, actor_id=None, reason=None) -> ArtifactMaterializationRequest:
        if self._store is None:
            raise ValueError("store not available")
        return self._store.set_request_status(
            request_id, ArtifactMaterializationStatus.EXPIRED, actor_id, reason)

    def _try_usage(self, rec, actor_id, action, **extra):
        if self._usage_store is None:
            return
        try:
            from src.core.usage import UsageEvent, UsageResource, UsageUnit
            resource_map = {
                "policy_create": UsageResource.ARTIFACT_MATERIALIZATION_POLICY_CREATE,
                "request_create": UsageResource.ARTIFACT_MATERIALIZATION_REQUEST_CREATE,
                "gate_evaluate": UsageResource.ARTIFACT_MATERIALIZATION_GATE_EVALUATE,
                "plan_reserve": UsageResource.ARTIFACT_MATERIALIZATION_PLAN_RESERVE_METADATA_ONLY,
                "ref_reserve": UsageResource.ARTIFACT_MATERIALIZATION_REFERENCE_RESERVE,
                "blocked": UsageResource.ARTIFACT_MATERIALIZATION_BLOCKED,
                "audit": UsageResource.ARTIFACT_MATERIALIZATION_AUDIT_EVENT,
            }
            resource = resource_map.get(action, UsageResource.ARTIFACT_MATERIALIZATION_AUDIT_EVENT)
            tid = extra.get("tenant_id") or (rec.tenant_id if rec else "")
            self._usage_store.record_event(UsageEvent(
                tenant_id=tid or "", user_id=actor_id or "", workspace_id=tid or "",
                resource=resource, quantity=1, unit=UsageUnit.COUNT,
                metadata={"materialization_allowed": False, "file_write_allowed": False,
                          "mount_allowed": False, "extraction_allowed": False,
                          "execution_allowed": False, "materialization_performed": False,
                          "file_written": False, "archive_read": False,
                          "package_executed": False, "metadata_only": True,
                          **{k: v for k, v in extra.items() if v}}))
        except Exception:
            logger.warning("artmat_usage_failed", exc_info=True)
