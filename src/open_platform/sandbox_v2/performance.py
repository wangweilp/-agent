"""Sandbox v2 performance and capacity benchmark helpers.

Step 16 builds a safe benchmark control plane only:
- synthetic fixture only
- no user code execution
- no external network requests
- no container or MicroVM startup
- no third-party load testing
"""

from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from src.open_platform.sandbox_v2.config import SandboxV2Settings, load_sandbox_v2_settings
from src.open_platform.sandbox_v2.models import (
    SandboxArtifact,
    SandboxJob,
    SandboxKillRequest,
    SandboxPackageQuarantineRecord,
    SandboxPackageRequest,
    SandboxV2ArtifactStatus,
    SandboxV2ArtifactType,
    SandboxV2BenchmarkConfig,
    SandboxV2BenchmarkResult,
    SandboxV2BenchmarkStatus,
    SandboxV2BenchmarkTarget,
    SandboxV2CapacityEstimate,
    SandboxV2Decision,
    SandboxV2JobStatus,
    SandboxV2Mode,
    SandboxNetworkEgressRequest,
    SandboxV2PackageManager,
    SandboxV2PackageQuarantineStatus,
    SandboxV2PackageRequestStatus,
    SandboxV2PackageSourceType,
    SandboxV2PerformanceProfile,
)


DEFAULT_TARGETS: tuple[str, ...] = (
    SandboxV2BenchmarkTarget.JOBS,
    SandboxV2BenchmarkTarget.QUEUE,
    SandboxV2BenchmarkTarget.WORKER,
    SandboxV2BenchmarkTarget.ARTIFACTS,
    SandboxV2BenchmarkTarget.PACKAGES,
    SandboxV2BenchmarkTarget.NETWORK,
    SandboxV2BenchmarkTarget.KILL_SWITCH,
    SandboxV2BenchmarkTarget.SECURITY_AUDIT,
    SandboxV2BenchmarkTarget.METRICS,
    SandboxV2BenchmarkTarget.ALERTS,
)

PROFILE_LIMITS: dict[str, dict[str, int]] = {
    SandboxV2PerformanceProfile.SMOKE: {
        "max_jobs": 3, "max_queue_items": 3, "max_artifacts": 2,
        "max_concurrency": 1, "timeout_seconds": 10,
    },
    SandboxV2PerformanceProfile.SMALL: {
        "max_jobs": 25, "max_queue_items": 25, "max_artifacts": 10,
        "max_concurrency": 2, "timeout_seconds": 30,
    },
    SandboxV2PerformanceProfile.MEDIUM: {
        "max_jobs": 100, "max_queue_items": 100, "max_artifacts": 50,
        "max_concurrency": 4, "timeout_seconds": 60,
    },
    SandboxV2PerformanceProfile.LARGE: {
        "max_jobs": 250, "max_queue_items": 250, "max_artifacts": 100,
        "max_concurrency": 8, "timeout_seconds": 120,
    },
    SandboxV2PerformanceProfile.CUSTOM: {
        "max_jobs": 10, "max_queue_items": 10, "max_artifacts": 5,
        "max_concurrency": 1, "timeout_seconds": 30,
    },
}

FORBIDDEN_METADATA_KEYS = frozenset({
    "command", "cmd", "args", "argv", "shell", "subprocess",
    "artifact_path", "path", "host_path", "mount", "url", "external_url",
    "container", "image", "docker", "podman", "microvm", "firecracker",
})
SENSITIVE_METADATA_KEYS = frozenset({
    "password", "secret", "token", "key", "credential", "dsn",
    "access_key", "secret_key", "api_key",
})


class SandboxV2PerformanceBenchmark:
    """Safe synthetic benchmark runner for Sandbox v2 internal control paths."""

    def __init__(
        self,
        *,
        store: Any,
        queue: Any = None,
        service: Any = None,
        artifact_store: Any = None,
        package_store: Any = None,
        network_service: Any = None,
        settings: SandboxV2Settings | None = None,
    ):
        self._store = store
        self._queue = queue
        self._service = service
        self._artifact_store = artifact_store
        self._package_store = package_store
        self._network_service = network_service
        self._settings = settings or load_sandbox_v2_settings()

    def create_benchmark_config(
        self,
        *,
        profile: str | None = None,
        targets: list[str] | None = None,
        max_jobs: int | None = None,
        max_queue_items: int | None = None,
        max_artifacts: int | None = None,
        max_concurrency: int | None = None,
        timeout_seconds: int | None = None,
        cleanup_after_run: bool | None = None,
        organization_id: str = "",
        workspace_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> SandboxV2BenchmarkConfig:
        selected_profile = str(profile or self._settings.perf_profile or SandboxV2PerformanceProfile.SMALL)
        self._validate_profile(selected_profile)
        selected_targets = self._validate_targets(targets or list(DEFAULT_TARGETS))
        safe_metadata = self._safe_metadata(metadata or {})
        limits = PROFILE_LIMITS[selected_profile]
        cfg = SandboxV2BenchmarkConfig(
            profile=selected_profile,
            targets=selected_targets,
            max_jobs=self._bounded_int(max_jobs, limits["max_jobs"], self._settings.perf_max_jobs, "max_jobs"),
            max_queue_items=self._bounded_int(
                max_queue_items, limits["max_queue_items"], self._settings.perf_max_queue_items, "max_queue_items"
            ),
            max_artifacts=self._bounded_int(
                max_artifacts, limits["max_artifacts"], self._settings.perf_max_artifacts, "max_artifacts"
            ),
            max_concurrency=self._bounded_int(
                max_concurrency, limits["max_concurrency"], self._settings.perf_max_concurrency, "max_concurrency"
            ),
            timeout_seconds=self._bounded_int(
                timeout_seconds, limits["timeout_seconds"], self._settings.perf_timeout_seconds, "timeout_seconds"
            ),
            cleanup_after_run=self._settings.perf_cleanup_after_run if cleanup_after_run is None else bool(cleanup_after_run),
            organization_id=organization_id,
            workspace_id=workspace_id,
            metadata={
                **safe_metadata,
                "synthetic_fixture_only": True,
                "no_user_code": True,
                "no_external_network": True,
                "no_container": True,
                "no_microvm": True,
                "test_run_id": f"sbxperf_{uuid4().hex[:12]}",
            },
        )
        if self._store and hasattr(self._store, "create_benchmark_config"):
            self._store.create_benchmark_config(cfg)
        return cfg

    def run_jobs_benchmark(self, config: SandboxV2BenchmarkConfig) -> SandboxV2BenchmarkResult:
        return self._time_operations(
            config,
            SandboxV2BenchmarkTarget.JOBS,
            self._operation_count(config, "max_jobs"),
            lambda i: self._create_synthetic_job(config, i),
        )

    def run_queue_benchmark(self, config: SandboxV2BenchmarkConfig) -> SandboxV2BenchmarkResult:
        if not self._queue:
            return self._skipped(config, SandboxV2BenchmarkTarget.QUEUE, "Queue backend is not configured.")

        def _op(i: int) -> bool:
            job = self._create_synthetic_job(config, i)
            item = self._queue.enqueue(
                job_id=job.job_id,
                organization_id=config.organization_id,
                workspace_id=config.workspace_id,
                priority=100,
                max_attempts=1,
            )
            leased = self._queue.lease_next(f"sbxperf-worker-{config.benchmark_id}", lease_seconds=1)
            if leased:
                self._queue.acknowledge(leased.queue_id)
            return bool(item and leased)

        return self._time_operations(
            config, SandboxV2BenchmarkTarget.QUEUE,
            self._operation_count(config, "max_queue_items"), _op,
        )

    def run_worker_benchmark(self, config: SandboxV2BenchmarkConfig) -> SandboxV2BenchmarkResult:
        if not self._queue or not self._service:
            return self._skipped(config, SandboxV2BenchmarkTarget.WORKER, "Queue or service is not configured.")

        def _op(i: int) -> bool:
            from src.open_platform.sandbox_v2.worker import SandboxV2Worker

            job = self._create_synthetic_job(config, i)
            self._queue.enqueue(job_id=job.job_id, priority=100, max_attempts=1)
            worker = SandboxV2Worker(
                queue=self._queue,
                service=self._service,
                worker_id=f"sbxperf-worker-{i}",
                timeout_seconds=1,
                lease_seconds=1,
            )
            result = worker.run_once()
            return result is not None

        return self._time_operations(
            config, SandboxV2BenchmarkTarget.WORKER,
            min(3, self._operation_count(config, "max_queue_items")), _op,
            warnings=["worker run-once keeps policy fail-closed; rejected jobs are valid safe outcomes"],
        )

    def run_artifact_benchmark(self, config: SandboxV2BenchmarkConfig) -> SandboxV2BenchmarkResult:
        def _op(i: int) -> bool:
            content = f"synthetic sandbox v2 artifact {i}\n".encode("utf-8")
            artifact = None
            if self._artifact_store:
                artifact = self._artifact_store.create_artifact(
                    job_id=f"sbxperf_job_{i}",
                    organization_id=config.organization_id,
                    workspace_id=config.workspace_id,
                    artifact_type=SandboxV2ArtifactType.TEXT,
                    name=f"synthetic-{i}.txt",
                    original_filename=f"synthetic-{i}.txt",
                    content=content,
                    read_only=True,
                    metadata=self._synthetic_metadata(config),
                )
            if artifact is None:
                artifact = SandboxArtifact(
                    job_id=f"sbxperf_job_{i}",
                    organization_id=config.organization_id,
                    workspace_id=config.workspace_id,
                    artifact_type=SandboxV2ArtifactType.TEXT,
                    name=f"synthetic-{i}.txt",
                    original_filename=f"synthetic-{i}.txt",
                    safe_filename=f"synthetic-{i}.txt",
                    storage_key=f"synthetic/{config.benchmark_id}/{i}",
                    size_bytes=len(content),
                    mime_type="text/plain",
                    status=SandboxV2ArtifactStatus.MATERIALIZED,
                    read_only=True,
                    metadata=self._synthetic_metadata(config),
                )
            self._store.create_artifact(artifact)
            return True

        return self._time_operations(
            config, SandboxV2BenchmarkTarget.ARTIFACTS,
            self._operation_count(config, "max_artifacts"), _op,
        )

    def run_package_benchmark(self, config: SandboxV2BenchmarkConfig) -> SandboxV2BenchmarkResult:
        def _op(i: int) -> bool:
            req = SandboxPackageRequest(
                job_id=f"sbxperf_job_{i}",
                organization_id=config.organization_id,
                workspace_id=config.workspace_id,
                requested_by="sandbox_v2_performance",
                package_name=f"synthetic-package-{i}",
                package_version="0.0.0",
                package_manager=SandboxV2PackageManager.PIP,
                source_url="offline://synthetic-fixture",
                source_type=SandboxV2PackageSourceType.OFFLINE_UPLOAD,
                requested_action="metadata_only",
                status=SandboxV2PackageRequestStatus.POLICY_CHECKED,
                metadata=self._synthetic_metadata(config),
            )
            self._store.create_package_request(req)
            quarantine = SandboxPackageQuarantineRecord(
                package_request_id=req.package_request_id,
                job_id=req.job_id,
                organization_id=config.organization_id,
                workspace_id=config.workspace_id,
                package_name=req.package_name,
                package_version=req.package_version,
                package_manager=req.package_manager,
                storage_key=f"synthetic/{config.benchmark_id}/{i}",
                size_bytes=32,
                sha256="0" * 64,
                status=SandboxV2PackageQuarantineStatus.QUARANTINED,
                metadata=self._synthetic_metadata(config),
            )
            self._store.create_quarantine_record(quarantine)
            return True

        return self._time_operations(
            config, SandboxV2BenchmarkTarget.PACKAGES,
            min(config.max_jobs, 10), _op,
        )

    def run_network_preflight_benchmark(self, config: SandboxV2BenchmarkConfig) -> SandboxV2BenchmarkResult:
        def _op(i: int) -> bool:
            if self._network_service:
                result = self._network_service.evaluate_egress_policy(
                    url="https://synthetic.invalid/preflight",
                    scheme="https",
                    hostname="synthetic.invalid",
                    port=443,
                    resolved_ips=["203.0.113.10"],
                    purpose="synthetic benchmark preflight only",
                )
                return "no_real_network" in result or "decision" in result
            from src.open_platform.sandbox_v2.network_policy import evaluate_egress_policy

            req = SandboxNetworkEgressRequest(
                url="https://synthetic.invalid/preflight",
                scheme="https",
                hostname="synthetic.invalid",
                port=443,
                resolved_ips=["203.0.113.10"],
                purpose="synthetic benchmark preflight only",
            )
            decision = evaluate_egress_policy(req)
            return bool(decision.fail_closed or not decision.allowed or decision.allowed)

        return self._time_operations(
            config, SandboxV2BenchmarkTarget.NETWORK,
            min(config.max_jobs, 20), _op,
            warnings=["network target performs policy preflight only; no socket or HTTP request is made"],
        )

    def run_kill_switch_benchmark(self, config: SandboxV2BenchmarkConfig) -> SandboxV2BenchmarkResult:
        def _op(i: int) -> bool:
            job = self._create_synthetic_job(config, i)
            if self._service:
                result = self._service.cancel_job(job.job_id)
                return bool(result.get("canceled") is not None or result.get("status"))
            req = SandboxKillRequest(
                job_id=job.job_id,
                organization_id=config.organization_id,
                workspace_id=config.workspace_id,
                requested_by="sandbox_v2_performance",
                reason="synthetic benchmark cancel request; no process kill",
                metadata=self._synthetic_metadata(config),
            )
            self._store.create_kill_request(req)
            return True

        return self._time_operations(
            config, SandboxV2BenchmarkTarget.KILL_SWITCH,
            min(config.max_jobs, 10), _op,
            warnings=["kill target updates sandbox-managed state only; no PID/container kill is attempted"],
        )

    def run_security_audit_benchmark(self, config: SandboxV2BenchmarkConfig) -> SandboxV2BenchmarkResult:
        def _op(i: int) -> bool:
            from src.open_platform.sandbox_v2.security_audit import SandboxV2SecurityAuditService

            audit = SandboxV2SecurityAuditService(store=self._store)
            event = audit.create_audit_event(
                event_type="benchmark_operation",
                severity="info",
                principal_id="sandbox_v2_performance",
                organization_id=config.organization_id,
                workspace_id=config.workspace_id,
                resource_type="benchmark",
                resource_id=config.benchmark_id,
                action="run",
                decision=SandboxV2Decision.ALLOW,
                reason="synthetic benchmark audit event",
                metadata={"target": "security_audit", "sequence": i},
            )
            return bool(event.audit_event_id)

        return self._time_operations(
            config, SandboxV2BenchmarkTarget.SECURITY_AUDIT,
            min(config.max_jobs, 20), _op,
        )

    def run_metrics_collection_benchmark(self, config: SandboxV2BenchmarkConfig) -> SandboxV2BenchmarkResult:
        def _op(i: int) -> bool:
            from src.open_platform.sandbox_v2.metrics import SandboxV2MetricsCollector

            data = SandboxV2MetricsCollector(store=self._store).collect_all(
                organization_id=config.organization_id,
                workspace_id=config.workspace_id,
            )
            return "samples" in data

        return self._time_operations(
            config, SandboxV2BenchmarkTarget.METRICS,
            min(5, config.max_jobs), _op,
        )

    def run_alert_evaluation_benchmark(self, config: SandboxV2BenchmarkConfig) -> SandboxV2BenchmarkResult:
        def _op(i: int) -> bool:
            from src.open_platform.sandbox_v2.alerts import SandboxV2AlertEngine

            engine = SandboxV2AlertEngine(store=self._store)
            alerts = engine.evaluate_all({"queue_depth": 0, "network_denied_total": 0})
            return isinstance(alerts, list) and len(alerts) <= 10

        return self._time_operations(
            config, SandboxV2BenchmarkTarget.ALERTS,
            min(5, config.max_jobs), _op,
            warnings=["alert target uses bounded synthetic metrics and does not send external notifications"],
        )

    def run_end_to_end_benchmark(self, config: SandboxV2BenchmarkConfig) -> SandboxV2BenchmarkResult:
        def _op(i: int) -> bool:
            self._create_synthetic_job(config, i)
            if self._network_service:
                self._network_service.evaluate_egress_policy(
                    url="https://synthetic.invalid/preflight",
                    scheme="https",
                    hostname="synthetic.invalid",
                    port=443,
                    resolved_ips=["203.0.113.10"],
                )
            from src.open_platform.sandbox_v2.metrics import SandboxV2MetricsCollector
            from src.open_platform.sandbox_v2.alerts import SandboxV2AlertEngine

            metrics = SandboxV2MetricsCollector(store=self._store).collect_all()
            SandboxV2AlertEngine(store=self._store).evaluate_all(metrics.get("gauges", {}))
            return True

        return self._time_operations(
            config, SandboxV2BenchmarkTarget.END_TO_END,
            min(3, config.max_jobs), _op,
            warnings=["end_to_end target is a synthetic control-plane path, not production load testing"],
        )

    def run_all(self, config: SandboxV2BenchmarkConfig) -> dict[str, Any]:
        results: list[SandboxV2BenchmarkResult] = []
        dispatch: dict[str, Callable[[SandboxV2BenchmarkConfig], SandboxV2BenchmarkResult]] = {
            SandboxV2BenchmarkTarget.JOBS: self.run_jobs_benchmark,
            SandboxV2BenchmarkTarget.QUEUE: self.run_queue_benchmark,
            SandboxV2BenchmarkTarget.WORKER: self.run_worker_benchmark,
            SandboxV2BenchmarkTarget.ARTIFACTS: self.run_artifact_benchmark,
            SandboxV2BenchmarkTarget.PACKAGES: self.run_package_benchmark,
            SandboxV2BenchmarkTarget.NETWORK: self.run_network_preflight_benchmark,
            SandboxV2BenchmarkTarget.KILL_SWITCH: self.run_kill_switch_benchmark,
            SandboxV2BenchmarkTarget.SECURITY_AUDIT: self.run_security_audit_benchmark,
            SandboxV2BenchmarkTarget.METRICS: self.run_metrics_collection_benchmark,
            SandboxV2BenchmarkTarget.ALERTS: self.run_alert_evaluation_benchmark,
            SandboxV2BenchmarkTarget.END_TO_END: self.run_end_to_end_benchmark,
        }
        for target in config.targets:
            fn = dispatch.get(str(target))
            if not fn:
                result = self._skipped(config, str(target), f"Unknown benchmark target: {target}")
            else:
                try:
                    result = fn(config)
                except Exception as exc:
                    result = self._failed(config, str(target), str(exc))
            if self._store and hasattr(self._store, "create_benchmark_result"):
                self._store.create_benchmark_result(result)
            results.append(result)

        estimate = self.estimate_capacity(config.profile, results)
        if self._store and hasattr(self._store, "create_capacity_estimate"):
            self._store.create_capacity_estimate(estimate)
        cleanup = self.cleanup_benchmark_data(config) if config.cleanup_after_run else {"cleanup": "disabled"}
        return {
            "benchmark_id": config.benchmark_id,
            "profile": config.profile,
            "targets": config.targets,
            "results": [r.to_dict() for r in results],
            "capacity_estimate": estimate.to_dict(),
            "cleanup": cleanup,
            "warnings": sorted({w for r in results for w in r.warnings}),
            "blockers": sorted({b for r in results for b in r.blockers}),
        }

    def compute_latency_stats(self, latency_ms: list[float]) -> dict[str, float]:
        if not latency_ms:
            return {"p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0}
        ordered = sorted(float(v) for v in latency_ms)

        def pct(p: float) -> float:
            idx = max(0, min(len(ordered) - 1, math.ceil((p / 100.0) * len(ordered)) - 1))
            return round(ordered[idx], 3)

        return {"p50_ms": pct(50), "p95_ms": pct(95), "p99_ms": pct(99)}

    def estimate_capacity(
        self,
        profile: str,
        results: list[SandboxV2BenchmarkResult],
    ) -> SandboxV2CapacityEstimate:
        by_target = {r.target: r for r in results}

        def per_min(target: str) -> float:
            result = by_target.get(target)
            if not result:
                return 0.0
            return round(max(result.ops_per_second, 0.0) * 60.0, 2)

        bottlenecks: list[str] = []
        if by_target.get(SandboxV2BenchmarkTarget.QUEUE) and by_target.get(SandboxV2BenchmarkTarget.JOBS):
            if per_min(SandboxV2BenchmarkTarget.QUEUE) < per_min(SandboxV2BenchmarkTarget.JOBS):
                bottlenecks.append("queue lease throughput is below job metadata creation throughput")
        if any(r.status == SandboxV2BenchmarkStatus.SKIPPED for r in results):
            bottlenecks.append("one or more targets were skipped because local dependencies were not configured")
        if profile in (SandboxV2PerformanceProfile.SMOKE, SandboxV2PerformanceProfile.SMALL):
            bottlenecks.append("sample size is intentionally small; do not infer production SLOs")

        recommendations = [
            "Keep ordinary pytest on smoke/small limits; never run large benchmarks by default.",
            "Move sustained job/metadata benchmarks to PostgreSQL before production capacity claims.",
            "Move distributed queue lease benchmarks to Redis before multi-worker rollout.",
            "Use MinIO/S3 for artifact-heavy capacity validation.",
        ]
        return SandboxV2CapacityEstimate(
            profile=profile,
            estimated_jobs_per_minute=per_min(SandboxV2BenchmarkTarget.JOBS),
            estimated_queue_items_per_minute=per_min(SandboxV2BenchmarkTarget.QUEUE),
            estimated_artifact_metadata_per_minute=per_min(SandboxV2BenchmarkTarget.ARTIFACTS),
            estimated_network_preflight_per_minute=per_min(SandboxV2BenchmarkTarget.NETWORK),
            bottlenecks=bottlenecks,
            recommendations=recommendations,
            metadata={
                "synthetic_fixture_only": True,
                "external_load_testing": False,
                "user_code_benchmarking": False,
            },
        )

    def cleanup_benchmark_data(self, config: SandboxV2BenchmarkConfig) -> dict[str, Any]:
        return {
            "cleanup": "metadata-isolated",
            "test_run_id": config.metadata.get("test_run_id", ""),
            "reason": "Benchmark-created records are tagged with test_run_id; no destructive cleanup required.",
        }

    def export_report_json(
        self,
        config: SandboxV2BenchmarkConfig,
        results: list[SandboxV2BenchmarkResult] | None = None,
        capacity: SandboxV2CapacityEstimate | None = None,
    ) -> dict[str, Any]:
        results = results if results is not None else self._load_results(config.benchmark_id)
        capacity = capacity or self._load_capacity()
        return {
            "benchmark": config.to_dict(),
            "results": [r.to_dict() for r in results],
            "capacity_estimate": capacity.to_dict() if capacity else None,
            "safety": {
                "synthetic_fixture_only": True,
                "external_load_testing": False,
                "user_code_benchmarking": False,
                "container_benchmarking": False,
                "microvm_benchmarking": False,
            },
        }

    def export_report_markdown(
        self,
        config: SandboxV2BenchmarkConfig,
        results: list[SandboxV2BenchmarkResult] | None = None,
        capacity: SandboxV2CapacityEstimate | None = None,
    ) -> str:
        report = self.export_report_json(config, results, capacity)
        lines = [
            f"# Sandbox v2 Benchmark Report: {config.benchmark_id}",
            "",
            f"- Profile: `{config.profile}`",
            "- Scope: synthetic fixture only; no user code, external network, containers, or MicroVMs",
            "",
            "| Target | Status | Ops | Success | Failure | p50 ms | p95 ms | p99 ms | ops/s |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for r in report["results"]:
            lines.append(
                f"| {r['target']} | {r['status']} | {r['total_operations']} | "
                f"{r['success_count']} | {r['failure_count']} | {r['p50_ms']} | "
                f"{r['p95_ms']} | {r['p99_ms']} | {r['ops_per_second']} |"
            )
        cap = report.get("capacity_estimate") or {}
        if cap:
            lines.extend([
                "",
                "## Capacity Estimate",
                f"- Jobs/min: {cap.get('estimated_jobs_per_minute', 0)}",
                f"- Queue items/min: {cap.get('estimated_queue_items_per_minute', 0)}",
                f"- Artifact metadata/min: {cap.get('estimated_artifact_metadata_per_minute', 0)}",
                f"- Network preflight/min: {cap.get('estimated_network_preflight_per_minute', 0)}",
                "",
                "## Recommendations",
            ])
            lines.extend(f"- {item}" for item in cap.get("recommendations", []))
        return "\n".join(lines) + "\n"

    def _time_operations(
        self,
        config: SandboxV2BenchmarkConfig,
        target: str,
        count: int,
        fn: Callable[[int], bool],
        warnings: list[str] | None = None,
    ) -> SandboxV2BenchmarkResult:
        started = datetime.now(timezone.utc)
        start_perf = time.perf_counter()
        latencies: list[float] = []
        success = 0
        failure = 0
        blockers: list[str] = []
        warning_list = list(warnings or [])
        if count >= 50:
            warning_list.append("rate guard active: operation count is bounded by profile/env limits")
        deadline = start_perf + max(1, config.timeout_seconds)
        for i in range(max(0, count)):
            if time.perf_counter() > deadline:
                blockers.append("benchmark timeout reached")
                break
            op_start = time.perf_counter()
            try:
                ok = bool(fn(i))
                if ok:
                    success += 1
                else:
                    failure += 1
            except Exception as exc:
                failure += 1
                blockers.append(str(exc)[:160])
            latencies.append((time.perf_counter() - op_start) * 1000.0)
        finished = datetime.now(timezone.utc)
        duration_ms = max(0, int((time.perf_counter() - start_perf) * 1000))
        total = success + failure
        stats = self.compute_latency_stats(latencies)
        status = SandboxV2BenchmarkStatus.COMPLETED if failure == 0 and not blockers else SandboxV2BenchmarkStatus.FAILED
        return SandboxV2BenchmarkResult(
            benchmark_id=config.benchmark_id,
            target=target,
            status=status,
            started_at=started,
            finished_at=finished,
            duration_ms=duration_ms,
            total_operations=total,
            success_count=success,
            failure_count=failure,
            p50_ms=stats["p50_ms"],
            p95_ms=stats["p95_ms"],
            p99_ms=stats["p99_ms"],
            ops_per_second=round((total / max(duration_ms / 1000.0, 0.001)), 3),
            warnings=warning_list,
            blockers=blockers,
            metadata=self._synthetic_metadata(config),
        )

    def _create_synthetic_job(self, config: SandboxV2BenchmarkConfig, sequence: int) -> SandboxJob:
        job = SandboxJob(
            organization_id=config.organization_id,
            workspace_id=config.workspace_id,
            agent_id="sandbox_v2_performance",
            requested_by="sandbox_v2_performance",
            mode=SandboxV2Mode.METADATA_ONLY,
            status=SandboxV2JobStatus.POLICY_CHECKED,
            requested_action="synthetic_metadata_only_benchmark",
            input_ref=f"synthetic://benchmark/{config.benchmark_id}/{sequence}",
            policy_snapshot={"synthetic_fixture_only": True},
            risk_level="low",
            metadata={**self._synthetic_metadata(config), "sequence": sequence},
        )
        self._store.create_job(job)
        return job

    def _operation_count(self, config: SandboxV2BenchmarkConfig, field_name: str) -> int:
        value = int(getattr(config, field_name, 1) or 1)
        profile_limit = PROFILE_LIMITS.get(str(config.profile), PROFILE_LIMITS[SandboxV2PerformanceProfile.SMALL]).get(field_name, value)
        return max(1, min(value, profile_limit))

    def _bounded_int(self, value: int | None, profile_default: int, env_max: int, name: str) -> int:
        selected = int(profile_default if value is None else value)
        if selected < 1:
            raise ValueError(f"{name} must be >= 1")
        hard_max = max(1, int(env_max or profile_default))
        if selected > hard_max:
            raise ValueError(f"{name} exceeds configured maximum {hard_max}")
        return selected

    def _validate_profile(self, profile: str) -> None:
        if profile not in PROFILE_LIMITS:
            raise ValueError("Invalid benchmark profile.")
        if profile == SandboxV2PerformanceProfile.LARGE and not self._settings.run_performance_benchmarks:
            raise ValueError("large profile is disabled unless SANDBOX_V2_RUN_PERFORMANCE_BENCHMARKS=true")

    def _validate_targets(self, targets: list[str]) -> list[str]:
        valid = {str(t) for t in SandboxV2BenchmarkTarget}
        clean: list[str] = []
        for target in targets:
            t = str(target)
            if t not in valid:
                raise ValueError(f"Invalid benchmark target: {target}")
            clean.append(t)
        return clean or [SandboxV2BenchmarkTarget.JOBS]

    def _safe_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        clean: dict[str, Any] = {}
        for key, value in metadata.items():
            key_lower = str(key).lower()
            if any(k in key_lower for k in SENSITIVE_METADATA_KEYS):
                raise ValueError("benchmark metadata must not contain sensitive keys")
            if key_lower in FORBIDDEN_METADATA_KEYS:
                raise ValueError("benchmark config must not accept user command, URL, path, container, or MicroVM input")
            if isinstance(value, str) and ("http://" in value.lower() or "https://" in value.lower()):
                raise ValueError("benchmark metadata must not contain external URLs")
            if isinstance(value, (dict, list)):
                encoded = json.dumps(value, ensure_ascii=False)
                if any(k in encoded.lower() for k in ("http://", "https://", "secret", "token", "password")):
                    raise ValueError("benchmark metadata contains disallowed nested content")
            clean[str(key)] = value
        return clean

    def _synthetic_metadata(self, config: SandboxV2BenchmarkConfig) -> dict[str, Any]:
        return {
            "benchmark_id": config.benchmark_id,
            "test_run_id": config.metadata.get("test_run_id", ""),
            "synthetic_fixture_only": True,
            "no_user_code": True,
            "no_external_network": True,
            "no_container": True,
            "no_microvm": True,
        }

    def _skipped(self, config: SandboxV2BenchmarkConfig, target: str, reason: str) -> SandboxV2BenchmarkResult:
        now = datetime.now(timezone.utc)
        return SandboxV2BenchmarkResult(
            benchmark_id=config.benchmark_id,
            target=target,
            status=SandboxV2BenchmarkStatus.SKIPPED,
            started_at=now,
            finished_at=now,
            warnings=[reason],
            metadata=self._synthetic_metadata(config),
        )

    def _failed(self, config: SandboxV2BenchmarkConfig, target: str, reason: str) -> SandboxV2BenchmarkResult:
        now = datetime.now(timezone.utc)
        return SandboxV2BenchmarkResult(
            benchmark_id=config.benchmark_id,
            target=target,
            status=SandboxV2BenchmarkStatus.FAILED,
            started_at=now,
            finished_at=now,
            failure_count=1,
            blockers=[reason[:160]],
            metadata=self._synthetic_metadata(config),
        )

    def _load_results(self, benchmark_id: str) -> list[SandboxV2BenchmarkResult]:
        if self._store and hasattr(self._store, "list_benchmark_results"):
            return self._store.list_benchmark_results(benchmark_id=benchmark_id, limit=100)
        return []

    def _load_capacity(self) -> SandboxV2CapacityEstimate | None:
        if self._store and hasattr(self._store, "get_latest_capacity_estimate"):
            return self._store.get_latest_capacity_estimate()
        return None
