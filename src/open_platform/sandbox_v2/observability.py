"""Sandbox v2 Observability Service — Step 18.

统一的 observability 集成服务：
- Prometheus metrics 导出 (复用 Step 15)
- Grafana dashboard 生成
- OpenTelemetry adapter 集成
- Trace span 管理
- Telemetry export 记录

不发送外部 telemetry，不访问外网，不连接 OTel Collector。
"""
from __future__ import annotations
import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from src.open_platform.sandbox_v2.models import (
    SandboxV2ObservabilityConfig,
    SandboxV2TraceSpan,
    SandboxV2TraceSpanStatus,
    SandboxV2TelemetryExportRecord,
    SandboxV2TelemetryExportStatus,
    SandboxV2TelemetrySignalType,
    SandboxV2GrafanaDashboardSpec,
)
from src.open_platform.sandbox_v2.otel_adapter import (
    get_otel_exporter, sanitize_attributes as _sanitize,
)
from src.open_platform.sandbox_v2.grafana import SandboxV2GrafanaDashboardBuilder
from src.open_platform.sandbox_v2.prometheus import SandboxV2PrometheusConfigBuilder

logger = logging.getLogger(__name__)


class SandboxV2ObservabilityService:
    """Sandbox v2 可观测性集成服务。"""

    def __init__(self, store: Any = None, metrics_collector: Any = None, settings: Any = None):
        self._store = store
        self._metrics = metrics_collector
        self._settings = settings

    @property
    def _cfg(self) -> SandboxV2ObservabilityConfig:
        s = self._settings
        return SandboxV2ObservabilityConfig(
            observability_enabled=bool(getattr(s, 'observability_enabled', False)),
            prometheus_export_enabled=bool(getattr(s, 'prometheus_export_enabled', True)),
            prometheus_scrape_path=str(getattr(s, 'prometheus_scrape_path', '')),
            grafana_dashboard_enabled=bool(getattr(s, 'grafana_dashboard_enabled', False)),
            otel_enabled=bool(getattr(s, 'otel_enabled', False)),
            otel_exporter=str(getattr(s, 'otel_exporter', 'disabled')),
            otel_endpoint_ref=str(getattr(s, 'otel_endpoint', '')),
            otel_service_name=str(getattr(s, 'otel_service_name', 'sandbox-v2')),
            otel_traces_enabled=bool(getattr(s, 'otel_traces_enabled', False)),
            otel_metrics_enabled=bool(getattr(s, 'otel_metrics_enabled', False)),
            otel_logs_enabled=bool(getattr(s, 'otel_logs_enabled', False)),
            include_sensitive_attributes=bool(getattr(s, 'otel_include_sensitive_attributes', False)),
            safe_mode=bool(getattr(s, 'observability_safe_mode', True)),
        )

    # ── Config / Readiness ──

    def get_observability_config(self) -> SandboxV2ObservabilityConfig:
        return self._cfg

    def get_observability_readiness(self) -> dict[str, Any]:
        cfg = self._cfg
        otel_readiness = self.get_otel_adapter_readiness()
        blockers: list[str] = []
        warnings: list[str] = []
        if cfg.otel_enabled and cfg.otel_exporter not in ("disabled", "mock"):
            warnings.append("OTel real export is not implemented in Step 18")
        if cfg.include_sensitive_attributes:
            blockers.append("Sensitive attributes must not be included in telemetry")
        return {
            "observability_config": True,
            "prometheus_scrape_config": True,
            "prometheus_alert_rules": True,
            "grafana_dashboard_spec": True,
            "otel_adapter": True,
            "otel_real_export": False,
            "external_telemetry_export": False,
            "telemetry_redaction": True,
            "trace_span_store": self._store is not None,
            "observability_safe_mode": cfg.safe_mode,
            "observability_enabled": cfg.observability_enabled,
            "prometheus_export_enabled": cfg.prometheus_export_enabled,
            "grafana_dashboard_enabled": cfg.grafana_dashboard_enabled,
            **otel_readiness,
            "blockers": blockers,
            "warnings": warnings,
        }

    # ── Prometheus ──

    def generate_prometheus_scrape_config(self, job_name: str = "sandbox-v2",
                                          host: str = "localhost:8000") -> dict[str, Any]:
        builder = SandboxV2PrometheusConfigBuilder(
            scrape_path=self._cfg.prometheus_scrape_path or "/api/runtime/sandbox-v2/monitoring/metrics/prometheus",
            job_name=job_name, host=host,
        )
        return builder.build_scrape_config()

    def generate_prometheus_alert_rules(self) -> dict[str, Any]:
        builder = SandboxV2PrometheusConfigBuilder()
        return builder.build_alerting_rules()

    def export_metrics_to_prometheus_text(self, organization_id: str = "", workspace_id: str = "") -> str:
        """Export metrics in Prometheus text format. Reuses Step 15 collector."""
        if not self._metrics:
            return "# No metrics collector configured\n"
        try:
            return self._metrics.export_prometheus_text(
                organization_id=organization_id, workspace_id=workspace_id,
            )
        except Exception:
            try:
                data = self._metrics.collect_all(organization_id=organization_id, workspace_id=workspace_id)
                lines = []
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, (int, float)):
                            lines.append(f"sandbox_v2_{k} {v}")
                return "\n".join(lines) + "\n"
            except Exception as e:
                return f"# Error: {e}\n"

    # ── Grafana ──

    def generate_grafana_dashboard(self, dashboard_type: str = "overview") -> dict[str, Any]:
        builder = SandboxV2GrafanaDashboardBuilder()
        if dashboard_type == "security":
            return builder.build_security_dashboard().to_dict()
        elif dashboard_type == "runtime":
            return builder.build_runtime_dashboard().to_dict()
        elif dashboard_type == "performance":
            return builder.build_performance_dashboard().to_dict()
        return builder.build_overview_dashboard().to_dict()

    def get_latest_grafana_dashboard(self) -> dict[str, Any] | None:
        if not self._store:
            return None
        try:
            spec = self._store.get_latest_grafana_dashboard_spec()
            return spec.to_dict() if spec else None
        except Exception:
            return None

    def save_grafana_dashboard_spec(self, spec: SandboxV2GrafanaDashboardSpec) -> SandboxV2GrafanaDashboardSpec:
        if self._store:
            try:
                self._store.create_grafana_dashboard_spec(spec)
            except Exception as e:
                logger.warning(f"Failed to persist dashboard spec: {e}")
        return spec

    # ── OpenTelemetry ──

    def get_otel_adapter_readiness(self) -> dict[str, Any]:
        exporter_name = self._cfg.otel_exporter if self._cfg.otel_enabled else "disabled"
        try:
            exporter = get_otel_exporter(exporter_name)
            readiness = exporter.get_readiness()
        except Exception:
            readiness = {"available": False, "error": "Failed to initialize OTel exporter"}
        return {
            "otel_enabled": self._cfg.otel_enabled,
            "otel_exporter": exporter_name,
            "traces_enabled": self._cfg.otel_traces_enabled,
            "metrics_enabled": self._cfg.otel_metrics_enabled,
            "logs_enabled": self._cfg.otel_logs_enabled,
            "sensitive_attributes_allowed": self._cfg.include_sensitive_attributes,
            **readiness,
        }

    def simulate_otel_export(self, signal_type: str = "metric",
                             items: list[dict[str, Any]] | None = None,
                             organization_id: str = "", workspace_id: str = "") -> dict[str, Any]:
        """模拟 OTel export — 不发送外部请求，只创建 internal export record。"""
        cfg = self._cfg
        exporter = get_otel_exporter(cfg.otel_exporter if cfg.otel_enabled else "disabled")
        items = items or []

        if signal_type == "metric":
            result = exporter.export_metrics(items, cfg)
        elif signal_type == "trace":
            result = exporter.export_trace_spans(items, cfg)
        elif signal_type == "log":
            result = exporter.export_logs(items, cfg)
        else:
            result = {"status": SandboxV2TelemetryExportStatus.REJECTED, "reason": f"Unknown signal type: {signal_type}", "exported_count": 0}

        # Create export record
        record = SandboxV2TelemetryExportRecord(
            provider=exporter.get_name(),
            signal_type=signal_type,
            status=result.get("status", "skipped"),
            organization_id=organization_id,
            workspace_id=workspace_id,
            exported_count=result.get("exported_count", 0),
            rejected_count=result.get("rejected_count", 0),
            reason=result.get("reason", ""),
        )
        if self._store:
            try:
                self._store.create_telemetry_export_record(record)
            except Exception as e:
                logger.warning(f"Failed to persist export record: {e}")

        return {**result, "export_record": record.to_dict()}

    # ── Trace Spans ──

    def create_trace_span(self, *, span_name: str = "", trace_id: str = "",
                          parent_span_id: str = "", organization_id: str = "",
                          workspace_id: str = "", resource_type: str = "",
                          resource_id: str = "",
                          attributes: dict[str, Any] | None = None,
                          ) -> SandboxV2TraceSpan:
        cfg = self._cfg
        attrs = _sanitize(attributes or {}, allow_sensitive=cfg.include_sensitive_attributes)

        span = SandboxV2TraceSpan(
            trace_id=trace_id or f"trace_{uuid4().hex[:24]}",
            parent_span_id=parent_span_id,
            span_name=span_name,
            status=SandboxV2TraceSpanStatus.OK,
            organization_id=organization_id,
            workspace_id=workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
            started_at=datetime.now(timezone.utc),
            attributes_redacted=attrs,
            metadata={"created_by": "step18_observability"},
        )

        if self._store:
            try:
                self._store.create_trace_span(span)
            except Exception as e:
                logger.warning(f"Failed to persist trace span: {e}")

        return span

    def finish_trace_span(self, span_id: str, status: str = SandboxV2TraceSpanStatus.OK,
                          attributes: dict[str, Any] | None = None) -> SandboxV2TraceSpan | None:
        if not self._store:
            return None
        finished_at = datetime.now(timezone.utc)
        duration_ms = 0
        # Get existing span to calculate duration
        existing = None
        try:
            spans = self._store.list_trace_spans(limit=100)
            for s in spans:
                if getattr(s, 'span_id', '') == span_id:
                    existing = s
                    break
        except Exception:
            pass

        if existing and hasattr(existing, 'started_at'):
            delta = finished_at - existing.started_at
            duration_ms = int(delta.total_seconds() * 1000)

        cfg = self._cfg
        attrs = _sanitize(attributes or {}, allow_sensitive=cfg.include_sensitive_attributes)
        try:
            return self._store.update_trace_span(span_id, status, finished_at=finished_at,
                                                 duration_ms=duration_ms, metadata=attrs)
        except Exception as e:
            logger.warning(f"Failed to update trace span: {e}")
            return None

    def list_trace_spans(self, organization_id: str = "", workspace_id: str = "",
                         trace_id: str = "", limit: int = 100) -> list[SandboxV2TraceSpan]:
        if not self._store:
            return []
        try:
            return self._store.list_trace_spans(
                organization_id=organization_id or None,
                workspace_id=workspace_id or None,
                trace_id=trace_id or None,
                limit=min(max(int(limit or 100), 1), 200),
            )
        except Exception:
            return []

    # ── Export Records ──

    def create_telemetry_export_record(self, **kwargs) -> SandboxV2TelemetryExportRecord | None:
        record = SandboxV2TelemetryExportRecord(**kwargs)
        if self._store:
            try:
                self._store.create_telemetry_export_record(record)
            except Exception as e:
                logger.warning(f"Failed to create export record: {e}")
                return None
        return record

    def list_telemetry_export_records(self, provider: str = "", signal_type: str = "",
                                      status: str = "", limit: int = 100) -> list[SandboxV2TelemetryExportRecord]:
        if not self._store:
            return []
        try:
            return self._store.list_telemetry_export_records(
                provider=provider or None, signal_type=signal_type or None,
                status=status or None, limit=min(max(int(limit or 100), 1), 200),
            )
        except Exception:
            return []
