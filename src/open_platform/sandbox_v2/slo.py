"""Sandbox v2 SLO Service — Step 19.

SLO definitions, evaluation, and summary.
基于 load test results + capacity plans 评估。
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any

from src.open_platform.sandbox_v2.models import (
    SandboxV2SLODefinition,
    SandboxV2SLOEvaluation,
    SandboxV2SLOStatus,
    SandboxV2LoadTestResult,
    SandboxV2LoadTestTarget,
)

logger = logging.getLogger(__name__)

_DEFAULT_SLOS: list[dict[str, Any]] = [
    {"name": "readiness-p95", "description": "Runtime readiness p95 latency",
     "target": SandboxV2LoadTestTarget.READINESS, "p95_ms": 500, "p99_ms": 1000,
     "error_rate_percent": 1.0, "availability_percent": 99.0},
    {"name": "metrics-p95", "description": "Metrics snapshot p95 latency",
     "target": SandboxV2LoadTestTarget.METRICS, "p95_ms": 800, "p99_ms": 1500,
     "error_rate_percent": 1.0, "availability_percent": 99.0},
    {"name": "health-p95", "description": "Health check p95 latency",
     "target": SandboxV2LoadTestTarget.HEALTH, "p95_ms": 1000, "p99_ms": 2000,
     "error_rate_percent": 1.0, "availability_percent": 99.0},
    {"name": "network-preflight-p95", "description": "Network preflight p95 latency",
     "target": SandboxV2LoadTestTarget.NETWORK_PREFLIGHT, "p95_ms": 200, "p99_ms": 500,
     "error_rate_percent": 1.0, "availability_percent": 99.0},
    {"name": "security-access-p95", "description": "Security access evaluate p95 latency",
     "target": SandboxV2LoadTestTarget.SECURITY_ACCESS, "p95_ms": 100, "p99_ms": 300,
     "error_rate_percent": 1.0, "availability_percent": 99.0},
    {"name": "global-error-rate", "description": "Overall error rate",
     "target": "global", "p95_ms": 5000, "p99_ms": 5000,
     "error_rate_percent": 1.0, "availability_percent": 99.0},
    {"name": "load-test-availability", "description": "Load test endpoint availability",
     "target": "global", "p95_ms": 5000, "p99_ms": 5000,
     "error_rate_percent": 5.0, "availability_percent": 99.0},
]


class SandboxV2SLOService:
    """SLO 定义与评估服务。"""

    def __init__(self, store: Any = None):
        self._store = store

    @staticmethod
    def get_default_slo_definitions() -> list[dict[str, Any]]:
        return list(_DEFAULT_SLOS)

    def create_slo_definition(self, **kwargs) -> SandboxV2SLODefinition:
        slo = SandboxV2SLODefinition(**kwargs)
        if self._store:
            try:
                self._store.create_slo_definition(slo)
            except Exception as e:
                logger.warning(f"Failed to persist SLO definition: {e}")
        return slo

    def list_slo_definitions(self, enabled: bool | None = None, limit: int = 100) -> list[SandboxV2SLODefinition]:
        if not self._store:
            return []
        try:
            return self._store.list_slo_definitions(enabled=enabled, limit=limit)
        except Exception:
            return []

    def evaluate_load_test_against_slo(
        self, result: SandboxV2LoadTestResult, slo_defs: list[SandboxV2SLODefinition] | None = None,
    ) -> list[SandboxV2SLOEvaluation]:
        evaluations: list[SandboxV2SLOEvaluation] = []
        defs = slo_defs or []

        for slo_def in defs:
            if not slo_def.enabled:
                continue
            # Match target
            if slo_def.target != "global" and slo_def.target != result.target:
                continue

            status = SandboxV2SLOStatus.NOT_EVALUATED
            reason_parts: list[str] = []

            # p95 check
            if result.p95_ms > slo_def.p95_ms:
                reason_parts.append(f"p95 {result.p95_ms}ms > SLO {slo_def.p95_ms}ms")
                status = SandboxV2SLOStatus.FAILED
            # p99 check
            elif result.p99_ms > slo_def.p99_ms:
                reason_parts.append(f"p99 {result.p99_ms}ms > SLO {slo_def.p99_ms}ms")
                status = SandboxV2SLOStatus.FAILED
            # Error rate check
            if result.error_rate_percent > slo_def.error_rate_percent:
                reason_parts.append(f"error_rate {result.error_rate_percent}% > SLO {slo_def.error_rate_percent}%")
                status = SandboxV2SLOStatus.FAILED
            # Availability check
            observed_avail = 100.0 - result.error_rate_percent
            if observed_avail < slo_def.availability_percent:
                reason_parts.append(f"availability {observed_avail}% < SLO {slo_def.availability_percent}%")
                status = SandboxV2SLOStatus.FAILED

            if status == SandboxV2SLOStatus.NOT_EVALUATED:
                status = SandboxV2SLOStatus.PASSED
                reason_parts.append("All SLO targets met")

            evaluation = SandboxV2SLOEvaluation(
                slo_id=slo_def.slo_id, load_test_id=result.load_test_id,
                status=status, target=result.target,
                observed_p95_ms=result.p95_ms, observed_p99_ms=result.p99_ms,
                observed_error_rate_percent=result.error_rate_percent,
                observed_availability_percent=observed_avail,
                reason="; ".join(reason_parts),
                evaluated_at=datetime.now(timezone.utc),
            )

            if self._store:
                try:
                    self._store.create_slo_evaluation(evaluation)
                except Exception as e:
                    logger.warning(f"Failed to persist SLO evaluation: {e}")

            evaluations.append(evaluation)

        return evaluations

    def list_slo_evaluations(self, load_test_id: str = "", slo_id: str = "",
                             limit: int = 100) -> list[SandboxV2SLOEvaluation]:
        if not self._store:
            return []
        try:
            return self._store.list_slo_evaluations(load_test_id=load_test_id or None,
                                                    slo_id=slo_id or None, limit=limit)
        except Exception:
            return []

    def generate_slo_summary(self, evaluations: list[SandboxV2SLOEvaluation]) -> dict[str, Any]:
        if not evaluations:
            return {"passed": 0, "failed": 0, "warning": 0, "not_evaluated": 0, "total": 0}
        passed = sum(1 for e in evaluations if e.status == SandboxV2SLOStatus.PASSED)
        failed = sum(1 for e in evaluations if e.status == SandboxV2SLOStatus.FAILED)
        warning = sum(1 for e in evaluations if e.status == SandboxV2SLOStatus.WARNING)
        not_eval = sum(1 for e in evaluations if e.status == SandboxV2SLOStatus.NOT_EVALUATED)
        return {"passed": passed, "failed": failed, "warning": warning,
                "not_evaluated": not_eval, "total": len(evaluations)}

    def get_slo_readiness(self) -> dict[str, Any]:
        try:
            defs = self.list_slo_definitions()
        except Exception:
            defs = []
        return {
            "slo_definitions": len(defs) > 0,
            "slo_evaluation": True,
            "default_slos_count": len(_DEFAULT_SLOS),
            "stored_slos_count": len(defs),
        }
