"""Sandbox v2 Prometheus Config Builder — Step 18.

生成 Prometheus scrape config + alert rules 示例文件。
不启动 Prometheus，不包含 secret，默认 localhost:8000 或占位符。
"""
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)


class SandboxV2PrometheusConfigBuilder:
    """Prometheus 配置生成器 — 只生成文本，不部署服务。"""

    def __init__(self, scrape_path: str = "/api/runtime/sandbox-v2/monitoring/metrics/prometheus",
                 job_name: str = "sandbox-v2", scrape_interval: str = "15s",
                 host: str = "localhost:8000"):
        self._scrape_path = scrape_path
        self._job_name = job_name
        self._scrape_interval = scrape_interval
        self._host = host

    def build_scrape_config(self) -> dict[str, Any]:
        """Build Prometheus scrape config dict."""
        return {
            "scrape_configs": [{
                "job_name": self._job_name,
                "scrape_interval": self._scrape_interval,
                "metrics_path": self._scrape_path,
                "static_configs": [{
                    "targets": [self._host],
                    "labels": {"service": "sandbox-v2", "environment": "development"},
                }],
            }],
        }

    def build_alerting_rules(self) -> dict[str, Any]:
        """Build Prometheus alerting rules. Corresponds to Step 15 default alerts."""
        return {
            "groups": [{
                "name": "sandbox-v2-alerts",
                "rules": [
                    self._rule("SandboxV2AuditChainFailure", "Audit hash chain verification failures detected",
                               "sandbox_v2_audit_chain_verify_failures_total > 0", "critical", "1m"),
                    self._rule("SandboxV2DeadLetter", "Dead letter items exist in queue",
                               "sandbox_v2_queue_dead_letter_total > 0", "warning", "2m"),
                    self._rule("SandboxV2CrossTenantDenied", "Cross-tenant access attempts detected",
                               "sandbox_v2_cross_tenant_denied_total > 0", "high", "1m"),
                    self._rule("SandboxV2MetadataServiceBlocked", "Metadata service access blocked",
                               "sandbox_v2_metadata_service_blocked_total > 0", "high", "1m"),
                    self._rule("SandboxV2WorkerNoHeartbeat", "Worker heartbeat age exceeds threshold",
                               "sandbox_v2_worker_heartbeat_age_seconds > 300", "critical", "2m"),
                    self._rule("SandboxV2BackendBlocker", "Backend configuration blockers exist",
                               "sandbox_v2_backend_blockers_total > 0", "high", "2m"),
                    self._rule("SandboxV2RedTeamFailed", "Red-team tests have failures",
                               "sandbox_v2_red_team_tests_failed > 0", "critical", "5m"),
                    self._rule("SandboxV2QueueDepthHigh", "Queue depth exceeds threshold",
                               "sandbox_v2_queue_depth > 100", "warning", "2m"),
                    self._rule("SandboxV2NetworkDeniedSpike", "Network denied requests spiking",
                               "rate(sandbox_v2_network_denied_total[5m]) > 0.5", "warning", "2m"),
                ],
            }],
        }

    @staticmethod
    def _rule(alert: str, description: str, expr: str, severity: str, for_duration: str) -> dict[str, Any]:
        return {
            "alert": alert,
            "expr": expr,
            "for": for_duration,
            "labels": {"severity": severity, "service": "sandbox-v2"},
            "annotations": {
                "summary": alert,
                "description": description,
            },
        }

    def export_scrape_yaml(self) -> str:
        """Export scrape config as YAML text example."""
        cfg = self.build_scrape_config()
        return _to_yaml(cfg)

    def export_alert_rules_yaml(self) -> str:
        """Export alert rules as YAML text example."""
        rules = self.build_alerting_rules()
        return _to_yaml(rules)


def _to_yaml(obj: Any, indent: int = 0) -> str:
    """Minimal YAML serializer — no pyyaml dependency needed for simple configs."""
    if obj is None:
        return "null"
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, (int, float)):
        return str(obj)
    if isinstance(obj, str):
        if any(ch in obj for ch in '":{}[]#&*!|>\'"%@`,'):
            return f'"{obj}"'
        return obj
    if isinstance(obj, list):
        if not obj:
            return "[]"
        lines = []
        for item in obj:
            child = _to_yaml(item, indent + 2)
            lines.append(f"{' ' * indent}- {child.lstrip()}")
        return "\n".join(lines)
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        lines = []
        for k, v in obj.items():
            child = _to_yaml(v, indent + 2)
            if isinstance(v, (list, dict)) and v:
                lines.append(f"{' ' * indent}{k}:")
                lines.append(f"  {child}")
            else:
                lines.append(f"{' ' * indent}{k}: {child.lstrip()}")
        return "\n".join(lines)
    return str(obj)
