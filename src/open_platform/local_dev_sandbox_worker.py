"""LocalDevSandboxPrototypeWorker — dry-run only, fail-closed local dev worker。

Step 24-G: DRY_RUN_ONLY, is_successful_execution()=False.
不 subprocess/container/network/file/secrets。"""

from __future__ import annotations

from src.open_platform.sandbox_worker import (
    SandboxWorker, SandboxWorkerAvailability, SandboxWorkerCheck, SandboxWorkerDecision,
    SandboxWorkerRequest, SandboxWorkerResult, SandboxWorkerResultStatus,
    SandboxWorkerType,
)
from src.open_platform.local_dev_sandbox import (
    LocalDevSandboxCheck, LocalDevSandboxCheckStatus, LocalDevSandboxCheckType,
    LocalDevSandboxConfig, LocalDevSandboxDecision, LocalDevSandboxMode,
    LocalDevSandboxSeverity,
)


class LocalDevSandboxPrototypeWorker(SandboxWorker):
    """Local dev dry-run prototype worker — disabled by default, fail-closed always。"""

    def __init__(self, config: LocalDevSandboxConfig | None = None):
        self._config = config or LocalDevSandboxConfig.disabled()

    def get_worker_type(self) -> str:
        return SandboxWorkerType.LOCAL_DEV_DRY_RUN if hasattr(SandboxWorkerType, 'LOCAL_DEV_DRY_RUN') else "local_dev_dry_run"

    def get_availability(self) -> str:
        if self._config.enabled and self._config.mode == LocalDevSandboxMode.DRY_RUN_ONLY:
            return SandboxWorkerAvailability.DEGRADED  # dry-run only, not really available
        return SandboxWorkerAvailability.DISABLED

    def evaluate_request(self, request: SandboxWorkerRequest) -> SandboxWorkerResult:
        result = SandboxWorkerResult(
            request_id=request.request_id, plan_id=request.plan_id,
            tenant_id=request.tenant_id,
            worker_type=self.get_worker_type(),
            availability=self.get_availability(),
            no_download_used=True, no_network_used=True, no_execution_performed=True,
            no_subprocess_used=True, no_container_used=True,
            no_agent_runtime_used=True, no_agent_registry_used=True,
        )

        # Check 0: disabled
        if not self._config.enabled or self._config.mode == LocalDevSandboxMode.DISABLED:
            result.add_check(_chk(LocalDevSandboxCheckType.LOCAL_DEV_DISABLED, LocalDevSandboxCheckStatus.BLOCKED,
                                  LocalDevSandboxSeverity.BLOCKER, "Local dev sandbox is DISABLED."))
            result.add_check(_chk(LocalDevSandboxCheckType.FAIL_CLOSED, LocalDevSandboxCheckStatus.PASSED,
                                  LocalDevSandboxSeverity.INFO, "Fail-closed: worker refused."))
            result.status = SandboxWorkerResultStatus.BLOCKED
            result.decision = SandboxWorkerDecision.BLOCKED_DISABLED
            result.calculate_status()
            return result

        # Dry-run mode
        result.add_check(_chk(LocalDevSandboxCheckType.DRY_RUN_ONLY_MODE, LocalDevSandboxCheckStatus.PASSED,
                              LocalDevSandboxSeverity.INFO, "Running in DRY_RUN_ONLY mode. No real execution."))

        # Policy config check
        snap = getattr(request, "policy_config_snapshot", None) or request.metadata.get("policy_config_snapshot", {})
        has_policy = isinstance(snap, dict) and snap
        if not has_policy:
            result.add_check(_chk(LocalDevSandboxCheckType.POLICY_CONFIG_PRESENT, LocalDevSandboxCheckStatus.BLOCKED,
                                  LocalDevSandboxSeverity.BLOCKER, "No policy_config_snapshot in request."))
            result.add_check(_chk(LocalDevSandboxCheckType.FAIL_CLOSED, LocalDevSandboxCheckStatus.PASSED,
                                  LocalDevSandboxSeverity.INFO, "Fail-closed: policy config missing."))
            result.status = SandboxWorkerResultStatus.BLOCKED
            result.decision = SandboxWorkerDecision.BLOCKED_POLICY_NOT_ENFORCEABLE
            result.calculate_status()
            return result

        enforceable = snap.get("enforceable", False)
        if not enforceable:
            result.add_check(_chk(LocalDevSandboxCheckType.POLICY_CONFIG_ENFORCEABLE, LocalDevSandboxCheckStatus.BLOCKED,
                                  LocalDevSandboxSeverity.BLOCKER, "Policy config is not enforceable."))
            result.add_check(_chk(LocalDevSandboxCheckType.FAIL_CLOSED, LocalDevSandboxCheckStatus.PASSED,
                                  LocalDevSandboxSeverity.INFO, "Fail-closed: policy not enforceable."))
            result.status = SandboxWorkerResultStatus.BLOCKED
            result.decision = SandboxWorkerDecision.BLOCKED_POLICY_NOT_ENFORCEABLE
            result.calculate_status()
            return result

        result.add_check(_chk(LocalDevSandboxCheckType.POLICY_CONFIG_PRESENT, LocalDevSandboxCheckStatus.PASSED,
                              LocalDevSandboxSeverity.INFO, "Policy config snapshot present and enforceable."))

        # Network deny
        nw = snap.get("network", {})
        if nw.get("allow_network"):
            result.add_check(_chk(LocalDevSandboxCheckType.NETWORK_DENY_CONFIRMED, LocalDevSandboxCheckStatus.BLOCKED,
                                  LocalDevSandboxSeverity.BLOCKER, "Network access requested but not supported."))
            result.add_check(_chk(LocalDevSandboxCheckType.FAIL_CLOSED, LocalDevSandboxCheckStatus.PASSED,
                                  LocalDevSandboxSeverity.INFO, "Fail-closed: network denied."))
            result.status = SandboxWorkerResultStatus.BLOCKED
            result.decision = SandboxWorkerDecision.BLOCKED_POLICY_NOT_ENFORCEABLE
            result.calculate_status()
            return result
        result.add_check(_chk(LocalDevSandboxCheckType.NETWORK_DENY_CONFIRMED, LocalDevSandboxCheckStatus.PASSED,
                              LocalDevSandboxSeverity.INFO, "Network: DENY_ALL confirmed."))

        # Secrets deny
        sc = snap.get("secrets", {})
        if sc.get("allow_secrets"):
            result.add_check(_chk(LocalDevSandboxCheckType.SECRETS_DENY_CONFIRMED, LocalDevSandboxCheckStatus.BLOCKED,
                                  LocalDevSandboxSeverity.BLOCKER, "Secrets access requested but not supported."))
            result.add_check(_chk(LocalDevSandboxCheckType.FAIL_CLOSED, LocalDevSandboxCheckStatus.PASSED,
                                  LocalDevSandboxSeverity.INFO, "Fail-closed: secrets denied."))
            result.status = SandboxWorkerResultStatus.BLOCKED
            result.decision = SandboxWorkerDecision.BLOCKED_POLICY_NOT_ENFORCEABLE
            result.calculate_status()
            return result
        result.add_check(_chk(LocalDevSandboxCheckType.SECRETS_DENY_CONFIRMED, LocalDevSandboxCheckStatus.PASSED,
                              LocalDevSandboxSeverity.INFO, "Secrets: DENY_ALL confirmed."))

        # Filesystem safe
        fs = snap.get("filesystem", {})
        if fs.get("allow_read") or fs.get("allow_write"):
            result.add_check(_chk(LocalDevSandboxCheckType.FILESYSTEM_SAFE_CONFIRMED, LocalDevSandboxCheckStatus.BLOCKED,
                                  LocalDevSandboxSeverity.BLOCKER, "Filesystem access requested but not supported."))
            result.add_check(_chk(LocalDevSandboxCheckType.FAIL_CLOSED, LocalDevSandboxCheckStatus.PASSED,
                                  LocalDevSandboxSeverity.INFO, "Fail-closed: filesystem denied."))
            result.status = SandboxWorkerResultStatus.BLOCKED
            result.decision = SandboxWorkerDecision.BLOCKED_POLICY_NOT_ENFORCEABLE
            result.calculate_status()
            return result
        result.add_check(_chk(LocalDevSandboxCheckType.FILESYSTEM_SAFE_CONFIRMED, LocalDevSandboxCheckStatus.PASSED,
                              LocalDevSandboxSeverity.INFO, "Filesystem: safe (DENY_ALL)."))

        # Data access
        da = snap.get("data_access", {})
        mode = da.get("mode", "")
        if mode not in ("deny_all", ""):
            result.add_check(_chk(LocalDevSandboxCheckType.DATA_ACCESS_BROKER_RESERVED, LocalDevSandboxCheckStatus.BLOCKED,
                                  LocalDevSandboxSeverity.BLOCKER, f"Data access mode '{mode}' not supported."))
            result.add_check(_chk(LocalDevSandboxCheckType.FAIL_CLOSED, LocalDevSandboxCheckStatus.PASSED,
                                  LocalDevSandboxSeverity.INFO, "Fail-closed: data access denied."))
            result.status = SandboxWorkerResultStatus.BLOCKED
            result.decision = SandboxWorkerDecision.BLOCKED_POLICY_NOT_ENFORCEABLE
            result.calculate_status()
            return result
        result.add_check(_chk(LocalDevSandboxCheckType.DATA_ACCESS_BROKER_RESERVED, LocalDevSandboxCheckStatus.PASSED,
                              LocalDevSandboxSeverity.INFO, "Data access: DENY_ALL (safe)."))

        # All safety checks passed — dry-run reserved only
        result.add_check(_chk(LocalDevSandboxCheckType.NO_PACKAGE_DOWNLOAD, LocalDevSandboxCheckStatus.PASSED,
                              LocalDevSandboxSeverity.INFO, "No package download."))
        result.add_check(_chk(LocalDevSandboxCheckType.NO_PACKAGE_EXECUTION, LocalDevSandboxCheckStatus.PASSED,
                              LocalDevSandboxSeverity.INFO, "No package execution."))
        result.add_check(_chk(LocalDevSandboxCheckType.NO_ENTRYPOINT_EXECUTION, LocalDevSandboxCheckStatus.PASSED,
                              LocalDevSandboxSeverity.INFO, "No entrypoint execution."))
        result.add_check(_chk(LocalDevSandboxCheckType.NO_NETWORK_USED, LocalDevSandboxCheckStatus.PASSED,
                              LocalDevSandboxSeverity.INFO, "No network used."))
        result.add_check(_chk(LocalDevSandboxCheckType.NO_SUBPROCESS_USED, LocalDevSandboxCheckStatus.PASSED,
                              LocalDevSandboxSeverity.INFO, "No subprocess used."))
        result.add_check(_chk(LocalDevSandboxCheckType.NO_CONTAINER_USED, LocalDevSandboxCheckStatus.PASSED,
                              LocalDevSandboxSeverity.INFO, "No container used."))
        result.add_check(_chk(LocalDevSandboxCheckType.NO_FILE_READ, LocalDevSandboxCheckStatus.PASSED,
                              LocalDevSandboxSeverity.INFO, "No file read."))
        result.add_check(_chk(LocalDevSandboxCheckType.NO_AGENT_RUNTIME_USED, LocalDevSandboxCheckStatus.PASSED,
                              LocalDevSandboxSeverity.INFO, "AgentRuntime not called."))
        result.add_check(_chk(LocalDevSandboxCheckType.NO_AGENT_REGISTRY_USED, LocalDevSandboxCheckStatus.PASSED,
                              LocalDevSandboxSeverity.INFO, "AgentRegistry not called."))
        result.add_check(_chk(LocalDevSandboxCheckType.FAIL_CLOSED, LocalDevSandboxCheckStatus.PASSED,
                              LocalDevSandboxSeverity.INFO, "Fail-closed safety net active. Dry-run only."))

        result.output_json = {"dry_run": True, "plan_id": request.plan_id,
                              "request_id": request.request_id,
                              "policy_config_enforceable": True,
                              "message": "Local dev dry-run completed without executing code."}
        result.status = SandboxWorkerResultStatus.RESERVED
        result.decision = SandboxWorkerDecision.RESERVED_ONLY
        result.calculate_status()
        return result


def _chk(ct, status, sev, msg, **kw):
    return SandboxWorkerCheck(check_type=str(ct), status=str(status), severity=str(sev), message=msg, metadata=kw)
