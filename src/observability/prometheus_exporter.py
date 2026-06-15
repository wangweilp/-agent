"""Step 23 — Prometheus Metrics Exporter.

Exposes /metrics endpoint in Prometheus text format.
Reads from global MetricsRegistry.
Default: disabled (PROMETHEUS_ENABLED=false).
"""
from __future__ import annotations

import logging
from typing import Any

from src.observability.metrics_registry import get_metrics_registry

logger = logging.getLogger(__name__)


class PrometheusExporter:
    """Prometheus /metrics exporter. Reads from global registry."""

    def __init__(self, settings: Any = None):
        self._settings = settings

    def _cfg(self, key: str, default: Any = None) -> Any:
        return getattr(self._settings, key, default) if self._settings else default

    @property
    def enabled(self) -> bool:
        return bool(self._cfg("prometheus_enabled", False))

    def export_prometheus_text(self) -> str:
        """Export all registered metrics in Prometheus text format."""
        if not self.enabled:
            return "# Prometheus metrics export is disabled (PROMETHEUS_ENABLED=false)\n"
        reg = get_metrics_registry()
        return reg.export_prometheus_text()

    def export_json(self) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "metrics": {}}
        reg = get_metrics_registry()
        return {"enabled": True, "metrics": reg.export_json()}

    def get_readiness(self) -> dict[str, Any]:
        reg = get_metrics_registry()
        all_metrics = reg.list_all()
        return {
            "enabled": self.enabled,
            "ready": self.enabled,
            "status": "ready" if self.enabled else "disabled",
            "reason": "" if self.enabled else "PROMETHEUS_ENABLED=false",
            "metrics_registered": len(all_metrics),
            "metric_names": sorted(all_metrics.keys())[:50],
        }
