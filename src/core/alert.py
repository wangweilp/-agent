"""Alert Domain Models — AlertRule / AlertEvent / AlertStore protocol.

六边形架构核心层：纯数据类 + 协议。
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import uuid4


# ── Enums ──


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertMetric(StrEnum):
    """可监控的指标类型。"""
    MEMORY_USAGE_PCT = "memory_usage_pct"
    QUEUE_DEPTH = "queue_depth"
    DLQ_BACKLOG = "dlq_backlog"
    API_LATENCY = "api_latency"
    COST_SPIKE = "cost_spike"
    ANOMALY_CALLS = "anomaly_calls"
    HOURLY_EVENT_COUNT = "hourly_event_count"
    DAILY_COST_CENTS = "daily_cost_cents"


class AlertCondition(StrEnum):
    GT = "gt"
    LT = "lt"
    GTE = "gte"
    LTE = "lte"


class NotificationChannel(StrEnum):
    EMAIL = "email"
    SYSTEM = "system"
    BOTH = "both"


# ── Data Classes ──


@dataclass
class AlertRule:
    """告警规则定义。"""
    tenant_id: str
    name: str
    metric: AlertMetric
    condition: AlertCondition
    threshold: float
    severity: AlertSeverity = AlertSeverity.WARNING
    channel: NotificationChannel = NotificationChannel.SYSTEM
    enabled: bool = True
    cooldown_minutes: int = 60
    id: str = field(default_factory=lambda: f"alr_{uuid4().hex[:12]}")
    last_triggered_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "metric": self.metric.value,
            "condition": self.condition.value,
            "threshold": self.threshold,
            "severity": self.severity.value,
            "channel": self.channel.value,
            "enabled": self.enabled,
            "cooldown_minutes": self.cooldown_minutes,
            "last_triggered_at": self.last_triggered_at.isoformat() if self.last_triggered_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class AlertEvent:
    """告警历史事件。"""
    tenant_id: str
    rule_id: str
    rule_name: str
    metric: AlertMetric
    current_value: float
    threshold: float
    severity: AlertSeverity
    channel: NotificationChannel
    message: str
    acknowledged: bool = False
    id: str = field(default_factory=lambda: f"ale_{uuid4().hex[:12]}")
    triggered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "metric": self.metric.value,
            "current_value": self.current_value,
            "threshold": self.threshold,
            "severity": self.severity.value,
            "channel": self.channel.value,
            "message": self.message,
            "acknowledged": self.acknowledged,
            "triggered_at": self.triggered_at.isoformat(),
        }


# ── Protocols ──


@runtime_checkable
class AlertStore(Protocol):
    """告警存储协议。"""

    def create_rule(self, rule: AlertRule) -> str: ...
    def get_rule(self, tenant_id: str, rule_id: str) -> AlertRule | None: ...
    def list_rules(self, tenant_id: str, enabled_only: bool = False) -> list[AlertRule]: ...
    def update_rule(self, tenant_id: str, rule_id: str, updates: dict) -> AlertRule | None: ...
    def delete_rule(self, tenant_id: str, rule_id: str) -> bool: ...
    def record_event(self, event: AlertEvent) -> str: ...
    def list_events(self, tenant_id: str, rule_id: str | None = None,
                    severity: str | None = None, acknowledged: bool | None = None,
                    limit: int = 50, offset: int = 0) -> list[AlertEvent]: ...
    def acknowledge_event(self, tenant_id: str, event_id: str) -> bool: ...
    def get_active_rules(self, tenant_id: str) -> list[AlertRule]: ...


# ── Preset Rules ──


def get_preset_rules(tenant_id: str) -> list[AlertRule]:
    """返回预设告警规则列表。"""
    return [
        AlertRule(
            tenant_id=tenant_id,
            name="memory-limit",
            metric=AlertMetric.MEMORY_USAGE_PCT,
            condition=AlertCondition.GT,
            threshold=80.0,
            severity=AlertSeverity.WARNING,
            channel=NotificationChannel.SYSTEM,
            cooldown_minutes=60,
        ),
        AlertRule(
            tenant_id=tenant_id,
            name="memory-critical",
            metric=AlertMetric.MEMORY_USAGE_PCT,
            condition=AlertCondition.GT,
            threshold=95.0,
            severity=AlertSeverity.CRITICAL,
            channel=NotificationChannel.BOTH,
            cooldown_minutes=30,
        ),
        AlertRule(
            tenant_id=tenant_id,
            name="queue-delay",
            metric=AlertMetric.QUEUE_DEPTH,
            condition=AlertCondition.GT,
            threshold=100.0,
            severity=AlertSeverity.WARNING,
            channel=NotificationChannel.SYSTEM,
            cooldown_minutes=30,
        ),
        AlertRule(
            tenant_id=tenant_id,
            name="dlq-backlog",
            metric=AlertMetric.DLQ_BACKLOG,
            condition=AlertCondition.GT,
            threshold=20.0,
            severity=AlertSeverity.CRITICAL,
            channel=NotificationChannel.BOTH,
            cooldown_minutes=15,
        ),
        AlertRule(
            tenant_id=tenant_id,
            name="cost-spike",
            metric=AlertMetric.DAILY_COST_CENTS,
            condition=AlertCondition.GT,
            threshold=1000.0,
            severity=AlertSeverity.WARNING,
            channel=NotificationChannel.SYSTEM,
            cooldown_minutes=120,
        ),
        AlertRule(
            tenant_id=tenant_id,
            name="anomaly-calls",
            metric=AlertMetric.HOURLY_EVENT_COUNT,
            condition=AlertCondition.GT,
            threshold=10000.0,
            severity=AlertSeverity.WARNING,
            channel=NotificationChannel.SYSTEM,
            cooldown_minutes=60,
        ),
    ]
