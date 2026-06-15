"""Step 23 — Observability Tests (20+).

Covers: metrics registration, counter, gauge, histogram,
Prometheus export, readiness states, disabled mode,
domain metrics (OIDC/SAML/Governance/Audit), tracing.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from src.observability.metrics_registry import (
    MetricsRegistry, Counter, Gauge, Histogram,
    get_metrics_registry, reset_metrics_registry,
)
from src.observability.prometheus_exporter import PrometheusExporter
from src.observability.tracing import Tracer, TraceSpan, get_tracer, reset_tracer
from src.observability.otel_config import OTelConfig
from src.observability.oidc_metrics import get_oidc_metrics, reset_oidc_metrics, OIDCMetrics
from src.observability.saml_metrics import get_saml_metrics, reset_saml_metrics, SAMLMetrics
from src.observability.governance_metrics import get_governance_metrics, reset_governance_metrics, GovernanceMetrics
from src.observability.audit_metrics import get_audit_metrics, AuditMetrics
from src.observability.service import ObservabilityService


class DisabledSettings:
    prometheus_enabled = False
    otel_enabled = False
    grafana_dashboard_enabled = False


class EnabledSettings:
    prometheus_enabled = True
    otel_enabled = True
    grafana_dashboard_enabled = True
    otel_exporter = "mock"
    otel_endpoint = ""
    otel_service_name = "sandbox-v2"
    otel_traces_enabled = True
    otel_include_sensitive_attributes = False


@pytest.fixture(autouse=True)
def reset_registry():
    reset_metrics_registry()
    reset_tracer()
    reset_oidc_metrics()
    reset_saml_metrics()
    reset_governance_metrics()
    yield
    reset_metrics_registry()
    reset_tracer()
    reset_oidc_metrics()
    reset_saml_metrics()
    reset_governance_metrics()


# ═══════════════════════════════════════════
# 1. Metrics Registry
# ═══════════════════════════════════════════

class TestMetricsRegistry:
    def test_counter_inc(self):
        c = Counter("test_counter", "A test counter")
        c.inc()
        assert c.value() == 1.0
        c.inc(2.5)
        assert c.value() == 3.5

    def test_gauge_set_inc_dec(self):
        g = Gauge("test_gauge", "A test gauge")
        g.set(10)
        assert g.value() == 10
        g.inc(3)
        assert g.value() == 13
        g.dec(5)
        assert g.value() == 8

    def test_histogram_observe(self):
        h = Histogram("test_histogram", "Test histogram", buckets=(1.0, 5.0, 10.0))
        h.observe(3.0)
        h.observe(7.0)
        h.observe(0.5)
        assert h.count() == 3
        assert h.sum() == 10.5

    def test_registry_register_and_get(self):
        reg = MetricsRegistry()
        c = reg.counter("reg_counter", "desc")
        assert reg.get("reg_counter") is c
        assert reg.get("nonexistent") is None

    def test_registry_list_all(self):
        reg = MetricsRegistry()
        reg.counter("c1")
        reg.gauge("g1")
        assert len(reg.list_all()) == 2

    def test_registry_export_prometheus_text(self):
        reg = MetricsRegistry()
        reg.counter("my_counter", "counter desc")
        reg.gauge("my_gauge", "gauge desc")
        text = reg.export_prometheus_text()
        assert "my_counter" in text
        assert "my_gauge" in text

    def test_registry_export_json(self):
        reg = MetricsRegistry()
        reg.counter("c1")
        reg.gauge("g1")
        data = reg.export_json()
        assert "c1" in data
        assert "g1" in data
        assert data["c1"]["type"] == "counter"

    def test_reset_all(self):
        reg = MetricsRegistry()
        c = reg.counter("c")
        c.inc(5)
        reg.reset_all()
        assert c.value() == 0

    def test_global_registry_singleton(self):
        r1 = get_metrics_registry()
        r2 = get_metrics_registry()
        assert r1 is r2

    def test_thread_safe_counter(self):
        import threading
        c = Counter("thread_counter")
        threads = []
        for _ in range(10):
            t = threading.Thread(target=lambda: [c.inc() for _ in range(100)])
            threads.append(t)
        for t in threads: t.start()
        for t in threads: t.join()
        assert c.value() == 1000


# ═══════════════════════════════════════════
# 2. Prometheus Exporter
# ═══════════════════════════════════════════

class TestPrometheusExporter:
    def test_disabled_mode(self):
        exporter = PrometheusExporter(settings=DisabledSettings())
        assert not exporter.enabled
        text = exporter.export_prometheus_text()
        assert "disabled" in text.lower()

    def test_enabled_mode(self):
        exporter = PrometheusExporter(settings=EnabledSettings())
        assert exporter.enabled
        text = exporter.export_prometheus_text()
        # Even with no metrics, should not include "disabled"
        assert "disabled" not in text.lower()

    def test_readiness_disabled(self):
        exporter = PrometheusExporter(settings=DisabledSettings())
        r = exporter.get_readiness()
        assert r["enabled"] is False
        assert r["status"] == "disabled"

    def test_readiness_enabled(self):
        exporter = PrometheusExporter(settings=EnabledSettings())
        r = exporter.get_readiness()
        assert r["enabled"] is True
        assert r["status"] == "ready"


# ═══════════════════════════════════════════
# 3. Domain Metrics
# ═══════════════════════════════════════════

class TestOIDCMetrics:
    def test_oidc_metrics_registered(self):
        oidc = get_oidc_metrics()
        reg = get_metrics_registry()
        assert "oidc_login_total" in reg.list_all()
        assert "oidc_token_validation_total" in reg.list_all()

    def test_oidc_counter_increments(self):
        oidc = get_oidc_metrics()
        oidc.record_login_success()
        assert oidc.login_total.value() == 1
        assert oidc.login_success_total.value() == 1

    def test_oidc_token_validation(self):
        oidc = get_oidc_metrics()
        oidc.record_token_validation(True)
        oidc.record_token_validation(False)
        assert oidc.token_validation_total.value() == 2
        assert oidc.token_validation_failure_total.value() == 1

    def test_oidc_nonce_replay_recording(self):
        oidc = get_oidc_metrics()
        assert oidc.nonce_replay_total.value() == 0
        oidc.record_nonce_replay()
        assert oidc.nonce_replay_total.value() == 1


class TestSAMLMetrics:
    def test_saml_metrics_registered(self):
        saml = get_saml_metrics()
        reg = get_metrics_registry()
        assert "saml_assertion_total" in reg.list_all()
        assert "saml_replay_attack_total" in reg.list_all()

    def test_saml_assertion_success(self):
        saml = get_saml_metrics()
        saml.record_assertion_success()
        assert saml.assertion_success_total.value() == 1

    def test_saml_replay_attack(self):
        saml = get_saml_metrics()
        saml.record_replay_attack()
        assert saml.replay_attack_total.value() == 1


class TestGovernanceMetrics:
    def test_policy_metrics(self):
        gov = get_governance_metrics()
        gov.record_policy_allow()
        gov.record_policy_deny()
        assert gov.policy_allow_total.value() == 1
        assert gov.policy_deny_total.value() == 1

    def test_execution_metrics(self):
        gov = get_governance_metrics()
        gov.record_execution_start()
        gov.record_execution_success()
        assert gov.sandbox_execution_success_total.value() == 1


class TestAuditMetrics:
    def test_audit_metrics(self):
        audit = get_audit_metrics()
        audit.record_audit_event("allow")
        audit.record_audit_event("deny")
        assert audit.audit_event_total.value() == 2

    def test_security_event(self):
        audit = get_audit_metrics()
        audit.record_security_event()
        assert audit.security_event_total.value() == 1


# ═══════════════════════════════════════════
# 4. Tracing
# ═══════════════════════════════════════════

class TestTracing:
    def test_tracer_disabled(self):
        t = Tracer(enabled=False)
        span = t.start_span("test")
        assert span.name == "test"
        t.end_span(span, "ok")
        assert t.span_count() == 0

    def test_tracer_enabled(self):
        t = Tracer(enabled=True)
        span = t.start_span("test_span", {"key": "val"})
        t.end_span(span, "ok")
        assert t.span_count() == 1
        spans = t.list_spans()
        assert len(spans) == 1
        assert spans[0]["name"] == "test_span"

    def test_span_context_manager(self):
        t = Tracer(enabled=True)
        with t.span_context("ctx_span") as span:
            span.set_attribute("step", "1")
        assert t.span_count() == 1

    def test_span_duration(self):
        import time
        t = Tracer(enabled=True)
        span = t.start_span("timed")
        time.sleep(0.01)
        t.end_span(span)
        assert span.duration_seconds > 0

    def test_span_parent_child(self):
        t = Tracer(enabled=True)
        parent = t.start_span("parent")
        child = t.start_span("child")
        t.end_span(child)
        t.end_span(parent)
        assert t.span_count() == 2

    def test_tracer_readiness_disabled(self):
        t = Tracer(enabled=False)
        r = t.get_readiness()
        assert r["enabled"] is False
        assert r["status"] == "disabled"


# ═══════════════════════════════════════════
# 5. Observability Service
# ═══════════════════════════════════════════

class TestObservabilityService:
    def test_disabled_readiness(self):
        svc = ObservabilityService(settings=DisabledSettings())
        r = svc.get_readiness()
        assert r["fail_closed"] is True
        assert r["prometheus"]["enabled"] is False
        assert r["otel"]["enabled"] is False
        assert r["dashboards"]["enabled"] is False

    def test_enabled_readiness(self):
        svc = ObservabilityService(settings=EnabledSettings())
        r = svc.get_readiness()
        assert r["prometheus"]["enabled"] is True
        assert r["otel"]["enabled"] is True
        assert r["dashboards"]["enabled"] is True

    def test_metrics_text_export(self):
        svc = ObservabilityService(settings=EnabledSettings())
        svc.record_oidc_login_success()
        svc.record_saml_assertion_success()
        text = svc.get_metrics_text()
        assert "oidc_login_total" in text
        assert "saml_assertion_total" in text

    def test_dashboard_list(self):
        svc = ObservabilityService(settings=EnabledSettings())
        dashboards = svc.list_dashboards()
        assert "oidc" in dashboards
        assert "saml" in dashboards
        assert "runtime" in dashboards
        assert "security" in dashboards
