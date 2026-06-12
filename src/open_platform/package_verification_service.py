"""Package Verification Service — 编排 artifact checksum/signature 验证。

Step 24-C:
- 读取 artifact metadata → checksum verifier → signature verifier
- 更新 artifact.verification_status + artifact audit event
- 不下载 / 不联网 / 不执行 / 不解压
- 不调用 cosign/gpg/minisign 外部命令
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.open_platform.package_artifact import ArtifactStatus, VerificationStatus
from src.open_platform.package_verification import (
    PackageVerificationRun, SignatureVerificationMode,
    VerificationCheck, VerificationCheckStatus, VerificationCheckType,
    VerificationRunStatus, VerificationSeverity,
)

logger = logging.getLogger(__name__)


class PackageVerificationService:
    """编排 checksum/signature 验证流程。"""

    def __init__(
        self,
        artifact_store: Any = None,
        verification_store: Any = None,
        usage_store: Any = None,
        trusted_key_ids: list[str] | None = None,
    ) -> None:
        self._artifact_store = artifact_store
        self._verification_store = verification_store
        self._usage_store = usage_store
        self._trusted_key_ids = trusted_key_ids or []

    def verify_artifact(
        self,
        artifact_id: str,
        requested_by: str,
        tenant_id: str,
        *,
        content_bytes: bytes | None = None,
        local_path: str | None = None,
        verify_signature: bool = True,
        allowed_root: str | None = None,
    ) -> PackageVerificationRun:
        """验证 artifact 的 checksum + signature。

        不下载。有 bytes/path 则计算 hash。签名只做 metadata 层验证。
        """
        if self._artifact_store is None:
            raise ValueError("artifact_store not available")
        if self._verification_store is None:
            raise ValueError("verification_store not available")

        # 1. Get artifact
        art = self._artifact_store.get_artifact(artifact_id)
        if art is None:
            raise ValueError(f"Artifact not found: {artifact_id}")
        if art.tenant_id != tenant_id:
            raise ValueError(f"Tenant mismatch: artifact tenant={art.tenant_id}, requested={tenant_id}")

        # 2. Check artifact status — reject/disabled → BLOCKED
        if art.artifact_status in (ArtifactStatus.REJECTED, ArtifactStatus.DISABLED):
            run = PackageVerificationRun(
                artifact_id=artifact_id, submission_id=art.submission_id,
                tenant_id=tenant_id, developer_id=art.developer_id,
                requested_by=requested_by, run_status=VerificationRunStatus.BLOCKED,
            )
            run.add_check(_chk(VerificationCheckType.ARTIFACT_INPUT_AVAILABLE, VerificationCheckStatus.BLOCKED,
                               VerificationSeverity.BLOCKER,
                               f"Artifact status is '{art.artifact_status}'. Cannot verify."))
            run.calculate_status()
            run.completed_at = datetime.now(timezone.utc)
            if self._verification_store:
                self._verification_store.create_run(run)
            return run

        # 3. Build run
        run = PackageVerificationRun(
            artifact_id=artifact_id, submission_id=art.submission_id,
            tenant_id=tenant_id, developer_id=art.developer_id,
            requested_by=requested_by,
            run_status=VerificationRunStatus.RUNNING,
            checksum_algorithm=art.checksum_algorithm,
            expected_checksum=art.checksum_value,
            signature_algorithm=art.signature_algorithm,
            signature_value_present=bool(art.signature_value),
            signature_mode=SignatureVerificationMode.METADATA_ONLY,
        )

        # 4. Checksum verification
        from src.open_platform.checksum_verifier import (
            ChecksumVerificationRequest, verify_checksum,
        )
        cs_req = ChecksumVerificationRequest(
            artifact_id=artifact_id, algorithm=art.checksum_algorithm,
            expected_checksum=art.checksum_value,
            content_bytes=content_bytes, local_path=local_path,
            allowed_root=allowed_root,
        )
        cs_result = verify_checksum(cs_req)
        run.checksum_algorithm = cs_result.algorithm
        run.actual_checksum = cs_result.actual_checksum
        run.checks.extend(cs_result.checks)

        # 5. Signature verification
        if verify_signature:
            from src.open_platform.signature_verifier import (
                SignatureVerificationRequest, verify_signature,
            )
            sig_req = SignatureVerificationRequest(
                artifact_id=artifact_id, signature_algorithm=art.signature_algorithm,
                signature_value=art.signature_value, signing_key_id=art.signing_key_id,
                mode=SignatureVerificationMode.METADATA_ONLY,
                trusted_key_ids=self._trusted_key_ids,
            )
            sig_result = verify_signature(sig_req)
            run.signature_verified = sig_result.signature_verified
            run.checks.extend(sig_result.checks)

        # 6. No network/execution/download check
        run.add_check(_chk(VerificationCheckType.NO_NETWORK_USED, VerificationCheckStatus.PASSED,
                           VerificationSeverity.INFO, "No network used during verification."))
        run.add_check(_chk(VerificationCheckType.NO_EXECUTION_USED, VerificationCheckStatus.PASSED,
                           VerificationSeverity.INFO, "No code execution performed during verification."))

        # 7. Calculate and save
        run.calculate_status()
        run.completed_at = datetime.now(timezone.utc)
        if self._verification_store:
            self._verification_store.create_run(run)

        # 8. Update artifact verification_status
        new_vs = self._compute_new_verification_status(run, art)
        if self._artifact_store and hasattr(self._artifact_store, "set_verification_status"):
            try:
                self._artifact_store.set_verification_status(
                    artifact_id, new_vs, requested_by,
                    f"Verification run {run.verification_id}: {run.run_status}",
                )
            except Exception:
                logger.warning("artifact_verification_status_update_failed", exc_info=True,
                              extra={"artifact_id": artifact_id})

        # 9. Record usage
        self._try_record_usage(run, requested_by)

        return run

    def _compute_new_verification_status(
        self, run: PackageVerificationRun, art: Any,
    ) -> str:
        if run.is_blocked():
            return art.verification_status  # don't downgrade
        if run.run_status == VerificationRunStatus.FAILED:
            return VerificationStatus.FAILED
        # Check if checksum matched
        cs_matched = any(
            c.check_type == VerificationCheckType.CHECKSUM_MATCH and
            c.status == VerificationCheckStatus.PASSED
            for c in run.checks
        )
        has_sig = run.signature_value_present
        if cs_matched and not has_sig:
            return VerificationStatus.CHECKSUM_VERIFIED
        if cs_matched and has_sig:
            return VerificationStatus.CHECKSUM_VERIFIED  # signature is metadata-only in 24-C
        # Input unavailable
        input_blocked = any(
            c.check_type == VerificationCheckType.ARTIFACT_INPUT_AVAILABLE and
            c.status == VerificationCheckStatus.BLOCKED
            for c in run.checks
        )
        if input_blocked:
            return VerificationStatus.CHECKSUM_PENDING
        return VerificationStatus.NOT_VERIFIED

    def get_latest_verification(self, artifact_id: str) -> PackageVerificationRun | None:
        if self._verification_store is None: return None
        return self._verification_store.get_latest_run_for_artifact(artifact_id)

    def _try_record_usage(self, run: PackageVerificationRun, actor_id: str) -> None:
        if self._usage_store is None: return
        try:
            from src.core.usage import UsageEvent, UsageResource, UsageUnit
            self._usage_store.record_event(UsageEvent(
                tenant_id=run.tenant_id, user_id=actor_id, workspace_id=run.tenant_id,
                resource=UsageResource.PACKAGE_VERIFICATION_RUN, quantity=1,
                unit=UsageUnit.COUNT,
                metadata={
                    "verification_id": run.verification_id, "artifact_id": run.artifact_id,
                    "submission_id": run.submission_id, "tenant_id": run.tenant_id,
                    "developer_id": run.developer_id, "run_status": run.run_status,
                    "checksum_algorithm": run.checksum_algorithm,
                    "checksum_matched": any(
                        c.check_type == VerificationCheckType.CHECKSUM_MATCH and
                        c.status == VerificationCheckStatus.PASSED
                        for c in run.checks),
                    "signature_algorithm": run.signature_algorithm,
                    "signature_metadata_present": run.signature_value_present,
                    "signature_verified": run.signature_verified,
                    "no_network_used": True, "no_execution_used": True,
                    "no_download_used": True,
                },
            ))
        except Exception:
            logger.warning("verification_usage_record_failed", exc_info=True,
                          extra={"verification_id": run.verification_id})


def _chk(ct, status, sev, msg, **kw) -> VerificationCheck:
    return VerificationCheck(check_type=ct, status=status, severity=sev, message=msg, metadata=kw)
