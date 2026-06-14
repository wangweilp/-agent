"""Sandbox v2 OpenTelemetry Adapter Skeleton — Step 18.

OTelExporter Protocol + Disabled/Mock/OTLP implementations.
不发送真实 telemetry，不访问外网，不连接 OTel Collector。
"""
from __future__ import annotations
import logging
from typing import Any, Protocol

from src.open_platform.sandbox_v2.models import (
    SandboxV2ObservabilityProvider,
    SandboxV2TelemetrySignalType,
    SandboxV2TelemetryExportStatus,
    SandboxV2TraceSpanStatus,
)

logger = logging.getLogger(__name__)

_SENSITIVE_ATTR_KEYS = frozenset({
    "secret", "token", "key", "password", "dsn", "credential",
    "access_key", "secret_key", "client_secret", "api_key",
    "token", "authorization", "cookie", "jwt",
})


def sanitize_attributes(attrs: dict[str, Any], allow_sensitive: bool = False) -> dict[str, Any]:
    """Redact sensitive attribute keys."""
    if not isinstance(attrs, dict):
        return {}
    if allow_sensitive:
        return dict(attrs)
    result: dict[str, Any] = {}
    for k, v in attrs.items():
        k_lower = k.lower()
        if any(sk in k_lower for sk in _SENSITIVE_ATTR_KEYS):
            result[k] = "[REDACTED]"
        elif isinstance(v, str) and len(v) > 500:
            result[k] = v[:500] + "..."
        else:
            result[k] = v
    return result


class OTelExporter(Protocol):
    def get_name(self) -> str: ...
    def get_readiness(self) -> dict[str, Any]: ...
    def export_metrics(self, metrics: list[dict[str, Any]], config: Any = None) -> dict[str, Any]: ...
    def export_trace_spans(self, spans: list[dict[str, Any]], config: Any = None) -> dict[str, Any]: ...
    def export_logs(self, logs: list[dict[str, Any]], config: Any = None) -> dict[str, Any]: ...


class DisabledOTelExporter:
    """默认 disabled — 所有 export 返回 disabled。"""

    def get_name(self) -> str:
        return SandboxV2ObservabilityProvider.DISABLED

    def get_readiness(self) -> dict[str, Any]:
        return {
            "name": "disabled",
            "available": True,
            "otel_real_export": False,
            "external_telemetry_export": False,
        }

    def export_metrics(self, metrics: list[dict[str, Any]], config: Any = None) -> dict[str, Any]:
        return {"status": SandboxV2TelemetryExportStatus.DISABLED, "reason": "OTel is disabled", "exported_count": 0}

    def export_trace_spans(self, spans: list[dict[str, Any]], config: Any = None) -> dict[str, Any]:
        return {"status": SandboxV2TelemetryExportStatus.DISABLED, "reason": "OTel is disabled", "exported_count": 0}

    def export_logs(self, logs: list[dict[str, Any]], config: Any = None) -> dict[str, Any]:
        return {"status": SandboxV2TelemetryExportStatus.DISABLED, "reason": "OTel is disabled", "exported_count": 0}


class MockOTelExporter:
    """只用于测试 — 不访问外网，记录 export count。"""

    def __init__(self):
        self._exported: list[dict[str, Any]] = []

    def get_name(self) -> str:
        return SandboxV2ObservabilityProvider.MOCK

    def get_readiness(self) -> dict[str, Any]:
        return {
            "name": "mock",
            "available": True,
            "otel_real_export": False,
            "external_telemetry_export": False,
        }

    def export_metrics(self, metrics: list[dict[str, Any]], config: Any = None) -> dict[str, Any]:
        allow = getattr(config, 'include_sensitive_attributes', False) if config else False
        safe = [sanitize_attributes(m, allow_sensitive=allow) for m in metrics]
        self._exported.append({"type": "metrics", "count": len(metrics), "items": safe})
        return {"status": SandboxV2TelemetryExportStatus.EXPORTED, "reason": "Mock export (no external request)",
                "exported_count": len(metrics), "rejected_count": 0}

    def export_trace_spans(self, spans: list[dict[str, Any]], config: Any = None) -> dict[str, Any]:
        allow = getattr(config, 'include_sensitive_attributes', False) if config else False
        safe = [sanitize_attributes(s, allow_sensitive=allow) for s in spans]
        self._exported.append({"type": "traces", "count": len(spans), "items": safe})
        return {"status": SandboxV2TelemetryExportStatus.EXPORTED, "reason": "Mock export (no external request)",
                "exported_count": len(spans), "rejected_count": 0}

    def export_logs(self, logs: list[dict[str, Any]], config: Any = None) -> dict[str, Any]:
        allow = getattr(config, 'include_sensitive_attributes', False) if config else False
        safe = [sanitize_attributes(l, allow_sensitive=allow) for l in logs]
        self._exported.append({"type": "logs", "count": len(logs), "items": safe})
        return {"status": SandboxV2TelemetryExportStatus.EXPORTED, "reason": "Mock export (no external request)",
                "exported_count": len(logs), "rejected_count": 0}

    @property
    def exported_records(self) -> list[dict[str, Any]]:
        return list(self._exported)


class OTLPHttpExporterSkeleton:
    """OTLP HTTP Exporter 骨架 — 只做配置校验，不发送 HTTP。

    不访问 endpoint URL，不发送 telemetry。
    本步骤不实现真实 HTTP export。
    """

    def get_name(self) -> str:
        return "otlp_http"

    def get_readiness(self) -> dict[str, Any]:
        return {
            "name": "otlp_http",
            "available": True,
            "otel_real_export": False,
            "external_telemetry_export": False,
            "preflight_only": True,
        }

    def validate_config(self, config: Any = None) -> dict[str, Any]:
        issues = []
        if not config:
            issues.append("No config provided")
            return {"valid": False, "issues": issues, "reason": "; ".join(issues)}
        endpoint = getattr(config, 'otel_endpoint', '') if not isinstance(config, dict) else config.get('otel_endpoint', '')
        if not endpoint:
            issues.append("OTLP endpoint is empty")
        if getattr(config, 'include_sensitive_attributes', False) if not isinstance(config, dict) else config.get('include_sensitive_attributes', False):
            issues.append("Sensitive attributes enabled — must be false")
        return {"valid": len(issues) == 0, "issues": issues, "reason": "; ".join(issues) if issues else "Config valid (skeleton mode)"}

    def export_metrics(self, metrics: list[dict[str, Any]], config: Any = None) -> dict[str, Any]:
        """Skeleton: 不发送 HTTP。返回 skipped。"""
        return {"status": SandboxV2TelemetryExportStatus.SKIPPED,
                "reason": "OTLP HTTP export not implemented in Step 18", "exported_count": 0}

    def export_trace_spans(self, spans: list[dict[str, Any]], config: Any = None) -> dict[str, Any]:
        return {"status": SandboxV2TelemetryExportStatus.SKIPPED,
                "reason": "OTLP HTTP traces not implemented in Step 18", "exported_count": 0}

    def export_logs(self, logs: list[dict[str, Any]], config: Any = None) -> dict[str, Any]:
        return {"status": SandboxV2TelemetryExportStatus.SKIPPED,
                "reason": "OTLP HTTP logs not implemented in Step 18", "exported_count": 0}


def get_otel_exporter(exporter_name: str) -> Any:
    exporters = {
        "disabled": DisabledOTelExporter(),
        "mock": MockOTelExporter(),
        "otlp_http": OTLPHttpExporterSkeleton(),
    }
    return exporters.get(exporter_name, DisabledOTelExporter())
