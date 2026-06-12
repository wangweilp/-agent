"""Artifact Extraction Guard Service — metadata-only entry validation. No archive read, no file write."""
from __future__ import annotations
import logging
from typing import Any
from .artifact_extraction_guard import *

logger = logging.getLogger(__name__)

class ArtifactExtractionGuardService:
    def __init__(self, store=None, package_download_store=None, artifact_store=None, usage_store=None):
        self._store = store; self._pkgdl_store = package_download_store
        self._artifact_store = artifact_store; self._usage_store = usage_store

    def create_guard_request(self, artifact_id: str, tenant_id: str, entries: list,
        *, package_download_request=None, quarantine_record=None,
        archive_format: str = ArchiveFormat.UNKNOWN_BLOCKED, requested_by: str | None = None) -> ArtifactExtractionGuardRequest:
        if self._store is None: raise ValueError("store not available")
        parsed = [_ensure_entry(e) for e in (entries or [])]
        req = ArtifactExtractionGuardRequest(
            artifact_id=artifact_id, tenant_id=tenant_id, requested_by=requested_by,
            archive_format=archive_format,
            package_download_request_id=getattr(package_download_request,"request_id",None) if package_download_request else None,
            package_quarantine_id=getattr(quarantine_record,"quarantine_id",None) if quarantine_record else None,
            download_request_snapshot=self._snap(package_download_request),
            quarantine_record_snapshot=self._snap(quarantine_record),
            artifact_snapshot=self._snap(self._artifact_store.get_artifact(artifact_id) if self._artifact_store and hasattr(self._artifact_store,"get_artifact") else None),
            entries=parsed, entry_count=len(parsed),
            total_declared_size_bytes=sum(e.size_bytes for e in parsed if e.size_bytes and e.size_bytes > 0) or None,
            guard_request_status=(ExtractionGuardRequestStatus.GUARD_REVIEW_REQUIRED if archive_format == ArchiveFormat.UNKNOWN_BLOCKED else ExtractionGuardRequestStatus.REQUESTED),
            decision=ExtractionGuardDecision.REVIEW_REQUIRED if archive_format == ArchiveFormat.UNKNOWN_BLOCKED else ExtractionGuardDecision.BLOCKED,
            plan_status=ExtractionPlanStatus.NOT_CREATED)
        created = self._store.create_request(req)
        self._try_usage(created, requested_by)
        return created

    def evaluate_guard(self, request_id: str) -> ArtifactExtractionGuardResult:
        if self._store is None: raise ValueError("store not available")
        req = self._store.get_request(request_id)
        if req is None: raise ArtifactExtractionRequestNotFoundError(f"Not found: {request_id}")
        result = ArtifactExtractionGuardResult(request_id=request_id, tenant_id=req.tenant_id)
        result.add_check(ExtractionGuardCheck(request_id=request_id, check_type=ExtractionGuardCheckType.NO_ARCHIVE_FILE_READ, status=ExtractionGuardCheckStatus.PASSED, severity=ExtractionGuardSeverity.INFO, message="No archive file was read."))
        result.add_check(ExtractionGuardCheck(request_id=request_id, check_type=ExtractionGuardCheckType.NO_EXTRACTION_PERFORMED, status=ExtractionGuardCheckStatus.PASSED, severity=ExtractionGuardSeverity.INFO, message="No extraction performed."))
        result.add_check(ExtractionGuardCheck(request_id=request_id, check_type=ExtractionGuardCheckType.NO_FILE_WRITTEN, status=ExtractionGuardCheckStatus.PASSED, severity=ExtractionGuardSeverity.INFO, message="No file written."))
        result.add_check(ExtractionGuardCheck(request_id=request_id, check_type=ExtractionGuardCheckType.NO_EXECUTION_PERFORMED, status=ExtractionGuardCheckStatus.PASSED, severity=ExtractionGuardSeverity.INFO, message="No execution performed."))
        result.add_check(ExtractionGuardCheck(request_id=request_id, check_type=ExtractionGuardCheckType.MANIFEST_METADATA_ONLY, status=ExtractionGuardCheckStatus.PASSED, severity=ExtractionGuardSeverity.INFO, message="Manifest metadata only — no archive file access."))

        if not req.entries:
            result.add_check(ExtractionGuardCheck(request_id=request_id, check_type=ExtractionGuardCheckType.ENTRY_NAME_PRESENT, status=ExtractionGuardCheckStatus.BLOCKED, severity=ExtractionGuardSeverity.BLOCKER, message="No entries provided."))
            result.calculate_status(); return self._save_result(result, request_id)

        if req.archive_format == ArchiveFormat.UNKNOWN_BLOCKED:
            result.add_check(ExtractionGuardCheck(request_id=request_id, check_type=ExtractionGuardCheckType.FAIL_CLOSED_ON_UNKNOWN, status=ExtractionGuardCheckStatus.BLOCKED, severity=ExtractionGuardSeverity.BLOCKER, message=f"Unknown archive format: {req.archive_format}"))

        seen = set(); blocked_ids = []
        for e in req.entries:
            if e.is_blocked:
                blocked_ids.append(e.entry_id)
                result.blocked_entries += 1
                result.add_check(ExtractionGuardCheck(request_id=request_id, check_type=ExtractionGuardCheckType.ENTRY_PATH_NORMALIZED if not e.normalized_path else ExtractionGuardCheckType.ZIP_SLIP_BLOCKED, status=ExtractionGuardCheckStatus.BLOCKED, severity=ExtractionGuardSeverity.BLOCKER, message=f"Blocked entry: {e.entry_name_redacted}"))
                continue
            if e.has_parent_traversal:
                blocked_ids.append(e.entry_id); result.blocked_entries += 1
                result.add_check(ExtractionGuardCheck(request_id=request_id, check_type=ExtractionGuardCheckType.PATH_TRAVERSAL_BLOCKED, status=ExtractionGuardCheckStatus.BLOCKED, severity=ExtractionGuardSeverity.BLOCKER, message=f"Path traversal: {e.entry_name_redacted}"))
                continue
            if e.is_absolute_path:
                blocked_ids.append(e.entry_id); result.blocked_entries += 1
                result.add_check(ExtractionGuardCheck(request_id=request_id, check_type=ExtractionGuardCheckType.ABSOLUTE_PATH_BLOCKED, status=ExtractionGuardCheckStatus.BLOCKED, severity=ExtractionGuardSeverity.BLOCKER, message=f"Absolute path: {e.entry_name_redacted}"))
                continue
            if e.has_windows_drive:
                blocked_ids.append(e.entry_id); result.blocked_entries += 1
                result.add_check(ExtractionGuardCheck(request_id=request_id, check_type=ExtractionGuardCheckType.WINDOWS_DRIVE_BLOCKED, status=ExtractionGuardCheckStatus.BLOCKED, severity=ExtractionGuardSeverity.BLOCKER, message=f"Windows drive: {e.entry_name_redacted}"))
                continue
            if e.has_nul_byte:
                blocked_ids.append(e.entry_id); result.blocked_entries += 1
                result.add_check(ExtractionGuardCheck(request_id=request_id, check_type=ExtractionGuardCheckType.NUL_BYTE_BLOCKED, status=ExtractionGuardCheckStatus.BLOCKED, severity=ExtractionGuardSeverity.BLOCKER, message=f"NUL byte: {e.entry_name_redacted}"))
                continue
            if e.is_symlink:
                blocked_ids.append(e.entry_id); result.blocked_entries += 1
                result.add_check(ExtractionGuardCheck(request_id=request_id, check_type=ExtractionGuardCheckType.SYMLINK_BLOCKED, status=ExtractionGuardCheckStatus.BLOCKED, severity=ExtractionGuardSeverity.BLOCKER, message=f"Symlink: {e.entry_name_redacted}"))
                continue
            np = e.normalized_path or ""
            if np in seen:
                blocked_ids.append(e.entry_id); result.blocked_entries += 1
                result.add_check(ExtractionGuardCheck(request_id=request_id, check_type=ExtractionGuardCheckType.DUPLICATE_PATH_BLOCKED, status=ExtractionGuardCheckStatus.BLOCKED, severity=ExtractionGuardSeverity.BLOCKER, message=f"Duplicate: {np}"))
                continue
            seen.add(np); result.normalized_paths.append(np); result.accepted_entries += 1
            if e.has_executable_permission:
                result.add_check(ExtractionGuardCheck(request_id=request_id, check_type=ExtractionGuardCheckType.EXECUTABLE_PERMISSION_REVIEWED, status=ExtractionGuardCheckStatus.WARNING, severity=ExtractionGuardSeverity.WARNING, message=f"Executable mode on: {np}"))
            if e.has_script_extension:
                result.add_check(ExtractionGuardCheck(request_id=request_id, check_type=ExtractionGuardCheckType.SCRIPT_EXTENSION_REVIEWED, status=ExtractionGuardCheckStatus.WARNING, severity=ExtractionGuardSeverity.WARNING, message=f"Script extension: {np}"))

        result.total_entries = len(req.entries)
        if req.entry_count > req.max_entry_count:
            result.add_check(ExtractionGuardCheck(request_id=request_id, check_type=ExtractionGuardCheckType.MAX_ENTRY_COUNT_CHECKED, status=ExtractionGuardCheckStatus.BLOCKED, severity=ExtractionGuardSeverity.BLOCKER, message=f"Entry count {req.entry_count} > max {req.max_entry_count}"))
        result.blocked_entry_ids = blocked_ids; result.calculate_status()
        return self._save_result(result, request_id)

    def reserve_read_only_plan(self, request_id: str, actor_id: str | None = None) -> ReadOnlyExtractionPlan:
        if self._store is None: raise ValueError("store not available")
        res = self._store.get_result_by_request(request_id)
        if res is None: raise ArtifactExtractionStateError("Result not found — run evaluate_guard first")
        plan = ReadOnlyExtractionPlan(request_id=request_id, plan_status=ExtractionPlanStatus.RESERVED_METADATA_ONLY,
            logical_extraction_ref=f"extref_{request_id}", allowed_normalized_paths=list(res.normalized_paths),
            blocked_entry_ids=list(res.blocked_entry_ids), extraction_allowed=False,
            file_write_allowed=False, execution_allowed=False, metadata_only=True, created_by=actor_id)
        return self._store.reserve_plan(plan)

    def cancel_request(self, rid, actor=None): return self._store.cancel_request(rid, actor) if self._store else None
    def expire_request(self, rid, actor=None): return self._store.expire_request(rid, actor) if self._store else None

    def _save_result(self, r, rid):
        if self._store: self._store.create_result(r)
        return r

    def _snap(self, obj):
        if obj is None: return {}
        if isinstance(obj, dict): return dict(obj)
        if hasattr(obj,"to_dict"): return obj.to_dict()
        return {}

    def _try_usage(self, req, actor_id):
        if self._usage_store is None: return
        try:
            from src.core.usage import UsageEvent, UsageResource, UsageUnit
            self._usage_store.record_event(UsageEvent(tenant_id=req.tenant_id, user_id=actor_id or "", workspace_id=req.tenant_id,
                resource=UsageResource.ARTIFACT_EXTRACTION_GUARD_REQUEST_CREATE, quantity=1, unit=UsageUnit.COUNT,
                metadata={"request_id":req.request_id,"artifact_id":req.artifact_id,"tenant_id":req.tenant_id,
                "archive_format":req.archive_format,"guard_request_status":req.guard_request_status,
                "entry_count":req.entry_count,"no_archive_file_read":True,"no_extraction_performed":True,
                "no_file_written":True,"no_execution_performed":True}))
        except Exception: logger.warning("ext_guard_usage_failed", exc_info=True)

def _ensure_entry(e):
    if isinstance(e, dict): return ArchiveEntryMetadata.from_dict(e)
    return e
