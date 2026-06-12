"""Package Validation Pipeline Service — 静态 package metadata 验证。

不下载，不解压，不执行，不联网。
"""

from __future__ import annotations
import logging, re as _re, uuid
from urllib.parse import urlparse
from datetime import datetime, timezone
from typing import Any

from src.core.usage import UsageEvent, UsageResource, UsageUnit
from src.open_platform.package_validation import (
    PackageSourceType, PackageValidationStatus, PackageValidationSeverity,
    PackageValidationCheckCode, PackageValidationCheck,
    PackageValidationRequest, PackageValidationResult,
)

logger = logging.getLogger(__name__)

_ALLOWED_SCHEMES = {"https"}
_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "metadata.google.internal", "169.254.169.254"}
_ALLOWED_CHECKSUM_ALGOS = {"sha256", "sha384", "sha512"}
_ALLOWED_SIGNATURE_ALGOS = {"minisign", "cosign", "gpg"}


class PackageValidationService:
    def __init__(self, pv_store=None, submission_store=None, developer_store=None, usage_store=None):
        self._pv_store = pv_store
        self._submission_store = submission_store
        self._developer_store = developer_store
        self._usage_store = usage_store

    # ═══════════════════════ Public ═══════════════════════

    def validate_submission_package(self, submission_id: str, requested_by: str,
                                     tenant_id: str, options: dict | None = None) -> PackageValidationResult:
        # Read submission
        if self._submission_store is None:
            raise ValueError("submission_store not available")
        sub = self._submission_store.get_submission(submission_id)
        if sub is None:
            raise ValueError(f"Submission not found: {submission_id}")
        if sub.tenant_id != tenant_id:
            raise ValueError("Submission not found")

        manifest = sub.agent_manifest
        req = PackageValidationRequest(
            submission_id=submission_id, requested_by=requested_by, tenant_id=tenant_id,
            package_url=sub.package_url, source_type=sub.source_type,
            manifest_name=manifest.name if manifest else "",
            manifest_version=manifest.version if manifest else "",
            manifest_runtime_type=manifest.runtime_type if manifest else "manifest_only",
            manifest_metadata=manifest.metadata if manifest else {},
            validation_options=options or {},
            metadata={},
        )

        result = PackageValidationResult(
            submission_id=submission_id, tenant_id=tenant_id, requested_by=requested_by,
            package_url=req.package_url, manifest_name=req.manifest_name,
            manifest_version=req.manifest_version, source_type=req.source_type,
            no_download_performed=True, no_execution_performed=True, no_network_performed=True,
        )

        # Run checks
        checks: list[PackageValidationCheck] = []
        checks.extend(self._check_source_presence(req))
        checks.extend(self._check_url_format(req))
        checks.extend(self._check_domain_policy(req))
        checks.extend(self._check_checksum(req))
        checks.extend(self._check_signature(req))
        checks.extend(self._check_manifest_consistency(req))
        checks.extend(self._check_dependencies(req))
        checks.extend(self._check_runtime_sandbox(req))
        checks.append(self._check_code(PackageValidationCheckCode.PACKAGE_NOT_DOWNLOADED,
            "Package was NOT downloaded. Static validation only.", True))
        checks.append(self._check_code(PackageValidationCheckCode.PACKAGE_NOT_EXECUTED,
            "Package was NOT executed. Static validation only.", True))

        result.checks = checks
        result.warnings = [c.message for c in checks if c.severity == PackageValidationSeverity.WARNING and not c.passed]
        result.errors = [c.message for c in checks if c.severity == PackageValidationSeverity.ERROR and not c.passed]
        result.blockers = [c.message for c in checks if c.severity == PackageValidationSeverity.BLOCKER and not c.passed]
        self._compute_status(result)
        result.completed_at = datetime.now(timezone.utc)

        # Persist
        if self._pv_store:
            self._pv_store.create_result(result)

        # Usage
        self._try_usage(result)
        return result

    def get_latest_validation(self, submission_id: str):
        if self._pv_store is None: return None
        return self._pv_store.get_latest_by_submission(submission_id)

    # ═══════════════════════ Checks ═══════════════════════

    def _chk(self, code, severity, passed, msg, meta=None) -> PackageValidationCheck:
        return PackageValidationCheck(code=code, severity=severity, passed=passed, message=msg, metadata=meta or {})

    def _check_code(self, code, msg, passed=True) -> PackageValidationCheck:
        return self._chk(code, PackageValidationSeverity.INFO, passed, msg)

    def _check_source_presence(self, req: PackageValidationRequest) -> list[PackageValidationCheck]:
        c = []
        st = req.source_type
        if st == "manifest" and not req.package_url:
            c.append(self._chk(PackageValidationCheckCode.URL_PRESENT, PackageValidationSeverity.INFO, True,
                               "Manifest-only submission — no package URL to validate."))
        elif st == "package_url" and not req.package_url:
            c.append(self._chk(PackageValidationCheckCode.URL_PRESENT, PackageValidationSeverity.ERROR, False,
                               "source_type=package_url but package_url is empty."))
        elif st == "repository" and not req.repository_url and not req.package_url:
            c.append(self._chk(PackageValidationCheckCode.URL_PRESENT, PackageValidationSeverity.WARNING, False,
                               "source_type=repository but no URL provided."))
        else:
            c.append(self._chk(PackageValidationCheckCode.SOURCE_TYPE_SUPPORTED, PackageValidationSeverity.INFO, True,
                               f"source_type={st}"))
        return c

    def _check_url_format(self, req: PackageValidationRequest) -> list[PackageValidationCheck]:
        c = []
        urls = []
        if req.package_url: urls.append(("package_url", req.package_url))
        if req.repository_url: urls.append(("repository_url", req.repository_url))
        if not urls:
            c.append(self._chk(PackageValidationCheckCode.URL_FORMAT_VALID, PackageValidationSeverity.INFO, True,
                               "No URL to validate."))
            return c
        for label, url in urls:
            try:
                p = urlparse(url)
                if not p.hostname:
                    c.append(self._chk(PackageValidationCheckCode.URL_FORMAT_VALID, PackageValidationSeverity.ERROR, False,
                                       f"[{label}] URL has no hostname: {url}"))
                    continue
                if p.scheme not in _ALLOWED_SCHEMES:
                    c.append(self._chk(PackageValidationCheckCode.HTTPS_REQUIRED, PackageValidationSeverity.ERROR, False,
                                       f"[{label}] Only HTTPS allowed, got: {p.scheme}"))
                    continue
                if p.hostname in _BLOCKED_HOSTS:
                    c.append(self._chk(PackageValidationCheckCode.DOMAIN_BLOCKED, PackageValidationSeverity.BLOCKER, False,
                                       f"[{label}] Domain is blocked: {p.hostname}"))
                    continue
                # Private IP check
                if self._is_private_ip(p.hostname):
                    c.append(self._chk(PackageValidationCheckCode.DOMAIN_BLOCKED, PackageValidationSeverity.BLOCKER, False,
                                       f"[{label}] Private IP not allowed: {p.hostname}"))
                    continue
                c.append(self._chk(PackageValidationCheckCode.URL_FORMAT_VALID, PackageValidationSeverity.INFO, True,
                                   f"[{label}] URL format validated."))
            except Exception:
                c.append(self._chk(PackageValidationCheckCode.URL_FORMAT_VALID, PackageValidationSeverity.ERROR, False,
                                   f"[{label}] Invalid URL format: {url}"))
        return c

    def _check_domain_policy(self, req: PackageValidationRequest) -> list[PackageValidationCheck]:
        c = []
        url = req.package_url or req.repository_url
        if not url: return c
        try:
            host = urlparse(url).hostname or ""
        except Exception:
            return c
        denied = req.validation_options.get("denied_domains", [])
        for d in denied:
            if host == d or host.endswith("." + d):
                c.append(self._chk(PackageValidationCheckCode.DOMAIN_BLOCKED, PackageValidationSeverity.BLOCKER, False,
                                   f"Domain '{host}' matches denied: '{d}'"))
                return c
        allowed = req.validation_options.get("allowed_domains", [])
        if allowed:
            match = any(host == a or host.endswith("." + a) for a in allowed)
            c.append(self._chk(PackageValidationCheckCode.DOMAIN_ALLOWED,
                               PackageValidationSeverity.INFO if match else PackageValidationSeverity.ERROR,
                               match, f"Domain '{host}' {'allowed' if match else 'not in allowed_domains'}"))
        else:
            c.append(self._chk(PackageValidationCheckCode.DOMAIN_ALLOWED, PackageValidationSeverity.INFO, True,
                               f"Domain '{host}' (no allowlist configured)"))
        return c

    def _check_checksum(self, req: PackageValidationRequest) -> list[PackageValidationCheck]:
        c = []
        if not req.package_url:
            c.append(self._chk(PackageValidationCheckCode.CHECKSUM_DECLARED, PackageValidationSeverity.INFO, True, "No package_url — checksum not required."))
            return c
        mm = req.manifest_metadata
        cs = mm.get("package_checksum", "")
        algo = mm.get("package_checksum_algorithm", "sha256")
        if not cs:
            c.append(self._chk(PackageValidationCheckCode.CHECKSUM_DECLARED, PackageValidationSeverity.WARNING, False,
                               "package_url present but package_checksum not declared in manifest metadata."))
        else:
            algo_ok = algo in _ALLOWED_CHECKSUM_ALGOS
            c.append(self._chk(PackageValidationCheckCode.CHECKSUM_DECLARED,
                               PackageValidationSeverity.INFO if algo_ok else PackageValidationSeverity.ERROR,
                               algo_ok, f"Checksum declared (algorithm={algo})" + ("" if algo_ok else f" — not in {_ALLOWED_CHECKSUM_ALGOS}")))
        return c

    def _check_signature(self, req: PackageValidationRequest) -> list[PackageValidationCheck]:
        c = []
        if not req.package_url:
            c.append(self._chk(PackageValidationCheckCode.SIGNATURE_DECLARED, PackageValidationSeverity.INFO, True, "No package_url — signature not required."))
            return c
        mm = req.manifest_metadata
        sig = mm.get("package_signature", "")
        algo = mm.get("package_signature_algorithm", "")
        if not sig:
            c.append(self._chk(PackageValidationCheckCode.SIGNATURE_DECLARED, PackageValidationSeverity.WARNING, False,
                               "package_url present but package_signature not declared."))
        elif algo and algo not in _ALLOWED_SIGNATURE_ALGOS:
            c.append(self._chk(PackageValidationCheckCode.SIGNATURE_DECLARED, PackageValidationSeverity.ERROR, False,
                               f"Signature algorithm '{algo}' not supported ({_ALLOWED_SIGNATURE_ALGOS})"))
        else:
            c.append(self._chk(PackageValidationCheckCode.SIGNATURE_DECLARED, PackageValidationSeverity.INFO, True, "Signature declared."))
        return c

    def _check_manifest_consistency(self, req: PackageValidationRequest) -> list[PackageValidationCheck]:
        c = []
        mm = req.manifest_metadata
        pn = mm.get("package_name", "")
        pv = mm.get("package_version", "")
        if pn and pn != req.manifest_name:
            c.append(self._chk(PackageValidationCheckCode.PACKAGE_NAME_MATCH, PackageValidationSeverity.WARNING, False,
                               f"package_name '{pn}' != manifest.name '{req.manifest_name}'"))
        else:
            c.append(self._chk(PackageValidationCheckCode.PACKAGE_NAME_MATCH, PackageValidationSeverity.INFO, True, "Package name matches."))
        if pv and pv != req.manifest_version:
            c.append(self._chk(PackageValidationCheckCode.PACKAGE_VERSION_MATCH, PackageValidationSeverity.WARNING, False,
                               f"package_version '{pv}' != manifest.version '{req.manifest_version}'"))
        else:
            c.append(self._chk(PackageValidationCheckCode.PACKAGE_VERSION_MATCH, PackageValidationSeverity.INFO, True, "Version matches."))
        lic = mm.get("license", "")
        c.append(self._chk(PackageValidationCheckCode.LICENSE_DECLARED,
                           PackageValidationSeverity.INFO if lic else PackageValidationSeverity.WARNING,
                           bool(lic), "License " + ("declared: " + lic if lic else "not declared.")))
        sc = mm.get("security_contact", "")
        c.append(self._chk(PackageValidationCheckCode.SECURITY_CONTACT_DECLARED,
                           PackageValidationSeverity.INFO if sc else PackageValidationSeverity.WARNING,
                           bool(sc), "Security contact " + ("declared." if sc else "not declared.")))
        return c

    def _check_dependencies(self, req: PackageValidationRequest) -> list[PackageValidationCheck]:
        c = []
        deps = req.manifest_metadata.get("dependencies")
        if deps is None:
            if req.package_url:
                c.append(self._chk(PackageValidationCheckCode.DEPENDENCIES_DECLARED, PackageValidationSeverity.WARNING, False,
                                   "package_url present but dependencies not declared."))
            else:
                c.append(self._chk(PackageValidationCheckCode.DEPENDENCIES_DECLARED, PackageValidationSeverity.INFO, True, "No dependencies to check."))
            return c
        if not isinstance(deps, list):
            c.append(self._chk(PackageValidationCheckCode.DEPENDENCIES_DECLARED, PackageValidationSeverity.ERROR, False,
                               "dependencies must be a list."))
            return c
        empty = [d for d in deps if isinstance(d, str) and not d.strip()]
        if empty:
            c.append(self._chk(PackageValidationCheckCode.DEPENDENCIES_DECLARED, PackageValidationSeverity.ERROR, False,
                               f"Dependencies contain {len(empty)} empty entries."))
        else:
            c.append(self._chk(PackageValidationCheckCode.DEPENDENCIES_DECLARED, PackageValidationSeverity.INFO, True,
                               f"Dep check list_len={len(deps)} (no CVE scan)."))
        return c

    def _check_runtime_sandbox(self, req: PackageValidationRequest) -> list[PackageValidationCheck]:
        c = []
        rt = req.manifest_runtime_type
        if rt and rt != "manifest_only":
            c.append(self._chk(PackageValidationCheckCode.RUNTIME_TYPE_SUPPORTED, PackageValidationSeverity.BLOCKER, False,
                               f"runtime_type='{rt}' not supported in MVP. Only 'manifest_only' allowed."))
        else:
            c.append(self._chk(PackageValidationCheckCode.RUNTIME_TYPE_SUPPORTED, PackageValidationSeverity.INFO, True, "runtime_type=manifest_only."))

        mm = req.manifest_metadata
        if mm.get("requires_network"):
            c.append(self._chk(PackageValidationCheckCode.NETWORK_REQUIREMENTS_DECLARED, PackageValidationSeverity.ERROR, False,
                               "requires_network=true — network access requested but not supported in MVP."))
        if mm.get("reads_user_data"):
            c.append(self._chk(PackageValidationCheckCode.USER_DATA_ACCESS_DECLARED, PackageValidationSeverity.WARNING, False,
                               "reads_user_data=true — user data access requested."))
        if mm.get("writes_user_data"):
            c.append(self._chk(PackageValidationCheckCode.USER_DATA_ACCESS_DECLARED, PackageValidationSeverity.ERROR, False,
                               "writes_user_data=true — user data write requested."))
        return c

    # ═══════════════════════ Helpers ═══════════════════════

    @staticmethod
    def _is_private_ip(host: str) -> bool:
        import ipaddress
        try:
            addr = ipaddress.ip_address(host)
            return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_unspecified
        except ValueError:
            return False

    def _compute_status(self, result: PackageValidationResult):
        if result.blockers:
            result.status = PackageValidationStatus.BLOCKED
            result.review_recommendation = "Reject or request changes. Blockers found."
        elif result.errors:
            result.status = PackageValidationStatus.FAILED
            result.review_recommendation = "Request changes before approval. Errors found."
        elif result.warnings:
            result.status = PackageValidationStatus.PASSED_WITH_WARNINGS
            result.review_recommendation = "Reviewer should inspect warnings before approval."
        else:
            result.status = PackageValidationStatus.PASSED
            result.review_recommendation = "Package metadata validation passed. Proceed with review."

    def _try_usage(self, result: PackageValidationResult):
        if self._usage_store is None: return
        try:
            self._usage_store.record_event(UsageEvent(
                tenant_id=result.tenant_id, user_id=result.requested_by, workspace_id=result.tenant_id,
                resource=UsageResource.PACKAGE_VALIDATION_RUN, quantity=1, unit=UsageUnit.COUNT,
                metadata={
                    "validation_id": result.validation_id, "submission_id": result.submission_id,
                    "tenant_id": result.tenant_id, "status": result.status,
                    "warning_count": len(result.warnings), "error_count": len(result.errors),
                    "blocker_count": len(result.blockers),
                    "no_download_performed": True, "no_execution_performed": True,
                },
            ))
        except Exception:
            logger.warning("pv_usage_failed", exc_info=True)
