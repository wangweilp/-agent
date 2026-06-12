"""Package Artifact Declaration Service — 从 submission manifest 声明 artifact。

Step 24-B:
- 读取 submission + manifest metadata
- 链接 latest package validation
- 创建 PackageArtifact + (可选) QuarantineRecord
- 不下载 package / 不计算 checksum / 不验证 signature / 不执行代码
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.open_platform.package_artifact import (
    ArtifactSourceType,
    ArtifactStatus,
    PackageArtifact,
    PackageArtifactStore,
    PackageQuarantineRecord,
    QuarantineStatus,
    ArtifactRiskLevel,
)

logger = logging.getLogger(__name__)


class PackageArtifactDeclarationService:
    """从 submission manifest metadata 声明 artifact。

    依赖注入：
    - artifact_store: PackageArtifactStore
    - submission_store: SubmissionStore (has get_submission)
    - package_validation_store: optional, for linking latest validation
    - usage_store: optional, for usage recording
    """

    def __init__(
        self,
        artifact_store: PackageArtifactStore,
        submission_store: Any = None,
        package_validation_store: Any = None,
        usage_store: Any = None,
    ) -> None:
        self._artifact_store = artifact_store
        self._submission_store = submission_store
        self._pv_store = package_validation_store
        self._usage_store = usage_store

    def declare_artifact_from_submission(
        self,
        submission_id: str,
        actor_id: str,
        tenant_id: str,
        *,
        quarantine: bool = True,
        source_type: str | None = None,
        marketplace_agent_id: str | None = None,
    ) -> PackageArtifact:
        """从 submission 声明 PackageArtifact。

        不下载 package。不执行。不计算 checksum。不验证 signature。
        """
        if self._submission_store is None:
            raise ValueError("submission_store not available")

        # 1. Read submission
        sub = self._submission_store.get_submission(submission_id)
        if sub is None:
            raise ValueError(f"Submission not found: {submission_id}")
        if sub.tenant_id != tenant_id:
            raise ValueError(f"Tenant mismatch: submission tenant={sub.tenant_id}, requested={tenant_id}")

        # 2. Extract manifest metadata
        manifest = getattr(sub, "agent_manifest", None)
        manifest_meta: dict[str, Any] = {}
        if manifest is not None:
            manifest_meta = dict(getattr(manifest, "metadata", {}) or {})

        dev_id = getattr(sub, "developer_id", "")

        # 3. Determine source type
        st = source_type or getattr(sub, "source_type", "manifest")
        if st == "package_url":
            asrc = ArtifactSourceType.PACKAGE_URL
        elif st == "repository":
            asrc = ArtifactSourceType.REPOSITORY
        else:
            asrc = ArtifactSourceType.INLINE_METADATA

        # 4. Build artifact
        artifact = PackageArtifact(
            submission_id=submission_id,
            developer_id=dev_id,
            tenant_id=tenant_id,
            marketplace_agent_id=marketplace_agent_id,
            source_type=asrc,
            package_url=getattr(sub, "package_url", None),
            repository_url=manifest_meta.get("repository_url"),
            package_name=manifest_meta.get("package_name") or (
                manifest.name if manifest else None),
            package_version=manifest_meta.get("package_version") or (
                manifest.version if manifest else None),
            checksum_algorithm=manifest_meta.get("package_checksum_algorithm") or "sha256",
            checksum_value=manifest_meta.get("package_checksum"),
            signature_algorithm=manifest_meta.get("package_signature_algorithm"),
            signature_value=manifest_meta.get("package_signature"),
            signing_key_id=manifest_meta.get("signing_key_id"),
            declared_size_bytes=manifest_meta.get("declared_size_bytes"),
            content_type=manifest_meta.get("content_type"),
            artifact_status=ArtifactStatus.DECLARED,
            package_metadata=manifest_meta,
            created_by=actor_id,
            updated_by=actor_id,
        )

        # 5. Link latest package validation
        if self._pv_store is not None:
            try:
                pv = self._pv_store.get_latest_by_submission(submission_id)
                if pv is not None:
                    artifact.validation_id = getattr(pv, "validation_id", None)
            except Exception:
                logger.debug("package_validation_lookup_failed", exc_info=True,
                            extra={"submission_id": submission_id})

        # 6. Create artifact
        created = self._artifact_store.create_artifact(artifact)

        # 7. Create quarantine record if requested
        if quarantine:
            qr = PackageQuarantineRecord(
                artifact_id=created.artifact_id,
                tenant_id=tenant_id,
                submission_id=submission_id,
                status=QuarantineStatus.QUARANTINED,
                reason="Auto-quarantine on artifact declaration",
                risk_level=ArtifactRiskLevel.UNKNOWN,
                policy_snapshot={},
                validation_summary=self._build_validation_summary(created),
                created_by=actor_id,
            )
            self._artifact_store.create_quarantine_record(qr)
            # Re-fetch artifact to get updated quarantine_status
            created = self._artifact_store.get_artifact(created.artifact_id)
            if created is None:
                raise ValueError(f"Artifact not found after creation: {created.artifact_id}")
            logger.info("artifact_quarantined", extra={
                "artifact_id": created.artifact_id,
                "quarantine_id": qr.quarantine_id,
            })

        # 8. Record usage
        self._try_record_usage(created, actor_id, quarantine)

        logger.info("artifact_declared", extra={
            "artifact_id": created.artifact_id,
            "submission_id": submission_id,
            "quarantine": quarantine,
        })
        return created

    def _build_validation_summary(self, artifact: PackageArtifact) -> dict[str, Any]:
        summary: dict[str, Any] = {"has_validation": False}
        if artifact.validation_id and self._pv_store is not None:
            try:
                pv = self._pv_store.get_result(artifact.validation_id)
                if pv is not None:
                    summary = {
                        "has_validation": True,
                        "validation_id": artifact.validation_id,
                        "status": getattr(pv, "status", ""),
                        "warnings_count": len(getattr(pv, "warnings", [])),
                        "errors_count": len(getattr(pv, "errors", [])),
                        "blockers_count": len(getattr(pv, "blockers", [])),
                        "checks_count": len(getattr(pv, "checks", [])),
                    }
            except Exception:
                pass
        return summary

    def _try_record_usage(
        self, artifact: PackageArtifact, actor_id: str, quarantined: bool,
    ) -> None:
        if self._usage_store is None:
            return
        try:
            from src.core.usage import UsageEvent, UsageResource, UsageUnit
            resource = UsageResource.PACKAGE_ARTIFACT_DECLARE
            self._usage_store.record_event(UsageEvent(
                tenant_id=artifact.tenant_id,
                user_id=actor_id,
                workspace_id=artifact.tenant_id,
                resource=resource,
                quantity=1,
                unit=UsageUnit.COUNT,
                metadata={
                    "artifact_id": artifact.artifact_id,
                    "submission_id": artifact.submission_id,
                    "tenant_id": artifact.tenant_id,
                    "developer_id": artifact.developer_id,
                    "source_type": artifact.source_type,
                    "artifact_status": artifact.artifact_status,
                    "verification_status": artifact.verification_status,
                    "quarantine_status": artifact.quarantine_status,
                    "risk_level": artifact.risk_level,
                    "validation_id": artifact.validation_id,
                    "quarantined": quarantined,
                    "action": "declare",
                },
            ))
        except Exception:
            logger.warning("artifact_usage_record_failed", exc_info=True,
                          extra={"artifact_id": artifact.artifact_id})
