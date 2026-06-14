"""Sandbox v2 Load Testing — Step 19.

Local dry-run + optional staging load test.
默认不访问任何网络资源。
只有显式 env 开启 staging 后才请求 STAGING_BASE_URL。
"""
from __future__ import annotations
import json
import logging
import math
import os
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from src.open_platform.sandbox_v2.models import (
    SandboxV2LoadTestConfig,
    SandboxV2LoadTestResult,
    SandboxV2LoadTestStatus,
    SandboxV2LoadTestTarget,
    SandboxV2LoadTestProfile,
    SandboxV2SLOStatus,
    SandboxV2SLOEvaluation,
    SandboxV2SLODefinition,
    SandboxV2CapacityPlan,
)

logger = logging.getLogger(__name__)

_PROFILE_LIMITS: dict[str, dict[str, int]] = {
    "smoke": {"max_users": 5, "max_rps": 5, "duration": 30, "timeout": 5},
    "staging_small": {"max_users": 10, "max_rps": 10, "duration": 60, "timeout": 10},
    "staging_medium": {"max_users": 20, "max_rps": 20, "duration": 120, "timeout": 15},
    "production_readonly": {"max_users": 5, "max_rps": 5, "duration": 30, "timeout": 5},
    "custom": {"max_users": 5, "max_rps": 5, "duration": 30, "timeout": 5},
}

_PRODUCTION_PATTERNS = frozenset({
    ".prod.", ".production.", "prod.", "api.prod", "live.", "app.prod",
})


class SandboxV2LoadTester:
    """Sandbox v2 负载测试器。"""

    def __init__(self, store: Any = None, service: Any = None, settings: Any = None):
        self._store = store
        self._service = service
        self._settings = settings

    def _get_settings(self) -> Any:
        if self._settings:
            return self._settings
        try:
            from src.open_platform.sandbox_v2.config import load_sandbox_v2_settings
            return load_sandbox_v2_settings()
        except Exception:
            return None

    # ── Validation ──

    @staticmethod
    def validate_load_test_config(config: SandboxV2LoadTestConfig) -> dict[str, Any]:
        blockers: list[str] = []
        warnings: list[str] = []

        if config.max_users < 1:
            blockers.append("max_users must be >= 1")
        if config.max_rps < 1:
            blockers.append("max_rps must be >= 1")
        if config.duration_seconds < 1:
            blockers.append("duration_seconds must be >= 1")

        limits = _PROFILE_LIMITS.get(config.profile, _PROFILE_LIMITS["smoke"])
        if config.max_users > limits["max_users"]:
            blockers.append(f"max_users={config.max_users} exceeds profile limit {limits['max_users']}")
        if config.max_rps > limits["max_rps"]:
            blockers.append(f"max_rps={config.max_rps} exceeds profile limit {limits['max_rps']}")
        if config.duration_seconds > limits["duration"]:
            blockers.append(f"duration={config.duration_seconds}s exceeds profile limit {limits['duration']}s")

        # Hard safety limits
        if config.max_users > 48:
            blockers.append(f"max_users={config.max_users} exceeds absolute max 48")
        if config.max_rps > 48:
            blockers.append(f"max_rps={config.max_rps} exceeds absolute max 48")
        if config.duration_seconds > 3600:
            blockers.append(f"duration={config.duration_seconds}s exceeds absolute max 3600s")

        return {"valid": len(blockers) == 0, "blockers": blockers, "warnings": warnings}

    @staticmethod
    def is_production_url(url: str) -> bool:
        if not url:
            return False
        lowered = url.lower()
        for pat in _PRODUCTION_PATTERNS:
            if pat in lowered:
                return True
        return False

    @staticmethod
    def is_allowed_staging_url(url: str) -> bool:
        if not url:
            return False
        lowered = url.lower()
        allowed_prefixes = ("http://localhost", "http://127.0.0.1", "http://0.0.0.0",
                           "https://localhost", "https://127.0.0.1")
        if lowered.startswith(allowed_prefixes):
            return True
        # Allow staging subdomains
        for staging_kw in (".staging.", ".dev.", ".test.", ".internal."):
            if staging_kw in lowered:
                return True
        return False

    def create_load_test_config(self, **kwargs) -> SandboxV2LoadTestConfig:
        s = self._get_settings()
        config = SandboxV2LoadTestConfig(
            profile=kwargs.get("profile", getattr(s, "load_test_profile", "smoke") if s else "smoke"),
            base_url_masked=kwargs.get("base_url_masked", getattr(s, "staging_base_url", "") if s else ""),
            targets=kwargs.get("targets", getattr(s, "load_test_targets", []) if s else []),
            max_users=kwargs.get("max_users", getattr(s, "load_test_max_users", 5) if s else 5),
            max_rps=kwargs.get("max_rps", getattr(s, "load_test_max_rps", 5) if s else 5),
            duration_seconds=kwargs.get("duration_seconds", getattr(s, "load_test_duration_seconds", 30) if s else 30),
            timeout_seconds=kwargs.get("timeout_seconds", getattr(s, "load_test_timeout_seconds", 5) if s else 5),
            allow_production=kwargs.get("allow_production", getattr(s, "load_test_allow_production", False) if s else False),
            require_confirmation=kwargs.get("require_confirmation", getattr(s, "load_test_require_confirmation", True) if s else True),
            organization_id=kwargs.get("organization_id", ""),
            workspace_id=kwargs.get("workspace_id", ""),
            metadata=kwargs.get("metadata", {}),
        )
        if self._store:
            try:
                self._store.create_load_test_config(config)
            except Exception as e:
                logger.warning(f"Failed to persist config: {e}")
        return config

    # ── Local Dry-Run ──

    def run_local_dry_run(self, config: SandboxV2LoadTestConfig) -> dict[str, Any]:
        """本地 dry-run — 只调用本地 service，不访问外部 URL。"""
        results: list[SandboxV2LoadTestResult] = []
        self._service_provided = self._service

        for target_name in (config.targets or ["readiness"]):
            t0 = time.time()
            try:
                result = self._run_target_local(target_name, config)
            except Exception as e:
                result = SandboxV2LoadTestResult(
                    load_test_id=config.load_test_id, target=target_name,
                    status=SandboxV2LoadTestStatus.FAILED,
                    finished_at=datetime.now(timezone.utc),
                    warnings=[f"Local dry-run failed: {e}"],
                )
            if result.started_at and result.finished_at:
                result.duration_ms = int((result.finished_at - result.started_at).total_seconds() * 1000)
            else:
                result.finished_at = datetime.now(timezone.utc)
                result.duration_ms = int((time.time() - t0) * 1000)
            results.append(result)

            if self._store:
                try:
                    self._store.create_load_test_result(result)
                except Exception:
                    pass

        return {
            "load_test_id": config.load_test_id,
            "mode": "local_dry_run",
            "profile": config.profile,
            "targets": config.targets,
            "results": [r.to_dict() for r in results],
            "summary": self._summarize(results),
        }

    def _run_target_local(self, target: str, config: SandboxV2LoadTestConfig) -> SandboxV2LoadTestResult:
        result = SandboxV2LoadTestResult(
            load_test_id=config.load_test_id, target=target,
            status=SandboxV2LoadTestStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )

        # Simulate multiple requests locally
        latencies: list[float] = []
        total = min(config.max_rps, 10)
        successes = 0
        failures = 0

        for _ in range(total):
            t0 = time.time()
            ok = self._call_local_target(target)
            lat = (time.time() - t0) * 1000
            latencies.append(lat)
            if ok:
                successes += 1
            else:
                failures += 1
            time.sleep(0.001)

        result.finished_at = datetime.now(timezone.utc)
        result.total_requests = total
        result.success_count = successes
        result.failure_count = failures
        result.status = SandboxV2LoadTestStatus.COMPLETED if failures == 0 else SandboxV2LoadTestStatus.COMPLETED

        stats = compute_latency_stats(latencies)
        result.p50_ms = stats["p50"]
        result.p95_ms = stats["p95"]
        result.p99_ms = stats["p99"]
        result.min_ms = stats["min"]
        result.max_ms = stats["max"]
        result.error_rate_percent = (failures / total * 100) if total > 0 else 0
        elapsed = (result.finished_at - result.started_at).total_seconds()
        result.requests_per_second = total / elapsed if elapsed > 0 else 0
        return result

    def _call_local_target(self, target: str) -> bool:
        """Local target call — uses service, no HTTP."""
        svc = self._service
        if not svc:
            return True  # no service: simulate ok
        try:
            if target == SandboxV2LoadTestTarget.READINESS:
                if hasattr(svc, 'get_performance_readiness'):
                    svc.get_performance_readiness()
                return True
            elif target == SandboxV2LoadTestTarget.METRICS:
                if hasattr(svc, 'get_observability_readiness'):
                    svc.get_observability_readiness()
                return True
            elif target == SandboxV2LoadTestTarget.HEALTH:
                return True
            elif target == SandboxV2LoadTestTarget.NETWORK_PREFLIGHT:
                return True
            elif target == SandboxV2LoadTestTarget.SECURITY_ACCESS:
                return True
            elif target == SandboxV2LoadTestTarget.OBSERVABILITY:
                if hasattr(svc, 'get_observability_readiness'):
                    svc.get_observability_readiness()
                return True
            else:
                return True
        except Exception:
            return False

    # ── Staging Load Test ──

    def run_staging_load_test(self, config: SandboxV2LoadTestConfig,
                              base_url: str = "", token: str = "") -> dict[str, Any]:
        """Staging load test — makes HTTP requests to staging URL."""
        if not base_url:
            return {"error": "No staging base URL configured", "status": "blocked"}

        s = self._get_settings()
        allow_prod = config.allow_production or (getattr(s, 'load_test_allow_production', False) if s else False)

        if self.is_production_url(base_url) and not allow_prod:
            return {"error": "Production URL blocked. Set allow_production=true only in staging.", "status": "blocked"}

        if not self.is_allowed_staging_url(base_url) and not allow_prod:
            return {"error": "External/unknown URL blocked. Only localhost, staging, or dev URLs allowed unless allow_production=true.", "status": "blocked"}

        # Only import requests when actually running staging
        try:
            import requests
        except ImportError:
            return {"error": "requests library not available — install to run staging load test", "status": "skipped"}

        results: list[dict[str, Any]] = []
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        for target in (config.targets or ["readiness"]):
            url = f"{base_url.rstrip('/')}/api/runtime/sandbox-v2/{target.replace('_', '-')}"
            latencies: list[float] = []
            successes = 0; failures = 0; timeouts = 0
            total = min(config.max_rps, 10)

            for _ in range(total):
                t0 = time.time()
                try:
                    resp = requests.get(url, timeout=config.timeout_seconds, headers=headers)
                    lat = (time.time() - t0) * 1000
                    latencies.append(lat)
                    if resp.status_code < 500:
                        successes += 1
                    else:
                        failures += 1
                except requests.Timeout:
                    timeouts += 1
                except Exception:
                    failures += 1
                time.sleep(0.05)

            stats = compute_latency_stats(latencies) if latencies else {"p50": 0, "p95": 0, "p99": 0, "min": 0, "max": 0}
            results.append({
                "target": target, "total_requests": total,
                "success_count": successes, "failure_count": failures,
                "timeout_count": timeouts,
                "p50_ms": stats["p50"], "p95_ms": stats["p95"], "p99_ms": stats["p99"],
                "min_ms": stats["min"], "max_ms": stats["max"],
            })

        return {"load_test_id": config.load_test_id, "mode": "staging", "results": results,
                "summary": self._summarize_staging(results)}

    # ── Staging summarization
    def _summarize_staging(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        if not results:
            return {}
        total_req = sum(r.get("total_requests", 0) for r in results)
        total_ok = sum(r.get("success_count", 0) for r in results)
        total_fail = sum(r.get("failure_count", 0) for r in results)
        return {"total_requests": total_req, "success_count": total_ok,
                "failure_count": total_fail, "error_rate_percent": round((total_fail / total_req * 100), 1) if total_req else 0}

    # ── Summarization ──

    @staticmethod
    def _summarize(results: list[SandboxV2LoadTestResult]) -> dict[str, Any]:
        if not results:
            return {}
        total = sum(r.total_requests for r in results)
        ok = sum(r.success_count for r in results)
        fail = sum(r.failure_count for r in results)
        return {
            "total_requests": total, "success_count": ok, "failure_count": fail,
            "error_rate_percent": round((fail / total * 100), 1) if total else 0,
            "overall_status": "completed" if fail == 0 else "completed_with_failures",
        }

    # ── Capacity Plan ──

    def generate_capacity_plan(self) -> SandboxV2CapacityPlan:
        s = self._get_settings()
        profile = getattr(s, 'perf_profile', 'small') if s else 'small'
        plan = SandboxV2CapacityPlan(
            recommended_profile=profile,
            recommended_backend=getattr(s, 'database_backend', 'sqlite') if s else 'sqlite',
            recommended_workers=2,
            recommended_queue_backend="redis" if profile in ("medium", "large") else "sqlite",
            recommended_object_storage="minio" if profile in ("medium", "large") else "local",
            expected_daily_jobs=1000 if profile == "small" else 10000 if profile == "medium" else 50000,
            expected_peak_rps=5.0 if profile == "small" else 20.0 if profile == "medium" else 100.0,
            bottlenecks=["SQLite write contention (multi-worker)"] if profile in ("medium", "large") else [],
            scaling_recommendations=self._scaling_recos(profile),
            risk_notes=self._risk_notes(profile),
        )
        if self._store:
            try:
                self._store.create_capacity_plan(plan)
            except Exception:
                pass
        return plan

    @staticmethod
    def _scaling_recos(profile: str) -> list[str]:
        if profile == "small":
            return ["SQLite OK for single-worker", "Consider Redis for 4+ workers"]
        elif profile in ("medium", "large"):
            return ["Use PostgreSQL", "Use Redis queue", "Use MinIO/S3 for artifacts",
                    "Deploy 4-8 workers", "Add load balancer"]
        return ["Smoke profile — no scaling needed"]

    @staticmethod
    def _risk_notes(profile: str) -> list[str]:
        return ["Load test results are synthetic estimates"] if profile == "smoke" else [
            "Staging load test may not match production traffic patterns",
            "Monitor real SLO in production before scaling",
        ]

    # ── Reports ──

    def export_load_test_report_json(self, load_test_id: str) -> dict[str, Any]:
        results = self._list_results(load_test_id)
        config = self._get_config(load_test_id)
        return {
            "load_test_id": load_test_id,
            "profile": config.profile if config else "",
            "targets": config.targets if config else [],
            "results": [r.to_dict() for r in results],
            "summary": self._summarize(results),
        }

    def export_load_test_report_markdown(self, load_test_id: str) -> str:
        data = self.export_load_test_report_json(load_test_id)
        lines = [f"# Sandbox v2 Load Test Report", f"", f"**Load Test ID:** {load_test_id}",
                 f"**Profile:** {data.get('profile', '')}", f"**Targets:** {', '.join(data.get('targets', []))}",
                 f"", f"## Results", f""]
        for r in data.get("results", []):
            lines.append(f"- **{r.get('target', '?')}**: {r.get('status')}, "
                         f"p50={r.get('p50_ms')}ms, p95={r.get('p95_ms')}ms, p99={r.get('p99_ms')}ms")
        s = data.get("summary", {})
        lines.append(f""); lines.append(f"## Summary")
        lines.append(f"Total: {s.get('total_requests', 0)}, OK: {s.get('success_count', 0)}, "
                      f"Failed: {s.get('failure_count', 0)}, Error %: {s.get('error_rate_percent', 0)}")
        return "\n".join(lines)

    def _list_results(self, load_test_id: str) -> list[SandboxV2LoadTestResult]:
        if not self._store:
            return []
        try:
            return self._store.list_load_test_results(load_test_id=load_test_id, limit=100)
        except Exception:
            return []

    def _get_config(self, load_test_id: str) -> SandboxV2LoadTestConfig | None:
        if not self._store:
            return None
        try:
            return self._store.get_load_test_config(load_test_id)
        except Exception:
            return None


# ── Stat helpers ──

def compute_latency_stats(latencies: list[float]) -> dict[str, float]:
    if not latencies:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "min": 0.0, "max": 0.0, "avg": 0.0}
    sorted_lat = sorted(latencies)
    n = len(sorted_lat)
    return {
        "p50": _percentile(sorted_lat, 0.50),
        "p95": _percentile(sorted_lat, 0.95),
        "p99": _percentile(sorted_lat, 0.99),
        "min": round(sorted_lat[0], 2),
        "max": round(sorted_lat[-1], 2),
        "avg": round(sum(sorted_lat) / n, 2),
    }


def compute_error_rate(success: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round((total - success) / total * 100, 2)


def _percentile(sorted_data: list[float], pct: float) -> float:
    if not sorted_data:
        return 0.0
    index = (len(sorted_data) - 1) * pct
    lower = int(index)
    upper = min(lower + 1, len(sorted_data) - 1)
    weight = index - lower
    return round(sorted_data[lower] * (1 - weight) + sorted_data[upper] * weight, 2)
