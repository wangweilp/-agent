"""Disabled Sandbox Worker Stub — fail-closed disabled worker。

Step 24-E: 唯一实现的 worker。永远 blocked。永不执行代码。
- worker_type = DISABLED_STUB
- availability = DISABLED
- evaluate_request → BLOCKED_DISABLED
- 无 execute/run/dispatch 方法
- 无 subprocess/container/network/file access
"""

from __future__ import annotations

from src.open_platform.sandbox_worker import (
    SandboxWorker, SandboxWorkerAvailability, SandboxWorkerCheck,
    SandboxWorkerCheckStatus, SandboxWorkerCheckType, SandboxWorkerDecision,
    SandboxWorkerRequest, SandboxWorkerResult, SandboxWorkerResultStatus,
    SandboxWorkerSeverity, SandboxWorkerType,
)


class DisabledSandboxWorker(SandboxWorker):
    """Fail-closed disabled worker — 所有请求被 block。"""

    def get_worker_type(self) -> str:
        return SandboxWorkerType.DISABLED_STUB

    def get_availability(self) -> str:
        return SandboxWorkerAvailability.DISABLED

    def evaluate_request(self, request: SandboxWorkerRequest) -> SandboxWorkerResult:
        result = SandboxWorkerResult(
            request_id=request.request_id, plan_id=request.plan_id,
            tenant_id=request.tenant_id,
            worker_type=self.get_worker_type(),
            availability=self.get_availability(),
            status=SandboxWorkerResultStatus.BLOCKED,
            decision=SandboxWorkerDecision.BLOCKED_DISABLED,
            no_download_used=True, no_network_used=True,
            no_execution_performed=True, no_subprocess_used=True,
            no_container_used=True, no_agent_runtime_used=True,
            no_agent_registry_used=True,
            output_json={},
        )

        # Core checks
        result.add_check(_chk(SandboxWorkerCheckType.WORKER_DISABLED,
                              SandboxWorkerCheckStatus.BLOCKED, SandboxWorkerSeverity.BLOCKER,
                              "Sandbox worker is DISABLED. No sandbox execution available in Step 24-E."))

        # Safety flags (all passed — worker does nothing)
        result.add_check(_chk(SandboxWorkerCheckType.NO_PACKAGE_DOWNLOAD,
                              SandboxWorkerCheckStatus.PASSED, SandboxWorkerSeverity.INFO,
                              "No package download performed."))
        result.add_check(_chk(SandboxWorkerCheckType.NO_NETWORK_USED,
                              SandboxWorkerCheckStatus.PASSED, SandboxWorkerSeverity.INFO,
                              "No network used."))
        result.add_check(_chk(SandboxWorkerCheckType.NO_EXECUTION_PERFORMED,
                              SandboxWorkerCheckStatus.PASSED, SandboxWorkerSeverity.INFO,
                              "No code execution performed."))
        result.add_check(_chk(SandboxWorkerCheckType.NO_SUBPROCESS_USED,
                              SandboxWorkerCheckStatus.PASSED, SandboxWorkerSeverity.INFO,
                              "No subprocess launched."))
        result.add_check(_chk(SandboxWorkerCheckType.NO_CONTAINER_USED,
                              SandboxWorkerCheckStatus.PASSED, SandboxWorkerSeverity.INFO,
                              "No container launched."))
        result.add_check(_chk(SandboxWorkerCheckType.NO_AGENT_RUNTIME_USED,
                              SandboxWorkerCheckStatus.PASSED, SandboxWorkerSeverity.INFO,
                              "AgentRuntime not called."))
        result.add_check(_chk(SandboxWorkerCheckType.NO_AGENT_REGISTRY_USED,
                              SandboxWorkerCheckStatus.PASSED, SandboxWorkerSeverity.INFO,
                              "AgentRegistry not called."))
        result.add_check(_chk(SandboxWorkerCheckType.FAIL_CLOSED,
                              SandboxWorkerCheckStatus.PASSED, SandboxWorkerSeverity.INFO,
                              "Fail-closed: worker refused execution. This is correct behavior in Step 24-E."))

        result.calculate_status()
        return result


def _chk(ct, status, sev, msg, **kw):
    return SandboxWorkerCheck(check_type=ct, status=status, severity=sev, message=msg, metadata=kw)
