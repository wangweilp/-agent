"""Marketplace Governance & Trust Domain。

Review / Report / TrustScore / RiskLevel / GovernanceEvent。

约束：metadata_only=True，不执行、不联网、不写文件、无 runtime/container/microVM。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum, StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4


# ═══════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════

class ReviewStatus(StrEnum):
    ACTIVE = "active"
    DELETED = "deleted"


class ReportType(StrEnum):
    SPAM = "spam"
    MALICIOUS = "malicious"
    COPYRIGHT = "copyright"
    FRAUD = "fraud"
    OTHER = "other"


class ReportStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GovernanceEventType(StrEnum):
    REVIEW_CREATED = "review_created"
    REVIEW_UPDATED = "review_updated"
    REVIEW_DELETED = "review_deleted"
    REPORT_CREATED = "report_created"
    REPORT_RESOLVED = "report_resolved"
    REPORT_DISMISSED = "report_dismissed"
    RISK_CHANGED = "risk_changed"
    TRUST_SCORE_CHANGED = "trust_score_changed"


# ═══════════════════════════════════════════
# Domain Models
# ═══════════════════════════════════════════

@dataclass
class Review:
    """用户对 AgentModule 的评价。一个 workspace 对同一模块只能有 1 个 active Review。"""
    id: str = field(default_factory=lambda: f"rev_{uuid4().hex[:12]}")
    workspace_id: str = ""
    agent_module_id: str = ""
    rating: int = 5
    title: str = ""
    content: str = ""
    status: str = ReviewStatus.ACTIVE
    created_by: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.workspace_id or not self.workspace_id.strip():
            errors.append("workspace_id 必填")
        if not self.agent_module_id or not self.agent_module_id.strip():
            errors.append("agent_module_id 必填")
        if not 1 <= self.rating <= 5:
            errors.append("rating 必须在 1-5 之间")
        if not self.title or not self.title.strip():
            errors.append("title 必填")
        if self.status not in [v.value for v in ReviewStatus]:
            errors.append(f"status 无效: {self.status}")
        return errors

    def is_valid(self) -> bool: return len(self.validate()) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "workspace_id": self.workspace_id,
            "agent_module_id": self.agent_module_id, "rating": self.rating,
            "title": self.title, "content": self.content, "status": self.status,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Review":
        return cls(
            id=str(d.get("id", "")), workspace_id=str(d.get("workspace_id", "")),
            agent_module_id=str(d.get("agent_module_id", "")),
            rating=int(d.get("rating", 5)), title=str(d.get("title", "")),
            content=str(d.get("content", "")),
            status=str(d.get("status", ReviewStatus.ACTIVE)),
            created_by=str(d.get("created_by", "")),
            created_at=_safe_dt(d.get("created_at")),
            updated_at=_safe_dt(d.get("updated_at")),
        )


@dataclass
class Report:
    """举报 AgentModule。"""
    id: str = field(default_factory=lambda: f"rpt_{uuid4().hex[:12]}")
    workspace_id: str = ""
    agent_module_id: str = ""
    report_type: str = ReportType.OTHER
    title: str = ""
    description: str = ""
    status: str = ReportStatus.OPEN
    created_by: str = ""
    resolved_by: str = ""
    resolved_at: datetime | None = None
    resolution_note: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.workspace_id.strip(): errors.append("workspace_id 必填")
        if not self.agent_module_id.strip(): errors.append("agent_module_id 必填")
        if self.report_type not in [v.value for v in ReportType]:
            errors.append(f"report_type 无效: {self.report_type}")
        if not self.title.strip(): errors.append("title 必填")
        if self.status not in [v.value for v in ReportStatus]:
            errors.append(f"status 无效: {self.status}")
        return errors

    def is_valid(self) -> bool: return len(self.validate()) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "workspace_id": self.workspace_id,
            "agent_module_id": self.agent_module_id, "report_type": self.report_type,
            "title": self.title, "description": self.description,
            "status": self.status, "created_by": self.created_by,
            "resolved_by": self.resolved_by,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolution_note": self.resolution_note,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Report":
        return cls(
            id=str(d.get("id", "")), workspace_id=str(d.get("workspace_id", "")),
            agent_module_id=str(d.get("agent_module_id", "")),
            report_type=str(d.get("report_type", ReportType.OTHER)),
            title=str(d.get("title", "")), description=str(d.get("description", "")),
            status=str(d.get("status", ReportStatus.OPEN)),
            created_by=str(d.get("created_by", "")),
            resolved_by=str(d.get("resolved_by", "")),
            resolved_at=_safe_dt(d.get("resolved_at")),
            resolution_note=str(d.get("resolution_note", "")),
            created_at=_safe_dt(d.get("created_at")),
        )


@dataclass
class TrustScore:
    """AgentModule 信任评分 0-100。纯 Metadata 计算。"""
    agent_module_id: str = ""
    score: float = 50.0
    published_days: int = 0
    review_count: int = 0
    average_rating: float = 0.0
    report_count: int = 0
    resolved_report_count: int = 0
    risk_level: str = RiskLevel.LOW
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_module_id": self.agent_module_id, "score": self.score,
            "published_days": self.published_days, "review_count": self.review_count,
            "average_rating": self.average_rating,
            "report_count": self.report_count,
            "resolved_report_count": self.resolved_report_count,
            "risk_level": self.risk_level,
            "calculated_at": self.calculated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TrustScore":
        return cls(
            agent_module_id=str(d.get("agent_module_id", "")),
            score=float(d.get("score", 50.0)),
            published_days=int(d.get("published_days", 0)),
            review_count=int(d.get("review_count", 0)),
            average_rating=float(d.get("average_rating", 0.0)),
            report_count=int(d.get("report_count", 0)),
            resolved_report_count=int(d.get("resolved_report_count", 0)),
            risk_level=str(d.get("risk_level", RiskLevel.LOW)),
            calculated_at=_safe_dt(d.get("calculated_at")),
        )


@dataclass
class GovernanceEvent:
    """治理审计事件。"""
    id: str = field(default_factory=lambda: f"govevt_{uuid4().hex[:12]}")
    agent_module_id: str = ""
    event_type: str = ""
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "agent_module_id": self.agent_module_id,
            "event_type": self.event_type, "description": self.description,
            "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "GovernanceEvent":
        return cls(
            id=str(d.get("id", "")), agent_module_id=str(d.get("agent_module_id", "")),
            event_type=str(d.get("event_type", "")),
            description=str(d.get("description", "")),
            metadata=dict(d.get("metadata", {})),
            created_at=_safe_dt(d.get("created_at")),
        )


# ═══════════════════════════════════════════
# Store Protocol
# ═══════════════════════════════════════════

@runtime_checkable
class MarketplaceGovernanceStore(Protocol):
    def create_review(self, r: Review) -> Review: ...
    def get_review(self, review_id: str) -> Review | None: ...
    def get_active_review(self, workspace_id: str, agent_module_id: str) -> Review | None: ...
    def list_reviews(self, *, agent_module_id: str = "", workspace_id: str = "",
                     limit: int = 50, offset: int = 0) -> list[Review]: ...
    def update_review(self, r: Review) -> None: ...
    def delete_review(self, review_id: str) -> None: ...
    def get_rating_aggregation(self, agent_module_id: str) -> dict[str, Any]: ...

    def create_report(self, r: Report) -> Report: ...
    def get_report(self, report_id: str) -> Report | None: ...
    def list_reports(self, *, agent_module_id: str = "", status: str = "",
                     limit: int = 50, offset: int = 0) -> list[Report]: ...
    def update_report(self, r: Report) -> None: ...
    def resolve_report(self, report_id: str, status: str, resolved_by: str,
                       resolution_note: str) -> None: ...

    def upsert_trust_score(self, ts: TrustScore) -> None: ...
    def get_trust_score(self, agent_module_id: str) -> TrustScore | None: ...
    def list_trust_scores(self, *, min_score: float = 0,
                          limit: int = 50) -> list[TrustScore]: ...

    def record_event(self, evt: GovernanceEvent) -> None: ...
    def get_timeline(self, agent_module_id: str, *, limit: int = 50) -> list[GovernanceEvent]: ...


# ═══════════════════════════════════════════
# Error Classes
# ═══════════════════════════════════════════

class ReviewNotFoundError(Exception):
    def __init__(self, msg="Review 不存在"): super().__init__(msg)

class ReviewAlreadyExistsError(Exception):
    def __init__(self, msg="已存在 active Review"): super().__init__(msg)

class ReviewValidationError(Exception):
    def __init__(self, msg="Review 校验失败", errors=None):
        super().__init__(msg); self.errors = errors or []

class ReportNotFoundError(Exception):
    def __init__(self, msg="Report 不存在"): super().__init__(msg)

class ReportValidationError(Exception):
    def __init__(self, msg="Report 校验失败", errors=None):
        super().__init__(msg); self.errors = errors or []


def _safe_dt(raw: str | None) -> datetime:
    if not raw: return datetime.now(timezone.utc)
    try: return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError): return datetime.now(timezone.utc)
