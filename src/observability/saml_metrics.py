"""Step 23 — SAML Metrics."""
from __future__ import annotations

from src.observability.metrics_registry import get_metrics_registry, Counter, Histogram, Gauge


class SAMLMetrics:
    def __init__(self):
        reg = get_metrics_registry()
        self.assertion_total: Counter = reg.counter("saml_assertion_total", "Total SAML assertions processed")
        self.assertion_success_total: Counter = reg.counter("saml_assertion_success_total", "Successful SAML assertions")
        self.assertion_failure_total: Counter = reg.counter("saml_assertion_failure_total", "Failed SAML assertions")
        self.replay_attack_total: Counter = reg.counter("saml_replay_attack_total", "SAML replay attack detections")
        self.metadata_refresh_total: Counter = reg.counter("saml_metadata_refresh_total", "Total SAML metadata refreshes")
        self.metadata_refresh_failure_total: Counter = reg.counter("saml_metadata_refresh_failure_total", "Failed SAML metadata refreshes")
        self.cert_validation_failure_total: Counter = reg.counter("saml_certificate_validation_failure_total", "Failed SAML certificate validations")
        self.signature_validation_total: Counter = reg.counter("saml_signature_validation_total", "Total SAML signature validations")
        self.signature_validation_failure_total: Counter = reg.counter("saml_signature_validation_failure_total", "Failed SAML signature validations")
        self.identity_mapping_total: Counter = reg.counter("saml_identity_mapping_total", "Total SAML identity mappings")
        self.assertion_latency: Histogram = reg.histogram("saml_assertion_validation_latency_seconds", "SAML assertion validation latency", buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0))
        self.active_sessions: Gauge = reg.gauge("saml_active_sessions", "Active SAML SSO sessions")

    def record_assertion_success(self) -> None: self.assertion_total.inc(); self.assertion_success_total.inc(); self.active_sessions.inc()
    def record_assertion_failure(self) -> None: self.assertion_total.inc(); self.assertion_failure_total.inc()
    def record_replay_attack(self) -> None: self.replay_attack_total.inc()
    def record_metadata_refresh(self, ok: bool) -> None: self.metadata_refresh_total.inc(); (not ok and self.metadata_refresh_failure_total.inc())
    def record_cert_validation_failure(self) -> None: self.cert_validation_failure_total.inc()
    def record_signature_validation(self, ok: bool) -> None: self.signature_validation_total.inc(); (not ok and self.signature_validation_failure_total.inc())
    def record_identity_mapping(self) -> None: self.identity_mapping_total.inc()
    def record_session_end(self) -> None: (self.active_sessions.value() > 0 and self.active_sessions.dec())


_saml_metrics: SAMLMetrics | None = None


def get_saml_metrics() -> SAMLMetrics:
    global _saml_metrics
    if _saml_metrics is None:
        _saml_metrics = SAMLMetrics()
    return _saml_metrics


def reset_saml_metrics() -> None:
    global _saml_metrics
    _saml_metrics = None
