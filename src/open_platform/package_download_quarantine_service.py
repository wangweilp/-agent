"""Package Download Quarantine Service — admin-gated request creation, no download, no network."""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any
from .package_download_quarantine import *

logger = logging.getLogger(__name__)

class PackageDownloadQuarantineService:
    def __init__(self, store=None, artifact_store=None, execution_store=None, usage_store=None):
        self._store = store
        self._artifact_store = artifact_store
        self._execution_store = execution_store
        self._usage_store = usage_store

    def create_download_request(self, artifact: Any, raw_source_url: str | None,
                                requested_by: str | None = None, execution_record: Any = None,
                                metadata: dict | None = None) -> PackageDownloadRequest:
        if self._store is None: raise ValueError("store not available")
        src = build_package_source_metadata(raw_source_url)
        aid = getattr(artifact, "artifact_id", "")
        tid = getattr(artifact, "tenant_id", "")
        did = getattr(artifact, "developer_id", "")
        sub_id = getattr(artifact, "submission_id", None)
        mkp_id = getattr(artifact, "marketplace_agent_id", None)

        block_st = (PackageDownloadRequestStatus.DOWNLOAD_DISABLED if src.is_blocked_source
                    else PackageDownloadRequestStatus.ADMIN_REVIEW_REQUIRED)

        req = PackageDownloadRequest(
            artifact_id=aid, marketplace_agent_id=mkp_id, tenant_id=tid,
            developer_id=did, submission_id=sub_id, requested_by=requested_by,
            source_metadata=src, request_status=block_st,
            decision=PackageDownloadDecision.BLOCKED if src.is_blocked_source else PackageDownloadDecision.REVIEW_REQUIRED,
            gate_status=PackageDownloadGateStatus.FAIL_CLOSED if src.is_blocked_source else PackageDownloadGateStatus.ADMIN_REQUIRED,
            quarantine_status=PackageDownloadQuarantineStatus.NOT_CREATED,
            risk_level=src.risk_level,
            artifact_snapshot=self._snap(artifact),
            execution_snapshot=self._snap(execution_record),
        )
        created = self._store.create_request(req)
        self._try_usage(created, requested_by)
        logger.info("pkg_download_request_created", extra={"request_id": created.request_id})
        return created

    def approve_for_future_download(self, request_id: str, admin_actor_id: str,
                                     reason: str | None = None) -> PackageDownloadRequest:
        if self._store is None: raise ValueError("store not available")
        return self._store.approve_for_future_download(request_id, admin_actor_id, reason)

    def reject_request(self, request_id: str, admin_actor_id: str,
                       reason: str | None = None) -> PackageDownloadRequest:
        if self._store is None: raise ValueError("store not available")
        return self._store.reject_request(request_id, admin_actor_id, reason)

    def reserve_quarantine_metadata(self, request_id: str, actor_id: str | None = None) -> PackageDownloadQuarantineRecord:
        if self._store is None: raise ValueError("store not available")
        req = self._store.get_request(request_id)
        if req is None: raise PackageDownloadRequestNotFoundError(f"Not found: {request_id}")
        rec = PackageDownloadQuarantineRecord(
            request_id=request_id, artifact_id=req.artifact_id, tenant_id=req.tenant_id,
            quarantine_status=PackageDownloadQuarantineStatus.RESERVED_METADATA_ONLY,
            logical_quarantine_ref=f"qref_{request_id}", file_materialized=False,
            extraction_allowed=False, execution_allowed=False, created_by=actor_id,
        )
        return self._store.reserve_quarantine_record(rec)

    def cancel_request(self, request_id: str, actor_id: str | None = None) -> PackageDownloadRequest:
        if self._store is None: raise ValueError("store not available")
        return self._store.cancel_request(request_id, actor_id)

    def expire_request(self, request_id: str, actor_id: str | None = None) -> PackageDownloadRequest:
        if self._store is None: raise ValueError("store not available")
        return self._store.expire_request(request_id, actor_id)

    def _snap(self, obj):
        if obj is None: return {}
        if isinstance(obj, dict): return dict(obj)
        if hasattr(obj, "to_dict"): return obj.to_dict()
        return {}

    def _try_usage(self, req, actor_id):
        if self._usage_store is None: return
        try:
            from src.core.usage import UsageEvent, UsageResource, UsageUnit
            self._usage_store.record_event(UsageEvent(
                tenant_id=req.tenant_id, user_id=actor_id or "", workspace_id=req.tenant_id,
                resource=UsageResource.PACKAGE_DOWNLOAD_REQUEST_CREATE, quantity=1, unit=UsageUnit.COUNT,
                metadata={"request_id":req.request_id,"artifact_id":req.artifact_id,
                    "marketplace_agent_id":req.marketplace_agent_id,"tenant_id":req.tenant_id,
                    "developer_id":req.developer_id,"request_status":req.request_status,
                    "decision":req.decision,"gate_status":req.gate_status,
                    "quarantine_status":req.quarantine_status,"source_scheme":req.source_metadata.source_scheme,
                    "source_host":req.source_metadata.source_host,
                    "source_url_hash":req.source_metadata.source_url_hash,
                    "is_blocked_source":req.source_metadata.is_blocked_source,
                    "no_download_performed":True,"no_network_used":True,"no_file_written":True,
                    "no_package_extracted":True,"no_execution_performed":True}))
        except Exception: logger.warning("pkgdl_usage_failed", exc_info=True)
