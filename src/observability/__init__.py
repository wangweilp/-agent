"""Production Observability Foundation — Step 23.

Prometheus Metrics + OpenTelemetry Tracing + Grafana Dashboards.

All observability capabilities default to disabled.
PROMETHEUS_ENABLED=false, OTEL_ENABLED=false, GRAFANA_DASHBOARD_ENABLED=false.

Exports:
    MetricsRegistry    — global metrics registry (Counter, Gauge, Histogram)
    PrometheusExporter — /metrics endpoint exporter
    OIDCMetrics        — OIDC auth metrics
    SAMLMetrics        — SAML auth metrics
    GovernanceMetrics  — runtime governance + sandbox execution metrics
    AuditMetrics       — audit + security event metrics
    Tracer             — OTel-compatible tracer with span context
    OTelConfig         — OTel configuration validator
    ObservabilityService — unified orchestrator + readiness
"""
from src.observability.metrics_registry import (
    get_metrics_registry, reset_metrics_registry,
    MetricsRegistry, Counter, Gauge, Histogram,
)
from src.observability.prometheus_exporter import PrometheusExporter
from src.observability.oidc_metrics import get_oidc_metrics, OIDCMetrics
from src.observability.saml_metrics import get_saml_metrics, SAMLMetrics
from src.observability.governance_metrics import get_governance_metrics, GovernanceMetrics
from src.observability.audit_metrics import get_audit_metrics, AuditMetrics
from src.observability.tracing import get_tracer, reset_tracer, Tracer, TraceSpan
from src.observability.otel_config import OTelConfig

__all__ = [
    "get_metrics_registry", "reset_metrics_registry",
    "MetricsRegistry", "Counter", "Gauge", "Histogram",
    "PrometheusExporter",
    "get_oidc_metrics", "OIDCMetrics",
    "get_saml_metrics", "SAMLMetrics",
    "get_governance_metrics", "GovernanceMetrics",
    "get_audit_metrics", "AuditMetrics",
    "get_tracer", "reset_tracer", "Tracer", "TraceSpan",
    "OTelConfig",
]
