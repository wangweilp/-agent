"""Usage Collector — 后台用量收集与告警检查服务。

负责:
- 定期评估活跃告警规则
- 检查指标是否超过阈值
- 触发告警事件
- 成本异常检测
"""
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from src.core.alert import (
    AlertCondition,
    AlertEvent,
    AlertMetric,
    AlertRule,
    AlertSeverity,
    NotificationChannel,
)
from src.core.usage import UsageResource

logger = logging.getLogger(__name__)

# 默认检查间隔（秒）
DEFAULT_CHECK_INTERVAL = 300  # 5 minutes
# 事件计数窗口（小时）
EVENT_WINDOW_HOURS = 1


class UsageCollector:
    """后台用量收集器。

    定期检查所有租户的活跃告警规则，评估指标并触发告警。
    """

    def __init__(
        self,
        usage_store: Any,
        alert_store: Any,
        subscription_store: Any,
        memory_store: Any = None,
        check_interval: int = DEFAULT_CHECK_INTERVAL,
    ) -> None:
        self._usage_store = usage_store
        self._alert_store = alert_store
        self._subscription_store = subscription_store
        self._memory_store = memory_store
        self._check_interval = check_interval
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """启动后台线程。"""
        if self._running:
            logger.warning("usage_collector:already_running")
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, name="usage-collector", daemon=True,
        )
        self._thread.start()
        logger.info("usage_collector:started", extra={"interval_s": self._check_interval})

    def shutdown(self) -> None:
        """安全关闭。"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        logger.info("usage_collector:shutdown")

    def _loop(self) -> None:
        """主循环：等待 -> 检查 -> 告警。"""
        while self._running:
            try:
                self._check_all_tenants()
            except Exception:
                logger.exception("usage_collector:check_failed")
            time.sleep(self._check_interval)

    def _check_all_tenants(self) -> None:
        """检查所有租户的告警规则。"""
        # 从 subscriptions 表获取所有租户
        try:
            all_subs = self._subscription_store.list_all_subscriptions()
        except Exception:
            logger.exception("usage_collector:list_subs_failed")
            return

        for sub in all_subs:
            tenant_id = sub.tenant_id
            try:
                self._check_tenant_alerts(tenant_id)
            except Exception:
                logger.exception("usage_collector:tenant_check_failed", extra={"tenant_id": tenant_id})

    def _check_tenant_alerts(self, tenant_id: str) -> None:
        """检查单个租户的所有活跃规则。"""
        active_rules = self._alert_store.get_active_rules(tenant_id)
        if not active_rules:
            return

        # 收集当前指标值
        metrics = self._collect_current_metrics(tenant_id)

        for rule in active_rules:
            current_value = metrics.get(rule.metric)
            if current_value is None:
                continue

            if self._evaluate_condition(rule, current_value):
                self._trigger_alert(rule, tenant_id, current_value)

    def _collect_current_metrics(self, tenant_id: str) -> dict:
        """收集租户当前各指标值。"""
        metrics: dict = {}
        now = datetime.now(timezone.utc)

        try:
            # memory_usage_pct — 从 usage_events 和 subscription limits 计算
            sub = self._subscription_store.get_subscription(tenant_id)
            memory_limit = 100  # default free tier
            if sub:
                from src.core.subscription import PLANS, PlanTier
                tier = (
                    PlanTier(sub.plan_tier)
                    if hasattr(sub.plan_tier, "value")
                    else PlanTier(str(sub.plan_tier))
                )
                limits = PLANS.get(tier)
                memory_limit = limits.memory_count if limits else 100

            memory_count_row = self._usage_store._db.execute(
                """SELECT COUNT(*) AS cnt FROM usage_events
                   WHERE tenant_id = ? AND resource = ?""",
                (tenant_id, UsageResource.MEMORY.value),
            ).fetchone()
            memory_count = int(dict(memory_count_row).get("cnt", 0) or 0)
            metrics[AlertMetric.MEMORY_USAGE_PCT] = (
                round(memory_count / memory_limit * 100, 1) if memory_limit > 0 else 0
            )

            # queue_depth — 从 memory_write queue 估算（通过 usage_events pending 计）
            # 简化：使用过去 5 分钟内未完成的记录数
            five_min_ago = (now - timedelta(minutes=5)).isoformat()
            queue_row = self._usage_store._db.execute(
                "SELECT COUNT(*) AS cnt FROM usage_events WHERE tenant_id = ? AND timestamp >= ?",
                (tenant_id, five_min_ago),
            ).fetchone()
            metrics[AlertMetric.QUEUE_DEPTH] = float(
                int(dict(queue_row).get("cnt", 0) or 0)
            )

            # dlq_backlog — 从 dead_letter 目录估算
            import os
            dlq_dir = os.path.join("data", "dead_letter")
            dlq_count = 0
            if os.path.isdir(dlq_dir):
                dlq_count = len([
                    f for f in os.listdir(dlq_dir)
                    if os.path.isfile(os.path.join(dlq_dir, f))
                ])
            metrics[AlertMetric.DLQ_BACKLOG] = float(dlq_count)

            # daily_cost_cents — 今日总成本
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            cost_row = self._usage_store._db.execute(
                "SELECT COALESCE(SUM(cost_cents), 0) AS cost FROM usage_events WHERE tenant_id = ? AND timestamp >= ?",
                (tenant_id, today_start),
            ).fetchone()
            metrics[AlertMetric.DAILY_COST_CENTS] = float(
                int(dict(cost_row).get("cost", 0) or 0)
            )

            # hourly_event_count — 最近 1 小时的事件数
            one_hour_ago = (now - timedelta(hours=EVENT_WINDOW_HOURS)).isoformat()
            event_row = self._usage_store._db.execute(
                "SELECT COUNT(*) AS cnt FROM usage_events WHERE tenant_id = ? AND timestamp >= ?",
                (tenant_id, one_hour_ago),
            ).fetchone()
            metrics[AlertMetric.HOURLY_EVENT_COUNT] = float(
                int(dict(event_row).get("cnt", 0) or 0)
            )

        except Exception:
            logger.exception("usage_collector:collect_metrics_failed", extra={"tenant_id": tenant_id})

        return metrics

    @staticmethod
    def _evaluate_condition(rule: AlertRule, current_value: float) -> bool:
        """评估是否触发告警。"""
        if rule.condition == AlertCondition.GT:
            return current_value > rule.threshold
        elif rule.condition == AlertCondition.GTE:
            return current_value >= rule.threshold
        elif rule.condition == AlertCondition.LT:
            return current_value < rule.threshold
        elif rule.condition == AlertCondition.LTE:
            return current_value <= rule.threshold
        return False

    def _trigger_alert(self, rule: AlertRule, tenant_id: str,
                       current_value: float) -> None:
        """触发告警事件并更新最后触发时间。"""
        message = (
            f"[{rule.severity.value.upper()}] {rule.name}: "
            f"当前值 {current_value:.1f} "
            f"{_condition_symbol(rule.condition)} 阈值 {rule.threshold:.1f}"
        )

        event = AlertEvent(
            tenant_id=tenant_id,
            rule_id=rule.id,
            rule_name=rule.name,
            metric=rule.metric,
            current_value=current_value,
            threshold=rule.threshold,
            severity=rule.severity,
            channel=rule.channel,
            message=message,
        )

        try:
            self._alert_store.record_event(event)
            # 更新最后触发时间
            self._alert_store.update_rule(
                tenant_id, rule.id,
                {"last_triggered_at": datetime.now(timezone.utc).isoformat()},
            )
            logger.info(
                "usage_collector:alert_triggered",
                extra={
                    "tenant_id": tenant_id,
                    "rule": rule.name,
                    "severity": rule.severity.value,
                    "current": current_value,
                    "threshold": rule.threshold,
                },
            )
        except Exception:
            logger.exception("usage_collector:trigger_failed", extra={
                "tenant_id": tenant_id, "rule_id": rule.id,
            })


def _condition_symbol(condition: AlertCondition) -> str:
    symbols = {
        AlertCondition.GT: ">",
        AlertCondition.GTE: ">=",
        AlertCondition.LT: "<",
        AlertCondition.LTE: "<=",
    }
    return symbols.get(condition, "?")
