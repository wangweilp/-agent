"""Runtime Capability Matrix — metadata registry for all runtime capabilities.

Step 26-F.5: NO runtime implementation. NO container/microVM start. NO execution.
Registry-only: records what capabilities exist and their control-plane status.

execution_allowed / fixture_execution_allowed / runtime_enabled = always False.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4


# ═══════════ Enums ═══════════

class CapabilityCategory(StrEnum):
    NETWORK = "network"
    FILESYSTEM = "filesystem"
    SECRETS = "secrets"
    SUBPROCESS = "subprocess"
    MEMORY = "memory"
    CPU = "cpu"
    CONTAINER = "container"
    MICROVM = "microvm"
    IPC = "ipc"
    ENVIRONMENT = "environment"


class CapabilityStatus(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    BLOCKED = "blocked"
    PLANNED = "planned"
    EXPERIMENTAL = "experimental"


# ═══════════ Dataclasses ═══════════

@dataclass
class RuntimeCapability:
    capability_id: str = field(default_factory=lambda: f"rtcap_{uuid4().hex[:16]}")
    name: str = ""
    category: str = ""
    status: str = CapabilityStatus.BLOCKED
    description: str = ""
    reason: str = ""
    execution_allowed: bool = False
    fixture_execution_allowed: bool = False
    runtime_enabled: bool = False
    metadata_only: bool = True
    source_policy: str = ""
    source_step: str = ""
    requires_additional_gate: bool = False
    required_gate: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "capability_id": self.capability_id, "name": self.name,
            "category": self.category, "status": self.status,
            "description": self.description, "reason": self.reason,
            "execution_allowed": self.execution_allowed,
            "fixture_execution_allowed": self.fixture_execution_allowed,
            "runtime_enabled": self.runtime_enabled,
            "metadata_only": self.metadata_only,
            "source_policy": self.source_policy, "source_step": self.source_step,
            "requires_additional_gate": self.requires_additional_gate,
            "required_gate": self.required_gate,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata": dict(self.metadata)
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            capability_id=str(d.get("capability_id", "")), name=str(d.get("name", "")),
            category=str(d.get("category", "")), status=str(d.get("status", "blocked")),
            description=str(d.get("description", "")), reason=str(d.get("reason", "")),
            execution_allowed=bool(d.get("execution_allowed", False)),
            fixture_execution_allowed=bool(d.get("fixture_execution_allowed", False)),
            runtime_enabled=bool(d.get("runtime_enabled", False)),
            metadata_only=bool(d.get("metadata_only", True)),
            source_policy=str(d.get("source_policy", "")),
            source_step=str(d.get("source_step", "")),
            requires_additional_gate=bool(d.get("requires_additional_gate", False)),
            required_gate=str(d.get("required_gate", "")),
            created_at=_safe_dt(d.get("created_at")),
            updated_at=_safe_dt(d.get("updated_at")),
            metadata=dict(d.get("metadata", {}))
        )


# ═══════════ Errors ═══════════

class RuntimeCapabilityError(Exception): pass
class RuntimeCapabilityNotFoundError(RuntimeCapabilityError): pass


# ═══════════ Protocol ═══════════

@runtime_checkable
class RuntimeCapabilityStore(Protocol):
    def create_capability(self, cap: RuntimeCapability) -> RuntimeCapability: ...
    def get_capability(self, capability_id: str) -> RuntimeCapability | None: ...
    def list_capabilities(self, *, category: str = "", status: str = "") -> list[RuntimeCapability]: ...
    def update_capability(self, cap: RuntimeCapability) -> RuntimeCapability: ...
    def export_matrix(self) -> dict[str, Any]: ...


# ═══════════ Default Matrix Builder ═══════════

def build_default_capability_matrix() -> list[RuntimeCapability]:
    return [
        RuntimeCapability(name="Network Egress", category=CapabilityCategory.NETWORK,
            status=CapabilityStatus.BLOCKED, description="Outbound network access",
            reason="Step26F policy; no network_enabled",
            source_policy="TrustedFixtureIsolationPolicy.network_enabled=False",
            source_step="Step 26-F", requires_additional_gate=True,
            required_gate="Step 26-G: Network Enforcement Runtime Spike"),
        RuntimeCapability(name="Network Ingress", category=CapabilityCategory.NETWORK,
            status=CapabilityStatus.BLOCKED, description="Inbound network access",
            reason="Step26F policy; no network_enabled",
            source_policy="TrustedFixtureIsolationPolicy.network_enabled=False",
            source_step="Step 26-F"),
        RuntimeCapability(name="Filesystem Write", category=CapabilityCategory.FILESYSTEM,
            status=CapabilityStatus.BLOCKED, description="Write to filesystem",
            reason="Step26F policy; no filesystem_write_enabled",
            source_policy="TrustedFixtureIsolationPolicy.filesystem_write_enabled=False",
            source_step="Step 26-F", requires_additional_gate=True,
            required_gate="Step 26-G: Filesystem Enforcement Runtime Spike"),
        RuntimeCapability(name="Filesystem Read", category=CapabilityCategory.FILESYSTEM,
            status=CapabilityStatus.BLOCKED, description="Read from filesystem",
            reason="Step26D: read-only refs only, no file_opened",
            source_policy="ArtifactMaterializationPolicy.file_write_enabled=False",
            source_step="Step 26-D"),
        RuntimeCapability(name="Secrets Access", category=CapabilityCategory.SECRETS,
            status=CapabilityStatus.BLOCKED, description="Read secrets/env vars",
            reason="No secrets broker; Step26F policy",
            source_policy="TrustedFixtureIsolationPolicy.secrets_enabled=False",
            source_step="Step 26-F", requires_additional_gate=True,
            required_gate="Step 26-G: Secrets Enforcement Runtime Spike"),
        RuntimeCapability(name="Subprocess Execution", category=CapabilityCategory.SUBPROCESS,
            status=CapabilityStatus.BLOCKED, description="Spawn child processes",
            reason="Step26F policy; no subprocess_enabled",
            source_policy="TrustedFixtureIsolationPolicy.subprocess_enabled=False",
            source_step="Step 26-F"),
        RuntimeCapability(name="Dynamic Import", category=CapabilityCategory.SUBPROCESS,
            status=CapabilityStatus.BLOCKED, description="Runtime module import",
            reason="Step26F policy; no dynamic_import_enabled",
            source_policy="TrustedFixtureIsolationPolicy.dynamic_import_enabled=False",
            source_step="Step 26-F"),
        RuntimeCapability(name="Eval/Exec", category=CapabilityCategory.SUBPROCESS,
            status=CapabilityStatus.BLOCKED, description="eval()/exec() calls",
            reason="Step26F policy; no eval_exec_enabled",
            source_policy="TrustedFixtureIsolationPolicy.eval_exec_enabled=False",
            source_step="Step 26-F"),
        RuntimeCapability(name="Memory Limit", category=CapabilityCategory.MEMORY,
            status=CapabilityStatus.PLANNED, description="Memory resource limit",
            reason="No cgroup memory controller; Step26E missing",
            source_step="Step 26-E", requires_additional_gate=True,
            required_gate="Step 26-E: Rootless Container Prototype Gate (memory cgroup)"),
        RuntimeCapability(name="CPU Limit", category=CapabilityCategory.CPU,
            status=CapabilityStatus.PLANNED, description="CPU resource limit",
            reason="No cgroup CPU controller; Step26E missing",
            source_step="Step 26-E", requires_additional_gate=True,
            required_gate="Step 26-E: Rootless Container Prototype Gate (CPU cgroup)"),
        RuntimeCapability(name="Rootless Container", category=CapabilityCategory.CONTAINER,
            status=CapabilityStatus.PLANNED, description="Rootless container runtime",
            reason="Step26E: ready_for_step26f=True but container_start_allowed=False",
            source_step="Step 26-E", requires_additional_gate=True,
            required_gate="Future Step 27"),
        RuntimeCapability(name="Container Start", category=CapabilityCategory.CONTAINER,
            status=CapabilityStatus.BLOCKED, description="Container process start",
            reason="Step26F policy; no container_start_enabled",
            source_policy="TrustedFixtureIsolationPolicy.container_start_enabled=False",
            source_step="Step 26-F"),
        RuntimeCapability(name="MicroVM Start", category=CapabilityCategory.MICROVM,
            status=CapabilityStatus.BLOCKED, description="MicroVM start",
            reason="Step26F policy; no microvm_start_enabled",
            source_policy="TrustedFixtureIsolationPolicy.microvm_start_enabled=False",
            source_step="Step 26-F"),
        RuntimeCapability(name="Inter-Process Communication", category=CapabilityCategory.IPC,
            status=CapabilityStatus.UNSUPPORTED, description="IPC between runtime processes",
            reason="No runtime processes exist; no plan for IPC",
            source_step="Step 26-F"),
        RuntimeCapability(name="Environment Variables", category=CapabilityCategory.ENVIRONMENT,
            status=CapabilityStatus.BLOCKED, description="Env var injection",
            reason="No secrets broker; Step26F policy",
            source_policy="TrustedFixtureIsolationPolicy.secrets_enabled=False",
            source_step="Step 26-F"),
        RuntimeCapability(name="Package Execution", category=CapabilityCategory.SUBPROCESS,
            status=CapabilityStatus.BLOCKED, description="Execute package code",
            reason="Step26F policy; no package_execution_enabled",
            source_policy="TrustedFixtureIsolationPolicy.package_execution_enabled=False",
            source_step="Step 26-F"),
        RuntimeCapability(name="Third-Party Execution", category=CapabilityCategory.SUBPROCESS,
            status=CapabilityStatus.BLOCKED, description="Execute third-party code",
            reason="Step26F policy; no third_party_execution_enabled",
            source_policy="TrustedFixtureIsolationPolicy.third_party_execution_enabled=False",
            source_step="Step 26-F"),
        RuntimeCapability(name="Entrypoint Execution", category=CapabilityCategory.SUBPROCESS,
            status=CapabilityStatus.BLOCKED, description="Execute entrypoint",
            reason="Step26F policy; no entrypoint_execution_enabled",
            source_policy="TrustedFixtureIsolationPolicy.entrypoint_execution_enabled=False",
            source_step="Step 26-F"),
        RuntimeCapability(name="Isolated Runtime", category=CapabilityCategory.CONTAINER,
            status=CapabilityStatus.PLANNED, description="Isolated runtime sandbox",
            reason="Step26F: ready_for_step26g=True but isolated_runtime_enabled=False",
            source_step="Step 26-F", requires_additional_gate=True,
            required_gate="Future Step 27"),
        RuntimeCapability(name="OS-Level Isolation", category=CapabilityCategory.CONTAINER,
            status=CapabilityStatus.PLANNED, description="Namespace/seccomp/AppArmor",
            reason="Step26E/F: capability assessed as MISSING",
            source_step="Step 26-E/26-F", requires_additional_gate=True,
            required_gate="Future Step 27"),
    ]


def _safe_dt(raw, none_ok=False):
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception: return None if none_ok else datetime.now(timezone.utc)
