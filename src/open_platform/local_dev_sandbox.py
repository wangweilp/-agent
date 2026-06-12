"""Local Dev Sandbox Domain Model — 本地开发 dry-run prototype。
Step 24-G: DISABLED/DRY_RUN_ONLY modes, is_real_execution()=False.
不 subprocess/container/network/file/secrets。"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

class LocalDevSandboxMode(StrEnum):
    DISABLED="disabled"; DRY_RUN_ONLY="dry_run_only"; TRUSTED_FIXTURE_RESERVED="trusted_fixture_reserved"

class LocalDevSandboxDecision(StrEnum):
    BLOCKED_DISABLED="blocked_disabled"; BLOCKED_POLICY_NOT_ENFORCEABLE="blocked_policy_not_enforceable"
    BLOCKED_PLAN_NOT_DISPATCHABLE="blocked_plan_not_dispatchable"
    DRY_RUN_RESERVED="dry_run_reserved"; FAIL_CLOSED="fail_closed"

class LocalDevSandboxCheckType(StrEnum):
    LOCAL_DEV_DISABLED="local_dev_disabled"; DRY_RUN_ONLY_MODE="dry_run_only_mode"
    PLAN_NOT_DISPATCHABLE="plan_not_dispatchable"; POLICY_CONFIG_PRESENT="policy_config_present"
    POLICY_CONFIG_ENFORCEABLE="policy_config_enforceable"; NETWORK_DENY_CONFIRMED="network_deny_confirmed"
    SECRETS_DENY_CONFIRMED="secrets_deny_confirmed"; FILESYSTEM_SAFE_CONFIRMED="filesystem_safe_confirmed"
    DATA_ACCESS_BROKER_RESERVED="data_access_broker_reserved"; NO_PACKAGE_DOWNLOAD="no_package_download"
    NO_PACKAGE_EXECUTION="no_package_execution"; NO_ENTRYPOINT_EXECUTION="no_entrypoint_execution"
    NO_NETWORK_USED="no_network_used"; NO_SUBPROCESS_USED="no_subprocess_used"
    NO_CONTAINER_USED="no_container_used"; NO_FILE_READ="no_file_read"
    NO_AGENT_RUNTIME_USED="no_agent_runtime_used"; NO_AGENT_REGISTRY_USED="no_agent_registry_used"
    FAIL_CLOSED="fail_closed"

class LocalDevSandboxCheckStatus(StrEnum):
    PASSED="passed"; WARNING="warning"; BLOCKED="blocked"; FAILED="failed"; SKIPPED="skipped"

class LocalDevSandboxSeverity(StrEnum):
    INFO="info"; WARNING="warning"; ERROR="error"; BLOCKER="blocker"

@dataclass
class LocalDevSandboxCheck:
    check_id: str = field(default_factory=lambda: f"ldschk_{uuid4().hex[:16]}")
    check_type: str = ""; status: str = LocalDevSandboxCheckStatus.PASSED
    severity: str = LocalDevSandboxSeverity.INFO; message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    def to_dict(self): return {"check_id":self.check_id,"check_type":self.check_type,"status":self.status,"severity":self.severity,"message":self.message,"metadata":dict(self.metadata),"created_at":self.created_at.isoformat() if self.created_at else None}
    @classmethod
    def from_dict(cls,d): return cls(check_id=str(d.get("check_id","")),check_type=str(d.get("check_type","")),status=str(d.get("status","passed")),severity=str(d.get("severity","info")),message=str(d.get("message","")),metadata=dict(d.get("metadata",{})),created_at=_safe_dt(d.get("created_at")))

@dataclass
class LocalDevSandboxConfig:
    config_id: str = field(default_factory=lambda: f"ldscfg_{uuid4().hex[:16]}")
    mode: str = LocalDevSandboxMode.DISABLED; enabled: bool = False; dry_run_only: bool = True
    allow_subprocess: bool = False; allow_container: bool = False; allow_network: bool = False
    allow_file_read: bool = False; allow_file_write: bool = False; allow_secrets: bool = False
    allow_agent_runtime: bool = False; allow_agent_registry: bool = False
    require_policy_config: bool = True; max_duration_ms: int = 30000; max_output_bytes: int = 65536
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    @classmethod
    def disabled(cls): return cls()
    @classmethod
    def dry_run_for_tests(cls):
        return cls(mode=LocalDevSandboxMode.DRY_RUN_ONLY, enabled=True, dry_run_only=True,
                   allow_subprocess=False, allow_container=False, allow_network=False,
                   allow_file_read=False, allow_file_write=False, allow_secrets=False,
                   allow_agent_runtime=False, allow_agent_registry=False)
    def to_dict(self): return {"config_id":self.config_id,"mode":self.mode,"enabled":self.enabled,"dry_run_only":self.dry_run_only,"allow_subprocess":self.allow_subprocess,"allow_container":self.allow_container,"allow_network":self.allow_network,"allow_file_read":self.allow_file_read,"allow_file_write":self.allow_file_write,"allow_secrets":self.allow_secrets,"allow_agent_runtime":self.allow_agent_runtime,"allow_agent_registry":self.allow_agent_registry,"require_policy_config":self.require_policy_config,"max_duration_ms":self.max_duration_ms,"max_output_bytes":self.max_output_bytes,"metadata":dict(self.metadata),"created_at":self.created_at.isoformat() if self.created_at else None}
    @classmethod
    def from_dict(cls,d): return cls(config_id=str(d.get("config_id","")),mode=str(d.get("mode","disabled")),enabled=bool(d.get("enabled",False)),dry_run_only=bool(d.get("dry_run_only",True)),allow_subprocess=bool(d.get("allow_subprocess",False)),allow_container=bool(d.get("allow_container",False)),allow_network=bool(d.get("allow_network",False)),allow_file_read=bool(d.get("allow_file_read",False)),allow_file_write=bool(d.get("allow_file_write",False)),allow_secrets=bool(d.get("allow_secrets",False)),allow_agent_runtime=bool(d.get("allow_agent_runtime",False)),allow_agent_registry=bool(d.get("allow_agent_registry",False)),require_policy_config=bool(d.get("require_policy_config",True)),max_duration_ms=int(d.get("max_duration_ms",30000)),max_output_bytes=int(d.get("max_output_bytes",65536)),metadata=dict(d.get("metadata",{})),created_at=_safe_dt(d.get("created_at")))

@dataclass
class LocalDevSandboxDryRunResult:
    dry_run_id: str = field(default_factory=lambda: f"ldsdry_{uuid4().hex[:16]}")
    request_id: str = ""; plan_id: str = ""; tenant_id: str = ""
    decision: str = LocalDevSandboxDecision.BLOCKED_DISABLED
    checks: list[LocalDevSandboxCheck] = field(default_factory=list)
    warnings_count: int = 0; errors_count: int = 0; blockers_count: int = 0
    output_preview: dict[str, Any] = field(default_factory=dict); output_truncated: bool = False
    no_execution_performed: bool = True; no_download_used: bool = True; no_network_used: bool = True
    no_subprocess_used: bool = True; no_container_used: bool = True
    no_file_read: bool = True; no_file_write: bool = True; no_secrets_read: bool = True
    no_agent_runtime_used: bool = True; no_agent_registry_used: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)
    def add_check(self,c): self.checks.append(c); self._recount()
    def _recount(self):
        self.warnings_count=sum(1 for c in self.checks if c.status==LocalDevSandboxCheckStatus.WARNING)
        self.errors_count=sum(1 for c in self.checks if c.status==LocalDevSandboxCheckStatus.FAILED)
        self.blockers_count=sum(1 for c in self.checks if c.status==LocalDevSandboxCheckStatus.BLOCKED)
    def calculate_status(self):
        self._recount()
        if self.blockers_count>0: self.decision=LocalDevSandboxDecision.BLOCKED_DISABLED
        elif self.errors_count>0: self.decision=LocalDevSandboxDecision.FAIL_CLOSED
        else: self.decision=LocalDevSandboxDecision.DRY_RUN_RESERVED
    def is_real_execution(self)->bool: return False
    def to_dict(self): return {"dry_run_id":self.dry_run_id,"request_id":self.request_id,"plan_id":self.plan_id,"tenant_id":self.tenant_id,"decision":self.decision,"checks":[c.to_dict() for c in self.checks],"warnings_count":self.warnings_count,"errors_count":self.errors_count,"blockers_count":self.blockers_count,"output_preview":dict(self.output_preview),"output_truncated":self.output_truncated,"no_execution_performed":self.no_execution_performed,"no_download_used":self.no_download_used,"no_network_used":self.no_network_used,"no_subprocess_used":self.no_subprocess_used,"no_container_used":self.no_container_used,"no_file_read":self.no_file_read,"no_file_write":self.no_file_write,"no_secrets_read":self.no_secrets_read,"no_agent_runtime_used":self.no_agent_runtime_used,"no_agent_registry_used":self.no_agent_registry_used,"created_at":self.created_at.isoformat() if self.created_at else None,"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d):
        checks=[LocalDevSandboxCheck.from_dict(c) for c in d.get("checks",[])]
        return cls(dry_run_id=str(d.get("dry_run_id","")),request_id=str(d.get("request_id","")),plan_id=str(d.get("plan_id","")),tenant_id=str(d.get("tenant_id","")),decision=str(d.get("decision","blocked_disabled")),checks=checks,warnings_count=int(d.get("warnings_count",0)),errors_count=int(d.get("errors_count",0)),blockers_count=int(d.get("blockers_count",0)),output_preview=dict(d.get("output_preview",{})),output_truncated=bool(d.get("output_truncated",False)),no_execution_performed=bool(d.get("no_execution_performed",True)),no_download_used=bool(d.get("no_download_used",True)),no_network_used=bool(d.get("no_network_used",True)),no_subprocess_used=bool(d.get("no_subprocess_used",True)),no_container_used=bool(d.get("no_container_used",True)),no_file_read=bool(d.get("no_file_read",True)),no_file_write=bool(d.get("no_file_write",True)),no_secrets_read=bool(d.get("no_secrets_read",True)),no_agent_runtime_used=bool(d.get("no_agent_runtime_used",True)),no_agent_registry_used=bool(d.get("no_agent_registry_used",True)),created_at=_safe_dt(d.get("created_at")),metadata=dict(d.get("metadata",{})))

class LocalDevSandboxError(Exception): pass
class LocalDevSandboxDisabledError(LocalDevSandboxError): pass
class LocalDevSandboxPolicyError(LocalDevSandboxError): pass
class LocalDevSandboxFailClosedError(LocalDevSandboxError): pass

def _safe_dt(raw,none_ok=False):
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(str(raw).replace("Z","+00:00"))
    except: return None if none_ok else datetime.now(timezone.utc)
