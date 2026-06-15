"""Step 23 — Observability Service (Unified Orchestrator).

Aggregates Prometheus exporter, OTel config, tracer, and all domain metrics.
Provides get_readiness() for Runtime Admin consumption.
"""
from __future__ import annotations

import logging
from typing import Any

from src.observability.prometheus_exporter import PrometheusExporter
from src.observability.otel_config import OTelConfig
from src.observability.tracing import get_tracer
from src.observability.metrics_registry import get_metrics_registry
from src.observability.oidc_metrics import get_oidc_metrics
from src.observability.saml_metrics import get_saml_metrics
from src.observability.governance_metrics import get_governance_metrics
from src.observability.audit_metrics import get_audit_metrics

logger = logging.getLogger(__name__)


def _status_of(*, enabled: bool, ready: bool) -> str:
    if enabled and ready: return "ready"
    if enabled and not ready: return "not_ready"
    return "disabled"


class ObservabilityService:
    """Central observability service for Step 23."""

    def __init__(self, settings: Any = None):
        self._settings = settings
        self.prometheus = PrometheusExporter(settings=settings)
        self.otel_config = OTelConfig(settings=settings)
        self.tracer = get_tracer(settings=settings)
        self.oidc = get_oidc_metrics()
        self.saml = get_saml_metrics()
        self.governance = get_governance_metrics()
        self.audit = get_audit_metrics()
        self.registry = get_metrics_registry()

    def _cfg(self, key: str, default: Any = None) -> Any:
        return getattr(self._settings, key, default) if self._settings else default

    # ── Metrics export ──

    def get_metrics_text(self) -> str:
        return self.prometheus.export_prometheus_text()

    def get_metrics_json(self) -> dict[str, Any]:
        return self.prometheus.export_json()

    # ── Dashboard access ──

    @property
    def dashboard_enabled(self) -> bool:
        return bool(self._cfg("grafana_dashboard_enabled", False))

    def list_dashboards(self) -> list[str]:
        return ["oidc", "saml", "runtime", "security"]

    # ── Readiness ──

    def get_readiness(self) -> dict[str, Any]:
        prom_r = self.prometheus.get_readiness()
        tracer_r = self.tracer.get_readiness()
        otel_valid = self.otel_config.validate()

        return {
            "step": "step23_observability_foundation",
            "available": True,
            "fail_closed": True,
            "prometheus": {
                "enabled": prom_r["enabled"],
                "ready": prom_r["ready"],
                "status": prom_r["status"],
                "reason": prom_r["reason"],
                "metrics_registered": prom_r["metrics_registered"],
            },
            "otel": {
                "enabled": self.otel_config.enabled,
                "ready": self.otel_config.enabled and otel_valid["valid"],
                "status": _status_of(enabled=self.otel_config.enabled, ready=otel_valid["valid"]),
                "reason": "" if self.otel_config.enabled else "OTEL_ENABLED=false",
                "exporter": self.otel_config.exporter,
                "config_valid": otel_valid["valid"],
                "config_issues": otel_valid.get("issues", []),
            },
            "tracing": {
                "enabled": tracer_r["enabled"],
                "ready": tracer_r["ready"],
                "status": tracer_r["status"],
                "reason": tracer_r["reason"],
                "spans_recorded": tracer_r["spans_recorded"],
                "active_spans": tracer_r["active_spans"],
            },
            "dashboards": {
                "enabled": self.dashboard_enabled,
                "ready": self.dashboard_enabled,
                "status": "ready" if self.dashboard_enabled else "disabled",
                "reason": "" if self.dashboard_enabled else "GRAFANA_DASHBOARD_ENABLED=false",
                "available_dashboards": self.list_dashboards(),
            },
            "metrics_domains": {
                "oidc_metrics_available": self.oidc is not None,
                "saml_metrics_available": self.saml is not None,
                "governance_metrics_available": self.governance is not None,
                "audit_metrics_available": self.audit is not None,
                "total_registered": len(self.registry.list_all()),
            },
        }

    # ── Record convenience methods ──

    def record_oidc_login_success(self) -> None: self.oidc.record_login_success()
    def record_oidc_login_failure(self, reason: str = "") -> None: self.oidc.record_login_failure(reason)
    def record_oidc_token_validation(self, success: bool) -> None: self.oidc.record_token_validation(success)
    def record_oidc_nonce_replay(self) -> None: self.oidc.record_nonce_replay()
    def record_oidc_jwks_refresh(self, success: bool) -> None: self.oidc.record_jwks_refresh(success)

    def record_saml_assertion_success(self) -> None: self.saml.record_assertion_success()
    def record_saml_assertion_failure(self) -> None: self.saml.record_assertion_failure()
    def record_saml_replay_attack(self) -> None: self.saml.record_replay_attack()
    def record_saml_signature_validation(self, ok: bool) -> None: self.saml.record_signature_validation(ok)

    def record_policy_allow(self) -> None: self.governance.record_policy_allow()
    def record_policy_deny(self) -> None: self.governance.record_policy_deny()
    def record_sandbox_execution_success(self) -> None: self.governance.record_execution_success()
    def record_sandbox_execution_failure(self) -> None: self.governance.record_execution_failure()

    def record_audit_event(self, decision: str = "allow") -> None: self.audit.record_audit_event(decision)
    def record_security_event(self) -> None: self.audit.record_security_event()
    def record_red_team_detection(self) -> None: self.audit.record_red_team_detection()

    # ── Tracing convenience ──

    def start_trace_span(self, name: str, attrs: dict[str, Any] | None = None, parent: str = ""):
        return self.tracer.start_span(name, attrs, parent_id=parent)

    def end_trace_span(self, span, status: str = "ok") -> None:
        self.tracer.end_span(span, status)
