"""Step 23 — OpenTelemetry Configuration.

OTel config model and exporter dispatch.
Default: disabled (OTEL_ENABLED=false).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

VALID_EXPORTERS = frozenset({"disabled", "mock", "otlp_http"})


class OTelConfig:
    """OTel configuration holder. All fields default safe."""

    def __init__(self, settings: Any = None):
        self.enabled: bool = bool(getattr(settings, 'otel_enabled', False)) if settings else False
        self.exporter: str = str(getattr(settings, 'otel_exporter', 'disabled') if settings else 'disabled')
        self.endpoint: str = str(getattr(settings, 'otel_endpoint', '') if settings else '')
        self.service_name: str = str(getattr(settings, 'otel_service_name', 'sandbox-v2') if settings else 'sandbox-v2')
        self.traces_enabled: bool = bool(getattr(settings, 'otel_traces_enabled', False)) if settings else False
        self.metrics_enabled: bool = bool(getattr(settings, 'otel_metrics_enabled', False)) if settings else False
        self.logs_enabled: bool = bool(getattr(settings, 'otel_logs_enabled', False)) if settings else False
        self.sensitive_attrs: bool = bool(getattr(settings, 'otel_include_sensitive_attributes', False)) if settings else False
        self.safe_mode: bool = True

        if self.exporter not in VALID_EXPORTERS:
            logger.warning(f"Invalid OTEL exporter '{self.exporter}', falling back to disabled")
            self.exporter = "disabled"

    def validate(self) -> dict[str, Any]:
        issues: list[str] = []
        if self.enabled and self.exporter == "otlp_http" and not self.endpoint:
            issues.append("OTLP HTTP exporter requires an endpoint (OTEL_ENDPOINT)")
        if self.enabled and self.sensitive_attrs:
            issues.append("include_sensitive_attributes=true must be false for production")
        if self.enabled and self.exporter not in VALID_EXPORTERS:
            issues.append(f"Invalid exporter '{self.exporter}'")
        return {"valid": len(issues) == 0, "issues": issues, "reason": "; ".join(issues) if issues else "Config valid"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "exporter": self.exporter,
            "endpoint": self.endpoint[:20] + "..." if len(self.endpoint) > 20 else self.endpoint,
            "service_name": self.service_name,
            "traces_enabled": self.traces_enabled,
            "metrics_enabled": self.metrics_enabled,
            "logs_enabled": self.logs_enabled,
            "safe_mode": self.safe_mode,
        }
