"""Sandbox v2 Grafana Dashboard Builder — Step 18.

生成 Grafana dashboard JSON spec。只生成 JSON，不连接 Grafana API。
不包含密钥，不包含本地绝对路径。
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any

from src.open_platform.sandbox_v2.models import SandboxV2GrafanaDashboardSpec

logger = logging.getLogger(__name__)

_DS = "${DS_PROMETHEUS}"
_METRIC_PREFIX = "sandbox_v2_"


def _panel(title: str, description: str, expr: str, panel_id: int,
           y: int = 0, panel_type: str = "stat") -> dict[str, Any]:
    return {
        "id": panel_id, "type": panel_type, "title": title,
        "description": description,
        "gridPos": {"h": 8, "w": 6, "x": (panel_id % 4) * 6, "y": y},
        "targets": [{"expr": expr, "datasource": {"type": "prometheus", "uid": _DS}}],
        "fieldConfig": {"defaults": {"thresholds": {"steps": [
            {"color": "green", "value": None}, {"color": "red", "value": 1}
        ]}}},
    }


class SandboxV2GrafanaDashboardBuilder:
    """Grafana dashboard JSON 生成器。"""

    def __init__(self):
        self._panels: list[dict[str, Any]] = []
        self._pid = 0

    def _next_id(self) -> int:
        self._pid += 1
        return self._pid

    def _add_stat(self, title: str, desc: str, expr: str, y: int = 0):
        self._panels.append(_panel(title, desc, f"{_METRIC_PREFIX}{expr}", self._next_id(), y, "stat"))

    def _add_timeseries(self, title: str, desc: str, expr: str, y: int = 0):
        self._panels.append(_panel(title, desc, f"rate({_METRIC_PREFIX}{expr}[5m])", self._next_id(), y, "timeseries"))

    def build_overview_dashboard(self) -> SandboxV2GrafanaDashboardSpec:
        self._panels.clear()
        self._pid = 0

        # Row 1: Job stats
        self._add_stat("Jobs Created", "Total jobs created", "jobs_created_total", 0)
        self._add_stat("Jobs Completed", "Total jobs completed", "jobs_completed_total", 0)
        self._add_stat("Jobs Failed", "Total jobs failed", "jobs_failed_total", 0)
        self._add_stat("Jobs Canceled", "Total jobs canceled", "jobs_canceled_total", 0)

        # Row 2: Queue & Worker
        self._add_stat("Queue Depth", "Current queue depth", "queue_depth", 8)
        self._add_stat("Dead Letter", "Dead letter items", "queue_dead_letter_total", 8)
        self._add_stat("Worker Heartbeat Age", "Worker heartbeat age (s)", "worker_heartbeat_age_seconds", 8)

        # Row 3: Security
        self._add_stat("Cross-Tenant Denied", "Cross-tenant access denied", "cross_tenant_denied_total", 16)
        self._add_stat("Network Denied", "Network egress denied", "network_denied_total", 16)
        self._add_stat("Metadata Blocked", "Metadata service blocked", "metadata_service_blocked_total", 16)
        self._add_stat("Kill Requests", "Total kill requests", "kill_requests_total", 16)

        # Row 4: Audit & Red-Team
        self._add_stat("Audit Chain Failures", "Audit hash chain failures", "audit_chain_verify_failures_total", 24)
        self._add_stat("Red-Team Failed", "Red-team tests failed", "red_team_tests_failed", 24)
        self._add_stat("Access Denied", "Access denied total", "access_denied_total", 24)

        # Row 5: Package & Backend
        self._add_stat("Package Quarantined", "Packages in quarantine", "package_quarantined_total", 32)
        self._add_stat("Package Rejected", "Packages rejected", "package_rejected_total", 32)
        self._add_stat("Backend Blockers", "Backend configuration blockers", "backend_blockers_total", 32)

        # Row 6: Performance
        self._add_stat("Benchmark Results", "Benchmark results total", "benchmark_results_total", 40)
        self._add_stat("Alert Count", "Alert count by severity", "alerts_total", 40)

        # Add timeseries for rate panels
        self._add_timeseries("Network Denied Rate", "Network denied per second", "network_denied_total", 48)
        self._add_timeseries("Job Created Rate", "Jobs per second", "jobs_created_total", 48)

        return SandboxV2GrafanaDashboardSpec(
            title="Sandbox v2 — Overview",
            version="1.0",
            panels=list(self._panels),
            datasource=_DS,
            tags=["sandbox-v2", "observability", "step-18"],
            generated_at=datetime.now(timezone.utc),
        )

    def build_security_dashboard(self) -> SandboxV2GrafanaDashboardSpec:
        self._panels.clear()
        self._pid = 0

        self._add_stat("Access Denied", "Access denied events", "access_denied_total", 0)
        self._add_stat("Cross-Tenant Denied", "Cross-tenant violations", "cross_tenant_denied_total", 0)
        self._add_stat("Audit Chain Fails", "Hash chain failures", "audit_chain_verify_failures_total", 0)
        self._add_stat("Red-Team Failed", "Red-team test failures", "red_team_tests_failed", 0)
        self._add_stat("Network Denied", "Network egress blocked", "network_denied_total", 8)
        self._add_stat("Metadata Blocked", "Metadata service blocked", "metadata_service_blocked_total", 8)
        self._add_stat("Kill Rejected", "Kill requests rejected", "kill_rejected_total", 8)

        self._add_timeseries("Access Denied Rate", "Denied per second", "access_denied_total", 16)
        self._add_timeseries("Cross-Tenant Rate", "Cross-tenant per second", "cross_tenant_denied_total", 16)

        return SandboxV2GrafanaDashboardSpec(
            title="Sandbox v2 — Security",
            version="1.0",
            panels=list(self._panels),
            datasource=_DS,
            tags=["sandbox-v2", "security", "observability"],
            generated_at=datetime.now(timezone.utc),
        )

    def build_runtime_dashboard(self) -> SandboxV2GrafanaDashboardSpec:
        self._panels.clear()
        self._pid = 0
        self._add_stat("Queue Depth", "Queue depth", "queue_depth", 0)
        self._add_stat("Dead Letter", "Dead letter total", "queue_dead_letter_total", 0)
        self._add_stat("Worker Heartbeat Age", "Heartbeat age (s)", "worker_heartbeat_age_seconds", 0)
        self._add_stat("Kill Requests", "Kill total", "kill_requests_total", 0)
        self._add_stat("Worker Failures", "Worker failures", "worker_failures_total", 8)
        self._add_stat("Backend Blockers", "Backend blockers", "backend_blockers_total", 8)
        return SandboxV2GrafanaDashboardSpec(
            title="Sandbox v2 — Runtime",
            version="1.0", panels=list(self._panels), datasource=_DS,
            tags=["sandbox-v2", "runtime", "observability"],
            generated_at=datetime.now(timezone.utc),
        )

    def build_performance_dashboard(self) -> SandboxV2GrafanaDashboardSpec:
        self._panels.clear()
        self._pid = 0
        self._add_stat("Benchmark Results", "Total benchmark results", "benchmark_results_total", 0)
        self._add_stat("Benchmark Failures", "Benchmark failures", "benchmark_failures_total", 0)
        self._add_stat("Capacity (jobs/min)", "Jobs per minute", "capacity_jobs_per_minute", 0)
        self._add_stat("Artifact Created", "Artifacts created", "artifact_created_total", 0)
        self._add_stat("Artifact Rejected", "Artifacts rejected", "artifact_rejected_total", 8)
        self._add_timeseries("Job Rate", "Jobs per second", "jobs_created_total", 16)
        return SandboxV2GrafanaDashboardSpec(
            title="Sandbox v2 — Performance",
            version="1.0", panels=list(self._panels), datasource=_DS,
            tags=["sandbox-v2", "performance", "observability"],
            generated_at=datetime.now(timezone.utc),
        )

    def export_dashboard_json(self) -> dict[str, Any]:
        """Export all dashboards as JSON."""
        return {
            "overview": self.build_overview_dashboard().to_dict(),
            "security": self.build_security_dashboard().to_dict(),
            "runtime": self.build_runtime_dashboard().to_dict(),
            "performance": self.build_performance_dashboard().to_dict(),
        }
