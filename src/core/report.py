"""Report Domain Models — Report / ReportType / ReportFormat / ReportStore protocol.

六边形架构核心层：纯数据类 + 协议。
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import uuid4


# ── Enums ──


class ReportType(StrEnum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class ReportFormat(StrEnum):
    JSON = "json"
    CSV = "csv"
    PDF = "pdf"


class ReportStatus(StrEnum):
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


# ── Data Classes ──


@dataclass
class ReportData:
    """报告内含数据 — 所有指标聚合。"""
    # 基本信息
    report_type: ReportType
    period_start: str
    period_end: str

    # SaaS 指标
    mrr_cents: int = 0
    arr_cents: int = 0
    total_tenants: int = 0
    active_tenants: int = 0
    paying_tenants: int = 0
    trial_tenants: int = 0
    conversion_rate: float = 0.0
    churn_rate: float = 0.0
    retention_rate: float = 0.0

    # 用量指标
    total_memories_created: int = 0
    total_llm_calls: int = 0
    total_embedding_calls: int = 0
    total_searches: int = 0
    total_imports: int = 0
    total_syncs: int = 0
    total_coach_sessions: int = 0

    # 成本与收入
    total_cost_cents: int = 0
    total_revenue_cents: int = 0
    net_revenue_cents: int = 0
    margin_percent: float = 0.0

    # 用户行为
    active_users: int = 0
    new_users: int = 0
    top_entities: list[dict] = field(default_factory=list)
    top_contributors: list[dict] = field(default_factory=list)
    import_channels: dict[str, int] = field(default_factory=dict)

    # 趋势数据（用于图表）
    daily_usage_trend: list[dict] = field(default_factory=list)
    memory_growth_trend: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "report_type": self.report_type.value,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "mrr_cents": self.mrr_cents,
            "arr_cents": self.arr_cents,
            "total_tenants": self.total_tenants,
            "active_tenants": self.active_tenants,
            "paying_tenants": self.paying_tenants,
            "trial_tenants": self.trial_tenants,
            "conversion_rate": self.conversion_rate,
            "churn_rate": self.churn_rate,
            "retention_rate": self.retention_rate,
            "total_memories_created": self.total_memories_created,
            "total_llm_calls": self.total_llm_calls,
            "total_embedding_calls": self.total_embedding_calls,
            "total_searches": self.total_searches,
            "total_imports": self.total_imports,
            "total_syncs": self.total_syncs,
            "total_coach_sessions": self.total_coach_sessions,
            "total_cost_cents": self.total_cost_cents,
            "total_revenue_cents": self.total_revenue_cents,
            "net_revenue_cents": self.net_revenue_cents,
            "margin_percent": self.margin_percent,
            "active_users": self.active_users,
            "new_users": self.new_users,
            "top_entities": self.top_entities,
            "top_contributors": self.top_contributors,
            "import_channels": self.import_channels,
            "daily_usage_trend": self.daily_usage_trend,
            "memory_growth_trend": self.memory_growth_trend,
        }


@dataclass
class Report:
    """报告记录。"""
    tenant_id: str
    report_type: ReportType
    period_start: str
    period_end: str
    format: ReportFormat = ReportFormat.JSON
    status: ReportStatus = ReportStatus.GENERATING
    data: ReportData | None = None
    id: str = field(default_factory=lambda: f"rpt_{uuid4().hex[:12]}")
    file_path: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "report_type": self.report_type.value,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "format": self.format.value,
            "status": self.status.value,
            "data": self.data.as_dict() if self.data else None,
            "file_path": self.file_path,
            "created_at": self.created_at.isoformat(),
        }


# ── Protocols ──


@runtime_checkable
class ReportStore(Protocol):
    """报告存储协议。"""

    def create_report(self, report: Report) -> str: ...
    def get_report(self, tenant_id: str, report_id: str) -> Report | None: ...
    def list_reports(self, tenant_id: str, report_type: str | None = None,
                     limit: int = 20) -> list[Report]: ...
    def update_report(self, tenant_id: str, report_id: str,
                      updates: dict) -> Report | None: ...
    def delete_report(self, tenant_id: str, report_id: str) -> bool: ...
    def export_csv(self, report: Report) -> str: ...
    def export_json(self, report: Report) -> str: ...


# ── Helpers ──


def compute_period_range(report_type: ReportType, now: datetime | None = None) -> tuple[str, str]:
    """计算报告周期的起止日期。

    Returns (period_start, period_end) as ISO date strings.
    """
    from datetime import timedelta

    if now is None:
        now = datetime.now(timezone.utc)

    today = now.date()

    if report_type == ReportType.WEEKLY:
        # 本周一到周日
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        return monday.isoformat(), sunday.isoformat()

    elif report_type == ReportType.MONTHLY:
        # 本月 1 日到月末
        first = today.replace(day=1)
        if today.month == 12:
            last = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            last = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        return first.isoformat(), last.isoformat()

    elif report_type == ReportType.QUARTERLY:
        # 本季首月 1 日到季末
        quarter_month = ((today.month - 1) // 3) * 3 + 1
        first = today.replace(month=quarter_month, day=1)
        if quarter_month + 3 > 12:
            last = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            last = today.replace(month=quarter_month + 3, day=1) - timedelta(days=1)
        return first.isoformat(), last.isoformat()

    return today.isoformat(), today.isoformat()
