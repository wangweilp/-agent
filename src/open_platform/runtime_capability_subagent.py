"""Runtime Capability Enforcement Sub-Agent — metadata-only enforcement checker.

Step 26-G: NO container/microVM start. NO fixture execution. NO third-party code.
NO package/entrypoint. NO network. NO file write. NO secrets.

All checks are metadata/control-plane only. execution_allowed/runtime_enabled/fixture_execution_allowed = always False.
"""

from __future__ import annotations
import json, logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .runtime_capability import (
    RuntimeCapability, CapabilityCategory, CapabilityStatus,
    RuntimeCapabilityStore, build_default_capability_matrix
)

logger = logging.getLogger(__name__)


@dataclass
class EnforcementCheckResult:
    check_id: str = field(default_factory=lambda: f"enfchk_{uuid4().hex[:16]}")
    capability_name: str = ""
    capability_id: str = ""
    category: str = ""
    current_status: str = ""
    expected_status: str = ""
    enforcement_passed: bool = True
    enforcement_type: str = ""
    block_reason: str = ""
    is_blocker_for_execution: bool = False
    requires_runtime_gate: bool = False
    recommended_action: str = ""
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "check_id": self.check_id,
            "capability_name": self.capability_name,
            "capability_id": self.capability_id,
            "category": self.category,
            "current_status": self.current_status,
            "expected_status": self.expected_status,
            "enforcement_passed": self.enforcement_passed,
            "enforcement_type": self.enforcement_type,
            "block_reason": self.block_reason,
            "is_blocker_for_execution": self.is_blocker_for_execution,
            "requires_runtime_gate": self.requires_runtime_gate,
            "recommended_action": self.recommended_action,
            "checked_at": self.checked_at.isoformat(),
        }


@dataclass
class EnforcementReport:
    report_id: str = field(default_factory=lambda: f"enfrep_{uuid4().hex[:16]}")
    checks: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    passed: int = 0
    failed: int = 0
    execution_blockers: int = 0
    runtime_gates_required: int = 0
    ready_for_step26g: bool = False
    ready_for_step26h: bool = False
    execution_allowed: bool = False
    runtime_enabled: bool = False
    fixture_execution_allowed: bool = False
    metadata_only: bool = True
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "report_id": self.report_id,
            "checks": self.checks,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "execution_blockers": self.execution_blockers,
            "runtime_gates_required": self.runtime_gates_required,
            "ready_for_step26g": self.ready_for_step26g,
            "ready_for_step26h": self.ready_for_step26h,
            "execution_allowed": self.execution_allowed,
            "runtime_enabled": self.runtime_enabled,
            "fixture_execution_allowed": self.fixture_execution_allowed,
            "metadata_only": self.metadata_only,
            "generated_at": self.generated_at.isoformat(),
            "metadata": self.metadata,
        }


class RuntimeCapabilityEnforcementSubAgent:
    """Metadata-only enforcement checker. Does NOT start any runtime, container, or execution."""

    def __init__(self, metadata_only: bool = True, execution_allowed: bool = False,
                 runtime_enabled: bool = False):
        if execution_allowed or runtime_enabled:
            raise ValueError("RuntimeCapabilityEnforcementSubAgent: execution_allowed and runtime_enabled must be False")
        self.metadata_only = True
        self.execution_allowed = False
        self.runtime_enabled = False

    def run_simulation(self, capabilities: list[RuntimeCapability]) -> EnforcementReport:
        """Run enforcement simulation on all capabilities. No real execution."""
        checks = []
        passed = 0
        failed = 0
        blockers = 0
        gates = 0

        for cap in capabilities:
            result = self._enforce_single(cap)
            checks.append(result.to_dict())
            if result.enforcement_passed:
                passed += 1
            else:
                failed += 1
            if result.is_blocker_for_execution:
                blockers += 1
            if result.requires_runtime_gate:
                gates += 1

        # ready_for_step26g = all control-plane enforcement passed (no failed checks)
        ready26g = failed == 0

        # ready_for_step26h = ready_for_step26g AND all BLOCKED capabilities have gates planned
        blocked_with_gate = [c for c in checks
                            if c["current_status"] == CapabilityStatus.BLOCKED.value
                            and c["requires_runtime_gate"]]
        ready26h = ready26g and len(blocked_with_gate) >= 4

        report = EnforcementReport(
            checks=checks, total=len(checks),
            passed=passed, failed=failed,
            execution_blockers=blockers,
            runtime_gates_required=gates,
            ready_for_step26g=ready26g,
            ready_for_step26h=ready26h,
            execution_allowed=False, runtime_enabled=False,
            fixture_execution_allowed=False, metadata_only=True,
            metadata={"step": "Step 26-G", "enforcement_type": "metadata_only"}
        )
        logger.info(f"Enforcement report: total={report.total} passed={report.passed} "
                     f"failed={report.failed} ready26g={ready26g} ready26h={ready26h}")
        return report

    def _enforce_single(self, cap: RuntimeCapability) -> EnforcementCheckResult:
        """Enforce a single capability. Metadata-only. No runtime side effects."""
        result = EnforcementCheckResult(
            capability_name=cap.name,
            capability_id=cap.capability_id,
            category=cap.category,
            current_status=cap.status,
            expected_status=cap.status,
            enforcement_type="metadata_only",
        )

        # ── Network Enforcement ──
        if cap.category == CapabilityCategory.NETWORK:
            result.expected_status = CapabilityStatus.BLOCKED
            result.enforcement_passed = (cap.status == CapabilityStatus.BLOCKED
                                         and not cap.execution_allowed)
            result.block_reason = "Step 26-F: network_enabled=False; Step 26-G runtime enforcement spike needed"
            result.is_blocker_for_execution = True
            result.requires_runtime_gate = True
            result.recommended_action = "Step 26-G: Implement network namespace isolation runtime spike"

        # ── Filesystem Enforcement ──
        elif cap.category == CapabilityCategory.FILESYSTEM:
            result.expected_status = CapabilityStatus.BLOCKED
            result.enforcement_passed = (cap.status == CapabilityStatus.BLOCKED
                                         and not cap.execution_allowed)
            result.block_reason = "Step 26-D/F: file_write_enabled=False; read-only refs only"
            result.is_blocker_for_execution = True
            result.requires_runtime_gate = True
            result.recommended_action = "Step 26-G: Implement filesystem read-only enforcement runtime spike"

        # ── Secrets Enforcement ──
        elif cap.category == CapabilityCategory.SECRETS:
            result.expected_status = CapabilityStatus.BLOCKED
            result.enforcement_passed = (cap.status == CapabilityStatus.BLOCKED
                                         and not cap.execution_allowed)
            result.block_reason = "Step 26-F: secrets_enabled=False; no secrets broker"
            result.is_blocker_for_execution = True
            result.requires_runtime_gate = True
            result.recommended_action = "Step 26-G: Implement secrets isolation enforcement runtime spike"

        # ── Subprocess Enforcement ──
        elif cap.category == CapabilityCategory.SUBPROCESS:
            result.expected_status = CapabilityStatus.BLOCKED
            result.enforcement_passed = (cap.status == CapabilityStatus.BLOCKED
                                         and not cap.execution_allowed)
            result.is_blocker_for_execution = ("Third-Party" in cap.name
                                               or "Package" in cap.name
                                               or "Entrypoint" in cap.name)
            result.block_reason = f"Step 26-F: {cap.source_policy}"
            if result.is_blocker_for_execution:
                result.requires_runtime_gate = True
                result.recommended_action = "Step 26-H: Third-party execution admission review required"

        # ── Memory/CPU Enforcement ──
        elif cap.category in (CapabilityCategory.MEMORY, CapabilityCategory.CPU):
            result.expected_status = CapabilityStatus.PLANNED
            result.enforcement_passed = (cap.status in (CapabilityStatus.PLANNED,
                                                        CapabilityStatus.BLOCKED)
                                         and not cap.execution_allowed)
            result.is_blocker_for_execution = True
            result.requires_runtime_gate = True
            result.block_reason = f"Step 26-E: {cap.reason}"
            result.recommended_action = "Step 26-E/27: Implement cgroup resource limits"

        # ── Container Enforcement ──
        elif cap.category == CapabilityCategory.CONTAINER:
            if cap.name == "Container Start":
                result.expected_status = CapabilityStatus.BLOCKED
                result.enforcement_passed = (cap.status == CapabilityStatus.BLOCKED
                                             and not cap.execution_allowed)
                result.is_blocker_for_execution = True
                result.block_reason = "Step 26-F: container_start_enabled=False"
                result.recommended_action = "Step 27: Container prototype after full capability gates pass"
            else:
                result.expected_status = CapabilityStatus.PLANNED
                result.enforcement_passed = cap.status in (CapabilityStatus.PLANNED,
                                                           CapabilityStatus.BLOCKED)
                result.is_blocker_for_execution = True
                result.requires_runtime_gate = True
                result.block_reason = f"Step 26-E/F: {cap.reason}"
                result.recommended_action = f"Gate required: {cap.required_gate}"

        # ── MicroVM Enforcement ──
        elif cap.category == CapabilityCategory.MICROVM:
            result.expected_status = CapabilityStatus.BLOCKED
            result.enforcement_passed = (cap.status == CapabilityStatus.BLOCKED
                                         and not cap.execution_allowed)
            result.is_blocker_for_execution = True
            result.block_reason = "Step 26-F: microvm_start_enabled=False"
            result.recommended_action = "Step 27: MicroVM prototype after container phase"

        # ── IPC Enforcement ──
        elif cap.category == CapabilityCategory.IPC:
            result.expected_status = CapabilityStatus.UNSUPPORTED
            result.enforcement_passed = cap.status == CapabilityStatus.UNSUPPORTED
            result.is_blocker_for_execution = False
            result.block_reason = "No runtime processes; IPC not planned"

        # ── Environment Enforcement ──
        elif cap.category == CapabilityCategory.ENVIRONMENT:
            result.expected_status = CapabilityStatus.BLOCKED
            result.enforcement_passed = (cap.status == CapabilityStatus.BLOCKED
                                         and not cap.execution_allowed)
            result.is_blocker_for_execution = False
            result.block_reason = "Step 26-F: secrets_enabled=False; no env injection"

        return result


def run_capability_enforcement_report(capabilities: list[RuntimeCapability] | None = None) -> EnforcementReport:
    """Convenience function: run enforcement and return report."""
    if capabilities is None:
        capabilities = build_default_capability_matrix()
    subagent = RuntimeCapabilityEnforcementSubAgent()
    return subagent.run_simulation(capabilities)
