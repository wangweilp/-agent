"""Production Observability Foundation — Step 23.

Unified metrics registry providing Counter, Gauge, Histogram primitives.
Thread-safe. Collectable. Exportable to Prometheus text format.

Default: all metrics disabled unless PROMETHEUS_ENABLED=true.
"""
from __future__ import annotations

import logging
import threading
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)


class Metric:
    """Base metric with labels support."""

    def __init__(self, name: str, description: str = "", labels: dict[str, str] | None = None):
        self.name = name
        self.description = description
        self.labels = labels or {}

    def _make_key(self, extra_labels: dict[str, str] | None = None) -> str:
        merged = {**self.labels, **(extra_labels or {})}
        if not merged:
            return self.name
        return f"{self.name}{{{','.join(f'{k}={v}' for k, v in sorted(merged.items()))}}}"


class Counter(Metric):
    """Monotonically increasing counter. Thread-safe."""

    def __init__(self, name: str, description: str = "", labels: dict[str, str] | None = None):
        super().__init__(name, description, labels)
        self._value: float = 0.0
        self._lock = threading.Lock()

    def inc(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value += amount

    def value(self) -> float:
        return self._value

    def reset(self) -> None:
        with self._lock:
            self._value = 0.0


class Gauge(Metric):
    """Point-in-time gauge. Thread-safe."""

    def __init__(self, name: str, description: str = "", labels: dict[str, str] | None = None):
        super().__init__(name, description, labels)
        self._value: float = 0.0
        self._lock = threading.Lock()

    def set(self, value: float) -> None:
        with self._lock:
            self._value = value

    def inc(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value += amount

    def dec(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value -= amount

    def value(self) -> float:
        return self._value

    def reset(self) -> None:
        with self._lock:
            self._value = 0.0


class Histogram(Metric):
    """Value distribution with configurable buckets. Thread-safe."""

    DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

    def __init__(self, name: str, description: str = "", labels: dict[str, str] | None = None,
                 buckets: tuple[float, ...] | None = None):
        super().__init__(name, description, labels)
        self._buckets = tuple(sorted(buckets or self.DEFAULT_BUCKETS))
        self._count: int = 0
        self._sum: float = 0.0
        self._bucket_counts: dict[float, int] = {b: 0 for b in self._buckets}
        self._lock = threading.Lock()

    def observe(self, value: float) -> None:
        with self._lock:
            self._count += 1
            self._sum += value
            for b in self._buckets:
                if value <= b:
                    self._bucket_counts[b] += 1

    def count(self) -> int:
        return self._count

    def sum(self) -> float:
        return self._sum

    def buckets(self) -> list[tuple[float, int]]:
        return sorted(self._bucket_counts.items())

    def reset(self) -> None:
        with self._lock:
            self._count = 0
            self._sum = 0.0
            self._bucket_counts = {b: 0 for b in self._buckets}


class MetricsRegistry:
    """Global metrics registry. Collects and exports all registered metrics."""

    def __init__(self):
        self._metrics: dict[str, Metric] = {}
        self._lock = threading.Lock()

    def register(self, metric: Metric) -> Metric:
        with self._lock:
            self._metrics[metric.name] = metric
        return metric

    def counter(self, name: str, description: str = "", labels: dict[str, str] | None = None) -> Counter:
        with self._lock:
            existing = self._metrics.get(name)
            if isinstance(existing, Counter):
                return existing
            c = Counter(name, description, labels)
            self._metrics[name] = c
        return c

    def gauge(self, name: str, description: str = "", labels: dict[str, str] | None = None) -> Gauge:
        with self._lock:
            existing = self._metrics.get(name)
            if isinstance(existing, Gauge):
                return existing
            g = Gauge(name, description, labels)
            self._metrics[name] = g
        return g

    def histogram(self, name: str, description: str = "",
                  labels: dict[str, str] | None = None,
                  buckets: tuple[float, ...] | None = None) -> Histogram:
        with self._lock:
            existing = self._metrics.get(name)
            if isinstance(existing, Histogram):
                return existing
            h = Histogram(name, description, labels, buckets)
            self._metrics[name] = h
        return h

    def get(self, name: str) -> Metric | None:
        return self._metrics.get(name)

    def list_all(self) -> dict[str, Metric]:
        return dict(self._metrics)

    def reset_all(self) -> None:
        with self._lock:
            for m in self._metrics.values():
                if hasattr(m, 'reset'):
                    m.reset()

    def export_prometheus_text(self) -> str:
        """Export all metrics in Prometheus text format."""
        lines: list[str] = []
        with self._lock:
            for name, m in sorted(self._metrics.items()):
                safe_name = name.replace("-", "_").replace(".", "_").replace(" ", "_")
                if m.description:
                    lines.append(f"# HELP {safe_name} {m.description}")
                if isinstance(m, Counter):
                    lines.append(f"# TYPE {safe_name} counter")
                    lines.append(f"{safe_name} {m.value()}")
                elif isinstance(m, Gauge):
                    lines.append(f"# TYPE {safe_name} gauge")
                    lines.append(f"{safe_name} {m.value()}")
                elif isinstance(m, Histogram):
                    lines.append(f"# TYPE {safe_name} histogram")
                    lines.append(f"{safe_name}_count {m.count()}")
                    lines.append(f"{safe_name}_sum {m.sum()}")
                    for b, c in m.buckets():
                        lines.append(f'{safe_name}_bucket{{le="{b}"}} {c}')
                    lines.append(f'{safe_name}_bucket{{le="+Inf"}} {m.count()}')
        if not lines:
            return "# No metrics registered\n"
        return "\n".join(lines) + "\n"

    def export_json(self) -> dict[str, Any]:
        """Export all metrics as JSON."""
        result: dict[str, Any] = {}
        with self._lock:
            for name, m in self._metrics.items():
                if isinstance(m, Counter):
                    result[name] = {"type": "counter", "value": m.value()}
                elif isinstance(m, Gauge):
                    result[name] = {"type": "gauge", "value": m.value()}
                elif isinstance(m, Histogram):
                    result[name] = {
                        "type": "histogram", "count": m.count(), "sum": m.sum(),
                        "buckets": {str(b): c for b, c in m.buckets()},
                    }
        return result


# ── Global Singleton ──

_registry: MetricsRegistry | None = None
_registry_lock = threading.Lock()


def get_metrics_registry() -> MetricsRegistry:
    """Get or create the global metrics registry."""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = MetricsRegistry()
    return _registry


def reset_metrics_registry() -> None:
    global _registry
    _registry = MetricsRegistry()
