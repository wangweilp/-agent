"""Package Download Worker Service — disabled-by-default, metadata-only.

Step 26-C: no real download, no network, no file write, no extraction, no execution.
All gate evaluations return BLOCKED_DISABLED.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from .package_download_worker import *

logger = logging.getLogger(__name__)


class PackageDownloadWorkerService:
    def __init__(self, store=None, package_download_store=None,
                 runtime_safety_store=None, usage_store=None):
        self._store = store
        self._package_download_store = package_download_store
        self._runtime_safety_store = runtime_safety_store
        self._usage_store = usage_store

    def create_disabled_worker_policy(self, tenant_id=None, scope=PackageDownloadWorkerScope.GLOBAL,
                                      created_by=None) -> PackageDownloadWorkerPolicy:
        if self._store is None:
            raise ValueError("store not available")
        p = PackageDownloadWorkerPolicy(
            tenant_id=tenant_id, scope=scope,
            enabled_metadata_only=True,
            worker_enabled=False, network_enabled=False, download_enabled=False,
            file_write_enabled=False, extraction_enabled=False, package_execution_enabled=False,
            requires_admin_approval=True, requires_kill_switch_clear=True,
            requires_incident_clear=True, blocks_private_network_sources=True,
            blocks_metadata_ip=True, blocks_localhost=True, created_by=created_by)
        created = self._store.create_policy(p)
        self._try_usage(created, created_by, "policy_create")
        return created

    def create_download_job_metadata_only(
            self, worker_policy_id, package_download_request_id=None,
            quarantine_record_id=None, actor_id=None,
            kill_switch_policy_id=None, incident_id=None,
            source_snapshot=None, request_snapshot=None,
            quarantine_snapshot=None, kill_switch_snapshot=None) -> PackageDownloadWorkerJob:
        if self._store is None:
            raise ValueError("store not available")
        pol = self._store.get_policy(worker_policy_id)
        tid = pol.tenant_id if pol else None

        j = PackageDownloadWorkerJob(
            tenant_id=tid, worker_policy_id=worker_policy_id,
            package_download_request_id=package_download_request_id,
            quarantine_record_id=quarantine_record_id,
            kill_switch_policy_id=kill_switch_policy_id,
            incident_id=incident_id,
            source_snapshot=source_snapshot or {},
            package_request_snapshot=request_snapshot or {},
            quarantine_snapshot=quarantine_snapshot or {},
            kill_switch_snapshot=kill_switch_snapshot or {},
            status=PackageDownloadWorkerStatus.DISABLED_BY_DEFAULT,
            decision=PackageDownloadWorkerDecision.BLOCKED_DISABLED,
            download_performed=False, network_used=False, file_written=False,
            package_materialized=False, package_executed=False,
            entrypoint_executed=False, worker_started=False, job_dispatched=False,
            no_network_used=True, no_download_performed=True, no_file_written=True,
            no_extraction_performed=True, no_execution_performed=True,
            no_worker_started=True, no_dispatch_performed=True)
        created = self._store.create_job(j)
        self._try_usage(None, actor_id, "job_create", job_id=created.job_id,
                        tenant_id=tid, request_id=package_download_request_id)
        return created

    def evaluate_download_worker_gate(self, job_id, actor_id=None) -> PackageDownloadWorkerGateResult:
        if self._store is None:
            raise ValueError("store not available")
        j = self._store.get_job(job_id)
        if j is None:
            raise PackageDownloadWorkerJobNotFoundError(f"Not found: {job_id}")

        checks = []
        blockers = 0

        # Check 1: policy disabled
        pol = self._store.get_policy(j.worker_policy_id) if j.worker_policy_id else None
        pol_disabled = True
        if pol and (pol.worker_enabled or pol.download_enabled or pol.network_enabled):
            pol_disabled = False
        checks.append({"check": "policy_disabled_by_default", "passed": pol_disabled,
                       "blocker": not pol_disabled})
        if not pol_disabled:
            blockers += 1

        # Check 2: kill switch trigger check
        ks_clear = True
        if self._runtime_safety_store and j.kill_switch_policy_id:
            try:
                trigger = self._runtime_safety_store.get_latest_trigger(j.kill_switch_policy_id)
                if trigger and trigger.status == RuntimeKillSwitchStatus.TRIGGERED_METADATA_ONLY:
                    ks_clear = False
            except Exception:
                pass
        checks.append({"check": "kill_switch_clear", "passed": ks_clear, "blocker": not ks_clear})
        if not ks_clear:
            blockers += 1

        # Build gate result — always blocked
        gate = PackageDownloadWorkerGateResult(
            job_id=job_id, tenant_id=j.tenant_id,
            status=PackageDownloadWorkerStatus.DISABLED_BY_DEFAULT,
            decision=PackageDownloadWorkerDecision.BLOCKED_DISABLED,
            checks=checks, blockers_count=blockers, warnings_count=0,
            worker_start_allowed=False, network_allowed=False,
            download_allowed=False, file_write_allowed=False,
            execution_allowed=False, metadata_only=True)
        created = self._store.create_gate_result(gate)
        self._try_usage(None, actor_id, "gate_evaluate", job_id=job_id,
                        tenant_id=j.tenant_id)
        return created

    def reserve_worker_lease_metadata_only(self, job_id, actor_id=None) -> PackageDownloadWorkerLease:
        if self._store is None:
            raise ValueError("store not available")
        j = self._store.get_job(job_id)
        if j is None:
            raise PackageDownloadWorkerJobNotFoundError(f"Not found: {job_id}")
        lease = PackageDownloadWorkerLease(
            job_id=job_id, policy_id=j.worker_policy_id, tenant_id=j.tenant_id,
            status=PackageDownloadWorkerStatus.LEASE_RESERVED_METADATA_ONLY,
            decision=PackageDownloadWorkerDecision.METADATA_LEASE_RESERVED,
            lease_active=False, worker_started=False,
            heartbeat_enabled=False, download_allowed=False)
        created = self._store.reserve_lease_metadata_only(lease)
        self._try_usage(None, actor_id, "lease_reserve", lease_id=created.lease_id,
                        job_id=job_id, tenant_id=j.tenant_id)
        return created

    def release_worker_lease_metadata_only(self, lease_id, actor_id=None,
                                           reason=None) -> PackageDownloadWorkerLease:
        if self._store is None:
            raise ValueError("store not available")
        return self._store.release_lease_metadata_only(lease_id, actor_id, reason)

    def cancel_job(self, job_id, actor_id=None, reason=None) -> PackageDownloadWorkerJob:
        if self._store is None:
            raise ValueError("store not available")
        return self._store.set_job_status(job_id, PackageDownloadWorkerStatus.CANCELLED,
                                          actor_id, reason)

    def expire_job(self, job_id, actor_id=None, reason=None) -> PackageDownloadWorkerJob:
        if self._store is None:
            raise ValueError("store not available")
        return self._store.set_job_status(job_id, PackageDownloadWorkerStatus.EXPIRED,
                                          actor_id, reason)

    def _try_usage(self, rec, actor_id, action, **extra):
        if self._usage_store is None:
            return
        try:
            from src.core.usage import UsageEvent, UsageResource, UsageUnit
            resource_map = {
                "policy_create": UsageResource.PACKAGE_DOWNLOAD_WORKER_POLICY_CREATE,
                "job_create": UsageResource.PACKAGE_DOWNLOAD_WORKER_JOB_CREATE,
                "gate_evaluate": UsageResource.PACKAGE_DOWNLOAD_WORKER_GATE_EVALUATE,
                "lease_reserve": UsageResource.PACKAGE_DOWNLOAD_WORKER_LEASE_RESERVE_METADATA_ONLY,
                "lease_release": UsageResource.PACKAGE_DOWNLOAD_WORKER_LEASE_RELEASE_METADATA_ONLY,
                "job_blocked": UsageResource.PACKAGE_DOWNLOAD_WORKER_JOB_BLOCKED,
                "audit": UsageResource.PACKAGE_DOWNLOAD_WORKER_AUDIT_EVENT,
            }
            resource = resource_map.get(action, UsageResource.PACKAGE_DOWNLOAD_WORKER_AUDIT_EVENT)
            tid = extra.get("tenant_id") or (rec.tenant_id if rec else "")
            self._usage_store.record_event(UsageEvent(
                tenant_id=tid or "", user_id=actor_id or "", workspace_id=tid or "",
                resource=resource, quantity=1, unit=UsageUnit.COUNT,
                metadata={"worker_enabled": False, "network_enabled": False,
                          "download_enabled": False, "download_performed": False,
                          "network_used": False, "file_written": False,
                          "package_executed": False, "worker_start_allowed": False,
                          "download_allowed": False, "metadata_only": True,
                          **{k: v for k, v in extra.items() if v}}))
        except Exception:
            logger.warning("pkgdlwk_usage_failed", exc_info=True)
