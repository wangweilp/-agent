"""Sandbox Enforcement Proof Domain Model — metadata-only proof, no real enforcement.

Step 25-G: NO socket/iptables/mount/chmod/secret read/os.environ.
is_enforcement_active()/is_execution_allowed() = always False."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

# ═══════ Enums ═══════
class EnforcementScope(StrEnum): NETWORK="network"; FILESYSTEM="filesystem"; SECRETS="secrets"; COMBINED="combined"
class EnforcementProofStatus(StrEnum):
    DRAFT="draft"; REQUESTED="requested"; PROOF_EVALUATED="proof_evaluated"
    PASSED_METADATA_ONLY="passed_metadata_only"; REVIEW_REQUIRED="review_required"
    BLOCKED="blocked"; FAIL_CLOSED="fail_closed"
class EnforcementProofDecision(StrEnum):
    METADATA_PROOF_PASSED="metadata_proof_passed"; REVIEW_REQUIRED="review_required"
    BLOCKED="blocked"; FAIL_CLOSED="fail_closed"
class NetworkRuleMode(StrEnum): DENY_ALL="deny_all"; ALLOWLIST_RESERVED="allowlist_reserved"; BLOCKED_UNSAFE="blocked_unsafe"
class FilesystemRuleMode(StrEnum):
    DENY_ALL="deny_all"; EPHEMERAL_ONLY_RESERVED="ephemeral_only_reserved"
    READ_ONLY_PACKAGE_RESERVED="read_only_package_reserved"; BLOCKED_UNSAFE="blocked_unsafe"
class SecretRuleMode(StrEnum): DENY_ALL="deny_all"; SCOPED_BROKER_RESERVED="scoped_broker_reserved"; BLOCKED_UNSAFE="blocked_unsafe"
class EnforcementRiskLevel(StrEnum): LOW="low"; MEDIUM="medium"; HIGH="high"; CRITICAL="critical"; UNKNOWN="unknown"
class EnforcementCheckType(StrEnum):
    DEFAULT_DENY_NETWORK="default_deny_network"; DEFAULT_DENY_FILESYSTEM="default_deny_filesystem"
    DEFAULT_DENY_SECRETS="default_deny_secrets"; NETWORK_METADATA_IP_BLOCKED="network_metadata_ip_blocked"
    NETWORK_LOCALHOST_BLOCKED="network_localhost_blocked"; NETWORK_PRIVATE_IP_BLOCKED="network_private_ip_blocked"
    NETWORK_RAW_SOCKET_BLOCKED="network_raw_socket_blocked"; NETWORK_DNS_EGRESS_REVIEWED="network_dns_egress_reviewed"
    FILESYSTEM_HOST_MOUNT_BLOCKED="filesystem_host_mount_blocked"
    FILESYSTEM_DOCKER_SOCKET_BLOCKED="filesystem_docker_socket_blocked"
    FILESYSTEM_ABSOLUTE_PATH_BLOCKED="filesystem_absolute_path_blocked"
    FILESYSTEM_TRAVERSAL_BLOCKED="filesystem_traversal_blocked"
    FILESYSTEM_SYMLINK_ESCAPE_BLOCKED="filesystem_symlink_escape_blocked"
    FILESYSTEM_WRITE_BLOCKED="filesystem_write_blocked"
    FILESYSTEM_EPHEMERAL_WORKSPACE_RESERVED="filesystem_ephemeral_workspace_reserved"
    SECRETS_RAW_ENV_INJECTION_BLOCKED="secrets_raw_env_injection_blocked"
    SECRETS_DIRECT_READ_BLOCKED="secrets_direct_read_blocked"
    SECRETS_SCOPED_BROKER_RESERVED="secrets_scoped_broker_reserved"
    NO_NETWORK_ENFORCEMENT_APPLIED="no_network_enforcement_applied"
    NO_FILESYSTEM_ENFORCEMENT_APPLIED="no_filesystem_enforcement_applied"
    NO_SECRET_READ_PERFORMED="no_secret_read_performed"
    NO_RUNTIME_STARTED="no_runtime_started"; FAIL_CLOSED_ON_UNSUPPORTED="fail_closed_on_unsupported"
class EnforcementCheckStatus(StrEnum): PASSED="passed"; WARNING="warning"; BLOCKED="blocked"; FAILED="failed"; SKIPPED="skipped"
class EnforcementSeverity(StrEnum): INFO="info"; WARNING="warning"; ERROR="error"; BLOCKER="blocker"
class EnforcementAuditEventType(StrEnum):
    PROOF_REQUEST_CREATED="proof_request_created"; NETWORK_RULE_EVALUATED="network_rule_evaluated"
    FILESYSTEM_RULE_EVALUATED="filesystem_rule_evaluated"; SECRET_RULE_EVALUATED="secret_rule_evaluated"
    PROOF_EVALUATED="proof_evaluated"; STATUS_CHANGED="status_changed"; DECISION_CHANGED="decision_changed"
    BLOCKED="blocked"; CANCELLED="cancelled"; EXPIRED="expired"; NOTE_ADDED="note_added"
class EnforcementAuditSeverity(StrEnum): INFO="info"; WARNING="warning"; ERROR="error"; BLOCKER="blocker"

# ═══════ Rule Builders ═══════
def build_default_deny_network_rule(allowed_domains=None, allowed_cidrs=None):
    doms = list(allowed_domains or [])
    cidrs = list(allowed_cidrs or [])
    risk = EnforcementRiskLevel.LOW
    for c in cidrs:
        if _is_private_cidr(c): risk = EnforcementRiskLevel.HIGH
    return NetworkEnforcementRule(mode=NetworkRuleMode.DENY_ALL, allow_network=False,
        allowed_domains=doms, allowed_cidrs=cidrs,
        block_metadata_ip=True, block_localhost=True, block_private_ranges=True,
        block_raw_sockets=True, dns_egress_requires_review=True,
        is_enforceable_metadata_only=True, is_runtime_applied=False, risk_level=risk)

def build_default_deny_filesystem_rule(allowed_read_refs=None, allowed_write_refs=None):
    return FilesystemEnforcementRule(mode=FilesystemRuleMode.DENY_ALL,
        allow_read=False, allow_write=False,
        allowed_read_refs=list(allowed_read_refs or []),
        allowed_write_refs=list(allowed_write_refs or []),
        host_mount_allowed=False, docker_socket_allowed=False,
        absolute_paths_allowed=False, traversal_allowed=False, symlink_escape_allowed=False,
        ephemeral_workspace_required=True, read_only_package_mount_reserved=True,
        is_enforceable_metadata_only=True, is_runtime_applied=False)

def build_default_deny_secret_rule(allowed_secret_refs=None):
    refs = list(allowed_secret_refs or [])
    return SecretEnforcementRule(mode=SecretRuleMode.DENY_ALL,
        allow_secrets=False, allowed_secret_refs=refs,
        raw_env_injection_allowed=False, direct_secret_read_allowed=False,
        broker_required=bool(refs), short_lived_token_required=True, audit_required=True,
        is_enforceable_metadata_only=True, is_runtime_applied=False)

def _is_private_cidr(cidr: str) -> bool:
    try:
        import ipaddress; n = ipaddress.ip_network(cidr, strict=False)
        return n.is_private or n.is_loopback or n.is_link_local or n.is_multicast
    except Exception: return True  # invalid = high risk

# ═══════ Dataclasses ═══════
@dataclass
class NetworkEnforcementRule:
    rule_id: str = field(default_factory=lambda: f"nwrule_{uuid4().hex[:16]}")
    mode: str = NetworkRuleMode.DENY_ALL; allow_network: bool = False
    allowed_domains: list[str] = field(default_factory=list); allowed_cidrs: list[str] = field(default_factory=list)
    blocked_cidrs: list[str] = field(default_factory=list)
    block_metadata_ip: bool = True; block_localhost: bool = True; block_private_ranges: bool = True
    block_raw_sockets: bool = True; dns_egress_requires_review: bool = True
    is_enforceable_metadata_only: bool = True; is_runtime_applied: bool = False
    risk_level: str = EnforcementRiskLevel.UNKNOWN
    metadata: dict[str,Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    def to_dict(self): return {"rule_id":self.rule_id,"mode":self.mode,"allow_network":self.allow_network,"allowed_domains":list(self.allowed_domains),"allowed_cidrs":list(self.allowed_cidrs),"blocked_cidrs":list(self.blocked_cidrs),"block_metadata_ip":self.block_metadata_ip,"block_localhost":self.block_localhost,"block_private_ranges":self.block_private_ranges,"block_raw_sockets":self.block_raw_sockets,"dns_egress_requires_review":self.dns_egress_requires_review,"is_enforceable_metadata_only":self.is_enforceable_metadata_only,"is_runtime_applied":self.is_runtime_applied,"risk_level":self.risk_level,"metadata":dict(self.metadata),"created_at":self.created_at.isoformat() if self.created_at else None}
    @classmethod
    def from_dict(cls,d): return cls(rule_id=str(d.get("rule_id","")),mode=str(d.get("mode","deny_all")),allow_network=bool(d.get("allow_network",False)),allowed_domains=list(d.get("allowed_domains",[])),allowed_cidrs=list(d.get("allowed_cidrs",[])),blocked_cidrs=list(d.get("blocked_cidrs",[])),block_metadata_ip=bool(d.get("block_metadata_ip",True)),block_localhost=bool(d.get("block_localhost",True)),block_private_ranges=bool(d.get("block_private_ranges",True)),block_raw_sockets=bool(d.get("block_raw_sockets",True)),dns_egress_requires_review=bool(d.get("dns_egress_requires_review",True)),is_enforceable_metadata_only=bool(d.get("is_enforceable_metadata_only",True)),is_runtime_applied=bool(d.get("is_runtime_applied",False)),risk_level=str(d.get("risk_level","unknown")),metadata=dict(d.get("metadata",{})),created_at=_safe_dt(d.get("created_at")))

@dataclass
class FilesystemEnforcementRule:
    rule_id: str = field(default_factory=lambda: f"fsrule_{uuid4().hex[:16]}")
    mode: str = FilesystemRuleMode.DENY_ALL; allow_read: bool = False; allow_write: bool = False
    allowed_read_refs: list[str] = field(default_factory=list); allowed_write_refs: list[str] = field(default_factory=list)
    host_mount_allowed: bool = False; docker_socket_allowed: bool = False
    absolute_paths_allowed: bool = False; traversal_allowed: bool = False; symlink_escape_allowed: bool = False
    ephemeral_workspace_required: bool = True; read_only_package_mount_reserved: bool = True
    is_enforceable_metadata_only: bool = True; is_runtime_applied: bool = False
    risk_level: str = EnforcementRiskLevel.UNKNOWN
    metadata: dict[str,Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    def to_dict(self): return {"rule_id":self.rule_id,"mode":self.mode,"allow_read":self.allow_read,"allow_write":self.allow_write,"allowed_read_refs":list(self.allowed_read_refs),"allowed_write_refs":list(self.allowed_write_refs),"host_mount_allowed":self.host_mount_allowed,"docker_socket_allowed":self.docker_socket_allowed,"absolute_paths_allowed":self.absolute_paths_allowed,"traversal_allowed":self.traversal_allowed,"symlink_escape_allowed":self.symlink_escape_allowed,"ephemeral_workspace_required":self.ephemeral_workspace_required,"read_only_package_mount_reserved":self.read_only_package_mount_reserved,"is_enforceable_metadata_only":self.is_enforceable_metadata_only,"is_runtime_applied":self.is_runtime_applied,"risk_level":self.risk_level,"metadata":dict(self.metadata),"created_at":self.created_at.isoformat() if self.created_at else None}
    @classmethod
    def from_dict(cls,d): return cls(rule_id=str(d.get("rule_id","")),mode=str(d.get("mode","deny_all")),allow_read=bool(d.get("allow_read",False)),allow_write=bool(d.get("allow_write",False)),allowed_read_refs=list(d.get("allowed_read_refs",[])),allowed_write_refs=list(d.get("allowed_write_refs",[])),host_mount_allowed=bool(d.get("host_mount_allowed",False)),docker_socket_allowed=bool(d.get("docker_socket_allowed",False)),absolute_paths_allowed=bool(d.get("absolute_paths_allowed",False)),traversal_allowed=bool(d.get("traversal_allowed",False)),symlink_escape_allowed=bool(d.get("symlink_escape_allowed",False)),ephemeral_workspace_required=bool(d.get("ephemeral_workspace_required",True)),read_only_package_mount_reserved=bool(d.get("read_only_package_mount_reserved",True)),is_enforceable_metadata_only=bool(d.get("is_enforceable_metadata_only",True)),is_runtime_applied=bool(d.get("is_runtime_applied",False)),risk_level=str(d.get("risk_level","unknown")),metadata=dict(d.get("metadata",{})),created_at=_safe_dt(d.get("created_at")))

@dataclass
class SecretEnforcementRule:
    rule_id: str = field(default_factory=lambda: f"secrule_{uuid4().hex[:16]}")
    mode: str = SecretRuleMode.DENY_ALL; allow_secrets: bool = False
    allowed_secret_refs: list[str] = field(default_factory=list)
    raw_env_injection_allowed: bool = False; direct_secret_read_allowed: bool = False
    broker_required: bool = False; short_lived_token_required: bool = True; audit_required: bool = True
    is_enforceable_metadata_only: bool = True; is_runtime_applied: bool = False
    risk_level: str = EnforcementRiskLevel.UNKNOWN
    metadata: dict[str,Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    def to_dict(self): return {"rule_id":self.rule_id,"mode":self.mode,"allow_secrets":self.allow_secrets,"allowed_secret_refs":list(self.allowed_secret_refs),"raw_env_injection_allowed":self.raw_env_injection_allowed,"direct_secret_read_allowed":self.direct_secret_read_allowed,"broker_required":self.broker_required,"short_lived_token_required":self.short_lived_token_required,"audit_required":self.audit_required,"is_enforceable_metadata_only":self.is_enforceable_metadata_only,"is_runtime_applied":self.is_runtime_applied,"risk_level":self.risk_level,"metadata":dict(self.metadata),"created_at":self.created_at.isoformat() if self.created_at else None}
    @classmethod
    def from_dict(cls,d): return cls(rule_id=str(d.get("rule_id","")),mode=str(d.get("mode","deny_all")),allow_secrets=bool(d.get("allow_secrets",False)),allowed_secret_refs=list(d.get("allowed_secret_refs",[])),raw_env_injection_allowed=bool(d.get("raw_env_injection_allowed",False)),direct_secret_read_allowed=bool(d.get("direct_secret_read_allowed",False)),broker_required=bool(d.get("broker_required",False)),short_lived_token_required=bool(d.get("short_lived_token_required",True)),audit_required=bool(d.get("audit_required",True)),is_enforceable_metadata_only=bool(d.get("is_enforceable_metadata_only",True)),is_runtime_applied=bool(d.get("is_runtime_applied",False)),risk_level=str(d.get("risk_level","unknown")),metadata=dict(d.get("metadata",{})),created_at=_safe_dt(d.get("created_at")))

@dataclass
class EnforcementProofRequest:
    request_id: str = field(default_factory=lambda: f"enfreq_{uuid4().hex[:16]}")
    tenant_id: str = ""; execution_id: str|None=None; queue_record_id: str|None=None
    policy_id: str|None=None; adapter_id: str|None=None; requested_by: str|None=None
    scope: str = EnforcementScope.COMBINED
    network_rule: NetworkEnforcementRule = field(default_factory=build_default_deny_network_rule)
    filesystem_rule: FilesystemEnforcementRule = field(default_factory=build_default_deny_filesystem_rule)
    secret_rule: SecretEnforcementRule = field(default_factory=build_default_deny_secret_rule)
    policy_config_snapshot: dict[str,Any] = field(default_factory=dict)
    adapter_descriptor_snapshot: dict[str,Any] = field(default_factory=dict)
    execution_snapshot: dict[str,Any] = field(default_factory=dict)
    queue_snapshot: dict[str,Any] = field(default_factory=dict)
    proof_status: str = EnforcementProofStatus.DRAFT; decision: str = EnforcementProofDecision.BLOCKED
    risk_level: str = EnforcementRiskLevel.UNKNOWN
    no_network_enforcement_applied: bool = True; no_filesystem_enforcement_applied: bool = True
    no_secret_read_performed: bool = True; no_runtime_started: bool = True; no_worker_started: bool = True
    no_queue_created: bool = True; no_job_dispatched: bool = True; no_execution_performed: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cancelled_at: datetime|None=None; expired_at: datetime|None=None; expires_at: datetime|None=None
    metadata: dict[str,Any] = field(default_factory=dict)
    def is_runtime_enforcement_active(self) -> bool: return False
    def is_execution_allowed(self) -> bool: return False
    def to_dict(self): return {"request_id":self.request_id,"tenant_id":self.tenant_id,"execution_id":self.execution_id,"queue_record_id":self.queue_record_id,"policy_id":self.policy_id,"adapter_id":self.adapter_id,"requested_by":self.requested_by,"scope":self.scope,"network_rule":self.network_rule.to_dict(),"filesystem_rule":self.filesystem_rule.to_dict(),"secret_rule":self.secret_rule.to_dict(),"policy_config_snapshot":dict(self.policy_config_snapshot),"adapter_descriptor_snapshot":dict(self.adapter_descriptor_snapshot),"execution_snapshot":dict(self.execution_snapshot),"queue_snapshot":dict(self.queue_snapshot),"proof_status":self.proof_status,"decision":self.decision,"risk_level":self.risk_level,"no_network_enforcement_applied":self.no_network_enforcement_applied,"no_filesystem_enforcement_applied":self.no_filesystem_enforcement_applied,"no_secret_read_performed":self.no_secret_read_performed,"no_runtime_started":self.no_runtime_started,"no_worker_started":self.no_worker_started,"no_queue_created":self.no_queue_created,"no_job_dispatched":self.no_job_dispatched,"no_execution_performed":self.no_execution_performed,"created_at":self.created_at.isoformat() if self.created_at else None,"updated_at":self.updated_at.isoformat() if self.updated_at else None,"cancelled_at":self.cancelled_at.isoformat() if self.cancelled_at else None,"expired_at":self.expired_at.isoformat() if self.expired_at else None,"expires_at":self.expires_at.isoformat() if self.expires_at else None,"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d): return cls(request_id=str(d.get("request_id","")),tenant_id=str(d.get("tenant_id","")),execution_id=d.get("execution_id"),queue_record_id=d.get("queue_record_id"),policy_id=d.get("policy_id"),adapter_id=d.get("adapter_id"),requested_by=d.get("requested_by"),scope=str(d.get("scope","combined")),network_rule=NetworkEnforcementRule.from_dict(d["network_rule"]) if isinstance(d.get("network_rule"),dict) else build_default_deny_network_rule(),filesystem_rule=FilesystemEnforcementRule.from_dict(d["filesystem_rule"]) if isinstance(d.get("filesystem_rule"),dict) else build_default_deny_filesystem_rule(),secret_rule=SecretEnforcementRule.from_dict(d["secret_rule"]) if isinstance(d.get("secret_rule"),dict) else build_default_deny_secret_rule(),policy_config_snapshot=dict(d.get("policy_config_snapshot",{})),adapter_descriptor_snapshot=dict(d.get("adapter_descriptor_snapshot",{})),execution_snapshot=dict(d.get("execution_snapshot",{})),queue_snapshot=dict(d.get("queue_snapshot",{})),proof_status=str(d.get("proof_status","draft")),decision=str(d.get("decision","blocked")),risk_level=str(d.get("risk_level","unknown")),no_network_enforcement_applied=bool(d.get("no_network_enforcement_applied",True)),no_filesystem_enforcement_applied=bool(d.get("no_filesystem_enforcement_applied",True)),no_secret_read_performed=bool(d.get("no_secret_read_performed",True)),no_runtime_started=bool(d.get("no_runtime_started",True)),no_worker_started=bool(d.get("no_worker_started",True)),no_queue_created=bool(d.get("no_queue_created",True)),no_job_dispatched=bool(d.get("no_job_dispatched",True)),no_execution_performed=bool(d.get("no_execution_performed",True)),created_at=_safe_dt(d.get("created_at")),updated_at=_safe_dt(d.get("updated_at")),cancelled_at=_safe_dt(d.get("cancelled_at"),True),expired_at=_safe_dt(d.get("expired_at"),True),expires_at=_safe_dt(d.get("expires_at"),True),metadata=dict(d.get("metadata",{})))

@dataclass
class EnforcementCheck:
    check_id: str = field(default_factory=lambda: f"enfchk_{uuid4().hex[:16]}")
    request_id: str = ""; check_type: str = ""; status: str = EnforcementCheckStatus.PASSED
    severity: str = EnforcementSeverity.INFO; message: str = ""
    metadata: dict[str,Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    def to_dict(self): return {"check_id":self.check_id,"request_id":self.request_id,"check_type":self.check_type,"status":self.status,"severity":self.severity,"message":self.message,"metadata":dict(self.metadata),"created_at":self.created_at.isoformat() if self.created_at else None}
    @classmethod
    def from_dict(cls,d): return cls(check_id=str(d.get("check_id","")),request_id=str(d.get("request_id","")),check_type=str(d.get("check_type","")),status=str(d.get("status","passed")),severity=str(d.get("severity","info")),message=str(d.get("message","")),metadata=dict(d.get("metadata",{})),created_at=_safe_dt(d.get("created_at")))

@dataclass
class EnforcementProofResult:
    result_id: str = field(default_factory=lambda: f"enfres_{uuid4().hex[:16]}")
    request_id: str = ""; tenant_id: str = ""
    proof_status: str = EnforcementProofStatus.BLOCKED; decision: str = EnforcementProofDecision.BLOCKED
    checks: list[EnforcementCheck] = field(default_factory=list)
    warnings_count: int = 0; errors_count: int = 0; blockers_count: int = 0
    metadata_only: bool = True; no_network_enforcement_applied: bool = True
    no_filesystem_enforcement_applied: bool = True; no_secret_read_performed: bool = True
    no_runtime_started: bool = True; no_execution_performed: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str,Any] = field(default_factory=dict)
    def add_check(self,c): self.checks.append(c); self._recount()
    def _recount(self):
        self.warnings_count=sum(1 for c in self.checks if c.status==EnforcementCheckStatus.WARNING)
        self.errors_count=sum(1 for c in self.checks if c.status==EnforcementCheckStatus.FAILED)
        self.blockers_count=sum(1 for c in self.checks if c.status==EnforcementCheckStatus.BLOCKED)
    def calculate_status(self):
        self._recount()
        if self.blockers_count>0: self.proof_status=EnforcementProofStatus.BLOCKED; self.decision=EnforcementProofDecision.BLOCKED
        elif self.errors_count>0: self.proof_status=EnforcementProofStatus.REVIEW_REQUIRED
        elif self.warnings_count>0: self.proof_status=EnforcementProofStatus.PASSED_METADATA_ONLY; self.decision=EnforcementProofDecision.METADATA_PROOF_PASSED
        else: self.proof_status=EnforcementProofStatus.PASSED_METADATA_ONLY; self.decision=EnforcementProofDecision.METADATA_PROOF_PASSED
    def is_enforcement_active(self) -> bool: return False
    def is_execution_allowed(self) -> bool: return False
    def to_dict(self): return {"result_id":self.result_id,"request_id":self.request_id,"tenant_id":self.tenant_id,"proof_status":self.proof_status,"decision":self.decision,"checks":[c.to_dict() for c in self.checks],"warnings_count":self.warnings_count,"errors_count":self.errors_count,"blockers_count":self.blockers_count,"metadata_only":self.metadata_only,"no_network_enforcement_applied":self.no_network_enforcement_applied,"no_filesystem_enforcement_applied":self.no_filesystem_enforcement_applied,"no_secret_read_performed":self.no_secret_read_performed,"no_runtime_started":self.no_runtime_started,"no_execution_performed":self.no_execution_performed,"created_at":self.created_at.isoformat() if self.created_at else None,"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d): checks=[EnforcementCheck.from_dict(c) for c in d.get("checks",[])]; return cls(result_id=str(d.get("result_id","")),request_id=str(d.get("request_id","")),tenant_id=str(d.get("tenant_id","")),proof_status=str(d.get("proof_status","blocked")),decision=str(d.get("decision","blocked")),checks=checks,warnings_count=int(d.get("warnings_count",0)),errors_count=int(d.get("errors_count",0)),blockers_count=int(d.get("blockers_count",0)),metadata_only=bool(d.get("metadata_only",True)),no_network_enforcement_applied=bool(d.get("no_network_enforcement_applied",True)),no_filesystem_enforcement_applied=bool(d.get("no_filesystem_enforcement_applied",True)),no_secret_read_performed=bool(d.get("no_secret_read_performed",True)),no_runtime_started=bool(d.get("no_runtime_started",True)),no_execution_performed=bool(d.get("no_execution_performed",True)),created_at=_safe_dt(d.get("created_at")),metadata=dict(d.get("metadata",{})))

@dataclass
class EnforcementProofAuditEvent:
    event_id: str = field(default_factory=lambda: f"enfevt_{uuid4().hex[:16]}")
    request_id: str = ""; tenant_id: str = ""
    event_type: str = ""; severity: str = EnforcementAuditSeverity.INFO
    actor_id: str|None=None; message: str = ""
    metadata: dict[str,Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    def to_dict(self): return {"event_id":self.event_id,"request_id":self.request_id,"tenant_id":self.tenant_id,"event_type":self.event_type,"severity":self.severity,"actor_id":self.actor_id,"message":self.message,"metadata":dict(self.metadata),"created_at":self.created_at.isoformat() if self.created_at else None}
    @classmethod
    def from_dict(cls,d): return cls(event_id=str(d.get("event_id","")),request_id=str(d.get("request_id","")),tenant_id=str(d.get("tenant_id","")),event_type=str(d.get("event_type","")),severity=str(d.get("severity","info")),actor_id=d.get("actor_id"),message=str(d.get("message","")),metadata=dict(d.get("metadata",{})),created_at=_safe_dt(d.get("created_at")))

# ═══════ Errors ═══════
class EnforcementProofError(Exception): pass
class EnforcementProofRequestNotFoundError(EnforcementProofError): pass
class EnforcementProofStateError(EnforcementProofError): pass
class EnforcementProofBlockedError(EnforcementProofError): pass

# ═══════ Protocol ═══════
@runtime_checkable
class EnforcementProofStore(Protocol):
    def create_request(self, request: EnforcementProofRequest) -> EnforcementProofRequest: ...
    def get_request(self, request_id: str) -> EnforcementProofRequest | None: ...
    def list_requests(self, *, tenant_id: str = "", execution_id: str = "", queue_record_id: str = "",
        status: str = "", decision: str = "", scope: str = "") -> list[EnforcementProofRequest]: ...
    def update_request(self, request: EnforcementProofRequest) -> EnforcementProofRequest: ...
    def set_request_status(self, request_id: str, status: str, actor_id: str | None = None, reason: str | None = None) -> EnforcementProofRequest: ...
    def set_decision(self, request_id: str, decision: str, actor_id: str | None = None, reason: str | None = None) -> EnforcementProofRequest: ...
    def create_result(self, result: EnforcementProofResult) -> EnforcementProofResult: ...
    def get_result(self, result_id: str) -> EnforcementProofResult | None: ...
    def get_result_by_request(self, request_id: str) -> EnforcementProofResult | None: ...
    def cancel_request(self, request_id: str, actor_id: str | None = None, reason: str | None = None) -> EnforcementProofRequest: ...
    def expire_request(self, request_id: str, actor_id: str | None = None, reason: str | None = None) -> EnforcementProofRequest: ...
    def add_audit_event(self, event: EnforcementProofAuditEvent) -> EnforcementProofAuditEvent: ...
    def list_audit_events(self, request_id: str) -> list[EnforcementProofAuditEvent]: ...
    def count_requests(self, *, tenant_id: str = "", status: str = "", decision: str = "", scope: str = "") -> int: ...

def _safe_dt(raw, none_ok=False):
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(str(raw).replace("Z","+00:00"))
    except: return None if none_ok else datetime.now(timezone.utc)
