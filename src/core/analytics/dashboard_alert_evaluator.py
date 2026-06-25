"""Dashboard Alert Evaluator — Dashboard V2 告警规则评估器。

接入已有 alert_store（AlertStoreAdapter），新增 3 条 Dashboard 告警规则：
1. Agent Success Rate < 95% → HIGH
2. Agent P95 Latency > 2000ms → MEDIUM
3. Token Daily Cost > configured_threshold → HIGH

设计原则：
- 可扩展：新增规则只需在 _RULES 中注册
- 失败降级：评估异常仅记录日志，不抛出
- 复用现有 AlertStoreAdapter.create_rule() / record_event()
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from src.core.analytics.analytics_repository import AnalyticsRepository
from src.core.alert import (
    AlertCondition,
    AlertEvent,
    AlertMetric,
    AlertSeverity,
    AlertRule,
    NotificationChannel,
)

logger = logging.getLogger(__name__)


@dataclass
class AlertRuleDef:
    """告警规则定义（可扩展）。"""
    name: str
    metric: AlertMetric
    condition: AlertCondition
    threshold: float
    severity: AlertSeverity
    description: str


class DashboardAlertEvaluator:
    """Dashboard V2 告警评估器。

    评估 AnalyticsRepository 中的指标，触发阈值时记录 AlertEvent。
    """

    # ── 规则定义（可扩展）──
    _RULES: list[AlertRuleDef] = [
        AlertRuleDef(
            name="agent_success_rate_low",
            metric=AlertMetric.API_LATENCY,  # 复用现有 metric（无 AGENT_SUCCESS_RATE 枚举）
            condition=AlertCondition.LT,
            threshold=95.0,
            severity=AlertSeverity.CRITICAL,  # HIGH
            description="Agent 成功率低于 95%",
        ),
        AlertRuleDef(
            name="agent_p95_latency_high",
            metric=AlertMetric.API_LATENCY,
            condition=AlertCondition.GT,
            threshold=2000.0,
            severity=AlertSeverity.WARNING,  # MEDIUM
            description="Agent P95 延迟超过 2000ms",
        ),
        AlertRuleDef(
            name="token_daily_cost_high",
            metric=AlertMetric.DAILY_COST_CENTS,
            condition=AlertCondition.GT,
            threshold=10_000_000,  # 默认 10 万分（¥1000），可配置
            severity=AlertSeverity.CRITICAL,  # HIGH
            description="Token 日成本超过阈值",
        ),
    ]

    def __init__(
        self,
        repo: AnalyticsRepository,
        alert_store,
        token_cost_threshold_cents: int = 10_000_000,
    ) -> None:
        self._repo = repo
        self._alert_store = alert_store
        # 覆盖默认阈值
        self._token_cost_threshold = token_cost_threshold_cents

    def evaluate_all(self, tenant_id: str = "") -> list[AlertEvent]:
        """评估所有规则，返回触发的 AlertEvent 列表。

        Args:
            tenant_id: 租户 ID（空则全局）
        Returns:
            触发的 AlertEvent 列表（已写入 alert_store）
        """
        triggered: list[AlertEvent] = []
        for rule_def in self._RULES:
            try:
                event = self._evaluate_rule(rule_def, tenant_id)
                if event is not None:
                    triggered.append(event)
            except Exception:
                logger.warning(
                    "dashboard_alert_evaluate_failed",
                    exc_info=True,
                    extra={"rule": rule_def.name},
                )
        return triggered

    def _evaluate_rule(self, rule_def: AlertRuleDef, tenant_id: str) -> AlertEvent | None:
        """评估单条规则。"""
        current_value = self._get_metric_value(rule_def.name, tenant_id)
        if current_value is None:
            return None

        # 应用自定义阈值（token_daily_cost_high）
        threshold = rule_def.threshold
        if rule_def.name == "token_daily_cost_high":
            threshold = self._token_cost_threshold

        triggered = self._check_condition(rule_def.condition, current_value, threshold)
        if not triggered:
            return None

        # 构造 AlertEvent 并写入 alert_store
        event = AlertEvent(
            tenant_id=tenant_id or "default",
            rule_id=f"dashboard_{rule_def.name}",
            rule_name=rule_def.name,
            metric=rule_def.metric,
            current_value=current_value,
            threshold=threshold,
            severity=rule_def.severity,
            channel=NotificationChannel.SYSTEM,
            message=f"{rule_def.description}: 当前值 {current_value}, 阈值 {threshold}",
        )
        try:
            self._alert_store.record_event(event)
        except Exception:
            logger.warning("dashboard_alert_record_failed", exc_info=True, extra={"rule": rule_def.name})
        return event

    def _get_metric_value(self, rule_name: str, tenant_id: str) -> float | None:
        """根据规则名获取当前指标值。"""
        if rule_name == "agent_success_rate_low":
            return self._repo.get_agent_success_rate(tenant_id, days=1)
        if rule_name == "agent_p95_latency_high":
            return self._repo.get_p95_latency_ms(tenant_id, days=1)
        if rule_name == "token_daily_cost_high":
            return float(self._repo.get_token_cost_cents(tenant_id, days=1))
        return None

    @staticmethod
    def _check_condition(condition: AlertCondition, value: float, threshold: float) -> bool:
        """检查条件是否满足。"""
        if condition == AlertCondition.GT:
            return value > threshold
        if condition == AlertCondition.LT:
            return value < threshold
        if condition == AlertCondition.GTE:
            return value >= threshold
        if condition == AlertCondition.LTE:
            return value <= threshold
        return False

    def seed_dashboard_rules(self, tenant_id: str) -> list[str]:
        """将 Dashboard 告警规则写入 alert_store（供 /alerts/rules 查询）。

        Returns:
            创建的 rule_id 列表
        """
        rule_ids: list[str] = []
        for rule_def in self._RULES:
            threshold = rule_def.threshold
            if rule_def.name == "token_daily_cost_high":
                threshold = self._token_cost_threshold
            rule = AlertRule(
                tenant_id=tenant_id,
                name=rule_def.name,
                metric=rule_def.metric,
                condition=rule_def.condition,
                threshold=threshold,
                severity=rule_def.severity,
                channel=NotificationChannel.SYSTEM,
            )
            try:
                rule_id = self._alert_store.create_rule(rule)
                rule_ids.append(rule_id)
            except Exception:
                logger.warning("dashboard_alert_seed_failed", exc_info=True, extra={"rule": rule_def.name})
        return rule_ids
