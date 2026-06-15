"""Step 23 — Runtime Governance & Sandbox Execution Metrics."""
from __future__ import annotations

from src.observability.metrics_registry import get_metrics_registry, Counter, Histogram, Gauge


class GovernanceMetrics:
    def __init__(self):
        reg = get_metrics_registry()
        self.policy_evaluation_total: Counter = reg.counter("policy_evaluation_total", "Total policy evaluations")
        self.policy_allow_total: Counter = reg.counter("policy_allow_total", "Policy allow decisions")
        self.policy_deny_total: Counter = reg.counter("policy_deny_total", "Policy deny decisions")
        self.policy_error_total: Counter = reg.counter("policy_error_total", "Policy evaluation errors")
        self.sandbox_execution_total: Counter = reg.counter("sandbox_execution_total", "Total sandbox executions")
        self.sandbox_execution_success_total: Counter = reg.counter("sandbox_execution_success_total", "Successful sandbox executions")
        self.sandbox_execution_failure_total: Counter = reg.counter("sandbox_execution_failure_total", "Failed sandbox executions")
        self.execution_latency: Histogram = reg.histogram("sandbox_execution_latency_seconds", "Sandbox execution latency", buckets=(0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0))
        self.active_executions: Gauge = reg.gauge("sandbox_active_executions", "Currently active sandbox executions")
        self.policy_evaluation_latency: Histogram = reg.histogram("policy_evaluation_latency_seconds", "Policy evaluation latency", buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5))
        self.governance_blockers: Gauge = reg.gauge("governance_production_blockers", "Number of production blockers from governance")

    def record_policy_allow(self) -> None: self.policy_evaluation_total.inc(); self.policy_allow_total.inc()
    def record_policy_deny(self) -> None: self.policy_evaluation_total.inc(); self.policy_deny_total.inc()
    def record_policy_error(self) -> None: self.policy_evaluation_total.inc(); self.policy_error_total.inc()
    def record_execution_success(self) -> None: self.sandbox_execution_total.inc(); self.sandbox_execution_success_total.inc(); self.active_executions.dec()
    def record_execution_failure(self) -> None: self.sandbox_execution_total.inc(); self.sandbox_execution_failure_total.inc(); self.active_executions.dec()
    def record_execution_start(self) -> None: self.active_executions.inc()


_gov_metrics: GovernanceMetrics | None = None


def get_governance_metrics() -> GovernanceMetrics:
    global _gov_metrics
    if _gov_metrics is None:
        _gov_metrics = GovernanceMetrics()
    return _gov_metrics


def reset_governance_metrics() -> None:
    global _gov_metrics
    _gov_metrics = None
