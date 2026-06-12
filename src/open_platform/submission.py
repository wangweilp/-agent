"""Open Platform Agent Submission Domain Model — Manifest / Submission / Review Record。

提供：
- AgentManifest — Agent 能力声明与安全 Profile
- SecurityProfile — 安全边界声明
- AgentSubmission — 提交流程状态机
- AgentReviewRecord — 审核记录
- SubmissionStore Protocol — 存储层抽象
- Manifest 校验逻辑

安全边界：
- MVP 不执行 package_url / 远程代码
- sandbox_level = no_execution
- manifest 必须声明 required_permissions
- draft → submitted → in_review → approved → published 状态机
- 未审核 submission 不允许 publish
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4


# ═══════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════


class RuntimeType(StrEnum):
    MANIFEST_ONLY = "manifest_only"
    KNOWLEDGE = "knowledge"
    WORKFLOW = "workflow"
    HTTP = "http"
    EXTERNAL = "external"


class SandboxLevel(StrEnum):
    NO_EXECUTION = "no_execution"
    RESTRICTED = "restricted"
    ISOLATED = "isolated"


class SubmissionSourceType(StrEnum):
    MANIFEST = "manifest"
    PACKAGE_URL = "package_url"
    REPOSITORY = "repository"


class SubmissionStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"
    WITHDRAWN = "withdrawn"


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"


# ═══════════════════════════════════════════
# Manifest Validation
# ═══════════════════════════════════════════

_MANIFEST_NAME_RE = re.compile(r"^[a-z0-9_-]+$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(-[a-zA-Z0-9_.]+)?(\+[a-zA-Z0-9_.]+)?$")


@dataclass
class ManifestValidationResult:
    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.valid = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


# ═══════════════════════════════════════════
# SecurityProfile
# ═══════════════════════════════════════════


@dataclass
class SecurityProfile:
    requires_network: bool = False
    reads_user_data: bool = False
    writes_user_data: bool = False
    sandbox_level: str = "no_execution"  # no_execution | restricted | isolated
    allowed_domains: list[str] = field(default_factory=list)
    data_access_scope: list[str] = field(default_factory=list)
    risk_notes: str | None = None

    def validate(self) -> ManifestValidationResult:
        result = ManifestValidationResult()
        if self.sandbox_level not in (s.value for s in SandboxLevel):
            result.add_error(f"sandbox_level 无效: {self.sandbox_level}")
        # MVP: 不允许自动代码执行
        if self.sandbox_level != SandboxLevel.NO_EXECUTION:
            result.add_warning(
                f"sandbox_level={self.sandbox_level} 在 MVP 阶段不支持，"
                f"当前仅支持 no_execution"
            )
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "requires_network": self.requires_network,
            "reads_user_data": self.reads_user_data,
            "writes_user_data": self.writes_user_data,
            "sandbox_level": self.sandbox_level,
            "allowed_domains": self.allowed_domains,
            "data_access_scope": self.data_access_scope,
            "risk_notes": self.risk_notes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SecurityProfile":
        return cls(
            requires_network=bool(d.get("requires_network", False)),
            reads_user_data=bool(d.get("reads_user_data", False)),
            writes_user_data=bool(d.get("writes_user_data", False)),
            sandbox_level=str(d.get("sandbox_level", "no_execution")),
            allowed_domains=list(d.get("allowed_domains", [])),
            data_access_scope=list(d.get("data_access_scope", [])),
            risk_notes=d.get("risk_notes"),
        )


# ═══════════════════════════════════════════
# AgentManifest
# ═══════════════════════════════════════════


@dataclass
class AgentManifest:
    name: str = ""
    display_name: str = ""
    description: str = ""
    version: str = "0.1.0"
    capabilities: list[str] = field(default_factory=list)
    required_permissions: list[str] = field(default_factory=list)
    supported_workflows: list[str] = field(default_factory=list)
    runtime_type: str = "manifest_only"
    entrypoint: str | None = None
    config_schema: dict[str, Any] = field(default_factory=dict)
    usage_limits: dict[str, Any] = field(default_factory=dict)
    security_profile: SecurityProfile | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> ManifestValidationResult:
        result = ManifestValidationResult()

        # 必填字段
        if not self.name:
            result.add_error("name 必填")
        elif not _MANIFEST_NAME_RE.match(self.name):
            result.add_error(f"name '{self.name}' 格式无效：只允许小写字母、数字、短横线、下划线")

        if not self.display_name:
            result.add_error("display_name 必填")

        if not self.description:
            result.add_error("description 必填")

        if not self.version:
            result.add_error("version 必填")
        elif not _SEMVER_RE.match(self.version):
            result.add_warning(f"version '{self.version}' 不是标准 semver 格式")

        if not self.capabilities:
            result.add_error("capabilities 不能为空")

        if not self.required_permissions:
            result.add_error("required_permissions 不能为空")

        if self.security_profile is None:
            result.add_error("security_profile 必填")
        else:
            sp_result = self.security_profile.validate()
            result.errors.extend(sp_result.errors)
            result.warnings.extend(sp_result.warnings)
            result.valid = result.valid and sp_result.valid

        # config_schema / usage_limits / metadata 类型检查
        if not isinstance(self.config_schema, dict):
            result.add_error("config_schema 必须是 dict")

        if not isinstance(self.usage_limits, dict):
            result.add_error("usage_limits 必须是 dict")

        if not isinstance(self.metadata, dict):
            result.add_error("metadata 必须是 dict")

        # MVP: 非 manifest_only 的 runtime_type 拒绝
        if self.runtime_type and self.runtime_type != RuntimeType.MANIFEST_ONLY:
            result.add_error(
                f"runtime_type='{self.runtime_type}' 在 MVP 阶段不支持；"
                f"当前仅支持 {RuntimeType.MANIFEST_ONLY}"
            )

        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "version": self.version,
            "capabilities": list(self.capabilities),
            "required_permissions": list(self.required_permissions),
            "supported_workflows": list(self.supported_workflows),
            "runtime_type": self.runtime_type,
            "entrypoint": self.entrypoint,
            "config_schema": self.config_schema,
            "usage_limits": self.usage_limits,
            "security_profile": self.security_profile.to_dict() if self.security_profile else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AgentManifest":
        sp = d.get("security_profile")
        return cls(
            name=str(d.get("name", "")),
            display_name=str(d.get("display_name", "")),
            description=str(d.get("description", "")),
            version=str(d.get("version", "0.1.0")),
            capabilities=list(d.get("capabilities", [])),
            required_permissions=list(d.get("required_permissions", [])),
            supported_workflows=list(d.get("supported_workflows", [])),
            runtime_type=str(d.get("runtime_type", "manifest_only")),
            entrypoint=d.get("entrypoint"),
            config_schema=dict(d.get("config_schema", {})),
            usage_limits=dict(d.get("usage_limits", {})),
            security_profile=SecurityProfile.from_dict(sp) if isinstance(sp, dict) else None,
            metadata=dict(d.get("metadata", {})),
        )


# ═══════════════════════════════════════════
# AgentSubmission
# ═══════════════════════════════════════════


@dataclass
class AgentSubmission:
    submission_id: str = field(default_factory=lambda: f"sub_{uuid4().hex[:12]}")
    developer_id: str = ""
    tenant_id: str = ""
    marketplace_agent_id: str | None = None
    agent_manifest: AgentManifest | None = None
    package_url: str | None = None
    source_type: str = "manifest"
    status: str = SubmissionStatus.DRAFT
    review_notes: str | None = None
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    published_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ── 状态机 helper ──

    @staticmethod
    def _allowed_transitions() -> dict[str, list[str]]:
        return {
            SubmissionStatus.DRAFT: [SubmissionStatus.SUBMITTED],
            SubmissionStatus.SUBMITTED: [SubmissionStatus.IN_REVIEW, SubmissionStatus.WITHDRAWN],
            SubmissionStatus.IN_REVIEW: [
                SubmissionStatus.APPROVED, SubmissionStatus.REJECTED, SubmissionStatus.WITHDRAWN,
            ],
            SubmissionStatus.REJECTED: [SubmissionStatus.DRAFT],
            SubmissionStatus.APPROVED: [SubmissionStatus.PUBLISHED],
            SubmissionStatus.PUBLISHED: [],
            SubmissionStatus.WITHDRAWN: [],
        }

    def can_edit(self) -> bool:
        return self.status == SubmissionStatus.DRAFT

    def can_submit(self) -> bool:
        return self.status == SubmissionStatus.DRAFT

    def can_withdraw(self) -> bool:
        return self.status in (SubmissionStatus.SUBMITTED, SubmissionStatus.IN_REVIEW)

    def can_review(self) -> bool:
        return self.status in (SubmissionStatus.SUBMITTED, SubmissionStatus.IN_REVIEW)

    def can_publish(self) -> bool:
        return self.status == SubmissionStatus.APPROVED

    def _check_transition(self, target: str) -> None:
        allowed = self._allowed_transitions().get(self.status, [])
        if target not in allowed:
            raise SubmissionStateError(
                f"不允许从 {self.status} 转换到 {target}。"
                f"当前允许的目标: {allowed}"
            )

    # ── 状态流转 ──

    def submit(self) -> None:
        self._check_transition(SubmissionStatus.SUBMITTED)
        self.status = SubmissionStatus.SUBMITTED
        self.submitted_at = datetime.now(timezone.utc)
        self.review_notes = None
        self.updated_at = datetime.now(timezone.utc)

    def start_review(self) -> None:
        self._check_transition(SubmissionStatus.IN_REVIEW)
        self.status = SubmissionStatus.IN_REVIEW
        self.updated_at = datetime.now(timezone.utc)

    def approve(self, reviewer_id: str, notes: str = "") -> None:
        self._check_transition(SubmissionStatus.APPROVED)
        self.status = SubmissionStatus.APPROVED
        self.reviewed_at = datetime.now(timezone.utc)
        self.reviewed_by = reviewer_id
        self.review_notes = notes or None
        self.updated_at = datetime.now(timezone.utc)

    def reject(self, reviewer_id: str, notes: str = "") -> None:
        self._check_transition(SubmissionStatus.REJECTED)
        self.status = SubmissionStatus.REJECTED
        self.reviewed_at = datetime.now(timezone.utc)
        self.reviewed_by = reviewer_id
        self.review_notes = notes or None
        self.updated_at = datetime.now(timezone.utc)

    def request_changes(self, reviewer_id: str, notes: str = "") -> None:
        self._check_transition(SubmissionStatus.REJECTED)
        self.status = SubmissionStatus.REJECTED
        self.reviewed_at = datetime.now(timezone.utc)
        self.reviewed_by = reviewer_id
        self.review_notes = notes or None
        self.updated_at = datetime.now(timezone.utc)

    def withdraw(self) -> None:
        self._check_transition(SubmissionStatus.WITHDRAWN)
        self.status = SubmissionStatus.WITHDRAWN
        self.updated_at = datetime.now(timezone.utc)

    def reopen_to_draft(self) -> None:
        """从 rejected 状态重新打开为 draft。"""
        if self.status != SubmissionStatus.REJECTED:
            raise SubmissionStateError(f"只有 rejected 状态可以重新打开为 draft，当前: {self.status}")
        self.status = SubmissionStatus.DRAFT
        self.updated_at = datetime.now(timezone.utc)

    def publish(self, marketplace_agent_id: str) -> None:
        self._check_transition(SubmissionStatus.PUBLISHED)
        self.status = SubmissionStatus.PUBLISHED
        self.marketplace_agent_id = marketplace_agent_id
        self.published_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    # ── serialization ──

    def to_dict(self) -> dict[str, Any]:
        return {
            "submission_id": self.submission_id,
            "developer_id": self.developer_id,
            "tenant_id": self.tenant_id,
            "marketplace_agent_id": self.marketplace_agent_id,
            "agent_manifest": self.agent_manifest.to_dict() if self.agent_manifest else None,
            "package_url": self.package_url,
            "source_type": self.source_type,
            "status": self.status,
            "review_notes": self.review_notes,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reviewed_by": self.reviewed_by,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ═══════════════════════════════════════════
# AgentReviewRecord
# ═══════════════════════════════════════════


@dataclass
class AgentReviewRecord:
    review_id: str = field(default_factory=lambda: f"rev_{uuid4().hex[:12]}")
    submission_id: str = ""
    reviewer_id: str = ""
    decision: str = ""
    notes: str = ""
    checklist: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "submission_id": self.submission_id,
            "reviewer_id": self.reviewer_id,
            "decision": self.decision,
            "notes": self.notes,
            "checklist": self.checklist,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ═══════════════════════════════════════════
# SubmissionStore Protocol
# ═══════════════════════════════════════════


@runtime_checkable
class SubmissionStore(Protocol):
    """Agent Manifest + Submission 存储协议。"""

    # ── Submission ──

    def create_submission(self, submission: AgentSubmission) -> AgentSubmission: ...
    def get_submission(self, submission_id: str) -> AgentSubmission | None: ...
    def list_submissions(
        self, *, developer_id: str = "", tenant_id: str = "", status: str = "",
    ) -> list[AgentSubmission]: ...
    def update_submission(self, submission: AgentSubmission) -> None: ...
    def update_submission_manifest(
        self, submission_id: str, developer_id: str, manifest: AgentManifest,
    ) -> None: ...
    def submit_submission(
        self, submission_id: str, developer_id: str,
    ) -> None: ...
    def withdraw_submission(
        self, submission_id: str, developer_id: str,
    ) -> None: ...
    def start_review(self, submission_id: str, reviewer_id: str) -> None: ...
    def approve_submission(
        self, submission_id: str, reviewer_id: str, notes: str, checklist: dict[str, Any],
    ) -> None: ...
    def reject_submission(
        self, submission_id: str, reviewer_id: str, notes: str, checklist: dict[str, Any],
    ) -> None: ...
    def request_changes(
        self, submission_id: str, reviewer_id: str, notes: str, checklist: dict[str, Any],
    ) -> None: ...
    def publish_submission(
        self, submission_id: str, marketplace_agent_id: str,
    ) -> None: ...

    # ── Review Records ──

    def create_review_record(self, record: AgentReviewRecord) -> AgentReviewRecord: ...
    def list_review_records(self, submission_id: str) -> list[AgentReviewRecord]: ...
    def get_latest_review_record(self, submission_id: str) -> AgentReviewRecord | None: ...

    # ── Validation ──

    def validate_submission_manifest(
        self, submission_id: str,
    ) -> ManifestValidationResult: ...


# ═══════════════════════════════════════════
# Error Classes
# ═══════════════════════════════════════════


class SubmissionNotFoundError(Exception):
    def __init__(self, message: str = "提交不存在"):
        super().__init__(message)


class SubmissionPermissionError(Exception):
    def __init__(self, message: str = "无权操作此提交"):
        super().__init__(message)


class SubmissionStateError(Exception):
    def __init__(self, message: str = "状态转换不允许"):
        super().__init__(message)


class ManifestValidationError(Exception):
    def __init__(self, message: str = "Manifest 校验失败", errors: list[str] | None = None):
        super().__init__(message)
        self.validation_errors = errors or []


class ReviewRecordError(Exception):
    def __init__(self, message: str = "审核记录错误"):
        super().__init__(message)
