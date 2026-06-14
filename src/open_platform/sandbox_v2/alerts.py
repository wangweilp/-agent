"""Sandbox v2 Alert Engine — Step 15 告警引擎。

默认告警规则 + 内部 alert record 管理。
不发送外部通知（external_notifications=false）。
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any

from src.open_platform.sandbox_v2.models import (
    SandboxV2AlertRule, SandboxV2Alert, SandboxV2AlertRuleType,
    SandboxV2AlertSeverityStep15, SandboxV2AlertStatusStep15,
    SandboxV2AuditEventType, SandboxV2AuditSeverity,
)

logger = logging.getLogger(__name__)

_DEFAULT_RULES: list[dict[str, Any]] = [
    {"name": "queue-dead-letter", "rule_type": SandboxV2AlertRuleType.THRESHOLD, "metric_name": "queue_dead_letter_total", "threshold": 0, "comparison": "gt", "severity": SandboxV2AlertSeverityStep15.HIGH, "description": "Dead letter items exist"},
    {"name": "queue-depth-high", "rule_type": SandboxV2AlertRuleType.THRESHOLD, "metric_name": "queue_depth", "threshold": 100, "comparison": "gt", "severity": SandboxV2AlertSeverityStep15.WARNING, "description": "Queue depth > 100"},
    {"name": "worker-no-heartbeat", "rule_type": SandboxV2AlertRuleType.THRESHOLD, "metric_name": "worker_heartbeat_age_seconds", "threshold": 300, "comparison": "gt", "severity": SandboxV2AlertSeverityStep15.CRITICAL, "description": "Worker heartbeat age > 300s"},
    {"name": "network-denied-spike", "rule_type": SandboxV2AlertRuleType.THRESHOLD, "metric_name": "network_denied_total", "threshold": 10, "comparison": "gt", "severity": SandboxV2AlertSeverityStep15.WARNING, "description": "Network denied > 10"},
    {"name": "cross-tenant-denied", "rule_type": SandboxV2AlertRuleType.THRESHOLD, "metric_name": "cross_tenant_denied_total", "threshold": 0, "comparison": "gt", "severity": SandboxV2AlertSeverityStep15.HIGH, "description": "Cross-tenant access denied"},
    {"name": "audit-chain-failure", "rule_type": SandboxV2AlertRuleType.THRESHOLD, "metric_name": "audit_chain_verify_failures_total", "threshold": 0, "comparison": "gt", "severity": SandboxV2AlertSeverityStep15.CRITICAL, "description": "Audit hash chain verification failures"},
    {"name": "artifact-rejected-spike", "rule_type": SandboxV2AlertRuleType.THRESHOLD, "metric_name": "artifact_rejected_total", "threshold": 20, "comparison": "gt", "severity": SandboxV2AlertSeverityStep15.WARNING, "description": "Artifact rejected > 20"},
    {"name": "backend-blocker-exists", "rule_type": SandboxV2AlertRuleType.THRESHOLD, "metric_name": "backend_blockers_total", "threshold": 0, "comparison": "gt", "severity": SandboxV2AlertSeverityStep15.HIGH, "description": "Backend blockers exist"},
    {"name": "red-team-failed", "rule_type": SandboxV2AlertRuleType.THRESHOLD, "metric_name": "red_team_tests_failed", "threshold": 0, "comparison": "gt", "severity": SandboxV2AlertSeverityStep15.CRITICAL, "description": "Red-team tests failed"},
]


class SandboxV2AlertEngine:

    def __init__(self, store: Any = None, audit_service: Any = None):
        self._store = store
        self._audit = audit_service

    def get_default_rules(self) -> list[dict[str, Any]]:
        return list(_DEFAULT_RULES)

    def _ensure_rules(self):
        if self._store:
            for rule_data in _DEFAULT_RULES:
                try:
                    existing = getattr(self._store, 'list_alert_rules', lambda **kw: [])()
                    names = [getattr(r, 'name', '') for r in existing]
                    if rule_data["name"] not in names:
                        rule = SandboxV2AlertRule(
                            name=rule_data["name"], description=rule_data.get("description", ""),
                            rule_type=rule_data.get("rule_type", "threshold"),
                            metric_name=rule_data.get("metric_name", ""),
                            threshold=rule_data.get("threshold", 0),
                            comparison=rule_data.get("comparison", "gt"),
                            severity=rule_data.get("severity", "warning"),
                            enabled=True,
                        )
                        self._store.create_alert_rule(rule)
                except Exception:
                    pass

    def evaluate_rule(self, rule: Any, metrics: dict[str, float]) -> SandboxV2Alert | None:
        metric_name = getattr(rule, 'metric_name', rule.get('metric_name', '')) if isinstance(rule, dict) else getattr(rule, 'metric_name', '')
        comparison = getattr(rule, 'comparison', rule.get('comparison', 'gt')) if isinstance(rule, dict) else getattr(rule, 'comparison', 'gt')
        threshold = getattr(rule, 'threshold', rule.get('threshold', 0)) if isinstance(rule, dict) else getattr(rule, 'threshold', 0)
        name = getattr(rule, 'name', rule.get('name', '')) if isinstance(rule, dict) else getattr(rule, 'name', '')
        severity = getattr(rule, 'severity', rule.get('severity', 'warning')) if isinstance(rule, dict) else getattr(rule, 'severity', 'warning')
        rule_id = getattr(rule, 'alert_rule_id', rule.get('alert_rule_id', '')) if isinstance(rule, dict) else getattr(rule, 'alert_rule_id', '')

        value = metrics.get(metric_name, 0)
        triggered = False
        if comparison == "gt": triggered = value > threshold
        elif comparison == "lt": triggered = value < threshold
        elif comparison == "gte": triggered = value >= threshold
        elif comparison == "lte": triggered = value <= threshold
        elif comparison == "eq": triggered = value == threshold

        if triggered:
            return SandboxV2Alert(
                alert_rule_id=rule_id, name=name,
                severity=severity, status=SandboxV2AlertStatusStep15.OPEN,
                reason=f"{name}: value {value} {comparison} threshold {threshold}",
                observed_value=value, threshold=threshold,
            )
        return None

    def evaluate_all(self, metrics_snapshot: dict[str, float], org: str = "", ws: str = "") -> list[SandboxV2Alert]:
        self._ensure_rules()
        alerts: list[SandboxV2Alert] = []
        rules: list[Any] = []
        if self._store:
            try: rules = self._store.list_alert_rules(organization_id=org or None, workspace_id=ws or None, enabled=True, limit=100)
            except Exception: rules = []
        if not rules:
            for rd in _DEFAULT_RULES:
                rule = SandboxV2AlertRule(name=rd["name"], rule_type=rd["rule_type"],
                                          metric_name=rd["metric_name"], threshold=rd["threshold"],
                                          comparison=rd["comparison"], severity=rd["severity"])
                rules.append(rule)
        for rule in rules:
            alert = self.evaluate_rule(rule, metrics_snapshot)
            if alert:
                alert.organization_id = org; alert.workspace_id = ws
                if self._store:
                    try: self._store.create_alert(alert)
                    except Exception: pass
                if self._audit:
                    try:
                        self._audit.create_audit_event(
                            event_type="alert_triggered", severity=alert.severity,
                            organization_id=org, workspace_id=ws,
                            resource_type="alert", resource_id=alert.alert_id,
                            action="evaluate", decision="alert",
                            reason=alert.reason,
                        )
                    except Exception: pass
                alerts.append(alert)
        return alerts

    def acknowledge_alert(self, alert_id: str, actor: str = "") -> dict[str, Any]:
        if self._store:
            try:
                return self._store.update_alert_status(alert_id, SandboxV2AlertStatusStep15.ACKNOWLEDGED, reason=f"Acknowledged by {actor}", actor=actor)
            except Exception as e:
                return {"error": str(e)}
        return {"error": "No store"}

    def resolve_alert(self, alert_id: str, actor: str = "") -> dict[str, Any]:
        if self._store:
            try:
                return self._store.update_alert_status(alert_id, SandboxV2AlertStatusStep15.RESOLVED, reason=f"Resolved by {actor}", actor=actor)
            except Exception as e:
                return {"error": str(e)}
        return {"error": "No store"}

    def list_alerts(self, org: str = "", ws: str = "", status: str | None = None, severity: str | None = None, limit: int = 100) -> list[Any]:
        if self._store:
            try: return self._store.list_alerts(status=status, severity=severity, organization_id=org or None, workspace_id=ws or None, limit=limit)
            except Exception: pass
        return []

    def list_rules(self, org: str = "", ws: str = "", enabled: bool | None = None, limit: int = 100) -> list[Any]:
        self._ensure_rules()
        if self._store:
            try: return self._store.list_alert_rules(organization_id=org or None, workspace_id=ws or None, enabled=enabled, limit=limit)
            except Exception: pass
        return []

    def get_alert_readiness(self) -> dict[str, Any]:
        return {
            "alert_engine": True, "internal_alert_records": True,
            "external_notifications": False, "default_rules_present": len(_DEFAULT_RULES),
            "alert_rules_present": True, "monitoring_safe_mode": True,
        }
