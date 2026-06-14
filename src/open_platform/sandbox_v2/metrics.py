"""Sandbox v2 Metrics Collector — Step 15 指标采集。

从 SQLite/local store 聚合指标，支持 Prometheus text + JSON 导出。
不依赖外部 Prometheus，不访问外网。
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from src.open_platform.sandbox_v2.models import (
    SandboxV2MetricName, SandboxV2MetricType, SandboxV2MetricsSnapshot, SandboxV2MetricSample,
)

logger = logging.getLogger(__name__)

_SENSITIVE_LABEL_KEYS = frozenset({"secret", "token", "key", "password", "dsn", "credential", "access_key", "secret_key"})


class SandboxV2MetricsCollector:

    def __init__(self, store: Any = None):
        self._store = store

    def _safe_label(self, k: str, v: str) -> str:
        k_lower = k.lower()
        for sk in _SENSITIVE_LABEL_KEYS:
            if sk in k_lower:
                return "[REDACTED]"
        return v

    def collect_all(self, organization_id: str = "", workspace_id: str = "") -> dict[str, Any]:
        samples: list[SandboxV2MetricSample] = []
        now = datetime.now(timezone.utc)
        org = organization_id; ws = workspace_id

        # Job metrics
        try:
            if self._store:
                jobs = self._store.list_jobs(organization_id=org or None, workspace_id=ws or None, limit=1000)
                created = sum(1 for j in jobs if getattr(j, 'status', '') == 'created')
                completed = sum(1 for j in jobs if getattr(j, 'status', '') in ('completed',))
                failed = sum(1 for j in jobs if getattr(j, 'status', '') in ('failed', 'dead_letter'))
                canceled = sum(1 for j in jobs if getattr(j, 'status', '') == 'canceled')
                samples.append(_sample(SandboxV2MetricName.JOBS_CREATED, SandboxV2MetricType.COUNTER, created, org, ws, now))
                samples.append(_sample(SandboxV2MetricName.JOBS_COMPLETED, SandboxV2MetricType.COUNTER, completed, org, ws, now))
                samples.append(_sample(SandboxV2MetricName.JOBS_FAILED, SandboxV2MetricType.COUNTER, failed, org, ws, now))
                samples.append(_sample(SandboxV2MetricName.JOBS_CANCELED, SandboxV2MetricType.COUNTER, canceled, org, ws, now))
        except Exception as e:
            logger.warning(f"Job metrics collection failed: {e}")

        # Queue
        try:
            if self._store:
                list_q = getattr(self._store, 'list_queue_items', getattr(self._store, 'list_queue', None))
                queue_items = list_q(status=None, limit=1000) if callable(list_q) else []
                dl = getattr(self._store, 'list_dead_letter', lambda limit: [])() if callable(getattr(self._store, 'list_dead_letter', None)) else []
                samples.append(_sample(SandboxV2MetricName.QUEUE_DEPTH, SandboxV2MetricType.GAUGE, len(queue_items), org, ws, now))
                samples.append(_sample(SandboxV2MetricName.QUEUE_DEAD_LETTER, SandboxV2MetricType.COUNTER, len(dl), org, ws, now))
        except Exception as e:
            logger.warning(f"Queue metrics: {e}")

        # Workers
        try:
            if self._store:
                workers = self._store.list_worker_heartbeats(limit=10) if hasattr(self._store, 'list_worker_heartbeats') else []
                if workers:
                    latest = max((getattr(w, 'last_heartbeat_at', None) for w in workers),
                                key=lambda x: x.isoformat() if hasattr(x, 'isoformat') else "")
                    if latest and hasattr(latest, 'isoformat'):
                        age = (datetime.now(timezone.utc) - latest).total_seconds()
                        samples.append(_sample(SandboxV2MetricName.WORKER_HEARTBEAT_AGE, SandboxV2MetricType.GAUGE, age, org, ws, now))
        except Exception as e:
            logger.warning(f"Worker metrics: {e}")

        # Security
        try:
            if self._store:
                audit_events = self._store.list_security_audit_events(organization_id=org or None, workspace_id=ws or None, limit=1000)
                cross_denied = sum(1 for e in audit_events if getattr(e, 'event_type', '') == 'cross_tenant_denied')
                access_denied = sum(1 for e in audit_events if getattr(e, 'event_type', '') == 'access_denied')
                chain_fails = sum(1 for e in audit_events if getattr(e, 'event_type', '') == 'audit_chain_fail')
                samples.append(_sample(SandboxV2MetricName.CROSS_TENANT_DENIED, SandboxV2MetricType.COUNTER, cross_denied, org, ws, now))
                samples.append(_sample(SandboxV2MetricName.ACCESS_DENIED, SandboxV2MetricType.COUNTER, access_denied, org, ws, now))
                samples.append(_sample(SandboxV2MetricName.AUDIT_CHAIN_FAIL, SandboxV2MetricType.COUNTER, chain_fails, org, ws, now))
        except Exception as e:
            logger.warning(f"Security metrics: {e}")

        # Kill
        try:
            if self._store:
                krs = self._store.list_kill_requests(job_id=None, status=None, limit=1000)
                rejected = sum(1 for k in krs if getattr(k, 'status', '') == 'rejected')
                samples.append(_sample(SandboxV2MetricName.KILL_REQUESTS, SandboxV2MetricType.COUNTER, len(krs), org, ws, now))
                samples.append(_sample(SandboxV2MetricName.KILL_REJECTED, SandboxV2MetricType.COUNTER, rejected, org, ws, now))
        except Exception as e:
            logger.warning(f"Kill metrics: {e}")

        # Network
        try:
            if self._store:
                nets = self._store.list_network_egress_requests(job_id=None, limit=1000)
                denied = sum(1 for n in nets if getattr(n, 'status', '') == 'rejected')
                samples.append(_sample(SandboxV2MetricName.NETWORK_PREFLIGHT, SandboxV2MetricType.COUNTER, len(nets), org, ws, now))
                samples.append(_sample(SandboxV2MetricName.NETWORK_DENIED, SandboxV2MetricType.COUNTER, denied, org, ws, now))
        except Exception as e:
            logger.warning(f"Network metrics: {e}")

        # MicroVM
        import platform as _plat
        if _plat.system() != "Linux":
            samples.append(_sample(SandboxV2MetricName.MICROVM_UNAVAILABLE, SandboxV2MetricType.GAUGE, 1.0, org, ws, now))
        else:
            samples.append(_sample(SandboxV2MetricName.MICROVM_UNAVAILABLE, SandboxV2MetricType.GAUGE, 0.0, org, ws, now))

        # Container
        import shutil
        has_container = shutil.which("docker") or shutil.which("podman")
        if not has_container:
            samples.append(_sample(SandboxV2MetricName.CONTAINER_UNAVAILABLE, SandboxV2MetricType.GAUGE, 1.0, org, ws, now))
        else:
            samples.append(_sample(SandboxV2MetricName.CONTAINER_UNAVAILABLE, SandboxV2MetricType.GAUGE, 0.0, org, ws, now))

        # Backend
        try:
            from src.open_platform.sandbox_v2.config import load_sandbox_v2_settings
            settings = load_sandbox_v2_settings()
            blockers = settings.backend_blockers()
            samples.append(_sample(SandboxV2MetricName.BACKEND_BLOCKERS, SandboxV2MetricType.GAUGE, len(blockers), org, ws, now))
        except Exception:
            pass

        # Performance / Capacity
        try:
            if self._store and hasattr(self._store, "list_benchmark_results"):
                bench = self._store.list_benchmark_results(limit=100)
                failures = sum(1 for r in bench if getattr(r, "status", "") == "failed")
                samples.append(_sample(SandboxV2MetricName.BENCHMARK_RESULTS, SandboxV2MetricType.COUNTER, len(bench), org, ws, now))
                samples.append(_sample(SandboxV2MetricName.BENCHMARK_FAILURES, SandboxV2MetricType.COUNTER, failures, org, ws, now))
            if self._store and hasattr(self._store, "get_latest_capacity_estimate"):
                capacity = self._store.get_latest_capacity_estimate()
                if capacity:
                    samples.append(_sample(
                        SandboxV2MetricName.CAPACITY_JOBS_PER_MINUTE,
                        SandboxV2MetricType.GAUGE,
                        getattr(capacity, "estimated_jobs_per_minute", 0.0),
                        org,
                        ws,
                        now,
                    ))
        except Exception as e:
            logger.warning(f"Performance metrics: {e}")

        return {
            "counters": {},
            "gauges": {s.name: s.value for s in samples},
            "samples": [s.to_dict() for s in samples],
        }

    def create_snapshot(self, organization_id: str = "", workspace_id: str = "") -> SandboxV2MetricsSnapshot:
        data = self.collect_all(organization_id, workspace_id)
        snap = SandboxV2MetricsSnapshot(
            organization_id=organization_id, workspace_id=workspace_id,
            counters=data["counters"], gauges=data["gauges"],
            health={}, warnings=[], blockers=[],
        )
        if self._store:
            try:
                self._store.create_metrics_snapshot(snap)
                for s in data.get("samples", []):
                    sample = SandboxV2MetricSample(
                        name=s["name"], metric_type=s.get("metric_type", "gauge"),
                        value=s.get("value", 0), organization_id=organization_id,
                        workspace_id=workspace_id,
                    )
                    self._store.create_metric_sample(sample)
            except Exception as e:
                logger.warning(f"Failed to persist metrics snapshot: {e}")
        return snap

    def export_prometheus_text(self, organization_id: str = "", workspace_id: str = "") -> str:
        data = self.collect_all(organization_id, workspace_id)
        lines: list[str] = []
        for s in data.get("samples", []):
            name = _safe_metric_name(s.get("name", "unknown"))
            value = s.get("value", 0)
            metric_type = s.get("metric_type", "gauge")
            lines.append(f"# HELP sandbox_v2_{name} Sandbox v2 {name}")
            lines.append(f"# TYPE sandbox_v2_{name} {metric_type}")
            labels_str = ""
            labels = s.get("labels", {})
            if labels:
                label_parts = [f'{k}="{v}"' for k, v in labels.items() if not any(sk in k.lower() for sk in _SENSITIVE_LABEL_KEYS)]
                if label_parts:
                    labels_str = "{" + ",".join(label_parts) + "}"
            lines.append(f"sandbox_v2_{name}{labels_str} {value}")
        return "\n".join(lines) + "\n"

    def export_json(self, organization_id: str = "", workspace_id: str = "") -> dict[str, Any]:
        import json
        snap = self.create_snapshot(organization_id, workspace_id)
        return snap.to_dict()


def _sample(name: str, metric_type: str, value: float, org: str, ws: str, now: datetime) -> SandboxV2MetricSample:
    return SandboxV2MetricSample(name=name, metric_type=metric_type, value=float(value),
                                  organization_id=org, workspace_id=ws, collected_at=now)


def _safe_metric_name(name: str) -> str:
    return name.replace("-", "_").replace(".", "_")
