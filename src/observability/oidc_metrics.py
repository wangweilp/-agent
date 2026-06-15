"""Step 23 — OIDC Metrics.

OIDC-specific counters and histograms registered on the global registry.
All metrics default to zero; only incremented when explicitly invoked.
"""
from __future__ import annotations

from src.observability.metrics_registry import get_metrics_registry, Counter, Histogram, Gauge


class OIDCMetrics:
    """OIDC authentication metrics collector."""

    def __init__(self):
        self._reg = get_metrics_registry()

        # Counters
        self.login_total: Counter = self._reg.counter(
            "oidc_login_total", "Total OIDC login attempts",
        )
        self.login_success_total: Counter = self._reg.counter(
            "oidc_login_success_total", "Successful OIDC logins",
        )
        self.login_failure_total: Counter = self._reg.counter(
            "oidc_login_failure_total", "Failed OIDC logins",
        )
        self.token_validation_total: Counter = self._reg.counter(
            "oidc_token_validation_total", "Total OIDC token validations",
        )
        self.token_validation_failure_total: Counter = self._reg.counter(
            "oidc_token_validation_failure_total", "Failed OIDC token validations",
        )
        self.nonce_replay_total: Counter = self._reg.counter(
            "oidc_nonce_replay_total", "OIDC nonce replay detections",
        )
        self.jwks_refresh_total: Counter = self._reg.counter(
            "oidc_jwks_refresh_total", "Total JWKS refreshes",
        )
        self.jwks_refresh_failure_total: Counter = self._reg.counter(
            "oidc_jwks_refresh_failure_total", "Failed JWKS refreshes",
        )
        self.discovery_fetch_total: Counter = self._reg.counter(
            "oidc_discovery_fetch_total", "Total OIDC discovery fetches",
        )
        self.discovery_fetch_failure_total: Counter = self._reg.counter(
            "oidc_discovery_fetch_failure_total", "Failed OIDC discovery fetches",
        )
        self.claim_validation_total: Counter = self._reg.counter(
            "oidc_claim_validation_total", "Total OIDC claim validations",
        )
        self.claim_validation_failure_total: Counter = self._reg.counter(
            "oidc_claim_validation_failure_total", "Failed OIDC claim validations",
        )
        self.identity_mapping_total: Counter = self._reg.counter(
            "oidc_identity_mapping_total", "Total OIDC identity mappings",
        )

        # Histograms
        self.token_validation_latency: Histogram = self._reg.histogram(
            "oidc_token_validation_latency_seconds",
            "OIDC token validation latency (seconds)",
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
        )
        self.login_latency: Histogram = self._reg.histogram(
            "oidc_login_latency_seconds",
            "OIDC login flow latency (seconds)",
            buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
        )

        # Gauge
        self.active_sessions: Gauge = self._reg.gauge(
            "oidc_active_sessions", "Currently active OIDC SSO sessions",
        )

    def record_login_success(self) -> None:
        self.login_total.inc()
        self.login_success_total.inc()
        self.active_sessions.inc()

    def record_login_failure(self, reason: str = "") -> None:
        self.login_total.inc()
        self.login_failure_total.inc()

    def record_token_validation(self, success: bool) -> None:
        self.token_validation_total.inc()
        if not success:
            self.token_validation_failure_total.inc()

    def record_nonce_replay(self) -> None:
        self.nonce_replay_total.inc()

    def record_jwks_refresh(self, success: bool) -> None:
        self.jwks_refresh_total.inc()
        if not success:
            self.jwks_refresh_failure_total.inc()

    def record_discovery_fetch(self, success: bool) -> None:
        self.discovery_fetch_total.inc()
        if not success:
            self.discovery_fetch_failure_total.inc()

    def record_claim_validation(self, success: bool) -> None:
        self.claim_validation_total.inc()
        if not success:
            self.claim_validation_failure_total.inc()

    def record_identity_mapping(self) -> None:
        self.identity_mapping_total.inc()

    def record_session_end(self) -> None:
        current = self.active_sessions.value()
        if current > 0:
            self.active_sessions.dec()


_oidc_metrics: OIDCMetrics | None = None


def get_oidc_metrics() -> OIDCMetrics:
    global _oidc_metrics
    if _oidc_metrics is None:
        _oidc_metrics = OIDCMetrics()
    return _oidc_metrics


def reset_oidc_metrics() -> None:
    global _oidc_metrics
    _oidc_metrics = None
