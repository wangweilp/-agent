"""Sandbox v2 MicroVM Policy Engine — Step 11 MicroVM / Firecracker PoC.

所有 MicroVM 执行都必须经过此 policy。
默认 deny。任一条件不满足 → rejected/unavailable。
"""

from __future__ import annotations

import logging

from src.open_platform.sandbox_v2.models import (
    SandboxV2RiskLevel,
    SandboxMicroVMRuntime,
    SandboxMicroVMExecutionStatus,
    SandboxMicroVMExecutionPlan,
    TRUSTED_MICROVM_FIXTURES,
)

logger = logging.getLogger(__name__)


def evaluate_microvm_policy(
    plan: SandboxMicroVMExecutionPlan,
    *,
    microvm_execution_enabled: bool = False,
    run_microvm_integration: bool = False,
    is_linux: bool = False,
    has_kvm: bool = False,
    firecracker_binary_present: bool = False,
    kernel_present: bool = False,
    rootfs_present: bool = False,
    network_enabled: bool = False,
    allow_user_kernel: bool = False,
    allow_user_rootfs: bool = False,
    allow_host_mounts: bool = False,
) -> dict:
    """评估 MicroVM 执行策略。

    返回 (allowed: bool, status: str, reason: str, risk_level: str, matched_rules: list[str])
    """
    try:
        return _eval_impl(
            plan,
            microvm_execution_enabled=microvm_execution_enabled,
            run_microvm_integration=run_microvm_integration,
            is_linux=is_linux, has_kvm=has_kvm,
            firecracker_binary_present=firecracker_binary_present,
            kernel_present=kernel_present, rootfs_present=rootfs_present,
            network_enabled=network_enabled,
            allow_user_kernel=allow_user_kernel,
            allow_user_rootfs=allow_user_rootfs,
            allow_host_mounts=allow_host_mounts,
        )
    except Exception:
        logger.exception("microvm_policy_failed")
        return {
            "allowed": False, "status": SandboxMicroVMExecutionStatus.REJECTED,
            "reason": "MicroVM policy exception — fail closed.",
            "risk_level": SandboxV2RiskLevel.CRITICAL,
            "matched_rules": ["exception_fail_closed"],
        }


def _eval_impl(plan, **kw) -> dict:
    matched: list[str] = []

    # Rule 1: MicroVM execution must be enabled
    if not kw.get("microvm_execution_enabled", False):
        return {
            "allowed": False, "status": SandboxMicroVMExecutionStatus.DISABLED,
            "reason": "MicroVM execution is disabled. Set SANDBOX_V2_MICROVM_EXECUTION_ENABLED=true.",
            "risk_level": SandboxV2RiskLevel.LOW,
            "matched_rules": [*matched, "microvm_disabled"],
        }
    matched.append("microvm_enabled")

    # Rule 2: Integration must be enabled for real execution
    if not kw.get("run_microvm_integration", False):
        return {
            "allowed": False, "status": SandboxMicroVMExecutionStatus.DISABLED,
            "reason": "MicroVM integration is disabled. Set SANDBOX_V2_RUN_MICROVM_INTEGRATION=true for real execution.",
            "risk_level": SandboxV2RiskLevel.LOW,
            "matched_rules": [*matched, "microvm_integration_disabled"],
        }
    matched.append("microvm_integration_enabled")

    # Rule 3: Must be Linux
    if not kw.get("is_linux", False):
        return {
            "allowed": False, "status": SandboxMicroVMExecutionStatus.UNAVAILABLE,
            "reason": "MicroVM execution requires Linux + KVM. Current platform is not Linux.",
            "risk_level": SandboxV2RiskLevel.MEDIUM,
            "matched_rules": [*matched, "platform_not_linux"],
        }
    matched.append("platform_linux")

    # Rule 4: Must have KVM
    if not kw.get("has_kvm", False):
        return {
            "allowed": False, "status": SandboxMicroVMExecutionStatus.UNAVAILABLE,
            "reason": "/dev/kvm not available. MicroVM execution requires KVM.",
            "risk_level": SandboxV2RiskLevel.MEDIUM,
            "matched_rules": [*matched, "kvm_unavailable"],
        }
    matched.append("kvm_available")

    # Rule 5: Firecracker binary must exist
    if not kw.get("firecracker_binary_present", False):
        return {
            "allowed": False, "status": SandboxMicroVMExecutionStatus.UNAVAILABLE,
            "reason": "Firecracker binary not found. Install Firecracker or set SANDBOX_V2_FIRECRACKER_BIN_PATH.",
            "risk_level": SandboxV2RiskLevel.HIGH,
            "matched_rules": [*matched, "firecracker_binary_missing"],
        }
    matched.append("firecracker_binary_present")

    # Rule 6: Kernel must exist
    if not kw.get("kernel_present", False):
        return {
            "allowed": False, "status": SandboxMicroVMExecutionStatus.UNAVAILABLE,
            "reason": "MicroVM kernel not found. Set SANDBOX_V2_FIRECRACKER_KERNEL_PATH.",
            "risk_level": SandboxV2RiskLevel.HIGH,
            "matched_rules": [*matched, "kernel_missing"],
        }
    matched.append("kernel_present")

    # Rule 7: Rootfs must exist
    if not kw.get("rootfs_present", False):
        return {
            "allowed": False, "status": SandboxMicroVMExecutionStatus.UNAVAILABLE,
            "reason": "MicroVM rootfs not found. Set SANDBOX_V2_FIRECRACKER_ROOTFS_PATH.",
            "risk_level": SandboxV2RiskLevel.HIGH,
            "matched_rules": [*matched, "rootfs_missing"],
        }
    matched.append("rootfs_present")

    # Rule 8: Network must be disabled
    if kw.get("network_enabled", False) or plan.network_enabled:
        return {
            "allowed": False, "status": SandboxMicroVMExecutionStatus.REJECTED,
            "reason": "MicroVM network must be disabled. SANDBOX_V2_MICROVM_NETWORK_ENABLED must be false.",
            "risk_level": SandboxV2RiskLevel.HIGH,
            "matched_rules": [*matched, "network_rejected"],
        }
    matched.append("network_disabled")

    # Rule 9: No user kernel allowed
    if kw.get("allow_user_kernel", False):
        return {
            "allowed": False, "status": SandboxMicroVMExecutionStatus.REJECTED,
            "reason": "User-provided kernel is not allowed. Use admin-configured kernel only.",
            "risk_level": SandboxV2RiskLevel.CRITICAL,
            "matched_rules": [*matched, "user_kernel_rejected"],
        }
    matched.append("user_kernel_denied")

    # Rule 10: No user rootfs allowed
    if kw.get("allow_user_rootfs", False):
        return {
            "allowed": False, "status": SandboxMicroVMExecutionStatus.REJECTED,
            "reason": "User-provided rootfs is not allowed. Use admin-configured rootfs only.",
            "risk_level": SandboxV2RiskLevel.CRITICAL,
            "matched_rules": [*matched, "user_rootfs_rejected"],
        }
    matched.append("user_rootfs_denied")

    # Rule 11: No host mounts allowed
    if kw.get("allow_host_mounts", False):
        return {
            "allowed": False, "status": SandboxMicroVMExecutionStatus.REJECTED,
            "reason": "Host mounts are not allowed for MicroVM execution.",
            "risk_level": SandboxV2RiskLevel.CRITICAL,
            "matched_rules": [*matched, "host_mounts_rejected"],
        }
    matched.append("host_mounts_denied")

    # Rule 12: Only trusted fixtures
    if not plan.fixture_id:
        return {
            "allowed": False, "status": SandboxMicroVMExecutionStatus.REJECTED,
            "reason": "MicroVM execution requires a fixture_id. User commands are not allowed.",
            "risk_level": SandboxV2RiskLevel.HIGH,
            "matched_rules": [*matched, "missing_fixture_id"],
        }
    if plan.fixture_id not in TRUSTED_MICROVM_FIXTURES:
        return {
            "allowed": False, "status": SandboxMicroVMExecutionStatus.REJECTED,
            "reason": f"Fixture '{plan.fixture_id}' is not a trusted MicroVM fixture. Allowed: {sorted(TRUSTED_MICROVM_FIXTURES.keys())}.",
            "risk_level": SandboxV2RiskLevel.HIGH,
            "matched_rules": [*matched, "untrusted_fixture_rejected"],
        }
    matched.append("trusted_fixture_valid")

    # All checks passed — preflight OK, can attempt real execution
    return {
        "allowed": True,
        "status": SandboxMicroVMExecutionStatus.PREFLIGHT_PASSED,
        "reason": "MicroVM policy passed. Preflight checks satisfied. Trusted fixture only.",
        "risk_level": SandboxV2RiskLevel.LOW,
        "matched_rules": matched,
    }
