"""Step 23 — Audit & Security Event Metrics."""
from __future__ import annotations

from src.observability.metrics_registry import get_metrics_registry, Counter, Gauge


class AuditMetrics:
    def __init__(self):
        reg = get_metrics_registry()
        self.audit_event_total: Counter = reg.counter("audit_event_total", "Total audit events written")
        self.audit_write_failure_total: Counter = reg.counter("audit_write_failure_total", "Failed audit event writes")
        self.security_event_total: Counter = reg.counter("security_event_total", "Total security events")
        self.red_team_detection_total: Counter = reg.counter("red_team_detection_total", "Red-team attack detection count")
        self.audit_event_allow_total: Counter = reg.counter("audit_event_allow_total", "Allow-decision audit events")
        self.audit_event_deny_total: Counter = reg.counter("audit_event_deny_total", "Deny-decision audit events")
        self.audit_chain_verify_total: Counter = reg.counter("audit_chain_verify_total", "Audit hash chain verifications")
        self.audit_chain_verify_failure_total: Counter = reg.counter("audit_chain_verify_failure_total", "Audit hash chain verification failures")
        self.audit_event_rate: Gauge = reg.gauge("audit_event_rate", "Audit events per second (recent)")

    def record_audit_event(self, decision: str = "allow") -> None:
        self.audit_event_total.inc()
        if decision == "allow":
            self.audit_event_allow_total.inc()
        else:
            self.audit_event_deny_total.inc()

    def record_audit_write_failure(self) -> None: self.audit_write_failure_total.inc()
    def record_security_event(self) -> None: self.security_event_total.inc()
    def record_red_team_detection(self) -> None: self.red_team_detection_total.inc()
    def record_chain_verify(self, ok: bool) -> None: self.audit_chain_verify_total.inc(); (not ok and self.audit_chain_verify_failure_total.inc())


_audit_metrics: AuditMetrics | None = None


def get_audit_metrics() -> AuditMetrics:
    global _audit_metrics
    if _audit_metrics is None:
        _audit_metrics = AuditMetrics()
    return _audit_metrics
